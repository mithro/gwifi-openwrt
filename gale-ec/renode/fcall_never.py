"""Directly invoke the still-never-entered pointer-table functions (DECLARE_HOST_COMMAND/CONSOLE/
HOOK handlers etc.) with pointer-filled globals + an argument sweep. The generic gfuzz crash-capped
these (they fault with garbage globals); pointer-fill makes their global pointer-derefs land in
zeroed scratch so the non-blocking ones actually run. Blocking ones are abandoned fast (crash-cap).
Computes the never-entered set from the live combined coverage. Accumulates tmp/never_edges.pkl.
"""
import os
import pickle
import struct

import fcall
import rda

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
GLO_LO, GLO_HI = 0x20000000, 0x20001df0
SCRATCH, SCRATCH2 = 0x20002000, 0x20002400
ARGS = [(0, 0, 0, 0), (SCRATCH, SCRATCH2, 0, 0), (1, SCRATCH, SCRATCH2, 0),
        (SCRATCH, SCRATCH2, SCRATCH2 + 0x100, 1), (2, SCRATCH, 0, 0), (0, SCRATCH, 16, 3)]


def text_ok(a):
    return (0x08000000 <= a < 0x0800b744) or (0x08010000 <= a < 0x0801b744)


def load_all_executed():
    ex = set()
    for n in ("cap_trace_cache.pkl", "sweep_edges.pkl", "fuzz_edges.pkl", "pdstate_edges.pkl",
              "printf_edges.pkl", "cmd_edges.pkl", "pure_edges.pkl", "struct_edges.pkl",
              "gfuzz_edges.pkl", "disp_edges.pkl", "never_edges.pkl"):
        p = os.path.join(TMP, n)
        if os.path.exists(p):
            with open(p, "rb") as f:
                ex |= set(pickle.load(f)[0])
    return ex


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
    out = os.path.join(TMP, "never_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass
    ptrs = rda.ptr_targets(binp)
    done = load_all_executed()
    never = sorted(p for p in ptrs if text_ok(p) and p not in done)
    print("targeting %d never-entered pointer-table functions" % len(never))

    trace = os.path.join(TMP, "never.txt")
    if os.path.exists(trace):
        os.remove(trace)
    nwords = (GLO_HI - GLO_LO) // 4
    ptrfill = struct.pack("<%dI" % nwords, *([SCRATCH] * nwords))

    s = [fcall.Session(binp, boot="1.5", trace=trace)]
    sp = [0]
    def read_sp():
        try:
            v = s[0].rsp.readreg(13); sp[0] = v if 0x20000000 <= v <= 0x20002000 else 0
        except Exception:
            sp[0] = 0
    read_sp()
    def reboot():
        s[0].close(); fold(trace, executed, edges)
        s[0] = fcall.Session(binp, boot="1.5", trace=trace); read_sp()
    def ckpt():
        with open(out, "wb") as f:
            pickle.dump((executed, edges), f)
    def write_glob():
        if sp[0] == 0:
            s[0].rsp.writemem(GLO_LO, ptrfill); return
        plo, phi = sp[0] - 0x800, sp[0] + 0x400
        if plo > GLO_LO:
            s[0].rsp.writemem(GLO_LO, ptrfill[:plo - GLO_LO])
        if phi < GLO_HI:
            s[0].rsp.writemem(phi, ptrfill[phi - GLO_LO:])

    entered = 0
    for i, fn in enumerate(never):
        crashes = 0
        before = fn in executed
        for v in ARGS:
            if crashes >= 3:
                break
            try:
                write_glob()
                s[0].rsp.writemem(SCRATCH, b"\x00" * 0x800)
                s[0].rsp.writemem(SCRATCH2, b"\x00" * 0x400)
                s[0].rsp.call(fn, v, timeout_continue=0.5)
                crashes = 0
            except Exception:
                crashes += 1; reboot()
        if fn in executed and not before:
            entered += 1
        if (i + 1) % 10 == 0:
            ckpt(); print("  ...%d/%d, %d newly entered, %d edges" % (i + 1, len(never), entered, len(edges)))
    s[0].close(); fold(trace, executed, edges); ckpt()
    print("saved %d edges, %d PCs; %d funcs newly entered -> tmp/never_edges.pkl"
          % (len(edges), len(executed), entered))


if __name__ == "__main__":
    main()
