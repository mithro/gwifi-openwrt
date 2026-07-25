"""PANIC + DIAGNOSTIC-COMMAND lever — fresh clusters: panic_printf (0x0800590c, ~30) + panic_data_print
(0x0800abe4, ~14) need real EXCEPTIONS, exercised via `crash <type>` (assert/divzero[/unsigned]/stack/
unaligned/watchdog) -> the fault handler -> panic_printf formats the exception frame -> reboot ->
`panicinfo` reads the saved panic (panic_data_print). Plus the fresh command clusters command_sysinfo
(16), command_help (12), command_tcpc (14). Genuine execution. RO + RW.
Usage: uv run --python .venv python cov_panic.py [rw]
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
    trace = os.path.join(TMP, "panic.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.1"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trpn" @%s PC' % trace]

    # each crash type -> exception -> panic_printf; then panicinfo reads the saved panic data.
    for ctype in ("assert", "divzero", "divzero unsigned", "stack", "unaligned", "watchdog"):
        c += cc("panicinfo", "0.08")                 # read any prior panic (panic_data_print) first
        c += cc("crash " + ctype, "0.4")             # trigger fault -> panic_printf -> (reboot)
        c += ['emulation RunFor "0.6"']              # let panic print + reboot settle
        c += cc("panicinfo", "0.1")                  # read the just-saved panic
    # fresh diagnostic command clusters
    for s in ("sysinfo", "sysinfo bogus", "help", "help pd", "help crash", "help help", "help xyz",
              "tcpc", "tcpc 0", "tcpc dump", "tcpc 0 dump", "version", "gettime", "hash", "hash ro",
              "hash rw", "hash 0 0x100", "reboot cancel", "panicinfo"):
        c += cc(s, "0.08")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "panic.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "panic_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/panic_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
