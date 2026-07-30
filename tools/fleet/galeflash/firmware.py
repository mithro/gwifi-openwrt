# SPDX-License-Identifier: Apache-2.0
"""Firmware-version identifiers recorded per puck for the fleet spreadsheet.

Answers "what firmware is flashed to / running on the device":
  * depthcharge_version() — the TFTP-first netboot payload we flash
  * rw_fwid()             — the coreboot RW firmware id in the flashed slots
  * parse_ec_version()    — the STM32 EC firmware id (from `ec version` output)
"""
import hashlib
import re
import subprocess
from pathlib import Path

from galeflash import const


def depthcharge_version() -> str:
    """Return '<git-rev> (elf:<sha12>)' identifying the flashed netboot payload.

    Pairs the recorded source rev (``const.DEPTHCHARGE_GIT``) with a short
    sha256 of the actual ``const.PAYLOAD_ELF`` so the sheet value is both
    human-readable and verifiable against the bytes that were flashed.  A
    missing payload is a hard error — better than silently mislabelling.
    """
    sha12 = hashlib.sha256(Path(const.PAYLOAD_ELF).read_bytes()).hexdigest()[:12]
    return f"{const.DEPTHCHARGE_GIT} (elf:{sha12})"


def parse_ec_version(ec_version_output: str) -> str:
    """Extract the RO firmware id from `flash_puck_usb.py ec version` output.

    The console prints e.g. ``RO:      gale_v1.1.5337-0115719``.  Returns the
    id; raises ValueError if no RO line is present (fail loud, don't guess).
    """
    m = re.search(r"^\s*RO:\s*(\S+)", ec_version_output, re.MULTILINE)
    if not m:
        raise ValueError(
            f"no 'RO:' firmware line in ec version output: {ec_version_output!r}")
    return m.group(1)


def rw_fwid(image_path: Path) -> str:  # pragma: no cover
    """Return the coreboot RW firmware id (RW_FWID_A) from a built/flashed image.

    Reads the RW_FWID_A FMAP region via cbfstool and strips NUL padding, e.g.
    ``Google_Gale.8281.47.0``.
    """
    raw = subprocess.check_output(
        [str(const.CBFSTOOL), str(image_path), "read", "-r", "RW_FWID_A",
         "-f", "/dev/stdout"],
    )
    return raw.split(b"\x00")[0].decode().strip()
