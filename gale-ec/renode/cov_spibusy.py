#!/usr/bin/env python3
"""SPI-BUSY-TIMEOUT lever — covers spi_dma_wait's FIFO/BSY busy-wait TIMEOUT arms (spi_master.c:173/187,
captured 0x08001a40/46/96/98 + RW mirrors) that no prior approach could reach: the stock spi2 ignores
SR-busy writes, and a real 800ms spin blows up the execution trace. Solution (genuine emulation build):
  - GaleSpi (custom STM32-SPI controller, registered AT spi2 in this dedicated session) with ForceBusy ->
    SR reports BSY|FTLVL|FRLVL so the busy-wait loop spins instead of exiting immediately;
  - GaleDma.ForceAllTcif -> dma_wait() returns success so spi_dma_wait reaches the SR loops;
  - TIM2 frequency raised 1000x -> get_time() reaches the 800ms deadline in ~1/1000 the instructions, so
    the EC_ERROR_TIMEOUT arm fires with a BOUNDED trace (no blowup). The flash read path is not exercised
    in this session, so GaleSpi need not bridge to the spiflash slave.
Validated: spi_dma_wait(0) returns 0x4 (EC_ERROR_TIMEOUT) under this setup. RO + RW.
Accumulates tmp/spibusy_edges.pkl. Usage: uv run --python .venv python cov_spibusy.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

# Swap spi2 -> GaleSpi AFTER boot (post_mon) so a non-bridging GaleSpi is absent during the firmware's
# boot-time spi2 init (which would otherwise hang boot). fcall creates the tracer BEFORE post_mon so the
# swap does not disrupt tracing. Knobs: ForceBusy (SR busy) + ForceAllTcif (dma_wait succeeds) + ~100x
# TIM2 so the 800ms SR timeout fires in a bounded (~MB) trace.
SWAP = ['sysbus Unregister sysbus.spi2',
        'machine LoadPlatformDescriptionFromString "galespi: Miscellaneous.GaleSpi @ sysbus 0x40003800"']
CLEAR_ISR = 'sysbus WriteDoubleWord 0x40020004 0x0FFFFFFF'

# Variants of the post-boot setup, each exposing different spi_dma_wait arms. GaleSpi now models the
# BSY/FTLVL phase (loop 1) and the FRLVL phase (loop 2) INDEPENDENTLY, so loop 2 can be driven with
# loop 1 already exited. dma_wait uses get_time too, so the dmafail variant also needs the fast timer.
VARIANTS = {
    # loop 1: SR busy forever + dma_wait succeeds + fast timer -> loop-1 EC_ERROR_TIMEOUT arm (low-word).
    'to_loop1': SWAP + ['sysbus.galespi ForceBusy true', 'sysbus.dma1 ForceAllTcif true',
                        'sysbus.timer2 Frequency 4800000000'],
    # both loops iterate a bounded number of times then exit (BSY/FTLVL clear -> loop1 exit; FRLVL set
    # for loop 2 then clear -> loop2 iterate+exit). Normal timer (within deadline -> timeout NOT-taken).
    'bounded': SWAP + ['sysbus.galespi BusyReads 40', 'sysbus.galespi FrlvlReads 40',
                       'sysbus.dma1 ForceAllTcif true'],
    # loop 1 exits quickly (small BusyReads) then FRLVL stays set forever -> loop-2 EC_ERROR_TIMEOUT arm.
    'to_loop2': SWAP + ['sysbus.galespi BusyReads 5', 'sysbus.galespi ForceFrlvl true',
                        'sysbus.dma1 ForceAllTcif true', 'sysbus.timer2 Frequency 4800000000'],
    # dma_wait(tx) FAILS (DMA ISR cleared, no ForceAllTcif) + fast timer so dma_wait's own 800ms deadline
    # fires in a bounded trace -> the `if (rv) return rv` tx arm (spi_master.c:167).
    'dmafail': SWAP + [CLEAR_ISR, 'sysbus.galespi ForceBusy true', 'sysbus.timer2 Frequency 4800000000'],
}



def cases():
    out = []
    for base in (0x08000000, 0x08010000):
        for port in (0, 1):
            for vname, vpost in VARIANTS.items():
                out.append(("spi_dma_wait/p%d/%s/%x" % (port, vname, base),
                            base + 0x19f8, (port, 0, 0, 0), vpost))
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
    out = os.path.join(TMP, "spibusy_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    for label, func, args, vpost in cases():
        trace = os.path.join(TMP, "spibusy.txt")
        if os.path.exists(trace):
            os.remove(trace)
        s = fcall.Session(binp, boot="1.5", post_mon=vpost, trace=trace)
        try:
            r0 = s.rsp.call(func, args, timeout_continue=20)
            print("  %-24s -> r0=0x%x" % (label, r0 & 0xFFFFFFFF))
        except Exception as e:
            print("  %-24s -> EXC %s" % (label, str(e)[:30]))
        finally:
            s.close()
            fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/spibusy_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
