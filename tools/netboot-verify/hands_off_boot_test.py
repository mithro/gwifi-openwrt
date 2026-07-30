#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hands-off field replica: autonomous boots with ZERO USB contact after the
trigger, judged from the wire alone.

The closest software approximation of the production scenario (puck on a
plain 5V/3A supply, no SuzyQ): EC cold reboot -> one `gale power on` (the
same set_ap_power(1) the charger fires) -> then NOTHING touches the EC or AP
console until the verdict is in. Evidence is wire-only: dnsmasq DHCP/TFTP
log and the OpenWrt lease. This removes every harness perturbation the
wedged runs 3/4 had (AP-console attach + gpioget polling during early boot,
while the SBL reads the EC-shared SPI flash).

Run ON THE BENCH with /usr/bin/python3 (pyusb tool + sudo).
Usage: hands_off_boot_test.py [ITERATIONS=6] [WAN_IF=eth-glan] [WATCH_S=150]
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/tim/local/gwifi/gwifi-openwrt/tools")
import flash_puck_usb as F  # noqa: E402

ND = "/home/tim/gale-netboot"
BASE_CONF = ND + "/dnsmasq-gale.conf"
CONF = ND + "/dnsmasq-auto.conf"
FIT = ND + "/tftp/netboot.itb"
LEASES = ND + "/leases"
DM = ND + "/dnsmasq_auto.log"
TOOLS = "/home/tim/local/gwifi/gwifi-openwrt/tools"
ITERS = int(sys.argv[1]) if len(sys.argv) > 1 else 6
WAN_IF = sys.argv[2] if len(sys.argv) > 2 else "eth-glan"
WATCH_S = int(sys.argv[3]) if len(sys.argv) > 3 else 150


def say(msg):
    print(msg, flush=True)


def sh(cmd, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        say("FATAL: %s -> %s" % (" ".join(cmd), (r.stdout + r.stderr).strip()))
        sys.exit(2)
    return r


def count(path, needle):
    try:
        return open(path, errors="replace").read().count(needle)
    except OSError:
        return 0


def openwrt_lease():
    try:
        for ln in open(LEASES, errors="replace"):
            if "OpenWrt" in ln:
                return ln.split()[2]
    except OSError:
        pass
    return ""


# ---- server up once, reused across iterations -------------------------------
say("=== netboot server on %s (hands-off campaign, %d iterations) ===" %
    (WAN_IF, ITERS))
for path in (BASE_CONF, FIT):
    if not os.path.exists(path):
        say("FATAL: missing %s" % path)
        sys.exit(2)
with open(CONF, "w") as f:
    f.write(re.sub(r"(?m)^interface=.*$", "interface=%s" % WAN_IF,
                   open(BASE_CONF).read()))
sh(["sudo", "pkill", "-f", "dnsmasq-gale.conf"])
sh(["sudo", "pkill", "-f", "dnsmasq-auto.conf"])
sh(["sudo", "ip", "link", "set", "eth-gwan", "up"])
sh(["sudo", "ip", "link", "set", "eth-glan", "up"])
sh(["sudo", "ip", "addr", "del", "192.168.50.1/24", "dev", WAN_IF])
sh(["sudo", "ip", "addr", "add", "192.168.50.1/24", "dev", WAN_IF], check=True)

passes = 0
for i in range(1, ITERS + 1):
    say("=== iteration %d/%d ===" % (i, ITERS))
    # Fresh dnsmasq per iteration so lease/log state is per-boot.
    sh(["sudo", "pkill", "-f", "dnsmasq-auto.conf"])
    open(DM, "w").close()
    try:
        os.remove(LEASES)
    except FileNotFoundError:
        pass
    dns = subprocess.Popen(["sudo", "/usr/sbin/dnsmasq", "-d", "-C", CONF],
                           stdout=open(DM, "w"), stderr=subprocess.STDOUT)
    time.sleep(2)
    if dns.poll() is not None:
        say("FATAL: dnsmasq died: %s" % open(DM, errors="replace").read()[:300])
        sys.exit(2)

    # EC cold reboot -> parked default state. Tool exits non-zero (re-enum).
    subprocess.run(["/usr/bin/python3", TOOLS + "/flash_puck_usb.py",
                    "ec", "reboot", "--deadline", "2"],
                   capture_output=True, text=True, timeout=30)
    time.sleep(6)

    # ONE trigger command, then hands off: close USB entirely.
    log = F.Log(None)
    dev = F.open_device(log)
    ec = F.Console(dev, "ec", log)
    ec.sync()
    state = ec.cmd("sysinfo")
    if "Copy:   RO" not in state or "unlocked" not in state:
        say("FATAL: EC not in fresh parked state: %s" % state.strip())
        sys.exit(2)
    ec.cmd("gale power on", until=lambda t: "OK" in t)
    ec.release()
    try:
        usb_dev = dev
        import usb.util
        usb.util.dispose_resources(usb_dev)
    except Exception as e:  # noqa: BLE001 - dispose is best-effort
        say("  (usb dispose: %s)" % e)
    t0 = time.time()
    say("  [t0] power-on sent; ALL USB CLOSED; watching the wire only")

    verdict = ""
    next_prog = 15
    while time.time() - t0 < WATCH_S:
        time.sleep(5)
        el = int(time.time() - t0)
        ow = openwrt_lease()
        if ow:
            verdict = ow
            say("  [+%3ds] OpenWrt lease %s" % (el, ow))
            break
        if el >= next_prog:
            say("  [+%3ds] disc=%d ack=%d tftp=%d" %
                (el, count(DM, "DHCPDISCOVER"), count(DM, "DHCPACK"),
                 count(DM, "netboot.itb")))
            next_prog += 15
    if verdict:
        passes += 1
        say("  iteration %d: PASS (lease %s)" % (i, verdict))
    else:
        say("  iteration %d: FAIL -- no OpenWrt lease in %ds "
            "(disc=%d ack=%d tftp=%d)" %
            (i, WATCH_S, count(DM, "DHCPDISCOVER"), count(DM, "DHCPACK"),
             count(DM, "netboot.itb")))

say("=== HANDS-OFF CAMPAIGN: %d/%d autonomous boots reached OpenWrt ===" %
    (passes, ITERS))
say("HANDS_OFF_DONE passes=%d iters=%d" % (passes, ITERS))
