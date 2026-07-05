"""Offline unit tests for gflash.py (clean-room gale SPI read/write tool).

No hardware. Every expected value is derived from a specification -- the
chromiumos-EC usb_spi V1 wire format, the W25Q64FV datasheet (256 B page,
4 KiB sector, 62 B max payload), the UEFI GPT header/entry-array CRC32s, the
coreboot FMAP binary layout, and Google's VPD 2.0 'gVpdInfo' magic -- never by
copying gflash's own output. Accept/reject cases are paired so each validator
test only passes if the check genuinely bites.

Two injection seams make this possible without a device:
  * Bridge.transact() only uses self.dev.{write,read}; we build a Bridge via
    __new__ and inject a FakeUsbDev to exercise the fail-loud USB framing.
  * every flash op (read_region/write_region/verified_read) takes a `bridge`
    and only calls .transact(); a SimFlash implementing transact() simulates an
    8 MiB array so we can test erase/program/verify/repair logic directly.
"""
import struct
import zlib

import pytest
import usb.core

import gflash


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
def usberr(msg, errno=None):
    """A usb.core.USBError with a specific errno, robust to pyusb signature."""
    e = usb.core.USBError(msg)
    if errno is not None:
        e.errno = errno
    return e


class FakeUsbDev:
    """Minimal pyusb device stand-in for Bridge.transact framing tests.

    `reads` is a list of canned bulk-IN outcomes, consumed in order: bytes are
    returned, a USBError is raised. `write_returns` overrides the OUT byte count
    (default: full length). All OUT packets are recorded in `.writes`.
    """

    def __init__(self, reads, write_returns=None, write_error=None):
        self._reads = list(reads)
        self.writes = []
        self.read_calls = 0
        self.write_calls = 0
        self._write_returns = write_returns
        self._write_error = write_error

    def write(self, ep, data, timeout):
        self.write_calls += 1
        self.writes.append(bytes(data))
        if self._write_error is not None:
            raise self._write_error
        return len(data) if self._write_returns is None else self._write_returns

    def read(self, ep, size, timeout):
        self.read_calls += 1
        item = self._reads.pop(0)
        if isinstance(item, Exception):
            raise item
        return bytearray(item)


def make_bridge(dev):
    """A Bridge wired to a fake device, skipping the hardware-probing __init__."""
    b = gflash.Bridge.__new__(gflash.Bridge)
    b.log = gflash.Log(None)
    b.txn = 0
    b.rtts = []
    b.dev = dev
    return b


class SimFlash:
    """A `bridge` for the flash-op logic: implements transact() against a
    simulated W25Q64 array (RDID/RDSR/READ/WREN/ERASE/PAGE-PROGRAM)."""

    def __init__(self, data=None, size=0x1000, sr1=0, sr2=0,
                 erase_works=True, program_xor=0):
        self.flash = bytearray(data if data is not None else b"\xff" * size)
        self.sr1 = sr1
        self.sr2 = sr2
        self.erase_works = erase_works
        self.program_xor = program_xor
        self.txn = 0
        self.rtts = []
        self.log = gflash.Log(None)
        self.ops = []

    def transact(self, wdata, rcount, context=""):
        self.txn += 1
        op = wdata[0]
        self.ops.append(op)
        if op == gflash.OP_RDSR1:
            return bytes([self.sr1])
        if op == gflash.OP_RDSR2:
            return bytes([self.sr2])
        if op == 0x9F:  # RDID
            return bytes(gflash.RDID_EXPECT)[:rcount]
        if op == gflash.OP_WREN:
            return b""
        if op == gflash.OP_READ:
            addr = int.from_bytes(wdata[1:4], "big")
            return bytes(self.flash[addr:addr + rcount])
        if op == gflash.OP_SECTOR_ERASE:
            addr = int.from_bytes(wdata[1:4], "big")
            if self.erase_works:
                self.flash[addr:addr + gflash.SECTOR_SIZE] = \
                    b"\xff" * gflash.SECTOR_SIZE
            return b""
        if op == gflash.OP_PAGE_PROGRAM:
            addr = int.from_bytes(wdata[1:4], "big")
            payload = bytes(b ^ self.program_xor for b in wdata[4:])
            self.flash[addr:addr + len(payload)] = payload
            return b""
        raise AssertionError("SimFlash: unexpected opcode 0x%02x" % op)


