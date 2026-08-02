# SPDX-License-Identifier: Apache-2.0
"""Netconsole receiver: UDP datagrams -> per-source-IP log files.

The gale fleet streams kernel printk (incl. panic traces) here because
the pucks have no accessible serial console in the field. One file per
puck under /var/log/gale-netconsole/<ip>.log, lines timestamped on
arrival. Runs as gwifi-netconsole.service on wisp (10.1.4.2:6666).
"""

from __future__ import annotations

import argparse
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BIND = ("10.1.4.2", 6666)
DEFAULT_DIR = Path("/var/log/gale-netconsole")


def serve(bind: tuple[str, int] = DEFAULT_BIND,
          log_dir: Path = DEFAULT_DIR,
          max_datagrams: int | None = None) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(bind)
    print(f"gale netconsole receiver on {bind[0]}:{bind[1]} -> {log_dir}",
          flush=True)
    count = 0
    while max_datagrams is None or count < max_datagrams:
        data, (src_ip, _) = sock.recvfrom(65535)
        count += 1
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        text = data.decode("utf-8", errors="replace")
        with open(log_dir / f"{src_ip}.log", "a") as fh:
            for line in text.splitlines() or [""]:
                fh.write(f"{stamp} {line}\n")


def parse_bind(argv: list[str]) -> tuple[str, int]:
    """Parse ``--bind HOST:PORT`` from argv, falling back to DEFAULT_BIND.

    The bind address used to be the DEFAULT_BIND constant alone -- welland's
    10.1.4.2 -- so a second site had no way to run this. The rendered unit
    now passes its own site's address (see ``gwifi_netboot.sites``).

    A malformed value exits rather than silently falling back: binding the
    wrong address would look healthy in systemd while receiving nothing.
    """
    parser = argparse.ArgumentParser(prog="gwifi_netboot.netconsole_rx")
    parser.add_argument("--bind", default=None,
                        help=f"HOST:PORT (default {DEFAULT_BIND[0]}:"
                             f"{DEFAULT_BIND[1]})")
    args = parser.parse_args(argv)
    if args.bind is None:
        return DEFAULT_BIND
    host, sep, port = args.bind.rpartition(":")
    if not sep or not host:
        parser.error(f"--bind must be HOST:PORT, got {args.bind!r}")
    if not port.isdigit():
        parser.error(f"--bind port must be numeric, got {port!r}")
    return (host, int(port))


if __name__ == "__main__":
    serve(parse_bind(sys.argv[1:]))
