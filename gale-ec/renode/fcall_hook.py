"""Call hook_notify(hook_type) candidates to fire DECLARE_HOOK handlers IN THEIR PROPER CONTEXT
(the never-entered set is dominated by chipset_startup/shutdown/suspend/resume/init/sysjump/second
handlers that only run when their hook fires). Sweep hook_type 0..24 with pointer-filled globals.
Signature match for hook_notify was weak, so drive all top candidates; the real one fires the
handlers, wrong ones fault-and-skip. Accumulates tmp/hook_edges.pkl. Genuine execution.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
GLO_LO, GLO_HI = 0x20000000, 0x20001df0
SCRATCH = 0x20002000
# confirmed hook_notify (byte-identical structure to rebuilt): RO 0x08004c60 + RW mirror
CANDS = [0x08004c60, 0x08014c60]


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
    out = os.path.join(TMP, "hook_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass
    trace = os.path.join(TMP, "hook.txt")
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
    def write_glob():
        if sp[0] == 0:
            s[0].rsp.writemem(GLO_LO, ptrfill); return
        plo, phi = sp[0] - 0x800, sp[0] + 0x400
        if plo > GLO_LO:
            s[0].rsp.writemem(GLO_LO, ptrfill[:plo - GLO_LO])
        if phi < GLO_HI:
            s[0].rsp.writemem(phi, ptrfill[phi - GLO_LO:])

    for fn in CANDS:
        if not ((0x08000000 <= fn < 0x0800b744) or (0x08010000 <= fn < 0x0801b744)):
            continue
        crashes = 0
        for htype in range(0, 25):
            if crashes >= 6:
                break
            try:
                # CLEAN boot globals — do NOT scribble; the hook handlers + deferred-call state must
                # be valid for the handlers to run instead of faulting (last pass corrupted them).
                s[0].rsp.call(fn, (htype, 0, 0, 0), timeout_continue=0.6)
                crashes = 0
            except Exception:
                crashes += 1; reboot()
        with open(out, "wb") as f:
            pickle.dump((executed, edges), f)
        print("  hook-swept 0x%08x" % fn)
    s[0].close(); fold(trace, executed, edges)
    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved %d edges, %d PCs -> tmp/hook_edges.pkl" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
