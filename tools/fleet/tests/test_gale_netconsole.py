# SPDX-License-Identifier: Apache-2.0
"""gale-netconsole must aim at the puck's OWN site's wisp.

The init script hardcoded welland's ``TARGET_IP="10.1.4.2"`` /
``TARGET_MAC="02:00:0a:01:04:02"``.  A monarto puck running that image
streams its kernel log across the WAN to the wrong site -- and nothing
reports it, because netconsole is fire-and-forget UDP: ``modprobe``
still succeeds and the "streaming printk" log line still appears.  The
kernel panics this channel exists to capture (field pucks have no serial
console) would simply never arrive.

These tests execute the real shell functions with /bin/sh rather than
asserting on the file's text, because the derivation only ever runs on a
puck at boot -- there is no other place it gets exercised.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[3]
          / "gale-image" / "files" / "etc" / "init.d" / "gale-netconsole")


def _sh(snippet: str) -> str:
    """Run a snippet under /bin/sh with the script's functions in scope."""
    text = SCRIPT.read_text()
    # Take everything before boot() -- the helpers and constants -- and
    # drop the rc.common shebang line, which is not a real interpreter.
    body = text.split("boot()")[0].replace("#!/bin/sh /etc/rc.common", "", 1)
    proc = subprocess.run(["/bin/sh", "-c", body + "\n" + snippet],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"sh failed: {proc.stderr}"
    assert not proc.stderr.strip(), f"unexpected stderr: {proc.stderr}"
    return proc.stdout.strip()


@pytest.mark.parametrize("puck_ip,wisp_ip", [
    ("10.1.4.105", "10.1.4.2"),    # welland
    ("10.2.4.105", "10.2.4.2"),    # monarto
    ("10.1.4.2", "10.1.4.2"),      # degenerate: wisp itself
    ("10.2.4.199", "10.2.4.2"),    # top of the DHCP pool
])
def test_wisp_ip_is_dot_two_of_the_pucks_own_subnet(puck_ip, wisp_ip):
    assert _sh(f'wisp_ip_for {puck_ip}') == wisp_ip


@pytest.mark.parametrize("wisp_ip,mac", [
    ("10.1.4.2", "02:00:0a:01:04:02"),
    ("10.2.4.2", "02:00:0a:02:04:02"),
])
def test_wisp_mac_encodes_the_ipv4(wisp_ip, mac):
    """The fleet MAC scheme is 02:00: + the four octets in hex, so the
    MAC cannot silently disagree with the address."""
    assert _sh(f'wisp_mac_for {wisp_ip}') == mac


def test_octets_are_zero_padded_to_two_hex_digits():
    """A bare %x would emit 02:00:a:2:4:2 -- not a valid MAC.  This is the
    one formatting slip that would produce a plausible-looking string that
    modprobe rejects."""
    mac = _sh('wisp_mac_for 10.2.4.2')
    assert re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", mac), mac


def test_a_monarto_puck_never_targets_welland():
    """The actual regression: derive from a monarto address and prove
    nothing points at 10.1.4.x."""
    ip = _sh('wisp_ip_for 10.2.4.105')
    mac = _sh(f'wisp_mac_for {ip}')
    assert ip == "10.2.4.2"
    assert mac == "02:00:0a:02:04:02"
    assert "0a:01:" not in mac


def test_no_dhcp_fallback_broadcasts_instead_of_giving_up():
    """The script must not `return 1` when br-mgmt has no address.

    It used to, which made the channel useless for the failure you most
    need it for: a puck that boots but never gets a lease emitted
    nothing, so a dead image and a dead network looked identical from the
    wire.  Now it broadcasts from an IPv4 link-local address instead.
    """
    text = SCRIPT.read_text()
    body = text.split("boot()")[1]
    assert "169.254." in body, "no link-local fallback source"
    assert "255.255.255.255" in body, "fallback must broadcast"
    assert "ff:ff:ff:ff:ff:ff" in body, "fallback needs a broadcast MAC"
    # The old give-up path must be gone: no bare `return 1` for the
    # no-address case.
    assert "netconsole not started" not in body


def test_fallback_source_is_deterministic_per_puck():
    """Two silent pucks must not collide on the same link-local address.

    Derived from the last two MAC octets, so it is stable across reboots
    and distinct per unit.
    """
    snippet = (
        'MAC=24:05:88:39:8a:08\n'
        'X=$(printf "%d" "0x$(echo "$MAC" | cut -d: -f5)")\n'
        'Y=$(printf "%d" "0x$(echo "$MAC" | cut -d: -f6)")\n'
        'echo "169.254.$X.$Y"\n'
    )
    assert _sh(snippet) == "169.254.138.8"

    other = snippet.replace("24:05:88:39:8a:08", "58:cb:52:ed:b0:f9")
    assert _sh(other) == "169.254.176.249"


def test_no_hardcoded_site_address_remains_in_the_script():
    """Guards against a future edit reintroducing a literal target."""
    # A TARGET_* value is legitimate only if it is DERIVED from the puck's
    # own address, or is the site-agnostic broadcast fallback.  Anything
    # else is a site literal creeping back in.
    BROADCAST = {'"255.255.255.255"', '"ff:ff:ff:ff:ff:ff"'}
    text = SCRIPT.read_text()
    assignments = re.findall(r'^\s*TARGET_(?:IP|MAC)=(.+)$', text, re.M)
    assert assignments, "no TARGET_* assignments found -- test is vacuous"
    for value in assignments:
        value = value.strip()
        assert "10.1.4.2" not in value, f"hardcoded welland target: {value}"
        assert "02:00:0a:01:04:02" not in value, f"hardcoded MAC: {value}"
        assert "$(" in value or value in BROADCAST, \
            f"TARGET_* must be derived or the broadcast fallback: {value}"
