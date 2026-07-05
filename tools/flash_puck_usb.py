#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""flash_puck_usb.py -- fast, reliable, libusb-ONLY gale puck (re)flash + boot verify.

Self-contained single file. Dependencies: pyusb only (plus futility/cbfstool
binaries and the dev keys for the build step, added in a later phase). It talks
to the Google Wifi ("gale") debug device 18d1:500f entirely over libusb:

    interface 0 = EC command console   (park the AP, sysinfo, reboot)
    interface 1 = AP console           (boot-log capture + watchdog)
    interface 3 = usb_spi V1 bridge     (SPI-NOR read/erase/program)

There is NO pyserial and NO /dev/ttyUSB dependency: all three interfaces are
driven from one shared libusb device handle in one process.

Design rules (non-negotiable):
  * FAIL LOUD, NO RETRIES. Every USB transfer / SPI status / verify is checked;
    any anomaly raises FatalError immediately with full diagnostics. The
    hardware is reliable -- a fault here is a bug in this code, never "flaky
    hardware", so we surface it instead of papering over it.
  * The AP shares the SPI bus, so it MUST be parked before any bridge op, and an
    independent watchdog kills the process on ANY AP byte during SPI work.
  * Writes are dry-run by default; --commit is required to erase/program.

This phase implements the libusb core (console + SPI bridge + park/session) and
a non-destructive `shakedown` that proves, on real hardware, the two riskiest
new things before any real flash:
    1. concurrency: EC+AP+SPI held simultaneously on one libusb handle while the
       AP-reader thread loops and SPI streams;
    2. the write path: RW_LEGACY (0x700000, above the RO guard) block+sector
       erase -> program -> verify -> restore byte-identical.
