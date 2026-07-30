#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase-1 PD verification: prove the puck boots AUTONOMOUSLY on USB-C PD power
(no SuzyQ attached) and netboots OpenWrt.

The SuzyQ/CCD path (flash_puck_usb.py verify-boot, loop_demo) can only drive the
AP by telling the EC `gale power on` over the debug console -- it never exercises
the EC's *autonomous* power-up on real charger power. This does: it brings up the
netboot server on eth-gwan, does a clean PD power-cycle via the Tasmota plug
(full AC drain -> on), and watches four independent signals every 10s:

  plug power >=4W        -> AP is drawing power (booting/running), vs ~2W parked
  eth-gwan carrier=1     -> puck WAN PHY driven up (AP running)
  dnsmasq DHCPDISCOVER   -> puck asking for a netboot server
  dnsmasq 'netboot.itb'  -> TFTP of the FIT (netboot proceeding)
  lease hostname OpenWrt -> OpenWrt actually booted

Run on the rig (rpi3b-gwifi) with the puck on PD power and its WAN on eth-gwan.
Usage: pd_netboot_test.py [OFF_DRAIN_S] [WATCH_S]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ND = "/home/tim/gale-netboot"
PLUG = "10.1.91.18"
DM = ND + "/dnsmasq_pd.log"
TD = ND + "/tcpdump_pd.log"
LEASES = ND + "/leases"
CONF = ND + "/dnsmasq-gale.conf"
OFF_S = int(sys.argv[1]) if len(sys.argv) > 1 else 75
WATCH_S = int(sys.argv[2]) if len(sys.argv) > 2 else 210


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print("  $ %s  ->  %s" % (" ".join(cmd), out if out else "(ok)"), flush=True)
    return r.returncode


def plug(c):
    url = "http://%s/cm?cmnd=%s" % (PLUG, c.replace(" ", "%20"))
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r)


def power_w():
    try:
        return plug("Status 10")["StatusSNS"]["ENERGY"]["Power"]
    except Exception as e:  # noqa: BLE001 - report and keep polling
        print("    (plug read error: %s)" % e, flush=True)
        return None


def carrier():
    try:
        return open("/sys/class/net/eth-gwan/carrier").read().strip()
    except Exception:  # noqa: BLE001
        return "?"


def count(path, needle):
    try:
        return open(path, errors="replace").read().count(needle)
    except Exception:  # noqa: BLE001
        return 0


def openwrt_lease():
    try:
        for ln in open(LEASES, errors="replace"):
            if "OpenWrt" in ln:
                return ln.split()[2]
    except Exception:  # noqa: BLE001
        pass
    return ""


# ---- [1] netboot server up ------------------------------------------------
print("=== [1] netboot server up on eth-gwan (serving netboot.itb) ===", flush=True)
for f in (DM, TD):
    open(f, "w").close()
try:
    os.remove(LEASES)
except FileNotFoundError:
    pass
sh(["sudo", "pkill", "-f", "dnsmasq-gale.conf"])
sh(["sudo", "ip", "addr", "del", "192.168.50.1/24", "dev", "eth-gwan"])
sh(["sudo", "ip", "link", "set", "eth-gwan", "up"])
sh(["sudo", "ip", "addr", "add", "192.168.50.1/24", "dev", "eth-gwan"])
time.sleep(2)
subprocess.Popen(
    ["sudo", "timeout", str(OFF_S + WATCH_S + 60), "tcpdump",
     "-i", "eth-gwan", "-n", "-e", "-l", "-s0"],
    stdout=open(TD, "w"), stderr=subprocess.STDOUT)
subprocess.Popen(
    ["sudo", "/usr/sbin/dnsmasq", "-d", "-C", CONF],
    stdout=open(DM, "w"), stderr=subprocess.STDOUT)
time.sleep(3)
startup = open(DM, errors="replace").read()
hits = " | ".join(
    l.strip() for l in startup.splitlines()
    if any(k in l for k in ("IP range", "no address", "started", "TFTP")))
print("  dnsmasq: " + (hits[:300] if hits else startup[:200].replace("\n", " ")),
      flush=True)

# ---- [2] clean PD power-cycle --------------------------------------------
print("=== [2] clean PD power-cycle: plug OFF %ds (full AC drain) -> ON ===" % OFF_S,
      flush=True)
print("  baseline power = %sW" % power_w(), flush=True)
plug("Power Off")
time.sleep(OFF_S)
plug("Power On")
print("  plug ON @ t0 -- watching for AUTONOMOUS boot (no SuzyQ attached)...",
      flush=True)

# ---- [3] monitor ----------------------------------------------------------
print("=== [3] monitor ~%ds ===" % WATCH_S, flush=True)
peak = 0
t0 = time.time()
verdict_ow = ""
while time.time() - t0 < WATCH_S:
    time.sleep(10)
    p = power_w()
    if isinstance(p, (int, float)):
        peak = max(peak, p)
    car = carrier()
    disc = count(DM, "DHCPDISCOVER")
    ack = count(DM, "DHCPACK")
    tftp = count(DM, "netboot.itb")
    owip = openwrt_lease()
    flags = []
    if isinstance(p, (int, float)) and p >= 4:
        flags.append("AP-POWER")
    if car == "1":
        flags.append("WAN-UP")
    if disc:
        flags.append("DHCP")
    if tftp:
        flags.append("TFTP")
    if owip:
        flags.append("OPENWRT=" + owip)
    print("  [+%3ds] power=%3sW carrier=%s discover=%d ack=%d tftp=%d  %s"
          % (int(time.time() - t0), p, car, disc, ack, tftp, " ".join(flags)),
          flush=True)
    if owip:
        verdict_ow = owip
        break

# ---- verdict --------------------------------------------------------------
print("=== VERDICT ===", flush=True)
print("  peak power   : %sW  (>=4W => the AP powered on autonomously on PD)" % peak,
      flush=True)
print("  DHCPDISCOVER : %d   (puck asked for netboot)" % count(DM, "DHCPDISCOVER"),
      flush=True)
print("  TFTP FIT     : %d   (netboot.itb served)" % count(DM, "netboot.itb"),
      flush=True)
print("  OpenWrt lease: %s" % (verdict_ow or "(none yet)"), flush=True)
if verdict_ow:
    v = "PASS: puck booted on PD with NO SuzyQ and netbooted OpenWrt end-to-end"
elif peak >= 4:
    v = ("PARTIAL: AP powered on autonomously on PD, but no OpenWrt lease yet "
         "(check DHCP/TFTP counts + dnsmasq_pd.log)")
else:
    v = "PARKED: AP stayed ~2W after a clean PD power-cycle (did not boot on PD)"
print("  => " + v, flush=True)
print("PD_NETBOOT_TEST_DONE", flush=True)
