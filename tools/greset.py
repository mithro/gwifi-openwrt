#!/usr/bin/env python3
"""Temporary recovery helper: USB-reset the gale debug device (18d1:500f) to
re-enumerate it -- this restores the /dev/ttyUSB console nodes (kernel re-probes
the interfaces) with clean endpoint toggles, WITHOUT resetting the EC MCU or
touching AP power. Run when a libusb tool left the console interfaces detached."""
import sys
import time

import usb.core

d = usb.core.find(idVendor=0x18D1, idProduct=0x500F)
if d is None:
    sys.exit("18d1:500f not found")
print("found bus %d addr %d; USB-resetting" % (d.bus, d.address), flush=True)
try:
    d.reset()
except usb.core.USBError as e:
    print("reset() raised (often expected as the handle drops): %s" % e, flush=True)
print("waiting for re-enumeration...", flush=True)
time.sleep(4)
d2 = usb.core.find(idVendor=0x18D1, idProduct=0x500F)
print("re-enumerated: %s" % ("yes" if d2 is not None else "NO"), flush=True)
