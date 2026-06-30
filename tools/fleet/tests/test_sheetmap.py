# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.sheetmap — pure column-mapping logic.

All tests use synthetic header+rows data; no live sheet access.
"""
import pytest

from galeflash.sheetmap import compute_updates, Update, Conflict, get_extended_header


# ---------------------------------------------------------------------------
# Synthetic sheet data
# ---------------------------------------------------------------------------

HEADER = ["#", "Model", "Firmware", "Serial", "MAC", "Setup Network", "Setup Code"]
# Col indices:  0     1        2          3       4           5              6

# Three data rows matching serials SER001, SER002, SER003
ROWS = [
    ["1", "AC-1304", "Google Original", "SER001", "AA:BB:CC:DD:EE:FF", "setupAAA", "codeA"],
    ["2", "AC-1304", "Google Original", "SER002", "",                  "setupBBB", "codeB"],
    ["3", "AC-1304", "Google Original", "SER003", "11:22:33:44:55:66", "setupCCC", "codeC"],
]

# Minimal valid record covering all mapped fields
_BASE_RECORD = {
    "serial_number":    "SER001",
    "mlb_serial_number": "MLB_SER001",
    "region":           "US",
    "ethernet_mac0":    "AA:BB:CC:DD:EE:FF",  # same as existing MAC col → skip
    "ethernet_mac1":    "AA:BB:CC:DD:EE:F0",
    "model_name":       "AC1304",
    "hwid":             "GALE C2I-A2A",
    "ro_frid":          "Google_Gale.9334.41.3",
    "is_stock":         True,
    # bookkeeping fields
    "backup_path":      "/backups/SER001.bin",
    "image_sha256":     "deadbeef" * 8,
    "flash_date":       "2026-06-28",
    "flash_status":     "ok",
}


# ---------------------------------------------------------------------------
# Test: empty new-column cells are filled with Updates
# ---------------------------------------------------------------------------

def test_new_columns_produce_updates_for_empty_cells():
    """Fields that map to new (not-yet-existing) columns emit Update for each row."""
    records = [dict(_BASE_RECORD, serial_number="SER002")]  # MAC col is empty for SER002
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    assert conflicts == [], f"Unexpected conflicts: {conflicts}"

    # SER002 is at rows[1]; MLB Serial is a new col (>= len(HEADER)=7)
    mlb_updates = [u for u in updates if u.value == "MLB_SER001"]
    assert len(mlb_updates) == 1
    assert mlb_updates[0].row == 1   # second data row (0-based)

    region_updates = [u for u in updates if u.value == "US"]
    assert len(region_updates) == 1
    assert region_updates[0].row == 1

    hwid_updates = [u for u in updates if u.value == "GALE C2I-A2A"]
    assert len(hwid_updates) == 1

    # All new-column cells are at col >= len(HEADER)
    new_col_threshold = len(HEADER)
    for u in updates:
        if u.row == 1:
            # For existing MAC col (col 4), the value is empty so it IS an Update
            if u.col < new_col_threshold:
                assert u.col == 4, f"Unexpected existing-col update at col {u.col}"
            # New cols must be >= threshold
            # (already guaranteed by building logic, just sanity-check no negative)
            assert u.col >= 0


# ---------------------------------------------------------------------------
# Test: already-correct cell is skipped (idempotent)
# ---------------------------------------------------------------------------

def test_matching_cell_is_skipped():
    """If the current cell value already equals the new value, no Update is emitted."""
    # SER001's MAC col (col 4) is "AA:BB:CC:DD:EE:FF" — same as ethernet_mac0
    records = [dict(_BASE_RECORD, serial_number="SER001")]
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    # No Update should target (row=0, col=4) because it already matches
    mac_col = HEADER.index("MAC")  # col 4
    skip_candidates = [u for u in updates if u.row == 0 and u.col == mac_col]
    assert skip_candidates == [], (
        f"MAC col should be skipped (already matches), got: {skip_candidates}"
    )


# ---------------------------------------------------------------------------
# Test: differing non-empty cell → Conflict, not Update
# ---------------------------------------------------------------------------

def test_differing_nonempty_cell_is_conflict():
    """A cell that is non-empty and differs from the new value becomes a Conflict."""
    # SER003's MAC col (col 4) is "11:22:33:44:55:66"; record sends a DIFFERENT mac0
    records = [dict(_BASE_RECORD, serial_number="SER003",
                    ethernet_mac0="FF:EE:DD:CC:BB:AA")]
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    mac_col = HEADER.index("MAC")  # col 4
    mac_conflicts = [c for c in conflicts if c.row == 2 and c.col == mac_col]
    assert len(mac_conflicts) == 1, f"Expected exactly one MAC conflict, got: {conflicts}"
    c = mac_conflicts[0]
    assert c.current == "11:22:33:44:55:66"
    assert c.new == "FF:EE:DD:CC:BB:AA"

    # The same cell must NOT appear in updates
    mac_updates = [u for u in updates if u.row == 2 and u.col == mac_col]
    assert mac_updates == []


# ---------------------------------------------------------------------------
# Test: serial not found → skipped (no exception)
# ---------------------------------------------------------------------------

def test_serial_not_found_is_skipped():
    """A record whose serial matches no row must be ignored, not raise."""
    records = [dict(_BASE_RECORD, serial_number="SERIAL_THAT_DOES_NOT_EXIST")]
    updates, conflicts = compute_updates(records, HEADER, ROWS)
    # No updates or conflicts — just silently skipped
    assert updates == []
    assert conflicts == []


# ---------------------------------------------------------------------------
# Test: multiple records, correct mixture of outcomes
# ---------------------------------------------------------------------------

def test_multiple_records_mixed_outcomes():
    """Multiple records produce independent updates/conflicts per row."""
    rec1 = dict(_BASE_RECORD, serial_number="SER001")  # MAC matches → skip
    rec2 = dict(_BASE_RECORD, serial_number="SER002")  # MAC empty → Update
    records = [rec1, rec2]
    updates, conflicts = compute_updates(records, HEADER, ROWS)

    mac_col = HEADER.index("MAC")
    # SER001 row=0: MAC already "AA:BB:CC:DD:EE:FF", should not be Updated
    row0_mac = [u for u in updates if u.row == 0 and u.col == mac_col]
    assert row0_mac == []

    # SER002 row=1: MAC is empty, ethernet_mac0 same value → should be Updated
    row1_mac = [u for u in updates if u.row == 1 and u.col == mac_col]
    assert len(row1_mac) == 1
    assert row1_mac[0].value == "AA:BB:CC:DD:EE:FF"


# ---------------------------------------------------------------------------
# Test: get_extended_header returns original + new headers in stable order
# ---------------------------------------------------------------------------

def test_get_extended_header_adds_new_columns():
    """get_extended_header appends new column headers in FIELD_TO_HEADER order."""
    extended = get_extended_header(HEADER)
    # Original columns preserved
    assert extended[:len(HEADER)] == HEADER
    # New columns added (all FIELD_TO_HEADER targets except "MAC" which exists)
    assert "MLB Serial" in extended
    assert "Region" in extended
    assert "MAC1" in extended
    assert "HWID" in extended
    assert "RO Firmware" in extended
    assert "Backup" in extended
    assert "Image SHA256" in extended
    assert "Flash Date" in extended
    assert "Flash Status" in extended
    # "MAC" must NOT be duplicated (already in HEADER)
    assert extended.count("MAC") == 1


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
