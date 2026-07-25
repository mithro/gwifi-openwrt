# SPDX-License-Identifier: Apache-2.0
"""Tests for identity loading (pucks.json from gdoc2netcfg)."""

import json
from pathlib import Path

import pytest

from gwifi_netboot.identity import IdentityError, Puck, load_identity

FIXTURE = Path(__file__).parent / "fixtures" / "pucks.json"


def test_loads_fixture():
    pucks = load_identity(FIXTURE)
    assert [p.name for p in pucks] == ["puck04", "puck12"]
    assert pucks[0] == Puck(
        name="puck04", number=4, serial="2831HW00VZA",
        eth0="44:07:0b:01:87:b4", eth1="44:07:0b:01:87:b5",
        ip="10.1.4.104")


def test_macs_normalized_lowercase_for_dnsmasq():
    pucks = load_identity(FIXTURE)
    assert pucks[1].eth0 == "44:07:0b:01:a2:21"
    assert pucks[1].eth1 == "44:07:0b:01:a2:22"


def test_missing_file_raises(tmp_path):
    with pytest.raises(IdentityError, match="No such"):
        load_identity(tmp_path / "absent.json")


def test_wrong_version_raises(tmp_path):
    p = tmp_path / "pucks.json"
    p.write_text(json.dumps({"version": 2, "pucks": []}))
    with pytest.raises(IdentityError, match="version"):
        load_identity(p)


def test_duplicate_mac_raises(tmp_path):
    doc = json.loads(FIXTURE.read_text())
    doc["pucks"][1]["eth0"] = doc["pucks"][0]["eth0"]
    p = tmp_path / "pucks.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(IdentityError, match="duplicate MAC"):
        load_identity(p)


def test_missing_field_raises(tmp_path):
    doc = json.loads(FIXTURE.read_text())
    del doc["pucks"][0]["serial"]
    p = tmp_path / "pucks.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(IdentityError, match="serial"):
        load_identity(p)


def test_malformed_json_raises(tmp_path):
    p = tmp_path / "pucks.json"
    p.write_text("{nope")
    with pytest.raises(IdentityError, match="JSON"):
        load_identity(p)


def test_lookup_by_mac():
    pucks = load_identity(FIXTURE)
    by_mac = {m: p for p in pucks for m in (p.eth0, p.eth1)}
    assert by_mac["44:07:0b:01:a2:22"].name == "puck12"
