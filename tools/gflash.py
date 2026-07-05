#!/usr/bin/env python3
"""
gflash.py -- standalone SPI flash read/write tool for the Google Wifi "gale"
boot flash (Winbond W25Q64, 8 MiB), accessed through the gale debug EC's
usb_spi bridge (USB 18d1:500f, interface 3, protocol V1).

Protocol V1, verified against the EC source (chip/stm32/usb_spi.{c,h} on the
gale firmware branch):

  Control transfer (to interface 3):
    bmRequestType 0x41 (OUT | VENDOR | INTERFACE), wValue = 0, wIndex = 3,
    wLength = 0.  bRequest 0 = ENABLE, 1 = DISABLE.  The EC STALLs malformed
    requests and requests made while the device side is disabled.

  Bulk transaction (OUT ep 0x03 / IN ep 0x83, 64-byte max packets):
    OUT: [write_count:u8][read_count:u8][write payload, exactly write_count B]
    IN:  [status:u16 LE][read payload, exactly read_count B]
    write_count <= 62, read_count <= 62.  The IN packet is always
    read_count + 2 bytes long, even when status != 0.
    status: 0 = ok, 1 = SPI timeout, 2 = busy, 3 = write count invalid,
    4 = read count invalid, 5 = bridge disabled, 0x8000|code = EC error.

Flash: Winbond W25Q64 (RDID 0x9F -> ef 40 17), 8 MiB, 4 KiB erase sectors,
256 B program pages.  READ 0x03 (24-bit BE addr), WREN 0x06, sector erase
0x20, page program 0x02, RDSR1 0x05 (WIP = bit 0).

Fail-loud policy: any unexpected event aborts immediately with full context
(what was sent, what came back, transaction number, flash offset, errno/status)
and a non-zero exit.  There are NO retries in the transaction path.  At the
2000 ms per-transfer deadline -- above the EC's 800 ms SPI ceiling (which yields
a *completed* USB_SPI_TIMEOUT status) and its 1600 ms watchdog (which yields
ENODEV) -- no benign transient survives to our layer (the host controller
retries NAKs below us), so a bulk STALL/ENODEV/ETIMEDOUT/overflow, a nonzero
completed status, a short/over-long transfer, an RDID mismatch, or a park not
acknowledged with "OK" are all real and fail loud on the spot.

Data-integrity note: the READ path additionally double-reads and, where two
full passes disagree, targeted-re-reads until they agree -- this is a DIFFERENT
mechanism from a transport retry.  It detects and LOGS a known, non-destructive
read glitch (silent 0x00-for-0xff) by comparison and confirms the correct bytes
by agreement; it surfaces rather than hides, and the final image is verified.

The AP watchdog is a fully independent thread: on ANY byte from the AP console
it logs the bytes, issues a best-effort bridge DISABLE, and os._exit()s the
whole process.  The SPI read/write/erase/program path has ZERO awareness of it
and simply runs with a generous per-transfer timeout.
"""

import argparse
import datetime
import hashlib
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

import serial
import usb.core
import usb.util

# ---------------------------------------------------------------------------
# Constants (all facts verified against EC sources / the live device).

USB_VID = 0x18D1
USB_PID = 0x500F
SPI_INTERFACE = 3
EP_OUT = 0x03
EP_IN = 0x83
IFACE_CLASS = 0xFF  # vendor specific
IFACE_SUBCLASS_GOOGLE_SPI = 0x51
IFACE_PROTOCOL_V1 = 0x01

MAX_WRITE = 62  # bytes of SPI write payload per transaction
MAX_READ = 62  # bytes of SPI read payload per transaction

FLASH_SIZE = 8 * 1024 * 1024
SECTOR_SIZE = 4096
PAGE_SIZE = 256
RDID_EXPECT = bytes.fromhex("ef4017")

OP_READ = 0x03
OP_WREN = 0x06
OP_SECTOR_ERASE = 0x20
OP_PAGE_PROGRAM = 0x02
OP_RDSR1 = 0x05
OP_RDSR2 = 0x35
SR1_WIP = 0x01
SR1_WEL = 0x02  # write enable latch
# W25Q64 SR1 block-protect / status-register-protect bits that, when set, make
# erase/program silently no-op instead of erroring.
SR1_BP = 0x1C  # BP0..BP2
SR1_TB = 0x20  # top/bottom
SR1_SRP0 = 0x80
SR2_SRP1 = 0x01

# Boot-critical lower half (bootblock / RO / RW section slots start below this).
# Writes below this are refused unless --allow-ro is given.
RO_GUARD_LIMIT = 0x400000

# Backup-image data validation.
FMAP_SIGNATURE = b"__FMAP__"
FMAP_EXPECTED_OFFSET = 0x300000
# Structural sanity bounds used to reject a SPURIOUS 8-byte "__FMAP__" match
# (a coincidence inside CBFS/compressed data) from being parsed as the real
# FMAP.  gale's real FMAP has 24 areas and a declared total of 0x800000; the
# spurious hit observed at 0x0453fb had 11876 areas and total ~1.85 GB.
FMAP_MAX_AREAS = 255
FMAP_MAX_TOTAL = 0x10000000  # 256 MiB: larger than any plausible SPI flash
GPT_SIGNATURE = b"EFI PART"
VPD_MAGIC = b"gVpdInfo"
# Region names actually present in gale's FMAP (parsed from the dump, not
# hardcoded into logic).  GPT lives in RW_GPT_PRIMARY (a cached copy of the eMMC
# GPT, but still a valid GPT with CRC32s); there is no region literally "RW_GPT".
GPT_REGION_NAMES = ("RW_GPT_PRIMARY", "RW_GPT")
VPD_REGION_NAMES = ("RO_VPD", "RW_VPD")
# futility built for aarch64 on the rig (const.FUTILITY); falls back to PATH.
FUTILITY_DEFAULT = (
    "/home/tim/local/gwifi/depthcharge-ipq4019/vboot_reference/build/futility/futility"
)

# READ transaction: opcode + 3 addr bytes leaves this much read payload room.
# (write payload and read count are independent 62-byte budgets in V1, so a
# READ can return the full 62 bytes.)
READ_CHUNK = MAX_READ
# PAGE PROGRAM: opcode + 3 addr bytes share the 62-byte write budget.
PROGRAM_CHUNK = MAX_WRITE - 4  # 58

EC_TTY = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
AP_TTY = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if01-port0"
BAUD = 115200

# 2000 ms per bulk/control transfer.  Chosen to exceed BOTH of the EC's internal
# ceilings so a slow-but-completing transaction is never falsely cut off:
# SPI_TRANSACTION_TIMEOUT_USEC = 800 ms (the EC's own SPI-DMA wait) and
# CONFIG_WATCHDOG_PERIOD_MS = 1600 ms (EC self-reset if the HOOKS task wedges).
# A completed txn returns the instant the EC's TX endpoint goes VALID (~0.5 ms),
# so the high ceiling costs nothing in the common case; a real 2000 ms ETIMEDOUT
# then means the EC neither answered nor reset within its own longest window.
USB_TIMEOUT_MS = 2000
EC_CMD_DEADLINE_S = 5.0  # per EC console command (write -> prompt)
PARK_DEADLINE_S = 3.0  # 'gale power off' -> 'OK' line
REPAIR_READS = 7  # targeted re-reads of a differing sub-range before giving up
REENUM_GONE_DEADLINE_S = 15.0  # EC reboot -> USB device disappears
REENUM_BACK_DEADLINE_S = 30.0  # USB device (both ttys) reappears
AP_FIRST_BYTE_DEADLINE_S = 45.0  # AP boots on its own after EC reboot
AP_BOOT_OBSERVE_S = 3.0  # observation window of early AP boot output
POST_PARK_QUIET_S = 2.0  # AP console must be silent this long after park
POST_PARK_MAX_S = 20.0  # ... within this budget, else the park failed
ERASE_DEADLINE_S = 3.0  # W25Q64 4K sector erase: typ 45ms, max 400ms
PROGRAM_DEADLINE_S = 1.0  # W25Q64 page program: typ 0.7ms, max 3ms

OTHER_USERS_PATTERN = "chunk_read|flash_one_puck|raiden|flashrom|gflash"

STATUS_NAMES = {
    0x0000: "SUCCESS",
    0x0001: "SPI_TIMEOUT",
    0x0002: "BUSY",
    0x0003: "WRITE_COUNT_INVALID",
    0x0004: "READ_COUNT_INVALID",
    0x0005: "BRIDGE_DISABLED",
}


def status_name(status):
    if status in STATUS_NAMES:
        return STATUS_NAMES[status]
    if status & 0x8000:
        return "EC_ERROR(0x%04x)" % (status & 0x7FFF)
    return "UNKNOWN(0x%04x)" % status


