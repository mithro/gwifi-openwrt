#!/usr/bin/env python3
"""SPI/DMA TCIF-SUCCESS lever — complements cov_dmafault (which clears the DMA ISR so dma_wait TIMES OUT)
by driving the OPPOSITE direction: GaleDma ForceAllTcif makes ISR report TCIF set for all channels, so
dma_wait()'s poll loop `while ((isr&mask)!=mask)` exits IMMEDIATELY (loop-not-entered = success), and a
direct-called spi_dma_wait then proceeds past both dma_wait() calls into the SR loops. Together with
cov_dmafault this gives BOTH directions of the dma_wait poll-loop condition + the spi_dma_wait
dma-success/fail arms. Bounded (no spin under ForceAllTcif). RO + RW. Accumulates tmp/spitcif_edges.pkl.
Usage: uv run --python .venv python cov_spitcif.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
MON = ['sysbus.dma1 ForceAllTcif true']


def cases():
    out = []
    for base in (0x08000000, 0x08010000):
        for ch in (1, 2, 3, 4, 5, 6, 7):
            out.append(("dma_wait/ch%d/%x" % (ch, base), base + 0x0d00, (ch, 0, 0, 0)))
        for port in (0, 1):
            out.append(("spi_dma_wait/p%d/%x" % (port, base), base + 0x19f8, (port, 0, 0, 0)))
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
    out = os.path.join(TMP, "spitcif_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    for label, func, args in cases():
        trace = os.path.join(TMP, "spitcif.txt")
        if os.path.exists(trace):
            os.remove(trace)
        s = fcall.Session(binp, boot="1.5", mon=MON, trace=trace)
        try:
            r0 = s.rsp.call(func, args, timeout_continue=8)
            print("  %-24s -> r0=0x%x" % (label, r0 & 0xFFFFFFFF))
        except Exception as e:
            print("  %-24s -> EXC %s" % (label, str(e)[:30]))
        finally:
            s.close()
            fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/spitcif_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
