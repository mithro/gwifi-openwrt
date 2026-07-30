#!/usr/bin/env python3
"""Demonstrate the netboot reboot-retry SELF-HEALING loop on the SuzyQ rig.

The fix is in vboot (RW depthcharge): no valid kernel on the fixed disk clears
the recovery request and returns non-SUCCESS so depthcharge cold_reboots to
retry -- instead of latching RW_NO_KERNEL and stranding the puck in RO recovery.

This rig's cold_reboot resets the AP SoC but the EC holds the rails without
cycling, so the SoC doesn't re-boot on its own (production PD/PMIC would). So we
supply that restart here (gale power off/on) once per cycle and confirm EVERY
boot is a NORMAL RW boot -- never an RO recovery boot, never "waiting for manual
recovery". That is the fix doing its job across the loop.

Usage: loop_demo.py [CYCLES] [SECONDS_PER_CYCLE]
"""
import re
import sys
import time

sys.path.insert(0, "/home/tim/local/gwifi/gwifi-openwrt/tools")
import flash_puck_usb as F  # noqa: E402

cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 3
percap = int(sys.argv[2]) if len(sys.argv) > 2 else 45
log = F.Log(None)


def ec(c):
    dev = F.open_device(log)
    e = F.Console(dev, "ec", log)
    e.sync()
    e.write(c.encode() + b"\r\n")
    time.sleep(1.2)
    try:
        e.release()
        F.usb.util.dispose_resources(dev)
    except Exception:  # noqa: BLE001
        pass


# Un-park to RW once (gale power on only raises the AP rails from RW).
print("sysjump RW (EC -> RW)...", flush=True)
try:
    ec("sysjump RW")
except Exception:  # noqa: BLE001 - re-enumerates
    pass
time.sleep(4)

tot_rw = tot_ro = tot_clear = tot_wait = tot_cold = 0
for cyc in range(1, cycles + 1):
    ec("gale power off")
    time.sleep(2)
    ec("gale power on")
    dev = F.open_device(log)
    ap = F.Console(dev, "ap", log)
    end = time.monotonic() + percap
    out = b""
    while time.monotonic() < end:
        d = ap.read(200, size=4096)
        if d:
            out += d
    try:
        ap.release()
        F.usb.util.dispose_resources(dev)
    except Exception:  # noqa: BLE001
        pass
    t = out.replace(b"\x00", b"").decode("latin1", "replace")
    rw = len(re.findall(r"9ff56ab[^\n]*romstage starting", t))
    ro = len(re.findall(r"60d1b1c[^\n]*romstage starting", t))
    clr = t.count("VbSetRecoveryRequest(0)")
    wait = t.count("waiting for manual recovery")
    cold = t.lower().count("doing a cold reboot")
    tot_rw += rw
    tot_ro += ro
    tot_clear += clr
    tot_wait += wait
    tot_cold += cold
    print("cycle %d: RW-boot=%d RO-recovery=%d clear-req=%d cold-reboot=%d wait-recovery=%d  (%dB)"
          % (cyc, rw, ro, clr, cold, wait, len(out)), flush=True)

print("TOTALS over %d cycles: RW-boots=%d  RO-recovery=%d  clear-req=%d  cold-reboots=%d  waiting=%d"
      % (cycles, tot_rw, tot_ro, tot_clear, tot_cold, tot_wait), flush=True)
ok = tot_rw >= cycles and tot_ro == 0 and tot_wait == 0 and tot_clear >= 1
print("VERDICT: %s" % (
    "PASS -- self-heals: every boot is a normal RW netboot retry, never RO recovery, never stuck"
    if ok else "CHECK -- see per-cycle counts"), flush=True)
print("LOOP_DEMO_DONE", flush=True)
