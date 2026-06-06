#!/usr/bin/env python3
"""Encode a USB-PD message into the gale EC's RX capture-sample byte array — i.e. act as
the CC partner's PD-PHY. Ported byte-for-byte from the firmware's own TX encoder
(common/usb_pd_tcpc.c prepare_message + chip/stm32/usb_pd_phy.c pd_write_preamble/
pd_write_sym/pd_write_last_edge) so the produced waveform is exactly what the EC would
itself drive, then converted to the TIM1 input-capture edge-timestamp form the EC's RX
hardware (COMP -> TIM1 CH1 capture -> DMA ch2) records into pd_phy[0].raw_samples.

The EC TX path fills raw_samples with the half-UI LINE LEVELS (2 half-UIs per PD bit, via
BMC + a running b_toggle). A real partner drives that waveform; the EC's RX captures the
TIM count at each level transition. With PERIOD=4 TIM ticks per half-UI, a '0' PD bit (no
mid transition) yields one 8-tick interval (>PERIOD_THRESHOLD=6 -> decoded '0') and a '1'
PD bit (mid transition) yields two 4-tick intervals (<=6 -> decoded '1') — exactly the
decoder's rule (chip/stm32/usb_pd_phy.c pd_dequeue_bits).

A built-in self-check re-implements pd_find_preamble + pd_dequeue_bits + decode and asserts
the generated samples round-trip back to the original header+objects+CRC, so we KNOW the
firmware will decode them before ever touching Renode.

Usage (as a library): from pd_encode import encode_message; samples = encode_message(header, objs)
Run directly to self-test the canonical Source_Capabilities message.
"""
import zlib

PERIOD = 4                  # TIM1 ticks per half-UI (psc=19 -> 2.4MHz; usb_pd_phy.c:52)
PD_PREAMBLE = 0xB4B4B4B4    # usb_pd_phy.c:47 ("starts with 0, ends with 1")
PD_SYNC1, PD_SYNC2, PD_EOP = 0x18, 0x11, 0x0D   # include/usb_pd.h / usb_pd_tcpc.c


def BMC(x):
    """Biphase Mark Coding of a 5-bit symbol -> 10-bit half-UI pattern (usb_pd_tcpc.c:48)."""
    return ((0x001 if x & 1 else 0x3FF)
            ^ (0x004 if x & 2 else 0x3FC)
            ^ (0x010 if x & 4 else 0x3F0)
            ^ (0x040 if x & 8 else 0x3C0)
            ^ (0x100 if x & 16 else 0x300))


# 4b5b table (usb_pd_tcpc.c:55) — index = 4-bit nibble, value = 5-bit code.
ENC4B5B = [0x1E, 0x09, 0x14, 0x15, 0x0A, 0x0B, 0x0E, 0x0F,
           0x12, 0x13, 0x16, 0x17, 0x1A, 0x1B, 0x1C, 0x1D]


