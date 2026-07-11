#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
# SPDX-License-Identifier: Apache-2.0
"""Deploy gwifi-netboot to wisp (idempotent).

rsyncs the package + unit to wisp:/opt/gwifi-netboot, installs the systemd
unit, restarts the service, and smoke-tests /status. With --artifacts, also
rsyncs staged image artifacts (images/ + tftp/) from a local directory.

Usage:
    uv run deploy.py [--host tim@10.1.4.2] [--artifacts DIR]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "HostKeyAlias=wisp.welland.mithis.com"]


def run(argv: list[str]) -> None:
    print(f"+ {' '.join(argv)}")
    subprocess.run(argv, check=True)


def ssh(host: str, cmd: str) -> None:
    run(["ssh", *SSH_OPTS, host, cmd])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="tim@10.1.4.2")
    parser.add_argument("--artifacts", type=Path, default=None,
                        help="local dir with images/ and tftp/ to rsync "
                             "to /srv/gwifi/")
    args = parser.parse_args()

    # Code + unit → staging in $HOME, then sudo install (rsync can't sudo).
    run(["rsync", "-a", "--delete", "-e", f"ssh {' '.join(SSH_OPTS)}",
         "--exclude", "__pycache__", "--exclude", ".pytest_cache",
         str(HERE / "gwifi_netboot"), str(HERE / "systemd"),
         str(HERE / "pyproject.toml"),
         f"{args.host}:gwifi-netboot-staging/"])
    ssh(args.host,
        "sudo mkdir -p /opt/gwifi-netboot /etc/gwifi-netboot "
        "/var/lib/gwifi-netboot && "
        "sudo rsync -a --delete --exclude state.json "
        "~/gwifi-netboot-staging/gwifi_netboot /opt/gwifi-netboot/ && "
        "sudo install -m 0644 ~/gwifi-netboot-staging/systemd/"
        "gwifi-netboot.service /etc/systemd/system/gwifi-netboot.service && "
        "sudo systemctl daemon-reload && "
        "sudo systemctl enable gwifi-netboot && "
        "sudo systemctl restart gwifi-netboot")

    if args.artifacts:
        for sub in ("images", "tftp"):
            src = args.artifacts / sub
            if src.is_dir():
                run(["rsync", "-a", "-e", f"ssh {' '.join(SSH_OPTS)}",
                     f"{src}/", f"{args.host}:gwifi-artifacts-{sub}/"])
                ssh(args.host,
                    f"sudo rsync -a ~/gwifi-artifacts-{sub}/ /srv/gwifi/{sub}/")

    # Smoke test.
    ssh(args.host,
        "sleep 2 && systemctl is-active gwifi-netboot && "
        "curl -sf http://10.1.4.2:8080/status | head -c 200 && echo")
    print("deploy OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
