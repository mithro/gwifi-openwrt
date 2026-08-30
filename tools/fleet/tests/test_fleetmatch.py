# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.fleetmatch — match a live puck against the fleet sheet."""
import pytest

from galeflash.fleetmatch import find_claimable_row, match_puck

# Header mirrors the real 'Google WiFi Pucks' tab (subset, real order/casing).
_HEADER = ["Flags", "Model", "OS", "Serial", "MAC", "Name", "PSK",
           "eth0", "eth1", "wlan0", "wlan1", "MLB Serial", "Region", "HWID",
           "RO Firmware", "RW Firmware", "Depthcharge", "EC Firmware",
           "Flash Date", "Flash Status"]

def _row(serial, eth0="", eth1="", status=""):
    r = [""] * len(_HEADER)
    r[3] = serial
    r[7] = eth0
    r[8] = eth1
    r[19] = status
    return r


_ROWS = [
    _row("2712HW0072Z", "24:05:88:36:E2:F4", "24:05:88:36:E2:F5",
         "flashed+boot-verified"),
    _row("1605HW000GM", "AA:BB:CC:DD:EE:00", "AA:BB:CC:DD:EE:01", ""),
]


def test_matches_by_serial_and_reports_row_and_status():
    live = {"serial_number": "1605HW000GM",
            "ethernet_mac0": "AABBCCDDEE00", "ethernet_mac1": "AABBCCDDEE01"}
    r = match_puck(live, _HEADER, _ROWS)
    assert r["matched"] is True
    assert r["serial"] == "1605HW000GM"
    assert r["row_number"] == 3          # header=row1, data idx1 -> sheet row 3
    assert r["flash_status"] == ""       # not yet flashed
    assert r["mac_ok"] is True


def test_already_flashed_status_surfaced():
    live = {"serial_number": "2712HW0072Z",
            "ethernet_mac0": "24058836E2F4", "ethernet_mac1": "24058836E2F5"}
    r = match_puck(live, _HEADER, _ROWS)
    assert r["matched"] is True
    assert r["row_number"] == 2
    assert r["flash_status"] == "flashed+boot-verified"
    assert r["mac_ok"] is True


def test_unknown_serial_is_not_matched():
    live = {"serial_number": "9999HW9999Z",
            "ethernet_mac0": "000000000000", "ethernet_mac1": "000000000001"}
    r = match_puck(live, _HEADER, _ROWS)
    assert r["matched"] is False
    assert r["row_number"] is None


def test_mac_mismatch_flagged_even_when_serial_matches():
    """Serial matches but the MACs don't — a data-integrity warning, not a match veto."""
    live = {"serial_number": "1605HW000GM",
            "ethernet_mac0": "DEADBEEF0000", "ethernet_mac1": "DEADBEEF0001"}
    r = match_puck(live, _HEADER, _ROWS)
    assert r["matched"] is True
    assert r["mac_ok"] is False
    assert any("mac" in n.lower() for n in r["notes"])


def test_mac_uncheckable_when_sheet_cells_empty():
    rows = [_row("5555HW5555Z", "", "", "")]
    live = {"serial_number": "5555HW5555Z",
            "ethernet_mac0": "112233445566", "ethernet_mac1": "112233445567"}
    r = match_puck(live, _HEADER, rows)
    assert r["matched"] is True
    assert r["mac_ok"] is None


# ---------------------------------------------------------------------------
# find_claimable_row — seed a placeholder row's Serial from the live puck
# ---------------------------------------------------------------------------
#
# The sheet is pre-populated with named-but-serial-less rows (puck16..puck22
# on 2026-08-12).  sync_sheet.compute_updates matches records to rows BY
# SERIAL, so until a placeholder's Serial cell is seeded every write for that
# puck lands in `unmatched` and is silently dropped.  These tests pin the
# gate that decides whether seeding a given row is safe.

def _named(name, serial=""):
    r = [""] * len(_HEADER)
    r[3] = serial
    r[5] = name
    return r


def test_blank_placeholder_row_is_claimable():
    rows = [_named("puck15", "3719HW004FU"), _named("puck16")]
    r = find_claimable_row("3108HT0023N", "puck16", _HEADER, rows)
    assert r["claimable"] is True
    assert r["already"] is False
    assert r["row_number"] == 3      # header=row1, data idx1 -> sheet row 3
    assert r["serial_col"] == 3      # found by NAME, not by position


def test_row_already_carrying_this_serial_needs_no_write():
    """Idempotent: re-running the claim must not be an error."""
    rows = [_named("puck16", "3108HT0023N")]
    r = find_claimable_row("3108HT0023N", "puck16", _HEADER, rows)
    assert r["claimable"] is False
    assert r["already"] is True
    assert r["row_number"] == 2


def test_row_holding_a_different_serial_is_refused():
    """Never overwrite an occupied identity cell — that row is another puck."""
    rows = [_named("puck16", "9999HW9999Z")]
    r = find_claimable_row("3108HT0023N", "puck16", _HEADER, rows)
    assert r["claimable"] is False
    assert r["already"] is False
    assert "9999HW9999Z" in r["reason"]


def test_serial_already_listed_on_another_row_is_refused():
    """Claiming would list one physical puck twice — refuse and name the row."""
    rows = [_named("puck07", "3108HT0023N"), _named("puck16")]
    r = find_claimable_row("3108HT0023N", "puck16", _HEADER, rows)
    assert r["claimable"] is False
    assert "puck07" in r["reason"]
    assert "row 2" in r["reason"]


