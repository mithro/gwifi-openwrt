#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Deploy the presence-detector service to fleet pucks.

Run AFTER the ansells-presence template is attached and device vars are set
(see runbook in the design spec).

**This CLI MUTATES pucks**: per reachable puck (registry: wisp's dnsmasq
gwifi-generated/pucks.conf) it runs `apk add` for the presence-detector's
runtime deps and enables/restarts the `presence-detector` init service, then
verifies four steps in order:
  files:   the ansells-presence template already delivered
           /opt/presence-detector/presence-detector.py,
           /etc/presence-detector/settings.json,
           /etc/init.d/presence-detector (fails loud if the template hasn't
           been attached yet — see the runbook)
  apk:     `apk update && apk add python3 python3-paho-mqtt` succeeded
  service: the service registered with procd within ~15s of restart
  mqtt:    syslog-error check on the puck (auth/connect failures surface
           here) — NOT a broker-side "message arrived" check; that
           fleet-wide verification happens once in runbook step 4, not
           per puck inside this CLI (accepted spec deviation, see Task 6)

Usage:
    uv run deploy_presence.py                 # whole registry
    uv run deploy_presence.py --puck 12       # just puck12
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from galeflash.livecollect import parse_pucks_conf
from galeflash.presencedeploy import STEPS, build_install_script, parse_results

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


def deploy_one(name: str, ip: str, *, verbose: bool) -> dict[str, tuple[bool, str]]:
    """Run the install script on one puck; returns {step: (ok, detail)}.

    parse_results() already raises ValueError on missing/duplicate/malformed
    RESULT lines — that check is not repeated here, it just propagates.
    """
    script = build_install_script()
    raw = ssh(f"root@{ip}", "sh -s", stdin=script)
    if verbose:
        print(raw)
    return parse_results(raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy presence-detector (apk install + service enable) to fleet pucks.")
    parser.add_argument("--puck", action="append", type=int, metavar="NN",
                        help="Deploy only to puckNN (repeatable).")
    parser.add_argument("--verbose", action="store_true",
                        help="Show raw install-script output (apk/service/log evidence).")
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

    table: dict[str, dict[str, tuple[bool, str]] | None] = {}
    for name in sorted(regs):
        reg = regs[name]
        print(f"Deploying to {name} ({reg.ip}) …", flush=True)
        try:
            table[name] = deploy_one(name, reg.ip, verbose=args.verbose)
        except (subprocess.TimeoutExpired, SshTransportError, ValueError) as exc:
            print(f"  {name}: FAILED ({exc})", file=sys.stderr)
            table[name] = None
            continue
        row = table[name]
        summary = "  ".join(
            f"{s}={'OK' if row[s][0] else 'FAIL'}" for s in STEPS)
        print(f"  {name}: {summary}")

    print("\n=== Summary (files / apk / service / mqtt) ===")
    hdr = "puck    " + "".join(f"{s:<10}" for s in STEPS)
    print(hdr)
    failures = 0
    for name in sorted(table):
        row = table[name]
        if row is None:
            print(f"{name:<8}" + "FAILED (ssh/parse error, see above)")
            failures += 1
            continue
        cells = []
        for s in STEPS:
            ok, _ = row[s]
            cells.append(f"{'OK' if ok else 'FAIL':<10}")
            if not ok:
                failures += 1
        print(f"{name:<8}" + "".join(cells))
        for s in STEPS:
            ok, detail = row[s]
            if not ok:
                print(f"        {s}: {detail}")
    if failures:
        sys.exit(f"\n{failures} step(s)/puck(s) FAILED")


if __name__ == "__main__":
    main()
