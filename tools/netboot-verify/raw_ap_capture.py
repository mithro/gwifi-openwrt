#!/usr/bin/env python3
# Raw read of the AP serial console (if1) for N seconds -- no EC/power control,
# just observe what the (already-powered) AP is emitting. Run with /usr/bin/python3.
import re
import sys
import time

sys.path.insert(0, "/home/tim/local/gwifi/gwifi-openwrt/tools")
import flash_puck_usb as F  # noqa: E402

secs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
log = F.Log(None)
dev = F.open_device(log)
ap = F.Console(dev, "ap", log)

start = time.monotonic()
end = start + secs
next_prog = start + 30
out = b""
while time.monotonic() < end:
    d = ap.read(200, size=4096)
    if d:
        out += d
    if time.monotonic() >= next_prog:
        t = out.replace(b"\x00", b"").decode("latin1", "replace")
        print("  [+%3ds] %d bytes, %d boot(s), %d cold-reboot(s)"
              % (int(time.monotonic() - start), len(out),
                 t.count("verstage starting"), t.lower().count("doing a cold reboot")), flush=True)
        next_prog += 30
ap.release()

txt = out.replace(b"\x00", b"").decode("latin1", "replace")
with open("/home/tim/gale-netboot/ap_raw.txt", "w") as f:
    f.write(txt)
rw_boots = len(re.findall(r"9ff56ab[^\n]*romstage starting", txt))
ro_boots = len(re.findall(r"60d1b1c[^\n]*romstage starting", txt))
print("captured %d bytes over %ds" % (len(out), secs))
print("real boots (verstage)     : %d" % txt.count("verstage starting"))
print("  RW normal boots (9ff56ab): %d  (netboot->eMMC retry cycles)" % rw_boots)
print("  RO recovery boots (60d1b1c): %d  (want 0 -- fix keeps loop in RW)" % ro_boots)
print("cold reboot (Doing a cold): %d" % txt.lower().count("doing a cold reboot"))
print("VbSetRecoveryRequest(0)   : %d  (NOT_REQUESTED -- my fix on fixed disk)" % txt.count("VbSetRecoveryRequest(0)"))
print("VbSetRecoveryRequest(91)  : %d  (RW_NO_KERNEL latch -- want 0 now)" % txt.count("VbSetRecoveryRequest(91)"))
print("waiting for manual recovery: %d  (want 0)" % txt.count("waiting for manual recovery"))
print("---- last 1200 chars ----")
print(txt[-1200:])
print("RAW_AP_CAPTURE_DONE")
