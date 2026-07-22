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
    """A puck missing one of the 7 expected wifi interfaces must fail loud."""
    from galeflash.livecollect import check_wifi_complete
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    check_wifi_complete("puck12", macs)  # complete — no raise
    incomplete = dict(macs)
    del incomplete["mesh-5g"]
    with pytest.raises(ValueError, match="mesh-5g"):
        check_wifi_complete("puck12", incomplete)
