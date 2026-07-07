# SPDX-License-Identifier: Apache-2.0
"""Pure column-mapping logic for syncing puck inventory dicts to a Google Sheet.

No I/O here — all functions are deterministic and testable without network access.

Usage
-----
    from galeflash.sheetmap import compute_updates, get_extended_header, Update, Conflict

    updates, conflicts, unmatched = compute_updates(records, header, rows)
"""

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Field → sheet column header mapping
# ---------------------------------------------------------------------------

# Maps inventory dict field names to the target sheet column header (display name).
# Case-insensitive matching is used when searching the existing header row.
# Fields absent from the sheet get new columns appended at the right, in this order.
FIELD_TO_HEADER: dict[str, str] = {
    "mlb_serial_number": "MLB Serial",
    "region":            "Region",
    "ethernet_mac0":     "eth0",          # existing col H — fill only if empty/matching
    "ethernet_mac1":     "eth1",          # existing col I — fill only if empty/matching
    "hwid":              "HWID",
    "ro_frid":           "RO Firmware",
    "backup_path":       "Backup",
    "image_sha256":      "Image SHA256",
    "flash_date":        "Flash Date",
    "flash_status":      "Flash Status",
}

# Note: the generic user-label "MAC" column (E) is left untouched — it is
# already populated with the operator's chosen MAC and is not an inventory
# field.  The wifi-MAC columns J=wlan0/K=wlan1 stay empty (no wifi MACs in
# inventory), so they are intentionally absent from FIELD_TO_HEADER.


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

class Update(NamedTuple):
    """A single cell write: (row, col, value).

    *row* is a 0-based index into the ``rows`` list (first data row = 0).
    *col* is a 0-based column index into the extended header
          (original columns first, then any new columns appended by this module).
    """
    row:   int
    col:   int
    value: str


class Conflict(NamedTuple):
    """A cell that is non-empty and differs from the new value — operator must resolve.

    Fields mirror Update plus the existing value.
    """
    row:     int
    col:     int
    current: str
    new:     str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_col_map(header: list[str]) -> dict[str, int]:
    """Return ``{field_name: col_index}`` for every field in FIELD_TO_HEADER.

    Existing columns are matched case-insensitively.  New columns are assigned
    indices starting at ``len(header)``, in FIELD_TO_HEADER iteration order.
    If two fields map to the same new column header they share the index.
    """
    lower_to_idx: dict[str, int] = {h.lower(): i for i, h in enumerate(header)}
    col_map: dict[str, int] = {}
    next_new: int = len(header)
    new_by_lower: dict[str, int] = {}

    for field, col_header in FIELD_TO_HEADER.items():
        key = col_header.lower()
        if key in lower_to_idx:
            col_map[field] = lower_to_idx[key]
        elif key in new_by_lower:
            col_map[field] = new_by_lower[key]
        else:
            col_map[field] = next_new
            new_by_lower[key] = next_new
            next_new += 1

    return col_map


# ---------------------------------------------------------------------------
# MAC formatting
# ---------------------------------------------------------------------------

def format_mac(value: str) -> str:
    """Format a MAC address as colon-separated uppercase hex for the sheet.

    VPD stores bare hex (``44070B0187B4``); the sheet's MAC columns use the
    colon convention (``44:07:0B:01:87:B4``).  This normalizes either form to
    colon-separated uppercase so format mismatches don't cause spurious
    conflicts/clobbers.

    It is idempotent (already-colon-formatted input round-trips) and leaves any
    string that isn't a 12-hex-digit MAC unchanged.
    """
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(hex_only) != 12:
        return value  # not a 12-hex-digit MAC — leave untouched
    hex_only = hex_only.upper()
    return ":".join(hex_only[i : i + 2] for i in range(0, 12, 2))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_extended_header(header: list[str]) -> list[str]:
    """Return *header* extended with any new column names introduced by FIELD_TO_HEADER.

    The original columns are preserved in order.  New column names are appended
    in FIELD_TO_HEADER iteration order, de-duplicated.
    """
    lower_existing = {h.lower() for h in header}
    new_cols: list[str] = []
    seen_new: set[str] = set()

    for col_header in FIELD_TO_HEADER.values():
        key = col_header.lower()
        if key not in lower_existing and key not in seen_new:
            new_cols.append(col_header)
            seen_new.add(key)

    return list(header) + new_cols


