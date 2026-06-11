"""Global-state fuzzer: the scalable version of the gate-write technique. The reached-one-direction
long tail is dominated by branches that test a GLOBAL variable; the plain argument fuzzer can't flip
them because it only varies r0-r3. Here, before each direct call we scribble a pseudo-random pattern
into the .data globals window (0x20001000..0x20001df0 — driver/state globals, kept clear of the boot
stack lower in RAM and the scheduler globals at 0x20001df8), then call the function with a few arg
vectors. The function executes for real against those global values, so global-dependent branches
flip both ways across rounds. Genuine execution, never a faked branch.

crash-cap + per-function checkpoint + 0.5s timeout. Accumulates tmp/gfuzz_edges.pkl.
Usage: uv run --python .venv python fcall_gfuzz.py [--max-funcs N] [--rounds R]
"""
import argparse
import os
import pickle
import struct

import fcall
import rda

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
GLO_LO, GLO_HI = 0x20001000, 0x20001df0    # .data globals window to mutate (safe-ish)
SCRATCH = 0x20002000
VECTORS = [(0, 0, 0, 0), (1, SCRATCH, 0, 0), (0xFFFFFFFF, 0xFFFFFFFF, 0, 0),
           (SCRATCH, SCRATCH + 0x400, 1, 0)]


def lcg(seed):
    x = seed & 0xFFFFFFFF
    while True:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        yield x


def text_ok(a):
    return (0x08000000 <= a < 0x0800b744) or (0x08010000 <= a < 0x0801b744)


