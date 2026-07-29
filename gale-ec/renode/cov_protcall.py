#!/usr/bin/env python3
"""FLASH-PROTECT / IMAGE-COPY direct-call lever — drives the flash_set_protect + system_run_image_copy
arms that need specific mask/flags, a pre-existing protect state, an at-boot-protect FAILURE, or the
system-locked state. Uses the validated direct-call + mon=-preset technique (entries confirmed by disasm):
  flash_set_protect@0x0800451c (uint32 mask, uint32 flags) -> the ALL_AT_BOOT(:491)/RO_NOW(:518) mask arms,
    the RO_AT_BOOT-already-set arm (:493, needs flash_get_protect()&RO_AT_BOOT -> WrpValue RO-protected),
    and the flash_protect_at_boot()-FAILED arms (:514/:521 if(rv) -> mon StuckBusy makes write_optb time out).
  system_run_image_copy@0x08006874 (enum copy) -> the switch(copy) cases (:105), bounds (:338/:588), and the
    system_is_locked() arm (:544 -> WrpValue RO-protected so system_is_locked() returns true).
Genuine execution of the real functions on injected args/state. RO + RW. Accumulates tmp/protcall_edges.pkl.
Usage: uv run --python .venv python cov_protcall.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

RO_AT_BOOT, RO_NOW, ALL_NOW, ALL_AT_BOOT = 0x01, 0x02, 0x04, 0x40
M = 0xFFFFFFFF
WRP_RO = 'sysbus.flashif WrpValue 0xFFFF0000'   # RO-protected pattern -> flash_get_protect reports RO_NOW
STUCK = 'sysbus.flashif StuckBusy true'


def cases():
    out = []
    for base in (0x08000000, 0x08010000):
        fsp = base + 0x451c          # flash_set_protect(mask, flags)
        sri = base + 0x6874          # system_run_image_copy(copy)
        # flash_set_protect: (label, func, args, mon-list, timeout)
        for mask, flags, mon, tmo in [
            (ALL_AT_BOOT, ALL_AT_BOOT, [], 6), (ALL_AT_BOOT, 0, [], 6),
            (RO_NOW, RO_NOW, [], 6), (RO_NOW | ALL_NOW, M, [], 6),
            (RO_AT_BOOT, RO_AT_BOOT, [], 6), (RO_AT_BOOT | ALL_AT_BOOT, M, [], 6),
            (ALL_NOW, ALL_NOW, [], 6), (M, M, [], 8),
            # at-boot-protect FAILS (write_optb times out) -> if(rv) arms
            (ALL_AT_BOOT, ALL_AT_BOOT, [STUCK], 12), (RO_AT_BOOT, RO_AT_BOOT, [STUCK], 12),
            # RO_AT_BOOT already set (WrpValue RO-protected) then request ALL_AT_BOOT
            (ALL_AT_BOOT, ALL_AT_BOOT, [WRP_RO], 8), (RO_NOW, RO_NOW, [WRP_RO], 8),
        ]:
            out.append(("fsp/m%x/f%x/%s/%x" % (mask, flags, "+".join(m.split()[1] for m in mon) or "-", base),
                        fsp, (mask, flags, 0, 0), mon, tmo))
        # system_run_image_copy: copy 0..5, plus locked (WrpValue RO-protected)
        for copy in (0, 1, 2, 3, 4, 5):
            out.append(("sri/c%d/%x" % (copy, base), sri, (copy, 0, 0, 0), [], 3))
        for copy in (1, 2):
            out.append(("sri/c%d/locked/%x" % (copy, base), sri, (copy, 0, 0, 0), [WRP_RO], 3))
    return out


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
    out = os.path.join(TMP, "protcall_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    for label, func, args, mon, tmo in cases():
        trace = os.path.join(TMP, "protcall.txt")
        if os.path.exists(trace):
            os.remove(trace)
        s = fcall.Session(binp, boot="1.5", mon=mon, trace=trace)
        try:
            r0 = s.rsp.call(func, args, timeout_continue=tmo)
            print("  %-30s -> r0=0x%x" % (label, r0 & 0xFFFFFFFF))
        except Exception as e:
            print("  %-30s -> EXC %s" % (label, str(e)[:30]))
        finally:
            s.close()
            fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/protcall_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
