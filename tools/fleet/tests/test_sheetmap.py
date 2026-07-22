# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.sheetmap — pure column-mapping logic.

All tests use synthetic header+rows data; no live sheet access.
"""
import pytest

from galeflash.sheetmap import (
    compute_updates,
    format_mac,
    get_extended_header,
    grid_dimensions_needed,
    Update,
    Conflict,
    FLASH_AUDIT_FIELDS,
)


# ---------------------------------------------------------------------------
# Synthetic sheet data — models the POST-rename schema (wan/lan/wl-main-*);
# the real 'Google WiFi Pucks' sheet is 28 columns, see REAL_HEADER below.
# Matching is always by header NAME, never by position.
# ---------------------------------------------------------------------------

HEADER = [
    "#", "Model", "Firmware", "Serial", "MAC", "Setup Network", "Setup Code",
    "wan", "lan", "wl-main-2g4", "wl-main-5g",
]
# Col indices: 0    1        2          3       4      5               6
#              7=wan  8=lan  9=wl-main-2g4  10=wl-main-5g

# Three data rows matching serials SER001, SER002, SER003.
# Note: trailing empty cells are omitted (as Google Sheets does), so SER002's
# row is short — the wan/lan/wl-main MAC cells are all absent (treated empty).
ROWS = [
    ["1", "AC-1304", "Google Original", "SER001", "AA:BB:CC:DD:EE:FF", "setupAAA", "codeA",
     "AA:BB:CC:DD:EE:FF", "", "", ""],
    ["2", "AC-1304", "Google Original", "SER002", "", "setupBBB", "codeB"],
    ["3", "AC-1304", "Google Original", "SER003", "11:22:33:44:55:66", "setupCCC", "codeC",
     "11:22:33:44:55:66", "", "", ""],
]

# Minimal valid record covering all mapped fields.  MACs are already in colon
# form here (the CLI's prepare_records does the bare-hex→colon conversion before
# compute_updates ever sees a record, so compute_updates stays format-agnostic).
_BASE_RECORD = {
    "serial_number":     "SER001",
    "mlb_serial_number": "MLB_SER001",
    "region":            "US",
    "ethernet_mac0":     "AA:BB:CC:DD:EE:FF",  # same as existing wan col → skip
    "ethernet_mac1":     "AA:BB:CC:DD:EE:F0",
    "model_name":        "AC1304",
    "hwid":              "GALE C2I-A2A",
    "ro_frid":           "Google_Gale.9334.41.3",
    "is_stock":          True,
    # bookkeeping fields
    "backup_path":       "/backups/SER001.bin",
    "image_sha256":      "deadbeef" * 8,
    "flash_date":        "2026-06-28",
    "flash_status":      "ok",
}

WAN_COL = HEADER.index("wan")  # 7 — holds ethernet_mac0
LAN_COL = HEADER.index("lan")  # 8 — holds ethernet_mac1
NEW_COL_THRESHOLD = len(HEADER)  # 11 — new columns start here


# ---------------------------------------------------------------------------
# Test: empty cells (new columns AND empty existing wan/lan) become Updates
# ---------------------------------------------------------------------------

def test_new_columns_produce_updates_for_empty_cells():
    """Fields mapping to empty cells emit an Update per matched row."""
    records = [dict(_BASE_RECORD, serial_number="SER002")]  # wan/lan empty for SER002
    updates, conflicts, unmatched = compute_updates(records, HEADER, ROWS)

    assert conflicts == [], f"Unexpected conflicts: {conflicts}"

    # SER002 is at rows[1]; MLB Serial is a new col (>= NEW_COL_THRESHOLD).
    mlb_updates = [u for u in updates if u.value == "MLB_SER001"]
    assert len(mlb_updates) == 1
    assert mlb_updates[0].row == 1            # second data row (0-based)
    assert mlb_updates[0].col >= NEW_COL_THRESHOLD

    region_updates = [u for u in updates if u.value == "US"]
    assert len(region_updates) == 1
    assert region_updates[0].row == 1

    # ethernet_mac0 maps to the EXISTING wan column (col 7), empty here → Update.
    wan_updates = [u for u in updates if u.row == 1 and u.col == WAN_COL]
    assert len(wan_updates) == 1
    assert wan_updates[0].value == "AA:BB:CC:DD:EE:FF"

    # ethernet_mac1 maps to the EXISTING lan column (col 8), empty here → Update.
    lan_updates = [u for u in updates if u.row == 1 and u.col == LAN_COL]
    assert len(lan_updates) == 1
    assert lan_updates[0].value == "AA:BB:CC:DD:EE:F0"

    # Every existing-column update for this row must be one of wan/lan.
    for u in updates:
        if u.row == 1 and u.col < NEW_COL_THRESHOLD:
            assert u.col in (WAN_COL, LAN_COL), f"Unexpected existing-col update at col {u.col}"


# ---------------------------------------------------------------------------
# Test: already-correct cell is skipped (idempotent)
# ---------------------------------------------------------------------------

def test_matching_cell_is_skipped():
    """If the current cell value already equals the new value, no Update is emitted."""
    # SER001's wan col (col 7) is "AA:BB:CC:DD:EE:FF" — same as ethernet_mac0.
    records = [dict(_BASE_RECORD, serial_number="SER001")]
    updates, conflicts, unmatched = compute_updates(records, HEADER, ROWS)

    skip_candidates = [u for u in updates if u.row == 0 and u.col == WAN_COL]
    assert skip_candidates == [], (
        f"wan col should be skipped (already matches), got: {skip_candidates}"
    )


# ---------------------------------------------------------------------------
# Test: differing non-empty cell → Conflict, not Update
# ---------------------------------------------------------------------------

def test_differing_nonempty_cell_is_conflict():
    """A cell that is non-empty and differs from the new value becomes a Conflict."""
    # SER003's wan col is "11:22:33:44:55:66"; record sends a DIFFERENT mac0.
    records = [dict(_BASE_RECORD, serial_number="SER003",
                    ethernet_mac0="FF:EE:DD:CC:BB:AA")]
    updates, conflicts, unmatched = compute_updates(records, HEADER, ROWS)

    wan_conflicts = [c for c in conflicts if c.row == 2 and c.col == WAN_COL]
    assert len(wan_conflicts) == 1, f"Expected exactly one wan conflict, got: {conflicts}"
    c = wan_conflicts[0]
    assert c.current == "11:22:33:44:55:66"
    assert c.new == "FF:EE:DD:CC:BB:AA"

    # The same cell must NOT appear in updates.
    wan_updates = [u for u in updates if u.row == 2 and u.col == WAN_COL]
    assert wan_updates == []


# ---------------------------------------------------------------------------
# Test: reflash overwrites — FLASH_AUDIT_FIELDS may replace differing cells
# when explicitly allowed; identity fields never may (2026-07-11: the pilot's
# reflash could not update its own audit columns because every differing
# non-empty cell was a hard conflict)
# ---------------------------------------------------------------------------

_REFLASH_HEADER = HEADER + ["MLB Serial", "Flash Date", "Flash Status"]
_MLB_COL = len(HEADER)
_FLASH_DATE_COL = len(HEADER) + 1
_REFLASH_ROWS = [
    ["1", "AC-1304", "Google Original", "SER001", "AA:BB:CC:DD:EE:FF",
     "setupAAA", "codeA", "AA:BB:CC:DD:EE:FF", "", "", "",
     "MLB-OLD-01", "2026-07-07", "flashed+boot-verified"],
]


def test_flash_audit_overwrite_turns_conflict_into_update():
    """With allow_overwrite=FLASH_AUDIT_FIELDS a differing Flash Date cell is
    an Update (a reflash is newer truth), not a Conflict."""
    records = [dict(_BASE_RECORD, serial_number="SER001",
                    flash_date="2026-07-11")]
    updates, conflicts, unmatched = compute_updates(
        records, _REFLASH_HEADER, _REFLASH_ROWS,
        allow_overwrite=FLASH_AUDIT_FIELDS)

    date_updates = [u for u in updates if u.col == _FLASH_DATE_COL]
    assert len(date_updates) == 1 and date_updates[0].value == "2026-07-11"
    assert [c for c in conflicts if c.col == _FLASH_DATE_COL] == []


def test_identity_field_still_conflicts_despite_overwrite_flag():
    """allow_overwrite=FLASH_AUDIT_FIELDS must NOT unlock identity columns."""
    records = [dict(_BASE_RECORD, serial_number="SER001",
                    mlb_serial_number="MLB-DIFFERENT")]
    updates, conflicts, unmatched = compute_updates(
        records, _REFLASH_HEADER, _REFLASH_ROWS,
        allow_overwrite=FLASH_AUDIT_FIELDS)

    assert [u for u in updates if u.col == _MLB_COL] == []
    mlb_conflicts = [c for c in conflicts if c.col == _MLB_COL]
    assert len(mlb_conflicts) == 1 and mlb_conflicts[0].current == "MLB-OLD-01"


def test_default_no_overwrite_keeps_flash_audit_conflicts():
    """Without the flag, a differing Flash Date is still a Conflict."""
    records = [dict(_BASE_RECORD, serial_number="SER001",
                    flash_date="2026-07-11")]
    updates, conflicts, unmatched = compute_updates(
        records, _REFLASH_HEADER, _REFLASH_ROWS)

    assert [u for u in updates if u.col == _FLASH_DATE_COL] == []
    assert len([c for c in conflicts if c.col == _FLASH_DATE_COL]) == 1


# ---------------------------------------------------------------------------
# Test: the generic E=MAC column is never targeted by inventory fields
# ---------------------------------------------------------------------------

def test_generic_mac_column_is_not_touched():
    """The user-label E=MAC column must not be written by any inventory field."""
    mac_col = HEADER.index("MAC")  # col 4
    records = [dict(_BASE_RECORD, serial_number="SER002")]
    updates, conflicts, unmatched = compute_updates(records, HEADER, ROWS)
    assert all(u.col != mac_col for u in updates)
    assert all(c.col != mac_col for c in conflicts)


# ---------------------------------------------------------------------------
# Test: serial not found → skipped (no exception)
# ---------------------------------------------------------------------------

def test_serial_not_found_is_reported_not_raised():
    """A record whose serial matches no row is skipped AND reported in unmatched."""
    records = [dict(_BASE_RECORD, serial_number="SERIAL_THAT_DOES_NOT_EXIST")]
    updates, conflicts, unmatched = compute_updates(records, HEADER, ROWS)
    assert updates == []
    assert conflicts == []
    # The unmatched serial must be surfaced so the operator can see the drop.
    assert unmatched == ["SERIAL_THAT_DOES_NOT_EXIST"]


def test_matched_records_produce_empty_unmatched_list():
    """When every record matches a row, unmatched is empty."""
    records = [dict(_BASE_RECORD, serial_number="SER001"),
               dict(_BASE_RECORD, serial_number="SER002")]
    _updates, _conflicts, unmatched = compute_updates(records, HEADER, ROWS)
    assert unmatched == []


# ---------------------------------------------------------------------------
# Test: multiple records, correct mixture of outcomes
# ---------------------------------------------------------------------------

def test_multiple_records_mixed_outcomes():
    """Multiple records produce independent updates/conflicts per row."""
    rec1 = dict(_BASE_RECORD, serial_number="SER001")  # wan col matches → skip
    rec2 = dict(_BASE_RECORD, serial_number="SER002")  # wan col empty → Update
    records = [rec1, rec2]
    updates, conflicts, unmatched = compute_updates(records, HEADER, ROWS)

    # SER001 row=0: wan col already "AA:BB:CC:DD:EE:FF", should not be Updated.
    row0_wan = [u for u in updates if u.row == 0 and u.col == WAN_COL]
    assert row0_wan == []

    # SER002 row=1: wan col empty, ethernet_mac0 same value → should be Updated.
    row1_wan = [u for u in updates if u.row == 1 and u.col == WAN_COL]
    assert len(row1_wan) == 1
    assert row1_wan[0].value == "AA:BB:CC:DD:EE:FF"


# ---------------------------------------------------------------------------
# Test: get_extended_header returns original + new headers in stable order
# ---------------------------------------------------------------------------

def test_get_extended_header_adds_new_columns():
    """get_extended_header appends new column headers in FIELD_TO_HEADER order."""
    extended = get_extended_header(HEADER)
    # Original columns preserved.
    assert extended[:len(HEADER)] == HEADER
    # New columns added (all FIELD_TO_HEADER targets except wan/lan which exist).
    assert "MLB Serial" in extended
    assert "Region" in extended
    assert "HWID" in extended
    assert "RO Firmware" in extended
    assert "Backup" in extended
    assert "Image SHA256" in extended
    assert "Flash Date" in extended
    assert "Flash Status" in extended
    # wan/lan are existing columns and must NOT be duplicated.
    assert extended.count("wan") == 1
    assert extended.count("lan") == 1
    # No phantom "MAC1" column is created.
    assert "MAC1" not in extended


# ---------------------------------------------------------------------------
# Test: format_mac normalizes bare hex → colon-separated uppercase
# ---------------------------------------------------------------------------

def test_format_mac_bare_hex():
    assert format_mac("44070B0187B4") == "44:07:0B:01:87:B4"


def test_format_mac_lowercase_bare_hex():
    assert format_mac("44070b0187b4") == "44:07:0B:01:87:B4"


def test_format_mac_is_idempotent():
    assert format_mac("44:07:0B:01:87:B4") == "44:07:0B:01:87:B4"


def test_format_mac_passthrough_non_mac():
    """Strings that aren't 12-hex-digit MACs are returned unchanged."""
    assert format_mac("not-a-mac") == "not-a-mac"
    assert format_mac("") == ""


