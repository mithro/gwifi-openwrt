#!/usr/bin/env python3
"""Targeted coverage of ep0_rx (the USB EP0 SETUP-packet handler, usb.c:~90-190, RO 0x080027e8) by
delivering a battery of standard USB control SETUP packets the normal enumeration never sends. The
campaign's USB path only does GET_DESCRIPTOR(DEVICE/CONFIG) + SET_CONFIGURATION + the SPI vendor
request, so ep0_rx's GET_STATUS arm (usb.c:168), STRING-descriptor + out-of-range-index arm (137),
interface-recipient arms (106/108), the descriptor-type switch (121, incl STRING/CONFIGURATION 161),
and the OUT-request arms (175/176, SET_ADDRESS) stay unreached.

Reuses usb_host.discover() to find the live EP0 RX buffer address (PMA-relative, set by usb_init),
then runs ONE traced renode pass delivering the extra SETUPs and folds the execution trace into
tmp/usbep0_edges.pkl (unioned by combine_coverage.py). Genuine execution of the captured firmware.
Serial + memory-capped via the same renode invocation pattern as the rest of the campaign.
"""
import os
import pickle
import subprocess

import usb_host as U
import coverage_captured as CC

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
BASE = os.path.join(HERE, "base.resc")

# Extra standard SETUPs (4 LE halfwords: [bmRequestType|bRequest<<8, wValue, wIndex, wLength]).
GET_STATUS_DEV = [0x0080, 0x0000, 0x0000, 0x0002]   # GET_STATUS, recipient device  (usb.c:168)
GET_STATUS_IF  = [0x0081, 0x0000, 0x0000, 0x0002]   # GET_STATUS, recipient interface (106/108/168)
GET_STR0       = [0x0680, 0x0300, 0x0000, 0x00FF]   # GET_DESCRIPTOR STRING idx 0 (lang) (121/137)
GET_STR1       = [0x0680, 0x0301, 0x0409, 0x00FF]   # GET_DESCRIPTOR STRING idx 1 (valid)
GET_STR_BAD    = [0x0680, 0x0320, 0x0000, 0x00FF]   # STRING idx 0x20 >= USB_STR_COUNT (137 true)
GET_CFG_DESC   = [0x0680, 0x0200, 0x0000, 0x00FF]   # GET_DESCRIPTOR CONFIGURATION, big wLength (150/155/161)
GET_DESC_BADTYPE = [0x0680, 0x0500, 0x0000, 0x0012] # descriptor type 5 -> switch default (121)
GET_DESC_IFACE = [0x0681, 0x0100, 0x0000, 0x0012]   # GET_DESCRIPTOR, recipient interface (106/108)
SET_ADDRESS    = [0x0500, 0x0005, 0x0000, 0x0000]   # SET_ADDRESS(5), OUT (175/176)
GET_STATUS_IF_BAD = [0x0081, 0x0000, 0x0009, 0x0002]  # interface index 9 >= USB_IFACE_COUNT (108 false)
# the OUT-request switch(req>>8) sub-cases (usb.c:175/176): exercise each std OUT bRequest + a default
SET_CONFIG     = [0x0900, 0x0001, 0x0000, 0x0000]   # SET_CONFIGURATION(1)
CLEAR_FEATURE  = [0x0100, 0x0000, 0x0000, 0x0000]   # CLEAR_FEATURE, device
SET_FEATURE    = [0x0300, 0x0001, 0x0000, 0x0000]   # SET_FEATURE, device
SET_FEATURE_IF = [0x0301, 0x0000, 0x0000, 0x0000]   # SET_FEATURE, interface recipient (106/108)
SET_INTERFACE  = [0x010B, 0x0000, 0x0000, 0x0000]   # SET_INTERFACE(11), interface recipient
SET_DESCRIPTOR = [0x0700, 0x0200, 0x0000, 0x0009]   # SET_DESCRIPTOR(7), OUT
OUT_DEFAULT    = [0x00FE, 0x0000, 0x0000, 0x0000]   # unhandled OUT bRequest 0xFE -> switch default
GET_DESC_SMALLW = [0x0680, 0x0200, 0x0000, 0x0004]  # CONFIG desc, tiny wLength=4 (len clamp 150)
GET_DESC_BIGW   = [0x0680, 0x0200, 0x0000, 0x0100]  # CONFIG desc, wLength=256 (>= MAX_PACKET, 155)
GET_DEV_DESC    = [0x0680, 0x0100, 0x0000, 0x0012]  # GET_DESCRIPTOR DEVICE (121 case)

BATTERY = [GET_STATUS_DEV, GET_STATUS_IF, GET_STATUS_IF_BAD, GET_STR0, GET_STR1, GET_STR_BAD,
           GET_CFG_DESC, GET_DESC_BADTYPE, GET_DESC_IFACE, SET_ADDRESS,
           SET_CONFIG, CLEAR_FEATURE, SET_FEATURE, SET_FEATURE_IF, SET_INTERFACE, SET_DESCRIPTOR,
           OUT_DEFAULT, GET_DESC_SMALLW, GET_DESC_BIGW, GET_DEV_DESC]


def traced_renode(extra, boot, mon, trace, timeout=400):
    cmds = ['$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(CAPTURED), '$name="usbh"',
            'include @%s' % BASE] + list(mon) + [
            'emulation RunFor "%s"' % boot, 'sysbus.usb SignalReset', 'emulation RunFor "0.1"',
            'cpu CreateExecutionTracing "tre" @%s PC' % trace] + extra + [
            'cpu DisableExecutionTracing', 'quit']
    subprocess.run(CC._renode_cmd("; ".join(cmds)),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=timeout)


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "usbep0_edges.pkl")
    ex, ed = set(), set()
    if os.path.exists(out):
        try:
            pe, ped = pickle.load(open(out, "rb"))
            ex |= set(pe); ed |= set(ped)
            print("loaded prior usbep0_edges.pkl: %d edges, %d PCs" % (len(ed), len(ex)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)

    boot, mon = "1.5", []
    # usb_host.renode() reads the module-global ARGS.bin; populate it for direct (non-CLI) use.
    U.ARGS = type("A", (), {"bin": os.path.abspath(CAPTURED), "boot": boot, "mon": mon})()
    d, reached = U.discover(boot, mon)
    if not d or (d["ep0_tx"] & 0xFFF) == 0:
        print("FAIL: EP0 not configured (usb_init not reached); reached=%s" % reached)
        return
    ep0_rx = U.PMA + (d["ep0_rx"] & 0xFFF)
    print("EP0 RX buffer @ 0x%X" % ep0_rx)

    trace = os.path.join(TMP, "usbep0.txt")
    if os.path.exists(trace):
        os.remove(trace)
    # configure first (so interface/config-dependent arms have valid state), then the battery
    seq = U.setup_ep0(ep0_rx, U.SET_CFG)
    for s in BATTERY:
        seq += U.setup_ep0(ep0_rx, s)
    traced_renode(seq, boot, mon, trace)
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(out, "wb"))
    print("saved -> tmp/usbep0_edges.pkl: %d edges, %d PCs" % (len(ed), len(ex)))


if __name__ == "__main__":
    main()
