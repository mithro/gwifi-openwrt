"""Offline tests for flash_puck_usb.py's new logic: the 64 KiB-block + 4 KiB-
sector erase planner and the block-erase-aware write_region. No hardware; a
SimFlash implements the bridge's transact() against a simulated array.
"""
import struct

import pytest

import flash_puck_usb as fp


def _image_with_fmap(areas):
    """8 MiB image with an FMAP at 0x300000. areas: [(name, off, size), ...]."""
    data = bytearray(b"\xff" * fp.FLASH_SIZE)
    fmap = bytearray(b"__FMAP__") + bytes([1, 1]) + struct.pack("<Q", 0)
    fmap += struct.pack("<I", fp.FLASH_SIZE) + b"FMAP".ljust(32, b"\0")
    fmap += struct.pack("<H", len(areas))
    for name, off, size in areas:
        fmap += struct.pack("<II", off, size) + name.encode().ljust(32, b"\0") + struct.pack("<H", 0)
    data[0x300000:0x300000 + len(fmap)] = fmap
    return bytes(data)


_STD_AREAS = [("RW_SECTION_A", 0x400000, 0x160000),
              ("RW_SECTION_B", 0x580000, 0x160000),
              ("GBB", 0x301000, 0xDF000), ("RO_VPD", 0x3E0000, 0x20000)]


def test_flash_plan_ro_last_order():
    plan = fp.flash_plan(_image_with_fmap(_STD_AREAS))
    assert [n for n, _, _ in plan] == ["RW_SECTION_A", "RW_SECTION_B", "GBB"]
    assert plan[-1][1] < fp.RO_GUARD_LIMIT          # GBB is the RO-last region


def test_flash_plan_missing_region_fails_loud():
    with pytest.raises(fp.FatalError):
        fp.flash_plan(_image_with_fmap([("RW_SECTION_A", 0x400000, 0x160000),
                                        ("GBB", 0x301000, 0xDF000)]))  # no RW_SECTION_B


def test_flash_plan_rounds_unaligned_gbb_to_sectors():
    # GBB's real size (0xDEF00) is not sector-aligned; the plan rounds the span
    # UP to the 4 KiB boundary (0xDF000), flashing the extra bytes from source.
    plan = fp.flash_plan(_image_with_fmap([("RW_SECTION_A", 0x400000, 0x160000),
                                           ("RW_SECTION_B", 0x580000, 0x160000),
                                           ("GBB", 0x301000, 0xDEF00)]))
    gbb = [e for e in plan if e[0] == "GBB"][0]
    assert gbb == ("GBB", 0x301000, 0xDF000)        # 0xDEF00 -> 0xDF000, aligned


def test_flash_plan_bad_image_size_fails_loud():
    with pytest.raises(fp.FatalError):
        fp.flash_plan(b"\xff" * 100)


class SimFlash:
    """A `bridge` for write_region/read_region: transact() over a simulated
    array covering [base, base+size). Handles RDID/RDSR/READ/WREN/erase/PP."""

    def __init__(self, base, size, fill=0x00, sr1=0, erase_works=True, program_xor=0):
        self.base = base
        self.flash = bytearray(bytes([fill]) * size)
        self.sr1 = sr1
        self.wel = False
        self.erase_works = erase_works
        self.program_xor = program_xor
        self.txn = 0
        self.rtts = []
        self.ops = []

    def _idx(self, addr):
        return addr - self.base

    def transact(self, wdata, rcount, context=""):
        self.txn += 1
        op = wdata[0]
        self.ops.append(op)
        if op == fp.OP_RDSR1:
            return bytes([self.sr1 | (fp.SR1_WEL if self.wel else 0)])
        if op == fp.OP_RDSR2:
            return bytes([0])
        if op == fp.OP_RDID:
            return bytes(fp.RDID_EXPECT)[:rcount]
        if op == fp.OP_WREN:
            self.wel = True                       # WREN latches WEL
            return b""
        if op == fp.OP_READ:
            a = self._idx(int.from_bytes(bytes(wdata[1:4]), "big"))
            return bytes(self.flash[a:a + rcount])
        if op in (fp.OP_SECTOR_ERASE, fp.OP_BLOCK_ERASE):
            a = self._idx(int.from_bytes(bytes(wdata[1:4]), "big"))
            size = fp.BLOCK_SIZE if op == fp.OP_BLOCK_ERASE else fp.SECTOR_SIZE
            if self.erase_works:
                self.flash[a:a + size] = b"\xff" * size
            self.wel = False                      # erase clears WEL
            return b""
        if op == fp.OP_PAGE_PROGRAM:
            a = self._idx(int.from_bytes(bytes(wdata[1:4]), "big"))
            payload = bytes(b ^ self.program_xor for b in wdata[4:])
            self.flash[a:a + len(payload)] = payload
            self.wel = False                      # program clears WEL
            return b""
        raise AssertionError("unexpected opcode 0x%02x" % op)


