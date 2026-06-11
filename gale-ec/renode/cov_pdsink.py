#!/usr/bin/env python3
"""PD-SINK lever — drives gale as a real SINK using the NEW GaleAdc.ForcePartnerSrc knob (a constant
>= PD_SRC_VNC source on CC1: sink sees SNK_3_0, source sees OPEN), set BEFORE boot so gale's FIRST CC
detection is a sink-attach instead of the SRC_ACCESSORY case-closed-debug latch that ForceSourceCc caused
(gale used to boot into SRC_ACCESSORY=17 and never sink-contract; now it reaches the SINK states
SNK_DISCOVERY/SNK_REQUESTED + the SNK hard-reset send/recover loop). Plus VBUS present (ForceRaw=3103 ~5V
on AIN8). Delivers Source_Caps/Accept/PS_RDY + a battery of in-flight PD messages + console pd commands so
the sink-side pd_task arms (handle_data/ctrl_request in sink role, SNK_DISCOVERY/REQUESTED/TRANSITION,
hard-reset send/execute/recover) run. Genuine execution. RO + RW. Accumulates tmp/pdsink_edges.pkl.
Usage: uv run --python .venv python cov_pdsink.py [rw]
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
    trace = os.path.join(TMP, "pdsink.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    def freact(t="0.15"):
        f = []
        for _ in range(4):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]

    # ForcePartnerSrc + VBUS BEFORE boot so gale's first detection is a stable sink-attach. SHORT boot
    # window (0.4s) so SRC_CAP arrives BEFORE gale's SINK_WAIT_CAP timeout -> gale reaches SNK_READY.
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "0.4"']
    if RW:
        c += cc("sysjump rw", "0.4")
        c += ['emulation RunFor "0.4"']
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    # reply slots for sink-initiated swaps / get-sink-cap so the handshakes complete from SNK_READY
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg((pe.header(4, 1, 0), [0x2601912C]))]
    c += ['cpu CreateExecutionTracing "trps" @%s PC' % trace]

    def reattach():
        return ['sysbus.adc ForcePartnerSrc false', 'sysbus.adc ForceRaw 0', 'emulation RunFor "0.4"',
                'sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "0.4"']

    mid = 1
    for cycle in range(3):
        # --- Phase A (HARD-RESET path): SRC_CAP delivered LATE so SINK_WAIT_CAP expires -> the SNK
        # hard-reset send/execute/recover arms (sink-specific, NOT shared with the source path).
        c += reattach() + ['emulation RunFor "1.0"']
        c += deliver(pe.SRC_CAP, "0.2") + deliver(pe.ctrl(13, mid & 7), "0.15"); mid += 1   # late cap + soft reset
        # --- Phase B (SNK_READY path): re-attach, EARLY repeated SRC_CAP -> Accept -> PS_RDY -> SNK_READY(9).
        c += reattach()
        for _ in range(3):
            c += deliver(pe.SRC_CAP, "0.1")
        c += deliver(pe.ACCEPT(mid), "0.15") + deliver(pe.PS_RDY(mid + 1), "0.3"); mid += 2
        # from stable SNK_READY: gale-initiated swaps/VDM (reactive ACK) -> DR_SWAP/PR_SWAP/VCONN/VDM arms
        for act in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn", "pd 0 vdm version", "pd 0 soft"):
            c += cc(act) + freact("0.2") + freact("0.15")
        # partner-initiated in-contract messages -> handle_ctrl/data_request (sink role)
        for ct in (8, 7, 9, 10, 11, 12, 5, 2, 4, 13, 6, 3):
            c += deliver(pe.ctrl(ct, mid & 7), "0.1"); mid += 1
        c += deliver((pe.header(1, 3, mid & 7), [0x22019096, 0x0002D12C, 0x0003C12C]), "0.12"); mid += 1
        c += deliver((pe.header(4, 1, mid & 7), [0x2601912C]), "0.1"); mid += 1
        c += deliver(pe.REQUEST(mid & 7, 1, 250), "0.1"); mid += 1
        for vm in [(pe.header(15, 1, mid & 7), [0xFF008001]), (pe.header(15, 4, mid & 7), [0xFF008042, 1, 2, 3])]:
            c += deliver(vm, "0.12")
        c += cc("pd 0 hard", "0.4")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pdsink.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdsink_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pdsink_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
