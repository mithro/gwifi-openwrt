# SPDX-License-Identifier: Apache-2.0
"""Extract a curated device-identity dict from a Gale SPI dump.

Only explicitly-listed fields are returned — sensitive VPD keys such as
``stable_device_secret_DO_NOT_SHARE`` and ``setup_psk`` are never included.
"""
import functools
import re
import subprocess
from pathlib import Path

from galeflash import const, vpd

# Fields to pluck from the merged VPD dicts (RO then RW).
# Explicit allowlist — nothing else enters the identity dict.
_VPD_FIELDS = (
    "serial_number",
    "mlb_serial_number",
    "region",
    "ethernet_mac0",
    "ethernet_mac1",
    "model_name",
)


def _ro_frid(buf: bytes) -> str:
    """Return the RO firmware ID string exactly as stored on-chip."""
    off, size = const.FMAP["RO_FRID"]
    region = buf[off : off + size]
    return region.split(b"\x00")[0].decode()


def _hwid(path: Path) -> str:
    """Return the hardware ID string from the GBB via futility."""
    out = subprocess.check_output(
        [str(const.FUTILITY), "gbb_utility", "--get", "--hwid", str(path)],
        text=True,
    )
    # Output: "hardware_id: GALE C2I-A2A-A3C-A4I-E87\n"
    m = re.search(r"hardware_id:\s*(.+)", out)
    if not m:
        raise ValueError(f"Could not parse HWID from futility output: {out!r}")
    return m.group(1).strip()


def _root_key_sha1(path: Path) -> str:
    """Return the GBB Root Key sha1sum from futility show output.

    The relevant block looks like::

        Root Key:
          ...
          Key sha1sum:         6d590b00dffc89019f82cc93469b13a737250bf1
        Recovery Key:
          ...

    We anchor on the "Root Key:" header's indentation and read the first
    "Key sha1sum:" within it, stopping if we reach another section header at
    the same-or-lower indentation (e.g. "Recovery Key:").
    """
    out = subprocess.check_output(
        [str(const.FUTILITY), "show", str(path)],
        text=True,
    )
    lines = out.splitlines()
    in_root_key = False
    root_indent = None
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if "Root Key:" in stripped:
            in_root_key = True
            root_indent = indent
            continue
        if in_root_key:
            m = re.search(r"Key sha1sum:\s+([0-9a-f]+)", line)
            if m:
                return m.group(1)
            if indent <= root_indent and stripped and stripped[0].isupper():
                break  # left the Root Key section without finding a sha1sum
    raise ValueError("Could not find Root Key sha1sum in futility show output")


@functools.lru_cache(maxsize=None)
def _dev_root_sha1() -> str:
    """Return the sha1sum of the dev-keys root public key."""
    out = subprocess.check_output(
        [str(const.FUTILITY), "show", str(const.DEVKEYS / "root_key.vbpubk")],
        text=True,
    )
    m = re.search(r"Key sha1sum:\s+([0-9a-f]+)", out)
    if not m:
        raise ValueError(f"Could not parse dev root key sha1sum: {out!r}")
    return m.group(1).strip()


def from_dump(path: Path) -> dict:
    """Return a curated identity dict for the Gale device whose SPI dump is at *path*.

    The returned dict contains only the fields listed in ``_VPD_FIELDS`` plus
    ``hwid``, ``ro_frid``, and ``is_stock``.  No sensitive VPD key ever enters
    the result.
    """
    path = Path(path)
    buf = path.read_bytes()

    # Decode both VPD regions; RW values shadow RO if both define a key.
    ro_off, ro_size = const.FMAP["RO_VPD"]
    rw_off, rw_size = const.FMAP["RW_VPD"]
    merged_vpd: dict = {}
    merged_vpd.update(vpd.decode(buf[ro_off : ro_off + ro_size]))
    merged_vpd.update(vpd.decode(buf[rw_off : rw_off + rw_size]))

    # Curate: only pluck explicitly-listed fields.
    result: dict = {field: merged_vpd.get(field) for field in _VPD_FIELDS}

    result["ro_frid"] = _ro_frid(buf)
    result["hwid"] = _hwid(path)

    root_sha1 = _root_key_sha1(path)
    dev_sha1 = _dev_root_sha1()
    result["is_stock"] = root_sha1 != dev_sha1

    return result
