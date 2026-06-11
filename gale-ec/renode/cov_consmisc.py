"""CONSOLE-MISC lever — several small console-command residuals in one run:
 command_help (console.c:696 "help list" / :712 "help <cmd>" usage / :714 shorthelp),
 command_reboot (system.c:948 "hard" / :951 "soft" / :958 "preserve" arg arms),
 command_tcpc (usb_pd_tcpc.c:1351 "tcpc <port>" CC status print).
Genuine console execution. RO + RW.  Usage: uv run --python .venv python cov_consmisc.py [rw]
"""
import os, pickle, subprocess, sys
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
                prev = None; continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None; continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "consmisc.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trcm" @%s PC' % trace]

    # command_help: list (:696), per-command usage (:712 cmd->argdesc) + shorthelp (:714) for cmds with/without
    for s in ("help", "help list", "help help", "help pd", "help crash", "help reboot", "help gpioget",
              "help hcdebug", "help chan", "help md", "help rw", "help flashinfo", "help nonexistent", "help h"):
        c += cc(s)
    # command_tcpc: CC status per port (:1351) + bad/no port
    for s in ("tcpc", "tcpc 0", "tcpc 1", "tcpc 9", "tcpc 0 dump", "tcpc dump"):
        c += cc(s)
    # command_reboot arg arms (parse runs before the actual reset): cancel/preserve don't reset; do the
    # non-resetting ones first, the resetting ones last (each re-inits the console after RunFor).
    for s in ("reboot cancel", "reboot preserve", "reboot wait-external", "reboot bogus"):
        c += cc(s)
    for s in ("reboot soft", "reboot hard", "reboot cold", "reboot ro", "reboot ap-off"):
        c += cc(s, "0.5")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "consmisc.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "consmisc_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/consmisc_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
