#!/usr/bin/env python3
"""Read-only raiden SPI register reader for the gale AP flash (W25Q64FV).

Speaks the chromiumos EC usb_spi V1 protocol, replicated faithfully from flashrom's
raiden_debug_spi.c (read this session):
  - claim interface IF3, vendor control REQ_ENABLE (0x41, bReq=0x0000, wIndex=3)
  - bulk OUT [write_count, read_count, payload]  ->  bulk IN [status:u16 LE, payload]
Reads RDID + SR1/SR2/SR3 to expose CMP (SR2 bit6) and WPS (SR3 bit2) -- the
protection bits flashrom does NOT decode and which can block erase while SR1
shows "no protection".

ISSUES ONLY READ OPCODES: 0x9F (RDID), 0x05/0x35/0x15 (RDSR1/2/3). No WREN, no
WRSR, no erase, no program. RDID must return ef 40 17 or results are not trusted.
"""
import os
import time

import serial
import usb.core
import usb.util

VID, PID = 0x18d1, 0x500f
IFNUM = 3
EP_OUT, EP_IN = 0x03, 0x83
REQ_ENABLE, REQ_DISABLE = 0x0000, 0x0001
RTYPE_OUT = 0x41  # LIBUSB_ENDPOINT_OUT | REQUEST_TYPE_VENDOR | RECIPIENT_INTERFACE
BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"


def ec_park():
    """gale power off -> park AP, grant EC the SPI bus (matches the working flow)."""
    port = os.path.realpath(BYID) if os.path.exists(BYID) else "/dev/ttyUSB0"
    with serial.Serial(port, 115200, timeout=0.2) as s:
        time.sleep(0.2)
        s.reset_input_buffer()
        s.write(b"gale power off\r\n")
        s.flush()
        time.sleep(0.8)
        if s.in_waiting:
            s.read(s.in_waiting)
    time.sleep(0.3)


def bits(v, names):
    return "  ".join(f"{n}={(v >> i) & 1}" for i, n in names)


def main():
    ec_park()
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        print("device 18d1:500f not found")
        raise SystemExit(2)

    detached = False
    try:
        if dev.is_kernel_driver_active(IFNUM):
            dev.detach_kernel_driver(IFNUM)
            detached = True
    except (usb.core.USBError, NotImplementedError) as e:
        print(f"# kernel-driver check: {e}")

    usb.util.claim_interface(dev, IFNUM)
    # Enable the SPI bridge (generic target 0,0 -- same as flashrom's default).
    dev.ctrl_transfer(RTYPE_OUT, REQ_ENABLE, 0, IFNUM, None, 1000)
    time.sleep(0.05)
    # Drain any stale IN data.
    for _ in range(100):
        try:
            dev.read(EP_IN, 64, timeout=20)
        except usb.core.USBError:
            break

    def xfer(wdata, rc):
        out = bytes([len(wdata), rc]) + bytes(wdata)
        dev.write(EP_OUT, out, timeout=1000)
        resp = bytes(dev.read(EP_IN, 64, timeout=1000))
        status = resp[0] | (resp[1] << 8)
        return status, resp[2:2 + rc]

    try:
        st_id, rdid = xfer([0x9F], 3)
        st1, sr1 = xfer([0x05], 1)
        st2, sr2 = xfer([0x35], 1)
        st3, sr3 = xfer([0x15], 1)
    finally:
        try:
            dev.ctrl_transfer(RTYPE_OUT, REQ_DISABLE, 0, IFNUM, None, 1000)
        except usb.core.USBError:
            pass
        usb.util.release_interface(dev, IFNUM)
        usb.util.dispose_resources(dev)
        if detached:
            try:
                dev.attach_kernel_driver(IFNUM)
            except usb.core.USBError:
                pass

    print(f"RDID  status=0x{st_id:04x}  id={rdid.hex()}   (expect ef4017)")
    ok = rdid == bytes([0xEF, 0x40, 0x17])
    print(f"SELF-CHECK: {'OK -- framing/enable correct, SR values trustworthy' if ok else 'MISMATCH -- DO NOT TRUST SR VALUES'}\n")

    s1, s2, s3 = sr1[0], sr2[0], sr3[0]
    print(f"SR1 = 0x{s1:02x}  (status=0x{st1:04x})")
    print("   " + bits(s1, list(enumerate(
        ["BUSY", "WEL", "BP0", "BP1", "BP2", "TB", "SEC", "SRP0"]))))
    print(f"SR2 = 0x{s2:02x}  (status=0x{st2:04x})")
    print("   " + bits(s2, list(enumerate(
        ["SRL", "QE", "R2", "LB1", "LB2", "LB3", "CMP", "SUS"]))))
    print(f"SR3 = 0x{s3:02x}  (status=0x{st3:04x})")
    print("   " + bits(s3, list(enumerate(
        ["R0", "R1", "WPS", "R3", "R4", "DRV0", "DRV1", "HOLD/RST"]))))

    cmp_set = (s2 >> 6) & 1
    wps_set = (s3 >> 2) & 1
    print()
    if cmp_set:
        print("** CMP=1: with BP=0 the protected range is COMPLEMENTED -> ENTIRE chip protected (blocks erase/program). flashrom missed this. **")
    if wps_set:
        print("** WPS=1: Individual Block/Sector Lock mode -> all sectors locked by default -> blocks erase/program. flashrom can't see this. **")
    if not cmp_set and not wps_set:
        print(">> Neither CMP nor WPS set. Protection is NOT in SR2/SR3 -> the erase failure points to power or the bridge, not flash WP.")


main()
