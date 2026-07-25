# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.livecollect — pure parsing/merge logic on live fixtures."""
import json
from pathlib import Path

import pytest

from galeflash.livecollect import (
    PuckReg,
    ethernet_macs_from_ip_link,
    parse_iw_dev,
    parse_pucks_conf,
    upstream_from_lldp,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pucks_conf():
    regs = parse_pucks_conf((FIXTURES / "pucks.conf").read_text())
    assert regs["puck12"] == PuckReg(
        name="puck12", wan_mac="44:07:0b:01:a2:21",
        lan_mac="44:07:0b:01:a2:22", ip="10.1.4.112")
    assert len(regs) == 9  # puck04..puck12
    assert set(regs) == {f"puck{n:02d}" for n in range(4, 13)}


def test_parse_iw_dev():
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    assert macs == {
        "mesh-5g":      "44:07:0b:01:a2:24",
        "wl-main-5g":   "42:07:0b:01:a2:24",
        "wl-guest-5g":  "46:07:0b:01:a2:24",
        "wl-iot-2g4":   "42:07:0b:01:a2:28",
        "wl-iot-5g":    "4e:07:0b:01:a2:24",
        "mesh-2g4":     "4e:07:0b:01:a2:28",
        "wl-guest-2g4": "46:07:0b:01:a2:28",
        "wl-main-2g4":  "44:07:0b:01:a2:28",
    }


def test_ethernet_macs_from_ip_link():
    doc = json.loads((FIXTURES / "puck12_ip_link.json").read_text())
    lan, wan = ethernet_macs_from_ip_link(doc)
    assert lan == "44:07:0b:01:a2:22"
    assert wan == "44:07:0b:01:a2:21"


def test_upstream_from_lldp_managed_switch():
    doc = json.loads((FIXTURES / "puck12_lldp.json").read_text())
    up = upstream_from_lldp(doc)
    assert up == "sw-netgear-gsm7252ps-s1 port 1/0/46"


def test_upstream_from_lldp_dumb_switch_returns_none():
    doc = json.loads((FIXTURES / "puck07_lldp_dumb_switch.json").read_text())
    assert upstream_from_lldp(doc) is None


def test_missing_wifi_interface_detected():
    """A puck missing one of the 8 expected wifi interfaces must fail loud."""
    from galeflash.livecollect import check_wifi_complete
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    check_wifi_complete("puck12", macs)  # complete — no raise
    incomplete = dict(macs)
    del incomplete["mesh-5g"]
    with pytest.raises(ValueError, match="mesh-5g"):
        check_wifi_complete("puck12", incomplete)


from galeflash.livecollect import merge_live_fields


def test_merge_live_fields_preserves_flash_data(tmp_path):
    inv = tmp_path / "SER001.json"
    inv.write_text(json.dumps({"serial_number": "SER001",
                               "flash_status": "ok",
                               "rw_fwid": "Google_Gale.8743.85.14"}))
    merge_live_fields(tmp_path, "SER001",
                      name="puck12",
                      upstream="sw-netgear-gsm7252ps-s1 port 1/0/46",
                      wifi_macs={"mesh-5g": "44:07:0b:01:a2:24"})
    data = json.loads(inv.read_text())
    assert data["flash_status"] == "ok"          # untouched
    assert data["rw_fwid"] == "Google_Gale.8743.85.14"
    assert data["name"] == "puck12"
    assert data["wifi_macs"]["mesh-5g"] == "44:07:0b:01:a2:24"


def test_merge_live_fields_creates_minimal_record(tmp_path):
    merge_live_fields(tmp_path, "SERNEW", name="puck11",
                      upstream=None, wifi_macs={"mesh-5g": "aa:bb:cc:dd:ee:ff"})
    data = json.loads((tmp_path / "SERNEW.json").read_text())
    assert data["serial_number"] == "SERNEW"
    assert data["name"] == "puck11"
    assert "upstream" not in data                # None → field absent


def test_merge_live_fields_none_upstream_does_not_erase(tmp_path):
    """A puck moved behind a dumb switch must not lose its recorded upstream."""
    inv = tmp_path / "SER001.json"
    inv.write_text(json.dumps({"serial_number": "SER001",
                               "upstream": "sw-old port 3"}))
    merge_live_fields(tmp_path, "SER001", name="puck07",
                      upstream=None, wifi_macs={})
    data = json.loads(inv.read_text())
    assert data["upstream"] == "sw-old port 3"
