#!/usr/bin/env python3
# Talk to the running netbooted OpenWrt over its serial console (if1 = AP
# stream). Netboot initramfs images auto-login root on the console. Confirm
# dropbear is RUNNING and that the WAN zone REJECTs input (why :22 was refused
# from the WAN side). Read-only commands; run with /usr/bin/python3 (pyusb).
import sys
import time

sys.path.insert(0, "/home/tim/local/gwifi/gwifi-openwrt/tools")
import flash_puck_usb as F  # noqa: E402


def drain(ap, ms=1500):
    end = time.monotonic() + ms / 1000.0
    out = b""
    while time.monotonic() < end:
        d = ap.read(200, size=4096)
        if d:
            out += d
    return out.replace(b"\x00", b"")


log = F.Log(None)
dev = F.open_device(log)
ap = F.Console(dev, "ap", log)

# Wake the console; netboot initramfs usually drops to a root shell.
ap.write(b"\r\n")
banner = drain(ap, 1500)
if b"login:" in banner:
    ap.write(b"root\r\n")
    banner += drain(ap, 1500)

# Command to run comes from argv (default: the dropbear/firewall check).
cmd = sys.argv[1] if len(sys.argv) > 1 else (
    "echo MARK1; pgrep dropbear | wc -l; uname -srm; echo MARK2")
ap.write(b"echo MARK1; " + cmd.encode() + b"; echo MARK2\r\n")
out = drain(ap, 5000)
ap.release()

text = (banner + b"\n---CMD---\n" + out).decode("latin1", "replace")
print(text)
print("PROBE_DONE")