class FatalError(Exception):
    pass


def is_usb_timeout(e):
    """True if a USBError is a transfer TIMEOUT (Errno 110, ETIMEDOUT) -- the
    case where NO data crossed for that transfer.  Distinct from STALL/pipe/
    other USB errors, which are NOT retried."""
    if isinstance(getattr(e, "errno", None), int) and e.errno == 110:
        return True
    s = str(e).lower()
    return "timeout" in s or "timed out" in s


def is_usb_nodev(e):
    """True if a USBError is ENODEV (Errno 19) / 'no such device' -- the device
    disappeared.  In our system this is the signature of the EC's 1600 ms
    watchdog resetting the MCU (it then re-enumerates and the AP boots), which is
    a distinct condition from a plain transfer timeout."""
    if isinstance(getattr(e, "errno", None), int) and e.errno == 19:
        return True
    s = str(e).lower()
    return "no such device" in s or "no device" in s


def hexs(data):
    return " ".join("%02x" % b for b in data)


def hexdump(data):
    """hexdump -C style: offset, 16 hex bytes, ascii."""
    lines = []
    for off in range(0, len(data), 16):
        row = data[off : off + 16]
        hx = " ".join("%02x" % b for b in row)
        asc = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in row)
        lines.append("%08x  %-47s  |%s|" % (off, hx, asc))
    return "\n".join(lines) if lines else "(empty)"


# ---------------------------------------------------------------------------
# Logging: every operation, timestamped.  Completeness beats compactness.


class Log:
    def __init__(self, path):
        self.f = None
        self.t0 = time.monotonic()
        if path:
            self.f = open(os.path.expanduser(path), "a")
            self.log("LOG", "opened (pid %d, argv %r)" % (os.getpid(), sys.argv))

    def log(self, tag, msg):
        if not self.f:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        stamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        rel = time.monotonic() - self.t0
        for line in str(msg).split("\n"):
            self.f.write("%s %+11.4f %-12s %s\n" % (stamp, rel, tag, line))

    def flush(self):
        if self.f:
            self.f.flush()

    def close(self):
        if self.f:
            self.log("LOG", "closed")
            self.f.close()
            self.f = None