class GlitchBridge:
    """A read-only `bridge` whose READ payloads are rewritten by `transform`
    (context, addr, true_bytes) -> bytes, to simulate read glitches."""

    def __init__(self, flash, transform):
        self.flash = bytes(flash)
        self.transform = transform
        self.txn = 0
        self.rtts = []
        self.log = gflash.Log(None)

    def transact(self, wdata, rcount, context=""):
        self.txn += 1
        assert wdata[0] == gflash.OP_READ
        addr = int.from_bytes(wdata[1:4], "big")
        true = self.flash[addr:addr + rcount]
        return self.transform(context, addr, true)


# --------------------------------------------------------------------------- #
# Group A: pure protocol/format helpers
# --------------------------------------------------------------------------- #
def test_addr3_is_24bit_big_endian():
    assert gflash.addr3(0x123456) == b"\x12\x34\x56"
    assert gflash.addr3(0) == b"\x00\x00\x00"
    assert gflash.addr3(0xFFFFFF) == b"\xff\xff\xff"


def test_status_name_known_and_conventions():
    assert gflash.status_name(0x0000) == "SUCCESS"
    assert gflash.status_name(0x0001) == "SPI_TIMEOUT"
    assert gflash.status_name(0x0005) == "BRIDGE_DISABLED"
    # EC error convention: high bit set -> EC_ERROR(low 15 bits)
    assert gflash.status_name(0x8005) == "EC_ERROR(0x0005)"
    # otherwise UNKNOWN
    assert gflash.status_name(0x0099) == "UNKNOWN(0x0099)"


def test_parse_num_accepts_bases():
    assert gflash.parse_num("0x400000") == 0x400000
    assert gflash.parse_num("4096") == 4096
    assert gflash.parse_num("0o20") == 16


def test_iter_program_chunks_never_crosses_256B_page():
    # W25Q64 page program must not cross a 256-byte page; payload <= 58 B
    # (62 B V1 max - 1 opcode - 3 address).
    for offset in (0x000000, 0x0000F0, 0x400000 + 5, 0x123401):
        data = bytes((i * 13 + 1) & 0xFF for i in range(600))
        chunks = list(gflash.iter_program_chunks(offset, data))
        rebuilt = b"".join(c for _, c in chunks)
        assert rebuilt == data                       # lossless
        prev_end = offset
        for addr, chunk in chunks:
            assert addr == prev_end                  # contiguous
            assert 0 < len(chunk) <= 58              # payload ceiling
            assert addr // 256 == (addr + len(chunk) - 1) // 256  # no page cross
            prev_end = addr + len(chunk)


def test_diff_runs_merges_adjacent_and_separates_gaps():
    assert gflash.diff_runs(b"abcd", b"abcd") == []
    assert gflash.diff_runs(b"abcd", b"aXcd") == [(1, 2)]
    assert gflash.diff_runs(b"abcd", b"aXYd") == [(1, 3)]          # adjacent merge
    assert gflash.diff_runs(b"abcde", b"aXcYe") == [(1, 2), (3, 4)]  # gap splits


def test_diff_runs_length_mismatch_is_fatal():
    with pytest.raises(gflash.FatalError):
        gflash.diff_runs(b"abc", b"ab")