# ---------------------------------------------------------------------------
# Test: Update and Conflict are NamedTuple-like and unpackable
# ---------------------------------------------------------------------------

def test_update_is_unpackable():
    u = Update(row=3, col=7, value="hello")
    row, col, value = u
    assert (row, col, value) == (3, 7, "hello")


def test_conflict_is_unpackable():
    c = Conflict(row=2, col=5, current="old", new="new")
    row, col, current, new = c
    assert (row, col, current, new) == (2, 5, "old", "new")


# ---------------------------------------------------------------------------
# Test: grid_dimensions_needed — the min (rowCount, columnCount) a write needs.
# Regression for the live-write 400 ("exceeds grid limits"): a values write
# past the sheet's edge fails, so the grid must be grown to at least these
# dims first.  Sheet row = data-row-index + 2 (1 header + 0-based); columnCount
# must be > the largest 0-based column index.
# ---------------------------------------------------------------------------

def test_grid_needed_column_is_max_index_plus_one():
    """A write to 0-based col 14 (spreadsheet column O) needs columnCount 15."""
    updates = [Update(row=6, col=14, value="x")]   # O8
    need_rows, need_cols = grid_dimensions_needed(updates, new_header_cols=[14])
    assert need_cols == 15


def test_grid_needed_row_is_data_index_plus_two():
    """Data row index 6 lives on spreadsheet row 8 -> needs rowCount >= 8."""
    updates = [Update(row=6, col=14, value="x")]
    need_rows, _ = grid_dimensions_needed(updates, new_header_cols=[14])
    assert need_rows == 8


