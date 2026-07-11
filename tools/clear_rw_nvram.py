#!/usr/bin/env python3
"""Erase the gale RW_NVRAM region (0x6f0000, 0x10000) to 0xff.

The vboot nvram is an append log in this region; all-0xff means "no valid
entry" and vboot regenerates defaults on the next boot — clearing any
latched recovery request (the RW_NO_KERNEL loop from no-server boot
sessions; see the gale-verify-boot-wedged-bench memory).  Uses the
verified flash tool's own primitives (park + settle + erase + program +
verify).  Run ON the rig with /usr/bin/python3.
"""
import sys

sys.path.insert(0, "/home/tim/local/gwifi/gwifi-openwrt/tools")
import flash_puck_usb as F  # noqa: E402

OFF = 0x6F0000
LEN = 0x10000

log = F.Log("~/gale-netboot/clear_nvram_txn.log")
new_session = F.make_session_factory(log, abort_every=512)

before = F.read_region_sessioned(new_session, OFF, LEN, log,
                                 label="nvram-before")
used = sum(1 for i in range(0, LEN, 16) if before[i:i + 16] != b"\xff" * 16)
print(f"before: {used} non-empty 16B entries")

F.flash_region(new_session, OFF, b"\xff" * LEN, log)

after = F.read_region_sessioned(new_session, OFF, LEN, log,
                                label="nvram-after")
assert after == b"\xff" * LEN, "RW_NVRAM not fully erased!"
print("RW_NVRAM erased + verified (all 0xff)")
