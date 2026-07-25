#!/usr/bin/env python3
"""SUPERSEDED / NET-0 — kept for the record. 0x08001770 is i2c_init(VOID) with i2c_init_port INLINED
(verified: rebuilt ELF has no separate i2c_init_port symbol); it iterates the const i2c_ports[] in flash,
so passing a port arg here is ignored -> this lever re-runs the boot config and adds nothing. gale's
i2c_ports[] is a SINGLE entry {"slave", I2C_PORT_SLAVE, 100kbps} (board.c:221, flash @0x0800bd2c), so the
`switch (p->kbps)` 1000/400/default arms + the `port==STM32_I2C1_PORT`-false arm are CONFIG-DEAD for the
gale build: reachable only by patching the const i2c_ports[].kbps/.port in flash (writemem to the modeled
flash) then calling i2c_init, or by a dead-code proof. TODO: fold into a future config-patch lever.
Accumulates tmp/i2cinit_edges.pkl.  Usage: uv run --python .venv python cov_i2cinit.py
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
TMP = os.path.join(HERE, "tmp")
PORTBUF = 0x20002c00
OFF = 0x1770              # i2c_init_port within each bank


def port_struct(port, kbps):
    # struct i2c_port_t: name@0 port@4 kbps@8 scl@12 sda@16
    return struct.pack("<IiiII", 0, port, kbps, 0, 0)


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
    out = os.path.join(TMP, "i2cinit_edges.pkl")
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass
    trace = os.path.join(TMP, "i2cinit.txt")
    if os.path.exists(trace):
        os.remove(trace)

    s = fcall.Session(CAPTURED, boot="1.5", trace=trace)
    try:
        for base in (0x08000000, 0x08010000):
            for port in (0, 1):
                for kbps in (1000, 400, 100, 333):     # 333 -> default (unknown speed) arm
                    s.rsp.writemem(PORTBUF, port_struct(port, kbps))
                    try:
                        r = s.rsp.call(base + OFF, (PORTBUF,), timeout_continue=8)
                        print("  %08x port=%d kbps=%4d -> r0=0x%x" % (base + OFF, port, kbps, r & 0xFFFFFFFF))
                    except Exception as e:
                        print("  %08x port=%d kbps=%4d -> (no-return) %s" % (base + OFF, port, kbps, type(e).__name__))
    finally:
        s.close()
        fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/i2cinit_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