def test_parse_flags_line_and_power_state():
    sysinfo = "sysinfo\r\nReset flags: 0x1\r\nFlags:  unlocked\r\n> "
    assert gflash.parse_flags_line(sysinfo) == "Flags:  unlocked"
    assert gflash.parse_power_state("gale power\r\n  power - off\r\n> ") == "off"
    assert gflash.parse_power_state("  power - on\n> ") == "on"


def test_parse_flags_line_missing_is_fatal():
    with pytest.raises(gflash.FatalError):
        gflash.parse_flags_line("no flags here\n> ")


def test_completion_predicates():
    assert gflash.has_flags_line("Flags: locked\n")
    assert not gflash.has_flags_line("Flags: locked")       # no newline yet
    assert gflash.has_power_state("x power - off\n")
    assert not gflash.has_power_state("x power - off")       # no newline yet
    assert gflash.has_ok_line("blah\nOK\nblah")
    assert not gflash.has_ok_line("NOTOK\ndone")


def test_describe_sr_decodes_bits():
    assert "SRP0" in gflash.describe_sr(gflash.SR1_SRP0, 0)
    assert "SRP1" in gflash.describe_sr(0, gflash.SR2_SRP1)
    assert "BP=7" in gflash.describe_sr(gflash.SR1_BP, 0)   # BP0..2 all set = 7
    assert gflash.describe_sr(0, 0) == "SR1=0x00 SR2=0x00"


# --------------------------------------------------------------------------- #
# Group B: Bridge.transact -- V1 framing + fail-loud, NO retries
# --------------------------------------------------------------------------- #
def test_transact_frames_v1_and_returns_payload():
    dev = FakeUsbDev(reads=[b"\x00\x00" + b"\xef\x40\x17"])  # status 0 + RDID
    b = make_bridge(dev)
    got = b.transact(bytes([0x9F]), 3, context="RDID")
    assert got == b"\xef\x40\x17"
    # OUT packet is [write_count, read_count, payload...] per V1.
    assert dev.writes == [bytes([1, 3, 0x9F])]
    assert b.txn == 1


def test_transact_nonzero_status_fails_loud():
    dev = FakeUsbDev(reads=[b"\x01\x00"])   # USB_SPI_TIMEOUT (0x0001)
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x9F]), 0, context="x")
    assert "SPI_TIMEOUT" in str(ei.value)


def test_transact_bridge_disabled_status_fails_loud():
    dev = FakeUsbDev(reads=[b"\x05\x00"])   # BRIDGE_DISABLED (0x0005)
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x03, 0, 0, 0]), 0)
    assert "BRIDGE_DISABLED" in str(ei.value)


def test_transact_short_in_fails_loud():
    dev = FakeUsbDev(reads=[b"\x00"])       # < 2 status bytes
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x9F]), 3)
    assert "too short" in str(ei.value)


def test_transact_length_mismatch_fails_loud():
    # asked for 3 payload bytes, got 1 (total 3 != 2+3)
    dev = FakeUsbDev(reads=[b"\x00\x00\xaa"])
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x9F]), 3)
    assert "length mismatch" in str(ei.value)


def test_transact_in_timeout_fails_loud_without_retry():
    dev = FakeUsbDev(reads=[usberr("operation timed out", errno=110)])
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x9F]), 3, context="RDID")
    assert "TIMEOUT" in str(ei.value)
    assert dev.read_calls == 1          # NOT retried


def test_transact_in_enodev_fails_loud():
    dev = FakeUsbDev(reads=[usberr("no such device", errno=19)])
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x9F]), 3)
    assert "ENODEV" in str(ei.value)


def test_transact_out_error_fails_loud_without_retry():
    dev = FakeUsbDev(reads=[], write_error=usberr("pipe error", errno=32))
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x9F]), 3)
    assert "OUT" in str(ei.value)
    assert dev.write_calls == 1 and dev.read_calls == 0


def test_transact_short_out_fails_loud():
    dev = FakeUsbDev(reads=[], write_returns=1)   # claims only 1 byte written
    b = make_bridge(dev)
    with pytest.raises(gflash.FatalError) as ei:
        b.transact(bytes([0x9F]), 3)
    assert "short bulk OUT" in str(ei.value)


