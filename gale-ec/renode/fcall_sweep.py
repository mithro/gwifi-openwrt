#!/usr/bin/env python3
"""Coverage sweep via direct function invocation (fcall) — drive branches the external-interface
scenarios can't reach. For each discovered function entry, call it with a small set of input
vectors (which flip argument-dependent conditionals) while tracing; fold the trace into the
both-directions branch set. Genuine execution of real code with real inputs (the EC-unit-test
approach), never faking a branch.

Robustness: each call runs with a short continue-timeout; a call that faults/loops (never hits the
spin trap) is abandoned and the session is rebuilt (a crash can wedge the firmware/GDB stub). Calls
are batched per session for speed, rebooting on failure.

Usage: uv run --python .venv python fcall_sweep.py [--bin <fw>] [--max N]
"""
import argparse
import os

import fcall
import rda

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
# Input vectors: flip argc-style, value-sign, pointer-vs-null, and a valid RAM pointer (scratch).
VECTORS = [(0, 0, 0, 0), (1, 0x20002000, 0, 0), (0xFFFFFFFF, 0xFFFFFFFF, 0, 0),
           (2, 0x20002000, 0x20002400, 0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=CAPTURED)
    ap.add_argument("--max", type=int, default=80)
    ap.add_argument("--per-session", type=int, default=40)
    args = ap.parse_args()
    binp = os.path.abspath(args.bin)
    os.makedirs(TMP, exist_ok=True)

    # function entries to sweep (bl targets + pointer-table targets), BOTH images.
    ins, cond, calls = rda.analyze(binp, extra_seeds=rda.ptr_targets(binp))
    allfuncs = set(calls) | rda.ptr_targets(binp)
    funcs = sorted(f for f in allfuncs
                   if (0x08000000 <= f < 0x0800b744) or (0x08010000 <= f < 0x0801b744))
    if args.max:
        funcs = funcs[:args.max]
    print("sweeping %d functions x %d vectors via direct invocation" % (len(funcs), len(VECTORS)))

    trace = os.path.join(TMP, "sweep.txt")
    executed, edges = set(), set()

    def fold():
        prev = None
        if not os.path.exists(trace):
            return
        with open(trace) as f:
            for ln in f:
                ln = ln.strip()
                if not ln.startswith("0x"):
                    prev = None; continue
                pc = int(ln, 16); executed.add(pc)
                if prev is not None:
                    edges.add((prev, pc))
                prev = pc
        os.remove(trace)

    i = 0
    calls_this_session = 0
    s = None
    def fresh():
        nonlocal s, calls_this_session
        if s is not None:
            s.close(); fold()
        s = fcall.Session(binp, boot="1.5", trace=trace)
        try:
            s.rsp.writemem(0x20002000, b"\x00" * 64)
        except Exception:
            pass
        calls_this_session = 0
    fresh()
    while i < len(funcs):
        f = funcs[i]
        crashed = False
        for v in VECTORS:
            try:
                s.rsp.call(f, v, timeout_continue=3)
                calls_this_session += 1
            except Exception:
                crashed = True
                break
        i += 1
        if crashed:
            fresh()                                   # a faulting call wedges the stub: rebuild
        elif calls_this_session >= args.per_session:
            fresh()                                   # periodic refresh to bound trace size / drift
        if i % 25 == 0:
            print("  ...%d/%d functions swept, %d edges so far" % (i, len(funcs), len(edges)))
    if s is not None:
        s.close(); fold()

    # measure both-dirs over the rda denominator
    taken = set(a for a in cond if (a, cond[a][1]) in edges)
    nottaken = set(a for a in cond if (a, cond[a][0]) in edges)
    both = [a for a in cond if a in taken and a in nottaken]
    reached = [a for a in cond if a in executed]
    print("\nsweep-only coverage: %d reached, %d both-dirs (of %d rda branches)" %
          (len(reached), len(both), len(cond)))
    import pickle
    with open(os.path.join(TMP, "sweep_edges.pkl"), "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved executed/edges -> tmp/sweep_edges.pkl (union with campaign for total)")


if __name__ == "__main__":
    main()
