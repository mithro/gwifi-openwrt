#!/usr/bin/env python3
"""DRP-FREE-RUN lever — drives the pd_task DUAL-ROLE TOGGLE while UNATTACHED, the one stimulus the
attached-contract soak levers never produce. With CC open (no Force* knob) and `pd dualrole on`, gale
ping-pongs PD_STATE_SRC_DISCONNECTED <-> PD_STATE_SNK_DISCONNECTED on the PD_T_DRP_SNK (40ms) /
PD_T_DRP_SRC (30ms) timers, so a multi-second RunFor cycles the toggle dozens of times and exercises
the timer/debounce arms that only run when real emulated time passes with no partner:
  usb_pd_protocol.c:1556/1557 try_src_marker, :1563 next_role_swap=+PD_T_DRP_SNK, :2032 +PD_T_DRP_SRC,
  :2051 cc_debounce wait, :1690 src_recover wait, :2014/2016 PD_FLAGS_TRY_SRC.
Also bundles the pure-stimulus arms: `pd dump 0..3` (debug_level arms :1025/:1832 when a packet arrives),
`pd enable 0/1` (pd_comm_enabled arm :2189), `pd <p> bist_tx/bist_rx/tx/charger` state pokes, and
`pd trysrc 0/1` toggled so both TRY_SRC directions run. Genuine console execution. RO + RW.
Accumulates tmp/drpfree_edges.pkl.
Usage: uv run --python .venv python cov_drpfree.py [rw]
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
    trace = os.path.join(TMP, "drpfree.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.15"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trdf" @%s PC' % trace]

    # ---- (A) DRP free-run, fully UNATTACHED (CC open: no Force knob). Toggle on, trysrc both ways.
    c += cc("pd dualrole on")
    c += cc("pd trysrc 1")
    for _ in range(4):                      # ~4s emulated: ~50 SNK/SRC toggle half-cycles
        c += ['emulation RunFor "1.0"']
    c += cc("pd trysrc 0")
    for _ in range(3):
        c += ['emulation RunFor "1.0"']
    # force sink, then force source (each free-runs its own disconnected state), then back to toggle
    c += cc("pd dualrole sink") + ['emulation RunFor "1.0"']
    c += cc("pd dualrole source") + ['emulation RunFor "1.0"']
    c += cc("pd dualrole on") + ['emulation RunFor "1.0"']

    # ---- (B) DRP toggle with a DEBUG ACCESSORY present (both CC in Rd band) so the source side of the
    # toggle detects an accessory (usb_pd_protocol.c:1576 cc1==RD && cc2==RD) -> SRC_ACCESSORY bring-up.
    c += ['sysbus.adc ForceAccessory true']
    c += cc("pd dualrole source") + ['emulation RunFor "1.5"']
    c += cc("pd dualrole on") + ['emulation RunFor "1.0"']
    c += ['sysbus.adc ForceAccessory false', 'emulation RunFor "0.8"']   # accessory removed -> src_recover

    # ---- (C) NORMAL SINK attached to gale-as-source (single Rd): SRC_DISCONNECTED -> SRC_STARTUP path,
    # then remove -> src_recover (760ms) wait arm (:1690) exercised by the >0.8s gap.
    c += ['sysbus.adc PartnerSink true']
    c += cc("pd dualrole source") + ['emulation RunFor "1.2"']
    c += ['sysbus.adc PartnerSink false', 'emulation RunFor "1.0"']
    c += cc("pd dualrole on") + ['emulation RunFor "0.8"']

    # ---- (D) debug_level arms: `pd dump N` then deliver a packet so the receive-path CPRINTF arms
    # (:1025 debug_level==1 && type!=PING, :1832 debug_level>=1) run at each level. Use a quick sink
    # contract context (ForceSourceCc) so a packet is actually processed in-state.
    c += ['sysbus.adc ForceSourceCc true', 'sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    c += cc("pd dualrole on") + ['emulation RunFor "0.4"']
    for lvl in ("0", "1", "2", "3"):
        c += cc("pd dump %s" % lvl)
        c += deliver(pe.SRC_CAP, "0.15")                 # data msg (type != PING) at this debug level
        c += deliver(pe.ctrl(1, 3), "0.1")               # a GoodCRC/ctrl ping-ish
        c += deliver(pe.ctrl(5, 4), "0.1")               # PD_CTRL_PING (type 5) -> the type==PING arm
    c += cc("pd dump 0")

    # ---- (E) pd enable 0 (pd_comm disabled) then deliver a packet (:2189 && pd_comm_enabled false arm)
    c += cc("pd enable 0")
    c += deliver(pe.SRC_CAP, "0.2")
    c += deliver(pe.ACCEPT(2), "0.15")
    c += ['emulation RunFor "0.5"']
    c += cc("pd enable 1") + ['emulation RunFor "0.3"']

    # ---- (F) BIST / forced state pokes (:757 BIST_MODE_2 etc.)
    for act in ("pd 0 bist_rx", "pd 0 bist_tx", "pd 0 tx", "pd 0 charger"):
        c += cc(act) + ['emulation RunFor "0.3"']
    c += ['sysbus.adc ForceSourceCc false', 'emulation RunFor "0.4"']

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "drpfree.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=1200)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "drpfree_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/drpfree_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