# ------------------------------- erase_plan -------------------------------- #
def test_erase_plan_all_blocks_when_aligned():
    plan = fp.erase_plan(0x400000, 0x160000, use_block=True)   # 22 x 64 KiB
    assert all(size == fp.BLOCK_SIZE and op == fp.OP_BLOCK_ERASE
               for _, size, op in plan)
    assert len(plan) == 0x160000 // fp.BLOCK_SIZE == 22


def test_erase_plan_block_plus_sector_tail():
    plan = fp.erase_plan(0x700000, 0x11000, use_block=True)    # 1 block + 1 sector
    assert [(a, s, op) for a, s, op in plan] == [
        (0x700000, fp.BLOCK_SIZE, fp.OP_BLOCK_ERASE),
        (0x710000, fp.SECTOR_SIZE, fp.OP_SECTOR_ERASE),
    ]


def test_erase_plan_sectors_until_block_alignment():
    # Starts unaligned: 4 KiB sectors until a 64 KiB boundary, then a block.
    plan = fp.erase_plan(0x40F000, 0x11000, use_block=True)   # sector -> aligned -> block
    assert plan == [
        (0x40F000, fp.SECTOR_SIZE, fp.OP_SECTOR_ERASE),
        (0x410000, fp.BLOCK_SIZE, fp.OP_BLOCK_ERASE),
    ]


def test_erase_plan_covers_range_contiguously():
    for off, ln in [(0x400000, 0x160000), (0x700000, 0x11000), (0x40F000, 0x11000),
                    (0x401000, 0x2000)]:
        plan = fp.erase_plan(off, ln)
        addr = off
        for a, s, _ in plan:
            assert a == addr                       # contiguous, in order
            addr += s
        assert addr == off + ln                    # exact coverage


def test_erase_plan_requires_4k_alignment():
    with pytest.raises(fp.FatalError):
        fp.erase_plan(0x700800, 0x1000)
    with pytest.raises(fp.FatalError):
        fp.erase_plan(0x700000, 0x800)


# ------------------------------ write_region ------------------------------- #
def test_write_region_block_and_sector_roundtrip():
    base, off, ln = 0x700000, 0x700000, 0x11000   # spans a block + a sector
    sim = SimFlash(base, ln, fill=0x00)           # non-blank, like real RW_LEGACY
    src = bytes((i * 37 + 5) & 0xFF for i in range(ln))
    timings = fp.write_region(sim, off, src, log=fp.Log(None), verify=True)
    assert bytes(sim.flash) == src
    assert set(("erase_s", "program_s", "verify_s")) <= set(timings)
    assert fp.OP_SECTOR_ERASE in sim.ops       # sector-only by default (proven, low-current)
    assert fp.OP_BLOCK_ERASE not in sim.ops


def test_write_region_detects_blocked_erase():
    sim = SimFlash(0x700000, 0x10000, fill=0x00, erase_works=False)
    with pytest.raises(fp.FatalError) as ei:
        fp.write_region(sim, 0x700000, b"\x11" * 0x10000, log=fp.Log(None))
    assert "ERASE NO-OP" in str(ei.value)


def test_write_region_verify_mismatch_fails_loud():
    sim = SimFlash(0x700000, 0x10000, fill=0x00, program_xor=0x01)
    with pytest.raises(fp.FatalError) as ei:
        fp.write_region(sim, 0x700000, b"\x20" * 0x10000, log=fp.Log(None))
    assert "VERIFY FAILED" in str(ei.value)


def test_write_region_refuses_block_protect():
    sim = SimFlash(0x700000, 0x10000, sr1=fp.SR1_BP)
    with pytest.raises(fp.FatalError) as ei:
        fp.write_region(sim, 0x700000, b"\xaa" * 0x10000, log=fp.Log(None))
    assert "block-protect" in str(ei.value)


# ------------------------- inline AP abort guard --------------------------- #
class FakeDev:
    """Minimal pyusb device double for SpiBridge.transact framing tests."""

    def write(self, ep, data, timeout):
        return len(data)

    def read(self, ep, size, timeout):
        return bytearray(b"\x00\x00" + b"\xef\x40\x17")   # status 0 + RDID payload


def _bare_bridge():
    b = fp.SpiBridge.__new__(fp.SpiBridge)
    b.dev = FakeDev()
    b.log = fp.Log(None)
    b.txn = 0
    b.rtts = []
    b.abort_check = None
    b.abort_every = 512
    return b


