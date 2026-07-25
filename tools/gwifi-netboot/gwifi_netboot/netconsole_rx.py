# SPDX-License-Identifier: Apache-2.0
"""Netconsole receiver: UDP datagrams -> per-source-IP log files.

The gale fleet streams kernel printk (incl. panic traces) here because
the pucks have no accessible serial console in the field. One file per
puck under /var/log/gale-netconsole/<ip>.log, lines timestamped on
arrival. Runs as gwifi-netconsole.service on wisp (10.1.4.2:6666).
"""

from __future__ import annotations

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


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BIND[1]
    serve((DEFAULT_BIND[0], port))
