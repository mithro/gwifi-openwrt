#!/usr/bin/env python3
"""Concolic/symbolic input-generation engine (angr) for the captured gale EC firmware.

For each reached-one-direction (flippable) branch, angr symbolically executes from the containing
function's entry with symbolic args + symbolic memory, and SOLVES for concrete inputs that drive the
branch's UNCOVERED edge. The solution (r0-r3 + a set of (addr,value) memory constraints) is emitted as
JSON; fcall_concolic.py then replays it in Renode for GENUINE execution (the real CPU takes the real
branch on the solved inputs — angr only generates the inputs, it never substitutes for execution).

This is the scalable answer to the state-coupled branches fuzzing can't flip: angr solves the path
constraints algebraically (magic values, nested conditions) instead of guessing.

Run with the isolated angr venv:  uv run --python .venv-angr python concolic_solve.py [--max N]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = 0x08000000
OUT = os.path.join(HERE, "tmp", "concolic_solutions.json")

import angr  # noqa: E402
import claripy  # noqa: E402
import capstone  # noqa: E402
import logging  # noqa: E402

logging.getLogger("angr").setLevel(logging.ERROR)
logging.getLogger("cle").setLevel(logging.ERROR)
logging.getLogger("pyvex").setLevel(logging.ERROR)

DATA = open(CAPTURED, "rb").read()
MD = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)


def func_start(addr):
    for back in range(0, 1400, 2):
        off = addr - back - BASE
        if off < 0:
            break
        for ins in MD.disasm(DATA[off:off + 2], addr - back):
            if ins.mnemonic == 'push' and 'lr' in ins.op_str:
                return addr - back
    return None


def branch_succs(addr):
    """For the B<cond> at addr: (fall_through, target). ARMv6-M: 16-bit B<cond> (T1)."""
    off = addr - BASE
    for ins in MD.disasm(DATA[off:off + 4], addr):
        if ins.op_str.startswith('#'):
            tgt = int(ins.op_str[1:], 0)
            return addr + ins.size, tgt
    return None, None


def load_targets():
    """reached-one-direction RO branches: (addr, covered_dir, missing_succ)."""
    out = []
    for l in open(os.path.join(HERE, "cap_uncovered.txt")):
        if not l.startswith("0x"):
            continue
        a, k = l.split(); a = int(a, 16)
        if a >= 0x08010000 or k == "unreached":
            continue
        ft, tgt = branch_succs(a)
        if ft is None:
            continue
        # taken-only covered -> missing edge is fall-through; nottaken-only -> missing is target
        missing = ft if k == "taken-only" else tgt
        out.append((a, k, missing))
    return out


def make_project():
    for arch in ("ARMCortexM", "ARMEL"):
        try:
            return angr.Project(CAPTURED, main_opts={
                "backend": "blob", "arch": arch, "base_addr": BASE}, auto_load_libs=False)
        except Exception as e:
            last = e
    raise last


import signal  # noqa: E402


class _Timeout(Exception):
    pass


def solve_one(proj, fstart, missing, avoid, max_steps=64, loop_bound=6):
    """Symbolically run F from entry; find a state at `missing`, avoiding `avoid`. Return solved
    {args, mem} or None. Bounded: LoopSeer + LengthLimiter cap path explosion; a SIGALRM wall-clock
    timeout (set by the caller) aborts a runaway exploration."""
    # Concrete-memory mode: do NOT symbol-fill memory/regs (that explodes on pointer derefs).
    # Only r0-r3 are symbolic; uninitialized memory reads return concrete 0; calls are skipped
    # (CALLLESS) so a `bl FUNC; cmp r0,#0` branch has r0 unconstrained and is solvable. This solves
    # arg-dependent + call-result branches fast; struct/global branches get concrete-0 memory.
    opts = {angr.options.CALLLESS} if hasattr(angr.options, "CALLLESS") else set()
    opts |= {angr.options.ZERO_FILL_UNCONSTRAINED_MEMORY,
             angr.options.ZERO_FILL_UNCONSTRAINED_REGISTERS}
    st = proj.factory.blank_state(addr=fstart | 1, add_options=opts)
    args = [claripy.BVS("r%d" % i, 32) for i in range(4)]
    st.regs.r0, st.regs.r1, st.regs.r2, st.regs.r3 = args
    st.regs.sp = 0x20008000
    st.regs.lr = 0xDEADBEEF
    simgr = proj.factory.simgr(st)
    try:
        simgr.use_technique(angr.exploration_techniques.LoopSeer(bound=loop_bound))
        simgr.use_technique(angr.exploration_techniques.LengthLimiter(max_length=max_steps))
    except Exception:
        pass
    # angr ARMCortexM state addresses carry the thumb bit (odd) — match find/avoid with it set.
    try:
        simgr.explore(find=missing | 1, avoid=[avoid | 1, 0xDEADBEEF, 0xDEADBEEE], num_find=1)
    except _Timeout:
        return None
    except Exception:
        return None
    if not simgr.found:
        return None
    f = simgr.found[0]
    sol = {"r%d" % i: f.solver.eval(args[i]) & 0xFFFFFFFF for i in range(4)}
    return {"args": sol, "mem": []}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--per-branch", type=int, default=20, help="per-branch wall-clock timeout (s)")
    args = ap.parse_args()

    os.makedirs(os.path.join(HERE, "tmp"), exist_ok=True)
    sols = {}
    if os.path.exists(OUT):
        try:
            sols = json.load(open(OUT))
        except Exception:
            sols = {}

    proj = make_project()
    targets = load_targets()
    print("concolic: %d flippable RO branches; solving %d (skip %d)"
          % (len(targets), args.max, args.skip), flush=True)

    def _alarm(signum, frame):
        raise _Timeout()
    signal.signal(signal.SIGALRM, _alarm)
    PER = args.per_branch

    done = 0
    for (a, k, missing) in targets[args.skip:]:
        if done >= args.max:
            break
        key = hex(a)
        if key in sols:
            continue
        fstart = func_start(a)
        if fstart is None:
            continue
        ft, tgt = branch_succs(a)
        avoid = tgt if missing == ft else ft
        signal.alarm(PER)
        try:
            sol = solve_one(proj, fstart, missing, avoid)
        except Exception:
            sol = None
        finally:
            signal.alarm(0)
        done += 1
        if sol:
            sol["func"] = fstart
            sol["branch"] = a
            sols[key] = sol
            print("  SOLVED %s (func %#x): %s" % (key, fstart, sol["args"]), flush=True)
            json.dump(sols, open(OUT, "w"), indent=1)
        else:
            print("  unsolved %s (func %#x)" % (key, fstart), flush=True)
    json.dump(sols, open(OUT, "w"), indent=1)
    print("saved %d solutions -> %s" % (len(sols), OUT))


if __name__ == "__main__":
    main()
