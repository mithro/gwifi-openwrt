#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
# SPDX-License-Identifier: Apache-2.0
"""Flash a gale fleet firmware image with the verified libusb tool.

Safety rail: reads the live device serial number and refuses to write anything
if it does not match the expected serial supplied on the command line.  This
prevents flashing the wrong puck in a multi-device lab.

The actual write is one invocation of flash_puck_usb.py `flash`, which owns:
  * RO-last region ordering (RW_SECTION_A, RW_SECTION_B, then GBB),
  * one parked + settled session per region (the 5 s post-ENABLE settle that
    sidesteps the rail-bounce event windows — see tools/EC-USB-SPI-BUG.md),
  * erase + program + byte-for-byte read-back verification,
  * fail-fast wedge canaries (any anomaly aborts loud, nothing is retried).

A partial failure leaves the device in the state written so far; writing RO
last means the puck stays stock-bootable until the very last region.

Usage:
  python3 flash_gale_fleet.py <out.bin> <expected-serial>
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — tools/ lives one level above this script's directory.
# flash_gale_fleet.py is at tools/fleet/flash_gale_fleet.py
# ---------------------------------------------------------------------------
TOOLS = Path(__file__).resolve().parent.parent  # tools/fleet/../ = tools/

sys.path.insert(0, str(Path(__file__).resolve().parent))  # make galeflash importable
from galeflash import serialguard  # noqa: E402


def _run(cmd, label):  # pragma: no cover
    print(f"\n===== {label} =====", flush=True)
    print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
    t0 = time.time()
    subprocess.check_call(cmd)
    print(f"  ok ({time.time() - t0:.1f}s)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path, help="Firmware image to flash (out.bin)")
    ap.add_argument("expected_serial", help="Serial number the live device must have")
    args = ap.parse_args(argv)

    if not args.image.exists():
        sys.exit(f"FATAL: image not found: {args.image}")

    # --- Step 1: read the live serial number (the tool parks the AP itself) ---
    live = serialguard.read_live_serial()

    # --- Step 2: serial guard — refuse to flash the wrong device ---
    if not serialguard.ok(live, args.expected_serial):
        print(
            f"\n\n"
            f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            f"SERIAL MISMATCH — ABORTING — nothing has been written\n"
            f"  live device serial : {live!r}\n"
            f"  expected serial    : {args.expected_serial!r}\n"
            f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nSerial OK: {live!r} matches {args.expected_serial!r}")

    # --- Step 3: flash all regions (RO-last) via the verified tool ---
    _run(
        [
            "python3",
            str(TOOLS / "flash_puck_usb.py"),
            "flash",
            str(args.image),
            "--commit",
            "--allow-ro",
        ],
        "flash RW_SECTION_A + RW_SECTION_B + GBB (RO-last, settled sessions)",
    )

    # --- Done ---
    print(
        "\n=== ALL FLASHES SUCCEEDED ===\n"
        "Device is parked.  The EC is LOCKED while parked (WP_L follows the\n"
        "AP 3.3V rail), so `gale power on` is refused.  To power on + verify:\n"
        f"  python3 {TOOLS / 'flash_puck_usb.py'} verify-boot --boot-log <boot.log>\n"
        "(EC reboot: clears dev/rec, PD auto-powers the AP ~1 s later.)"
    )


if __name__ == "__main__":
    main()
