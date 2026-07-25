# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.vlanreach — probe-script builder and result parser."""
import pytest

from galeflash.vlanreach import VLAN_PROBES, build_remote_script, parse_results


def test_probe_set_matches_puck_bridge_vlans():
    assert [p.vid for p in VLAN_PROBES] == [4, 10, 20, 90, 99]
    modes = {p.vid: p.mode for p in VLAN_PROBES}
    assert modes == {4: "mgmt", 10: "dhcp", 20: "dhcp",
                     90: "dhcp", 99: "arp"}


def test_build_remote_script_probes_every_vlan():
    script = build_remote_script(12)
    assert "mgmt_probe 4 10.1.4.1" in script
    assert "dhcp_probe 10 10.1.10.1 21" in script
    assert "dhcp_probe 20 10.1.20.1 24" in script
    assert "dhcp_probe 90 10.1.90.1 23" in script
    # guest temp address is per-puck unique: 200 + NN
    assert "arp_probe 99 10.1.99.1 24 10.1.99.212" in script


def test_build_remote_script_guest_ip_uniquified_per_puck():
    ips = {build_remote_script(n).split("arp_probe 99 ")[1].split()[2]
           for n in (1, 7, 12)}
    assert ips == {"10.1.99.201", "10.1.99.207", "10.1.99.212"}


def test_build_remote_script_rejects_implausible_puck():
    with pytest.raises(ValueError, match="implausible"):
        build_remote_script(0)


def test_parse_results_ok_and_fail():
    out = "\n".join([
        "== vlan4 ==",
        "64 bytes from 10.1.4.1: seq=0 ttl=64 time=2.1 ms",
        "RESULT 4 OK icmp",
        "RESULT 10 OK dhcp+icmp lease=10.1.10.57",
        "udhcpc: no lease, failing",
        "RESULT 20 FAIL no-dhcp-lease",
        "RESULT 90 OK dhcp+icmp lease=10.1.90.201",
        "RESULT 99 FAIL no-arp src=10.1.99.212",
    ])
    assert parse_results(out) == {
        4:  (True,  "icmp"),
        10: (True,  "dhcp+icmp lease=10.1.10.57"),
        20: (False, "no-dhcp-lease"),
        90: (True,  "dhcp+icmp lease=10.1.90.201"),
        99: (False, "no-arp src=10.1.99.212"),
    }


def test_parse_results_duplicate_vlan_fails_loud():
    with pytest.raises(ValueError, match="duplicate"):
        parse_results("RESULT 4 OK icmp\nRESULT 4 OK icmp")


def test_parse_results_malformed_line_fails_loud():
    with pytest.raises(ValueError, match="malformed"):
        parse_results("RESULT 4 MAYBE icmp")
