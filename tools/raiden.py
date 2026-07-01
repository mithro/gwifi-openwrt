#!/usr/bin/env python3
"""Shared gale AP-flash raiden transport (chromiumos EC usb_spi V1).

Single source of truth for: parking the AP, claiming the EC's raiden bulk
interface, enabling the SPI bridge, and a FAIL-LOUD SPI transfer. Every transfer
validates the USB response length and raises on any non-zero usb_spi status -- it
never silently zero-fills or returns partial/garbage data. Used by raiden_sr.py
and raiden_write_region.py.

Protocol (usb_spi V1, from flashrom raiden_debug_spi.c):
  claim IF3 -> vendor ctrl REQ_ENABLE (0x41, bReq 0x0000, wIndex 3)
  bulk OUT [write_count, read_count, payload]  ->  bulk IN [status:u16 LE, payload]
"""
import os
import time

import serial
import usb.core
import usb.util

VID, PID = 0x18D1, 0x500F
IFNUM, EP_OUT, EP_IN = 3, 0x03, 0x83
REQ_ENABLE, REQ_DISABLE = 0x0000, 0x0001
RTYPE_OUT = 0x41  # LIBUSB_ENDPOINT_OUT | REQUEST_TYPE_VENDOR | RECIPIENT_INTERFACE
BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
RDID_EXPECT = bytes([0xEF, 0x40, 0x17])  # Winbond W25Q64FV
V1_MAX = 62                               # max read OR write payload per transaction

# SPI flash opcodes
OP_RDID, OP_RDSR1, OP_RDSR2, OP_RDSR3 = 0x9F, 0x05, 0x35, 0x15
OP_WREN, OP_WRDI = 0x06, 0x04
OP_SE4K, OP_BE64K, OP_PP, OP_READ = 0x20, 0xD8, 0x02, 0x03

# usb_spi V1 status codes (chip/stm32/usb_spi.h)
_STATUS = {
    0x0000: "SUCCESS", 0x0001: "SPI_TIMEOUT", 0x0002: "BUSY",
    0x0003: "WRITE_COUNT_INVALID", 0x0004: "READ_COUNT_INVALID",
    0x0005: "DISABLED (bridge off / WP enabled)",
}


class RaidenError(RuntimeError):
    """Any bridge/SPI failure. Raised loudly; never swallowed into bad data."""