def test_unknown_name_is_refused():
    rows = [_named("puck16")]
    r = find_claimable_row("3108HT0023N", "puck99", _HEADER, rows)
    assert r["claimable"] is False
    assert r["row_number"] is None
    assert "puck99" in r["reason"]


def test_duplicate_names_are_ambiguous_and_refused():
    rows = [_named("puck16"), _named("puck16")]
    r = find_claimable_row("3108HT0023N", "puck16", _HEADER, rows)
    assert r["claimable"] is False
    assert "ambiguous" in r["reason"].lower()


def test_name_match_ignores_case_and_surrounding_whitespace():
    rows = [_named(" PUCK16 ")]
    r = find_claimable_row("3108HT0023N", "puck16", _HEADER, rows)
    assert r["claimable"] is True
    assert r["row_number"] == 2


def test_missing_name_column_raises():
    header = [h for h in _HEADER if h != "Name"]
    with pytest.raises(ValueError, match="Name"):
        find_claimable_row("3108HT0023N", "puck16", header, [])


def test_missing_flash_status_column_is_flagged_not_silently_blank():
    """A truncated fetch must not read as 'not yet flashed'.

    identify_puck.py fetched A1:Z1000 while the sheet's schema reached AH, so
    'Flash Status' fell outside the header entirely.  _cell() returns "" for a
    -1 column index, which is indistinguishable from a genuinely blank cell —
    so puck07 (flashed+boot-verified) reported as READY TO FLASH.  Surface the
    absent column instead of guessing.
    """
    header = [h for h in _HEADER if h != "Flash Status"]
    rows = [[""] * len(header)]
    rows[0][3] = "1605HW000GM"
    live = {"serial_number": "1605HW000GM"}
    r = match_puck(live, header, rows)
    assert r["matched"] is True
    assert r["flash_status_known"] is False
    assert any("flash status" in n.lower() for n in r["notes"])


def test_flash_status_is_known_when_the_column_exists():
    live = {"serial_number": "2712HW0072Z",
            "ethernet_mac0": "24058836E2F4", "ethernet_mac1": "24058836E2F5"}
    r = match_puck(live, _HEADER, _ROWS)
    assert r["flash_status_known"] is True
    assert r["flash_status"] == "flashed+boot-verified"


# ---------------------------------------------------------------------------
# MAC columns follow the sheet's CURRENT names (wan/lan), not the legacy ones
# ---------------------------------------------------------------------------
#
# sheetmap.RENAME_HEADERS renamed eth0->wan and eth1->lan, and the live
# 'Google WiFi Pucks' tab has carried 'wan'/'lan' since 2026-07-25.
# match_puck still looked the columns up as "eth0"/"eth1", so _col() returned
# -1 for both, _cell() turned that into "", and the MAC cross-check silently
# degraded to mac_ok=None -- reported to the operator as "n/a (sheet has no
# MACs)".  Verified against the live sheet on 2026-08-30: feeding deliberately
# wrong MACs for a real flashed puck produced mac_ok=None and no notes, so
# identify_puck.py could never reach its exit-4 MISMATCH gate.

_RENAMED_HEADER = ["wan" if h == "eth0" else "lan" if h == "eth1" else h
                   for h in _HEADER]


def test_mac_check_works_against_the_renamed_wan_lan_columns():
    live = {"serial_number": "1605HW000GM",
            "ethernet_mac0": "AABBCCDDEE00", "ethernet_mac1": "AABBCCDDEE01"}
    r = match_puck(live, _RENAMED_HEADER, _ROWS)
    assert r["matched"] is True
    assert r["mac_ok"] is True
    assert r["mac_columns_known"] is True


def test_mac_mismatch_is_caught_on_the_renamed_columns():
    """The regression that mattered: a wrong puck must not read as 'n/a'."""
    live = {"serial_number": "1605HW000GM",
            "ethernet_mac0": "DEADBEEF0000", "ethernet_mac1": "DEADBEEF0001"}
    r = match_puck(live, _RENAMED_HEADER, _ROWS)
    assert r["mac_ok"] is False
    assert any("mac" in n.lower() for n in r["notes"])


def test_legacy_eth0_eth1_headers_still_work():
    """A sheet that has not been renamed yet must keep cross-checking."""
    live = {"serial_number": "1605HW000GM",
            "ethernet_mac0": "DEADBEEF0000", "ethernet_mac1": "DEADBEEF0001"}
    r = match_puck(live, _HEADER, _ROWS)
    assert r["mac_ok"] is False
    assert r["mac_columns_known"] is True


def test_absent_mac_columns_are_flagged_not_silently_uncheckable():
    """No wan/lan AND no eth0/eth1 = unreadable schema, not 'sheet has no MACs'."""
    header = [h for h in _HEADER if h not in ("eth0", "eth1")]
    rows = [[""] * len(header)]
    rows[0][3] = "1605HW000GM"
    live = {"serial_number": "1605HW000GM",
            "ethernet_mac0": "AABBCCDDEE00", "ethernet_mac1": "AABBCCDDEE01"}
    r = match_puck(live, header, rows)
    assert r["matched"] is True
    assert r["mac_columns_known"] is False
    assert r["mac_ok"] is None
    assert any("mac" in n.lower() for n in r["notes"])