def test_grid_needed_counts_new_header_only_columns():
    """A brand-new column with a header but (here) no data cell still counts."""
    updates = [Update(row=0, col=3, value="x")]
    _, need_cols = grid_dimensions_needed(updates, new_header_cols=[9])
    assert need_cols == 10


def test_grid_needed_empty_is_zero():
    assert grid_dimensions_needed([], new_header_cols=[]) == (0, 0)


# ---------------------------------------------------------------------------
# Real 28-column header (live sheet 2026-07-22) — positions matter for the
# rename tests; matching stays name-based.
# ---------------------------------------------------------------------------

from galeflash.sheetmap import (
    LIVE_OVERWRITE_FIELDS,
    compute_header_renames,
)

REAL_HEADER = [
    "#", "Name", "Location", "Upstream", "Controlled By", "Model", "Firmware",
    "Serial", "MAC", "Setup Network", "Setup Code",
    "eth0", "eth1", "wlan0", "wlan1",
    "MLB Serial", "Region", "HWID", "RO Firmware", "RW Firmware",
    "Depthcharge", "EC Firmware", "Flash Date", "Flash Status",
    "Backup", "Backup SHA256", "Image Archive", "Image SHA256",
]

RENAMED_HEADER = [
    "wan" if h == "eth0" else "lan" if h == "eth1"
    else "wl-main-2g4" if h == "wlan0" else "wl-main-5g" if h == "wlan1"
    else h
    for h in REAL_HEADER
]