def test_transact_oversize_request_is_guarded():
    b = make_bridge(FakeUsbDev(reads=[]))
    with pytest.raises(gflash.FatalError):
        b.transact(b"x" * 63, 0)          # write > 62
    with pytest.raises(gflash.FatalError):
        b.transact(b"x", 63)              # read > 62


def test_check_rdid_accepts_expected_rejects_other():
    gflash.check_rdid(make_bridge(FakeUsbDev(reads=[b"\x00\x00\xef\x40\x17"])))
    with pytest.raises(gflash.FatalError) as ei:
        gflash.check_rdid(make_bridge(FakeUsbDev(reads=[b"\x00\x00\x00\x00\x00"])))
    assert "RDID mismatch" in str(ei.value)


# --------------------------------------------------------------------------- #
# Group C: read/write/verify/repair logic (SimFlash / GlitchBridge)
# --------------------------------------------------------------------------- #
def test_read_region_streams_exact_bytes_in_62B_chunks():
    payload = bytes((i * 7) & 0xFF for i in range(0x1000))
    sim = SimFlash(data=payload, size=len(payload))
    got = gflash.read_region(sim, 0x10, 200)
    assert got == payload[0x10:0x10 + 200]
    # 200 bytes / 62 per txn -> 4 transactions
    assert sim.txn == (200 + 62 - 1) // 62


def test_verified_read_identical_passes_no_repair():
    payload = bytes((i * 3 + 1) & 0xFF for i in range(124))
    sim = SimFlash(data=payload, size=len(payload))
    data, report = gflash.verified_read(sim, 0, 124, sim.log)
    assert data == payload
    assert report["runs"] == []
    assert report["pass1_sha"] == report["pass2_sha"]


def test_verified_read_repairs_transient_pass2_glitch():
    payload = bytes((i * 5 + 2) & 0xFF for i in range(124))

    def transform(context, addr, true):
        # corrupt byte 0 of the first chunk, but only on pass 2
        if context.startswith("pass2") and addr == 0:
            b = bytearray(true)
            b[0] ^= 0xFF
            return bytes(b)
        return true

    gb = GlitchBridge(payload, transform)
    data, report = gflash.verified_read(gb, 0, 124, gb.log)
    assert data == payload                       # true value recovered
    assert len(report["runs"]) == 1
    lo, hi, p1_wrong, p2_wrong = report["runs"][0]
    assert (lo, hi) == (0, 1)
    assert p2_wrong and not p1_wrong             # pass2 was the glitched one


def test_verified_read_unstable_range_fails_loud():
    payload = bytes((i * 9 + 4) & 0xFF for i in range(124))
    counter = {"n": 0}

    def transform(context, addr, true):
        if context.startswith("repair"):
            counter["n"] += 1
            b = bytearray(true)
            b[0] = counter["n"] & 0xFF           # every repair read differs
            return bytes(b)
        if context.startswith("pass2") and addr == 0:
            b = bytearray(true)
            b[0] ^= 0xFF
            return bytes(b)
        return true

    gb = GlitchBridge(payload, transform)
    with pytest.raises(gflash.FatalError) as ei:
        gflash.verified_read(gb, 0, 124, gb.log)
    assert "repair failed" in str(ei.value)


def test_wait_wip_clear_returns_when_idle_and_times_out_when_busy():
    assert gflash.wait_wip_clear(SimFlash(sr1=0), 1.0, "x") == 1  # WIP clear
    busy = SimFlash(sr1=gflash.SR1_WIP)
    with pytest.raises(gflash.FatalError) as ei:
        gflash.wait_wip_clear(busy, 0.05, "erase@0x0")           # never clears
    assert "still busy" in str(ei.value)


