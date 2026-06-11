#!/usr/bin/env python3
"""Targeted coverage of the signed/unsigned integer-division helpers in the math region:
  __divsi3   @ RO 0x0800ae9c / RW 0x0801ae9c   (signed divide; sign-handling wrappers)
  __modsi3   @ RO 0x0800aeba / RW 0x0801aeba   (signed modulo)
  __udivmod  @ RO 0x0800aeec / RW 0x0801aeec   (unsigned core: normalization shift loop)

The firmware's own callers only pass POSITIVE operands (counts, voltages, currents), so the
negative-operand sign-handling arms (cmp #0; bge; rsbs) and the divisor-normalization edge
(bmi at 0x0800aefc) are never exercised. We direct-call them with a signed operand matrix
(neg/pos/zero/INT_MIN x neg/pos/zero/large-divisor) — genuine execution, the helper really
divides the injected operands. Accumulates tmp/div_edges.pkl (unioned by combine_coverage.py).
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

FUNCS = [0x0800ae9c, 0x0800aeba, 0x0800aeec,
         0x0801ae9c, 0x0801aeba, 0x0801aeec]

M = 0xFFFFFFFF
# (numerator r0, denominator r1): cover every sign combination + zero + INT_MIN + divisor
# values that drive the normalization shift loop (bit30/bit31 set, bls/bmi/bhi arms).
OPERANDS = [
    (7, 3), (-7 & M, 3), (7, -3 & M), (-7 & M, -3 & M),         # all 4 sign combos
    (0, 5), (5, 0), (0, 0),                                      # zero numerator / div-by-zero
    (0x80000000, 1), (0x80000000, -1 & M), (1, 0x80000000),     # INT_MIN edges
    (0x7FFFFFFF, 2), (-2147483648 & M, 7), (100, -1 & M),
    (0xFFFFFFFF, 0x40000000), (0xFFFFFFFF, 0x80000000),         # large divisor: normalization shifts
    (0x12345678, 0x00010000), (0x00000001, 0x00000002),         # bls (num<den) arm
    (1000000, 3), (0xDEADBEEF, 0x0000000F), (0xABCDEF01, 7),
]


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
    out = os.path.join(TMP, "div_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior div_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)

    trace = os.path.join(TMP, "div.txt")
    if os.path.exists(trace):
        os.remove(trace)

    s = fcall.Session(binp, boot="1.5", trace=trace)
    try:
        for fn in FUNCS:
            for a, b in OPERANDS:
                try:
                    s.rsp.call(fn, (a, b, 0, 0), timeout_continue=1)
                except Exception:
                    s.close()
                    fold(trace, executed, edges)
                    s = fcall.Session(binp, boot="1.5", trace=trace)
    finally:
        s.close()
        fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/div_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
