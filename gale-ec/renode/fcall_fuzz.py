#!/usr/bin/env python3
"""Coverage-GUIDED function fuzzer (AFL-style feedback, applied per firmware function via Renode's
GDB stub). The fixed-vector sweep (fcall_sweep.py) only flips a branch if one of its 4 hand-picked
argument tuples happens to satisfy the predicate; this driver instead KEEPS any input that reveals a
new edge and mutates it further, so argument-dependent conditionals get flipped systematically.

It is TARGETED: it reads the current uncovered-branch list (cap_uncovered.txt, produced by
combine_coverage.py), maps each uncovered branch back to its containing function (nearest discovered
entry <= the branch address), and fuzzes ONLY those functions — the ones still hiding a
one-direction-only or unreached branch. Functions already saturated are skipped.

Feedback signal: Renode's CreateExecutionTracing flushes the PC stream to a file incrementally, so
the bytes appended since the previous call ARE that input's executed-PC list — no gdb single-step
needed. Each call's edge set is diffed against the running global edge set; an input that adds edges
is promoted into the corpus.

This is genuine execution of the real captured firmware with real (mutated) inputs — never a faked
branch outcome. Output: tmp/fuzz_edges.pkl = (executed, edges), unioned by combine_coverage.py.

Usage: uv run --python .venv python fcall_fuzz.py [--bin <fw>] [--calls-per-func N] [--stall N]
                                                  [--per-session N] [--max-funcs N]
"""
import argparse
import os
import pickle

import fcall
import rda

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
SCRATCH = 0x20002000          # RAM pointer args point here; we fuzz the bytes underneath
SCRATCH2 = 0x20002400
SCRATCH_LEN = 256

# "Interesting" 32-bit values: argc-style small ints, signs/extremes, and valid RAM/flash pointers
# (so a pointer arg both points at fuzzable scratch and, alternately, at NULL / a bad address).
INTERESTING = [0, 1, 2, 3, 4, 5, 8, 16, 0xFF, 0x100, 0x7F, 0x80, 0x7FFF, 0x8000,
               0xFFFF, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xFFFFFFFE,
               SCRATCH, SCRATCH2, SCRATCH + 4, 0x20001000, 0x08000000, 0x40021000]
