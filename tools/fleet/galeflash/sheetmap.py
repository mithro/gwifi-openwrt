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
    "mlb_serial_number":   "MLB Serial",
    "region":              "Region",
    "ethernet_mac0":       "wan",         # renamed from stale 'eth0' header
    "ethernet_mac1":       "lan",         # renamed from stale 'eth1' header
    "hwid":                "HWID",
    # --- firmware flashed to / running on the device ---
    "ro_frid":             "RO Firmware",   # coreboot RO version (unchanged by flash)
    "rw_fwid":             "RW Firmware",   # coreboot RW version in the flashed slots
    "depthcharge_version": "Depthcharge",   # TFTP-first netboot payload we flash
    "ec_version":          "EC Firmware",   # STM32 EC firmware on the device (live)
    # --- flash audit + off-site backup archive ---
    "flash_date":          "Flash Date",
    "flash_status":        "Flash Status",
    "backup_path":         "Backup",        # big-storage path of the pre-flash capture
    "backup_sha256":       "Backup SHA256", # sha256 of the pre-flash capture
    "image_archive":       "Image Archive", # big-storage path of the flashed image
    "image_sha256":        "Image SHA256",  # sha256 of the flashed image
    # --- live-collected data (collect_puck_live.py) ---
    "name":                "Name",         # puck hostname, existing col B
    "upstream":            "Upstream",     # LLDP switch+port, existing col D
    "wifi_wl_main_2g4":    "wl-main-2g4",  # renamed from stale 'wlan0'
    "wifi_wl_main_5g":     "wl-main-5g",   # renamed from stale 'wlan1'
    "wifi_wl_guest_2g4":   "wl-guest-2g4",
    "wifi_wl_guest_5g":    "wl-guest-5g",
    "wifi_wl_iot_2g4":     "wl-iot-2g4",
    "wifi_wl_iot_5g":      "wl-iot-5g",   # added to the simple profile 2026-07-25
    "wifi_mesh_2g4":       "mesh-2g4",
    "wifi_mesh_5g":        "mesh-5g",
}

# Note: the generic user-label "MAC" column is left untouched — it holds the
# operator's chosen MAC, not an inventory field.  The CPU-side eth0 netdev MAC
# is randomized every boot (observed 2026-07-22) and is deliberately not
# recorded.  Column positions are matched by header NAME, never by letter.

# Fields that legitimately CHANGE on every reflash.  compute_updates() may be
# told (allow_overwrite=FLASH_AUDIT_FIELDS) to replace differing non-empty
# cells for these; identity fields (serial/MLB/region/MACs/HWID) and ro_frid
# (unchanged by our RO-preserving flash) are never overwritten — a differing
# identity cell always signals a real problem, not a reflash.
FLASH_AUDIT_FIELDS: frozenset[str] = frozenset({
    "rw_fwid", "depthcharge_version", "ec_version",
    "flash_date", "flash_status",
    "backup_path", "backup_sha256", "image_archive", "image_sha256",
})

# Live-collected fields that legitimately change over time, unlocked by
# --update-live: 'upstream' changes when a puck is recabled, and the wifi
# BSSIDs are creation-order dependent — a `wifi` reload can permute a
# radio's vif MACs (observed live 2026-07-22: puck12's 5G set shuffled).
# 'name' and the VPD-derived wan/lan MACs stay identity-guarded.
LIVE_OVERWRITE_FIELDS: frozenset[str] = frozenset({
    "upstream",
    "wifi_wl_main_2g4", "wifi_wl_main_5g",
    "wifi_wl_guest_2g4", "wifi_wl_guest_5g",
    "wifi_wl_iot_2g4", "wifi_wl_iot_5g",
    "wifi_mesh_2g4", "wifi_mesh_5g",
})

# Stale sheet headers → real gale interface names.  Applied by
# compute_header_renames(); matching is case-insensitive and renames only a
# cell whose current value still equals the old name.
RENAME_HEADERS: dict[str, str] = {
    "eth0":  "wan",
    "eth1":  "lan",
    "wlan0": "wl-main-2g4",
    "wlan1": "wl-main-5g",
}


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

def compute_header_renames(
    header: list[str],
) -> tuple[list[tuple[int, str, str]], list[str]]:
    """Compute header-cell renames per RENAME_HEADERS.

    Three-way outcome per (old, new) entry, matched case-insensitively:
      - old present, new absent  → rename entry ``(col_idx, old, new)``
      - new present, old absent  → no-op (already renamed)
      - both present             → conflict (rename would duplicate a header)
      - neither present          → conflict (the sheet changed under us)

    Returns (renames, conflicts); conflicts are human-readable strings and the
    caller must refuse to write while any exist.  Data cells are never touched.
    """
    lower_to_idx = {h.lower(): i for i, h in enumerate(header)}
    renames: list[tuple[int, str, str]] = []
    conflicts: list[str] = []
    for old, new in RENAME_HEADERS.items():
        old_idx = lower_to_idx.get(old.lower())
        new_idx = lower_to_idx.get(new.lower())
        if old_idx is not None and new_idx is not None:
            conflicts.append(
                f"header has BOTH {old!r} (col {old_idx}) and {new!r} "
                f"(col {new_idx}) — rename would duplicate"
            )
        elif old_idx is not None:
            renames.append((old_idx, header[old_idx], new))
        elif new_idx is None:
            conflicts.append(
                f"header has neither {old!r} nor {new!r} — sheet layout changed"
            )
    return renames, conflicts


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
    allow_overwrite: frozenset[str] = frozenset(),
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
    allow_overwrite:
        Field names whose differing non-empty cells become Updates instead of
        Conflicts (pass FLASH_AUDIT_FIELDS when syncing a reflash — the new
        flash is newer truth for those columns).  Empty by default: every
        differing non-empty cell is a Conflict.

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
            elif current == "" or field in allow_overwrite:
                updates.append(Update(row=row_idx, col=col_idx, value=new_val))
            else:
                conflicts.append(
                    Conflict(row=row_idx, col=col_idx, current=current, new=new_val)
                )

    return updates, conflicts, unmatched