def a3(addr):
    """24-bit big-endian address bytes for a 3-byte-address SPI opcode."""
    return [(addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF]


def ec_park(attempts=5):
    """`gale power off` on the EC console: park the AP and grant the EC the SPI bus.

    CRITICAL: raiden write ops auto-power-on the AP after each operation, so the AP
    must be RE-parked before every raiden session. If the (occasionally flaky) EC
    console drops/garbles the command, the AP stays awake and starts reading the SPI
    to boot -- then the AP and the EC bridge are two masters on the same SPI bus and
    the next raiden transfer times out. So don't fire-and-forget: send the command
    and READ BACK the EC's acknowledgement ("...power...off..."), retrying until it
    confirms. Raise (fail loud) if it never confirms -- the caller is a fresh worker
    whose failure triggers the per-chunk retry, which re-parks cleanly."""
    port = os.path.realpath(BYID) if os.path.exists(BYID) else "/dev/ttyUSB0"
    text = ""
    with serial.Serial(port, 115200, timeout=0.2) as s:
        for _ in range(attempts):
            time.sleep(0.15)
            s.reset_input_buffer()
            s.write(b"gale power off\r\n")
            s.flush()
            # Read until the console falls quiet (or a hard cap), then check the ack.
            resp = b""
            t0 = last = time.time()
            while time.time() - t0 < 2.0:
                n = s.in_waiting
                if n:
                    resp += s.read(n)
                    last = time.time()
                elif time.time() - last > 0.3:
                    break
                else:
                    time.sleep(0.02)
            text = resp.decode("latin1", "replace").lower()
            # EC acks with e.g. "power off ap" / "power - off"; both contain "off".
            if "off" in text and "power" in text:
                time.sleep(0.2)
                return
    raise RaidenError(
        f"ec_park: EC console did not confirm AP parked after {attempts} "
        f"'gale power off' attempts -- refusing to drive SPI against a possibly "
        f"awake AP (last response: {text!r})")


class Raiden:
    """A parked, enabled raiden SPI session. Use as a context manager:

        with Raiden() as r:
            rdid = r.xfer([OP_RDID], 3)

    __init__ parks the AP, enables the bridge, and validates RDID, so a disabled
    bridge / wrong chip / framing error fails loud immediately instead of later.
    """

    def __init__(self, park=True, validate=True):
        if park:
            ec_park()
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RaidenError("gale debug device 18d1:500f not found (SuzyQ attached?)")
        self.detached = False
        try:
            if self.dev.is_kernel_driver_active(IFNUM):
                self.dev.detach_kernel_driver(IFNUM)
                self.detached = True
        except (usb.core.USBError, NotImplementedError):
            pass
        usb.util.claim_interface(self.dev, IFNUM)
        self.dev.ctrl_transfer(RTYPE_OUT, REQ_ENABLE, 0, IFNUM, None, 1000)
        time.sleep(0.05)
        self._drain()
        if validate:
            rdid = self.xfer([OP_RDID], 3)
            if rdid != RDID_EXPECT:
                self.close()
                raise RaidenError(f"RDID={rdid.hex()} != {RDID_EXPECT.hex()} "
                                  f"(bridge not ready, wrong chip, or framing error)")

    def _drain(self):
        for _ in range(100):
            try:
                self.dev.read(EP_IN, 64, timeout=20)
            except usb.core.USBError:
                break

    def xfer(self, wdata, rc):
        """One usb_spi V1 transaction; returns exactly `rc` bytes read.

        FAIL-LOUD: raises RaidenError on a short USB response, a non-zero usb_spi
        status, or a short payload. Callers therefore never see partial/garbage
        data masquerading as a successful read.
        """
        if len(wdata) > V1_MAX or rc > V1_MAX:
            raise RaidenError(f"xfer exceeds V1 limit: write {len(wdata)} / read {rc} (max {V1_MAX})")
        op = wdata[0] if wdata else -1
        out = bytes([len(wdata), rc]) + bytes(wdata)
        self.dev.write(EP_OUT, out, timeout=2000)
        resp = bytes(self.dev.read(EP_IN, 64, timeout=2000))
        if len(resp) < 2:
            raise RaidenError(f"short USB response: {len(resp)} B (<2 status bytes), opcode 0x{op:02x}")
        status = resp[0] | (resp[1] << 8)
        if status != 0:
            raise RaidenError(f"usb_spi status 0x{status:04x} "
                              f"({_STATUS.get(status, 'unknown')}), opcode 0x{op:02x}")
        data = resp[2:2 + rc]
        if len(data) != rc:
            raise RaidenError(f"short payload: got {len(data)}/{rc} B, opcode 0x{op:02x}")
        return data

    def sr1(self):
        return self.xfer([OP_RDSR1], 1)[0]

    def wait_wip(self, timeout=2.0):
        """Poll SR1 until WIP (busy) clears. Sparse polling (each RDSR is a
        transaction counting against the ~1444/session cliff). Raises if stuck."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not (self.sr1() & 1):
                return
            time.sleep(0.005)
        raise RaidenError(f"WIP still set after {timeout:.1f}s (erase/program stalled)")

    def read_data(self, addr, n):
        """Read n (<=62) bytes via Read Data (0x03) at a 3-byte address."""
        return self.xfer([OP_READ] + a3(addr), n)

    def close(self):
        try:
            self.dev.ctrl_transfer(RTYPE_OUT, REQ_DISABLE, 0, IFNUM, None, 1000)
        except usb.core.USBError:
            pass
        usb.util.release_interface(self.dev, IFNUM)
        usb.util.dispose_resources(self.dev)
        if self.detached:
            try:
                self.dev.attach_kernel_driver(IFNUM)
            except usb.core.USBError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
