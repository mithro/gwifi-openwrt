#!/usr/bin/env python3
"""DEBOUNCE-TIMING lever — targets the pd_task timing branches (usb_pd_protocol.c:2051
`if (get_time().val < pd[port].cc_debounce) break;` and :1690 `if (get_time().val < pd[port].src_recover)`)
which need the SAME branch evaluated BOTH with time < deadline (break/wait) AND time >= deadline
(proceed). Short coarse RunFors land on one side only. Here each CC transition / hard-reset is followed
by MANY small RunFor steps that straddle the debounce/recover deadline, so the pd_task loop re-wakes and
re-evaluates the branch on both sides. Sink + source roles. Genuine execution. RO + RW.
Accumulates tmp/debounce_edges.pkl.
Usage: uv run --python .venv python cov_debounce.py [rw]
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
    trace = os.path.join(TMP, "debounce.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def step(n=40, dt="0.01"):
        # many small RunFor steps so the pd_task loop re-wakes repeatedly and re-evaluates the debounce/
        # recover comparison on BOTH sides of its deadline (time < then >= cc_debounce / src_recover).
        return ['emulation RunFor "%s"' % dt] * n

    def fire_react(t="0.1"):
        f = []
        for _ in range(4):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trdb" @%s PC' % trace]

    # SINK CC debounce: connect/disconnect, each straddled by fine steps across the debounce deadline
    for _ in range(4):
        c += ['sysbus.adc ForceSourceCc false'] + step(50, "0.008")     # disconnect -> SNK debounce window
        c += ['sysbus.adc ForceSourceCc true'] + step(50, "0.008")      # reconnect -> debounce window
    # SOURCE CC debounce + src_recover: PartnerSink, dualrole source, hard reset (recover timer), fine steps
    c += ['sysbus.adc PartnerSink true'] + cc("pd dualrole source") + step(40, "0.01")
    for _ in range(3):
        c += ['sysbus.adc PartnerSink false'] + step(50, "0.008")       # source disconnect -> SRC debounce
        c += ['sysbus.adc PartnerSink true'] + step(50, "0.008")
    # source hard reset -> SRC_HARD_RESET_RECOVER -> src_recover deadline straddled by fine steps
    for _ in range(3):
        c += cc("pd 0 hard") + step(60, "0.008")
    # DRP toggle (both roles auto-toggling) with fine steps across the toggle/debounce deadlines
    c += cc("pd dualrole toggle") + step(80, "0.01")
    c += cc("pd dualrole on") + step(60, "0.01")
    # interleave a contract so the debounce checks in the connected states also run
    c += ['sysbus.adc ForceSourceCc true'] + cc("pd dualrole sink")
    for mid in (1, 2):
        c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
        for i in range(8):
            c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.SRC_CAP), 'sysbus.dma1 ExpectContractMsg']
        c += fire_react("0.2") + step(30, "0.01")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "debounce.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "debounce_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/debounce_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
