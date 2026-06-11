#!/usr/bin/env python3
"""I2C-SLAVE-EVENT lever — targets i2c2_event_interrupt (0x08001854, i2c-stm32f0.c) per
UNCOVERED-BY-FUNCTION.md: the bus-error arm (ARLO|BERR :287), the NACK arm (:350), the response-TX
loop (tx_pending/tx_index<tx_end :363/364, now reachable via the model's multi-TXIS script), and the
old-protocol arm (*buff < EC_COMMAND_PROTOCOL_3 :245). Uses the GaleI2c InjectBusErr / InjectNack
knobs + a sub-protocol-3 first byte. Genuine execution of the real I2C slave ISR. RO + RW.
Accumulates tmp/i2cevt_edges.pkl.
Usage: uv run --python .venv python cov_i2cevt.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


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
    trace = os.path.join(TMP, "i2cevt.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.4"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    # a valid protocol-3 HELLO (so the response-TX loop has multiple bytes to send -> tx_index<tx_end)
    hello = C._hc_packet(0x0001, 0, 3, 4, [0x44, 0x33, 0x22, 0x11])
    getver = C._hc_packet(0x0002, 0, 3, 0, [])
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "tri2" @%s PC' % trace]
    # 1) NORMAL host commands -> multi-byte response TX (tx_pending true, tx_index<tx_end loop)
    for _ in range(2):
        c += ['sysbus.i2c1 HostCmd "%s"' % hello, 'emulation RunFor "0.3"']
    c += ['sysbus.i2c1 HostCmd "%s"' % getver, 'emulation RunFor "0.3"']
    # 1b) LONG-response commands so the response-TX loop (tx_index<tx_end :363/364/356) iterates fully:
    #     GET_VERSION(0x02 ~ version strings), GET_BUILD_INFO(0x04), GET_CHIP_INFO(0x05), GET_FEATURES(0x0d)
    for cmd in (0x0002, 0x0004, 0x0005, 0x000d, 0x0016, 0x0010):
        c += ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, 0, []), 'emulation RunFor "0.3"']
    # 2) BUS ERROR (ARLO|BERR) arm
    c += ['sysbus.i2c1 InjectBusErr true', 'sysbus.i2c1 HostCmd "%s"' % hello, 'emulation RunFor "0.3"',
          'sysbus.i2c1 InjectBusErr false']
    # 3) MASTER NACK arm
    c += ['sysbus.i2c1 InjectNack true', 'sysbus.i2c1 HostCmd "%s"' % hello, 'emulation RunFor "0.3"',
          'sysbus.i2c1 InjectNack false']
    # 4) OLD-PROTOCOL (*buff < EC_COMMAND_PROTOCOL_3=0xda): raw payload starting with a low byte.
    #    A protocol-2 style command: first byte = command (e.g. 0x01) then version/data — < 0xda.
    for raw in ("0100000000", "0200000000", "00", "017f0000"):
        c += ['sysbus.i2c1 HostCmd "%s"' % raw, 'emulation RunFor "0.2"']
    # 5) combine: bus error THEN a valid command (recovery path)
    c += ['sysbus.i2c1 InjectBusErr true', 'sysbus.i2c1 HostCmd "%s"' % getver, 'emulation RunFor "0.2"',
          'sysbus.i2c1 InjectBusErr false', 'sysbus.i2c1 HostCmd "%s"' % hello, 'emulation RunFor "0.3"']

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "i2cevt.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "i2cevt_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/i2cevt_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
