#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["google-auth", "requests"]
# ///
# SPDX-License-Identifier: Apache-2.0
"""Identify the connected puck by matching it against the fleet spreadsheet.

Reads the live puck's VPD identity (serial + eth MACs, non-destructive) and
looks it up in the 'Google WiFi Pucks' sheet — no label reading needed.
Reports which fleet row it is, whether it has already been flashed, and the
exact flash_one_puck command to run.

Usage:
    uv run identify_puck.py

Exit codes:
    0  matched, not yet flashed  -> ready to flash
    2  matched, already flashed  -> re-flash needs --rekeyed-ok
    3  not found in the sheet    -> unknown / blank puck
    4  matched but MAC mismatch  -> investigate before flashing
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_sheet
from galeflash import fleetmatch, serialguard


def main() -> int:
    print("Reading live puck identity (non-destructive VPD read)...", flush=True)
    live = serialguard.read_live_identity()
    print(f"  live serial : {live.get('serial_number')!r}")
    print(f"  live eth0   : {live.get('ethernet_mac0')!r}")
    print(f"  live eth1   : {live.get('ethernet_mac1')!r}")

    token = sync_sheet.sheet_auth()
    title, _rows, _cols = sync_sheet._sheet_props(token)
    all_rows = sync_sheet._sheets_get(token, f"'{title}'!A1:Z1000")
    if not all_rows:
        print("ERROR: sheet appears empty.", file=sys.stderr)
        return 1
    header, rows = all_rows[0], all_rows[1:]

    m = fleetmatch.match_puck(live, header, rows)
    print(f"\nSheet: {title!r} ({len(rows)} pucks listed)")

    if not m["matched"]:
        print(f"\n  ✗ NOT IN SHEET — serial {m['serial']!r} is not a listed puck.")
        for n in m["notes"]:
            print(f"    - {n}")
        print("    This may be a new/blank device; add it to the fleet sheet "
              "before flashing.")
        return 3

    print(f"\n  ✓ MATCH — {m['serial']} is sheet row {m['row_number']}.")
    print(f"    flash status : {m['flash_status'] or '(blank — not yet flashed)'}")
    print(f"    MAC check    : "
          + {True: "ok", False: "MISMATCH", None: "n/a (sheet has no MACs)"}[m["mac_ok"]])
    for n in m["notes"]:
        print(f"    - {n}")

    if m["mac_ok"] is False:
        print("\n  ✗ MAC MISMATCH — do NOT flash until this is understood.")
        return 4

    date = "<YYYY-MM-DD>"
    if "flash" in m["flash_status"].lower():
        print(f"\n  ⚠ ALREADY FLASHED ({m['flash_status']}). To re-flash:")
        print(f"    uv run flash_one_puck.py --serial-hint {m['serial']} "
              f"--date {date} --rekeyed-ok")
        return 2

    print(f"\n  → READY TO FLASH:")
    print(f"    uv run flash_one_puck.py --serial-hint {m['serial']} --date {date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