def load_uncovered_funcs(entries):
    import bisect
    p = os.path.join(HERE, "cap_uncovered.txt")
    if not os.path.exists(p):
        return entries
    cnt = {}
    with open(p) as f:
        for ln in f:
            q = ln.split()
            if q and q[0].startswith("0x"):
                a = int(q[0], 16)
                i = bisect.bisect_right(entries, a) - 1
                if i >= 0:
                    cnt[entries[i]] = cnt.get(entries[i], 0) + 1
    return sorted(cnt, key=lambda f: (-cnt[f], f))


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-funcs", type=int, default=60)
    ap.add_argument("--rounds", type=int, default=12, help="random global-state rounds per function")
    ap.add_argument("--skip-funcs", type=int, default=0)
    ap.add_argument("--seed", type=lambda x: int(x,0), default=0x1234)
    ap.add_argument("--wide", action="store_true",
                    help="mutate the FULL globals 0x20000000..0x20001df0 (incl. low .bss), protecting "
                         "a window around the live stack pointer so the call frame survives")
    ap.add_argument("--funcs-file", default=None,
                    help="explicit newline-separated 0x-function list to target (overrides yield-sort)")
    ap.add_argument("--const-sweep", action="store_true",
                    help="instead of random rounds, byte-FILL the global window with each value in a "
                         "curated set (the firmware's own cmp immediates 0..N) so `cmp global_byte,#K` "
                         "flips deterministically (random scribbling only hits K with prob ~K/256).")
    args = ap.parse_args()
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "gfuzz_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("fresh (%s)" % e)

    ins, cond, calls = rda.analyze(binp, extra_seeds=rda.ptr_targets(binp))
    entries = sorted(f for f in (set(calls) | rda.ptr_targets(binp)) if text_ok(f))
    if args.funcs_file:                               # explicit target list (e.g. only global-byte-cmp funcs)
        funcs = [int(l, 0) for l in open(args.funcs_file) if l.strip().startswith("0x") and text_ok(int(l, 0))]
        funcs = funcs[args.skip_funcs:args.skip_funcs + args.max_funcs] if args.max_funcs else funcs[args.skip_funcs:]
    else:
        funcs = [f for f in load_uncovered_funcs(entries) if text_ok(f)][args.skip_funcs:args.skip_funcs+args.max_funcs]
    print("global-fuzzing %d functions x %d rounds" % (len(funcs), args.rounds))

    trace = os.path.join(TMP, "gfuzz.txt")
    if os.path.exists(trace):
        os.remove(trace)
    rng = lcg(args.seed)
    glo_lo = 0x20000000 if args.wide else GLO_LO
    nbytes = GLO_HI - glo_lo

    sp_prot = [0, 0]                              # [prot_lo, prot_hi] around the live stack pointer
    def read_sp_prot():
        try:
            sp = s_box[0].rsp.readreg(13)
            if 0x20000000 <= sp <= 0x20002000:
                sp_prot[0], sp_prot[1] = sp - 0x800, sp + 0x400
            else:
                sp_prot[0], sp_prot[1] = 0, 0
        except Exception:
            sp_prot[0], sp_prot[1] = 0, 0

    s_box = [fcall.Session(binp, boot="1.5", trace=trace)]
    s = s_box
    if args.wide:
        read_sp_prot()
    def reboot():
        s[0].close(); fold(trace, executed, edges)
        s[0] = fcall.Session(binp, boot="1.5", trace=trace)
        if args.wide:
            read_sp_prot()

    def write_globals(blk):
        if not args.wide or sp_prot[1] == 0:
            s[0].rsp.writemem(glo_lo, blk); return
        # write around the protected stack window so the call frame is not clobbered
        plo, phi = max(glo_lo, sp_prot[0]), min(GLO_HI, sp_prot[1])
        if plo > glo_lo:
            s[0].rsp.writemem(glo_lo, blk[:plo - glo_lo])
        if phi < GLO_HI:
            s[0].rsp.writemem(phi, blk[phi - glo_lo:])
    def ckpt():
        with open(out, "wb") as f:
            pickle.dump((executed, edges), f)

    def rand_block(n, salt):
        # deterministic pseudo-random bytes, varied per round/salt
        vals = bytearray(n)
        for i in range(0, n, 4):
            v = next(rng) ^ (salt * 2654435761 & 0xFFFFFFFF)
            vals[i:i+4] = struct.pack("<I", v & 0xFFFFFFFF)
        return bytes(vals)

    # const-sweep value set: the firmware's typical cmp immediates (small enums/states + a few bit masks).
    # Byte-filling the window with V makes every `cmp global_byte, #V` take its V-equal edge.
    SWEEP_VALS = list(range(0, 16)) + [0x20, 0x40, 0x7f, 0x80, 0xff]   # small enums/states + key masks
    n_rounds = len(SWEEP_VALS) if args.const_sweep else args.rounds

    done = 0
    for fn in funcs:
        crashes = 0
        for r in range(n_rounds):
            if crashes >= 4:
                break
            if args.const_sweep:
                blk = bytes([SWEEP_VALS[r]]) * nbytes
                for v in VECTORS:
                    try:
                        write_globals(blk)
                        s[0].rsp.writemem(SCRATCH, b"\x00" * 0x800)
                        s[0].rsp.call(fn, v, timeout_continue=0.5)
                        crashes = 0
                    except Exception:
                        crashes += 1; reboot(); break
                continue
            # round 0 = all-zero, 1 = all-0xFF, 2 = VALID-POINTER fill (every word = a safe RAM ptr,
            # so a global used as a pointer derefs into zeroed scratch instead of faulting -> the
            # body of pointer-heavy functions actually runs), 3 = pointer fill + low bits varied,
            # else pseudo-random.
            if r == 0:
                blk = b"\x00" * nbytes
            elif r == 1:
                blk = b"\xff" * nbytes
            elif r == 2:
                blk = struct.pack("<%dI" % (nbytes // 4), *([SCRATCH] * (nbytes // 4)))
            elif r == 3:
                blk = struct.pack("<%dI" % (nbytes // 4),
                                  *[(SCRATCH + ((i * 4) & 0x3f)) for i in range(nbytes // 4)])
            else:
                blk = rand_block(nbytes, r)
            for v in VECTORS:
                try:
                    write_globals(blk)
                    s[0].rsp.writemem(SCRATCH, b"\x00" * 0x800)
                    s[0].rsp.call(fn, v, timeout_continue=0.5)
                    crashes = 0
                except Exception:
                    crashes += 1; reboot()
                    break
        done += 1
        if done % 10 == 0:
            ckpt()
            print("  ...%d/%d funcs, %d edges, %d PCs" % (done, len(funcs), len(edges), len(executed)))
    s[0].close(); fold(trace, executed, edges); ckpt()
    print("saved %d edges, %d PCs -> tmp/gfuzz_edges.pkl" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