# Deterministic byte patterns for the scratch region (no Math.random in this env; index-derived).
BYTE_PATTERNS = [b"\x00" * SCRATCH_LEN, b"\xff" * SCRATCH_LEN,
                 bytes((i * 17) & 0xff for i in range(SCRATCH_LEN)),
                 bytes((i & 1) and 0xff or 0x00 for i in range(SCRATCH_LEN)),
                 bytes(((i // 4) & 0xff) for i in range(SCRATCH_LEN))]


def lcg(seed):
    """Tiny deterministic PRNG (Math.random is banned in the JS workflow env; here it's plain
    Python, but a fixed-seed LCG keeps the whole fuzz run reproducible run-to-run)."""
    x = seed & 0xFFFFFFFF
    while True:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        yield x


def text_ok(a):
    return (0x08000000 <= a < 0x0800b744) or (0x08010000 <= a < 0x0801b744)


def prologue_entries(binp):
    """Discover function entries that rda misses because they are reached only indirectly (via the
    scheduler / a fall-through), by scanning .text for the canonical Thumb prologue `push {..,lr}`
    (0xB5xx). These are exactly the functions whose branches show up as 'unreached' lumped under an
    earlier entry. File offset = addr - 0x08000000 for both RO and RW banks (128 KiB packed dump)."""
    with open(binp, "rb") as f:
        img = f.read()
    out = set()
    for lo, hi in ((0x08000000, 0x0800b744), (0x08010000, 0x0801b744)):
        a = lo
        while a + 2 <= hi:
            o = a - 0x08000000
            if o + 2 <= len(img):
                hw = img[o] | (img[o + 1] << 8)
                if 0xB500 <= hw <= 0xB5FF:        # push {rlist, lr}
                    out.add(a)
            a += 2
    return out


def load_uncovered():
    """Uncovered branch addresses from the last combine_coverage.py run (one-dir-only + unreached).
    These are the branches worth attacking. If absent, returns None (fuzz all functions)."""
    p = os.path.join(HERE, "cap_uncovered.txt")
    if not os.path.exists(p):
        return None
    out = set()
    with open(p) as f:
        for ln in f:
            ln = ln.strip().split()
            if ln and ln[0].startswith("0x"):
                try:
                    out.add(int(ln[0], 16))
                except ValueError:
                    pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=CAPTURED)
    ap.add_argument("--calls-per-func", type=int, default=80,
                    help="cap; actual budget is yield-adaptive up to this")
    ap.add_argument("--stall", type=int, default=24, help="give up a func after N no-new-edge calls")
    ap.add_argument("--per-session", type=int, default=60)
    ap.add_argument("--max-funcs", type=int, default=0, help="0 = all targeted functions")
    ap.add_argument("--skip-funcs", type=int, default=0,
                    help="skip the first N yield-ordered functions (fuzz the lower-yield tail)")
    ap.add_argument("--call-timeout", type=float, default=1.0,
                    help="seconds to wait for a single function call to return before abandoning it")
    args = ap.parse_args()
    binp = os.path.abspath(args.bin)
    os.makedirs(TMP, exist_ok=True)

    # discover function entries + branch map on the captured image. Richer entry set than rda alone:
    # bl targets ∪ pointer-table targets ∪ prologue-scan entries (indirectly-reached functions), so
    # each uncovered branch is attributed to its TRUE containing function and can be direct-called.
    ins, cond, calls = rda.analyze(binp, extra_seeds=rda.ptr_targets(binp))
    pro = prologue_entries(binp)
    entries = sorted(f for f in (set(calls) | rda.ptr_targets(binp) | pro) if text_ok(f))
    print("entries: %d (rda calls+ptrs + %d prologue-scan)" % (len(entries), len(pro)))
    uncovered = load_uncovered()

    def containing(addr):
        lo, hi, mid = 0, len(entries), -1
        # rightmost entry <= addr
        import bisect
        i = bisect.bisect_right(entries, addr) - 1
        return entries[i] if i >= 0 else None

    yield_by = {}
    if uncovered is None:
        target_funcs = entries
        print("no cap_uncovered.txt -> fuzzing ALL %d functions" % len(entries))
    else:
        for a in uncovered:
            if a in cond:                       # only real branch sites
                c = containing(a)
                if c is not None:
                    yield_by[c] = yield_by.get(c, 0) + 1
        # highest-yield functions first so early runtime buys the most coverage
        target_funcs = sorted(yield_by, key=lambda f: (-yield_by[f], f))
        print("targeting %d functions that contain >=1 of %d uncovered branches "
              "(top yield: %s)"
              % (len(target_funcs), len(uncovered),
                 ", ".join("0x%x:%d" % (f, yield_by[f]) for f in target_funcs[:5])))
    if args.skip_funcs:
        target_funcs = target_funcs[args.skip_funcs:]
    if args.max_funcs:
        target_funcs = target_funcs[:args.max_funcs]

    trace = os.path.join(TMP, "fuzz.txt")
    if os.path.exists(trace):
        os.remove(trace)
    # ACCUMULATE across runs: load any prior fuzz_edges.pkl so a second pass (e.g. enhanced selectors,
    # or a different --max-funcs slice) UNIONS into the existing coverage instead of overwriting it.
    executed, edges = set(), set()
    prior = os.path.join(TMP, "fuzz_edges.pkl")
    if os.path.exists(prior):
        try:
            with open(prior, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior fuzz_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior fuzz_edges.pkl (%s); starting fresh" % e)
    rng = lcg(0xC0FFEE)

    # ---- session management ---------------------------------------------------------------------
    state = {"s": None, "calls": 0, "fpos": 0}

    def write_scratch(s, pat):
        try:
            s.rsp.writemem(SCRATCH, pat)
            s.rsp.writemem(SCRATCH2, pat)
        except Exception:
            pass

    def fresh():
        if state["s"] is not None:
            state["s"].close()
        state["s"] = fcall.Session(binp, boot="1.5", trace=trace)
        state["calls"] = 0
        # after close()+reopen the trace file is recreated; resync our read position
        state["fpos"] = os.path.getsize(trace) if os.path.exists(trace) else 0
        write_scratch(state["s"], BYTE_PATTERNS[0])

    def read_new_pcs():
        """PCs appended to the trace since the last call -> this call's executed set + edges."""
        pcs = []
        if not os.path.exists(trace):
            return pcs
        with open(trace) as f:
            f.seek(state["fpos"])
            chunk = f.read()
            state["fpos"] = f.tell()
        for ln in chunk.splitlines():
            ln = ln.strip()
            if len(ln) < 4 or not ln.startswith("0x"):
                continue
            try:
                pcs.append(int(ln, 16))
            except ValueError:
                pass
        return pcs

    def run_input(func, regs, pat):
        """Call func with regs (and scratch=pat); return number of globally-new edges, or None on
        crash/hang (caller reboots)."""
        s = state["s"]
        write_scratch(s, pat)
        try:
            s.rsp.call(func, regs, timeout_continue=args.call_timeout)
        except Exception:
            return None
        state["calls"] += 1
        pcs = read_new_pcs()
        new = 0
        prev = None
        for pc in pcs:
            executed.add(pc)
            if prev is not None:
                e = (prev, pc)
                if e not in edges:
                    edges.add(e); new += 1
            prev = pc
        return new

    # ---- per-function guided fuzz ---------------------------------------------------------------
    # Seeds: a DENSE r0=0..47 selector sweep (cracks switch() dispatchers keyed on an enum arg, the
    # dominant 'unreached' pattern) followed by pointer-shaped vectors. Adaptive budget caps how many
    # a low-yield leaf actually tries; a 178-branch dispatcher gets the whole sweep.
    SEEDS = [(i, SCRATCH, SCRATCH2, 0) for i in range(48)] + \
            [(0, 0, 0, 0), (0xFFFFFFFF, 0xFFFFFFFF, 0, 0), (SCRATCH, SCRATCH2, 1, 0),
             (1, SCRATCH, 0, 0)]

    def mutate(regs, pat):
        r = list(regs)
        k = next(rng) % 5
        if k < 3:                                   # mutate one register to an interesting value
            idx = next(rng) % 4
            r[idx] = INTERESTING[next(rng) % len(INTERESTING)]
        elif k == 3:                                # bit-flip a register
            idx = next(rng) % 4
            r[idx] = (r[idx] ^ (1 << (next(rng) % 32))) & 0xFFFFFFFF
        else:                                       # swap to a different scratch byte-pattern
            pat = BYTE_PATTERNS[next(rng) % len(BYTE_PATTERNS)]
        return tuple(r), pat

    fresh()
    funcs_done = 0
    for fi, func in enumerate(target_funcs):
        # yield-adaptive budget: a 178-branch dispatcher earns the full cap; a 1-branch leaf
        # gets just enough to try a handful of seeds + a few mutations.
        y = yield_by.get(func, 1)
        budget = max(12, min(args.calls_per_func, 10 + 2 * y))
        corpus = []                                 # inputs that revealed new edges -> mutate later
        crashes = 0                                  # a func that faults every call wastes a ~10s
        CRASH_CAP = 4                                # reboot per call -> abandon after a few crashes
        # Phase 1: raw seeds (the dense r0 selector sweep). Run EVERY seed up to budget regardless of
        # barren results — switch case values aren't contiguous, so a no-new-edge selector must not
        # abort the sweep. This is what cracks switch() dispatchers; mutation alone never sweeps one.
        for s in SEEDS:
            if budget <= 0 or crashes >= CRASH_CAP:
                break
            regs, pat = tuple(s), BYTE_PATTERNS[0]
            new = run_input(func, regs, pat)
            budget -= 1
            if new is None:
                crashes += 1; fresh(); continue
            crashes = 0
            if new > 0:
                corpus.append((regs, pat))
            if state["calls"] >= args.per_session:
                fresh()
        # Phase 2: mutate the productive seeds to flip the remaining argument-dependent edges.
        stall = 0
        if not corpus:
            corpus = [(tuple(SEEDS[0]), BYTE_PATTERNS[0])]
        ci = 0
        while budget > 0 and stall < args.stall and crashes < CRASH_CAP:
            base_regs, base_pat = corpus[ci % len(corpus)]
            ci += 1
            regs, pat = mutate(base_regs, base_pat)
            new = run_input(func, regs, pat)
            budget -= 1
            if new is None:
                crashes += 1; fresh(); stall += 1; continue
            crashes = 0
            if new > 0:
                corpus.append((regs, pat)); stall = 0
            else:
                stall += 1
            if state["calls"] >= args.per_session:
                fresh()
        funcs_done += 1
        if funcs_done % 10 == 0:
            print("  ...%d/%d funcs fuzzed, %d edges, %d PCs"
                  % (funcs_done, len(target_funcs), len(edges), len(executed)))
            # checkpoint so a long run is never lost
            with open(os.path.join(TMP, "fuzz_edges.pkl"), "wb") as f:
                pickle.dump((executed, edges), f)
    if state["s"] is not None:
        state["s"].close()

    with open(os.path.join(TMP, "fuzz_edges.pkl"), "wb") as f:
        pickle.dump((executed, edges), f)

    taken = set(a for a in cond if (a, cond[a][1]) in edges)
    nottaken = set(a for a in cond if (a, cond[a][0]) in edges)
    both = [a for a in cond if a in taken and a in nottaken]
    reached = [a for a in cond if a in executed]
    print("\nfuzz-only coverage: %d reached, %d both-dirs (of %d rda branches)"
          % (len(reached), len(both), len(cond)))
    print("saved executed/edges -> tmp/fuzz_edges.pkl (union with campaign+sweep for total)")


if __name__ == "__main__":
    main()
