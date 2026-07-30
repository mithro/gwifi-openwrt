#!/usr/bin/env python3
# Restore RW_NVRAM (vboot nvdata @ 0x6f0000) from the clean pre-flash dump to
# clear a PERSISTENT RW_NO_KERNEL (0x5b) recovery loop on 2831 -- self-inflicted
# by repeated verify-boots with no netboot server (each fails to find a kernel).
# RW_NVRAM is in the RW area (> RO_GUARD_LIMIT), so no --allow-ro / no RO risk.
# Run with the SYSTEM python (/usr/bin/python3) so pyusb resolves.
import sys

sys.path.insert(0, "/home/tim/local/gwifi/gwifi-openwrt/tools")
import flash_puck_usb as F  # noqa: E402

DUMP = "/home/tim/local/gwifi/fleet-flash/backups/gale-2831HW00WGD-2026-07-07-pre-flash.bin"
OFF, SIZE = 0x6F0000, 0x10000
assert OFF >= F.RO_GUARD_LIMIT, "RW_NVRAM must be in the RW area"
data = open(DUMP, "rb").read()[OFF:OFF + SIZE]
assert len(data) == SIZE, "short read from dump"

log = F.Log(None)
F.info("restoring RW_NVRAM (0x%06x, %d B) from clean dump -> clears recovery loop" % (OFF, SIZE))
new_session = F.make_session_factory(log, 512)   # AP-abort poll cadence (flash default)
F.flash_region(new_session, OFF, data, log)
F.info("RW_NVRAM restored + verified -- recovery request cleared; next boot = normal")
print("RW_NVRAM_RESTORE_DONE")
