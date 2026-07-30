# SPDX-License-Identifier: Apache-2.0
"""Decode a Google VPD 2.0 region (RO_VPD / RW_VPD) to a {key: value} dict.

The VPD 2.0 container format:
  - A google_vpd_info header (locatable by the 8-byte "gVpdInfo" magic),
    followed by 5 bytes of version/size metadata (total 13 bytes to skip).
  - TLV entries:
      type byte  0x01 = string pair, 0x00 = terminator, 0xff = padding/end
      key:   pad-len varint, then that many bytes
      value: pad-len varint, then that many bytes
  - pad-len varint: 7 bits per byte, high bit set means more bytes follow.
"""


def _pad_len(buf, i):
    """Decode a VPD pad-len varint: 7 bits/byte, MSB = more bytes follow.

    Returns (value, new_index).  If the buffer is truncated mid-varint
    (i >= len(buf)) the function stops early and returns whatever partial
    value has accumulated so far, keeping new_index at the end of the
    buffer.  This prevents IndexError on a short partial read from the
    SPI bridge.
    """
    v = 0
    while True:
        if i >= len(buf):
            return v, i
        b = buf[i]; i += 1
        v = (v << 7) | (b & 0x7f)
        if not (b & 0x80):
            return v, i


def decode(region: bytes) -> dict:
    """Decode a Google VPD 2.0 region blob to a {key: value} dict.

    Returns an empty dict if the region is erased or the magic is absent
    (e.g. a blank RW_VPD).
    """
    start = region.find(b"gVpdInfo")
    if start < 0:
        return {}

    # The "gVpdInfo" magic is 8 bytes; it is followed by 5 bytes of
    # version/size metadata (confirmed by byte-inspection of the G4 fixture:
    # bytes are 04 0d 7f 00 00).  First TLV entry type byte is at start+13.
    i = start + 13

    out = {}
    while i < len(region):
        t = region[i]; i += 1
        if t in (0x00, 0xff):
            break
        if t != 0x01:
            break
        klen, i = _pad_len(region, i)
        key = region[i:i + klen].decode()
        i += klen
        vlen, i = _pad_len(region, i)
        val = region[i:i + vlen].decode(errors="replace")
        i += vlen
        out[key] = val
    return out
