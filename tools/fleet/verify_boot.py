#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Power-cycle a gale puck via EC reboot and verify what its firmware boots.

Runs under SYSTEM python3 (pyserial from dist-packages), like the other
hardware tools.  Classification logic lives in galeflash.bootverify.

Why EC reboot instead of `gale power on` (gale-ec/board-gale-r146/board.c):
  - `gale power/dev/rec` sets are SILENT no-ops while system_is_locked(); the
    only true ack is an "OK" line.  system_is_locked() is live: WP_L is pulled
    up by the AP's 3.3V rail, so a PARKED AP means locked and `gale power on`
    from a parked state is always refused.
  - EC `reboot` resets ENTERING_DEV/REC to OFF (GPIO_INPUT defaults) and the
    PD charger renegotiation auto-powers the AP ~1 s later.  One EC reboot is
    therefore a clean normal-mode cold boot — no console power command needed.

Serial discipline: single owner per port; every EC command is read until the
'> ' prompt returns; the capture ends on a decisive boot marker (the deadline
is only a safety bound).

Exit codes: 0 = GOOD (dev-key depthcharge/netboot), 2 = BAD (recovery /
verification failure), 3 = UNDECIDED (no decisive marker before the deadline).
"""
import argparse
import os
import sys
import threading
import time
from pathlib import Path

import serial  # python3-serial (system dist-packages)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from galeflash import bootverify  # noqa: E402

EC_BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP_BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"


def resolve(byid, fallback):
    return byid if os.path.exists(byid) else fallback


def open_port(path):
    s = serial.Serial()
    s.port = path
    s.baudrate = 115200
    s.timeout = 0.2
    s.dtr = False   # do not toggle modem lines on open
    s.rts = False
    s.open()
    return s


def ec_cmd(ec, cmd, timeout=6.0):
    """Send one command, read the complete response (prompt seen + quiet).

    Deferred cputs lines land AFTER the '> ' prompt, so ends-with-'>' alone
    would sit out the hard cap whenever one trails the response."""
    ec.reset_input_buffer()
    ec.write((cmd + "\r\n").encode())
    ec.flush()
    buf = bytearray()
    deadline = time.time() + timeout
    last_data = time.time()
    while time.time() < deadline:
        d = ec.read(256)
        if d:
            buf.extend(d)
            last_data = time.time()
        elif b">" in buf and time.time() - last_data > 0.25:
            break
    return bytes(buf).decode("latin1", "replace")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True,
                        help="Where to write the raw AP boot capture")
    parser.add_argument("--timeout", type=float, default=150.0,
                        help="Safety bound on the capture (default 150 s)")
    args = parser.parse_args(argv)

    ec_path = resolve(EC_BYID, "/dev/ttyUSB0")
    ap_path = resolve(AP_BYID, "/dev/ttyUSB1")

    ap_buf = bytearray()
    stop = False

    def drain_ap():
        """Single AP reader: open as soon as the tty re-enumerates, drain."""
        ap = None
        deadline = time.time() + 30
        while ap is None and time.time() < deadline:
            try:
                ap = open_port(resolve(AP_BYID, ap_path))
            except (OSError, serial.SerialException):
                time.sleep(0.2)
        if ap is None:
            return
        try:
            while not stop:
                d = ap.read(4096)
                if d:
                    ap_buf.extend(d)
        finally:
            ap.close()

    ec = open_port(ec_path)
    print("===== verify-boot: pre-reboot EC state =====", flush=True)
    print(ec_cmd(ec, "sysinfo"), flush=True)
    print(ec_cmd(ec, "gale"), flush=True)

    print("===== EC reboot (clears dev/rec + lock; PD auto-powers the AP) =====",
          flush=True)
    ec.write(b"reboot\r\n")
    ec.flush()
    ec.close()

    # Wait for the USB device to drop off, then start the AP reader, which
    # opens the tty the moment it re-enumerates (captures the boot from ~T0).
    deadline = time.time() + 20
    while os.path.exists(ec_path) and time.time() < deadline:
        time.sleep(0.2)
    reader = threading.Thread(target=drain_ap, daemon=True)
    reader.start()

    ec = None
    deadline = time.time() + 30
    while ec is None and time.time() < deadline:
        try:
            ec = open_port(resolve(EC_BYID, ec_path))
        except (OSError, serial.SerialException):
            time.sleep(0.3)
    if ec is None:
        raise SystemExit("EC console did not re-enumerate after reboot")
    time.sleep(2.5)   # PD renegotiation window before the state snapshot
    print("===== post-reboot EC state (expect unlocked, dev/rec OFF) =====",
          flush=True)
    print(ec_cmd(ec, "sysinfo"), flush=True)
    print(ec_cmd(ec, "gale"), flush=True)

    # Capture until a decisive marker (the deadline is a safety bound only).
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        text = bytes(ap_buf).replace(b"\x00", b"").decode("latin1", "replace")
        if bootverify.decisive(text):
            break
        time.sleep(0.5)
    time.sleep(5)     # collect a little context after the first marker
    stop = True
    time.sleep(0.5)

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_bytes(bytes(ap_buf))
    text = bytes(ap_buf).replace(b"\x00", b"").decode("latin1", "replace")
    result = bootverify.classify(text)

    print(f"\n===== verify-boot: verdict {result['verdict']} =====")
    print(f"  capture    : {len(ap_buf)} bytes -> {args.log}")
    print(f"  dev_signed : {result['dev_signed']}")
    print(f"  slot       : {result['slot']}")
    print(f"  good       : {result['good']}")
    print(f"  bad        : {result['bad']}")
    print(ec_cmd(ec, "gale"), flush=True)
    ec.close()

    return {"GOOD": 0, "BAD": 2, "UNDECIDED": 3}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
