#!/usr/bin/env python3
"""USB host-bridge over the GaleUsb device-controller model — LIVE enumeration.

Plays the USB *host*: drives a bus reset (SignalReset -> the EC's usb_reset configures
EP0) and EP0 control transfers (GET_DESCRIPTOR) through GaleUsb's SignalReset/
SignalTransfer hooks + the packet-memory (PMA), exercising live enumeration rather than
static descriptor bytes. Image-agnostic: it first discovers the EC's EP0 buffer addresses
from the buffer-descriptor table (they differ between firmware versions), then runs the
control transfers against the right PMA addresses.

Usage:
  uv run python usb_host.py --bin <image> [--boot 2.5] [--mon "<pre-boot monitor cmd>"]

The original (v1.1.5337) brings up usb_init autonomously (~st17); the rebuilt needs a
debug accessory to reach usb_init, so pass --mon "sysbus.adc CcPullAddress 0x20001107"
and a short --boot (e.g. 0.4) to enumerate it in the window before its raiden-EP4 panic.
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
PMA = 0x40006000
BTABLE0 = PMA          # btable_ep[0]: tx_addr@+0, tx_count@+2, rx_addr@+4, rx_count@+6


def renode(extra, boot, mon, timeout=400):
    cmds = ['$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(ARGS.bin), '$name="usbh"',
            'include @%s' % BASE] + list(mon) + [
            'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
            'emulation RunFor "%s"' % boot,
            'sysbus.usb SignalReset', 'emulation RunFor "0.1"'] + extra + ['quit']
    out = subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=timeout).stdout
    return out, re.findall(r'^(0x[0-9A-Fa-f]+)\s*$', out, re.M)


def setup(rx_pma, hws):
    c = []
    for i, hw in enumerate(hws):
        c.append('sysbus WriteWord 0x%X 0x%04X' % (rx_pma + 2 * i, hw))
    c += ['sysbus WriteWord 0x%X 0x8408' % (BTABLE0 + 6), 'sysbus.usb SignalTransfer 0 true true',
          'emulation RunFor "0.1"']
    return c


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--boot", default="2.5")
    ap.add_argument("--mon", action="append", default=[])
    ARGS = ap.parse_args()

    # Pass 1: discover EP0 tx/rx buffer addresses (version-specific) from the btable.
    out1, r1 = renode(['sysbus ReadWord 0x%X' % (BTABLE0 + 0),   # tx_addr
                       'sysbus ReadWord 0x%X' % (BTABLE0 + 4)],  # rx_addr
                      ARGS.boot, ARGS.mon)
    usb_init = "USB init done" in out1
    print("=== USB host-bridge: %s ===" % os.path.basename(ARGS.bin))
    print("usb_init reached:", usb_init)
    if len(r1) < 2 or int(r1[0], 16) == 0:
        print("FAIL: EP0 not configured (tx_addr=%s) — usb_init not reached / controller down."
              % (r1[0] if r1 else "n/a"))
        return
    txp = PMA + (int(r1[0], 16) & 0xFFF)
    rxp = PMA + (int(r1[1], 16) & 0xFFF)
    print("EP0 buffers: tx=0x%X rx=0x%X" % (txp, rxp))

    # Pass 2: GET_DESCRIPTOR(DEVICE,18) then GET_DESCRIPTOR(CONFIG,64) at the real addresses.
    extra = setup(rxp, [0x0680, 0x0100, 0x0000, 0x0012])
    extra += ['sysbus ReadWord 0x%X' % (BTABLE0 + 2)]                      # device tx_count
    extra += ['sysbus ReadWord 0x%X' % (txp + 2 * i) for i in range(9)]    # device desc
    extra += setup(rxp, [0x0680, 0x0200, 0x0000, 0x0040])
    extra += ['sysbus ReadWord 0x%X' % (BTABLE0 + 2)]                      # config tx_count
    extra += ['sysbus ReadWord 0x%X' % (txp + 2 * i) for i in range(5)]    # config first 10 bytes
    _, r = renode(extra, ARGS.boot, ARGS.mon)

    if len(r) < 16:
        print("FAIL: enumeration reads incomplete (%d)" % len(r)); return
    dtxc = int(r[0], 16)
    dd = []
    for hw in (int(x, 16) for x in r[1:10]):
        dd += [hw & 0xFF, (hw >> 8) & 0xFF]
    idv = dd[8] | (dd[9] << 8); idp = dd[10] | (dd[11] << 8)
    print("DEVICE DESC: tx_count=%d bytes=%s" % (dtxc, " ".join("%02x" % b for b in dd)))
    print("  idVendor=0x%04x idProduct=0x%04x" % (idv, idp))
    dev_ok = (dtxc == 18 and dd[0] == 18 and dd[1] == 1 and idv == 0x18d1 and idp == 0x500f)
    ctxc = int(r[10], 16)
    cd = []
    for hw in (int(x, 16) for x in r[11:16]):
        cd += [hw & 0xFF, (hw >> 8) & 0xFF]
    wtotal = cd[2] | (cd[3] << 8); nif = cd[4]
    print("CONFIG DESC: tx_count=%d bLength=%d bType=%d wTotalLength=%d bNumInterfaces=%d"
          % (ctxc, cd[0], cd[1], wtotal, nif))
    cfg_ok = (cd[0] == 9 and cd[1] == 2 and nif == 4)
    print("RESULT:", "PASS — live USB enumeration: device 0x18d1:0x%04x, config %d ifaces"
          % (idp, nif) if (dev_ok and cfg_ok) else "CHECK")


if __name__ == "__main__":
    main()
