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

A brand-new puck is not in the sheet at all: the fleet rows for undeployed
units (puck16…puck22) carry a Name but no Serial, and every downstream step
joins on the **Serial** column.  ``--claim puckNN`` seeds that one cell from
the live VPD, which is what binds this physical unit to that fleet name; run
it before flashing, or the pipeline's sheet sync silently writes nothing.

Usage:
    uv run identify_puck.py                       # identify only
    uv run identify_puck.py --claim puck16        # dry run: show the write
    uv run identify_puck.py --claim puck16 --write

Exit codes:
    0  matched, not yet flashed  -> ready to flash
    2  matched, already flashed  -> re-flash needs --rekeyed-ok
    3  not found in the sheet    -> unknown / blank puck (or a claim dry run)
    4  matched but MAC mismatch  -> investigate before flashing
    5  --claim refused           -> the named row cannot safely take this serial
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_sheet
from galeflash import fleetmatch, serialguard

# Must span the WHOLE schema.  This was A1:Z1000 while the sheet already
# reached column AH, so 'Flash Status' (AD) was outside the fetched header:
# match_puck's status lookup returned "" for every puck and identify_puck
# reported an already-flashed unit as READY TO FLASH (verified 2026-08-12 on
# puck07, flashed+boot-verified).  Matches sync_sheet.py's own range.
SHEET_RANGE = "A1:ZZ1000"


def _fetch(token: str, title: str) -> tuple[list[str], list[list[str]]]:
    """Return (header, data_rows) for the target tab."""
    all_rows = sync_sheet._sheets_get(token, f"'{title}'!{SHEET_RANGE}")
    if not all_rows:
        raise SystemExit("ERROR: sheet appears empty.")
    return all_rows[0], all_rows[1:]


def _claim(token: str, title: str, header: list[str], rows: list[list[str]],
           serial: str, name: str, write: bool) -> int | None:
    """Seed the Serial cell of the row called *name*.

    Returns None when the caller should carry on to the normal match (the row
    is now, or already was, bound to this serial); otherwise an exit code.
    """
    c = fleetmatch.find_claimable_row(serial, name, header, rows)

    if c["already"]:
        print(f"\n  = {c['reason']}")
        return None

    if not c["claimable"]:
        print(f"\n  ✗ CLAIM REFUSED — {c['reason']}", file=sys.stderr)
        return 5

    cell = sync_sheet._a1(title, c["row_number"] - 2, c["serial_col"])
    print(f"\n  → CLAIM {name} = {serial}")
    print(f"    write {serial!r} to {cell}  (row {c['row_number']}, "
          f"column {sync_sheet._col_letter(c['serial_col'])} 'Serial')")

    if not write:
        print("\n  DRY RUN — nothing written.  Re-run with --write to apply.")
        return 3

    sync_sheet._sheets_batch_update(token, [{"range": cell, "values": [[serial]]}])

    # Read the cell back rather than trusting the API's updatedCells count:
    # this is an identity binding, and everything downstream keys off it.
    got = sync_sheet._sheets_get(token, cell)
    written = got[0][0] if got and got[0] else ""
    if written != serial:
        print(f"\n  ✗ WRITE NOT CONFIRMED — {cell} reads {written!r}, "
              f"expected {serial!r}", file=sys.stderr)
        return 5
    print(f"    ✓ confirmed: {cell} now reads {written!r}")
    return None


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--claim", metavar="NAME",
        help="Bind the live puck's serial to the sheet row named NAME "
             "(e.g. puck16).  Only fills a BLANK Serial cell; never "
             "overwrites one, and refuses if the serial is listed elsewhere.")
    p.add_argument(
        "--write", action="store_true",
        help="Apply the --claim write (default: dry run, read-only).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.write and not args.claim:
        print("ERROR: --write only applies to --claim.", file=sys.stderr)
        return 1

    print("Reading live puck identity (non-destructive VPD read)...", flush=True)
    live = serialguard.read_live_identity()
    print(f"  live serial : {live.get('serial_number')!r}")
    print(f"  live eth0   : {live.get('ethernet_mac0')!r}")
    print(f"  live eth1   : {live.get('ethernet_mac1')!r}")

    token = sync_sheet.sheet_auth()
    title, _rows, _cols = sync_sheet._sheet_props(token)
    header, rows = _fetch(token, title)
    print(f"\nSheet: {title!r} ({len(rows)} rows, {len(header)} columns)")

    if args.claim:
        serial = (live.get("serial_number") or "").strip()
        if not serial:
            print("ERROR: live puck reports no serial_number — cannot claim.",
                  file=sys.stderr)
            return 1
        rc = _claim(token, title, header, rows, serial, args.claim, args.write)
        if rc is not None:
            return rc
        # Re-read so the match below sees the cell we just seeded.
        header, rows = _fetch(token, title)

    m = fleetmatch.match_puck(live, header, rows)

    if not m["matched"]:
        print(f"\n  ✗ NOT IN SHEET — serial {m['serial']!r} is not a listed puck.")
        for n in m["notes"]:
            print(f"    - {n}")
        print("    This may be a new/blank device.  If it is one of the "
              "undeployed fleet rows, bind it with:")
        print("      uv run identify_puck.py --claim puckNN --write")
        return 3

    print(f"\n  ✓ MATCH — {m['serial']} is sheet row {m['row_number']}.")
    status = (m["flash_status"] or "(blank — not yet flashed)"
              if m["flash_status_known"] else "(UNKNOWN — no such column)")
    print(f"    flash status : {status}")
    mac_note = {True: "ok", False: "MISMATCH",
                None: "n/a (sheet cells are blank)"}[m["mac_ok"]]
    if not m["mac_columns_known"]:
        mac_note = "UNAVAILABLE (no wan/lan columns in the header)"
    print(f"    MAC check    : {mac_note}")
    for n in m["notes"]:
        print(f"    - {n}")

    if m["mac_ok"] is False:
        print("\n  ✗ MAC MISMATCH — do NOT flash until this is understood.")
        return 4

    if not m["flash_status_known"]:
        # Never let an unreadable status pass as "not yet flashed".
        print("\n  ✗ CANNOT CONFIRM FLASH STATE — refusing to call this ready.")
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