def info(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# EC command console (USB interface 0 tty).


class ECConsole:
    """Synchronous EC console.  Commands are terminated by the "> " prompt;
    asynchronous lines can arrive a few ms after the prompt, so completion is
    prompt-seen + line quiet (one serial timeout with no new data)."""

    def __init__(self, log):
        self.log = log
        self.ser = serial.Serial(EC_TTY, BAUD, timeout=0.2, exclusive=True)
        self.log.log("EC", "opened %s" % EC_TTY)
        stray = self.ser.read(4096)
        if stray:
            self.log.log("EC", "stray bytes at open (%dB):\n%s" % (len(stray), hexdump(stray)))

    def _read_until_prompt(self, what, deadline_s):
        buf = b""
        t_end = time.monotonic() + deadline_s
        while time.monotonic() < t_end:
            chunk = self.ser.read(4096)
            if chunk:
                buf += chunk
                continue
            # One full serial timeout with no data: line is quiet.
            if b"> " in buf:
                return buf
        raise FatalError(
            "EC console: no prompt within %.1fs after %r; received %d bytes:\n%s"
            % (deadline_s, what, len(buf), hexdump(buf))
        )

    def sync(self):
        self.ser.write(b"\n")
        buf = self._read_until_prompt("(sync newline)", EC_CMD_DEADLINE_S)
        self.log.log("EC", "sync -> %r" % buf)

    def cmd(self, command, deadline_s=EC_CMD_DEADLINE_S, until=None, require=True):
        """Send `command` exactly ONCE, then read its response.

        With `until` (a predicate on the accumulated decoded text) the response
        is re-READ until the predicate holds or the deadline elapses -- the
        command is never re-sent, only the read is retried, so this is safe even
        for a state-changing command (the write already happened).  This defends
        against a momentary short read / split line (e.g. sysinfo returning a
        bare prompt before its body arrives) without papering over a real
        anomaly: if `require` and the predicate never holds, it fails loud.

        Without `until`, completion is the generic "prompt seen and the line has
        gone quiet" heuristic."""
        stray = self.ser.read(4096)
        if stray:
            self.log.log("EC", "stray bytes before %r (%dB):\n%s" % (command, len(stray), hexdump(stray)))
        self.log.log("EC", "send: %r" % command)
        self.ser.write(command.encode() + b"\n")
        buf = b""
        matched = False
        t_end = time.monotonic() + deadline_s
        while time.monotonic() < t_end:
            chunk = self.ser.read(4096)
            if chunk:
                buf += chunk
            if until is not None:
                if until(buf.decode(errors="backslashreplace")):
                    matched = True
                    break
            elif not chunk and b"> " in buf:
                matched = True
                break
        text = buf.decode(errors="backslashreplace")
        self.log.log("EC", "recv (%dB, matched=%s): %r" % (len(buf), matched, text))
        if require and not matched:
            raise FatalError(
                "EC console: expected response to %r not seen within %.1fs; "
                "received %d bytes:\n%s" % (command, deadline_s, len(buf), hexdump(buf))
            )
        return text

    def send_reboot(self):
        """Send 'reboot' and close: the whole USB device re-enumerates."""
        self.log.log("EC", "send: 'reboot' (device will re-enumerate)")
        self.ser.write(b"reboot\n")
        t_end = time.monotonic() + 1.0
        buf = b""
        while time.monotonic() < t_end:
            try:
                chunk = self.ser.read(4096)
            except (serial.SerialException, OSError):
                break  # device already dropped
            buf += chunk
        self.log.log("EC", "reboot output: %r" % buf)
        self.close()

    def close(self):
        try:
            self.ser.close()
        except (serial.SerialException, OSError):
            pass
        self.log.log("EC", "closed")


_POWER_STATE_RE = re.compile(r"power\s*-\s*(on|off)\b")


def has_flags_line(text):
    """True once a complete (newline-terminated) 'Flags:' line has arrived."""
    i = text.find("Flags:")
    return i >= 0 and "\n" in text[i:]


def has_power_state(text):
    """True once a complete 'power - on|off' line has arrived."""
    m = _POWER_STATE_RE.search(text)
    return bool(m) and "\n" in text[m.end():]


def parse_flags_line(sysinfo_text):
    for line in sysinfo_text.splitlines():
        if line.strip().startswith("Flags:"):
            return line.strip()
    raise FatalError("EC sysinfo output has no 'Flags:' line:\n%r" % sysinfo_text)


def has_ok_line(text):
    return any(line.strip() == "OK" for line in text.splitlines())


def parse_power_state(text):
    """Parse '   power - on|off' from 'gale power' output (not the echo)."""
    for line in text.splitlines():
        s = line.strip()
        if s.endswith("- on") and "power" in s:
            return "on"
        if s.endswith("- off") and "power" in s:
            return "off"
    raise FatalError("EC 'gale power' output has no state line:\n%r" % text)


# ---------------------------------------------------------------------------
# AP console watchdog (USB interface 1 tty).


class APWatchdog(threading.Thread):
    """Fully independent AP-console guard thread.  It owns the (already open) AP
    console tty; on ANY byte arriving it logs the bytes (hex+ascii), issues a
    minimal best-effort bridge DISABLE, and tears the WHOLE process down with
    os._exit().  Nothing in the SPI read/write/erase/program path is aware of
    it: if the AP wakes mid-transaction, the process is killed out from under
    the SPI loop.  `bridge` is set by the caller once the Bridge exists (it may
    still be None if the AP wakes during early bring-up)."""

    def __init__(self, ser, log):
        super().__init__(name="ap-watchdog", daemon=True)
        self.ser = ser
        self.log = log
        self.bridge = None  # set by Session after the Bridge is created
        self._stop_req = threading.Event()

    def run(self):
        while not self._stop_req.is_set():
            try:
                data = self.ser.read(4096)
            except (serial.SerialException, OSError) as e:
                self._trip(b"", "AP console serial error: %s" % e)
                return
            if data:
                self._trip(bytes(data), None)
                return  # unreachable: _trip calls os._exit

    def _trip(self, data, note):
        detail = note or ("%d bytes on AP console:\n%s" % (len(data), hexdump(data)))
        self.log.log("AP-WATCHDOG", "TRIPPED (AP woke): %s" % detail)
        self.log.flush()
        # Minimal safe bridge DISABLE so we don't leave the bridge ENABLED for
        # the next run (best effort; must not raise).
        if self.bridge is not None:
            self.bridge.emergency_disable()
        self.log.log("AP-WATCHDOG", "os._exit(3) due to AP console activity")
        self.log.flush()
        sys.stderr.write(
            "FATAL: AP console watchdog tripped -- the AP woke during a SPI "
            "operation; aborting the whole process. See --log for the bytes.\n"
        )
        sys.stderr.flush()
        os._exit(3)

    def stop(self):
        self._stop_req.set()
        self.join(2.0)


# ---------------------------------------------------------------------------
# usb_spi bridge (protocol V1).


class Bridge:
    def __init__(self, log):
        self.log = log
        self.txn = 0  # count of transactions issued (also the fail-loud txn id)
        self.rtts = []

        dev = usb.core.find(idVendor=USB_VID, idProduct=USB_PID)
        if dev is None:
            raise FatalError("USB device %04x:%04x not found" % (USB_VID, USB_PID))
        self.dev = dev
        cfg = dev.get_active_configuration()
        intf = usb.util.find_descriptor(
            cfg,
            custom_match=lambda i: i.bInterfaceNumber == SPI_INTERFACE
            and i.bAlternateSetting == 0,
        )
        if intf is None:
            raise FatalError(
                "USB interface %d not found in active configuration" % SPI_INTERFACE
            )
        eps = sorted(ep.bEndpointAddress for ep in intf)
        desc = (
            "iface %d: class 0x%02x subclass 0x%02x protocol 0x%02x endpoints %s"
            % (
                intf.bInterfaceNumber,
                intf.bInterfaceClass,
                intf.bInterfaceSubClass,
                intf.bInterfaceProtocol,
                ["0x%02x" % e for e in eps],
            )
        )
        self.log.log("USB", "device bus %d addr %d; %s" % (dev.bus, dev.address, desc))
        if (
            intf.bInterfaceClass != IFACE_CLASS
            or intf.bInterfaceSubClass != IFACE_SUBCLASS_GOOGLE_SPI
            or intf.bInterfaceProtocol != IFACE_PROTOCOL_V1
        ):
            raise FatalError("not a V1 Google usb_spi interface: %s" % desc)
        if eps != [EP_OUT, EP_IN]:
            raise FatalError(
                "unexpected endpoints on interface %d: %s (want [0x%02x, 0x%02x])"
                % (SPI_INTERFACE, ["0x%02x" % e for e in eps], EP_OUT, EP_IN)
            )
        if dev.is_kernel_driver_active(SPI_INTERFACE):
            raise FatalError(
                "a kernel driver is bound to usb_spi interface %d; refusing" % SPI_INTERFACE
            )
        usb.util.claim_interface(dev, SPI_INTERFACE)
        self.log.log("USB", "claimed interface %d" % SPI_INTERFACE)

    def _ctrl(self, brequest, name, tolerate=False):
        # V1 convention (verified against the EC usb_spi_interface source):
        # bRequest selects ENABLE(0)/DISABLE(1); wValue MUST be 0 -- the EC
        # STALLs any nonzero wValue.
        self.log.log(
            "CTRL",
            "bmRequestType=0x41 bRequest=%d (%s) wValue=0 wIndex=%d wLength=0"
            % (brequest, name, SPI_INTERFACE),
        )
        try:
            n = self.dev.ctrl_transfer(0x41, brequest, 0x0000, SPI_INTERFACE, b"", USB_TIMEOUT_MS)
        except usb.core.USBError as e:
            if tolerate:
                self.log.log("CTRL", "%s tolerated error: %s" % (name, e))
                return
            raise FatalError(
                "%s control transfer failed: %s "
                "(the EC STALLs this if the request is malformed or the "
                "device-side bridge is disabled)" % (name, e)
            )
        self.log.log("CTRL", "%s ok (returned %r)" % (name, n))

    def enable(self):
        # Startup self-heal: ALWAYS DISABLE before ENABLE, so an unclean prior
        # exit (a killed process, or the AP watchdog's os._exit) that left the
        # bridge host-enabled cannot wedge this run.  A well-formed DISABLE never
        # STALLs; tolerate any error defensively.
        self._ctrl(1, "DISABLE(self-heal)", tolerate=True)
        self._ctrl(0, "ENABLE")

    def disable(self):
        self._ctrl(1, "DISABLE")

    def emergency_disable(self):
        """Best-effort DISABLE issued by the AP watchdog thread just before it
        os._exit()s the process.  Runs concurrently with the main thread's bulk
        transfers and must never raise."""
        try:
            self.dev.ctrl_transfer(0x41, 1, 0x0000, SPI_INTERFACE, b"", 500)
            self.log.log("USB", "emergency DISABLE (AP watchdog) ok")
        except Exception as e:  # noqa: BLE001 - best effort
            self.log.log("USB", "emergency DISABLE (AP watchdog) failed: %r" % e)

    def _bulk_fail(self, e, direction, txn, context, pkt):
        """Classify a bulk-transfer USBError into a fail-loud FatalError.

        At USB_TIMEOUT_MS (2000 ms > the EC's 800 ms SPI ceiling and 1600 ms
        watchdog) there is NO benign transient left at our layer: the host
        controller retries NAKs below us, so anything that reaches here is real.
        Every case fails loud immediately -- no retries."""
        errno = getattr(e, "errno", None)
        sent = hexs(pkt)
        if is_usb_nodev(e):
            return FatalError(
                "bulk %s ENODEV at txn #%d (%s): %s (errno=%r) -- the device "
                "disappeared: signature of the EC's 1600 ms watchdog resetting "
                "the MCU (it re-enumerates and the AP boots). Sent [%s]"
                % (direction, txn, context, e, errno, sent)
            )
        if is_usb_timeout(e):
            return FatalError(
                "bulk %s TIMEOUT at txn #%d (%s): %s (errno=%r) -- the EC did not "
                "answer within %d ms and did not reboot. A live EC completes in "
                "<1 ms, returns a completed USB_SPI_TIMEOUT status by 800 ms, or "
                "is watchdog-rebooted by 1600 ms; a %d ms bulk timeout is a real "
                "anomaly and is NOT retried. Sent [%s]"
                % (direction, txn, context, e, errno, USB_TIMEOUT_MS, USB_TIMEOUT_MS, sent)
            )
        return FatalError(
            "bulk %s failed at txn #%d (%s): %s (errno=%r) -- STALL/pipe/overflow/"
            "other USB error; not retried. Sent [%s]"
            % (direction, txn, context, e, errno, sent)
        )

    def transact(self, wdata, rcount, context=""):
        """One V1 transaction: bulk OUT then bulk IN.  Returns read payload.

        NO retries.  Every abnormal outcome fails loud immediately with full
        diagnostics (txn #, context/offset, direction, bytes sent, errno/status):
          * completed, status == 0            -> return payload.
          * completed, status != 0            -> fail loud (incl. USB_SPI_TIMEOUT
                                                 0x0001, a completed EC-side SPI
                                                 timeout -- a real anomaly).
          * USBError ENODEV / ETIMEDOUT / STALL / overflow / other -> fail loud,
                                                 with a direction-specific message.
          * short OUT, short/over-long IN      -> fail loud.
        At the 2000 ms deadline no benign transient survives to this layer (the
        host controller retries NAKs below us), so any retry here would paper
        over a real error -- and re-issuing into a fragile mid-fault EC is
        actively harmful.

        This method contains ZERO awareness of the AP watchdog: the watchdog is a
        fully independent thread that os._exit()s the whole process if the AP
        wakes, so the SPI loop just runs with a generous per-transfer timeout."""
        if not (0 <= len(wdata) <= MAX_WRITE) or not (0 <= rcount <= MAX_READ):
            raise FatalError(
                "internal bug: transaction size out of range (wc=%d rc=%d, %s)"
                % (len(wdata), rcount, context)
            )
        self.txn += 1
        txn = self.txn
        pkt = bytes([len(wdata), rcount]) + bytes(wdata)
        self.log.log("SPI-OUT", "#%06d %s wc=%d rc=%d data: %s" % (txn, context, len(wdata), rcount, hexs(pkt)))
        t0 = time.perf_counter()

        # --- bulk OUT: fail loud on any error, no retry ---
        try:
            n = self.dev.write(EP_OUT, pkt, USB_TIMEOUT_MS)
        except usb.core.USBError as e:
            raise self._bulk_fail(e, "OUT", txn, context, pkt)
        if n != len(pkt):
            raise FatalError(
                "short bulk OUT at txn #%d (%s): wrote %d of %d bytes [%s]"
                % (txn, context, n, len(pkt), hexs(pkt))
            )

        # --- bulk IN: fail loud on any error, no retry ---
        try:
            resp = bytes(self.dev.read(EP_IN, 64, USB_TIMEOUT_MS))
        except usb.core.USBError as e:
            raise self._bulk_fail(e, "IN", txn, context, pkt)
        rtt = time.perf_counter() - t0
        self.rtts.append(rtt)
        if len(resp) < 2:
            raise FatalError(
                "bulk IN too short at txn #%d (%s): got %d bytes [%s], sent [%s]"
                % (txn, context, len(resp), hexs(resp), hexs(pkt))
            )
        status = resp[0] | (resp[1] << 8)
        self.log.log(
            "SPI-IN",
            "#%06d %s status=0x%04x len=%d rtt=%.3fms data: %s"
            % (txn, context, status, len(resp), rtt * 1e3, hexs(resp[2:])),
        )
        if status != 0:
            raise FatalError(
                "usb_spi status %s at txn #%d (%s): sent [%s], response [%s]"
                % (status_name(status), txn, context, hexs(pkt), hexs(resp))
            )
        if len(resp) != 2 + rcount:
            raise FatalError(
                "bulk IN length mismatch at txn #%d (%s): expected %d (=2+%d) bytes, "
                "got %d: sent [%s], response [%s]"
                % (txn, context, 2 + rcount, rcount, len(resp), hexs(pkt), hexs(resp))
            )
        return resp[2:]

    def release(self):
        try:
            usb.util.release_interface(self.dev, SPI_INTERFACE)
            self.log.log("USB", "released interface %d" % SPI_INTERFACE)
        finally:
            usb.util.dispose_resources(self.dev)

    def rtt_summary(self):
        if not self.rtts:
            return "no transactions"
        r = sorted(self.rtts)
        return (
            "%d txns, rtt min/median/mean/p99/max = %.3f/%.3f/%.3f/%.3f/%.3f ms"
            % (
                len(r),
                r[0] * 1e3,
                statistics.median(r) * 1e3,
                statistics.fmean(r) * 1e3,
                r[min(len(r) - 1, int(len(r) * 0.99))] * 1e3,
                r[-1] * 1e3,
            )
        )


# ---------------------------------------------------------------------------
# Flash operations.


def addr3(addr):
    return bytes([(addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF])


def check_rdid(bridge):
    got = bridge.transact(bytes([0x9F]), 3, context="RDID")
    if got != RDID_EXPECT:
        raise FatalError(
            "RDID mismatch: expected %s (W25Q64), got %s" % (RDID_EXPECT.hex(), got.hex())
        )
    info("RDID ok: %s (W25Q64)" % got.hex())


def read_region(bridge, offset, length, label="read"):
    """Tight synchronous stream of READ transactions.  Returns bytes."""
    out = bytearray()
    addr = offset
    end = offset + length
    t0 = time.monotonic()
    last_print = t0
    while addr < end:
        n = min(READ_CHUNK, end - addr)
        payload = bridge.transact(
            bytes([OP_READ]) + addr3(addr), n, context="%s@0x%06x" % (label, addr)
        )
        out += payload
        addr += n
        now = time.monotonic()
        if now - last_print >= 1.0 or addr >= end:
            done = addr - offset
            rate = done / max(now - t0, 1e-9)
            eta = (end - addr) / max(rate, 1e-9)
            info(
                "%s: 0x%06x/0x%06x %6.2f%%  %.3f MiB/s  ETA %4ds  txn=%d"
                % (label, addr, end, 100.0 * done / length, rate / (1024 * 1024), int(eta), bridge.txn)
            )
            last_print = now
    return bytes(out)


def diff_runs(a, b):
    """Return contiguous [lo, hi) index runs where byte strings a and b differ."""
    if len(a) != len(b):
        raise FatalError("diff_runs length mismatch: %d vs %d" % (len(a), len(b)))
    runs = []
    n = len(a)
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i + 1
            while j < n and a[j] != b[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def repair_run(bridge, region_offset, lo, hi):
    """Establish ground truth for a differing sub-range by targeted re-reads.

    Re-reads flash bytes [region_offset+lo, region_offset+hi) up to REPAIR_READS
    times and returns the first value that two reads agree on.  Only ever called
    on ranges where the two full passes already disagreed, so correct data is
    never touched.  If no two re-reads agree the range is genuinely unstable and
    we fail loud rather than guess."""
    abs_lo = region_offset + lo
    length = hi - lo
    seen = []
    for attempt in range(1, REPAIR_READS + 1):
        val = read_region(bridge, abs_lo, length, label="repair@0x%06x" % abs_lo)
        for prev_i, prev in seen:
            if prev == val:
                bridge.log.log(
                    "REPAIR",
                    "0x%06x..0x%06x confirmed: re-reads #%d and #%d agree (%d bytes)"
                    % (abs_lo, abs_lo + length, prev_i, attempt, length),
                )
                return val
        seen.append((attempt, val))
    shas = ", ".join("#%d %s" % (i, hashlib.sha256(v).hexdigest()[:12]) for i, v in seen)
    raise FatalError(
        "repair failed for 0x%06x..0x%06x: %d re-reads and no two agree (%s)"
        % (abs_lo, abs_lo + length, REPAIR_READS, shas)
    )


def verified_read(bridge, offset, length, log):
    """Two full passes + targeted repair.  Returns (data, report_dict)."""
    info("verify: pass 1/2")
    pass1 = read_region(bridge, offset, length, label="pass1")
    info("verify: pass 2/2")
    pass2 = read_region(bridge, offset, length, label="pass2")
    runs = diff_runs(pass1, pass2)
    report = {
        "pass1_sha": hashlib.sha256(pass1).hexdigest(),
        "pass2_sha": hashlib.sha256(pass2).hexdigest(),
        "runs": [],
    }
    if not runs:
        info("verify: two full passes are byte-identical")
        return pass1, report
    total = sum(hi - lo for lo, hi in runs)
    info("verify: passes DISAGREE in %d run(s), %d bytes total; repairing" % (len(runs), total))
    log.log("VERIFY", "pass1 sha=%s pass2 sha=%s" % (report["pass1_sha"], report["pass2_sha"]))
    confirmed = bytearray(pass1)
    for lo, hi in runs:
        good = repair_run(bridge, offset, lo, hi)
        p1_wrong = pass1[lo:hi] != good
        p2_wrong = pass2[lo:hi] != good
        who = "+".join([w for w, bad in (("pass1", p1_wrong), ("pass2", p2_wrong)) if bad]) or "neither(?!)"
        info(
            "verify: 0x%06x..0x%06x (%d B) repaired; glitched: %s"
            % (offset + lo, offset + hi, hi - lo, who)
        )
        log.log(
            "VERIFY",
            "run 0x%06x..0x%06x len=%d pass1_wrong=%s pass2_wrong=%s"
            % (offset + lo, offset + hi, hi - lo, p1_wrong, p2_wrong),
        )
        report["runs"].append((offset + lo, offset + hi, p1_wrong, p2_wrong))
        confirmed[lo:hi] = good
    return bytes(confirmed), report


def wait_wip_clear(bridge, deadline_s, context):
    """Poll RDSR1 until WIP clears.  Polling the status register IS the
    flash's completion mechanism; the deadline bounds it."""
    t_end = time.monotonic() + deadline_s
    polls = 0
    while True:
        sr1 = bridge.transact(bytes([OP_RDSR1]), 1, context="RDSR1 %s" % context)[0]
        polls += 1
        if not (sr1 & SR1_WIP):
            return polls
        if time.monotonic() > t_end:
            raise FatalError(
                "flash still busy (WIP set) %.1fs after %s (%d polls, SR1=0x%02x)"
                % (deadline_s, context, polls, sr1)
            )


def iter_program_chunks(offset, data):
    """Yield (addr, chunk): <= 58 bytes, never crossing a 256 B page."""
    i = 0
    while i < len(data):
        addr = offset + i
        n = min(PROGRAM_CHUNK, PAGE_SIZE - (addr % PAGE_SIZE), len(data) - i)
        yield addr, data[i : i + n]
        i += n


def read_sr(bridge):
    """Return (sr1, sr2) status-register bytes."""
    sr1 = bridge.transact(bytes([OP_RDSR1]), 1, context="RDSR1")[0]
    sr2 = bridge.transact(bytes([OP_RDSR2]), 1, context="RDSR2")[0]
    return sr1, sr2


def describe_sr(sr1, sr2):
    bits = []
    if sr1 & SR1_BP:
        bits.append("BP=%d" % ((sr1 & SR1_BP) >> 2))
    if sr1 & SR1_TB:
        bits.append("TB")
    if sr1 & SR1_SRP0:
        bits.append("SRP0")
    if sr2 & SR2_SRP1:
        bits.append("SRP1")
    return "SR1=0x%02x SR2=0x%02x%s" % (sr1, sr2, (" [" + ",".join(bits) + "]") if bits else "")


def write_region(bridge, offset, data, log, verify=True):
    """Erase (4K sectors) + program (page-bounded) + confirmed read-back verify,
    all in the caller's single park+ENABLE session.  Returns a timings dict.

    Erase-block detection: if the block-protect / SRP bits make erase silently
    no-op, the erased sector will not read back as 0xff -- we spot-check the
    head of every sector right after its WIP clears and fail loud naming the SR
    state, rather than discovering it only at final verify."""
    length = len(data)
    nsectors = length // SECTOR_SIZE
    timings = {}

    # Guard: confirm the block-protect bits are clear before we start; a locked
    # SR would make every erase a silent no-op.
    sr1, sr2 = read_sr(bridge)
    log.log("WRITE", "pre-erase %s" % describe_sr(sr1, sr2))
    if sr1 & (SR1_BP | SR1_TB):
        raise FatalError(
            "refusing to write: block-protect bits set, erase would silently "
            "no-op (%s)" % describe_sr(sr1, sr2)
        )

    info("erase: %d sectors (0x%06x..0x%06x)" % (nsectors, offset, offset + length))
    t0 = time.monotonic()
    last_print = t0
    for i in range(nsectors):
        saddr = offset + i * SECTOR_SIZE
        bridge.transact(bytes([OP_WREN]), 0, context="WREN erase@0x%06x" % saddr)
        bridge.transact(
            bytes([OP_SECTOR_ERASE]) + addr3(saddr), 0, context="ERASE@0x%06x" % saddr
        )
        wait_wip_clear(bridge, ERASE_DEADLINE_S, "erase@0x%06x" % saddr)
        # Spot-check: the sector head must now be 0xff.  If not, erase no-oped.
        head = bridge.transact(
            bytes([OP_READ]) + addr3(saddr), READ_CHUNK, context="erasecheck@0x%06x" % saddr
        )
        if any(b != 0xFF for b in head):
            sr1, sr2 = read_sr(bridge)
            raise FatalError(
                "ERASE NO-OP at sector 0x%06x: head not 0xff after erase "
                "(first non-ff byte 0x%02x at +%d); %s -- erase appears blocked"
                % (saddr, next(b for b in head if b != 0xFF),
                   next(k for k, b in enumerate(head) if b != 0xFF), describe_sr(sr1, sr2))
            )
        now = time.monotonic()
        if now - last_print >= 1.0 or i == nsectors - 1:
            done = (i + 1) * SECTOR_SIZE
            rate = done / max(now - t0, 1e-9)
            eta = (nsectors - i - 1) * SECTOR_SIZE / max(rate, 1e-9)
            info(
                "erase: %d/%d sectors %6.2f%%  %.3f MiB/s  ETA %3ds"
                % (i + 1, nsectors, 100.0 * (i + 1) / nsectors, rate / (1024 * 1024), int(eta))
            )
            last_print = now
    timings["erase_s"] = time.monotonic() - t0
    info("erase: done in %.1fs (%.3f MiB/s)" % (timings["erase_s"], length / timings["erase_s"] / (1024 * 1024)))

    chunks = list(iter_program_chunks(offset, data))
    info("program: %d bytes in %d chunks" % (length, len(chunks)))
    t0 = time.monotonic()
    last_print = t0
    for ci, (addr, chunk) in enumerate(chunks):
        bridge.transact(bytes([OP_WREN]), 0, context="WREN pp@0x%06x" % addr)
        bridge.transact(
            bytes([OP_PAGE_PROGRAM]) + addr3(addr) + chunk, 0, context="PP@0x%06x" % addr
        )
        wait_wip_clear(bridge, PROGRAM_DEADLINE_S, "pp@0x%06x" % addr)
        now = time.monotonic()
        if now - last_print >= 1.0 or ci == len(chunks) - 1:
            done = addr + len(chunk) - offset
            rate = done / max(now - t0, 1e-9)
            eta = (length - done) / max(rate, 1e-9)
            info(
                "program: 0x%06x/0x%06x %6.2f%%  %.3f MiB/s  ETA %3ds"
                % (addr + len(chunk), offset + length, 100.0 * done / length,
                   rate / (1024 * 1024), int(eta))
            )
            last_print = now
    timings["program_s"] = time.monotonic() - t0
    info("program: done in %.1fs (%.3f MiB/s)" % (timings["program_s"], length / timings["program_s"] / (1024 * 1024)))

    if not verify:
        return timings

    # WRITE-VERIFY: we hold the source of truth (the bytes we just wrote), so a
    # SINGLE read-back compared byte-for-byte against the source is sufficient.
    # No double-read / repair, no RDID heuristic.  A read glitch that causes a
    # false mismatch simply fails loud; the operator re-runs (erase+program+
    # verify is idempotent and safe).
    info("verify: reading back once and comparing to source")
    t0 = time.monotonic()
    readback = read_region(bridge, offset, length, label="verify")
    timings["verify_s"] = time.monotonic() - t0
    if readback != data:
        runs = diff_runs(readback, data)
        first_lo = runs[0][0]
        runs_desc = ", ".join(
            "0x%06x..0x%06x (%dB)" % (offset + a, offset + b, b - a) for a, b in runs[:20]
        )
        raise FatalError(
            "VERIFY FAILED: read-back differs from source in %d run(s), %d bytes; "
            "first differing byte at 0x%06x (source wrote 0x%02x, flash read 0x%02x); "
            "runs: %s%s"
            % (
                len(runs),
                sum(b - a for a, b in runs),
                offset + first_lo,
                data[first_lo],
                readback[first_lo],
                runs_desc,
                " ..." if len(runs) > 20 else "",
            )
        )
    info("verify: ok, read-back matches source (%.1fs, %.3f MiB/s)"
         % (timings["verify_s"], length / timings["verify_s"] / (1024 * 1024)))
    return timings


# ---------------------------------------------------------------------------
# Backup-image data validation.
#
# A reference-less backup read has no source of truth to compare against, so
# read-twice-must-agree only filters TRANSIENT glitches.  It cannot catch a
# PERSISTENT brownout (both passes read the same zeros).  Real data validation
# closes that hole: a browned/corrupt region fails its checksum / crypto check.
# Every check fails loud on failure.


def _parse_fmap_at(data, i):
    """Parse an FMAP whose "__FMAP__" signature starts at byte offset i.

    Returns a dict, or None if the bytes there are NOT a structurally sane FMAP.
    The gate exists because an 8-byte "__FMAP__" coincidence can occur inside
    CBFS/compressed data BEFORE the real FMAP; a sane FMAP has a non-empty
    printable-ASCII name, a bounded area count, a plausible declared total, and
    every area lying within that total.  A spurious hit fails at least one."""
    off = i + len(FMAP_SIGNATURE)
    try:
        ver_major, ver_minor = data[off], data[off + 1]
        off += 2
        base = struct.unpack_from("<Q", data, off)[0]
        off += 8
        total = struct.unpack_from("<I", data, off)[0]
        off += 4
        name_raw = data[off : off + 32]
        off += 32
        nareas = struct.unpack_from("<H", data, off)[0]
        off += 2
    except struct.error:
        return None
    name = name_raw.split(b"\0")[0]
    if not name or any(b < 0x20 or b > 0x7E for b in name):
        return None
    if not (1 <= nareas <= FMAP_MAX_AREAS):
        return None
    if not (0 < total <= FMAP_MAX_TOTAL):
        return None
    areas = {}
    try:
        for _ in range(nareas):
            a_off, a_size = struct.unpack_from("<II", data, off)
            off += 8
            a_name = data[off : off + 32].split(b"\0")[0].decode("ascii", "replace")
            off += 32
            (a_flags,) = struct.unpack_from("<H", data, off)
            off += 2
            areas[a_name] = (a_off, a_size, a_flags)
    except struct.error:
        return None
    if any(a_off + a_size > total for a_off, a_size, _ in areas.values()):
        return None
    return {
        "fmap_offset": i,
        "version": (ver_major, ver_minor),
        "base": base,
        "size": total,
        "name": name.decode("ascii"),
        "areas": areas,
    }


def parse_fmap(data):
    """Locate and parse the coreboot FMAP.  Returns a dict or None.

    A spurious 8-byte "__FMAP__" match can PRECEDE the real FMAP (observed live
    2026-07-06: a hit at 0x0453fb with a non-printable name and 11876 areas
    shadowed the real FMAP at 0x300000, so validate_full_image silently skipped
    its GPT/VPD checks and reported "all passed").  So scan ALL matches, keep
    only the structurally sane ones, and prefer the one at the conventional
    offset over any earlier sane hit."""
    candidates = []
    start = 0
    while True:
        i = data.find(FMAP_SIGNATURE, start)
        if i < 0:
            break
        parsed = _parse_fmap_at(data, i)
        if parsed is not None:
            candidates.append(parsed)
        start = i + 1
    if not candidates:
        return None
    for c in candidates:
        if c["fmap_offset"] == FMAP_EXPECTED_OFFSET:
            return c
    return candidates[0]


def validate_gpt(region, log, label):
    """Validate a GPT's header CRC32 and partition-entry-array CRC32 (UEFI)."""
    i = region.find(GPT_SIGNATURE)
    if i < 0:
        raise FatalError("%s: no 'EFI PART' GPT header signature found" % label)
    if i + 92 > len(region):
        raise FatalError("%s: GPT header at +0x%x truncated" % (label, i))
    header_size = struct.unpack_from("<I", region, i + 12)[0]
    if not (92 <= header_size <= len(region) - i):
        raise FatalError("%s: implausible GPT header_size %d" % (label, header_size))
    stored_hdr_crc = struct.unpack_from("<I", region, i + 16)[0]
    tmp = bytearray(region[i : i + header_size])
    struct.pack_into("<I", tmp, 16, 0)  # zero header_crc32 field before CRC
    calc_hdr_crc = zlib.crc32(bytes(tmp)) & 0xFFFFFFFF
    log.log(
        "VALIDATE",
        "%s: GPT header @+0x%x size=%d stored_crc=0x%08x calc_crc=0x%08x"
        % (label, i, header_size, stored_hdr_crc, calc_hdr_crc),
    )
    if calc_hdr_crc != stored_hdr_crc:
        raise FatalError(
            "%s: GPT header CRC32 mismatch (stored 0x%08x, computed 0x%08x) -- "
            "header corrupt" % (label, stored_hdr_crc, calc_hdr_crc)
        )

    current_lba = struct.unpack_from("<Q", region, i + 24)[0]
    part_entry_lba = struct.unpack_from("<Q", region, i + 72)[0]
    num_entries = struct.unpack_from("<I", region, i + 80)[0]
    entry_size = struct.unpack_from("<I", region, i + 84)[0]
    stored_arr_crc = struct.unpack_from("<I", region, i + 88)[0]
    arr_len = num_entries * entry_size
    if arr_len <= 0 or arr_len > len(region):
        raise FatalError(
            "%s: implausible GPT entry array (%d entries x %d B)"
            % (label, num_entries, entry_size)
        )
    # The header records LBAs on a 512-byte-block virtual disk.  Locate the
    # entry array relative to the header we found; a corrupt array matches no
    # candidate and fails loud.
    candidates = []
    if part_entry_lba >= current_lba:
        candidates.append(i + (part_entry_lba - current_lba) * 512)
    candidates.append(i + 512)
    candidates.append(i + header_size)
    matched = None
    for c in candidates:
        if 0 <= c and c + arr_len <= len(region):
            if (zlib.crc32(region[c : c + arr_len]) & 0xFFFFFFFF) == stored_arr_crc:
                matched = c
                break
    if matched is None:
        raise FatalError(
            "%s: GPT partition-entry-array CRC32 mismatch (stored 0x%08x; %d "
            "entries x %d B; tried region offsets %s) -- entries corrupt"
            % (label, stored_arr_crc, num_entries, entry_size,
               ["0x%x" % c for c in candidates])
        )
    log.log(
        "VALIDATE",
        "%s: GPT entry-array CRC ok @+0x%x (%d entries x %d B, crc 0x%08x)"
        % (label, matched, num_entries, entry_size, stored_arr_crc),
    )


def validate_vpd(region, log, label):
    """Check the Google VPD 2.0 'gVpdInfo' header magic.  VPD 2.0's container
    header carries no whole-blob CRC we can validate here, so this is
    magic-only; it still catches a fully browned (all-0x00) VPD region."""
    i = region.find(VPD_MAGIC)
    if i < 0:
        raise FatalError(
            "%s: no 'gVpdInfo' VPD 2.0 magic found -- region blank/corrupt?" % label
        )
    size = struct.unpack_from("<I", region, i + 8)[0] if i + 12 <= len(region) else None
    log.log("VALIDATE", "%s: VPD 'gVpdInfo' magic @+0x%x payload_size=%s" % (label, i, size))
    info("validate: %s VPD 2.0 present (gVpdInfo, payload_size=%s) -- magic-only "
         "(container has no header CRC to check)" % (label, size))


def verify_vboot(data, log, futility_path=None, skip=False):
    """vboot FW_MAIN_A/B body verification via futility, matching identity.py's
    proven gate: run `futility show <image>` and treat a NONZERO EXIT as body-
    verification failure (a good dump prints 'Body verification succeeded'; a
    corrupt one exits 1 with 'Error verifying firmware body').  Uses the rig's
    aarch64 futility by default, falling back to PATH."""
    if skip:
        info("validate: vboot verification SKIPPED (--skip-vboot)")
        log.log("VALIDATE", "vboot skipped by flag")
        return
    fut = futility_path or FUTILITY_DEFAULT
    if not (fut and os.path.exists(fut)):
        fut = shutil.which("futility")
    if not fut:
        raise FatalError(
            "vboot verification requires 'futility'; not found at %s nor on PATH. "
            "Pass --futility PATH, or --skip-vboot to accept the dump WITHOUT vboot "
            "verification (not recommended for a trusted backup)."
            % (futility_path or FUTILITY_DEFAULT)
        )
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    try:
        log.log("VALIDATE", "running: %s show %s" % (fut, tmp))
        proc = subprocess.run([fut, "show", tmp], capture_output=True, text=True)
        log.log(
            "VALIDATE",
            "futility show rc=%d\nstdout:\n%s\nstderr:\n%s"
            % (proc.returncode, proc.stdout, proc.stderr),
        )
        if proc.returncode != 0:
            raise FatalError(
                "vboot body verification FAILED (futility show rc=%d):\n%s\n%s"
                % (proc.returncode, proc.stdout.strip(), proc.stderr.strip())
            )
        ok_marker = "Body verification succeeded" in (proc.stdout + proc.stderr)
        info("validate: vboot ok -- futility show exit 0%s (FW_MAIN_A/B body "
             "verified)" % (" ('Body verification succeeded')" if ok_marker else ""))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def validate_full_image(data, log, futility_path=None, skip_vboot=False):
    """Data-integrity checks on a full-chip backup, driven off the dump's OWN
    parsed FMAP (region names are not hardcoded).  Validate whichever
    load-bearing regions are present; fail loud on any check that fails."""
    if len(data) != FLASH_SIZE:
        raise FatalError(
            "validate: expected a full %d-byte image, got %d" % (FLASH_SIZE, len(data))
        )
    info("validate: data-integrity checks on the backup image")
    fmap = parse_fmap(data)
    if fmap is None:
        raise FatalError("validate: no __FMAP__ signature found in the image")
    foff = fmap["fmap_offset"]
    areas = fmap["areas"]
    info("validate: FMAP '%s' at 0x%06x (%d areas)" % (fmap["name"], foff, len(areas)))
    log.log("VALIDATE", "FMAP areas: %s" % ", ".join(sorted(areas)))
    if foff != FMAP_EXPECTED_OFFSET:
        info("validate: NOTE FMAP at 0x%06x, expected 0x%06x" % (foff, FMAP_EXPECTED_OFFSET))

    def region(name):
        o, s, _ = areas[name]
        if o + s > len(data):
            raise FatalError("validate: '%s' area 0x%x+0x%x exceeds image" % (name, o, s))
        return data[o : o + s]

    # Strongest first: vboot FW_MAIN_A/B (~2.7 MiB cryptographically covered),
    # verified against the whole image via futility.
    verify_vboot(data, log, futility_path=futility_path, skip=skip_vboot)

    # GPT: RW_GPT_PRIMARY (cached copy of the eMMC GPT).  A full-chip gale image
    # MUST contain it; its absence means the selected FMAP is wrong or the dump
    # is corrupt -- fail loud rather than silently skip (a silent skip once
    # masked a spurious-FMAP parse as "all checks passed").
    gpt_name = next((n for n in GPT_REGION_NAMES if n in areas), None)
    if not gpt_name:
        raise FatalError(
            "validate: FMAP '%s' at 0x%06x has no %s region -- a full-chip gale "
            "image must contain a GPT region; the FMAP is wrong or the dump is "
            "corrupt (areas: %s)"
            % (fmap["name"], foff, "/".join(GPT_REGION_NAMES), ", ".join(sorted(areas)))
        )
    gpt_region = region(gpt_name)
    if gpt_region == b"\xff" * len(gpt_region):
        # A netboot gale's cached-GPT region is legitimately erased (verified:
        # pristine stock 2712HW0072Z reads 0xff across RW_GPT).  Blank is OK;
        # only a NON-blank region must hold a valid GPT, else it is corrupt.
        info("validate: %s is blank (erased) -- no cached GPT to validate "
             "(normal for a netboot gale)" % gpt_name)
        log.log("VALIDATE", "%s all-0xff (blank); GPT content check N/A" % gpt_name)
    else:
        validate_gpt(gpt_region, log, gpt_name)

    # VPD magic (RO and, if present, RW).  RO_VPD is likewise mandatory.
    vpd_names = [vn for vn in VPD_REGION_NAMES if vn in areas]
    if not vpd_names:
        raise FatalError(
            "validate: FMAP '%s' at 0x%06x has no %s region -- a full-chip gale "
            "image must contain VPD; the FMAP is wrong or the dump is corrupt"
            % (fmap["name"], foff, "/".join(VPD_REGION_NAMES))
        )
    for vn in vpd_names:
        validate_vpd(region(vn), log, vn)

    info("validate: all applicable data-integrity checks passed")


# ---------------------------------------------------------------------------
# Device preparation: exclusive access, EC state, park, watchdog, bridge.


def check_no_other_users(log):
    proc = subprocess.run(
        ["pgrep", "-af", OTHER_USERS_PATTERN], capture_output=True, text=True
    )
    lines = []
    for line in proc.stdout.splitlines():
        pid = int(line.split(None, 1)[0])
        # Exclude ourselves and the shell that launched us (its cmdline
        # contains our own command line and so matches the pattern).
        if pid in (os.getpid(), os.getppid()):
            continue
        lines.append(line)
    log.log("PRECHECK", "pgrep -af %r ->\n%s" % (OTHER_USERS_PATTERN, "\n".join(lines) or "(nothing)"))
    if lines:
        raise FatalError(
            "other processes may be using the bridge; refusing to start:\n%s"
            % "\n".join(lines)
        )


def wait_path(path, present, deadline_s, what):
    t_end = time.monotonic() + deadline_s
    while time.monotonic() < t_end:
        if os.path.exists(path) == present:
            return
        time.sleep(0.05)
    raise FatalError(
        "%s: %s did not %s within %.0fs"
        % (what, path, "appear" if present else "disappear", deadline_s)
    )


def drain_ap_until_quiet(ap_ser, log, quiet_s, max_s, tag):
    """Read the AP console until it has been silent for quiet_s (a parked AP
    must be silent).  Everything received is logged.  Returns bytes seen."""
    total = b""
    t_end = time.monotonic() + max_s
    last_data = time.monotonic()
    while time.monotonic() < t_end:
        chunk = ap_ser.read(4096)
        if chunk:
            total += chunk
            last_data = time.monotonic()
        elif time.monotonic() - last_data >= quiet_s:
            break
    else:
        log.log(tag, "still emitting after %.0fs (%dB):\n%s" % (max_s, len(total), hexdump(total)))
        raise FatalError(
            "AP console still emitting %.0fs after park (%d bytes; see log)"
            % (max_s, len(total))
        )
    if total:
        log.log(tag, "%d bytes before quiet:\n%s" % (len(total), hexdump(total)))
    else:
        log.log(tag, "silent")
    return total


class Session:
    """Prepared device: EC console open, AP parked, watchdog armed, bridge
    enabled and RDID-verified."""

    def __init__(self, log):
        self.log = log
        self.ec = None
        self.ap_ser = None
        self.watchdog = None
        self.bridge = None

    def prepare(self):
        log = self.log
        check_no_other_users(log)

        self.ec = ECConsole(log)
        self.ec.sync()
        flags = parse_flags_line(self.ec.cmd("sysinfo", until=has_flags_line))
        info("EC state: %s" % flags)

        if "unlocked" not in flags:
            # Locked: the only way to an acknowledged park is an EC reboot
            # (which re-enumerates USB and lets the AP boot on its own).
            info("EC is locked; rebooting EC to reach a parkable state")
            self.ec.send_reboot()
            self.ec = None
            wait_path(EC_TTY, False, REENUM_GONE_DEADLINE_S, "EC reboot")
            info("USB device dropped; waiting for re-enumeration")
            wait_path(EC_TTY, True, REENUM_BACK_DEADLINE_S, "re-enumeration (EC tty)")
            wait_path(AP_TTY, True, REENUM_BACK_DEADLINE_S, "re-enumeration (AP tty)")
            log.log("REENUM", "both ttys back")
            info("re-enumerated; waiting for AP boot output (ground truth)")

            self.ap_ser = serial.Serial(AP_TTY, BAUD, timeout=0.2, exclusive=True)
            log.log("AP", "opened %s" % AP_TTY)
            t_end = time.monotonic() + AP_FIRST_BYTE_DEADLINE_S
            first = b""
            while time.monotonic() < t_end:
                first = self.ap_ser.read(4096)
                if first:
                    break
            if not first:
                raise FatalError(
                    "no AP console output within %.0fs of EC reboot; "
                    "cannot confirm the AP booted" % AP_FIRST_BYTE_DEADLINE_S
                )
            log.log("AP-BOOT", "first %d bytes:\n%s" % (len(first), hexdump(first)))
            info("AP is booting (%d bytes seen); observing %.1fs" % (len(first), AP_BOOT_OBSERVE_S))
            # Observation window: capture early boot output and give the EC's
            # write-protect input (which follows the AP 3.3V rail) time to
            # reflect the running state.  The park's required "OK" ack below
            # is the actual gate.
            t_end = time.monotonic() + AP_BOOT_OBSERVE_S
            boot = b""
            while time.monotonic() < t_end:
                boot += self.ap_ser.read(4096)
            log.log("AP-BOOT", "observation window %d bytes:\n%s" % (len(boot), hexdump(boot)))

            self.ec = ECConsole(log)
            self.ec.sync()
            flags = parse_flags_line(self.ec.cmd("sysinfo", until=has_flags_line))
            info("EC state after reboot: %s" % flags)
        else:
            self.ap_ser = serial.Serial(AP_TTY, BAUD, timeout=0.2, exclusive=True)
            log.log("AP", "opened %s" % AP_TTY)

        # Park the AP.  A set is required, so the "OK" ack is required: a locked
        # EC silently prints state and does nothing.  Sent once; we read until
        # the OK line arrives (it may follow the prompt by a few ms) or the
        # deadline -- absence of OK within the deadline means "not acknowledged".
        park = self.ec.cmd(
            "gale power off", deadline_s=PARK_DEADLINE_S, until=has_ok_line, require=False
        )
        if not has_ok_line(park):
            raise FatalError(
                "park not acknowledged: 'gale power off' produced no 'OK' line "
                "within %.1fs (EC flags were %r); a locked EC silently ignores "
                "the set. Response:\n%r" % (PARK_DEADLINE_S, flags, park)
            )
        info("parked: 'gale power off' acknowledged with OK")

        # A parked AP must be silent; capture any power-down tail first.
        drain_ap_until_quiet(
            self.ap_ser, self.log, POST_PARK_QUIET_S, POST_PARK_MAX_S, "AP-POSTPARK"
        )

        # Confirm EC state.
        flags = parse_flags_line(self.ec.cmd("sysinfo", until=has_flags_line))
        info("EC state after park: %s" % flags)
        state = parse_power_state(self.ec.cmd("gale power", until=has_power_state))
        if state != "off":
            raise FatalError("EC 'gale power' reports %r after an acknowledged park" % state)
        info("EC bookkeeping: power - off")

        # Arm the AP watchdog: from here, ANY byte on the AP console os._exit()s
        # the whole process (see APWatchdog).  It is fully independent of the SPI
        # path.
        self.watchdog = APWatchdog(self.ap_ser, self.log)
        self.watchdog.start()
        self.log.log("AP-WATCHDOG", "armed")
        info("AP watchdog armed")

        self.bridge = Bridge(self.log)
        # Give the watchdog the bridge handle so it can DISABLE on trip.
        self.watchdog.bridge = self.bridge
        self.bridge.enable()  # self-heals with a DISABLE-before-ENABLE
        check_rdid(self.bridge)

    def teardown(self, had_error):
        """DISABLE, release, stop watchdog, final EC state log.  On the
        success path failures here are real failures; after an error they are
        logged but suppressed so the primary error propagates."""

        def step(name, fn):
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - teardown reporting
                self.log.log("TEARDOWN", "%s failed: %s" % (name, e))
                if not had_error:
                    raise

        if self.bridge is not None:
            step("DISABLE", self.bridge.disable)
            step("release", self.bridge.release)
        # The watchdog is independent: on a trip it os._exit()s the process, so
        # if we reach teardown it did NOT trip; just stop the thread.
        if self.watchdog is not None:
            step("watchdog stop", self.watchdog.stop)
        if self.ap_ser is not None:
            step("AP tty close", self.ap_ser.close)
        if self.ec is not None:

            def final_state():
                flags = parse_flags_line(self.ec.cmd("sysinfo", until=has_flags_line))
                state = parse_power_state(self.ec.cmd("gale power", until=has_power_state))
                info("final EC state: %s, power - %s" % (flags, state))

            step("final EC state", final_state)
            step("EC close", self.ec.close)


# ---------------------------------------------------------------------------
# Commands.


def parse_num(s):
    return int(s, 0)


def cmd_read(args, log):
    offset = args.offset
    length = args.length if args.length is not None else FLASH_SIZE - offset
    if not (0 <= offset < FLASH_SIZE) or length <= 0 or offset + length > FLASH_SIZE:
        raise FatalError(
            "read range invalid: offset=0x%x length=0x%x (flash is 0x%x bytes)"
            % (offset, length, FLASH_SIZE)
        )
    info("read: 0x%06x..0x%06x (%d bytes) -> %s" % (offset, offset + length, length, args.out))
    log.log("CMD", "read offset=0x%x length=0x%x out=%s" % (offset, length, args.out))

    session = Session(log)
    had_error = True
    report = None
    try:
        session.prepare()
        t0 = time.monotonic()
        if args.verify:
            data, report = verified_read(session.bridge, offset, length, log)
        else:
            data = read_region(session.bridge, offset, length)
        dt = time.monotonic() - t0
        had_error = False
    finally:
        session.teardown(had_error)

    out = os.path.expanduser(args.out)
    with open(out, "wb") as f:
        f.write(data)
    sha = hashlib.sha256(data).hexdigest()
    rate = length / dt / (1024 * 1024)
    if args.verify:
        if report["runs"]:
            info(
                "verify: image CONFIRMED after repairing %d run(s):" % len(report["runs"])
            )
            for lo, hi, p1w, p2w in report["runs"]:
                info(
                    "  0x%06x..0x%06x  glitched: %s"
                    % (lo, hi, "+".join(w for w, b in (("pass1", p1w), ("pass2", p2w)) if b) or "neither")
                )
        else:
            info("verify: image CONFIRMED (two passes byte-identical, no repair needed)")
        info("read+verify complete: %d bytes in %.1fs (2 passes + repair)" % (length, dt))
    else:
        info("read complete: %d bytes in %.1fs (%.3f MiB/s)" % (length, dt, rate))
    info("sha256 %s  %s" % (sha, out))
    info("usb_spi: %s" % session.bridge.rtt_summary())
    log.log("DONE", "read ok: %dB %.1fs sha256=%s verify=%s" % (length, dt, sha, args.verify))
    log.log("DONE", session.bridge.rtt_summary())

    # Reference-less backup validation: read-twice-must-agree only filters
    # transient glitches; real data validation catches a persistent brownout.
    # Runs only for a full-chip --verify backup (the whole-image checks need
    # FMAP/vboot/GPT).  The dump is already written above, so a validation
    # failure still leaves the (suspect) image on disk for diagnosis.
    if args.verify:
        if offset == 0 and length == FLASH_SIZE:
            validate_full_image(
                data, log, futility_path=args.futility, skip_vboot=args.skip_vboot
            )
        else:
            info("validate: skipped (partial region read; whole-image FMAP/vboot/"
                 "GPT checks are N/A)")
            log.log("VALIDATE", "skipped: partial read offset=0x%x length=0x%x" % (offset, length))


def describe_write_plan(offset, data):
    length = len(data)
    nsectors = length // SECTOR_SIZE
    chunks = list(iter_program_chunks(offset, data))
    verify_txns = (length + READ_CHUNK - 1) // READ_CHUNK
    # Per erase: WREN + ERASE + >=1 RDSR poll.  Per chunk: WREN + PP + >=1 poll.
    est_txns = nsectors * 3 + len(chunks) * 3 + verify_txns + 1
    info("write plan:")
    info("  source sha256: %s" % hashlib.sha256(data).hexdigest())
    info("  region: 0x%06x..0x%06x (%d bytes)" % (offset, offset + length, length))
    info("  erase:  %d x 4K sectors (WREN + 0x20 + WIP poll each)" % nsectors)
    info(
        "  program: %d chunks (<=%dB each, page-bounded; WREN + 0x02 + WIP poll each)"
        % (len(chunks), PROGRAM_CHUNK)
    )
    info("  verify: full read-back of the region (%d READ txns)" % verify_txns)
    info("  estimated usb_spi transactions: >= %d" % est_txns)


def cmd_write(args, log):
    src = os.path.expanduser(args.src)
    data = open(src, "rb").read()
    offset = args.offset
    length = args.length if args.length is not None else len(data)
    if length != len(data):
        raise FatalError(
            "--length 0x%x does not match source file size 0x%x (%s)"
            % (length, len(data), src)
        )
    if offset % SECTOR_SIZE or length % SECTOR_SIZE:
        raise FatalError(
            "write region must be 4K-aligned: offset=0x%x length=0x%x" % (offset, length)
        )
    if length <= 0 or offset + length > FLASH_SIZE:
        raise FatalError(
            "write range invalid: offset=0x%x length=0x%x (flash is 0x%x bytes)"
            % (offset, length, FLASH_SIZE)
        )
    if offset < RO_GUARD_LIMIT and not args.allow_ro:
        raise FatalError(
            "refusing to write below 0x%06x (bootblock / RO / RW slots): "
            "offset=0x%06x. Pass --allow-ro to override (dangerous)."
            % (RO_GUARD_LIMIT, offset)
        )

    describe_write_plan(offset, data)
    if args.dry_run:
        info("dry run: no hardware touched")
        return
    if not args.confirm:
        raise FatalError(
            "refusing to erase/program without --confirm "
            "(write-path execution is operator-gated)"
        )

    log.log("CMD", "write offset=0x%x length=0x%x src=%s allow_ro=%s"
            % (offset, length, src, args.allow_ro))
    session = Session(log)
    had_error = True
    timings = None
    try:
        session.prepare()
        t0 = time.monotonic()
        timings = write_region(session.bridge, offset, data, log, verify=not args.no_verify)
        dt = time.monotonic() - t0
        had_error = False
    finally:
        session.teardown(had_error)

    def mbps(sec):
        return length / sec / (1024 * 1024) if sec else float("nan")

    info("write complete: %d bytes in %.1fs" % (length, dt))
    info("  erase:   %.1fs  %.3f MiB/s" % (timings["erase_s"], mbps(timings["erase_s"])))
    info("  program: %.1fs  %.3f MiB/s" % (timings["program_s"], mbps(timings["program_s"])))
    if "verify_s" in timings:
        info("  verify:  %.1fs  %.3f MiB/s" % (timings["verify_s"], mbps(timings["verify_s"])))
    info("usb_spi: %s" % session.bridge.rtt_summary())
    log.log("DONE", "write ok: %dB %.1fs erase=%.1fs program=%.1fs verify=%s"
            % (length, dt, timings["erase_s"], timings["program_s"], timings.get("verify_s")))
    log.log("DONE", session.bridge.rtt_summary())


def main():
    p = argparse.ArgumentParser(
        description="SPI flash read/write for gale via the debug EC usb_spi bridge (V1)"
    )
    p.add_argument("--log", metavar="FILE", help="append a complete operation log to FILE")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("read", help="read flash to a file")
    pr.add_argument("out", help="output file")
    pr.add_argument("--offset", type=parse_num, default=0)
    pr.add_argument("--length", type=parse_num, default=None, help="default: to end of flash")
    pr.add_argument(
        "--verify",
        action="store_true",
        help="reference-less backup: read twice and reconcile (targeted re-read "
        "until two reads agree), then run data validation on a full-chip image "
        "(vboot FW_MAIN_A/B via futility, RW_GPT CRC32s, __FMAP__, VPD magic)",
    )
    pr.add_argument(
        "--futility",
        default=FUTILITY_DEFAULT,
        help="path to futility for the vboot check (default: the rig's aarch64 "
        "build; falls back to PATH)",
    )
    pr.add_argument(
        "--skip-vboot",
        action="store_true",
        help="skip the futility vboot check during --verify validation "
        "(e.g. futility unavailable); other data checks still run",
    )

    pw = sub.add_parser("write", help="4K-aligned erase + program + confirmed verify")
    pw.add_argument("src", help="source image")
    pw.add_argument("--offset", type=parse_num, required=True)
    pw.add_argument("--length", type=parse_num, default=None, help="default: source file size")
    pw.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    pw.add_argument("--confirm", action="store_true", help="actually erase/program the flash")
    pw.add_argument(
        "--allow-ro",
        action="store_true",
        help="permit writes below 0x%06x (bootblock/RO/RW slots); dangerous" % RO_GUARD_LIMIT,
    )
    pw.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the confirmed read-back verify (measurement only; NOT for real flashes)",
    )

    args = p.parse_args()
    log = Log(args.log)
    try:
        if args.command == "read":
            cmd_read(args, log)
        else:
            cmd_write(args, log)
    except FatalError as e:
        log.log("FATAL", str(e))
        log.flush()
        print("FATAL: %s" % e, file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        log.close()


if __name__ == "__main__":
    main()
