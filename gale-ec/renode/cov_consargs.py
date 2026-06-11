#!/usr/bin/env python3
"""GALE-SUBCOMMAND + cheap-argv console lever. Root cause found in UNCOVERED-BY-FUNCTION.md triage:
command_power/command_dev/command_rec are entries in gale_subcommands[] (dispatched by command_gale),
NOT top-level commands — so cov_cmdargs.py's bare `dev`/`power`/`rec` NEVER reached them with args.
The correct invocation is `gale <sub> <arg>` (command_gale calls handler(argc-1, argv+1)); bare `gale`
calls every handler with argc=1 (status path only).

This drives:
  * `gale {power,dev,rec,polarity} {1,0,x}` -> argc>1 + parse_bool success(v=1/v=0)/fail; `gale power 0`
    sets ap_is_on=0 so the `ap_is_on ? "on":"off"` (board.c:324, nottaken r3==0) prints "off";
  * `gale`, `gale cc`, `gale vbus`, `gale bogus` (EC_ERROR_PARAM1 not-found return);
  * md/rw memory commands with argc + format + '.'-arg shapes (command_mem_dump/command_read_word);
  * help <cmd> (command_help shorthelp arm); chan; gpioget/gpioset BOGUS (gpio_is_implemented false arm).
Generous 0.12s per command (the console TASK must wake + execute, not just buffer the chars). Genuine
console execution of the real captured firmware. RO + RW. Accumulates tmp/consargs_edges.pkl.
Usage: uv run --python .venv python cov_consargs.py [rw]
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

CMDS = [
    # --- gale subcommands (the confirmed root-cause win) ---
    # parse_bool accepts ONLY word forms (on/off/ena*/dis*/t*/f*/y*/n*), NOT digits "0"/"1".
    # set_ap_power() is DEFERRED (hook_call_deferred), and ap_is_on is BSS(=0 at boot): the print in
    # the SAME command sees the stale value, so toggle then RE-PRINT (the next `gale power`) after the
    # hook fires to flip board.c:324 `ap_is_on ? "on":"off"` both ways.
    "gale",                                   # argc<2 -> calls each handler(argc=1): status path
    "gale power off", "gale power",           # queue off (hook), then print -> ap_is_on==0
    "gale power on", "gale power",            # queue on (hook),  then print -> ap_is_on==1
    "gale power x",                           # parse_bool fail (no set_ap_power)
    "gale dev on", "gale dev off", "gale dev x",     # v=1 / v=0 / parse_bool fail
    "gale rec on", "gale rec off", "gale rec x",
    "gale polarity 1", "gale polarity 0", "gale polarity x",   # polarity uses strtoi, digits OK
    "gale cc", "gale vbus",
    "gale bogus", "gale p",                   # not-found -> EC_ERROR_PARAM1 / prefix match
    # --- memory commands: argc, format selector, '.'-arg ---
    "md", "md 0x20000000", "md 0x20000000 8", "md b 0x20000000", "md h 0x20000000 4",
    "md w 0x20000000 2", "md .", "md . 4",
    "rw", "rw 0x20000000", "rw 0x20000000 0x55", "rw b 0x20000000", "rw . 0x12", "rw .b 0x20000000",
    # --- help (shorthelp present/absent), chan, gpio name-lookup fail arm ---
    "help", "help gale", "help md", "help help", "help nosuchcmd",
    "chan", "chan 0", "chan 0xffffffff", "chan save", "chan restore", "chan 7",
    "gpioget", "gpioget NOSUCHPIN", "gpioset NOSUCHPIN 1",
]


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
    trace = os.path.join(TMP, "consargs.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.12"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trcs" @%s PC' % trace]
    for cmd in CMDS:
        c += cc(cmd)
    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "consargs.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "consargs_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/consargs_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
