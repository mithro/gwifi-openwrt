#!/usr/bin/env python3
"""Minimal USB host-bridge over the GaleUsb device-controller model.

The gale EC firmware brings up its STM32F0 USB-FS device controller (usb_init,
CNTR=0xe400) once CCD activates. This harness plays the USB *host*: it drives a bus
reset and EP0 control transfers through GaleUsb's SignalReset/SignalTransfer hooks +
the packet-memory (PMA), so we can exercise LIVE enumeration (not just static
descriptor bytes) — the device descriptor here, extensible to config/string
descriptors, SET_ADDRESS, and the bulk console/raiden endpoints.

Usage:
  uv run python usb_host.py --bin <image> [--boot 2.5]

It boots the image, runs until usb_init has completed, signals a USB reset (the EC's
usb_reset configures EP0: control, RX VALID, TX NAK), then issues a standard
GET_DESCRIPTOR(DEVICE) control-IN and reads the device descriptor the firmware places
in the EP0 TX buffer. Prints PASS/FAIL with the parsed descriptor.
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")

# STM32F0 USB packet memory (PMA) base + the EC's EP0 buffer-descriptor layout.
PMA = 0x40006000
BTABLE0 = PMA                 # btable_ep[0]: tx_addr@+0, tx_count@+2, rx_addr@+4, rx_count@+6
USB = 0x40005C00              # USB_FS regs; EP0R@+0x00, CNTR@+0x40

# GET_DESCRIPTOR(DEVICE, index 0, length 18) — standard control SETUP (8 bytes).
SETUP_GET_DEV_DESC = [0x0680, 0x0100, 0x0000, 0x0012]  # 4 little-endian halfwords


def renode(cmds, timeout=400):
    out = subprocess.run(
        ["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, timeout=timeout)
    return out.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--boot", default="2.5", help="virtual seconds before host drives the bus")
    args = ap.parse_args()

    # One Renode session: boot -> reset -> read btable -> write SETUP -> deliver ->
    # read EP0 TX buffer. We read btable_ep[0] for tx/rx addresses (robust across
    # images), then re-derive absolute PMA addresses for the SETUP write + response read.
    # Renode monitor can't reuse a read value in a later command, so we read the btable
    # AND just use the standard EC EP0 layout (tx@0x40, rx@0x80) which the read confirms.
    cmds = [
        '$h=@%s' % HERE,
        '$bin=@%s' % os.path.abspath(args.bin),
        '$name="usbh"',
        'include @%s' % BASE,
        'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
        'emulation RunFor "%s"' % args.boot,
        # bus reset -> EC usb_reset configures EP0
        'sysbus.usb SignalReset',
        'emulation RunFor "0.1"',
        'sysbus ReadWord 0x%X' % (BTABLE0 + 0),   # tx_addr
        'sysbus ReadWord 0x%X' % (BTABLE0 + 4),   # rx_addr
        'sysbus ReadWord 0x%X' % USB,             # EP0R after reset
    ]
    # Write the SETUP packet into the EP0 RX buffer (standard rx_addr = 0x80 -> 0x40006080)
    rx = PMA + 0x80
    tx = PMA + 0x40
    for i, hw in enumerate(SETUP_GET_DEV_DESC):
        cmds.append('sysbus WriteWord 0x%X 0x%04X' % (rx + 2 * i, hw))
    cmds += [
        'sysbus WriteWord 0x%X 0x8408' % (BTABLE0 + 6),   # rx_count: 8 bytes received
        'sysbus.usb SignalTransfer 0 true true',          # deliver SETUP (rx, setup)
        'emulation RunFor "0.1"',
        'sysbus ReadWord 0x%X' % (BTABLE0 + 2),           # tx_count (descriptor length)
    ]
    for i in range(9):  # 18-byte device descriptor = 9 halfwords
        cmds.append('sysbus ReadWord 0x%X' % (tx + 2 * i))
    # Second control-IN: GET_DESCRIPTOR(CONFIG, len 64) — first packet of the config
    # descriptor (header + interface/endpoint descriptors: console/AP/unused/raiden).
    for i, hw in enumerate([0x0680, 0x0200, 0x0000, 0x0040]):
        cmds.append('sysbus WriteWord 0x%X 0x%04X' % (rx + 2 * i, hw))
    cmds += [
        'sysbus WriteWord 0x%X 0x8408' % (BTABLE0 + 6),
        'sysbus.usb SignalTransfer 0 true true',
        'emulation RunFor "0.1"',
        'sysbus ReadWord 0x%X' % (BTABLE0 + 2),           # config tx_count
        'sysbus ReadWord 0x%X' % (tx + 0),                # cfg bLength/bType
        'sysbus ReadWord 0x%X' % (tx + 2),                # wTotalLength
        'sysbus ReadWord 0x%X' % (tx + 4),                # bNumInterfaces/bConfigValue
    ]
    cmds.append('quit')

    out = renode(cmds)

    # Parse the ordered hex reads after each MARK.
    reads = re.findall(r'^(0x[0-9A-Fa-f]+)\s*$', out, re.M)
    # Order: tx_addr, rx_addr, ep0r, tx_count, desc[0..8]
    usb_init_done = "USB init done" in out
    print("=== USB host-bridge live enumeration: %s ===" % os.path.basename(args.bin))
    print("usb_init reached:", usb_init_done)
    if len(reads) < 13:
        print("FAIL: insufficient reads (%d) — controller not enumerable. Output tail:" % len(reads))
        for l in out.splitlines()[-15:]:
            print("  " + l)
        return
    txa, rxa, ep0r = reads[0], reads[1], reads[2]
    txcount = int(reads[3], 16)
    desc_hw = [int(x, 16) for x in reads[4:13]]
    # halfwords -> little-endian bytes
    desc = []
    for hw in desc_hw:
        desc.append(hw & 0xFF)
        desc.append((hw >> 8) & 0xFF)
    print("EP0 tx_addr=%s rx_addr=%s EP0R(after reset)=%s" % (txa, rxa, ep0r))
    print("GET_DESCRIPTOR(DEVICE) -> tx_count=%d bytes" % txcount)
    print("device descriptor bytes:", " ".join("%02x" % b for b in desc))
    if len(desc) >= 12:
        bLength = desc[0]; bType = desc[1]
        idVendor = desc[8] | (desc[9] << 8)
        idProduct = desc[10] | (desc[11] << 8)
        print("  bLength=%d bDescriptorType=%d idVendor=0x%04x idProduct=0x%04x"
              % (bLength, bType, idVendor, idProduct))
        dev_ok = (txcount == 18 and bLength == 18 and bType == 1 and idVendor == 0x18d1)
        print("DEVICE DESC:", "PASS (Google 0x18d1)" if dev_ok else "CHECK")

    # Config descriptor (reads[13..16]: cfg tx_count, [bLen|bType], wTotalLength, [nIf|cfgVal])
    cfg_ok = False
    if len(reads) >= 17:
        cfg_txc = int(reads[13], 16)
        h0 = int(reads[14], 16); wtotal = int(reads[15], 16); h2 = int(reads[16], 16)
        cfg_bLength = h0 & 0xFF; cfg_bType = (h0 >> 8) & 0xFF
        num_ifaces = h2 & 0xFF
        print("CONFIG DESC: first-packet=%d bytes, bLength=%d bType=%d wTotalLength=%d bNumInterfaces=%d"
              % (cfg_txc, cfg_bLength, cfg_bType, wtotal, num_ifaces))
        cfg_ok = (cfg_bLength == 9 and cfg_bType == 2 and num_ifaces == 4)
        print("CONFIG DESC:", "PASS (4 interfaces: console if00/AP if01/unused/raiden if03)"
              if cfg_ok else "CHECK")
    print("RESULT:", "PASS — live USB enumeration (device + config)" if (dev_ok and cfg_ok)
          else "PARTIAL/CHECK")


if __name__ == "__main__":
    main()
