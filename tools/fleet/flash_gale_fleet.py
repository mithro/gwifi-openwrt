#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
# SPDX-License-Identifier: Apache-2.0
"""Flash a gale fleet firmware image over the SuzyQ / raiden bridge.

Safety rail: reads the live device serial number and refuses to write anything
if it does not match the expected serial supplied on the command line.  This
prevents flashing the wrong puck in a multi-device lab.

Write order (RO region written LAST):
  1. RW_SECTION_A
  2. RW_SECTION_B
  3. 0x301000:0xdf000  (GBB + RO_FRID, --allow-ro)

A partial failure leaves the device in the state written so far; writing RO
last means the puck stays stock-bootable until the very last step.

Usage:
  python3 flash_gale_fleet.py <out.bin> <expected-serial> [--chunk 0x1000]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — tools/ lives three levels above this script's package directory.
# flash_gale_fleet.py is at tools/fleet/flash_gale_fleet.py
# TOOLS is the sibling tools/ root:  tools/
# ---------------------------------------------------------------------------
TOOLS = Path(__file__).resolve().parent.parent  # tools/fleet/../ = tools/

sys.path.insert(0, str(Path(__file__).resolve().parent))  # make galeflash importable
from galeflash import flashplan, serialguard  # noqa: E402


def _run(cmd, label):  # pragma: no cover
    print(f"\n===== {label} =====", flush=True)
    print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
    t0 = time.time()
    subprocess.check_call(cmd)
    print(f"  ok ({time.time() - t0:.1f}s)")


def _park(label="re-park AP"):  # pragma: no cover
    _run(["python3", str(TOOLS / "ec_console.py"), "gale power off"], label)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path, help="Firmware image to flash (out.bin)")
    ap.add_argument("expected_serial", help="Serial number the live device must have")
    ap.add_argument("--chunk", default="0x1000",
                    help="Chunk size for raiden_write_region (default: 0x1000; "
                         "fleet can opt into 0x4000 for faster writes)")
    args = ap.parse_args(argv)

    if not args.image.exists():
        sys.exit(f"FATAL: image not found: {args.image}")

    # --- Step 1: park AP, then read the live serial number ---
    _park("park AP (initial)")
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

    # --- Step 3: flash each region in RO-last order ---
    for region, extra_flags in flashplan.regions_in_order():
        _park()
        cmd = [
            "python3",
            str(TOOLS / "raiden_write_region.py"),
            str(args.image),
            region,
            "--chunk", args.chunk,
            "--commit",
        ] + extra_flags
        _run(cmd, f"flash {region}")

    # --- Done ---
    print(
        "\n=== ALL FLASHES SUCCEEDED ===\n"
        "Device is parked.  The EC is LOCKED while parked (WP_L follows the\n"
        "AP 3.3V rail), so `gale power on` is refused.  To power on + verify:\n"
        f"  python3 {Path(__file__).resolve().parent / 'verify_boot.py'} "
        "--log <boot.log>\n"
        "(EC reboot: clears dev/rec, PD auto-powers the AP ~1 s later.)"
    )


if __name__ == "__main__":
    main()
