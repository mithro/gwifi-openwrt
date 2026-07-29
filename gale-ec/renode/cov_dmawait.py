#!/usr/bin/env python3
"""DIRECT-CALL dma_wait lever (chip/stm32/dma.c:245, captured 0x08000d00). dma_wait polls
`while ((dma->isr & TCIF(ch)) != mask) { if (deadline <= get_time()) return TIMEOUT; udelay(); }`.
In every prior run TCIF was already set so dma_wait returned SUCCESS immediately — the TIMEOUT arm and
the deadline-compare (0x08000d3a low word) never ran. Here we direct-call dma_wait with the DMA ISR
flags CLEARED (IFCR W1C) + ForceAllTcif OFF so TCIF stays clear -> the loop spins; a fast timer makes
the 100ms deadline fire in a bounded trace -> the low-word timeout compare + return TIMEOUT execute.
(The HIGH-word compares 0x0d34/0d36 need get_time to straddle a 2^32-us boundary -> separate technique.)
RO + RW. Accumulates tmp/dmawait_edges.pkl.  Usage: uv run --python .venv python cov_dmawait.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
TMP = os.path.join(HERE, "tmp")
OFF = 0xd00               # dma_wait within each bank
CLEAR_ISR = 'sysbus WriteDoubleWord 0x40020004 0x0FFFFFFF'   # DMA1 IFCR (W1C) -> clear all flags

# The timeout loop must do >=1 WITHIN-deadline iteration (covers the lo-word `get_lo <= deadline_lo`
# arm 0x0d3a) before firing. 4.8GHz was too fast (get_time jumped past the 100ms deadline before the
# first check). Sweep slower speedups so an early iteration is within-deadline yet the trace stays
# bounded (~deadline/polling = 1000 iters; lower freq = fewer instructions per udelay spin).
VARIANTS = {
    'to_240M': [CLEAR_ISR, 'sysbus.timer2 Frequency 240000000'],
    'to_96M':  [CLEAR_ISR, 'sysbus.timer2 Frequency 96000000'],
    'success': ['sysbus.dma1 ForceAllTcif true'],   # TCIF set -> loop-exit -> EC_SUCCESS
}


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    executed, edges = set(), set()
    out = os.path.join(TMP, "dmawait_edges.pkl")
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    for base in (0x08000000, 0x08010000):
        for vname, vpost in VARIANTS.items():
            for ch in (0, 4, 5):              # a few valid DMA channels (rx/tx SPI use 4/5)
                trace = os.path.join(TMP, "dmawait.txt")
                if os.path.exists(trace):
                    os.remove(trace)
                s = fcall.Session(CAPTURED, boot="1.5", post_mon=vpost, trace=trace)
                try:
                    r = s.rsp.call(base + OFF, (ch, 0, 0, 0), timeout_continue=20)
                    print("  %08x ch=%d %-8s -> r0=0x%x" % (base + OFF, ch, vname, r & 0xFFFFFFFF))
                except Exception as e:
                    print("  %08x ch=%d %-8s -> EXC %s" % (base + OFF, ch, vname, str(e)[:24]))
                finally:
                    s.close()
                    fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/dmawait_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
