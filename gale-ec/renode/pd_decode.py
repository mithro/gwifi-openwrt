#!/usr/bin/env python3
"""Decoder for gale's PD TX (captured by GaleDma.DumpTx) — the inverse of pd_encode's TX path.

gale's pd_phy clocks the BMC half-UI LEVEL stream out over SPI1; GaleDma captures those bytes
(lastTx, dumped via DumpTx). This decodes that level stream back to PD messages:
  * levels = LSB-first bits of each captured byte (the firmware packs raw_samples LSB-first/word)
  * symbols are 10 half-UIs each; emitted10 = b_toggle ^ BMC(symbol); b_toggle' = bit9(emitted)
    ? 0x3FF : 0; preamble leaves b_toggle = 0x3FF
  * SOP = SYNC1,SYNC1,SYNC1,SYNC2 ; the next 4 4b5b symbols are the 16-bit header nibbles

VALIDATED two ways: (1) round-trips pd_encode.build_tx output (recovers the exact header), and
(2) decodes a REAL captured gale contract TX stream into GoodCRC / Request / DR_Swap / Soft_Reset.
This is the reference algorithm for the C# reactive PD partner (decode gale's message -> inject the
protocol-correct reply so swaps / soft+hard reset / contract handshakes complete, unlocking
pd_task's swap/reset/error states).
"""
import pd_encode as pe

_REVBMC = {pe.BMC(x): x for x in range(32)}
_DEC4B5B = {c: n for n, c in enumerate(pe.ENC4B5B)}
_PD_SOP = [pe.PD_SYNC1] * 3 + [pe.PD_SYNC2]

# PD control-message type names (cnt==0) and data-message names (cnt>0).
CTRL = {1: "GoodCRC", 2: "GotoMin", 3: "Accept", 4: "Reject", 5: "Ping", 6: "PS_RDY",
        7: "Get_Source_Cap", 8: "Get_Sink_Cap", 9: "DR_Swap", 10: "PR_Swap",
        11: "VCONN_Swap", 12: "Wait", 13: "Soft_Reset"}
DATA = {1: "Source_Cap", 2: "Request", 3: "BIST", 4: "Sink_Cap", 15: "VDM"}


def levels_from_hex(hexstr):
    raw = bytes.fromhex(hexstr.strip())
    return [(b >> k) & 1 for b in raw for k in range(8)]


def _syms_at(levels, start, nmax):
    off, bt, syms = start, 0x3FF, []
    while off + 10 <= len(levels) and len(syms) < nmax:
        em = 0
        for k in range(10):
            em |= levels[off + k] << k
        b = _REVBMC.get(em ^ bt)
        if b is None:
            break
        syms.append(b)
        bt = 0x3FF if (em & 0x200) else 0
        off += 10
    return syms


def _header_at(levels, start):
    s = _syms_at(levels, start, 8)
    if len(s) < 8 or s[:4] != _PD_SOP:
        return None
    try:
        nibs = [_DEC4B5B[s[4 + j]] for j in range(4)]
    except KeyError:
        return None
    return nibs[0] | nibs[1] << 4 | nibs[2] << 8 | nibs[3] << 12


def decode_messages(levels):
    """Scan the captured level stream and return [(offset, header, type, cnt, msg_id, name), ...]."""
    out = []
    i = 0
    while i < len(levels) - 60:
        hdr = _header_at(levels, i)
        if hdr is not None:
            t, cnt, mid = hdr & 0x1f, (hdr >> 12) & 7, (hdr >> 9) & 7
            name = (DATA.get(t, "data%d" % t) if cnt else CTRL.get(t, "ctrl%d" % t))
            out.append((i, hdr, t, cnt, mid, name))
            i += 200
            continue
        i += 1
    return out


def decode_hexfile(path):
    return decode_messages(levels_from_hex(open(path).read()))


if __name__ == "__main__":
    import sys
    # self-test: round-trip a known message through pd_encode then decode
    hdr = pe.header(3, 0, 5)
    bits = pe.build_tx(hdr, []).level_bits()
    got = _header_at(bits, 128)
    assert got == hdr, "round-trip failed: 0x%x != 0x%x" % (got, hdr)
    print("self-test OK: decoded header 0x%04x" % got)
    if len(sys.argv) > 1:
        for off, hdr, t, cnt, mid, name in decode_hexfile(sys.argv[1]):
            print("  @%-5d %-14s %s msgid=%d hdr=0x%04x" % (off, name, "DATA" if cnt else "CTRL", mid, hdr))
