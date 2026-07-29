#!/usr/bin/env python3
"""CONSOLE-ARG-MATRIX lever — driven by UNCOVERED-BY-FUNCTION.md, which shows 107+ uncovered branches
in console/host command handlers are argument-parse checks (parse_bool true/false, argc too-few/too-many,
strtoi valid/invalid/boundary). The campaign runs commands but not with the arg variety that flips both
sides of these checks. This runs each real gale console command through an argument MATRIX: no-arg,
valid/invalid bool, valid/invalid/boundary integers, and extra args. Genuine console execution of the
real firmware. RO + RW. Accumulates tmp/cmdargs_edges.pkl.
Usage: uv run --python .venv python cov_cmdargs.py [rw]
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

# gale console commands that take args (from UNCOVERED-BY-FUNCTION.md command_* handlers + the build).
# Each is fed the arg matrix; harmless/destructive ones (crash/reboot/sysjump/hibernate) are run LAST.
ARG_CMDS = ["rec", "dev", "power", "adc", "chan", "gpioget", "gpioset", "hcdebug", "hostevent",
            "hash", "md", "rw", "spixfer", "sysinfo", "gettime", "flashinfo", "flashread",
            "flashwrite", "flasherase", "flashwp", "pd", "version", "waitms", "sleepmask",
            "panicinfo", "forcetime", "ctrlram", "i2cxfer", "port80", "hangdet", "idlestats"]
# argument patterns: exercise parse_bool(both), argc(0..3), strtoi(valid/invalid/boundary/neg/hex)
ARG_SETS = ["", "0", "1", "on", "off", "enable", "disable", "true", "false", "x", "bogus",
            "-1", "0x0", "0xffffffff", "4294967296", "0x20000000", "256", "0x1000 0x10",
            "0 0x1f 3", "0 0", "1 2 3 4", "0x08000000 0x100", "ro", "rw", "abort"]


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
    trace = os.path.join(TMP, "cmdargs.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.03"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trca" @%s PC' % trace]
    for cmd in ARG_CMDS:
        for a in ARG_SETS:
            c += cc((cmd + " " + a).strip())
    # destructive/reboot-ish commands LAST (each may reset the console); keep them minimal
    for cmd in ("crash", "reboot", "sysjump", "hibernate"):
        for a in ("", "unaligned", "watchdog", "hard", "ro", "x"):
            c += cc((cmd + " " + a).strip(), "0.05")
    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "cmdargs.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "cmdargs_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/cmdargs_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
