#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["google-auth", "requests"]
# ///
# SPDX-License-Identifier: Apache-2.0
"""Sync per-puck identity inventory into the 'Google WiFi Pucks' Google Sheet.

Auth: service-account key at $GALE_SHEETS_SA_JSON
      (default: ~/.config/gale-fleet/sheets-sa.json).
      Falls back to legacy OAuth token if the SA key is absent.

Usage:
    uv run sync_sheet.py                        # dry run — read only, print plan
    uv run sync_sheet.py --write                # apply updates to the live sheet
    uv run sync_sheet.py --inventory /path/to/  # override inventory directory
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

# Allow running directly from tools/fleet/
sys.path.insert(0, str(Path(__file__).parent))

from galeflash.sheetmap import (
    FIELD_TO_HEADER,
    FLASH_AUDIT_FIELDS,
    compute_updates,
    format_mac,
    get_extended_header,
    grid_dimensions_needed,
)

# Inventory fields whose bare-hex VPD values must be colon-formatted for the
# sheet's MAC columns (eth0/eth1) before reaching compute_updates.
MAC_FIELDS = ("ethernet_mac0", "ethernet_mac1")

# ---------------------------------------------------------------------------
# Sheet constants (same spreadsheet as gwifi_sheets.py / fill_pucks.py)
# ---------------------------------------------------------------------------

SPREADSHEET_ID = "1fFm2irzmnLb7RQNmAi4DmAm2_c61wrd5A2j3ZzdqIWE"
TARGET_GID = 210946497
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"

DEFAULT_INVENTORY = Path("/home/tim/local/gwifi/fleet-flash/inventory")
DEFAULT_SA_KEY    = Path.home() / ".config" / "gale-fleet" / "sheets-sa.json"
LEGACY_TOKEN_PATH = Path.home() / "local" / "sheets_token.json"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def sheet_auth() -> str:
    """Return a valid OAuth2 bearer token.

    Prefers service-account credentials ($GALE_SHEETS_SA_JSON or the default
    path).  Falls back to the legacy user-OAuth token file if the SA key is
    absent (read-only operations only; the legacy token may lack write scope).
    """
    import os

    sa_path = Path(os.environ.get("GALE_SHEETS_SA_JSON", str(DEFAULT_SA_KEY))).expanduser()

    if sa_path.exists():
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request

        creds = service_account.Credentials.from_service_account_file(
            str(sa_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        creds.refresh(Request())
        return creds.token

    # Legacy fallback: OAuth token file (read-only scope may not support writes)
    if LEGACY_TOKEN_PATH.exists():
        print(
            f"WARNING: SA key not found at {sa_path}; "
            f"falling back to legacy OAuth token at {LEGACY_TOKEN_PATH}",
            file=sys.stderr,
        )
        with open(LEGACY_TOKEN_PATH) as fh:
            creds_data = json.load(fh)
        resp = requests.post(
            creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            data={
                "client_id":     creds_data["client_id"],
                "client_secret": creds_data["client_secret"],
                "refresh_token": creds_data["refresh_token"],
                "grant_type":    "refresh_token",
            },
        )
        if resp.status_code != 200:
            print(f"Token refresh failed: {resp.status_code}\n{resp.text}", file=sys.stderr)
            resp.raise_for_status()
        return resp.json()["access_token"]

    sys.exit(
        f"ERROR: No auth credentials found.\n"
        f"  SA key path tried: {sa_path}\n"
        f"  Legacy token path: {LEGACY_TOKEN_PATH}\n"
        f"  Set GALE_SHEETS_SA_JSON or place the key at {DEFAULT_SA_KEY}"
    )


# ---------------------------------------------------------------------------
# Sheets helpers
# ---------------------------------------------------------------------------

def _sheets_get(token: str, range_str: str) -> list[list[str]]:
    """GET a range from the spreadsheet; returns rows (may be empty)."""
    url = f"{SHEETS_API}/{SPREADSHEET_ID}/values/{range_str}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json().get("values", [])


def _sheets_batch_update(token: str, data: list[dict]) -> dict:
    """POST a values:batchUpdate (RAW input option)."""
    url = f"{SHEETS_API}/{SPREADSHEET_ID}/values:batchUpdate"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"valueInputOption": "RAW", "data": data},
    )
    if not resp.ok:
        # Surface the Sheets API's actual error message (raise_for_status hides
        # the response body, which carries the real reason for a 400).
        print(f"Sheets batchUpdate {resp.status_code}:\n{resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def _sheet_props(token: str) -> tuple[str, int, int]:
    """Return (title, rowCount, columnCount) of the target tab (gid=TARGET_GID)."""
    resp = requests.get(
        f"{SHEETS_API}/{SPREADSHEET_ID}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "sheets.properties"},
    )
    resp.raise_for_status()
    for sheet in resp.json().get("sheets", []):
        p = sheet["properties"]
        if p["sheetId"] == TARGET_GID:
            grid = p.get("gridProperties", {})
            return p["title"], grid.get("rowCount", 0), grid.get("columnCount", 0)
    raise ValueError(f"No sheet with gid={TARGET_GID} in spreadsheet {SPREADSHEET_ID}")


def _grow_grid(token: str, need_rows: int, need_cols: int,
               have_rows: int, have_cols: int) -> None:
    """Expand the target tab's grid so a values write of up to (need_rows,
    need_cols) fits. The Sheets *values* API never auto-grows the grid — a
    write past the edge 400s ('exceeds grid limits') — so grow it first via
    the spreadsheet metadata API. No-op if the grid is already big enough."""
    new_rows = max(have_rows, need_rows)
    new_cols = max(have_cols, need_cols)
    if new_rows == have_rows and new_cols == have_cols:
        return
    print(f"Growing grid {have_rows}x{have_cols} -> {new_rows}x{new_cols} "
          f"to fit the new columns", flush=True)
    resp = requests.post(
        f"{SHEETS_API}/{SPREADSHEET_ID}:batchUpdate",
        headers={"Authorization": f"Bearer {token}"},
        json={"requests": [{
            "updateSheetProperties": {
                "properties": {
                    "sheetId": TARGET_GID,
                    "gridProperties": {"rowCount": new_rows, "columnCount": new_cols},
                },
                "fields": "gridProperties.rowCount,gridProperties.columnCount",
            }
        }]},
    )
    if not resp.ok:
        print(f"Grid grow {resp.status_code}:\n{resp.text}", file=sys.stderr)
        resp.raise_for_status()


def _col_letter(col_idx: int) -> str:
    """Convert 0-based column index to A1 column letter(s) (A, B, …, Z, AA, …)."""
    result = ""
    idx = col_idx
    while True:
        result = chr(ord("A") + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


def _a1(title: str, row_idx: int, col_idx: int) -> str:
    """Return A1 notation for a DATA cell.

    *row_idx* is the 0-based index into the data rows list (not the header).
    Sheet row 1 = header; sheet row 2 = data row 0, so the sheet row is
    ``row_idx + 2``.
    """
    return f"'{title}'!{_col_letter(col_idx)}{row_idx + 2}"


def _a1_header(title: str, col_idx: int) -> str:
    """Return A1 notation for a HEADER cell (always sheet row 1)."""
    return f"'{title}'!{_col_letter(col_idx)}1"


# ---------------------------------------------------------------------------
# Inventory loading
# ---------------------------------------------------------------------------

def load_inventory(inventory_dir: Path) -> list[dict]:
    """Return a list of inventory dicts loaded from *.json in *inventory_dir*."""
    files = sorted(inventory_dir.glob("*.json"))
    if not files:
        print(f"WARNING: No JSON files found in {inventory_dir}", file=sys.stderr)
        return []
    records = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            records.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: Skipping {f}: {exc}", file=sys.stderr)
    return records


def prepare_records(records: list[dict]) -> list[dict]:
    """Format MAC fields for sheet presentation, leaving the inventory JSON alone.

    Returns shallow copies with ``ethernet_mac0``/``ethernet_mac1`` colon-formatted
    (uppercase) so they match the sheet's eth0/eth1 column convention.  This runs
    in the CLI/record-prep layer so ``compute_updates`` stays format-agnostic.
    """
    prepared: list[dict] = []
    for rec in records:
        rec = dict(rec)
        for field in MAC_FIELDS:
            if rec.get(field):
                rec[field] = format_mac(rec[field])
        prepared.append(rec)
    return prepared


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync puck inventory JSON → Google WiFi Pucks sheet."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        metavar="DIR",
        help=f"Directory containing <serial>.json files (default: {DEFAULT_INVENTORY})",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply updates to the live sheet (default: dry run, read-only).",
    )
    parser.add_argument(
        "--update-flash",
        action="store_true",
        help="Reflash mode: overwrite differing FLASH-AUDIT cells (RW/EC/"
             "Depthcharge firmware ids, Flash Date/Status, Backup/Image "
             "paths+sha256s) instead of treating them as conflicts.  "
             "Identity columns are still conflict-guarded.",
    )
    args = parser.parse_args()

    mode = "WRITE" if args.write else "DRY-RUN"

    # --- Auth & load sheet ---------------------------------------------------
    token = sheet_auth()
    title, grid_rows, grid_cols = _sheet_props(token)
    print(f"Sheet: {title!r} (gid={TARGET_GID})  mode={mode}")

    # Read range stops at column Z (26 cols).  We're at ~19 columns today, so
    # this is fine — but FIELD_TO_HEADER must stay under 26 total columns or the
    # read/write range would truncate the rightmost new columns.  If the schema
    # ever grows past Z, widen this range (and the read-back range below) or
    # compute the last-column letter from get_extended_header(header).
    all_rows = _sheets_get(token, f"'{title}'!A1:Z1000")
    if not all_rows:
        print("ERROR: Sheet appears empty (no rows returned).", file=sys.stderr)
        sys.exit(1)

    header: list[str] = all_rows[0]
    rows:   list[list[str]] = all_rows[1:]

    # Column index of the "Serial" header — computed once, reused throughout.
    serial_col_idx = [h.lower() for h in header].index("serial")

    print(f"Loaded {len(rows)} data rows, {len(header)} header columns.")

    # --- Load inventory ------------------------------------------------------
    records = load_inventory(args.inventory)
    print(f"Loaded {len(records)} inventory record(s) from {args.inventory}")

    if not records:
        print("Nothing to sync.")
        return

    # Colon-format MAC fields for the sheet's eth0/eth1 columns (inventory JSON
    # stays bare hex; only the sheet presentation is colon-separated).
    records = prepare_records(records)

    # --- Compute updates -----------------------------------------------------
    allow = FLASH_AUDIT_FIELDS if args.update_flash else frozenset()
    if args.update_flash:
        print("Reflash mode: differing flash-audit cells will be OVERWRITTEN.")
    updates, conflicts, unmatched = compute_updates(records, header, rows,
                                                    allow_overwrite=allow)
    extended_header    = get_extended_header(header)
    new_col_start      = len(header)

    # Surface records whose serial isn't in the sheet (visible, not dropped).
    for serial in unmatched:
        print(
            f"WARNING: serial {serial!r} not found in sheet — skipped",
            file=sys.stderr,
        )

    # Identify new column headers that need to be written
    new_header_cells: list[tuple[int, str]] = []  # (col_idx, header_name)
    seen_new_cols: set[int] = set()
    for u in updates:
        if u.col >= new_col_start and u.col not in seen_new_cols:
            seen_new_cols.add(u.col)
            new_header_cells.append((u.col, extended_header[u.col]))

    # --- Report conflicts ----------------------------------------------------
    if conflicts:
        print(f"\n{'='*60}")
        print(f"CONFLICTS ({len(conflicts)}) — will NOT write until resolved:")
        print(f"{'='*60}")
        for c in conflicts:
            col_name = extended_header[c.col] if c.col < len(extended_header) else f"col{c.col}"
            row_data = rows[c.row]
            serial = row_data[serial_col_idx] if serial_col_idx < len(row_data) else "?"
            print(
                f"  Row {c.row+2} serial={serial!r} col={col_name!r}: "
                f"current={c.current!r}  would-write={c.new!r}"
            )
        print()

    # --- Report planned updates ----------------------------------------------
    print(f"\nPlanned updates: {len(updates)} cell(s)")
    if updates:
        for u in sorted(updates, key=lambda x: (x.row, x.col)):
            col_name = extended_header[u.col] if u.col < len(extended_header) else f"col{u.col}"
            row_data = rows[u.row]
            serial = row_data[serial_col_idx] if serial_col_idx < len(row_data) else "?"
            cell_ref = _a1(title, u.row, u.col)
            print(f"  {cell_ref}  [{col_name}]  serial={serial!r}  <- {u.value!r}")

    if new_header_cells:
        print(f"\nNew column headers to write: {len(new_header_cells)}")
        for col_idx, col_name in sorted(new_header_cells):
            cell_ref = _a1_header(title, col_idx)
            print(f"  {cell_ref}  <- {col_name!r}")

    # --- Exit if conflicts ---------------------------------------------------
    if conflicts:
        print("\nAborting: resolve conflicts before writing.", file=sys.stderr)
        sys.exit(2)

    if not args.write:
        print(f"\nDry run complete ({len(updates)} update(s) pending). Re-run with --write to apply.")
        return

    # new_header_cells is derived from updates, so "no updates" ⇒ nothing to write.
    if not updates:
        print("\nNothing to write — sheet is already up to date.")
        return

    # --- Apply updates -------------------------------------------------------
    batch: list[dict] = []

    # New column headers first
    for col_idx, col_name in new_header_cells:
        batch.append({
            "range":  _a1_header(title, col_idx),
            "values": [[col_name]],
        })

    # Data cell updates
    for u in updates:
        batch.append({
            "range":  _a1(title, u.row, u.col),
            "values": [[u.value]],
        })

    # Grow the grid first if any target cell is past the current edge (new
    # identity columns can extend beyond the sheet's existing width).
    need_rows, need_cols = grid_dimensions_needed(
        updates, [col_idx for col_idx, _ in new_header_cells])
    _grow_grid(token, need_rows, need_cols, grid_rows, grid_cols)

    result = _sheets_batch_update(token, batch)
    total_cells = result.get("totalUpdatedCells", "?")
    print(f"\nWrote {len(batch)} range(s); totalUpdatedCells={total_cells}")

    # --- Verify by reading back ----------------------------------------------
    print("\n=== Verification (read-back) ===")
    affected_rows = sorted({u.row for u in updates})
    back = _sheets_get(token, f"'{title}'!A1:Z1000")  # Z-column assumption: see read note above
    for row_idx in affected_rows:
        sheet_row = row_idx + 2  # 1-based; header is row 1
        if sheet_row - 1 < len(back):
            row_data = back[sheet_row - 1]
            serial = row_data[serial_col_idx] if serial_col_idx < len(row_data) else "?"
            print(f"  Row {sheet_row} serial={serial!r}: {row_data}")


if __name__ == "__main__":
    main()
