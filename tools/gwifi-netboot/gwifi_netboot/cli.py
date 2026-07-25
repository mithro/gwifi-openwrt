# SPDX-License-Identifier: Apache-2.0
"""gwifi-netboot CLI: status | arm | disarm | render | serve.

Arming a puck makes wisp's DHCP offer it the installer bootfile on the
next power cycle; the installer phones home, which auto-disarms on
success/already-current. Runs as root on wisp (writes the dnsmasq
fragment and restarts dnsmasq).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gwifi_netboot.dnsmasqctl import DnsmasqctlError, install_fragment
from gwifi_netboot.httpd import App, Installer, make_server
from gwifi_netboot.identity import IdentityError
from gwifi_netboot.state import StateStore

DEFAULTS = {
    "identity": "/etc/gwifi-netboot/pucks.json",
    "state": "/var/lib/gwifi-netboot/state.json",
    "fragment": "/etc/dnsmasq.d/gwifi-generated/pucks.conf",
    "manifest": "/srv/gwifi/images/manifest.json",
}


def _build_app(args, installer: Installer) -> App:
    return App(
        identity_path=Path(args.identity),
        state=StateStore(Path(args.state)),
        fragment_path=Path(args.fragment),
        manifest_path=Path(args.manifest),
        installer=installer,
    )


def _resolve_macs(app: App, names: list[str], all_pucks: bool) -> list[str]:
    pucks = app.identity()
    if all_pucks:
        return [p.eth0 for p in pucks]
    by_name = {p.name: p for p in pucks}
    macs = []
    for name in names:
        if name not in by_name:
            known = ", ".join(sorted(by_name)) or "(none — identity empty?)"
            raise SystemExit(f"unknown puck {name!r}; known: {known}")
        macs.append(by_name[name].eth0)
    return macs


def main(argv: list[str] | None = None,
         installer: Installer = install_fragment) -> int:
    parser = argparse.ArgumentParser(prog="gwifi-netboot", description=__doc__)
    for key, default in DEFAULTS.items():
        parser.add_argument(f"--{key}", default=default)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show pucks + arming/install state (JSON)")

    for cmd in ("arm", "disarm"):
        p = sub.add_parser(cmd, help=f"{cmd} pucks for install")
        p.add_argument("pucks", nargs="*", metavar="puck")
        p.add_argument("--all", action="store_true", dest="all_pucks")

    p = sub.add_parser("render", help="render + activate the dnsmasq fragment")
    p.add_argument("--check", action="store_true",
                   help="only validate identity/render, do not install")

    p = sub.add_parser("serve", help="run the manifest/phone-home HTTP API")
    p.add_argument("--bind", default="10.1.4.2:8080")

    args = parser.parse_args(argv)
    app = _build_app(args, installer)

    try:
        if args.command == "status":
            print(json.dumps(app.status(), indent=2))
            return 0

        if args.command in ("arm", "disarm"):
            if not args.pucks and not args.all_pucks:
                print("nothing to do: name pucks or pass --all",
                      file=sys.stderr)
                return 2
            macs = _resolve_macs(app, args.pucks, args.all_pucks)
            getattr(app.state, args.command)(macs)
            app.regenerate()
            print(f"{args.command}ed {len(macs)} puck(s); dnsmasq updated")
            return 0

        if args.command == "render":
            content_pucks = app.identity()
            if not content_pucks and app.identity_path.exists():
                # identity file present but unusable -> IdentityError below
                from gwifi_netboot.identity import load_identity
                load_identity(app.identity_path)
            if args.check:
                print(f"identity OK: {len(content_pucks)} puck(s)")
                return 0
            app.regenerate()
            print("fragment rendered + activated")
            return 0

        if args.command == "serve":
            host, _, port = args.bind.rpartition(":")
            app.regenerate()  # converge on startup
            server = make_server(app, host, int(port))
            print(f"gwifi-netboot API on {args.bind}", flush=True)
            server.serve_forever()
            return 0
    except (IdentityError, DnsmasqctlError, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code is not None and not isinstance(e.code, str):
            raise
        print(f"error: {e}", file=sys.stderr)
        return 1

    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