def test_rename_headers_fresh_sheet():
    """All four stale headers produce rename entries at their positions."""
    renames, rename_conflicts = compute_header_renames(REAL_HEADER)
    assert rename_conflicts == []
    assert sorted(renames) == sorted([
        (11, "eth0", "wan"),
        (12, "eth1", "lan"),
        (13, "wlan0", "wl-main-2g4"),
        (14, "wlan1", "wl-main-5g"),
    ])


def test_rename_headers_already_renamed_is_noop():
    renames, rename_conflicts = compute_header_renames(RENAMED_HEADER)
    assert renames == []
    assert rename_conflicts == []


def test_rename_headers_missing_both_is_conflict():
    """Neither old nor new name present → conflict (sheet changed under us)."""
    header = [h for h in REAL_HEADER if h != "wlan1"]
    renames, rename_conflicts = compute_header_renames(header)
    assert any("wlan1" in c for c in rename_conflicts)


def test_rename_headers_both_present_is_conflict():
    """Old AND new name present → conflict (rename would create a duplicate)."""
    header = REAL_HEADER + ["wan"]
    renames, rename_conflicts = compute_header_renames(header)
    assert any("eth0" in c and "wan" in c for c in rename_conflicts)
    assert (11, "eth0", "wan") not in renames


def test_ethernet_macs_target_renamed_columns():
    """ethernet_mac0/1 land in the wan/lan columns of a post-rename header —
    no duplicate eth0/eth1 columns are appended."""
    extended = get_extended_header(RENAMED_HEADER)
    assert "eth0" not in extended
    assert "eth1" not in extended
    rows = [["1", "", "", "", "", "AC-1304", "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "ethernet_mac0": "AA:BB:CC:DD:EE:01",
                "ethernet_mac1": "AA:BB:CC:DD:EE:02"}]
    updates, conflicts, unmatched = compute_updates(records, RENAMED_HEADER, rows)
    assert conflicts == [] and unmatched == []
    by_col = {u.col: u.value for u in updates}
    assert by_col[RENAMED_HEADER.index("wan")] == "AA:BB:CC:DD:EE:01"
    assert by_col[RENAMED_HEADER.index("lan")] == "AA:BB:CC:DD:EE:02"


