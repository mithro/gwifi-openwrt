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


def test_bridge_mac_from_ip_link():
    from galeflash.livecollect import bridge_mac_from_ip_link
    doc = json.loads((FIXTURES / "puck12_ip_link.json").read_text())
    assert bridge_mac_from_ip_link(doc) == "44:07:0b:01:a2:21"


def test_bridge_mac_missing_br0_fails_loud():
    from galeflash.livecollect import bridge_mac_from_ip_link
    with pytest.raises(ValueError, match="br0"):
        bridge_mac_from_ip_link([{"ifname": "lan", "address": "aa:bb:cc:dd:ee:01"}])


def test_upstream_from_lldp_managed_switch():
    doc = json.loads((FIXTURES / "puck12_lldp.json").read_text())
    up = upstream_from_lldp(doc)
    assert up == "sw-netgear-gsm7252ps-s1 port 1/0/46"


def test_upstream_from_lldp_strips_manage_prefix():
    """Switches advertise their management hostname (manage-<name>); the
    sheet records the plain name (observed live: puck06 on m4300-s2)."""
    doc = json.loads((FIXTURES / "puck12_lldp.json").read_text()
                     .replace("sw-netgear-gsm7252ps-s1.welland",
                              "manage-sw-netgear-gsm7252ps-s1.welland"))
    assert upstream_from_lldp(doc) == "sw-netgear-gsm7252ps-s1 port 1/0/46"


def test_upstream_from_lldp_dumb_switch_returns_none():
    doc = json.loads((FIXTURES / "puck07_lldp_dumb_switch.json").read_text())
    assert upstream_from_lldp(doc) is None


def test_missing_wifi_interface_detected():
    """A puck missing one of the 6 required AP interfaces must fail loud."""
    from galeflash.livecollect import check_wifi_complete
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    check_wifi_complete("puck12", macs)  # complete — no raise
    incomplete = dict(macs)
    del incomplete["wl-main-5g"]
    with pytest.raises(ValueError, match="wl-main-5g"):
        check_wifi_complete("puck12", incomplete)


def test_absent_mesh_interfaces_are_fine():
    """Mesh is preserved-but-detached: a rebooted puck without mesh ifaces
    (observed live 2026-07-25: puck07) must pass."""
    from galeflash.livecollect import check_wifi_complete
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    no_mesh = {k: v for k, v in macs.items() if not k.startswith("mesh-")}
    check_wifi_complete("puck07", no_mesh)  # no raise


def test_unknown_interface_still_detected():
    from galeflash.livecollect import check_wifi_complete
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    macs = dict(macs)
    macs["wl-mystery-6g"] = "aa:bb:cc:dd:ee:ff"
    with pytest.raises(ValueError, match="wl-mystery-6g"):
        check_wifi_complete("puck12", macs)


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


def test_merge_live_fields_keeps_recorded_mesh_when_absent(tmp_path):
    """A mesh-less collect (detached mesh, post-reboot) must not erase the
    recorded mesh BSSIDs; non-mesh keys are still replaced wholesale."""
    inv = tmp_path / "SER001.json"
    inv.write_text(json.dumps({"serial_number": "SER001",
                               "wifi_macs": {"mesh-5g": "44:07:0b:01:a2:24",
                                             "wl-main-2g4": "old:mac"}}))
    merge_live_fields(tmp_path, "SER001", name="puck07", upstream=None,
                      wifi_macs={"wl-main-2g4": "44:07:0b:01:a2:28"})
    data = json.loads(inv.read_text())
    assert data["wifi_macs"]["mesh-5g"] == "44:07:0b:01:a2:24"  # kept
    assert data["wifi_macs"]["wl-main-2g4"] == "44:07:0b:01:a2:28"  # replaced


def test_merge_live_fields_none_upstream_does_not_erase(tmp_path):
    """A puck moved behind a dumb switch must not lose its recorded upstream."""
    inv = tmp_path / "SER001.json"
    inv.write_text(json.dumps({"serial_number": "SER001",
                               "upstream": "sw-old port 3"}))
    merge_live_fields(tmp_path, "SER001", name="puck07",
                      upstream=None, wifi_macs={})
    data = json.loads(inv.read_text())
    assert data["upstream"] == "sw-old port 3"


# --------------------------------------------------- collect_puck_live sites

def _load_collector():
    """collect_puck_live.py is a CLI script, not a package module."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "collect_puck_live.py"
    spec = importlib.util.spec_from_file_location("collect_puck_live", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_collector_knows_both_sites():
    """Until 2026-08-05 the registry host was hardcoded to welland, so the
    monarto pucks could never be collected and their sheet BSSID cells stayed
    blank. Same gap that was fixed in deploy_presence/set_device_vars."""
    assert set(_load_collector().SITES) == {"welland", "monarto"}


def test_each_site_registry_is_its_own_wisp():
    # a copy-paste slip here would collect monarto using welland's puck list
    sites = _load_collector().SITES
    assert sites["welland"] == "tim@10.1.4.2"
    assert sites["monarto"] == "tim@10.2.4.2"


def test_collector_has_no_module_level_registry_host():
    """Guard the regression: a reintroduced module-level REGISTRY_HOST would
    silently make --site a no-op."""
    mod = _load_collector()
    assert not hasattr(mod, "REGISTRY_HOST"), (
        "REGISTRY_HOST is back at module level; --site would be ignored")