class TxBits:
    """Replicates the firmware's raw_samples TX bit buffer (LSB-first per 32-bit word)
    and the running b_toggle, via pd_write_preamble / pd_write_sym / pd_write_last_edge."""

    def __init__(self):
        self.words = {}
        self.b_toggle = 0
        self.off = 0

    def _setword(self, idx, val):
        self.words[idx] = val & 0xFFFFFFFF

    def _orword(self, idx, val):
        self.words[idx] = (self.words.get(idx, 0) | val) & 0xFFFFFFFF

    def preamble(self):
        for i in range(4):
            self._setword(i, PD_PREAMBLE)
        self.b_toggle = 0x3FF
        self.off = 2 * 64

    def sym(self, val10):
        word_idx = self.off // 32
        bit_idx = self.off % 32
        val = self.b_toggle ^ val10
        self.b_toggle = 0x3FF if (val & 0x200) else 0
        if bit_idx <= 22:
            if bit_idx == 0:
                self._setword(word_idx, 0)
            self._orword(word_idx, (val << bit_idx) & 0xFFFFFFFF)
        else:
            self._orword(word_idx, (val << bit_idx) & 0xFFFFFFFF)
            self._setword(word_idx + 1, val >> (32 - bit_idx))
        self.off += 5 * 2

    def last_edge(self):
        word_idx = self.off // 32
        bit_idx = self.off % 32
        if bit_idx == 0:
            self._setword(word_idx, 0)
        if not self.b_toggle:                  # last bit was 0 -> add an edge
            if bit_idx == 31:
                self._orword(word_idx, 1 << bit_idx)
                self._setword(word_idx + 1, 1)
                word_idx += 1
            else:
                self._orword(word_idx, 3 << bit_idx)
        self._setword(word_idx + 1, 0)
        self.off += 3

    def encode_short(self, v16):
        for sh in (0, 4, 8, 12):
            self.sym(BMC(ENC4B5B[(v16 >> sh) & 0xF]))

    def encode_word(self, v32):
        self.encode_short(v32 & 0xFFFF)
        self.encode_short((v32 >> 16) & 0xFFFF)

    def level_bits(self):
        """Return the half-UI level stream as a list of 0/1, LSB-first per word."""
        nbits = self.off
        bits = []
        for i in range(nbits):
            w = self.words.get(i // 32, 0)
            bits.append((w >> (i % 32)) & 1)
        return bits


def crc32_pd(header, objs):
    """Firmware crc32: init 0xFFFFFFFF, hash header (2 bytes LE) + each obj (4 bytes LE),
    final XOR 0xFFFFFFFF. Equivalent to zlib.crc32 over those little-endian bytes."""
    buf = bytes([header & 0xFF, (header >> 8) & 0xFF])
    for o in objs:
        buf += bytes([o & 0xFF, (o >> 8) & 0xFF, (o >> 16) & 0xFF, (o >> 24) & 0xFF])
    return zlib.crc32(buf) & 0xFFFFFFFF


def build_tx(header, objs):
    """prepare_message: preamble + SOP + header + objects + CRC + EOP + last edge."""
    tx = TxBits()
    tx.preamble()
    tx.sym(BMC(PD_SYNC1)); tx.sym(BMC(PD_SYNC1)); tx.sym(BMC(PD_SYNC1)); tx.sym(BMC(PD_SYNC2))
    tx.encode_short(header)
    for o in objs:
        tx.encode_word(o)
    tx.encode_word(crc32_pd(header, objs))
    tx.sym(BMC(PD_EOP))
    tx.last_edge()
    return tx


def levels_to_samples(bits):
    """Convert the half-UI level stream into TIM1 capture timestamps: one byte per level
    transition, value = (half-UI index * PERIOD) & 0xFF. Idle line before bit 0 is taken
    as the inverse of bits[0] so the leading edge is captured."""
    samples = []
    prev = bits[0] ^ 1
    for i, b in enumerate(bits):
        if b != prev:
            samples.append((i * PERIOD) & 0xFF)
            prev = b
    return bytes(samples)


def encode_message(header, objs):
    return levels_to_samples(build_tx(header, objs).level_bits())


# ---- self-check: port of pd_find_preamble + pd_dequeue_bits + decode (RX side) ----
PERIOD_THRESHOLD = 6
DEC4B5B = {c: n for n, c in enumerate(ENC4B5B)}


def _find_preamble(s):
    allv = 0
    for bit in range(1, len(s)):
        cnt = (s[bit] - s[bit - 1]) & 0xFF
        allv = ((allv >> 1) | (0x80000000 if cnt <= PERIOD_THRESHOLD else 0)) & 0xFFFFFFFF
        if allv == 0x36db6db6:
            return bit - 1
    return -1


class _Deq:
    def __init__(self, s, off):
        self.s = s; self.off = off

    def bits(self, n):
        out = 0
        for k in range(n):
            cnt = (self.s[self.off] - self.s[self.off - 1]) & 0xFF
            if cnt <= PERIOD_THRESHOLD:           # '1': consume a second short half
                self.off += 1
                cnt2 = (self.s[self.off] - self.s[self.off - 1]) & 0xFF
                if cnt2 > PERIOD_THRESHOLD:
                    raise ValueError("bad 1-bit second half at %d" % self.off)
                out |= (1 << k)
                self.off += 1
            else:                                  # '0'
                self.off += 1
        return out

    def short(self):
        w = self.bits(20)
        return (DEC4B5B[w & 0x1f] | (DEC4B5B[(w >> 5) & 0x1f] << 4)
                | (DEC4B5B[(w >> 10) & 0x1f] << 8) | (DEC4B5B[(w >> 15) & 0x1f] << 12))


def _self_check(header, objs):
    s = encode_message(header, objs)
    pre = _find_preamble(s)
    assert pre >= 0, "preamble (0x36db6db6) not found"
    d = _Deq(s, pre)
    sop = d.bits(20)
    PD_SOP = PD_SYNC1 | (PD_SYNC1 << 5) | (PD_SYNC1 << 10) | (PD_SYNC2 << 15)
    assert sop == PD_SOP, "SOP mismatch: got 0x%X want 0x%X" % (sop, PD_SOP)
    h = d.short()
    assert h == header, "header mismatch: got 0x%X want 0x%X" % (h, header)
    got = []
    for _ in objs:
        lo = d.short(); hi = d.short()
        got.append(lo | (hi << 16))
    assert got == objs, "objs mismatch: %s vs %s" % ([hex(x) for x in got], [hex(x) for x in objs])
    clo = d.short(); chi = d.short()
    rxcrc = clo | (chi << 16)
    assert rxcrc == crc32_pd(header, objs), "CRC mismatch 0x%X" % rxcrc
    return s


# Canonical messages (include/usb_pd.h PD_HEADER / PDO_FIXED).
def header(msg_type, cnt, msg_id, prole=1, drole=1, rev=1):
    return (msg_type | (rev << 6) | (drole << 5) | (prole << 8) | (msg_id << 9) | (cnt << 12))


PDO_5V_1A5 = 0x22019096          # PDO_FIXED(5000,1500, dual-role|data-swap)
SRC_CAP = (header(1, 1, 0), [PDO_5V_1A5])          # PD_DATA_SOURCE_CAP, 1 PDO
def ACCEPT(mid): return (header(3, 0, mid), [])    # PD_CTRL_ACCEPT
def PS_RDY(mid): return (header(6, 0, mid), [])    # PD_CTRL_PS_RDY


def ctrl(ctrl_type, mid):
    """A control message (no data objects)."""
    return (header(ctrl_type, 0, mid), [])


def vdm_discover_identity(mid):
    """A structured VDM (data msg type 15) carrying a Discover Identity command, so the
    firmware's pd_svdm / VDM-handling branches execute. VDO[0] = SVID(PD SID 0xFF00)<<16 |
    (1<<15 structured) | (0 ver) | CMDT_INIT(0) | CMD Discover Identity(1)."""
    vdm_hdr = (0xFF00 << 16) | (1 << 15) | (0 << 6) | 1
    return (header(15, 1, mid), [vdm_hdr])


# A battery of message TYPES to drive the decode + protocol-dispatch branches broadly.
# (Control: GOTO_MIN2 ACCEPT3 REJECT4 PING5 PS_RDY6 GET_SRC_CAP7 GET_SNK_CAP8 DR_SWAP9
#  PR_SWAP10 VCONN_SWAP11 WAIT12 SOFT_RESET13; Data: SOURCE_CAP1 + VDM.)
def battery():
    out = [("Source_Caps", SRC_CAP)]
    for name, t in [("GotoMin", 2), ("Accept", 3), ("Reject", 4), ("Ping", 5), ("PS_RDY", 6),
                    ("GetSrcCap", 7), ("GetSnkCap", 8), ("DR_Swap", 9), ("PR_Swap", 10),
                    ("VconnSwap", 11), ("Wait", 12), ("SoftReset", 13)]:
        out.append((name, ctrl(t, 1)))
    out.append(("VDM_DiscId", vdm_discover_identity(1)))
    return out


if __name__ == "__main__":
    for name, (h, objs) in [("Source_Caps", SRC_CAP), ("Accept", ACCEPT(1)), ("PS_RDY", PS_RDY(2))]:
        s = _self_check(h, objs)
        print("%-12s header=0x%04X objs=%s  -> %d samples, round-trips OK"
              % (name, h, [hex(o) for o in objs], len(s)))
