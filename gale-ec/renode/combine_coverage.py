#!/usr/bin/env python3
"""Authoritative CAPTURED branch coverage = union of the external-stimulus campaign
(coverage_captured.py -> tmp/cap_trace_cache.pkl) AND the direct function-invocation sweep
(fcall_sweep.py -> tmp/sweep_edges.pkl), measured over the validated rda denominator.

Both sources are genuine execution of the real captured firmware (external interfaces + direct
unit-test-style function calls); the union is the real reachable-and-executed coverage.
"""
import os
import pickle

import rda

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")


def load(name):
    p = os.path.join(TMP, name)
    if not os.path.exists(p):
        return set(), set()
    with open(p, "rb") as f:
        return pickle.load(f)


def main():
    cexec, cedges = load("cap_trace_cache.pkl")
    sexec, sedges = load("sweep_edges.pkl")
    executed = set(cexec) | set(sexec)
    edges = set(cedges) | set(sedges)
    seeds = executed | rda.ptr_targets(os.path.abspath(CAP))
    insns, cond, calls = rda.analyze(os.path.abspath(CAP), extra_seeds=seeds)
    taken = set(a for a in cond if (a, cond[a][1]) in edges)
    nottaken = set(a for a in cond if (a, cond[a][0]) in edges)
    both = [a for a in cond if a in taken and a in nottaken]
    reached = [a for a in cond if a in executed]

    def bd(es):
        t = set(a for a in cond if (a, cond[a][1]) in es)
        n = set(a for a in cond if (a, cond[a][0]) in es)
        return len([a for a in cond if a in t and a in n])

    print("=== CAPTURED combined coverage (campaign + function-call sweep) ===")
    print("  rda branches (denominator): %d" % len(cond))
    print("  reached:        %d (%.1f%%)" % (len(reached), 100.0 * len(reached) / len(cond)))
    print("  both-dirs:      %d (%.1f%%)" % (len(both), 100.0 * len(both) / len(cond)))
    print("  campaign-only both-dirs: %d" % bd(cedges))
    print("  sweep-only both-dirs:    %d" % bd(sedges))
    print("  sweep adds over campaign: +%d" % (len(both) - bd(cedges)))
    uncov = sorted(a for a in cond if a not in (set(taken) & set(nottaken)))
    with open(os.path.join(HERE, "cap_uncovered.txt"), "w") as f:
        for a in uncov:
            st = ("unreached" if a not in executed else
                  ("taken-only" if a in taken else ("nottaken-only" if a in nottaken else "?")))
            f.write("0x%08x %s\n" % (a, st))
    print("  wrote %d uncovered -> cap_uncovered.txt" % len(uncov))


if __name__ == "__main__":
    main()
