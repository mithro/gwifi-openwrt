#!/usr/bin/env python3
"""Targeted coverage of vfnprintf (the EC format-string core at 0x80059b8 / RW 0x80159b8) by calling
it directly with a battery of format strings covering every specifier + flag + width/precision combo.
Its ~36 uncovered branches per bank are format cases the firmware's fixed cprintf calls never hit.

vfnprintf(int (*addchar)(void *ctx, int c), void *ctx, const char *fmt, va_list args):
  r0 = addchar callback  -> a tiny 'movs r0,#0; bx lr' stub we plant in RAM (returns EC_SUCCESS so
                            printing continues), r1 = ctx (ignored), r2 = fmt (RAM), r3 = va_list
                            (RAM array of arg words; va_arg walks it).

Genuine execution of the real captured firmware; accumulates tmp/printf_edges.pkl (unioned by
combine_coverage.py). Serial + memory-capped via fcall.Session.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

STUB = 0x20002800          # 'movs r0,#0; bx lr'  (00 20 70 47)  -- always EC_SUCCESS
FMT = 0x20002000          # format string
ARGS = 0x20002400         # va_list arg words
STR1 = 0x20002600         # a sample NUL-terminated string for %s args
ESTUB = 0x20002820         # counter-based addchar: succeeds N times then returns error
ECNT = 0x20002810          # the RAM counter ESTUB decrements (ctx points here)

# ESTUB hand-assembled Thumb (Cortex-M0): addchar(r0=ctx=&count, r1=c)
#   ldr r2,[r0]; cmp r2,#0; beq fail; subs r2,#1; str r2,[r0]; movs r0,#0; bx lr
#   fail: movs r0,#1; bx lr   -> returns nonzero (output error) once the counter hits 0
ESTUB_CODE = bytes([0x02, 0x68, 0x00, 0x2a, 0x03, 0xd0, 0x01, 0x3a,
                    0x02, 0x60, 0x00, 0x20, 0x70, 0x47, 0x01, 0x20, 0x70, 0x47])

# Format strings covering specifiers, length mods, flags, width/precision, and the cros_ec %b/%r/%h.
FORMATS = [
    "plain text no specifiers\n",
    "%d %i %u %x %X %o %c %s %p %%\n",
    "%5d|%-5d|%05d|%+d|% d|%.3d\n",
    "%08x|%#x|%X|%#o\n",
    "%ld %lld %lu %llx %lX\n",
    "%hd %hhd %hx %hhx\n",
    "%zu %zd\n",
    "%.*d|%*d|%-*.*s\n",
    "%b %032b\n",                       # cros_ec binary specifier
    "%s=%s end %c%c\n",
    "%10.4f %e %g\n",                   # float (may be unsupported -> error/skip branch)
    "%q %y %Z bad-specifiers %\n",      # invalid specifiers -> the default/error arm
    "%-+ #08.3lld combo\n",
    "string with %% literal and %s\n",
    # --- expanded edge cases to recover the remaining branches ---
    "%0d %00d %.0d %0.0d\n",                 # zero width / zero precision
    "%100d %-100s\n",                        # very large width (overflow/clamp path)
    "%.20d %.50s\n",                         # large precision
    "%+u %+x % x %#0d\n",                    # flag combos that don't apply
    "%c%c%c%c %d%d%d\n",                     # repeated specifiers (arg-walk)
    "%lX %lo %lc %ls\n",                     # long + odd specifiers
    "%hhu %hho %hhX\n",
    "%9.9f %.0f %+.2f %-8.1f\n",             # float widths/precision/flags
    "%a %A %E %G\n",                         # hex-float / upper exp
    "%5%  %-%  trailing %",                  # %% with flags + dangling %
    "%2$d %1$s positional\n",                # positional (likely unsupported -> error)
    "%*.*f %-*d %0*x\n",                     # star width AND precision
    "%td %jd %Lf\n",                         # ptrdiff/intmax/long-double mods
    "no-newline-no-nul-edge%s",
    # --- branch-targeted additions (decoded from uncovered cmp immediates) ---
    "%T\n",                                  # 0x54 'T' EC timestamp specifier (0x8005b5e/0x8005b82)
    "ts=%T end\n",
    "%-T %10T\n",                            # timestamp with flags/width
    "%X %x %u %p %b\n",                       # ensure the X/x/u/p/b dispatch ladder is walked
    "%d %d %d %d\n",                          # signed: consumes INT_MIN/INT_MAX/neg args below
    "%08X lower=%08x\n",                      # hex with a-f digits (0x8005b3c hex-digit loop)
    "%020b\n",                                # binary width pad
]


def main():
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "printf_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior printf_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)

    trace = os.path.join(TMP, "printf.txt")
    if os.path.exists(trace):
        os.remove(trace)

    # va_list arg words: cover INT_MIN/INT_MAX (signed neg path 0x8005cf0/cf8), -1, lowercase-hex
    # digits (0xabcdef -> 0x8005b3c), width/prec values, and %s pointers.
    argwords = struct.pack("<16I", 0x80000000, 0x7FFFFFFF, 0xFFFFFFFF, 0x00ABCDEF,
                           STR1, STR1, 7, 4, 0x2A, 0xDEADBEEF, STR1, 2, 0x10, STR1, 5, 99)

    # Error-path passes: a counter stub that returns EC_SUCCESS for K chars then fails, driving
    # the four "output returned error" branches (cmp r0,#0; bne) at successive emit positions:
    #   K=0 percent-emit (0x80059f0), K=1 literal-emit (0x8005a10),
    #   K small hex-digit-emit (0x8005b3c), K small pad-emit (0x8005cc4).
    EFORMATS = ["%%pct", "abcdef", "%x", "%X", "%10d", "%-10d", "%5s", "%T",
                "%p", "%08x", "%010d", "%-5d", "%.3s", "%-8s", "%5.2d", "%#x", "ab%scd", "%c%c"]
    EK = list(range(0, 16))   # fail addchar at each output position so every per-site addchar-fail arm runs

    def run_once(s, entry, ctx, fmt):
        s.rsp.writemem(FMT, fmt.encode() + b"\x00")
        s.rsp.writemem(ARGS, argwords)
        s.rsp.call(vfn, (entry | 1, ctx, FMT, ARGS), timeout_continue=3)

    def fresh():
        s = fcall.Session(binp, boot="1.5", trace=trace)
        s.rsp.writemem(STUB, bytes([0x00, 0x20, 0x70, 0x47]))   # movs r0,#0 ; bx lr
        s.rsp.writemem(ESTUB, ESTUB_CODE)
        s.rsp.writemem(STR1, b"sampleStr\x00")
        return s

    for bank, vfn in (("RO", 0x080059b8), ("RW", 0x080159b8)):
        s = fresh()
        try:
            # pass 0: NULL / empty format pointer -> the `cmp r2,#0` (r2 = format arg) NULL-guard arm
            # (0x8005cf0) + the `while (*format)` immediate-exit (empty string) fall-through.
            for fmtptr in (0, FMT):
                try:
                    if fmtptr == FMT:
                        s.rsp.writemem(FMT, b"\x00")          # empty string at FMT
                    s.rsp.writemem(ARGS, argwords)
                    s.rsp.call(vfn, (STUB | 1, 0, fmtptr, ARGS), timeout_continue=3)
                except Exception:
                    s.close(); s = fresh()
            # pass 1: always-success stub over the full specifier battery
            for fmt in FORMATS:
                try:
                    run_once(s, STUB, 0, fmt)
                except Exception:
                    s.close(); s = fresh()
            # pass 2: counter error-stub (ctx=&counter) over the error-targeted formats
            for k in EK:
                for fmt in EFORMATS:
                    try:
                        s.rsp.writemem(ECNT, struct.pack("<I", k))
                        run_once(s, ESTUB, ECNT, fmt)
                    except Exception:
                        s.close(); s = fresh()
        finally:
            s.close()
        # fold this bank's trace
        if os.path.exists(trace):
            prev = None
            with open(trace) as f:
                for ln in f:
                    ln = ln.strip()
                    if len(ln) < 4 or not ln.startswith("0x"):
                        prev = None; continue
                    try:
                        pc = int(ln, 16)
                    except ValueError:
                        prev = None; continue
                    executed.add(pc)
                    if prev is not None:
                        edges.add((prev, pc))
                    prev = pc
            os.remove(trace)
        print("  %s vfnprintf swept: %d edges, %d PCs so far" % (bank, len(edges), len(executed)))

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/printf_edges.pkl")


if __name__ == "__main__":
    main()
