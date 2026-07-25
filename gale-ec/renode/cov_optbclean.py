"""CLEAN-FLASH-OP lever — the mirror of cov_flashfault. That lever direct-calls write_optb /
flash_physical_write / flash_physical_erase ONLY with a fault pre-armed (StuckBusy / InjectProgErr /
InjectWriteProtErr), so wait_busy() returns nonzero and each function bails at its FIRST check — leaving
every downstream SUCCESS branch dark (the report shows write_optb's wait_busy/unlock success fall-throughs
+ the `*hword == value` fast path + the OPTPG/lock tail as nottaken-only/unreached). GaleFlash models
SR.BSY=0 (instant op) + OPTKEYR->OPTWRE, so a CLEAN direct-call (no fault) walks the whole success ladder,
including preserve_optb's recursive write_optb calls. Two write_optb values cover both the "already equal"
fast path (value==current 0xff) and the full erase+program path (value!=current).
Direct execution of the captured firmware, no faked outcomes. RO + RW mirrors. Accumulates
tmp/optbclean_edges.pkl. Usage: uv run --python .venv python cov_optbclean.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

DBUF = 0x20002400        # source data for writes


def cases():
    """(label, func_addr, args, timeout) — NO fault monitor, clean completing ops."""
    out = []
    for base in (0x08000000, 0x08010000):
        wr = base + 0x1024          # flash_physical_write(offset, size, data)
        er = base + 0x10e0          # flash_physical_erase(offset, size)
        wo = base + 0x0f44          # write_optb(byte, value)
        roff = 0x18000              # an RW-region offset
        # write_optb: value==0xff vs current(0xff) -> `*hword==value` fast SUCCESS path (:172-ish);
        # value!=0xff -> preserve_optb (recursion) + unlock + OPTPG + write + wait_busy success + lock.
        out.append(("optb/eq0xff/%x" % base, wo, (0, 0xFF, 0, 0), 20))
        out.append(("optb/wr0xAA/%x" % base, wo, (0, 0xAA, 0, 0), 40))
        out.append(("optb/wr0x55b2/%x" % base, wo, (2, 0x55, 0, 0), 40))
        # flash_physical_write / erase: clean completion -> their EC_SUCCESS tails (no WRPRTERR/PGERR).
        out.append(("write/clean/%x" % base, wr, (roff, 4, DBUF, 0), 15))
        out.append(("erase/clean/%x" % base, er, (roff, 0x800, 0, 0), 15))
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
    out = os.path.join(TMP, "optbclean_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    for label, func, args, tmo in cases():
        trace = os.path.join(TMP, "optbclean.txt")
        if os.path.exists(trace):
            os.remove(trace)
        # clean model: NO fault monitor -> BSY=0, OPTKEYR unlocks -> success ladder runs.
        s = fcall.Session(binp, boot="1.5", trace=trace)
        try:
            s.rsp.writemem(DBUF, bytes([0xA5, 0x5A, 0xC3, 0x3C]))
            r0 = s.rsp.call(func, args, timeout_continue=tmo)
            print("  %-22s -> r0=0x%x" % (label, r0 & 0xFFFFFFFF))
        except Exception as e:
            print("  %-22s -> EXC %s" % (label, e))
        finally:
            s.close()
            fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/optbclean_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
