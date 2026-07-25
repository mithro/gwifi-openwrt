#!/usr/bin/env python3
"""VDM-TRANSMIT lever — targets the pd_task VDM-send state machine (usb_pd_protocol.c:1107 switch
(vdm_state) / :1126 res = pd_transmit(SOP, header, vdo_data) + the res<0 / res>=0 handling). Needs gale
as DFP (after a DR swap) with a VDM QUEUED (vdo_count>0), then the transmit covered BOTH ways: SUCCESS
(reactive partner GoodCRCs the VDM TX -> vdm_state advances) and FAILURE (SuppressGoodCrc -> pd_transmit
res<0 -> the error/retry arm). Genuine execution. RO + RW. Accumulates tmp/vdmtx_edges.pkl.
Usage: uv run --python .venv python cov_vdmtx.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C
import pd_encode as pe

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


def hexmsg(m):
    sm = pe.encode_message(*m)
    return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "vdmtx.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def fire_react(t="0.15"):
        f = []
        for _ in range(4):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    # VDM ACK replies (slots 9..12) so a transmitted VDM completes in the SUCCESS phase
    for k, ack in enumerate([(pe.header(15, 4, 0), [0xFF008042, 0x12345678, 0xABCD, 0]),
                             (pe.header(15, 5, 0), [0xFF018043, 1, 2, 3, 4]),
                             (pe.header(15, 1, 0), [0xFF1C8045]),
                             (pe.header(15, 1, 0), [0xFF008041])]):
        c += ['sysbus.dma1 SetReply %d "%s"' % (9 + k, hexmsg(ack))]
    c += ['cpu CreateExecutionTracing "trvt" @%s PC' % trace]

    # reach SNK_READY then DR swap so gale becomes DFP (the VDM-INITIATING role)
    for mid in (1, 2, 3):
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid)) + deliver(pe.PS_RDY(mid + 1), "0.25")
    c += cc("pd 0 swap data") + fire_react("0.2") + fire_react("0.15")     # -> DFP

    # PHASE 1 (VDM TX SUCCEEDS): queue VDM discovery; reactive partner ACKs -> vdm_state machine walks
    for act in ("pd 0 vdm vers", "pd 0 vdm ping 1", "pd 0 vdm curr"):
        c += cc(act) + fire_react("0.2") + fire_react("0.2") + fire_react("0.15")
    # also deliver inbound VDM requests (handle_vdm_request as DFP) + their ACKs
    for vm in [(pe.header(15, 1, 4), [0xFF008001]), (pe.header(15, 4, 5), [0xFF008042, 1, 2, 3]),
               (pe.header(15, 1, 6), [0xFF018000])]:
        c += deliver(vm, "0.15")

    # PHASE 2 (VDM TX FAILS): SuppressGoodCrc -> gale's VDM transmit gets no ACK -> pd_transmit res<0
    c += ['sysbus.dma1 SuppressGoodCrc true', 'sysbus.dma1 ReactiveEnabled false']
    for act in ("pd 0 vdm vers", "pd 0 vdm ping 1", "pd 0 vdm curr"):
        c += cc(act) + ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"', 'emulation RunFor "0.4"']
    c += ['sysbus.dma1 SuppressGoodCrc false', 'sysbus.dma1 ReactiveEnabled true']
    # recover + re-VDM (success again after the failures)
    for act in ("pd 0 soft", "pd 0 vdm vers"):
        c += cc(act) + fire_react("0.2")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "vdmtx.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "vdmtx_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/vdmtx_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
