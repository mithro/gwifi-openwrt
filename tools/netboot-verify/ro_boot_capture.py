#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot the AP with the EC left in its CURRENT copy (RO by default, no sysjump)
and capture the AP console -- reproducing the autonomous PD boot path (where the
EC never jumps to RW) over CCD, so we can see WHERE it stalls.

The discriminating experiment: an RO-EC boot vs an RW-EC boot. If RO stalls
before netboot but RW netboots, the EC RO/RW state is the autonomous-boot
blocker. Run with /usr/bin/python3 (system pyusb).

Usage: ro_boot_capture.py [SECS] [ro|rw]
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/tim/local/gwifi/gwifi-openwrt/tools")
import flash_puck_usb as F  # noqa: E402

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 75
MODE = sys.argv[2] if len(sys.argv) > 2 else "ro"
ND = "/home/tim/gale-netboot"


def server_up():
    """Bring up DHCP+TFTP (serving netboot.itb) on eth-gwan so a reached netboot
    can complete; also sniff the WAN so we can see the puck's DHCP/ARP."""
    for f in (ND + "/dnsmasq_ro.log", ND + "/tcpdump_ro.log"):
        open(f, "w").close()
    try:
        os.remove(ND + "/leases")
    except FileNotFoundError:
        pass
    subprocess.run(["sudo", "pkill", "-f", "dnsmasq-gale.conf"])
    subprocess.run(["sudo", "ip", "addr", "del", "192.168.50.1/24", "dev", "eth-gwan"])
    subprocess.run(["sudo", "ip", "link", "set", "eth-gwan", "up"])
    subprocess.run(["sudo", "ip", "addr", "add", "192.168.50.1/24", "dev", "eth-gwan"])
    subprocess.Popen(
        ["sudo", "timeout", str(SECS + 60), "tcpdump", "-i", "eth-gwan",
         "-n", "-e", "-l", "-s0"],
        stdout=open(ND + "/tcpdump_ro.log", "w"), stderr=subprocess.STDOUT)
    subprocess.Popen(
        ["sudo", "/usr/sbin/dnsmasq", "-d", "-C", ND + "/dnsmasq-gale.conf"],
        stdout=open(ND + "/dnsmasq_ro.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(3)


print("=== bringing up netboot server on eth-gwan ===", flush=True)
server_up()

log = F.Log(None)
dev = F.open_device(log)
ec = F.Console(dev, "ec", log)
ec.sync()


def ec_cmd(c, wait=0.6):
    ec.drain()
    ec.write((c + "\r\n").encode())
    time.sleep(wait)
    return ec.read(200).decode("latin1", "replace")


print("=== EC state before boot ===", flush=True)
print(ec_cmd("sysinfo"), flush=True)

if MODE == "rw":
    print(">>> sysjump RW (EC RO->RW) ...", flush=True)
    ec.write(b"sysjump RW\r\n")
    time.sleep(4)
    # sysjump re-enumerates; reopen everything
    F.usb.util.dispose_resources(dev)
    time.sleep(2)
    dev = F.open_device(log)
    ec = F.Console(dev, "ec", log)
    ec.sync()
    print(ec_cmd("sysinfo"), flush=True)

print(">>> gale power off -> on  (EC copy stays %s)" % MODE.upper(), flush=True)
print(ec_cmd("gale power off", wait=1.5), flush=True)
print(ec_cmd("gale power on", wait=0.4), flush=True)
ec.release()

# Capture the AP console from power-on.
ap = F.Console(dev, "ap", log)
start = time.monotonic()
nextp = start + 15
out = b""
while time.monotonic() - start < SECS:
    d = ap.read(200, size=4096)
    if d:
        out += d
    if time.monotonic() >= nextp:
        t = out.replace(b"\x00", b"").decode("latin1", "replace")
        print("  [+%3ds] %5d B | coreboot=%d depthcharge=%d netboot=%d nolink=%d"
              % (int(time.monotonic() - start), len(out),
                 t.count("romstage starting"), t.count("Starting depthcharge"),
                 t.count("netboot: trying TFTP"), t.count("no link")), flush=True)
        nextp += 15
ap.release()
F.usb.util.dispose_resources(dev)

txt = out.replace(b"\x00", b"").decode("latin1", "replace")
open("/home/tim/gale-netboot/ro_boot_%s.txt" % MODE, "w").write(txt)
print("=== captured %d bytes (mode=%s) ===" % (len(out), MODE), flush=True)
for m in ["verstage starting", "romstage starting", "Starting depthcharge on gale",
          "netboot: trying TFTP", "net_wait_for_link", "no link", "DHCP",
          "TFTP", "no kernel", "Doing a cold reboot", "waiting for manual recovery"]:
    print("  %-34s : %d" % (m, txt.count(m)), flush=True)
print("---- last 1600 chars ----", flush=True)
print(txt[-1600:], flush=True)
print("RO_BOOT_CAPTURE_DONE mode=%s bytes=%d" % (MODE, len(out)), flush=True)
