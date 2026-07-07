# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.fleetmatch — match a live puck against the fleet sheet."""
import pytest

from galeflash.fleetmatch import match_puck

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
