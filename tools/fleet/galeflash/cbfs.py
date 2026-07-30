# SPDX-License-Identifier: Apache-2.0
"""CBFS helpers for Gale SPI images.

extend_fw_main_a — grow FW_MAIN_A's trailing CBFS empty entry to fill
the full FMAP region, so a re-signed preamble's body_size matches the
region size.  Faithfully ported from tmp/extend_cbfs_empty.py.
"""
from __future__ import annotations

import struct
import subprocess
from pathlib import Path

from galeflash import const

# CBFS entry magic
_LAR = b"LARCHIVE"
# CBFS header field layout (big-endian): magic[8], len(u32), type(u32),
# attrs_off(u32), offset(u32) where "offset" = header size
_HDR_LEN_OFF = 8   # byte offset of the len field within a LARCHIVE header


def extend_fw_main_a(path: Path) -> None:
    """Grow FW_MAIN_A's trailing CBFS empty entry so it fills the FMAP region.

    Operates in-place on *path*.  Raises ``RuntimeError`` on unexpected
    CBFS layout (no entries, or last entry is not the empty sentinel).
    """
    fw_off, fw_size = const.FMAP["FW_MAIN_A"]

    buf = bytearray(path.read_bytes())

    # Scan FW_MAIN_A for LARCHIVE entries.
    entries: list[tuple[int, int, int, int]] = []  # (e_off, e_len, e_type, hdr_size)
    pos = 0
    while pos < fw_size - 32:
        idx = buf.find(_LAR, fw_off + pos, fw_off + fw_size)
        if idx < 0:
            break
        e_off = idx - fw_off   # offset within FW_MAIN_A
        e_len    = struct.unpack(">I", buf[idx +  8 : idx + 12])[0]
        e_type   = struct.unpack(">I", buf[idx + 12 : idx + 16])[0]
        # bytes 16-19: attributes offset (unused)
        e_offset = struct.unpack(">I", buf[idx + 20 : idx + 24])[0]  # header size
        entries.append((e_off, e_len, e_type, e_offset))
        # Advance past this entry (data starts at hdr + hdr_size).
        pos = e_off + e_offset + e_len
        pos = (pos + 63) & ~63   # 64-byte CBFS alignment

    if not entries:
        raise RuntimeError("no CBFS entries found in FW_MAIN_A")

    last_off, last_len, last_type, last_hdr_size = entries[-1]
    if last_type != 0xFFFFFFFF:
        raise RuntimeError(
            f"last CBFS entry type=0x{last_type:08x}; expected 0xffffffff (empty)"
        )

    # New data_len so the empty entry fills exactly to the end of FW_MAIN_A.
    new_data_len = fw_size - last_off - last_hdr_size
    # Patch the len field in-place (big-endian u32 at offset 8 of the header).
    hdr_abs = fw_off + last_off
    struct.pack_into(">I", buf, hdr_abs + _HDR_LEN_OFF, new_data_len)

    path.write_bytes(bytes(buf))


def print_fw_main_a(path: Path) -> None:
    """Run ``cbfstool <path> print -r FW_MAIN_A`` and print output."""
    result = subprocess.run(
        [str(const.CBFSTOOL), str(path), "print", "-r", "FW_MAIN_A"],
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
