#!/usr/bin/env python3
"""Minimal, transparent chromiumos-EC USB console client for the gale debug EC.

Opens the EC_PD command console ONCE (resolved via stable by-id path), runs the
commands given on argv (default = a read-only state dump), prints each response.
Sends nothing destructive on its own (it just relays the commands you pass).

Usage:  ec_console.py [cmd ...]
  e.g.  ec_console.py                    # read-only: version/flashinfo/sysinfo/gpioget
        ec_console.py "gale power off"   # park the AP / grant the EC the SPI bus
"""
import os
import sys
import time

import serial  # python3-serial (system dist-packages on the Pi)

# Stable identifier for interface if00 = the EC_PD (EC command) console.
BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
port = os.path.realpath(BYID) if os.path.exists(BYID) else "/dev/ttyUSB0"

cmds = sys.argv[1:] or ["", "version", "flashinfo", "sysinfo", "gpioget"]


def run(s, c, settle=0.6, quiet_gap=0.4, hard_cap=4.0):
    """Send one command, then read until the console goes quiet (or hard_cap)."""
    s.reset_input_buffer()
    s.write((c + "\r\n").encode())
    s.flush()
    time.sleep(settle)
    data = b""
    last = time.time()
    start = time.time()
    while time.time() - start < hard_cap:
        n = s.in_waiting
        if n:
            data += s.read(n)
            last = time.time()
        elif time.time() - last > quiet_gap:
            break
        else:
            time.sleep(0.03)
    return data.decode("latin1", "replace")


print(f"# EC console port = {port}")
with serial.Serial(port, 115200, timeout=0.2) as s:
    time.sleep(0.3)
    for c in cmds:
        out = run(s, c)
        print(f"\n===== EC <- {c!r} =====")
        print(out, end="" if out.endswith("\n") else "\n")