def test_transact_polls_abort_check_every_abort_every():
    b = _bare_bridge()
    b.abort_every = 4
    seen = []
    b.abort_check = lambda txn: seen.append(txn)
    for _ in range(9):
        b.transact([0x9F], 3)
    assert seen == [4, 8]              # polled at the interval, not every txn


def test_transact_abort_check_raise_aborts_the_stream():
    b = _bare_bridge()
    b.abort_every = 3
    b.abort_check = lambda txn: (_ for _ in ()).throw(fp.FatalError("AP woke @%d" % txn))
    b.transact([0x9F], 3)
    b.transact([0x9F], 3)             # first two are below the interval
    with pytest.raises(fp.FatalError) as ei:
        b.transact([0x9F], 3)        # third hits the guard
    assert "AP woke" in str(ei.value)


# ------------------------- sessioned flash/read ---------------------------- #
class _FakeSess:
    def __init__(self, bridge):
        self.bridge = bridge

    def teardown(self):
        pass


def test_flash_region_writes_and_reads_across_pieces():
    # One SimFlash stands in for the flash across all "fresh sessions".
    sim = SimFlash(0x700000, 0x3000, fill=0x00)
    ns = lambda: _FakeSess(sim)  # noqa: E731
    src = bytes((i * 13 + 1) & 0xFF for i in range(0x3000))
    fp.flash_region(ns, 0x700000, src, log=fp.Log(None))
    assert bytes(sim.flash) == src
    got = fp.read_region_sessioned(ns, 0x700000, 0x3000, fp.Log(None), piece=0x1000)
    assert got == src


def test_flash_region_requires_4k_alignment():
    ns = lambda: _FakeSess(SimFlash(0x700000, 0x2000))  # noqa: E731
    with pytest.raises(fp.FatalError):
        fp.flash_region(ns, 0x700000, b"\x00" * 0x800, fp.Log(None))


def test_flash_region_downshifts_past_a_session_budget():
    # A DEGRADED session (small txn budget) fails a large piece; flash_region must
    # split down until pieces fit, and the whole region still comes out correct.
    base, size = 0x700000, 0x8000
    flash = bytearray(b"\x00" * size)

    class BudgetBridge(SimFlash):
        def __init__(self):
            super().__init__(base, size)
            self.flash = flash                 # shared across "sessions"
            self.budget = 400                  # a >4 KiB piece exceeds this

        def transact(self, wdata, rcount, context=""):
            if self.txn >= self.budget:
                raise fp.FatalError("simulated session budget exhausted")
            return super().transact(wdata, rcount, context)

    class FS:
        def __init__(self):
            self.bridge = BudgetBridge()

        def teardown(self):
            pass

    src = bytes((i * 7 + 1) & 0xFF for i in range(size))
    fp.flash_region(lambda: FS(), base, src, fp.Log(None))
    assert bytes(flash) == src                 # completed correctly via downshift


# ------------------------- boot classification ----------------------------- #
def test_boot_classify_good_dev_signed():
    text = ("vb2 ... This is developer signed firmware ...\n"
            "Starting depthcharge on gale...\nSending DHCP discover")
    r = fp.boot_classify(text)
    assert r["verdict"] == "GOOD"
    assert r["dev_signed"] is True


def test_boot_classify_bad_wins_over_good_banner():
    text = "Starting depthcharge on gale...\nVB2:vb2_fail entering recovery"
    assert fp.boot_classify(text)["verdict"] == "BAD"


def test_boot_classify_bare_recovery_is_not_failure():
    text = ("vb2_check_recovery() Recovery reason from previous boot: 0x0\n"
            "gpio: recovery=0")
    assert fp.boot_classify(text)["verdict"] == "UNDECIDED"


def test_boot_slot_last_verified():
    assert fp.boot_slot("... FW_MAIN_A found ...") == "A"
    assert fp.boot_slot("FW_MAIN_A found ... then FW_MAIN_B found") == "B"
    assert fp.boot_slot("no slot line here") is None


# ------------------------- program chunking (page) ------------------------- #
def test_iter_program_chunks_never_crosses_page():
    data = bytes((i * 3) & 0xFF for i in range(600))
    for offset in (0x700000, 0x7000F0):
        prev = offset
        for addr, chunk in fp.iter_program_chunks(offset, data):
            assert addr == prev
            assert 0 < len(chunk) <= 58
            assert addr // 256 == (addr + len(chunk) - 1) // 256
            prev = addr + len(chunk)
        assert prev == offset + len(data)
