#!/usr/bin/env python3
"""Reattach the kernel (usb-serial) driver to the gale console interfaces so
/dev/ttyUSB0/1 return for the pyserial tools, after a libusb tool detached them."""
import sys
import time

import usb.core
import usb.util

d = usb.core.find(idVendor=0x18D1, idProduct=0x500F)
if d is None:
    sys.exit("18d1:500f not found")
for ifnum in (0, 1):
    try:
        if not d.is_kernel_driver_active(ifnum):
            d.attach_kernel_driver(ifnum)
            print("attached kernel driver to if%d" % ifnum, flush=True)
        else:
            print("if%d already has a kernel driver" % ifnum, flush=True)
    except (usb.core.USBError, NotImplementedError) as e:
        print("if%d attach failed: %s" % (ifnum, e), flush=True)
usb.util.dispose_resources(d)
time.sleep(1.0)
