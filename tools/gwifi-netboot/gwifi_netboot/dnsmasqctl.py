# SPDX-License-Identifier: Apache-2.0
"""Gate + install + restart for the generated dnsmasq fragment.

Sequence: write fragment to a temp file -> `dnsmasq --test` against it ->
atomic rename into place -> `systemctl restart dnsmasq`. A fragment that
fails the syntax check never replaces the last-good config and never
triggers a restart.

restart, not reload: dnsmasq's SIGHUP re-reads /etc/hosts and
dhcp-hostsfile but NOT conf-dir files, so a restart is the only correct
primitive for changed dhcp-host/dhcp-boot lines (sub-second daemon).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

Runner = Callable[[list[str]], None]


class DnsmasqctlError(Exception):
    """Fragment failed validation or dnsmasq restart failed."""


def _default_runner(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


def install_fragment(content: str, target: Path,
                     run: Runner = _default_runner) -> None:
    """Validate, atomically install, and activate a dnsmasq fragment."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())

        try:
            run(["dnsmasq", "--test", f"--conf-file={tmp}"])
        except subprocess.CalledProcessError as e:
            raise DnsmasqctlError(
                f"dnsmasq --test rejected the rendered fragment: {e}") from e

        os.replace(tmp, target)
        tmp = None
    finally:
        if tmp is not None:
            os.unlink(tmp)

    try:
        run(["systemctl", "restart", "dnsmasq"])
    except subprocess.CalledProcessError as e:
        raise DnsmasqctlError(f"dnsmasq restart failed: {e}") from e
