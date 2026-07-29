#!/usr/bin/env python3
"""CC-STATE / DRP / DISCONNECT lever — targets pd_task sub-clusters per UNCOVERED-BY-FUNCTION.md:
the CC-debounce wait (usb_pd_protocol.c:2051 `if (get_time().val < pd[port].cc_debounce) break`),
try-source DRP (:1563), and the connect/disconnect transitions. The campaign holds a fixed CC level;
here we TOGGLE the emulated CC attach (GaleAdc ForceSourceCc / PartnerSink on<->off) with timing across
the debounce window, drive `pd dualrole toggle/on` (DRP try-source), and hard-reset, so the
disconnect/debounce/reconnect/try-source arms run both ways. Genuine execution. RO + RW.
Accumulates tmp/ccstate_edges.pkl.
Usage: uv run --python .venv python cov_ccstate.py [rw]
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
    trace = os.path.join(TMP, "ccstate.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
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
    c += ['cpu CreateExecutionTracing "trcc" @%s PC' % trace]

    # reach SNK contract, then DISCONNECT (CC open) -> cc_debounce -> SNK_DISCONNECTED, then RECONNECT.
    for mid in (1, 2, 3):
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid)) + deliver(pe.PS_RDY(mid + 1), "0.3")
    for _ in range(3):
        c += ['sysbus.adc ForceSourceCc false', 'emulation RunFor "0.05"']    # CC open: enter debounce
        c += ['emulation RunFor "0.02"']                                       # short: time < cc_debounce (break)
        c += ['emulation RunFor "0.4"']                                        # long: time >= cc_debounce (continue)
        c += ['sysbus.adc ForceSourceCc true', 'emulation RunFor "0.3"']       # reconnect -> re-debounce
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(4)) + deliver(pe.PS_RDY(5), "0.3")
    # DRP / try-source: dual-role toggle + PartnerSink so gale tries to source (try_src) (:1563)
    c += ['sysbus.adc PartnerSink true']
    for act in ("pd dualrole toggle", "pd dualrole on", "pd trysrc 1", "pd dualrole source",
                "pd trysrc 0", "pd dualrole sink", "pd dualrole off"):
        c += cc(act) + ['emulation RunFor "0.3"']
    # source contract + source hard-reset -> SRC_HARD_RESET_RECOVER recovery timer (:1690)
    c += cc("pd dualrole source") + ['emulation RunFor "1.0"']
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(2))]
    for _ in range(4):
        c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
    c += ['emulation RunFor "0.3"']
    c += cc("pd 0 hard") + ['emulation RunFor "0.05"', 'emulation RunFor "0.6"']   # recovery timer window
    c += cc("pd 0 hard") + ['emulation RunFor "0.6"']
    # toggle CC during source mode (disconnect a sink) + reconnect
    for _ in range(2):
        c += ['sysbus.adc PartnerSink false', 'emulation RunFor "0.3"']
        c += ['sysbus.adc PartnerSink true', 'emulation RunFor "0.3"']

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "ccstate.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "ccstate_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/ccstate_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
