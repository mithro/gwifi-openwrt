"""Targeted coverage of console-command handlers (signature `int handler(int argc, char **argv)`)
by calling them directly with a crafted argv — an array of pointers to real argument strings in RAM.
The generic fuzzer fed a garbage argv pointer so these stayed one-direction; a well-formed argv with
varied tokens (on/off/enable/numbers/hex/flags/out-of-range) flips the in-handler argument-validation
branches both ways.

Targets are top-uncovered functions whose head matches the argc pattern (`cmp r0,#1`/`cmp r0,#2`
near entry). Accumulates tmp/cmd_edges.pkl (unioned by combine_coverage.py). Serial + mem-capped.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

ARGV = 0x20002400          # array of char* (argv)
STRBASE = 0x20002600       # arg strings live here, 16 bytes apart

# Candidate handler entries (RO + RW mirror, +0x10000). Identified by the argc/argv prologue.
TARGETS = [0x0800971c, 0x08013c00, 0x08009eb0, 0x080047cc, 0x080127e8,
           0x0801971c, 0x08013c00 + 0x10000, 0x08019eb0, 0x080147cc, 0x080127e8 + 0x10000]

# Argument-token batteries: each is a list of argv tokens (argv[0]=command name placeholder).
ARG_SETS = [
    ["c"],
    ["c", "on"], ["c", "off"], ["c", "enable"], ["c", "disable"],
    ["c", "0"], ["c", "1"], ["c", "2"], ["c", "-1"], ["c", "255"],
    ["c", "0x1f"], ["c", "0xffffffff"], ["c", "100"], ["c", "999999"],
    ["c", "rw"], ["c", "ro"], ["c", "source"], ["c", "sink"], ["c", "toggle"],
    ["c", "x"], ["c", "bad"], ["c", "0", "1"], ["c", "1", "2", "3"],
    ["c", "dump"], ["c", "flush"], ["c", "0", "0xff", "1"],
]


def setup_argv(rsp, tokens):
    """Write tokens as NUL-terminated strings + an argv pointer array; return (argc, ARGV)."""
    ptrs = []
    for i, t in enumerate(tokens):
        a = STRBASE + i * 16
        rsp.writemem(a, t.encode() + b"\x00")
        ptrs.append(a)
    rsp.writemem(ARGV, struct.pack("<%dI" % len(ptrs), *ptrs))
    return len(tokens), ARGV


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
    out = os.path.join(TMP, "cmd_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior cmd_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)
    trace = os.path.join(TMP, "cmd.txt")
    if os.path.exists(trace):
        os.remove(trace)

    targets = sorted(set(t for t in TARGETS
                         if (0x08000000 <= t < 0x0800b744) or (0x08010000 <= t < 0x0801b744)))
    s = fcall.Session(binp, boot="1.5", trace=trace)
    calls = 0
    for fn in targets:
        for tokens in ARG_SETS:
            try:
                argc, argv = setup_argv(s.rsp, tokens)
                s.rsp.call(fn, (argc, argv, 0, 0), timeout_continue=2)
                calls += 1
            except Exception:
                s.close(); fold(trace, executed, edges)
                s = fcall.Session(binp, boot="1.5", trace=trace)
        print("  swept 0x%08x" % fn)
        if calls >= 50:
            s.close(); fold(trace, executed, edges)
            s = fcall.Session(binp, boot="1.5", trace=trace); calls = 0
    s.close(); fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved %d edges, %d PCs -> tmp/cmd_edges.pkl" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
