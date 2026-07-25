#!/usr/bin/env python3
"""Group uncovered branches by enclosing function, to turn the coverage grind into a priority list.

Reads cap_uncovered.txt (captured) or cov_uncovered_{RO,RW}.txt (rebuilt), maps each uncovered
branch to its enclosing function (nearest preceding function entry discovered by rda), annotates
with the recovered console-command name where known, and prints the functions with the most
uncovered branches first. That tells us exactly which emulation capability / stimulus to build next.

Usage: uv run --python .venv python analyze_uncov.py [cap_uncovered.txt]
"""
import os
import sys

import rda
import symbolize

CAPTURED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                        "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")


def function_entries(binpath):
    """A superset of function start addresses: vector roots + bl targets + pointer-table targets."""
    insns, cond, calls = rda.analyze(binpath, extra_seeds=rda.ptr_targets(binpath))
    entries = set(calls) | rda.ptr_targets(binpath)
    return sorted(entries)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    binarg = [a for a in sys.argv[1:] if a.startswith("--bin=")]
    path = args[0] if args else "cap_uncovered.txt"
    binpath = os.path.abspath(binarg[0].split("=", 1)[1]) if binarg else os.path.abspath(CAPTURED)
    entries = function_entries(binpath)
    names = symbolize.symbol_map(binpath)

    def enclosing(addr):
        # binary search for greatest entry <= addr
        lo, hi = 0, len(entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if entries[mid] <= addr:
                lo = mid + 1
            else:
                hi = mid
        return entries[lo - 1] if lo else addr

    groups = {}     # entry -> [count, unreached, onedir]
    total = 0
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                continue
            parts = ln.split()
            addr = int(parts[0], 16)
            state = parts[-1] if len(parts) > 1 else "?"   # last col is state in both file formats
            e = enclosing(addr)
            g = groups.setdefault(e, [0, 0, 0])
            g[0] += 1
            if state == "unreached":
                g[1] += 1
            else:
                g[2] += 1
            total += 1

    print("uncovered branches in %s: %d, across %d functions" % (path, total, len(groups)))
    print("%-42s %6s %10s %8s" % ("function (entry)", "uncov", "unreached", "one-dir"))
    for e in sorted(groups, key=lambda k: -groups[k][0])[:45]:
        nm = names.get(e, "")
        g = groups[e]
        print("  0x%08x %-30s %6d %10d %8d" % (e, nm, g[0], g[1], g[2]))


if __name__ == "__main__":
    main()
