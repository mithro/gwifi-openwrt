# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.sheetmap — pure column-mapping logic.

All tests use synthetic header+rows data; no live sheet access.
"""
import pytest

from galeflash.sheetmap import (
    compute_updates,
    format_mac,
    get_extended_header,
    Update,
    Conflict,
)


# ---------------------------------------------------------------------------
# Synthetic sheet data — mirrors the real 'Google WiFi Pucks' layout, which has
# purpose-built MAC columns H=eth0, I=eth1, J=wlan0, K=wlan1.
# ---------------------------------------------------------------------------

HEADER = [
    "#", "Model", "Firmware", "Serial", "MAC", "Setup Network", "Setup Code",
    "eth0", "eth1", "wlan0", "wlan1",
]
# Col indices: 0    1        2          3       4      5               6
#              7=eth0  8=eth1  9=wlan0  10=wlan1

# Three data rows matching serials SER001, SER002, SER003.
# Note: trailing empty cells are omitted (as Google Sheets does), so SER002's
# row is short — eth0/eth1/wlan0/wlan1 are all absent (treated as empty).
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
    "ethernet_mac0":     "AA:BB:CC:DD:EE:FF",  # same as existing eth0 col → skip
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

ETH0_COL = HEADER.index("eth0")  # 7
ETH1_COL = HEADER.index("eth1")  # 8
NEW_COL_THRESHOLD = len(HEADER)  # 11 — new columns start here


# ---------------------------------------------------------------------------
# Test: empty cells (new columns AND empty existing eth0/eth1) become Updates
# ---------------------------------------------------------------------------

def test_new_columns_produce_updates_for_empty_cells():
    """Fields mapping to empty cells emit an Update per matched row."""
    records = [dict(_BASE_RECORD, serial_number="SER002")]  # eth0/eth1 empty for SER002
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    assert conflicts == [], f"Unexpected conflicts: {conflicts}"

    # SER002 is at rows[1]; MLB Serial is a new col (>= NEW_COL_THRESHOLD).
    mlb_updates = [u for u in updates if u.value == "MLB_SER001"]
    assert len(mlb_updates) == 1
    assert mlb_updates[0].row == 1            # second data row (0-based)
    assert mlb_updates[0].col >= NEW_COL_THRESHOLD

    region_updates = [u for u in updates if u.value == "US"]
    assert len(region_updates) == 1
    assert region_updates[0].row == 1

    # ethernet_mac0 maps to the EXISTING eth0 column (col 7), empty here → Update.
    eth0_updates = [u for u in updates if u.row == 1 and u.col == ETH0_COL]
    assert len(eth0_updates) == 1
    assert eth0_updates[0].value == "AA:BB:CC:DD:EE:FF"

    # ethernet_mac1 maps to the EXISTING eth1 column (col 8), empty here → Update.
    eth1_updates = [u for u in updates if u.row == 1 and u.col == ETH1_COL]
    assert len(eth1_updates) == 1
    assert eth1_updates[0].value == "AA:BB:CC:DD:EE:F0"

    # Every existing-column update for this row must be one of eth0/eth1.
    for u in updates:
        if u.row == 1 and u.col < NEW_COL_THRESHOLD:
            assert u.col in (ETH0_COL, ETH1_COL), f"Unexpected existing-col update at col {u.col}"


# ---------------------------------------------------------------------------
# Test: already-correct cell is skipped (idempotent)
# ---------------------------------------------------------------------------

def test_matching_cell_is_skipped():
    """If the current cell value already equals the new value, no Update is emitted."""
    # SER001's eth0 col (col 7) is "AA:BB:CC:DD:EE:FF" — same as ethernet_mac0.
    records = [dict(_BASE_RECORD, serial_number="SER001")]
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    skip_candidates = [u for u in updates if u.row == 0 and u.col == ETH0_COL]
    assert skip_candidates == [], (
        f"eth0 col should be skipped (already matches), got: {skip_candidates}"
    )


# ---------------------------------------------------------------------------
# Test: differing non-empty cell → Conflict, not Update
# ---------------------------------------------------------------------------

def test_differing_nonempty_cell_is_conflict():
    """A cell that is non-empty and differs from the new value becomes a Conflict."""
    # SER003's eth0 col is "11:22:33:44:55:66"; record sends a DIFFERENT mac0.
    records = [dict(_BASE_RECORD, serial_number="SER003",
                    ethernet_mac0="FF:EE:DD:CC:BB:AA")]
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    eth0_conflicts = [c for c in conflicts if c.row == 2 and c.col == ETH0_COL]
    assert len(eth0_conflicts) == 1, f"Expected exactly one eth0 conflict, got: {conflicts}"
    c = eth0_conflicts[0]
    assert c.current == "11:22:33:44:55:66"
    assert c.new == "FF:EE:DD:CC:BB:AA"

    # The same cell must NOT appear in updates.
    eth0_updates = [u for u in updates if u.row == 2 and u.col == ETH0_COL]
    assert eth0_updates == []


# ---------------------------------------------------------------------------
# Test: the generic E=MAC column is never targeted by inventory fields
# ---------------------------------------------------------------------------

def test_generic_mac_column_is_not_touched():
    """The user-label E=MAC column must not be written by any inventory field."""
    mac_col = HEADER.index("MAC")  # col 4
    records = [dict(_BASE_RECORD, serial_number="SER002")]
    updates, conflicts = compute_updates(records, HEADER, ROWS)
    assert all(u.col != mac_col for u in updates)
    assert all(c.col != mac_col for c in conflicts)


# ---------------------------------------------------------------------------
# Test: serial not found → skipped (no exception)
# ---------------------------------------------------------------------------

def test_serial_not_found_is_skipped():
    """A record whose serial matches no row must be ignored, not raise."""
    records = [dict(_BASE_RECORD, serial_number="SERIAL_THAT_DOES_NOT_EXIST")]
    updates, conflicts = compute_updates(records, HEADER, ROWS)
    assert updates == []
    assert conflicts == []


# ---------------------------------------------------------------------------
# Test: multiple records, correct mixture of outcomes
# ---------------------------------------------------------------------------

def test_multiple_records_mixed_outcomes():
    """Multiple records produce independent updates/conflicts per row."""
    rec1 = dict(_BASE_RECORD, serial_number="SER001")  # eth0 matches → skip
    rec2 = dict(_BASE_RECORD, serial_number="SER002")  # eth0 empty → Update
    records = [rec1, rec2]
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    # SER001 row=0: eth0 already "AA:BB:CC:DD:EE:FF", should not be Updated.
    row0_eth0 = [u for u in updates if u.row == 0 and u.col == ETH0_COL]
    assert row0_eth0 == []

    # SER002 row=1: eth0 empty, ethernet_mac0 same value → should be Updated.
    row1_eth0 = [u for u in updates if u.row == 1 and u.col == ETH0_COL]
    assert len(row1_eth0) == 1
    assert row1_eth0[0].value == "AA:BB:CC:DD:EE:FF"


# ---------------------------------------------------------------------------
# Test: get_extended_header returns original + new headers in stable order
# ---------------------------------------------------------------------------

def test_get_extended_header_adds_new_columns():
    """get_extended_header appends new column headers in FIELD_TO_HEADER order."""
    extended = get_extended_header(HEADER)
    # Original columns preserved.
    assert extended[:len(HEADER)] == HEADER
    # New columns added (all FIELD_TO_HEADER targets except eth0/eth1 which exist).
    assert "MLB Serial" in extended
    assert "Region" in extended
    assert "HWID" in extended
    assert "RO Firmware" in extended
    assert "Backup" in extended
    assert "Image SHA256" in extended
    assert "Flash Date" in extended
    assert "Flash Status" in extended
    # eth0/eth1 are existing columns and must NOT be duplicated.
    assert extended.count("eth0") == 1
    assert extended.count("eth1") == 1
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
