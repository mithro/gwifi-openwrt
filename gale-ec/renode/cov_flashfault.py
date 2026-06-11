#!/usr/bin/env python3
"""FLASH-FAULT direct-call lever — covers the flash wait_busy/PGERR/WRPRTERR TIMEOUT-error arms that a
healthy op never hits, WITHOUT the trace blowup that killed the console-driven approach. Key technique:
boot a GDB-stub session with the GaleFlash fault knob pre-set via `mon=` (StuckBusy / InjectProgErr /
InjectWriteProtErr), then DIRECT-CALL ONE flash op and trace just that call. A single wait_busy timeout
is loop-bounded (~1.5M instr ~ a few MB trace), so one-op-per-session stays bounded — unlike the live
firmware where the fault recurs across many ops and the global trace explodes.
Validated: flash_physical_write(0x18000,4,buf) with StuckBusy returns 0x4 (EC_ERROR_TIMEOUT) -> the
error path is genuinely taken. Captured: flash_physical_write@0x08001024, flash_physical_erase@0x080010e0,
write_optb@0x08000f44 (+ RW mirrors @ +0x10000). Accumulates tmp/flashfault_edges.pkl.
Usage: uv run --python .venv python cov_flashfault.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

DBUF = 0x20002400        # source data for writes

# (label, func_addr, args, fault_monitor_cmd)
def cases():
    out = []
    for base in (0x08000000, 0x08010000):
        wr = base + 0x1024          # flash_physical_write(offset, size, data)
        er = base + 0x10e0          # flash_physical_erase(offset, size)
        wo = base + 0x0f44          # write_optb(byte, value)
        roff = 0x18000              # an RW-region offset
        for fault in ('StuckBusy true', 'InjectProgErr true', 'InjectWriteProtErr true'):
            out.append(("write/%s/%x" % (fault.split()[0], base), wr, (roff, 4, DBUF, 0), fault, 10))
            out.append(("erase/%s/%x" % (fault.split()[0], base), er, (roff, 0x800, 0, 0), fault, 10))
            # write_optb runs MANY wait_busy spins under a persistent StuckBusy -> needs a long timeout.
            out.append(("optb/%s/%x" % (fault.split()[0], base), wo, (0, 0xAA, 0, 0), fault, 40))
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
    out = os.path.join(TMP, "flashfault_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    for label, func, args, fault, tmo in cases():
        trace = os.path.join(TMP, "flashfault.txt")
        if os.path.exists(trace):
            os.remove(trace)
        # one op per session: the fault knob is pre-armed, the single op's spin is bounded.
        s = fcall.Session(binp, boot="1.5", mon=['sysbus.flashif %s' % fault], trace=trace)
        try:
            s.rsp.writemem(DBUF, bytes([0xA5, 0x5A, 0xC3, 0x3C]))
            r0 = s.rsp.call(func, args, timeout_continue=tmo)
            print("  %-26s -> r0=0x%x" % (label, r0 & 0xFFFFFFFF))
        except Exception as e:
            print("  %-26s -> EXC %s" % (label, e))
        finally:
            s.close()
            fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/flashfault_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