def test_write_region_erase_program_verify_roundtrip():
    sim = SimFlash(size=gflash.SECTOR_SIZE)
    # pre-fill with non-ff so we can tell erase happened
    sim.flash[:] = bytes((i * 11) & 0xFF for i in range(gflash.SECTOR_SIZE))
    src = bytes((i * 17 + 9) & 0xFF for i in range(gflash.SECTOR_SIZE))
    timings = gflash.write_region(sim, 0, src, sim.log, verify=True)
    assert bytes(sim.flash) == src
    assert set(("erase_s", "program_s", "verify_s")) <= set(timings)
    assert gflash.OP_WREN in sim.ops and gflash.OP_SECTOR_ERASE in sim.ops


def test_write_region_refuses_when_block_protect_set():
    sim = SimFlash(size=gflash.SECTOR_SIZE, sr1=gflash.SR1_BP)
    with pytest.raises(gflash.FatalError) as ei:
        gflash.write_region(sim, 0, b"\xaa" * gflash.SECTOR_SIZE, sim.log)
    assert "block-protect" in str(ei.value)


def test_write_region_detects_erase_no_op():
    sim = SimFlash(size=gflash.SECTOR_SIZE, erase_works=False)
    sim.flash[:] = b"\x00" * gflash.SECTOR_SIZE     # head won't become 0xff
    with pytest.raises(gflash.FatalError) as ei:
        gflash.write_region(sim, 0, b"\x11" * gflash.SECTOR_SIZE, sim.log)
    assert "ERASE NO-OP" in str(ei.value)


def test_write_region_verify_mismatch_fails_loud():
    sim = SimFlash(size=gflash.SECTOR_SIZE, program_xor=0x01)  # writes corrupted
    with pytest.raises(gflash.FatalError) as ei:
        gflash.write_region(sim, 0, b"\x20" * gflash.SECTOR_SIZE, sim.log)
    assert "VERIFY FAILED" in str(ei.value)


# --------------------------------------------------------------------------- #
# Group D: backup-image data validation (spec-built structures)
# --------------------------------------------------------------------------- #
def build_gpt(corrupt_header=False, corrupt_array=False, with_sig=True):
    """A minimal but CRC-correct UEFI GPT region (1024 B): header + entry array."""
    header = bytearray(92)
    header[0:8] = b"EFI PART" if with_sig else b"XXXXXXXX"
    struct.pack_into("<I", header, 12, 92)     # header_size
    struct.pack_into("<Q", header, 24, 1)      # current_lba
    struct.pack_into("<Q", header, 72, 2)      # part_entry_lba (=current+1 -> +512)
    struct.pack_into("<I", header, 80, 4)      # num_entries
    struct.pack_into("<I", header, 84, 128)    # entry_size -> arr_len 512
    array = bytes((i * 7 + 3) & 0xFF for i in range(512))
    struct.pack_into("<I", header, 88, zlib.crc32(array) & 0xFFFFFFFF)
    struct.pack_into("<I", header, 16, 0)      # zero before header CRC
    struct.pack_into("<I", header, 16, zlib.crc32(bytes(header)) & 0xFFFFFFFF)
    region = bytearray(1024)
    region[0:92] = header
    region[512:1024] = array
    if corrupt_array:
        region[512] ^= 0xFF
    if corrupt_header:
        region[50] ^= 0xFF                     # inside header, not the CRC field
    return bytes(region)


def build_fmap(areas):
    """areas: list of (name, offset, size, flags). Returns FMAP blob bytes."""
    buf = bytearray(b"__FMAP__")
    buf += bytes([1, 1])                        # ver_major, ver_minor
    buf += struct.pack("<Q", 0)                 # base
    buf += struct.pack("<I", 0x800000)          # total size
    buf += b"FMAP".ljust(32, b"\0")             # name
    buf += struct.pack("<H", len(areas))
    for name, off, size, flags in areas:
        buf += struct.pack("<II", off, size)
        buf += name.encode().ljust(32, b"\0")
        buf += struct.pack("<H", flags)
    return bytes(buf)


