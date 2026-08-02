# SPDX-License-Identifier: Apache-2.0
"""Offline tests for openwisp/create-vm.py."""
import importlib.util
import sys
from pathlib import Path

import pytest

CV_PATH = Path(__file__).resolve().parents[3] / "openwisp" / "create-vm.py"


def _load():
    """Load the hyphenated script as a module.

    ``sys.modules[spec.name] = mod`` BEFORE ``exec_module`` is required, not
    optional: a module defining a dataclass under ``from __future__ import
    annotations`` makes dataclasses resolve its string annotations via
    ``sys.modules[cls.__module__].__dict__``.  Unregistered, that lookup
    returns None and the import dies with a bare
    ``AttributeError: 'NoneType' object has no attribute '__dict__'``.
    This ordering is also what the importlib docs' own recipe uses.
    """
    spec = importlib.util.spec_from_file_location("create_vm", CV_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_mac_for_ipv4_encodes_the_address():
    cv = _load()
    assert cv.mac_for_ipv4("10.2.4.2") == "02:00:0a:02:04:02"
    assert cv.mac_for_ipv4("10.1.4.2") == "02:00:0a:01:04:02"


def test_mac_for_ipv4_rejects_non_ipv4():
    cv = _load()
    with pytest.raises(ValueError):
        cv.mac_for_ipv4("2404:e80:a137:204::2")


def test_both_sites_present():
    cv = _load()
    assert set(cv.SITES) == {"welland", "monarto"}


def test_site_macs_agree_with_their_ipv4():
    """The table cannot drift: every site's MAC must encode its own IPv4."""
    cv = _load()
    for name, site in cv.SITES.items():
        assert site.mac == cv.mac_for_ipv4(site.ipv4), name


def test_monarto_matches_the_live_reservation():
    """Pins the values ten64.monarto's dhcp-host line already commits to."""
    cv = _load()
    m = cv.SITES["monarto"]
    assert m.mac == "02:00:0a:02:04:02"
    assert m.ipv4 == "10.2.4.2"
    assert m.ipv6 == "2404:e80:a137:204::2"
    assert m.bridge == "br-wifi"
    assert m.fqdn == "wisp.monarto.mithis.com"


def test_monarto_pins_ipv6_transport():
    """D5: monarto's IPv4 is a reverse proxy on another host."""
    cv = _load()
    assert "-6" in cv.SITES["monarto"].ssh_opts
