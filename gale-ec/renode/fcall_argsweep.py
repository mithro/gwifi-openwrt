#!/usr/bin/env python3
"""Semantic argument sweep: the div/pdo/misc wins all came from calling a function with arg values
equal to ITS OWN compared constants (not random fuzzing). Generalize that across EVERY function that
still contains a reached-one-direction (flippable) branch: disassemble it, collect the constants it
compares against (cmp/cmn/sub #imm), and direct-call it with r0 (and r1) set to each of those
constants + boundary values (0/1/-1/INT_MIN/INT_MAX/scratch-ptr). This flips the arg-driven dispatch
and sign branches the firmware's fixed call sites never hit. Genuine execution; accumulates
tmp/argsweep_edges.pkl (unioned by combine_coverage.py).
"""
import os
import pickle

import capstone
import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
SCRATCH = 0x20002000          # valid pointer arg
M = 0xFFFFFFFF

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
DATA = open(os.path.abspath(CAPTURED), "rb").read()
BASE = 0x08000000


def func_start(addr):
    for back in range(0, 1200, 2):
        off = addr - back - BASE
        if off < 0:
            break
        for ins in md.disasm(DATA[off:off + 2], addr - back):
            if ins.mnemonic == 'push' and 'lr' in ins.op_str:
                return addr - back
    return None


def func_consts(fstart, end):
    """Constants the function compares against (cmp/cmn/subs #imm) + the function's small range."""
    consts = set()
    off = fstart - BASE
    for ins in md.disasm(DATA[off:off + (end - fstart)], fstart):
        if ins.mnemonic in ('cmp', 'cmn', 'subs', 'adds', 'movs') and '#' in ins.op_str:
            try:
                v = int(ins.op_str.split('#')[1], 0)
                consts.add(v & M)
                consts.add((v - 1) & M)
                consts.add((v + 1) & M)
            except Exception:
                pass
        if ins.address > fstart + 0x400:
            break
    return consts


def main():
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "argsweep_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior argsweep_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)

    # Functions (RO half) that still contain a reached-one-direction branch.
    funcs = {}
    for l in open(os.path.join(HERE, "cap_uncovered.txt")):
        if not l.startswith("0x"):
            continue
        a, k = l.split(); a = int(a, 16)
        if a >= 0x08010000 or k == "unreached":
            continue
        fs = func_start(a)
        if fs is not None:
            funcs.setdefault(fs, []).append(a)
    targets = sorted(funcs)
    print("semantic arg-sweep over %d flippable RO functions" % len(targets))

    BOUND = [0, 1, 2, 3, M, 0x80000000, 0x7FFFFFFF, SCRATCH, 0xFF, 0x10]
    trace = os.path.join(TMP, "argsweep.txt")
    if os.path.exists(trace):
        os.remove(trace)

    s = [fcall.Session(binp, boot="1.5", trace=trace)]
    n = [0]

    def fold():
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

    def reboot():
        s[0].close(); fold()
        s[0] = fcall.Session(binp, boot="1.5", trace=trace); n[0] = 0

    for fi, fs in enumerate(targets):
        vals = sorted(func_consts(fs, fs + 0x400) | set(BOUND))
        vals = vals[:40]                       # cap per-function
        crashes = 0
        for v in vals:
            if crashes >= 4:
                break
            try:
                # r0=v (the dispatched/compared arg), r1=scratch ptr, r2=v, r3=0
                s[0].rsp.writemem(SCRATCH, b"\x00" * 64)
                s[0].rsp.call(fs, (v, SCRATCH, v, 0), timeout_continue=1)
                n[0] += 1; crashes = 0
            except Exception:
                crashes += 1; reboot()
        # also sweep r1 for a few funcs (second-arg dispatch)
        for v in vals[:8]:
            try:
                s[0].rsp.call(fs, (SCRATCH, v, 0, 0), timeout_continue=1)
            except Exception:
                reboot()
        if n[0] > 400:                          # periodic checkpoint
            s[0].close(); fold()
            with open(out, "wb") as f:
                pickle.dump((executed, edges), f)
            s[0] = fcall.Session(binp, boot="1.5", trace=trace); n[0] = 0
        if fi % 20 == 0:
            print("  ...%d/%d funcs, %d edges, %d PCs" % (fi, len(targets), len(edges), len(executed)))

    s[0].close(); fold()
    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/argsweep_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
