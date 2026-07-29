# SPDX-License-Identifier: Apache-2.0
"""Load puck identity from gdoc2netcfg's pucks.json.

Identity is read-only here: gdoc2netcfg generates it from the 'Google WiFi
Pucks' sheet and deploys it to /etc/gwifi-netboot/pucks.json. MACs are
normalized to lowercase (dnsmasq's format).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = ("name", "number", "serial", "eth0", "eth1", "ip")


class IdentityError(Exception):
    """pucks.json is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class Puck:
    name: str
    number: int
    serial: str
    eth0: str
    eth1: str
    ip: str


def load_identity(path: Path) -> list[Puck]:
    """Load and validate pucks.json; MACs normalized lowercase."""
    try:
        text = path.read_text()
    except OSError as e:
        raise IdentityError(f"cannot read {path}: {e}") from e

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise IdentityError(f"invalid JSON in {path}: {e}") from e

    if doc.get("version") != 1:
        raise IdentityError(
            f"unsupported pucks.json version {doc.get('version')!r} "
            f"(expected 1)")

    pucks: list[Puck] = []
    seen_macs: set[str] = set()
    for entry in doc.get("pucks", []):
        for field_name in REQUIRED_FIELDS:
            if field_name not in entry:
                raise IdentityError(
                    f"puck entry missing field {field_name!r}: {entry!r}")
        puck = Puck(
            name=entry["name"],
            number=int(entry["number"]),
            serial=entry["serial"],
            eth0=entry["eth0"].lower(),
            eth1=entry["eth1"].lower(),
            ip=entry["ip"],
        )
        for mac in (puck.eth0, puck.eth1):
            if mac in seen_macs:
                raise IdentityError(f"duplicate MAC {mac} in {path}")
            seen_macs.add(mac)
        pucks.append(puck)

    return sorted(pucks, key=lambda p: p.number)
