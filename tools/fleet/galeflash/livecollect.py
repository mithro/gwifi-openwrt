# SPDX-License-Identifier: Apache-2.0
"""Pure parsing + merge logic for the live puck collector.

No I/O beyond the inventory-file merge — collect_puck_live.py does ssh I/O
and calls these.  Fail loud: unexpected shapes raise, nothing is fabricated
or skipped.
"""

import json
import re
from pathlib import Path
from typing import NamedTuple

# The 6 AP interfaces every production gale puck runs (the openwisp-managed
# simple profile added wl-iot-5g, first seen live 2026-07-25 on puck03).
# A live puck missing one of these is an error, not a gap to skip.
REQUIRED_WIFI_IFACES: frozenset[str] = frozenset({
    "wl-main-2g4", "wl-main-5g",
    "wl-guest-2g4", "wl-guest-5g",
    "wl-iot-2g4", "wl-iot-5g",
})
# Mesh is preserved-but-detached fleet-wide (simple profile): whether the
# mesh interfaces exist depends on image vintage and reboot state (puck07
# lost them on its 2026-07-25 reboot; puck03 has them).  Present = record,
# absent = fine.
OPTIONAL_WIFI_IFACES: frozenset[str] = frozenset({"mesh-2g4", "mesh-5g"})


class PuckReg(NamedTuple):
    """One row of the wisp dnsmasq puck registry."""
    name:    str
    wan_mac: str
    lan_mac: str
    ip:      str


_DHCP_HOST_RE = re.compile(
    r"^dhcp-host=([0-9a-f:]{17}),([0-9a-f:]{17}),([0-9.]+),(puck\d+)\s*$"
)


def parse_pucks_conf(text: str) -> dict[str, PuckReg]:
    """Parse wisp's gwifi-generated/pucks.conf into {puck_name: PuckReg}.

    Lines are ``dhcp-host=<wan_mac>,<lan_mac>,<ip>,<puckNN>``.  Any
    non-comment, non-blank line that isn't a well-formed dhcp-host line
    raises — the registry is machine-generated, drift means trouble.
    """
    regs: dict[str, PuckReg] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _DHCP_HOST_RE.match(line)
        if not m:
            raise ValueError(f"unparseable pucks.conf line: {line!r}")
        wan_mac, lan_mac, ip, name = m.groups()
        if name in regs:
            raise ValueError(f"duplicate registry entry for {name}")
        regs[name] = PuckReg(name=name, wan_mac=wan_mac,
                             lan_mac=lan_mac, ip=ip)
    if not regs:
        raise ValueError("pucks.conf contained no dhcp-host entries")
    return regs


def parse_iw_dev(text: str) -> dict[str, str]:
    """Parse ``iw dev`` output into {interface_name: mac}.

    Only Interface/addr pairs are extracted; an addr with no preceding
    Interface raises.
    """
    macs: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Interface "):
            current = line.split(None, 1)[1]
        elif line.startswith("addr "):
            if current is None:
                raise ValueError(f"addr line with no Interface: {line!r}")
            macs[current] = line.split(None, 1)[1]
            current = None
    if not macs:
        raise ValueError("iw dev output contained no interfaces")
    return macs


def check_wifi_complete(puck: str, macs: dict[str, str]) -> None:
    """Raise if a required AP interface is missing or an unknown one appears."""
    missing = REQUIRED_WIFI_IFACES - set(macs)
    if missing:
        raise ValueError(
            f"{puck}: missing wifi interface(s): {', '.join(sorted(missing))}"
        )
    unexpected = set(macs) - REQUIRED_WIFI_IFACES - OPTIONAL_WIFI_IFACES
    if unexpected:
        raise ValueError(
            f"{puck}: unexpected wifi interface(s): {', '.join(sorted(unexpected))}"
        )


def ethernet_macs_from_ip_link(doc: list[dict]) -> tuple[str, str]:
    """Return (lan_mac, wan_mac) from an ``ip -j link`` document."""
    by_name = {i["ifname"]: i for i in doc}
    try:
        return by_name["lan"]["address"], by_name["wan"]["address"]
    except KeyError as exc:
        raise ValueError(f"ip -j link missing interface: {exc}") from exc


def bridge_mac_from_ip_link(doc: list[dict]) -> str:
    """Return br0's MAC from an ``ip -j link`` document.

    br0 carries the VPD wan MAC even when the DSA user ports' netdev MACs
    have been clobbered with a locally-administered address by a config
    apply (observed 2026-07-25: rebooted puck07 reported the same
    4a:4b:fd:... on both lan and wan).  The DSA conduit eth0 is NOT usable
    for this — its MAC is random per boot — so br0 is the stable fallback
    identity anchor.
    """
    by_name = {i["ifname"]: i for i in doc}
    try:
        return by_name["br0"]["address"]
    except KeyError as exc:
        raise ValueError(f"ip -j link missing interface: {exc}") from exc


def upstream_from_lldp(doc: dict) -> str | None:
    """Extract 'shortname port <id>' from lldpcli -f json0 output.

    A neighbor qualifies as the upstream switch iff its port id type is
    ``local`` (managed-switch behaviour; dumb-switch peers advertise
    ``mac``-type port ids) AND it advertises a chassis name.  Returns None
    when no neighbor qualifies (puck behind an unmanaged switch); raises if
    MORE than one qualifies (ambiguous topology).

    Switches advertise their *management* hostname (``manage-<name>``);
    the sheet records the switch by its plain name, so the prefix is
    stripped (house style, per the user's manual edits of 2026-07-25/26).
    """
    interfaces = doc.get("lldp", [{}])[0].get("interface", [])
    candidates: list[str] = []
    for iface in interfaces:
        for chassis in iface.get("chassis", []):
            names = [n.get("value") for n in chassis.get("name", [])
                     if n.get("value")]
            if not names:
                continue
            for port in iface.get("port", []):
                for pid in port.get("id", []):
                    if pid.get("type") == "local" and pid.get("value"):
                        short = names[0].split(".")[0]
                        short = short.removeprefix("manage-")
                        candidates.append(f"{short} port {pid['value']}")
    if len(candidates) > 1:
        raise ValueError(f"multiple upstream switch candidates: {candidates}")
    return candidates[0] if candidates else None


def merge_live_fields(
    inventory_dir: Path,
    serial: str,
    *,
    name: str,
    upstream: str | None,
    wifi_macs: dict[str, str],
) -> Path:
    """Merge live-collected fields into inventory/<serial>.json.

    Creates a minimal record for never-flashed pucks.  Flash fields are never
    touched.  ``upstream=None`` (no managed switch visible) leaves any
    existing recorded upstream in place — absence of LLDP is not evidence of
    recabling.  Returns the path written.
    """
    path = Path(inventory_dir) / f"{serial}.json"
    if path.exists():
        data = json.loads(path.read_text())
        if data.get("serial_number") != serial:
            raise ValueError(
                f"{path}: serial_number {data.get('serial_number')!r} "
                f"!= filename serial {serial!r}"
            )
    else:
        data = {"serial_number": serial}
    data["name"] = name
    if upstream is not None:
        data["upstream"] = upstream
    if wifi_macs:
        merged = dict(wifi_macs)
        for k, v in (data.get("wifi_macs") or {}).items():
            # Mesh is preserved-but-detached: a collect from a puck whose
            # reboot dropped the mesh ifaces must not erase the recorded
            # mesh BSSIDs (absence is not evidence, same as upstream=None).
            if k in OPTIONAL_WIFI_IFACES and k not in merged:
                merged[k] = v
        data["wifi_macs"] = dict(sorted(merged.items()))
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path
