#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Collect live data from gale pucks into the fleet inventory.

Per reachable puck (registry: wisp's dnsmasq gwifi-generated/pucks.conf):
serial (VPD sysfs), hostname, lan/wan MACs, the 7 wifi BSSIDs, and the LLDP
upstream switch+port.  Merges into inventory/<serial>.json for sync_sheet.py.

Usage:
    uv run collect_puck_live.py                 # whole registry
    uv run collect_puck_live.py --puck 12       # just puck12
    uv run collect_puck_live.py --inventory DIR # override inventory dir
    uv run collect_puck_live.py --site monarto  # the monarto registry
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from galeflash.livecollect import (
    check_wifi_complete,
    bridge_mac_from_ip_link,
    ethernet_macs_from_ip_link,
    merge_live_fields,
    parse_iw_dev,
    parse_pucks_conf,
    upstream_from_lldp,
)

DEFAULT_INVENTORY = Path("/home/tim/local/gwifi/fleet-flash/inventory")

# Each site's wisp serves its own puck registry (gwifi-netboot writes it).
# Addressed by IP rather than name because this CLI also runs from hosts that
# resolve the site names differently -- same table as tools/fleet/
# deploy_presence.py and openwisp/build-templates.py.
SITES = {
    "welland": "tim@10.1.4.2",   # wisp.welland.mithis.com
    "monarto": "tim@10.2.4.2",   # wisp.monarto.mithis.com
}
REGISTRY_PATH = "/etc/dnsmasq.d/gwifi-generated/pucks.conf"

# Generous timeouts: a puck on a lossy mesh-backhaul management path (40%
# loss observed on puck07, 2026-07-22) needs TCP retransmit time — a 30s
# ceiling misclassified it as offline.  Offline pucks still fail fast
# ("no route to host" returns in seconds).
SSH_OPTS = ["-4", "-o", "ConnectTimeout=30",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=8",
            "-o", "StrictHostKeyChecking=accept-new"]

# One ssh round-trip per puck: emit every section with markers.  The pucks
# are cross-site (~250 ms RTT) — batching matters.  `set -e` makes any
# failing remote command abort the chain with a non-zero (non-255) rc, so a
# reachable puck with e.g. a broken lldpcli is a HARD error, never mistaken
# for an offline puck.
_MARKER = "@@SECTION@@"
_PUCK_SCRIPT = (
    f"set -e; "
    f"echo {_MARKER}serial;   cat /sys/firmware/vpd/ro/serial_number; echo;"
    f"echo {_MARKER}hostname; uname -n;"
    f"echo {_MARKER}iplink;   ip -j link;"
    f"echo {_MARKER}iwdev;    iw dev;"
    f"echo {_MARKER}lldp;     lldpcli -f json0 show neighbors ports lan"
)


class SshTransportError(RuntimeError):
    """ssh could not reach the host (rc 255) — the host may just be offline."""


def ssh(host: str, command: str, timeout: int = 180) -> str:
    """Run a command over ssh; raise (with stderr shown) on failure.

    OpenSSH exits 255 on transport failure (unreachable, refused, auth);
    any other non-zero rc is the REMOTE command's — a different, harder
    failure that must not be classified as "offline".
    """
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, command],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)   # never suppress stderr
    if result.returncode == 255:
        raise SshTransportError(f"ssh {host} unreachable (rc=255)")
    if result.returncode != 0:
        raise RuntimeError(
            f"remote command failed on {host} (rc={result.returncode})")
    return result.stdout


def split_sections(raw: str) -> dict[str, str]:
    """Split marker-delimited ssh output into {section_name: content}."""
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith(_MARKER):
            if current is not None:
                sections[current] = "\n".join(lines)
            current = line[len(_MARKER):].strip()
            lines = []
        else:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines)
    expected = {"serial", "hostname", "iplink", "iwdev", "lldp"}
    missing = expected - set(sections)
    if missing:
        raise ValueError(f"ssh output missing section(s): {sorted(missing)}")
    return sections


