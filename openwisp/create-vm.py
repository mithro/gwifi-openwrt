#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create the `wisp` OpenWISP controller VM on a site's Ten64.

welland's wisp VM was built by hand and the procedure was never captured
(openwisp/README.md admits the cloud-init step "is outside this directory").
This script is that missing step, made reproducible and checkable.

See docs/superpowers/specs/2026-08-02-wisp-monarto-design.md for the design
decisions, in particular D4 (refuse on MAC/reservation disagreement),
D5 (monarto is IPv6-direct-only) and D6 (do not pin the QEMU machine version).
"""
from __future__ import annotations

import ipaddress
import re
import subprocess
from dataclasses import dataclass


def mac_for_ipv4(addr: str) -> str:
    """Derive the locally-administered MAC that encodes an IPv4 address.

    The fleet's addressing plan embeds the address in the MAC:
    ``10.2.4.2`` -> ``02:00:0a:02:04:02``.  This makes DHCP reservations
    self-documenting, and lets a typo be caught by comparison rather than
    by a VM that mysteriously never gets its lease.
    """
    parsed = ipaddress.ip_address(addr)
    if parsed.version != 4:
        raise ValueError(f"expected an IPv4 address, got {addr!r}")
    return "02:00:" + ":".join(f"{o:02x}" for o in parsed.packed)


@dataclass(frozen=True)
class Site:
    """Everything that differs between one site's wisp VM and another's."""

    name: str
    fqdn: str
    ten64: str
    ipv4: str
    gw4: str
    ipv6: str
    gw6: str
    bridge: str = "br-wifi"
    prefix4: int = 24
    prefix6: int = 64
    # ssh options for reaching this site's ten64.  monarto MUST pin IPv6:
    # its A record is a reverse proxy on a different machine (D5).
    ssh_opts: tuple[str, ...] = ()

    @property
    def mac(self) -> str:
        return mac_for_ipv4(self.ipv4)


SITES: dict[str, Site] = {
    "welland": Site(
        name="welland",
        fqdn="wisp.welland.mithis.com",
        ten64="ten64.welland.mithis.com",
        ipv4="10.1.4.2", gw4="10.1.4.1",
        ipv6="2404:e80:a137:104::2", gw6="2404:e80:a137:104::1",
    ),
    "monarto": Site(
        name="monarto",
        fqdn="wisp.monarto.mithis.com",
        ten64="ten64.monarto.mithis.com",
        ipv4="10.2.4.2", gw4="10.2.4.1",
        ipv6="2404:e80:a137:204::2", gw6="2404:e80:a137:204::1",
        ssh_opts=("-6",),
    ),
}


RESERVATION_PATH = "/etc/dnsmasq.d/wifi/generated/wisp.conf"


class PreflightError(RuntimeError):
    """A pre-flight check failed; nothing has been changed on the target."""


@dataclass(frozen=True)
class Reservation:
    mac: str
    ipv4: str
    ipv6: str | None


def parse_reservation(text: str) -> Reservation:
    """Parse the `dhcp-host=` line out of a generated dnsmasq fragment."""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("dhcp-host="):
            continue
        fields = line[len("dhcp-host="):].split(",")
        mac = fields[0].strip().lower()
        v4 = next((f.strip() for f in fields
                   if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", f.strip())), None)
        v6 = next((f.strip()[1:-1] for f in fields
                   if f.strip().startswith("[") and f.strip().endswith("]")), None)
        if v4 is None:
            raise PreflightError(f"dhcp-host line has no IPv4: {line!r}")
        return Reservation(mac=mac, ipv4=v4, ipv6=v6)
    raise PreflightError(f"no dhcp-host line found in {RESERVATION_PATH}")


def _ssh(site: Site, *argv: str) -> str:
    """Run a command on the site's ten64 and return stdout.

    ``site.ssh_opts`` carries the IPv6 pin for monarto (D5).  stderr is
    deliberately NOT suppressed: it is captured and folded into the error.
    """
    cmd = ["ssh", *site.ssh_opts, "-o", "ConnectTimeout=15",
           "-o", "BatchMode=yes", site.ten64, *argv]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PreflightError(
            f"ssh to {site.ten64} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip()}")
    return proc.stdout


def _read_reservation(site: Site) -> str:      # pragma: no cover - network
    return _ssh(site, "sudo", "cat", RESERVATION_PATH)


def check_reservation(site: Site) -> None:
    """Refuse unless the site's live dhcp-host reservation matches the table.

    A MAC typo would otherwise produce a VM that boots, never receives its
    reservation, and fails confusingly much later.
    """
    got = parse_reservation(_read_reservation(site))
    if got.mac != site.mac:
        raise PreflightError(
            f"{site.name}: reservation MAC {got.mac} != planned {site.mac}")
    if got.ipv4 != site.ipv4:
        raise PreflightError(
            f"{site.name}: reservation IPv4 {got.ipv4} != planned {site.ipv4}")