def test_parse_fmap_roundtrip_and_absent():
    blob = build_fmap([("RW_GPT_PRIMARY", 0x560000, 0x1000, 0),
                       ("RO_VPD", 0x3E0000, 0x20000, 0)])
    fmap = gflash.parse_fmap(blob)
    assert fmap["name"] == "FMAP"
    assert fmap["version"] == (1, 1)
    assert fmap["size"] == 0x800000
    assert fmap["areas"]["RW_GPT_PRIMARY"] == (0x560000, 0x1000, 0)
    assert fmap["areas"]["RO_VPD"] == (0x3E0000, 0x20000, 0)
    assert gflash.parse_fmap(b"\xff" * 4096) is None


def test_validate_gpt_accepts_good_rejects_corruption():
    log = gflash.Log(None)
    gflash.validate_gpt(build_gpt(), log, "GPT")            # must not raise
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_gpt(build_gpt(corrupt_array=True), log, "GPT")
    assert "entry-array CRC32 mismatch" in str(ei.value)
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_gpt(build_gpt(corrupt_header=True), log, "GPT")
    assert "header CRC32 mismatch" in str(ei.value)
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_gpt(build_gpt(with_sig=False), log, "GPT")
    assert "EFI PART" in str(ei.value)


def test_validate_vpd_accepts_magic_rejects_blank():
    log = gflash.Log(None)
    gflash.validate_vpd(b"gVpdInfo" + b"\x00\x01\x00\x00" + b"\x00" * 64,
                        log, "RO_VPD")                       # must not raise
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_vpd(b"\x00" * 128, log, "RO_VPD")
    assert "gVpdInfo" in str(ei.value)


def build_spurious_fmap():
    """An 8-byte '__FMAP__' coincidence with a garbage header, reproducing the
    real spurious hit observed at 0x0453fb: non-printable name, absurd declared
    total (~1.85 GB) and area count (11876)."""
    b = bytearray(b"__FMAP__")
    b += bytes([228, 0])                                  # ver garbage
    b += struct.pack("<Q", 0x2061000D206F4E30)            # base garbage
    b += struct.pack("<I", 0x6E756F66)                    # total garbage
    b += bytes([0x64, 0xBE, 0x03, 0x23, 0x7A, 0x78,       # name: non-printable
                0xAB, 0x03, 0x01, 0x2C, 0x08]) + b"\x00" * 21
    b += struct.pack("<H", 11876)                         # nareas garbage
    return bytes(b)


def build_full_image(break_gpt=False, spurious=False,
                     include_gpt=True, include_vpd=True, blank_gpt=False):
    data = bytearray(b"\xff" * gflash.FLASH_SIZE)
    areas = []
    if include_gpt:
        if not blank_gpt:   # blank_gpt: declare the FMAP area but leave it 0xff
            gpt = build_gpt(corrupt_array=break_gpt)
            data[0x560000:0x560000 + len(gpt)] = gpt
        areas.append(("RW_GPT_PRIMARY", 0x560000, 0x1000, 0))
    if include_vpd:
        vpd = b"gVpdInfo" + b"\x00\x01\x00\x00" + b"\x00" * 64
        data[0x3E0000:0x3E0000 + len(vpd)] = vpd
        areas.append(("RO_VPD", 0x3E0000, 0x20000, 0))
    fmap = build_fmap(areas)
    data[0x300000:0x300000 + len(fmap)] = fmap
    if spurious:
        sp = build_spurious_fmap()
        data[0x0453FB:0x0453FB + len(sp)] = sp   # a spurious hit BEFORE the real FMAP
    return bytes(data)


def test_validate_full_image_accepts_good_backup():
    gflash.validate_full_image(build_full_image(), gflash.Log(None),
                               skip_vboot=True)               # must not raise