def grid_dimensions_needed(
    updates: list,
    new_header_cols: list[int],
) -> tuple[int, int]:
    """Return the minimum (rowCount, columnCount) a values write must fit inside.

    The Sheets *values* API never auto-grows the grid — a write past the sheet's
    edge 400s ("exceeds grid limits") — so the caller must grow the grid to at
    least these dimensions first.

    ``updates`` are Update(row, col, ...) where *row* is a 0-based data-row
    index (spreadsheet row = row + 2: one header row, 0-based) and *col* is a
    0-based column index.  ``new_header_cols`` are 0-based column indices of
    header cells (spreadsheet row 1).  columnCount must exceed the largest
    0-based column index; rowCount must reach the largest spreadsheet row.
    Returns (0, 0) when there is nothing to write.
    """
    cols = [u.col for u in updates] + list(new_header_cols)
    need_cols = (max(cols) + 1) if cols else 0
    need_rows = (max(u.row for u in updates) + 2) if updates else 0
    return need_rows, need_cols


def compute_updates(
    records: list[dict],
    header: list[str],
    rows: list[list[str]],
) -> tuple[list[Update], list[Conflict], list[str]]:
    """Compute per-cell writes and conflicts for a batch of inventory records.

    Parameters
    ----------
    records:
        Inventory dicts (keys: ``serial_number`` plus any FIELD_TO_HEADER keys).
    header:
        The sheet's first row (list of column header strings, zero-indexed).
    rows:
        Sheet data rows, *excluding* the header row (``rows[0]`` = sheet row 2).
        Each inner list may be shorter than ``len(header)`` if trailing cells are
        empty (Google Sheets omits them).

    Returns
    -------
    updates:
        Cells to write.  ``Update.col`` may be ``>= len(header)`` for new columns.
    conflicts:
        Non-empty cells whose current value differs from the intended new value.
        The caller should print them and exit non-zero; do not apply updates when
        conflicts are present.
    unmatched:
        Serial numbers of records that matched no sheet row (in input order).
        The caller should surface these so a puck whose serial isn't in the
        sheet is visible rather than silently dropped.
    """
    lower_to_idx: dict[str, int] = {h.lower(): i for i, h in enumerate(header)}

    # Find the "Serial" column index (required).
    serial_col = lower_to_idx.get("serial")
    if serial_col is None:
        raise ValueError("Header row has no 'Serial' column — cannot match records.")

    # Build serial → 0-based row index mapping.
    serial_to_row: dict[str, int] = {}
    for row_idx, row in enumerate(rows):
        serial = row[serial_col] if serial_col < len(row) else ""
        if serial:
            serial_to_row[serial] = row_idx

    # Build field → column index map (handles new columns too).
    col_map = _build_col_map(header)

    updates: list[Update] = []
    conflicts: list[Conflict] = []
    unmatched: list[str] = []

    for record in records:
        serial = record.get("serial_number", "")
        row_idx = serial_to_row.get(serial)
        if row_idx is None:
            # No matching row — record it so the caller can warn the operator.
            unmatched.append(serial)
            continue

        row_data = rows[row_idx]

        for field, col_idx in col_map.items():
            if field not in record:
                continue

            raw = record[field]
            if raw is None:
                continue
            new_val = str(raw)
            if not new_val:
                continue  # don't write empty strings

            current = row_data[col_idx] if col_idx < len(row_data) else ""

            if current == new_val:
                continue  # idempotent — already correct
            elif current == "":
                updates.append(Update(row=row_idx, col=col_idx, value=new_val))
            else:
                conflicts.append(
                    Conflict(row=row_idx, col=col_idx, current=current, new=new_val)
                )

    return updates, conflicts, unmatched
