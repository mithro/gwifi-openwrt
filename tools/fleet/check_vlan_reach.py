#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Verify each puck can reach the ten64 through every VLAN it bridges.

Per reachable puck (registry: wisp's dnsmasq gwifi-generated/pucks.conf):
  vlan  4 (mgmt):  ping 10.1.4.1 from the puck's own mgmt address
  vlan 10/20/90:   udhcpc probe on br0.<vid> (no-op script, nothing kept),
                   then ping the ten64 gateway from the leased address
  vlan 99 (guest): temp static 10.1.99.2NN (no DHCP on guest by design),
                   ARP-resolve 10.1.99.1 — the ten64 offers no L3 service
                   on guest and firewalls the rest, so ARP is the proof

Usage:
    uv run check_vlan_reach.py                 # whole registry
    uv run check_vlan_reach.py --puck 12       # just puck12
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from galeflash.livecollect import parse_pucks_conf
from galeflash.vlanreach import VLAN_PROBES, build_remote_script, parse_results

REGISTRY_HOST = "tim@10.1.4.2"  # wisp.welland.mithis.com
REGISTRY_PATH = "/etc/dnsmasq.d/gwifi-generated/pucks.conf"

SSH_OPTS = ["-4", "-o", "ConnectTimeout=20",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=8",
            "-o", "StrictHostKeyChecking=accept-new"]


class SshTransportError(RuntimeError):
    """ssh could not reach the host (rc 255) — the host may just be offline."""


def ssh(host: str, command: str, *, stdin: str | None = None,
        timeout: int = 240) -> str:
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, command],
        input=stdin, capture_output=True, text=True, timeout=timeout,
    )
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)   # never suppress stderr
    if result.returncode == 255:
        raise SshTransportError(f"ssh {host} unreachable (rc=255)")
    if result.returncode != 0:
        raise RuntimeError(
            f"remote command failed on {host} (rc={result.returncode})")
    return result.stdout


def check_one(name: str, ip: str, *, verbose: bool) -> dict[int, tuple[bool, str]]:
    """Run the probe script on one puck; returns {vid: (ok, detail)}."""
    script = build_remote_script(int(name.removeprefix("puck")))
    raw = ssh(f"root@{ip}", "sh -s", stdin=script)
    if verbose:
        print(raw)
    results = parse_results(raw)
    missing = {p.vid for p in VLAN_PROBES} - set(results)
    if missing:
        raise ValueError(
            f"{name}: probe output missing RESULT for vlan(s) "
            f"{sorted(missing)} — script did not complete:\n{raw}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check puck→ten64 reachability on every VLAN.")
    parser.add_argument("--puck", action="append", type=int, metavar="NN",
                        help="Check only puckNN (repeatable).")
    parser.add_argument("--verbose", action="store_true",
                        help="Show raw probe output (ping/udhcpc evidence).")
    args = parser.parse_args()

    print(f"Fetching registry from {REGISTRY_HOST}:{REGISTRY_PATH}")
    regs = parse_pucks_conf(ssh(REGISTRY_HOST, f"sudo -n cat {REGISTRY_PATH}"))
    if args.puck:
        wanted = {f"puck{n:02d}" for n in args.puck}
        unknown = wanted - set(regs)
        if unknown:
            sys.exit(f"ERROR: not in registry: {', '.join(sorted(unknown))}")
        regs = {k: v for k, v in regs.items() if k in wanted}
    print(f"Registry: {len(regs)} puck(s): {', '.join(sorted(regs))}")

    vids = [p.vid for p in VLAN_PROBES]
    table: dict[str, dict[int, tuple[bool, str]] | None] = {}
    for name in sorted(regs):
        reg = regs[name]
        print(f"Probing {name} ({reg.ip}) …", flush=True)
        try:
            table[name] = check_one(name, reg.ip, verbose=args.verbose)
        except (subprocess.TimeoutExpired, SshTransportError) as exc:
            print(f"  {name}: UNREACHABLE ({exc})", file=sys.stderr)
            table[name] = None
            continue
        row = table[name]
        summary = "  ".join(
            f"vlan{v}={'OK' if row[v][0] else 'FAIL'}" for v in vids)
        print(f"  {name}: {summary}")

    print("\n=== Summary (puck → ten64 per VLAN) ===")
    hdr = "puck    " + "".join(f"vlan{v:<6}" for v in vids)
    print(hdr)
    failures = 0
    for name in sorted(table):
        row = table[name]
        if row is None:
            print(f"{name:<8}" + "UNREACHABLE (mgmt ssh)")
            continue
        cells = []
        for v in vids:
            ok, _ = row[v]
            cells.append(f"{'OK' if ok else 'FAIL':<10}")
            if not ok:
                failures += 1
        print(f"{name:<8}" + "".join(cells))
        for v in vids:
            ok, detail = row[v]
            if not ok:
                print(f"        vlan{v}: {detail}")
    if failures:
        sys.exit(f"\n{failures} VLAN leg(s) FAILED")


if __name__ == "__main__":
    main()
