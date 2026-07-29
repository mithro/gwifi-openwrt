#!/usr/bin/env python3
"""PD-SOAK lever — one LONG continuous PD session that accumulates state across transitions, to reach
the scattered pd_task branches that short scenarios (which reset each boot) miss: data_role-dependent
arms (usb_pd_protocol.c:1858 `data_role == PD_ROLE_DFP`), the reconnect-after-PD flag
(:1743 PD_FLAGS_PREVIOUS_PD_CONN), and the role-transition / DRP arms. Sequence (all in ONE traced run
with the reactive partner): sink contract -> DR swap (->DFP) -> PR swap (->source) -> hard reset ->
disconnect -> reconnect (PREVIOUS_PD_CONN now set) -> re-contract -> BIST/VDM, repeated. Genuine
execution. RO + RW. Accumulates tmp/pdsoak_edges.pkl.
Usage: uv run --python .venv python cov_pdsoak.py [rw]
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
    trace = os.path.join(TMP, "pdsoak.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.15"):
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
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg((pe.header(4, 1, 0), [0x2601912C]))]
    for slot, ack in ((9, (pe.header(15, 4, 0), [0xFF008042, 0, 0, 0])), (10, (pe.header(15, 1, 0), [0xFF008041])),
                      (11, (pe.header(15, 1, 0), [0xFF008041])), (12, (pe.header(15, 1, 0), [0xFF008041]))):
        c += ['sysbus.dma1 SetReply %d "%s"' % (slot, hexmsg(ack))]
    c += ['cpu CreateExecutionTracing "trps" @%s PC' % trace]

    mid = 1
    for cycle in range(5):
        # (1) sink contract
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid)) + deliver(pe.PS_RDY(mid + 1), "0.25"); mid += 2
        # (2) gale-initiated swaps from READY (reactive partner ACKs) -> DR_SWAP (->DFP), PR_SWAP, VCONN
        for act in ("pd 0 swap data", "pd 0 swap vconn", "pd 0 swap power"):
            c += cc(act) + fire_react("0.2") + fire_react("0.15")
        # (2b) once gale is DFP, run a FULL VDM discovery (vdm_state machine in a live contract)
        for act in ("pd 0 vdm vers", "pd 0 vdm ping 1", "pd 0 vdm curr"):
            c += cc(act) + fire_react("0.2") + fire_react("0.15")
        # (3) partner-initiated swaps + caps requests delivered to gale-in-READY
        for ct in (9, 10, 11, 7, 8, 2, 5, 12, 13):  # DR/PR/VCONN swap, GET_SRC/SNK_CAP, GOTO_MIN, PING, WAIT, SOFT
            c += deliver(pe.ctrl(ct, mid & 7), "0.12"); mid += 1
        # (4) data messages in-contract: re-Source_Cap, Request, Sink_Cap, BIST carrier + test-data
        c += deliver((pe.header(1, 3, mid & 7), [0x22019096, 0x0002D12C, 0x0003C12C]), "0.15"); mid += 1
        c += deliver(pe.REQUEST(mid & 7, 1, 250), "0.15"); mid += 1
        c += deliver((pe.header(4, 1, mid & 7), [0x2601912C]), "0.12"); mid += 1   # Sink_Cap
        c += deliver((pe.header(3, 1, mid & 7), [0x00000000]), "0.12"); mid += 1   # BIST carrier mode 2
        c += deliver((pe.header(3, 1, mid & 7), [0x80000000]), "0.12"); mid += 1   # BIST test data
        # (5) soft reset then hard reset -> recover -> re-contract
        c += cc("pd 0 soft") + fire_react("0.2")
        c += cc("pd 0 hard") + ['emulation RunFor "0.4"']
        # (6) DISCONNECT (CC open) then RECONNECT -> sets PD_FLAGS_PREVIOUS_PD_CONN for next contract
        c += ['sysbus.adc ForceSourceCc false', 'emulation RunFor "0.5"']
        c += ['sysbus.adc ForceSourceCc true', 'emulation RunFor "0.3"']
    # (7) switch to SOURCE role (PartnerSink) for a source-side soak with accumulated PD-conn flag
    c += ['sysbus.adc PartnerSink true'] + cc("pd dualrole source") + ['emulation RunFor "1.0"']
    for mid2 in (3, 4, 5):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(mid2))] + fire_react("0.3")
    # source-READY: gale-initiated + partner-initiated in source role, then disconnect/reconnect cycles
    for act in ("pd 0 swap data", "pd 0 swap power", "pd 0 vdm vers", "pd 0 vdm ping 1",
                "pd 0 soft", "pd 0 state", "pd 0 hard"):
        c += cc(act) + fire_react("0.2")
    for ct in (9, 10, 7, 8, 13, 2):               # partner swap/caps requests to gale-as-source
        c += deliver(pe.ctrl(ct, ct & 7), "0.12")
    for _ in range(3):                             # source disconnect/reconnect (PartnerSink toggle)
        c += ['sysbus.adc PartnerSink false', 'emulation RunFor "0.4"']
        c += ['sysbus.adc PartnerSink true', 'emulation RunFor "0.3"']
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(6))] + fire_react("0.3")
    # back to dual-role toggle / sink to exercise the DRP auto-toggle arms with accumulated flags
    c += cc("pd dualrole toggle") + ['emulation RunFor "0.5"'] + cc("pd dualrole on") + ['emulation RunFor "0.5"']

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pdsoak.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdsoak_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pdsoak_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
