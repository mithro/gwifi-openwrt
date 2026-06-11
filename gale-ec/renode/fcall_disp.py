"""Focused driver for the big PD-policy dispatcher region 0x8007f8e / 0x8017f8e (~17% of the
remaining gap). It dispatches on r3 (PD_DRP_* dual-role mode) and reads many globals; the generic
gfuzz left r3=0 and crash-capped it. Here we combine the working techniques: pointer-fill the whole
globals window (so global pointer-derefs hit zeroed scratch instead of faulting) AND sweep r3 over
the dual-role modes + r0-r2 over scratch/values, many rounds, rebuilding on crash but never giving
up early. Accumulates tmp/disp_edges.pkl. Genuine execution.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
GLO_LO, GLO_HI = 0x20000000, 0x20001df0
SCRATCH, SCRATCH2 = 0x20002000, 0x20002400
FNS = [0x08007f8e, 0x08017f8e]
# (r0, r1, r2) shapes; r3 swept separately over dual-role modes 0..3 + a few others
ARGS = [(0, SCRATCH, SCRATCH2), (1, SCRATCH, SCRATCH2), (SCRATCH, SCRATCH2, 1),
        (0xFFFFFFFF, SCRATCH, 0), (0, 0, 0), (2, SCRATCH, SCRATCH2)]
R3S = [0, 1, 2, 3, 4, 9, 0xFF]


def lcg(seed):
    x = seed & 0xFFFFFFFF
    while True:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        yield x


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
    out = os.path.join(TMP, "disp_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("fresh (%s)" % e)
    trace = os.path.join(TMP, "disp.txt")
    if os.path.exists(trace):
        os.remove(trace)
    nwords = (GLO_HI - GLO_LO) // 4
    rng = lcg(0x7f8e)

    s = [fcall.Session(binp, boot="1.5", trace=trace)]
    sp = [0]
    def read_sp():
        try:
            v = s[0].rsp.readreg(13)
            sp[0] = v if 0x20000000 <= v <= 0x20002000 else 0
        except Exception:
            sp[0] = 0
    read_sp()
    def reboot():
        s[0].close(); fold(trace, executed, edges)
        s[0] = fcall.Session(binp, boot="1.5", trace=trace); read_sp()
    def ckpt():
        with open(out, "wb") as f:
            pickle.dump((executed, edges), f)

    def write_glob(blk):
        if sp[0] == 0:
            s[0].rsp.writemem(GLO_LO, blk); return
        plo, phi = sp[0] - 0x800, sp[0] + 0x400
        if plo > GLO_LO:
            s[0].rsp.writemem(GLO_LO, blk[:plo - GLO_LO])
        if phi < GLO_HI:
            s[0].rsp.writemem(phi, blk[phi - GLO_LO:])

    ROUNDS = 14
    for fn in FNS:
        if not ((0x08000000 <= fn < 0x0800b744) or (0x08010000 <= fn < 0x0801b744)):
            continue
        for r in range(ROUNDS):
            if r == 0:
                blk = b"\x00" * (nwords * 4)
            elif r % 3 == 1:
                blk = struct.pack("<%dI" % nwords, *([SCRATCH] * nwords))   # pointer-fill
            elif r % 3 == 2:
                blk = struct.pack("<%dI" % nwords, *[(SCRATCH + ((i * 4) & 0x7f)) for i in range(nwords)])
            else:
                blk = struct.pack("<%dI" % nwords, *[next(rng) & 0xFFFFFFFF for _ in range(nwords)])
            for (r0, r1, r2) in ARGS:
                for r3 in R3S:
                    try:
                        write_glob(blk)
                        s[0].rsp.writemem(SCRATCH, b"\x00" * 0x800)
                        s[0].rsp.writemem(SCRATCH2, b"\x00" * 0x200)
                        s[0].rsp.call(fn, (r0, r1, r2, r3), timeout_continue=0.5)
                    except Exception:
                        reboot()
            ckpt()
        print("  dispatcher-swept 0x%08x" % fn)
    s[0].close(); fold(trace, executed, edges); ckpt()
    print("saved %d edges, %d PCs -> tmp/disp_edges.pkl" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