def test_validate_full_image_rejects_corrupt_gpt():
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_full_image(build_full_image(break_gpt=True),
                                   gflash.Log(None), skip_vboot=True)
    assert "CRC32 mismatch" in str(ei.value)


def test_validate_full_image_size_and_fmap_guards():
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_full_image(b"\xff" * 100, gflash.Log(None), skip_vboot=True)
    assert "full" in str(ei.value)
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_full_image(b"\xff" * gflash.FLASH_SIZE, gflash.Log(None),
                                   skip_vboot=True)
    assert "__FMAP__" in str(ei.value)


# --- regression: spurious __FMAP__ selection + silent-skip (observed live) --- #
def test_parse_fmap_rejects_spurious_only_image():
    # A full image whose ONLY __FMAP__ is a garbage coincidence has no real
    # FMAP -> parse must return None, not a garbage dict.
    data = bytearray(b"\xff" * gflash.FLASH_SIZE)
    sp = build_spurious_fmap()
    data[0x0453FB:0x0453FB + len(sp)] = sp
    assert gflash.parse_fmap(bytes(data)) is None


def test_parse_fmap_skips_spurious_and_returns_real():
    fmap = gflash.parse_fmap(build_full_image(spurious=True))
    assert fmap is not None
    assert fmap["fmap_offset"] == gflash.FMAP_EXPECTED_OFFSET       # the real one
    assert fmap["name"] == "FMAP"
    assert "RW_GPT_PRIMARY" in fmap["areas"] and "RO_VPD" in fmap["areas"]


def test_parse_fmap_prefers_expected_offset_over_earlier_sane():
    # Two structurally-sane FMAPs; the real one at 0x300000 must win.
    data = bytearray(b"\xff" * gflash.FLASH_SIZE)
    early = build_fmap([("DECOY", 0x1000, 0x1000, 0)])
    data[0x100000:0x100000 + len(early)] = early
    real = build_fmap([("RW_GPT_PRIMARY", 0x560000, 0x1000, 0)])
    data[0x300000:0x300000 + len(real)] = real
    fmap = gflash.parse_fmap(bytes(data))
    assert fmap["fmap_offset"] == gflash.FMAP_EXPECTED_OFFSET
    assert "RW_GPT_PRIMARY" in fmap["areas"]


def test_validate_full_image_ignores_spurious_fmap_and_checks_regions():
    # THE production bug: a spurious __FMAP__ must not shadow the real FMAP and
    # silently skip the GPT/VPD checks.
    gflash.validate_full_image(build_full_image(spurious=True), gflash.Log(None),
                               skip_vboot=True)                     # must not raise
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_full_image(build_full_image(spurious=True, break_gpt=True),
                                   gflash.Log(None), skip_vboot=True)
    assert "CRC32 mismatch" in str(ei.value)                       # GPT check DID run


def test_validate_full_image_fails_loud_when_gpt_or_vpd_absent():
    # Region entirely ABSENT from the FMAP (not merely blank) -> the FMAP is
    # wrong; fail loud instead of silently skipping.
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_full_image(build_full_image(include_gpt=False),
                                   gflash.Log(None), skip_vboot=True)
    assert "GPT" in str(ei.value)
    with pytest.raises(gflash.FatalError) as ei:
        gflash.validate_full_image(build_full_image(include_vpd=False),
                                   gflash.Log(None), skip_vboot=True)
    assert "VPD" in str(ei.value)


def test_validate_full_image_accepts_blank_gpt_region():
    # gale's RW_GPT region is legitimately erased (0xff) on netboot pucks
    # (verified: pristine stock 2712HW0072Z). A blank cached-GPT region present
    # in the FMAP must be accepted, not treated as corruption.
    gflash.validate_full_image(build_full_image(blank_gpt=True), gflash.Log(None),
                               skip_vboot=True)   # must not raise
