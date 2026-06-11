"""CONSOLE-MISC-4 lever — more bundled small console clusters:
 command_powerbtn (power_button.c: argc>1 strtoi ms / simulate press+release),
 command_gale + its subcommands (board/gale/board.c: power/polarity/cc/vbus/dev/rec dispatch + no-arg
 usage + bad subcmd), command_pd no-arg arms (dump level print :2915, dualrole state print :2882),
 pd <port> dev <volt> (pd_request_source_voltage), mmapinfo (switch.c). Genuine console execution. RO+RW.
Usage: uv run --python .venv python cov_consmisc4.py [rw]
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
    trace = os.path.join(TMP, "consmisc4.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trc4" @%s PC' % trace]

    cmds = [
        # command_pd no-arg arms: dump level print, dualrole state print, trysrc/enable status
        "pd dump", "pd dualrole", "pd trysrc", "pd enable 1", "pd dump 0x22",
        # pd <port> dev <volt> -> pd_request_source_voltage (validate requested voltage vs PDOs)
        "pd 0 dev", "pd 0 dev 5", "pd 0 dev 9", "pd 0 dev 12", "pd 0 dev 20", "pd 0 dev 0", "pd 0 dev xx",
        # command_powerbtn: no-arg (press+release), with ms, bad arg
        "powerbtn", "powerbtn 0", "powerbtn 100", "powerbtn 500", "powerbtn -1", "powerbtn xyz",
        # command_gale dispatch: no-arg usage + each subcommand + bad subcmd
        "gale", "gale power", "gale polarity", "gale cc", "gale vbus", "gale dev", "gale dev 5",
        "gale rec", "gale bogus", "gale p",
        # switch.c
        "mmapinfo",
    ]
    for s in cmds:
        c += cc(s, "0.1")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "consmisc4.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "consmisc4_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/consmisc4_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
