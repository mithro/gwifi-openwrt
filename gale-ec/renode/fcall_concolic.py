#!/usr/bin/env python3
"""Replay angr's concolic solutions in Renode for GENUINE execution.

Reads tmp/concolic_solutions.json (produced by concolic_solve.py): each entry = {func, branch, args:
{r0..r3}, mem:[(addr,val)]}. For each, in a real booted Renode session: apply the memory constraints,
set r0-r3 to the solved values, and direct-call the function. The REAL CPU executes the REAL branch on
the solved inputs — angr only generated the inputs. Accumulates tmp/concolic_edges.pkl (unioned by
combine_coverage.py); also reports which target branches genuinely flipped.
"""
import json
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
SOL = os.path.join(TMP, "concolic_solutions.json")


def fold(trace, executed, edges):
    if not os.path.exists(trace):
        return
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


def main():
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    if not os.path.exists(SOL):
        print("no concolic_solutions.json yet"); return
    sols = json.load(open(SOL))
    out = os.path.join(TMP, "concolic_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    trace = os.path.join(TMP, "concolic.txt")
    if os.path.exists(trace):
        os.remove(trace)

    s = [fcall.Session(binp, boot="1.5", trace=trace)]

    def reboot():
        s[0].close(); fold(trace, executed, edges)
        s[0] = fcall.Session(binp, boot="1.5", trace=trace)

    n = 0
    for key, sol in sols.items():
        fn = sol.get("func")
        a = sol.get("args", {})
        try:
            for (addr, val) in sol.get("mem", []):
                s[0].rsp.writemem(addr, struct.pack("<I", val & 0xFFFFFFFF))
            s[0].rsp.call(fn, (a.get("r0", 0), a.get("r1", 0), a.get("r2", 0), a.get("r3", 0)),
                          timeout_continue=1)
            n += 1
        except Exception:
            reboot()
    s[0].close(); fold(trace, executed, edges)

    # report which target branches genuinely flipped both ways now
    flipped = 0
    for key, sol in sols.items():
        a = sol["branch"]
        # both edges present?
        succ = [e for e in edges if e[0] == a]
        if len(set(succ)) >= 2:
            flipped += 1
    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("replayed %d solutions; %d target branches now both-dir in concolic trace; %d edges"
          % (n, flipped, len(edges)))
    print("saved -> tmp/concolic_edges.pkl")


if __name__ == "__main__":
    main()
