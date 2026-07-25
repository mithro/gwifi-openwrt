#!/usr/bin/env python3
"""Static map of the CURRENT residual uncovered branches (cap_uncovered.txt) to their containing
functions, so we can see whether the remaining gap is concentrated (few big functions) or diffuse
(long tail). Pure static analysis (rda + the binary) — no Renode, safe to run while the fuzzer holds
the serial slot.

Cross-references the rebuilt ELF's symbol table: the rebuilt and captured do not share addresses, but
the function ORDER and relative layout are near-identical, so the rebuilt symbol whose offset-within-
text matches the captured function entry is a strong name hint.
"""
import os
import subprocess

import rda

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
REBUILT_ELF = os.path.join(HERE, "ec-rebuilt.elf")


def text_ok(a):
    return (0x08000000 <= a < 0x0800b744) or (0x08010000 <= a < 0x0801b744)


def load_uncovered():
    out = {}
    with open(os.path.join(HERE, "cap_uncovered.txt")) as f:
        for ln in f:
            p = ln.split()
            if len(p) >= 2 and p[0].startswith("0x"):
                out[int(p[0], 16)] = p[1]
    return out


def rebuilt_syms():
    """addr(without RO/RW bank bit) -> name, from the rebuilt ELF (if present)."""
    syms = {}
    if not os.path.exists(REBUILT_ELF):
        return syms
    r = subprocess.run(["arm-none-eabi-nm", "-n", REBUILT_ELF], capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["nm", "-n", REBUILT_ELF], capture_output=True, text=True)
    for ln in r.stdout.splitlines():
        p = ln.split()
        if len(p) == 3 and p[1] in "tT":
            syms[int(p[0], 16) & ~1] = p[2]
    return syms


def main():
    ins, cond, calls = rda.analyze(CAP, extra_seeds=rda.ptr_targets(CAP))
    entries = sorted(f for f in (set(calls) | rda.ptr_targets(CAP)) if text_ok(f))
    import bisect

    def containing(a):
        i = bisect.bisect_right(entries, a) - 1
        return entries[i] if i >= 0 else None

    uncov = load_uncovered()
    syms = rebuilt_syms()
    # nearest rebuilt symbol by offset within text bank
    sym_addrs = sorted(syms)

    def name_for(faddr):
        # map captured entry to a rebuilt text offset (strip bank), find nearest sym at/below
        off = faddr & 0x0000FFFF        # within-bank offset (RO bank ~0x0000.., RW ~0x1....)
        # rebuilt RO text starts at 0x08000000; try exact-ish match on low 16 bits
        cands = [s for s in sym_addrs if (s & 0x0000FFFF) == off]
        if cands:
            return syms[cands[0]]
        # fallback: nearest by low-16 offset
        if not sym_addrs:
            return "?"
        best = min(sym_addrs, key=lambda s: abs((s & 0xFFFF) - off))
        return "~" + syms[best]

    per = {}
    for a, kind in uncov.items():
        if a not in cond:
            continue
        c = containing(a)
        if c is None:
            continue
        d = per.setdefault(c, {"unreached": 0, "taken-only": 0, "nottaken-only": 0, "other": 0})
        d[kind if kind in d else "other"] += 1

    ranked = sorted(per, key=lambda f: -sum(per[f].values()))
    total = sum(sum(v.values()) for v in per.values())
    print("residual uncovered branches in cond: %d, across %d functions" % (total, len(per)))
    print("cumulative coverage if each function were fully covered:\n")
    print("%-12s %5s  %4s %4s %4s   %s" % ("func", "total", "unr", "tk1", "nt1", "name(hint)"))
    cum = 0
    for f in ranked[:40]:
        d = per[f]
        n = sum(d.values())
        cum += n
        print("0x%08x %5d  %4d %4d %4d   %s  [cum %d, %.1f%% of gap]"
              % (f, n, d["unreached"], d["taken-only"], d["nottaken-only"],
                 name_for(f), cum, 100.0 * cum / total))
    # concentration summary
    tops = [sum(per[f].values()) for f in ranked]
    for k in (10, 20, 50, 100):
        if len(tops) >= k:
            print("top %3d functions hold %d/%d uncovered (%.1f%%)"
                  % (k, sum(tops[:k]), total, 100.0 * sum(tops[:k]) / total))


if __name__ == "__main__":
    main()