"""
import argparse
import os
import struct
import sys
import time

import usb.core
import usb.util

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
USB_VID, USB_PID = 0x18D1, 0x500F
IF_EC, IF_AP, IF_SPI = 0, 1, 3
SPI_EP_OUT, SPI_EP_IN = 0x03, 0x83
IFACE_CLASS, IFACE_SUBCLASS_GOOGLE_SPI, IFACE_PROTOCOL_V1 = 0xFF, 0x51, 0x01

MAX_WRITE = MAX_READ = 62            # usb_spi V1 payload ceiling
READ_CHUNK = MAX_READ
PROGRAM_CHUNK = MAX_WRITE - 4        # 58: opcode + 3 addr + <=58 data
USB_TIMEOUT_MS = 2000               # > EC 800 ms SPI ceiling & 1600 ms watchdog

FLASH_SIZE = 8 * 1024 * 1024
PAGE_SIZE = 256
SECTOR_SIZE = 0x1000                 # 4 KiB
BLOCK_SIZE = 0x10000                 # 64 KiB
RO_GUARD_LIMIT = 0x400000
RDID_EXPECT = bytes.fromhex("ef4017")

OP_READ, OP_WREN = 0x03, 0x06
OP_SECTOR_ERASE, OP_BLOCK_ERASE, OP_PAGE_PROGRAM = 0x20, 0xD8, 0x02
OP_RDID, OP_RDSR1, OP_RDSR2 = 0x9F, 0x05, 0x35
SR1_WIP, SR1_WEL, SR1_BP, SR1_TB, SR1_SRP0 = 0x01, 0x02, 0x1C, 0x20, 0x80

SECTOR_ERASE_DEADLINE_S = 3.0        # W25Q64 4K: typ 45 ms, max 400 ms
BLOCK_ERASE_DEADLINE_S = 4.0         # W25Q64 64K: typ 150 ms, max 2000 ms
PROGRAM_DEADLINE_S = 1.0             # page program: typ 0.7 ms, max 3 ms
EC_CMD_DEADLINE_S = 5.0
PARK_DEADLINE_S = 3.0
POST_PARK_QUIET_S = 2.0
POST_PARK_MAX_S = 20.0

EC_PROMPT = b"> "

STATUS_NAMES = {
    0x0000: "SUCCESS", 0x0001: "SPI_TIMEOUT", 0x0002: "BUSY",
    0x0003: "WRITE_COUNT_INVALID", 0x0004: "READ_COUNT_INVALID",
    0x0005: "BRIDGE_DISABLED",
}


class FatalError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def status_name(status):
    if status in STATUS_NAMES:
        return STATUS_NAMES[status]
    if status & 0x8000:
        return "EC_ERROR(0x%04x)" % (status & 0x7FFF)
    return "UNKNOWN(0x%04x)" % status


def is_usb_timeout(e):
    if isinstance(getattr(e, "errno", None), int) and e.errno == 110:
        return True
    s = str(e).lower()
    return "timeout" in s or "timed out" in s


def is_usb_nodev(e):
    if isinstance(getattr(e, "errno", None), int) and e.errno == 19:
        return True
    s = str(e).lower()
    return "no such device" in s or "no device" in s


def hexs(data):
    return " ".join("%02x" % b for b in data)


def addr3(addr):
    return bytes([(addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF])


def info(msg):
    print(msg, flush=True)


class Log:
    def __init__(self, path):
        self.f = open(os.path.expanduser(path), "a") if path else None
        self.t0 = time.monotonic()
        if self.f:
            self.log("LOG", "opened pid %d argv %r" % (os.getpid(), sys.argv))

    def log(self, tag, msg):
        if not self.f:
            return
        rel = time.monotonic() - self.t0
        for line in str(msg).split("\n"):
            self.f.write("%+11.4f %-10s %s\n" % (rel, tag, line))
        self.f.flush()

    def close(self):
        if self.f:
            self.log("LOG", "closed")
            self.f.close()
            self.f = None


# --------------------------------------------------------------------------- #
# Shared libusb device
# --------------------------------------------------------------------------- #
def open_device(log):
    """Find and return the one shared 18d1:500f handle. Never set_configuration
    (leave the kernel's config intact); interfaces are claimed individually."""
    dev = usb.core.find(idVendor=USB_VID, idProduct=USB_PID)
    if dev is None:
        raise FatalError("USB device %04x:%04x not found (SuzyQ attached?)"
                         % (USB_VID, USB_PID))
    log.log("USB", "device bus %d addr %d" % (dev.bus, dev.address))
    return dev


def _detach_and_claim(dev, ifnum, log):
    try:
        if dev.is_kernel_driver_active(ifnum):
            dev.detach_kernel_driver(ifnum)
            log.log("USB", "detached kernel driver from if%d" % ifnum)
    except NotImplementedError:
        pass
    usb.util.claim_interface(dev, ifnum)
    log.log("USB", "claimed if%d" % ifnum)


def _bulk_endpoints(intf):
    ep_in = ep_out = None
    for ep in intf:
        if usb.util.endpoint_type(ep.bmAttributes) != usb.util.ENDPOINT_TYPE_BULK:
            continue
        if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
            ep_in = ep_in or ep
        else:
            ep_out = ep_out or ep
    return ep_in, ep_out


# --------------------------------------------------------------------------- #
# EC / AP console over libusb (raw bulk streams; no baud/DTR)
# --------------------------------------------------------------------------- #
class Console:
    """One gale debug console (EC=if0 or AP=if1) over libusb bulk transfers."""

    def __init__(self, dev, which, log):
        self.dev = dev
        self.which = which
        self.ifnum = IF_EC if which == "ec" else IF_AP
        self.log = log
        cfg = dev.get_active_configuration()
        intf = usb.util.find_descriptor(
            cfg, custom_match=lambda i: i.bInterfaceNumber == self.ifnum
            and i.bAlternateSetting == 0)
        if intf is None:
            raise FatalError("interface %d (%s console) not present" % (self.ifnum, which))
        self.ep_in, self.ep_out = _bulk_endpoints(intf)
        if self.ep_in is None or self.ep_out is None:
            raise FatalError("interface %d has no bulk IN+OUT pair" % self.ifnum)
        _detach_and_claim(dev, self.ifnum, log)
        # Reset the bulk-endpoint DATA0/DATA1 toggle: re-claiming an interface
        # whose kernel driver was NOT just detached (a repeated run) leaves a
        # stale toggle, so the device's prompt bytes get silently dropped and the
        # console desyncs. clear_halt resyncs it to a known state.
        for ep in (self.ep_in, self.ep_out):
            try:
                dev.clear_halt(ep.bEndpointAddress)
            except usb.core.USBError as e:
                self.log.log("USB", "clear_halt if%d ep 0x%02x: %s (continuing)"
                             % (self.ifnum, ep.bEndpointAddress, e))
        # Flush any bytes the device buffered from a prior session.
        self.drain(idle_ms=50, max_ms=500)
        self.log.log("EC" if which == "ec" else "AP",
                     "%s console: bulk IN 0x%02x OUT 0x%02x on if%d"
                     % (which, self.ep_in.bEndpointAddress,
                        self.ep_out.bEndpointAddress, self.ifnum))

    def read(self, timeout_ms=200, size=64):
        try:
            data = self.ep_in.read(size, timeout=max(1, int(timeout_ms)))
        except usb.core.USBError as e:
            if is_usb_timeout(e):
                return b""
            raise
        return bytes(data)

    def write(self, data):
        n = self.ep_out.write(bytes(data), timeout=USB_TIMEOUT_MS)
        if n != len(data):
            raise FatalError("short console write: %d of %d" % (n, len(data)))

    def drain(self, idle_ms=30, max_ms=800):
        end = time.monotonic() + max_ms / 1000.0
        got = bytearray()
        while time.monotonic() < end:
            chunk = self.read(idle_ms)
            if not chunk:
                break
            got += chunk
        return bytes(got)

    def sync(self):
        """Send a newline and read to a clean, quiet '> ' prompt, clearing any
        stale/desynced bytes (from a prior session, or a kernel-driver probe
        after we detach/re-claim the interface). Fails loud if no prompt."""
        self.write(b"\r\n")
        end = time.monotonic() + EC_CMD_DEADLINE_S
        buf = bytearray()
        last = time.monotonic()
        while time.monotonic() < end:
            chunk = self.read(200)
            if chunk:
                buf += chunk
                last = time.monotonic()
            elif EC_PROMPT in buf and time.monotonic() - last > 0.2:
                self.log.log("EC", "sync -> %r" % bytes(buf))
                return
        raise FatalError("EC console sync: no quiet prompt within %.1fs; got %r"
                         % (EC_CMD_DEADLINE_S, bytes(buf)))

    def cmd(self, command, until=None, deadline_s=EC_CMD_DEADLINE_S, require=True):
        """Send `command` exactly ONCE, then read its response (never re-send).

        Completion: with `until` (a predicate on the accumulated decoded text)
        the read is retried until the predicate holds; otherwise the '> ' prompt
        has appeared and the stream has gone quiet. Fails loud if `require` and
        the response never completes -- no silent short reads."""
        self.drain()
        self.write(command.encode() + b"\r\n")
        buf = bytearray()
        matched = False
        end = time.monotonic() + deadline_s
        while time.monotonic() < end:
            chunk = self.read(200)
            if chunk:
                buf += chunk
            text = buf.decode("latin1", "replace")
            if until is not None:
                if until(text):
                    matched = True
                    break
            elif not chunk and EC_PROMPT in buf:
                matched = True
                break
        text = buf.decode("latin1", "replace")
        self.log.log("EC", "cmd %r -> matched=%s %r" % (command, matched, text))
        if require and not matched:
            raise FatalError("EC console: no complete response to %r within %.1fs; got %r"
                             % (command, deadline_s, text))
        return text

    def release(self):
        try:
            usb.util.release_interface(self.dev, self.ifnum)
        except usb.core.USBError:
            pass


def has_flags_line(text):
    i = text.find("Flags:")
    return i >= 0 and "\n" in text[i:]


def has_ok_line(text):
    return any(line.strip() == "OK" for line in text.splitlines())


def parse_flags_line(text):
    for line in text.splitlines():
        if line.strip().startswith("Flags:"):
            return line.strip()
    raise FatalError("EC sysinfo has no Flags line: %r" % text)


# NOTE: there is deliberately NO AP watchdog THREAD. The AP console (if1) and
# the SPI bridge (if3) share ONE libusb context; a concurrent reader thread
# doing blocking bulk-reads on if1 serializes on libusb's event loop and
# intermittently stalls SPI transactions to their full 2000 ms timeout (a hard
# failure) and even desyncs the EC console -- measured on real hardware
# 2026-07-06. Reliable design: the AP is guarded INLINE from the SPI thread
# (SpiBridge.abort_check, wired to Session._ap_abort_check): every abort_every
# transactions the same thread polls if1 once; any byte aborts loud. Single-
# threaded => zero context contention => reliable, and an AP wake is still caught
# within abort_every txns (~0.1 s).


# --------------------------------------------------------------------------- #
# SPI bridge (usb_spi V1) over libusb -- fail loud, no retries
# --------------------------------------------------------------------------- #
class SpiBridge:
    def __init__(self, dev, log):
        self.dev = dev
        self.log = log
        self.txn = 0
        self.rtts = []
        self.abort_check = None      # callable(txn); polled inline every abort_every
        self.abort_every = 512
        cfg = dev.get_active_configuration()
        intf = usb.util.find_descriptor(
            cfg, custom_match=lambda i: i.bInterfaceNumber == IF_SPI
            and i.bAlternateSetting == 0)
        if intf is None:
            raise FatalError("usb_spi interface %d not present" % IF_SPI)
        if (intf.bInterfaceClass, intf.bInterfaceSubClass, intf.bInterfaceProtocol) \
                != (IFACE_CLASS, IFACE_SUBCLASS_GOOGLE_SPI, IFACE_PROTOCOL_V1):
            raise FatalError("if%d is not a V1 Google usb_spi interface" % IF_SPI)
        eps = sorted(ep.bEndpointAddress for ep in intf)
        if eps != [SPI_EP_OUT, SPI_EP_IN]:
            raise FatalError("unexpected usb_spi endpoints %s" % ["0x%02x" % e for e in eps])
        _detach_and_claim(dev, IF_SPI, log)

    def _ctrl(self, brequest, name, tolerate=False):
        self.log.log("CTRL", "bReq=%d (%s) wValue=0 wIndex=%d" % (brequest, name, IF_SPI))
        try:
            self.dev.ctrl_transfer(0x41, brequest, 0x0000, IF_SPI, b"", USB_TIMEOUT_MS)
        except usb.core.USBError as e:
            if tolerate:
                self.log.log("CTRL", "%s tolerated: %s" % (name, e))
                return
            raise FatalError("%s control transfer failed: %s" % (name, e))

    def _drain(self):
        for _ in range(50):
            try:
                self.dev.read(SPI_EP_IN, 64, timeout=20)
            except usb.core.USBError:
                break

    def enable(self):
        self._ctrl(1, "DISABLE(self-heal)", tolerate=True)  # clear any wedged prior enable
        self._ctrl(0, "ENABLE")
        # usb_spi_board_enable raises SYS_PWR_EN + the 3.3V flash rail; give it a
        # moment to settle and drain any stale IN data before trusting RDID (the
        # proven raiden transport does the same -- otherwise a not-yet-stable rail
        # reads back as RDID 000000).
        time.sleep(0.1)
        self._drain()

    def disable(self):
        self._ctrl(1, "DISABLE")

    def emergency_disable(self):
        try:
            self.dev.ctrl_transfer(0x41, 1, 0x0000, IF_SPI, b"", 500)
        except Exception:  # noqa: BLE001 - best effort from watchdog
            pass

    def _bulk_fail(self, e, direction, txn, ctx, pkt):
        errno = getattr(e, "errno", None)
        if is_usb_nodev(e):
            kind = "ENODEV (device vanished -- EC watchdog MCU reset?)"
        elif is_usb_timeout(e):
            kind = "TIMEOUT (EC did not answer in %d ms and did not reboot)" % USB_TIMEOUT_MS
        else:
            kind = "STALL/pipe/other USB error"
        return FatalError("bulk %s FAILED at txn #%d (%s): %s [errno=%r] -- %s; "
                          "NOT retried. sent [%s]"
                          % (direction, txn, ctx, e, errno, kind, hexs(pkt)))

    def transact(self, wdata, rcount, context=""):
        """One usb_spi V1 transaction. Returns exactly `rcount` payload bytes.
        Fails loud on every abnormal outcome; no retries anywhere."""
        if not (0 <= len(wdata) <= MAX_WRITE) or not (0 <= rcount <= MAX_READ):
            raise FatalError("transaction size out of range wc=%d rc=%d (%s)"
                             % (len(wdata), rcount, context))
        self.txn += 1
        txn = self.txn
        if self.abort_check is not None and txn % self.abort_every == 0:
            self.abort_check(txn)   # inline AP guard (same thread, between txns)
        pkt = bytes([len(wdata), rcount]) + bytes(wdata)
        t0 = time.perf_counter()
        try:
            n = self.dev.write(SPI_EP_OUT, pkt, USB_TIMEOUT_MS)
        except usb.core.USBError as e:
            raise self._bulk_fail(e, "OUT", txn, context, pkt)
        if n != len(pkt):
            raise FatalError("short bulk OUT #%d (%s): %d/%d" % (txn, context, n, len(pkt)))
        try:
            resp = bytes(self.dev.read(SPI_EP_IN, 64, USB_TIMEOUT_MS))
        except usb.core.USBError as e:
            raise self._bulk_fail(e, "IN", txn, context, pkt)
        self.rtts.append(time.perf_counter() - t0)
        if len(resp) < 2:
            raise FatalError("bulk IN too short #%d (%s): %d bytes [%s]"
                             % (txn, context, len(resp), hexs(resp)))
        status = resp[0] | (resp[1] << 8)
        if status != 0:
            raise FatalError("usb_spi status %s at txn #%d (%s): sent [%s] resp [%s]"
                             % (status_name(status), txn, context, hexs(pkt), hexs(resp)))
        if len(resp) != 2 + rcount:
            raise FatalError("bulk IN length mismatch #%d (%s): got %d want %d"
                             % (txn, context, len(resp), 2 + rcount))
        return resp[2:]

    def release(self):
        try:
            usb.util.release_interface(self.dev, IF_SPI)
        except usb.core.USBError:
            pass

    def rtt_ms(self):
        if not self.rtts:
            return "no txns"
        r = sorted(self.rtts)
        return ("%d txns rtt min/med/p99/max = %.3f/%.3f/%.3f/%.3f ms"
                % (len(r), r[0]*1e3, r[len(r)//2]*1e3,
                   r[min(len(r)-1, int(len(r)*0.99))]*1e3, r[-1]*1e3))


def check_rdid(bridge):
    got = bridge.transact([OP_RDID], 3, context="RDID")
    if got != RDID_EXPECT:
        raise FatalError("RDID %s != %s (bridge not ready / wrong chip / framing)"
                         % (got.hex(), RDID_EXPECT.hex()))
    return got


def read_sr(bridge):
    sr1 = bridge.transact([OP_RDSR1], 1, context="RDSR1")[0]
    sr2 = bridge.transact([OP_RDSR2], 1, context="RDSR2")[0]
    return sr1, sr2


# --------------------------------------------------------------------------- #
# Flash read / erase / program
# --------------------------------------------------------------------------- #
def read_region(bridge, offset, length, label="read", progress=True):
    out = bytearray()
    addr, end = offset, offset + length
    t0 = last = time.monotonic()
    while addr < end:
        n = min(READ_CHUNK, end - addr)
        out += bridge.transact([OP_READ] + list(addr3(addr)), n,
                               context="%s@0x%06x" % (label, addr))
        addr += n
        now = time.monotonic()
        if progress and (now - last >= 1.0 or addr >= end):
            done = addr - offset
            info("%s: 0x%06x/0x%06x %5.1f%%  %.3f MiB/s  txn=%d"
                 % (label, addr, end, 100.0*done/length,
                    done/max(now-t0, 1e-9)/(1024*1024), bridge.txn))
            last = now
    return bytes(out)


def erase_plan(offset, length):
    """List of (addr, size, opcode): 64 KiB block-erase where the range covers a
    full aligned block, else 4 KiB sector-erase. Requires 4 KiB alignment."""
    if offset % SECTOR_SIZE or length % SECTOR_SIZE:
        raise FatalError("erase range not 4 KiB aligned: 0x%x+0x%x" % (offset, length))
    plan = []
    addr, end = offset, offset + length
    while addr < end:
        if addr % BLOCK_SIZE == 0 and end - addr >= BLOCK_SIZE:
            plan.append((addr, BLOCK_SIZE, OP_BLOCK_ERASE))
            addr += BLOCK_SIZE
        else:
            plan.append((addr, SECTOR_SIZE, OP_SECTOR_ERASE))
            addr += SECTOR_SIZE
    return plan


def iter_program_chunks(offset, data):
    i = 0
    while i < len(data):
        addr = offset + i
        n = min(PROGRAM_CHUNK, PAGE_SIZE - (addr % PAGE_SIZE), len(data) - i)
        yield addr, data[i:i + n]
        i += n


def wait_wip_clear(bridge, deadline_s, context):
    end = time.monotonic() + deadline_s
    polls = 0
    while True:
        sr1 = bridge.transact([OP_RDSR1], 1, context="RDSR1 %s" % context)[0]
        polls += 1
        if not (sr1 & SR1_WIP):
            return polls
        if time.monotonic() > end:
            raise FatalError("WIP still set %.1fs after %s (%d polls, SR1=0x%02x)"
                             % (deadline_s, context, polls, sr1))


def write_region(bridge, offset, data, log, verify=True):
    """Erase (64 KiB blocks + 4 KiB tail) -> program (page-bounded) -> read-back
    verify vs source. Every step fails loud; the block/sector erase is spot-
    checked for the 0xff transition so a blocked (no-op) erase can't slip by."""
    length = len(data)
    sr1, sr2 = read_sr(bridge)
    if sr1 & (SR1_BP | SR1_TB):
        raise FatalError("refusing to write: block-protect set SR1=0x%02x" % sr1)

    plan = erase_plan(offset, length)
    nblk = sum(1 for _, s, _ in plan if s == BLOCK_SIZE)
    nsec = len(plan) - nblk
    info("erase: %d x 64K blocks + %d x 4K sectors (0x%06x..0x%06x)"
         % (nblk, nsec, offset, offset + length))
    t0 = time.monotonic()
    for addr, size, op in plan:
        deadline = BLOCK_ERASE_DEADLINE_S if size == BLOCK_SIZE else SECTOR_ERASE_DEADLINE_S
        kind = "block" if size == BLOCK_SIZE else "sector"
        bridge.transact([OP_WREN], 0, context="WREN erase@0x%06x" % addr)
        wel = read_sr(bridge)[0]
        if not (wel & SR1_WEL):
            raise FatalError("WREN did not latch WEL before %s erase@0x%06x "
                             "(SR1=0x%02x) -- erase would no-op" % (kind, addr, wel))
        bridge.transact([op] + list(addr3(addr)), 0, context="ERASE@0x%06x" % addr)
        wait_wip_clear(bridge, deadline, "erase@0x%06x" % addr)
        head = bridge.transact([OP_READ] + list(addr3(addr)), READ_CHUNK,
                               context="erasecheck@0x%06x" % addr)
        if any(b != 0xFF for b in head):
            # Distinguish a genuine no-op from AP-bus contention: re-probe RDID
            # and re-read. RDID != ef4017 or a 0x00 re-read => the flash is not
            # responding to US (AP woke and is driving the bus); RDID ok with the
            # head unchanged => the erase truly no-op'd (protect/WEL).
            rdid = bridge.transact([OP_RDID], 3, context="diag-rdid@0x%06x" % addr)
            sr1d, sr2d = read_sr(bridge)
            head2 = bridge.transact([OP_READ] + list(addr3(addr)), READ_CHUNK,
                                    context="diag-reread@0x%06x" % addr)
            if rdid != RDID_EXPECT:
                cause = ("flash UNRESPONSIVE (RDID=%s != ef4017) -- AP woke and is "
                         "contending the SPI bus" % rdid.hex())
            else:
                cause = ("flash RESPONDS (RDID ok) -- erase truly no-op'd (protect/WEL)")
            raise FatalError("ERASE NO-OP at 0x%06x (%s): head[0]=0x%02x reread[0]=0x%02x "
                             "SR1=0x%02x(WEL=%d) SR2=0x%02x; %s"
                             % (addr, kind, head[0], head2[0], sr1d,
                                (sr1d >> 1) & 1, sr2d, cause))
    erase_s = time.monotonic() - t0
    info("erase: done %.1fs" % erase_s)

    chunks = list(iter_program_chunks(offset, data))
    info("program: %d bytes in %d chunks" % (length, len(chunks)))
    t0 = time.monotonic()
    for addr, chunk in chunks:
        bridge.transact([OP_WREN], 0, context="WREN pp@0x%06x" % addr)
        bridge.transact([OP_PAGE_PROGRAM] + list(addr3(addr)) + list(chunk), 0,
                        context="PP@0x%06x" % addr)
        wait_wip_clear(bridge, PROGRAM_DEADLINE_S, "pp@0x%06x" % addr)
    program_s = time.monotonic() - t0
    info("program: done %.1fs" % program_s)

    timings = {"erase_s": erase_s, "program_s": program_s}
    if not verify:
        return timings
    t0 = time.monotonic()
    readback = read_region(bridge, offset, length, label="verify")
    timings["verify_s"] = time.monotonic() - t0
    if readback != data:
        for i, (a, b) in enumerate(zip(readback, data)):
            if a != b:
                raise FatalError("VERIFY FAILED at 0x%06x: source 0x%02x flash 0x%02x"
                                 % (offset + i, b, a))
        raise FatalError("VERIFY FAILED: length mismatch %d vs %d" % (len(readback), length))
    info("verify: read-back matches source")
    return timings


# --------------------------------------------------------------------------- #
# Sessioned read/write -- the bridge silently no-ops operations past a per-
# ENABLE-session transaction budget (WREN stops latching WEL; reads return
# 0x00). Measured on this rig 2026-07-06: ~1330 txns, and VARIABLE day to day.
# A fresh in-process session (teardown + bring_up) resets it (proven: WREN
# latches again at txn 4 after a reopen). So every multi-KiB operation is split
# into fresh-session pieces sized to stay well under the budget.
# --------------------------------------------------------------------------- #
READ_PIECE = 0x8000     # 32 KiB/read-session (~528 txns) -- safe margin
WRITE_PIECE = 0x2000    # 8 KiB/write-session (~570 txns): well under the ~1330
#                         budget, and HALF the session churn of 4 KiB (rapid
#                         dispose/reopen/ENABLE cycles stress the EC into slow
#                         responses + bulk timeouts).


def read_region_sessioned(new_session, offset, length, log, piece=READ_PIECE,
                          label="read"):
    out = bytearray()
    done = 0
    for po in range(offset, offset + length, piece):
        plen = min(piece, offset + length - po)
        sess = new_session()
        try:
            out += read_region(sess.bridge, po, plen, label=label, progress=False)
        finally:
            sess.teardown()
        done += plen
        info("%s: 0x%06x/0x%06x %3.0f%%" % (label, po + plen, offset + length,
                                            100.0 * done / length))
    return bytes(out)


def flash_region(new_session, offset, data, log, piece=WRITE_PIECE, verify=True):
    """Erase+program+verify `data` at `offset`, one fresh session per `piece`."""
    n = len(data)
    if offset % SECTOR_SIZE or n % SECTOR_SIZE:
        raise FatalError("flash_region 0x%x+0x%x not 4 KiB aligned" % (offset, n))
    done = 0
    for po in range(offset, offset + n, piece):
        plen = min(piece, offset + n - po)
        pdata = data[po - offset:po - offset + plen]
        sess = new_session()
        try:
            write_region(sess.bridge, po, pdata, log, verify=verify)
        finally:
            sess.teardown()
        done += plen
        info("flash: 0x%06x/0x%06x %3.0f%% (%d B piece, per-piece verified)"
             % (po + plen, offset + n, 100.0 * done / n, plen))


# --------------------------------------------------------------------------- #
# Boot verification -- classification (pure); the EC-reboot + AP capture that
# feeds it is added with the flash orchestration and validated on hardware.
# Markers are from real 2712HW0072Z captures (see fleet/galeflash/bootverify.py):
# a GOOD normal-mode dev-key boot reaches depthcharge + netboot; EVERY boot
# prints "recovery" in a GPIO/vboot line, so a bare "recovery" is NOT a failure.
# --------------------------------------------------------------------------- #
BOOT_DEV_SIGNED = "This is developer signed firmware"
BOOT_GOOD_MARKERS = ("Starting depthcharge", "Sending DHCP discover", "TFTP")
BOOT_BAD_MARKERS = ("VB2:vb2_fail", "Need recovery", "Recovery requested",
                    "Entering recovery mode")


def boot_markers(text):
    return ([m for m in BOOT_GOOD_MARKERS if m in text],
            [m for m in BOOT_BAD_MARKERS if m in text])


def boot_decisive(text):
    good, bad = boot_markers(text)
    return bool(good or bad)


def boot_slot(text):
    last = None
    for name in ("A", "B"):
        idx = text.rfind("FW_MAIN_%s found" % name)
        if idx >= 0 and (last is None or idx > last[1]):
            last = (name, idx)
    return last[0] if last else None


def boot_classify(text):
    """Verdict GOOD|BAD|UNDECIDED. Any BAD marker wins (a recovery boot can still
    print a depthcharge banner)."""
    good, bad = boot_markers(text)
    verdict = "BAD" if bad else ("GOOD" if good else "UNDECIDED")
    return {"verdict": verdict, "good": good, "bad": bad,
            "dev_signed": BOOT_DEV_SIGNED in text, "slot": boot_slot(text)}


# --------------------------------------------------------------------------- #
# Session: park the AP over libusb, enable the bridge
# --------------------------------------------------------------------------- #
class Session:
    def __init__(self, log):
        self.log = log
        self.dev = None
        self.ec = None
        self.ap = None
        self.bridge = None

    def _ap_abort_check(self, txn):
        """Inline AP guard: one tiny if1 read; any byte means the AP woke and can
        contend the SPI bus, so abort loud (after a best-effort bridge DISABLE)."""
        d = self.ap.read(2)
        if d:
            if self.bridge:
                self.bridge.emergency_disable()
            raise FatalError("AP EMITTED %d bytes during SPI at txn #%d -- the AP "
                             "woke and can contend the bus; aborting: %s"
                             % (len(d), txn, hexs(d[:32])))

    def bring_up(self):
        log = self.log
        self.dev = open_device(log)
        self.ec = Console(self.dev, "ec", log)
        self.ap = Console(self.dev, "ap", log)

        self.ec.sync()   # clean prompt baseline before the first command
        flags = parse_flags_line(self.ec.cmd("sysinfo", until=has_flags_line))
        info("EC state: %s" % flags)
        if "unlocked" not in flags:
            raise FatalError("EC is %r, not unlocked -- park needs an unlocked EC; "
                             "reboot the EC first" % flags)

        park = self.ec.cmd("gale power off", until=has_ok_line,
                           deadline_s=PARK_DEADLINE_S, require=False)
        if not has_ok_line(park):
            raise FatalError("park not acknowledged: 'gale power off' produced no OK "
                             "within %.1fs: %r" % (PARK_DEADLINE_S, park))
        info("parked: 'gale power off' acknowledged with OK")

        # A parked AP must fall silent; capture any power-down tail.
        end = time.monotonic() + POST_PARK_MAX_S
        last = time.monotonic()
        tail = bytearray()
        while time.monotonic() < end:
            d = self.ap.read(200)
            if d:
                tail += d
                last = time.monotonic()
            elif time.monotonic() - last >= POST_PARK_QUIET_S:
                break
        else:
            raise FatalError("AP still emitting %.0fs after park (%d bytes) -- not parked"
                             % (POST_PARK_MAX_S, len(tail)))
        info("AP quiet after park (%d bytes tail)" % len(tail))

        self.bridge = SpiBridge(self.dev, log)
        self.bridge.enable()
        rdid = check_rdid(self.bridge)
        self.bridge.abort_check = self._ap_abort_check   # single-threaded AP guard
        info("bridge enabled; RDID %s (inline AP guard every %d txns)"
             % (rdid.hex(), self.bridge.abort_every))
        return self

    def teardown(self):
        # Fail-SAFE: teardown must never raise, or it masks the real error that
        # brought us here (a raising bridge.disable() would replace e.g. a
        # VERIFY FAILED with a generic "DISABLE failed"). Best-effort only.
        try:
            if self.bridge:
                self.bridge.emergency_disable()   # 500 ms, swallows errors
                self.bridge.release()
        finally:
            for c in (self.ec, self.ap):
                if c:
                    c.release()
            if self.dev:
                # Deliberately do NOT reattach the console kernel drivers: a
                # reattached ttyUSB gets probed by ModemManager/getty, which
                # desyncs the EC console before the next run re-claims it. The
                # real flow re-enumerates via the final EC reboot, which restores
                # the tty nodes cleanly.
                usb.util.dispose_resources(self.dev)


# --------------------------------------------------------------------------- #
# shakedown: non-destructive hardware validation of concurrency + write path
# --------------------------------------------------------------------------- #
SESSION_SETTLE_S = 1.0   # let the EC/USB settle between fresh ENABLE sessions;
#                          disposing the device then immediately re-opening +
#                          re-ENABLE races the EC (control-transfer timeout).


def make_session_factory(log, abort_every):
    """Return a callable that yields a fresh, brought-up Session -- each fresh
    ENABLE resets the bridge's per-session transaction budget."""
    state = {"first": True}

    def new_session():
        if not state["first"]:
            time.sleep(SESSION_SETTLE_S)
        state["first"] = False
        s = Session(log)
        try:
            s.bring_up()
        except BaseException:
            s.teardown()
            raise
        s.bridge.abort_every = abort_every
        return s
    return new_session


def cmd_shakedown(args, log):
    new_session = make_session_factory(log, args.abort_every)
    ok = False
    try:
        # 1) bring-up + SPI reliability in one fresh session
        info("== 1/2 reliability: %d SPI reads, single-threaded, inline AP guard =="
             % args.spins)
        s = new_session()
        try:
            t0 = time.monotonic()
            for _ in range(args.spins):
                check_rdid(s.bridge)
            info("SPI stream OK: %d RDID in %.1fs, %s"
                 % (args.spins, time.monotonic() - t0, s.bridge.rtt_ms()))
        finally:
            s.teardown()

        off, ln = args.offset, args.length
        if off < RO_GUARD_LIMIT:
            raise FatalError("shakedown scratch 0x%06x is below the RO guard 0x%06x"
                             % (off, RO_GUARD_LIMIT))
        info("\n== 2/2 write path (fresh session per %d B): 0x%06x..0x%06x =="
             % (WRITE_PIECE, off, off + ln))
        orig = read_region_sessioned(new_session, off, ln, log, label="save-orig")
        info("saved original (%d bytes, %s)"
             % (len(orig), "all-0xff" if orig == b"\xff" * ln else "non-blank -> restore"))
        if not args.commit:
            info("DRY-RUN: would erase/program a test pattern then restore, one fresh "
                 "session per %d B. Pass --commit to exercise the write path." % WRITE_PIECE)
            ok = True
            return 0

        t0 = time.monotonic()
        pattern = bytes((0xA5 ^ (i & 0xFF)) for i in range(ln))
        info("-- programming test pattern --")
        flash_region(new_session, off, pattern, log)      # per-piece erase+program+verify
        info("-- restoring original --")
        flash_region(new_session, off, orig, log)
        info("-- independent read-back confirm --")
        confirm = read_region_sessioned(new_session, off, ln, log, label="confirm")
        if confirm != orig:
            raise FatalError("RESTORE FAILED: region not byte-identical to original")
        info("\nWRITE PATH OK on real hardware: erase+program+verify across fresh "
             "sessions, region restored byte-identical (%.1fs)." % (time.monotonic() - t0))
        ok = True
        return 0
    finally:
        if not ok:
            info("shakedown ABORTED (fail-loud).")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--log", metavar="FILE", help="append a full operation log")
    sub = p.add_subparsers(dest="command", required=True)

    sd = sub.add_parser("shakedown", help="non-destructive libusb concurrency + write-path test")
    sd.add_argument("--spins", type=int, default=2000, help="SPI reads during concurrency test")
    sd.add_argument("--offset", type=lambda s: int(s, 0), default=0x700000,
                    help="scratch region offset (RW_LEGACY, above the RO guard)")
    sd.add_argument("--length", type=lambda s: int(s, 0), default=0x11000,
                    help="scratch length (default 0x11000 = 1 block + 1 sector)")
    sd.add_argument("--commit", action="store_true",
                    help="actually erase/program/restore the scratch region")
    sd.add_argument("--abort-every", type=int, default=512,
                    help="inline AP-guard poll interval, in SPI transactions")

    args = p.parse_args(argv)
    log = Log(args.log)
    try:
        return cmd_shakedown(args, log)
    except FatalError as e:
        log.log("FATAL", str(e))
        print("FATAL: %s" % e, file=sys.stderr, flush=True)
        return 1
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
