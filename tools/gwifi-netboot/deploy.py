#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
# SPDX-License-Identifier: Apache-2.0
"""Deploy gwifi-netboot to a site's wisp (idempotent).

rsyncs the package to wisp:/opt/gwifi-netboot, installs the RENDERED systemd
units and the RENDERED /etc/dnsmasq.d/gwifi.conf, restarts dnsmasq and the
services, and smoke-tests /status.  With --artifacts, also rsyncs staged
image artifacts (images/ + tftp/) from a local directory.

Every address comes from ``gwifi_netboot.sites``.  This used to be hardcoded
to welland throughout -- including ``HostKeyAlias=wisp.welland.mithis.com``,
which would have made a monarto deploy validate against welland's SSH host
key.

It also installs the dnsmasq config, which previously existed ONLY as a
hand-written file on wisp.welland.  That omission is why monarto had nothing
serving DHCP/TFTP on the wifi VLAN: the site router sets
``no-dhcp-interface=br-wifi`` on purpose, because serving that VLAN is
wisp's job.

Usage:
    uv run deploy.py --site monarto [--artifacts DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from gwifi_netboot import sites as sitelib  # noqa: E402


def run(argv: list[str], *, dry: bool = False) -> None:
    print(f"+ {' '.join(argv)}", flush=True)
    if not dry:
        subprocess.run(argv, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, choices=sorted(sitelib.SITES),
                        help="which site's wisp to deploy to")
    parser.add_argument("--artifacts", type=Path, default=None,
                        help="local dir with images/ and tftp/ to rsync "
                             "to /srv/gwifi/")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would run; change nothing")
    args = parser.parse_args()

    site = sitelib.SITES[args.site]
    dry = args.dry_run
    # HostKeyAlias follows the SITE, not a constant -- see module docstring.
    ssh_opts = ["-o", "BatchMode=yes",
                "-o", f"HostKeyAlias={site.fqdn}", *site.ssh_opts]
    ssh_cmd = f"ssh {' '.join(ssh_opts)}"
    host = site.ssh_target

    def ssh(cmd: str) -> None:
        run(["ssh", *ssh_opts, host, cmd], dry=dry)

    print(f"=== gwifi-netboot -> {site.name} ({host}, binds {site.wisp_ip}) ===")

    # Render the site-specific files into a staging dir beside this script.
    staged = HERE / ".rendered" / site.name
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "gwifi-netboot.service").write_text(sitelib.netboot_unit(site))
    (staged / "gwifi-netconsole.service").write_text(
        sitelib.netconsole_unit(site))
    (staged / "gwifi.conf").write_text(sitelib.dnsmasq_conf(site))
    print(f"rendered units + dnsmasq conf for {site.name} -> {staged}")
    if dry:
        print("--- gwifi.conf ---")
        print((staged / "gwifi.conf").read_text())

    # Code + rendered files -> staging in $HOME, then sudo install (rsync
    # cannot sudo).
    run(["rsync", "-a", "--delete", "-e", ssh_cmd,
         "--exclude", "__pycache__", "--exclude", ".pytest_cache",
         str(HERE / "gwifi_netboot"), str(HERE / "pyproject.toml"),
         f"{host}:gwifi-netboot-staging/"], dry=dry)
    run(["rsync", "-a", "-e", ssh_cmd,
         f"{staged}/", f"{host}:gwifi-netboot-staging/rendered/"], dry=dry)

    ssh("sudo mkdir -p /opt/gwifi-netboot /etc/gwifi-netboot "
        "/var/lib/gwifi-netboot /etc/dnsmasq.d/gwifi-generated "
        "/srv/gwifi/tftp /srv/gwifi/images && "
        "sudo rsync -a --delete --exclude state.json "
        "~/gwifi-netboot-staging/gwifi_netboot /opt/gwifi-netboot/ && "
        "sudo install -m 0644 ~/gwifi-netboot-staging/rendered/*.service "
        "/etc/systemd/system/ && "
        "sudo install -m 0644 ~/gwifi-netboot-staging/rendered/gwifi.conf "
        "/etc/dnsmasq.d/gwifi.conf && "
        "sudo systemctl daemon-reload")

    # dnsmasq first: the netboot unit is ordered After=dnsmasq.service, and it
    # is dnsmasq that actually answers the pucks.  Install it if absent -- a
    # freshly built wisp has no dnsmasq, and without it nothing serves DHCP or
    # TFTP on the wifi VLAN.
    ssh("command -v dnsmasq >/dev/null || "
        "{ sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive "
        "apt-get install -y dnsmasq; }")
    ssh("sudo systemctl enable dnsmasq && sudo systemctl restart dnsmasq && "
        "systemctl is-active dnsmasq")
    ssh("for n in gwifi-netboot.service gwifi-netconsole.service; do "
        "  sudo systemctl enable $n; sudo systemctl restart $n; done")

    if args.artifacts:
        for sub in ("images", "tftp"):
            src = args.artifacts / sub
            if src.is_dir():
                run(["rsync", "-a", "-e", ssh_cmd,
                     f"{src}/", f"{host}:gwifi-artifacts-{sub}/"], dry=dry)
                ssh(f"sudo rsync -a ~/gwifi-artifacts-{sub}/ /srv/gwifi/{sub}/")

    # Smoke test against THIS site's address.
    ssh("sleep 2 && systemctl is-active gwifi-netboot gwifi-netconsole && "
        f"curl -sf http://{site.wisp_ip}:8080/status | head -c 200 && echo")
    print(f"deploy OK ({site.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