def test_wifi_fields_land_in_renamed_wlan_columns():
    """wl-main BSSIDs go to the renamed wlan0/wlan1 columns; the other five
    wifi columns are appended after the current right edge."""
    rows = [["1", "", "", "", "", "AC-1304", "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "wifi_wl_main_2g4": "44:07:0B:01:A2:28",
                "wifi_wl_main_5g": "42:07:0B:01:A2:24",
                "wifi_mesh_5g": "44:07:0B:01:A2:24"}]
    updates, conflicts, _ = compute_updates(records, RENAMED_HEADER, rows)
    assert conflicts == []
    by_col = {u.col: u.value for u in updates}
    assert by_col[RENAMED_HEADER.index("wl-main-2g4")] == "44:07:0B:01:A2:28"
    assert by_col[RENAMED_HEADER.index("wl-main-5g")] == "42:07:0B:01:A2:24"
    mesh_cols = [c for c in by_col if c >= len(RENAMED_HEADER)]
    assert len(mesh_cols) == 1
    ext = get_extended_header(RENAMED_HEADER)
    assert ext[mesh_cols[0]] == "mesh-5g"


def test_name_and_upstream_fields_map_to_existing_columns():
    rows = [["1", "", "", "", "", "AC-1304", "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "name": "puck12",
                "upstream": "sw-netgear-gsm7252ps-s1 port 1/0/46"}]
    updates, conflicts, _ = compute_updates(records, RENAMED_HEADER, rows)
    assert conflicts == []
    by_col = {u.col: u.value for u in updates}
    assert by_col[RENAMED_HEADER.index("Name")] == "puck12"
    assert by_col[RENAMED_HEADER.index("Upstream")].startswith("sw-netgear-gsm7252ps-s1")


def test_update_live_allows_upstream_overwrite_only():
    """LIVE_OVERWRITE_FIELDS unlocks a differing Upstream cell but not Name."""
    rows = [["1", "puck-old-name", "", "sw-old port 1", "", "AC-1304",
             "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "name": "puck12",
                "upstream": "sw-netgear-gsm7252ps-s1 port 1/0/46"}]
    updates, conflicts, _ = compute_updates(
        records, RENAMED_HEADER, rows, allow_overwrite=LIVE_OVERWRITE_FIELDS)
    up_col = RENAMED_HEADER.index("Upstream")
    name_col = RENAMED_HEADER.index("Name")
    assert any(u.col == up_col for u in updates)
    assert any(c.col == name_col for c in conflicts)
    assert not any(u.col == name_col for u in updates)


def test_extended_header_width_covers_all_new_columns():
    """len(get_extended_header()) is the column count the ranges must span."""
    ext = get_extended_header(RENAMED_HEADER)
    # 28 existing + 5 appended (guest x2, iot, mesh x2) = 33 columns (A..AG)
    assert len(ext) == 33
    assert ext[28:] == ["wl-guest-2g4", "wl-guest-5g", "wl-iot-2g4",
                        "mesh-2g4", "mesh-5g"]
