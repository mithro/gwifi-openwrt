#!/usr/bin/env python3
"""DMA-FAULT direct-call lever — covers the DMA transfer-complete TIMEOUT arms (chip/stm32/dma.c:252-254
`while ((isr&TCIF)!=TCIF) if (deadline<=get_time()) return EC_ERROR_TIMEOUT;`) and the spi_dma_wait
dma-failed early-returns (spi_master.c:167/180). Same bounded-trace technique as cov_flashfault: boot a
GDB-stub session that PRE-CLEARS the DMA interrupt-flag register via `mon=` (IFCR @0x40020004 W1C all
flags) so no channel shows TCIF, then DIRECT-CALL ONE op and trace just that call. One dma_wait timeout
is time-bounded (DMA_TRANSFER_TIMEOUT_US=100ms ~ a few-MB trace), so one-op-per-session stays bounded.
Validated: dma_wait(ch) with ISR cleared -> r0=0x4 (EC_ERROR_TIMEOUT). Captured: dma_wait@0x08000d00,
spi_dma_wait@0x080019f8 (+ RW mirrors @ +0x10000). Accumulates tmp/dmafault_edges.pkl.
Usage: uv run --python .venv python cov_dmafault.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

CLEAR_ISR = 'sysbus WriteDoubleWord 0x40020004 0x0FFFFFFF'   # DMA1 IFCR: clear all TCIF/GIF flags


def cases():
    out = []
    for base in (0x08000000, 0x08010000):
        dw = base + 0x0d00          # dma_wait(channel)
        sw = base + 0x19f8          # spi_dma_wait(port)
        for ch in (1, 2, 3, 4):
            out.append(("dma_wait/ch%d/%x" % (ch, base), dw, (ch, 0, 0, 0)))
        for port in (0, 1):
            out.append(("spi_dma_wait/p%d/%x" % (port, base), sw, (port, 0, 0, 0)))
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
    out = os.path.join(TMP, "dmafault_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    for label, func, args in cases():
        trace = os.path.join(TMP, "dmafault.txt")
        if os.path.exists(trace):
            os.remove(trace)
        s = fcall.Session(binp, boot="1.5", mon=[CLEAR_ISR], trace=trace)
        try:
            r0 = s.rsp.call(func, args, timeout_continue=12)
            print("  %-24s -> r0=0x%x" % (label, r0 & 0xFFFFFFFF))
        except Exception as e:
            print("  %-24s -> EXC %s" % (label, e))
        finally:
            s.close()
            fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/dmafault_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
