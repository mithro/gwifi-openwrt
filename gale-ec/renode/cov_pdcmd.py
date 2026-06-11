#!/usr/bin/env python3
"""COMMAND_PD lever — targets command_pd (0x0800971c, usb_pd_protocol.c) per UNCOVERED-BY-FUNCTION.md:
the drp_state switch print (:2882 — `pd dualrole` no-arg after each mode is set), the vdm sub-dispatch
(:3053 `strncasecmp(argv[3], "curr", 4)` etc. — `pd <port> vdm ping/curr/vers`), debug_level set (:2920
`pd dump <n>`), ports enable/disable (:2935), and the state print (:3069 `pd <port> state`). The generic
cmdargs lever never sends these exact subcommands. Genuine console execution. RO + RW.
Accumulates tmp/pdcmd_edges.pkl.
Usage: uv run --python .venv python cov_pdcmd.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


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
    trace = os.path.join(TMP, "pdcmd.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trpc" @%s PC' % trace]

    cmds = []
    # drp_state switch print (:2882): set each mode, then `pd dualrole` (no arg) to print THAT case
    for mode in ("on", "off", "sink", "source"):
        cmds += ["pd dualrole %s" % mode, "pd dualrole"]
    cmds += ["pd dualrole toggle", "pd dualrole", "pd dualrole bogus"]
    # vdm sub-dispatch (:3053): pd <port> vdm ping/curr/vers + bad
    cmds += ["pd 0 vdm ping 1", "pd 0 vdm ping 0", "pd 0 vdm ping", "pd 0 vdm curr",
             "pd 0 vdm vers", "pd 0 vdm version", "pd 0 vdm bogus", "pd 0 vdm"]
    # debug level (:2920)
    cmds += ["pd dump 0", "pd dump 1", "pd dump 2", "pd dump 3", "pd dump"]
    # ports enable/disable (:2935)
    cmds += ["pd enable", "pd disable", "pd trysrc 0", "pd trysrc 1", "pd trysrc"]
    # state / flags / info prints (:3069) on each port + bad port
    cmds += ["pd 0 state", "pd 1 state", "pd 0 flags", "pd 0", "pd 9 state",
             "pd 0 dev 5000", "pd 0 dev 20000", "pd 0 dev", "pd 0 charger", "pd 0 comm on",
             "pd 0 comm off", "pd 0 ping on", "pd 0 ping off", "pd 0 tx", "pd 0 bist",
             "pd 0 soft", "pd 0 hard", "pd 0 swap power", "pd 0 swap data", "pd 0 swap vconn"]
    # arg-count / bad-subcommand edges
    cmds += ["pd", "pd bogus", "pd 0 bogus", "pd 0xff state"]
    for sc in cmds:
        c += cc(sc)

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pdcmd.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdcmd_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pdcmd_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