def collect_one(reg, inventory_dir: Path) -> str:
    """Collect one puck; returns the serial.  Raises on any inconsistency."""
    raw = ssh(f"root@{reg.ip}", _PUCK_SCRIPT)
    s = split_sections(raw)

    serial = s["serial"].strip()
    hostname = s["hostname"].strip()
    if not serial:
        raise ValueError(f"{reg.name}: empty VPD serial_number")
    if hostname != reg.name:
        raise ValueError(
            f"{reg.name}: device hostname {hostname!r} != registry name")

    lan_mac, wan_mac = ethernet_macs_from_ip_link(json.loads(s["iplink"]))
    if (lan_mac.lower(), wan_mac.lower()) != (reg.lan_mac, reg.wan_mac):
        # A config apply can clobber the DSA user ports' netdev MACs with a
        # locally-administered address; br0 keeps the VPD wan MAC (see
        # bridge_mac_from_ip_link) — identity falls back to it.
        conduit = bridge_mac_from_ip_link(json.loads(s["iplink"])).lower()
        if conduit != reg.wan_mac:
            raise ValueError(
                f"{reg.name}: live MACs lan={lan_mac} wan={wan_mac} "
                f"(br0={conduit}) do not match registry "
                f"lan={reg.lan_mac} wan={reg.wan_mac} — identity mismatch")
        print(f"  {reg.name}: lan/wan netdev MACs are config-clobbered "
              f"(lan={lan_mac} wan={wan_mac}); identity via br0={conduit}")

    wifi_macs = parse_iw_dev(s["iwdev"])
    check_wifi_complete(reg.name, wifi_macs)

    upstream = upstream_from_lldp(json.loads(s["lldp"]))
    if upstream is None:
        print(f"  {reg.name}: no managed switch visible via LLDP "
              f"(unmanaged upstream) — Upstream not recorded")

    path = merge_live_fields(inventory_dir, serial, name=hostname,
                             upstream=upstream, wifi_macs=wifi_macs)
    print(f"  {reg.name}: serial={serial} upstream={upstream!r} -> {path}")
    return serial


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect live puck data into the fleet inventory.")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY,
                        metavar="DIR")
    parser.add_argument("--puck", action="append", type=int, metavar="NN",
                        help="Collect only puckNN (repeatable).")
    parser.add_argument("--site", choices=sorted(SITES), default="welland",
                        help="which deployment's puck registry to collect "
                             "(default: welland)")
    args = parser.parse_args()

    registry_host = SITES[args.site]
    print(f"site: {args.site}")
    print(f"Fetching registry from {registry_host}:{REGISTRY_PATH}")
    regs = parse_pucks_conf(ssh(registry_host, f"sudo -n cat {REGISTRY_PATH}"))
    if args.puck:
        wanted = {f"puck{n:02d}" for n in args.puck}
        unknown = wanted - set(regs)
        if unknown:
            sys.exit(f"ERROR: not in registry: {', '.join(sorted(unknown))}")
        regs = {k: v for k, v in regs.items() if k in wanted}
    print(f"Registry: {len(regs)} puck(s): {', '.join(sorted(regs))}")

    collected: list[str] = []
    unreachable: list[str] = []
    for name in sorted(regs):
        reg = regs[name]
        print(f"Collecting {name} ({reg.ip}) …", flush=True)
        try:
            collected.append(collect_one(reg, args.inventory))
        except (subprocess.TimeoutExpired, SshTransportError) as exc:
            # Transport-level failure only = puck offline; report, keep going.
            print(f"  {name}: UNREACHABLE ({exc})", file=sys.stderr)
            unreachable.append(name)
        # RuntimeError (remote command failed on a REACHABLE puck) and
        # ValueError (bad/incomplete data) propagate: hard failures, not
        # gaps to skip.

    print(f"\nCollected {len(collected)} puck(s): {', '.join(collected)}")
    if unreachable:
        print(f"UNREACHABLE ({len(unreachable)}): {', '.join(unreachable)}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
