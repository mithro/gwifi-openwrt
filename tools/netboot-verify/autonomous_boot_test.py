#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Autonomous-boot equivalence test: prove the AP netboots from the EC's
cold-boot parked state, triggered exactly like a charger would.

Background (from the gale EC source): on real charger power the EC calls
pd_set_input_current_limit(5V, >2.5A) -> set_ap_power(1). The console command
`gale power on` calls the SAME set_ap_power(1) (board.c command_power), so
running it against a freshly cold-booted, still-parked, RO, unlocked EC
exercises the identical rails-up path -- but with the SuzyQ attached we get
the AP console + EC state as evidence. The only link this cannot test is the
CC-line charger detect itself (evidenced separately by the blue LED on the
stock adapter).

What the old pd_netboot_test.py got wrong (and this fixes):
  - ">=4W means booting" was never calibrated; an idle netboot loop can sit
    well under 4W. Here power draw is not used as a signal at all.
  - carrier was treated as "AP is running", but SYS_PWR_EN defaults HIGH at
    EC boot (gpio.inc), powering the PHY even when parked. Ignored here.
  - it trusted eth-gwan to be the puck's WAN. Here tcpdump watches BOTH
    dongles, so a swapped-interface bug is caught, not silently fatal.

EC lock gotcha (discovered by this test's run 2): WP_L is sensed from the
SYS_PWR domain, so `gale power off` (which drops SYS_PWR_EN) locks the EC
and the console power path stays refused until an EC cold reboot restores
the SYS_PWR_EN=high default. The charger path (pd_set_input_current_limit)
has no lock gate, so real-adapter operation is unaffected.

Run ON THE RIG with /usr/bin/python3 (needs the pyusb tool + sudo).
Usage: autonomous_boot_test.py [WATCH_S] [WAN_IF]
  WAN_IF: which dongle the netboot server binds (default eth-gwan; run 1 on
  rpi4-gwifi proved that bench has the puck's netboot port on eth-glan).
  WAN_IF=none: NO netboot server -- proves the fallback path instead: netboot
  must time out, try eMMC, and (if eMMC has no bootable kernel) reboot-retry
  forever. Verdict counts boot cycles + fall-through markers on the console.
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
AP_OUT = ND + "/ap_auto.txt"
TD = {"eth-gwan": ND + "/tcpdump_auto_gwan.log",
      "eth-glan": ND + "/tcpdump_auto_glan.log"}
WATCH_S = int(sys.argv[1]) if len(sys.argv) > 1 else 240
WAN_IF = sys.argv[2] if len(sys.argv) > 2 else "eth-gwan"
NO_SERVER = WAN_IF == "none"
# Optional: force this dongle admin-DOWN for the whole run (kills link on the
# puck port it is cabled to). Lets us reproduce a single-port-cabled bench:
# run 4 suggested depthcharge's ipq40xx TX path wedges when BOTH puck ports
# have link (rpi3b, single-cabled, netboots fine; rpi4, dual-cabled, hangs
# RX-only in dhcp_send_packet -- the known hang in netboot.c).
DOWN_IF = sys.argv[3] if len(sys.argv) > 3 else None
RAILS = ("VDD_3P3_EN", "VDD_3P3_2G_EN", "VDD_1P8_EN", "VDD_1P35_EN",
         "VDD_1P1_CPU_EN")


def say(msg):
    print(msg, flush=True)


def sh(cmd, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    say("  $ %s  ->  %s" % (" ".join(cmd), out if out else "(ok)"))
    if check and r.returncode != 0:
        say("FATAL: command failed")
        sys.exit(2)
    return r.returncode


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


def rails_state(gpioget_text):
    """Map rail name -> 0/1 from `gpioget` output."""
    state = {}
    for name in RAILS + ("SYS_PWR_EN",):
        m = re.search(r"([01])\*?\s+%s\b" % re.escape(name), gpioget_text)
        state[name] = int(m.group(1)) if m else None
    return state


# ---- [0] preflight: netboot server on eth-gwan, sniffers on BOTH dongles ---
say("=== [0] preflight: server assets + interfaces (serving on %s) ===" % WAN_IF)
if not NO_SERVER:
    for path in (BASE_CONF, FIT):
        if not os.path.exists(path):
            say("FATAL: missing %s" % path)
            sys.exit(2)
    # bench-local conf: same as the base conf but bound to WAN_IF
    base = open(BASE_CONF).read()
    with open(CONF, "w") as f:
        f.write(re.sub(r"(?m)^interface=.*$", "interface=%s" % WAN_IF, base))
say("  netboot FIT: %s (%d bytes)" % (FIT, os.path.getsize(FIT)))
for f in (DM,) + tuple(TD.values()):
    open(f, "w").close()
try:
    os.remove(LEASES)
except FileNotFoundError:
    pass
sh(["sudo", "pkill", "-f", "dnsmasq-gale.conf"])
sh(["sudo", "pkill", "-f", "dnsmasq-auto.conf"])
if DOWN_IF is not None and DOWN_IF in TD:
    del TD[DOWN_IF]
for ifc in TD:
    sh(["sudo", "ip", "link", "set", ifc, "up"])
    sh(["sudo", "ip", "addr", "del", "192.168.50.1/24", "dev", ifc])
if DOWN_IF:
    say("  forcing %s DOWN (single-port-cabled experiment)" % DOWN_IF)
    sh(["sudo", "ip", "link", "set", DOWN_IF, "down"], check=True)
sniffers = [subprocess.Popen(
    ["sudo", "timeout", str(WATCH_S + 120), "tcpdump", "-i", ifc, "-n", "-l",
     "udp port 67 or udp port 68 or udp port 69"],
    stdout=open(TD[ifc], "w"), stderr=subprocess.STDOUT) for ifc in TD]
if NO_SERVER:
    say("  NO netboot server (fallback-proof mode): DHCP must go unanswered")
else:
    sh(["sudo", "ip", "addr", "add", "192.168.50.1/24", "dev", WAN_IF], check=True)
    dns = subprocess.Popen(["sudo", "/usr/sbin/dnsmasq", "-d", "-C", CONF],
                           stdout=open(DM, "w"), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if count(DM, "TFTP root is") or count(DM, "DHCP, IP range"):
            break
        if dns.poll() is not None:
            say("FATAL: dnsmasq exited: %s" % open(DM, errors="replace").read()[:400])
            sys.exit(2)
        time.sleep(0.5)
    else:
        say("FATAL: dnsmasq did not report startup in 8s: %s"
            % open(DM, errors="replace").read()[:400])
        sys.exit(2)
    say("  dnsmasq up (DHCP range + TFTP root confirmed in log)")

# ---- [1] EC pre-state: must be the autonomous cold-boot parked state -------
say("=== [1] EC pre-state (want: RO, unlocked, rails DOWN) ===")
log = F.Log(None)
dev = F.open_device(log)
ec = F.Console(dev, "ec", log)
ec.sync()
sysinfo = ec.cmd("sysinfo")
say("  " + " | ".join(l.strip() for l in sysinfo.splitlines()
                      if any(k in l for k in ("Copy", "Jumped", "Flags"))))
pdstate = ec.cmd("pd 0 state")
say("  " + next((l.strip() for l in pdstate.splitlines() if "Port" in l), "?"))
pre = rails_state(ec.cmd("gpioget"))
say("  rails pre : %s" % pre)
if any(pre[r] for r in RAILS):
    # Do NOT `gale power off` here: set_ap_power_off() also drops SYS_PWR_EN,
    # and WP_L is sensed from the SYS_PWR domain -- so power-off makes
    # system_is_locked() true and the console can never power the AP back on
    # (proven on rpi4-gwifi 2026-07-10). Only an EC cold reboot (which
    # restores SYS_PWR_EN's GPIO_OUT_HIGH default) recovers. Keep this script
    # single-USB-session: tell the operator to reboot the EC and rerun.
    say("FATAL: AP rails already up. Cold-reboot the EC first (restores the")
    say("  parked+unlocked default state), then rerun:")
    say("    /usr/bin/python3 ../flash_puck_usb.py ec reboot --deadline 2")
    sys.exit(2)

# ---- [2] the charger-equivalent trigger ------------------------------------
say("=== [2] trigger: `gale power on` (== pd charger path set_ap_power(1)) ===")
resp = ec.cmd("gale power on", until=lambda t: "OK" in t)
say("  EC ack: %r" % resp.strip().replace("\r", ""))
deadline = time.monotonic() + 3
post = {}
while time.monotonic() < deadline:
    post = rails_state(ec.cmd("gpioget"))
    if all(post[r] == 1 for r in RAILS):
        break
    time.sleep(0.3)
else:
    say("FATAL: rails did not all rise within 3s: %s" % post)
    sys.exit(2)
say("  rails post: %s  (ALL UP)" % post)
t0 = time.monotonic()
ec.release()

# ---- [3] watch: AP console + DHCP/TFTP on both dongles ---------------------
say("=== [3] watch %ds: AP console + dnsmasq + per-dongle DHCP ===" % WATCH_S)
ap = F.Console(dev, "ap", log)
raw = b""
verdict_ow = ""
next_prog = 10
while time.monotonic() - t0 < WATCH_S:
    chunk = ap.read(200, size=4096)
    if chunk:
        raw += chunk
    el = time.monotonic() - t0
    if el >= next_prog:
        txt = raw.replace(b"\x00", b"").decode("latin1", "replace")
        disc = count(DM, "DHCPDISCOVER")
        ack = count(DM, "DHCPACK")
        tftp = count(DM, "netboot.itb")
        gwan = count(TD.get("eth-gwan", ""), "BOOTP/DHCP")
        glan = count(TD.get("eth-glan", ""), "BOOTP/DHCP")
        verdict_ow = openwrt_lease()
        say("  [+%3ds] ap=%6dB boots=%d | dhcp disc=%d ack=%d tftp=%d | "
            "wire gwan=%d glan=%d %s"
            % (int(el), len(raw), txt.count("verstage starting"), disc, ack,
               tftp, gwan, glan, ("OPENWRT=" + verdict_ow) if verdict_ow else ""))
        if verdict_ow:
            break
        next_prog += 10
ap.release()

txt = raw.replace(b"\x00", b"").decode("latin1", "replace")
with open(AP_OUT, "w") as f:
    f.write(txt)

# ---- [4] verdict ------------------------------------------------------------
say("=== [4] verdict ===")
disc = count(DM, "DHCPDISCOVER")
tftp = count(DM, "netboot.itb")
glan_dhcp = count(TD.get("eth-glan", ""), "BOOTP/DHCP")
say("  AP console bytes : %d (saved to %s)" % (len(raw), AP_OUT))
say("  verstage starts  : %d" % txt.count("verstage starting"))
say("  depthcharge start: %d" % txt.count("Starting depthcharge"))
say("  DHCPDISCOVER     : %d   DHCPACK: %d" % (disc, count(DM, "DHCPACK")))
say("  TFTP netboot.itb : %d" % tftp)
say("  OpenWrt lease    : %s" % (openwrt_lease() or "(none)"))
if NO_SERVER:
    cycles = txt.count("verstage starting")
    reboots = txt.lower().count("doing a cold reboot")
    fallthru = (txt.count("falling through to vboot")
                + txt.count("no link; letting caller fall through"))
    stuck_rec = txt.count("waiting for manual recovery")
    wire = sum(count(TD[i], "BOOTP/DHCP") for i in TD)
    say("  boot cycles (verstage) : %d" % cycles)
    say("  cold reboots           : %d" % reboots)
    say("  netboot->vboot fallthru: %d" % fallthru)
    say("  manual-recovery stalls : %d (want 0)" % stuck_rec)
    say("  unanswered DHCP on wire: %d" % wire)
    emmc_os = ("Linux version" in txt or "br-lan" in txt
               or "UBI: attached" in txt)
    if stuck_rec:
        say("  => FAIL-FALLBACK: latched into manual recovery (RW_NVRAM?)")
    elif fallthru and emmc_os:
        say("  => PASS-FALLBACK-EMMC: netboot went unanswered (%d wire "
            "DHCPs), fell through, and the eMMC OS booted" % wire)
    elif cycles >= 2 and reboots >= 1:
        say("  => PASS-FALLBACK-RETRY: netboot times out, falls through, "
            "eMMC has no kernel, and the puck reboot-retries autonomously "
            "(%d cycles in %ds)" % (cycles, WATCH_S))
    else:
        say("  => UNDECIDED-FALLBACK: cycles=%d reboots=%d fallthru=%d -- "
            "read %s" % (cycles, reboots, fallthru, AP_OUT))
    say("  ---- last 800 chars of AP console ----")
    say(txt[-800:])
    say("AUTONOMOUS_BOOT_TEST_DONE")
    sys.exit(0)

other_if = next((i for i in TD if i != WAN_IF), None)
other_dhcp = count(TD[other_if], "BOOTP/DHCP") if other_if else 0
if glan_dhcp and WAN_IF != "eth-glan":
    say("  !! DHCP seen on eth-glan -- interface identity bug in earlier tests")
if openwrt_lease():
    say("  => PASS: parked RO EC + set_ap_power(1) -> netboot -> OpenWrt, "
        "no EC reboot, no RW jump, no human")
elif tftp:
    say("  => PARTIAL: TFTP served but OpenWrt lease not seen -- read %s" % AP_OUT)
elif disc:
    say("  => PARTIAL: DHCP ran but no TFTP -- check dnsmasq log %s" % DM)
elif other_dhcp:
    say("  => WRONG-IF: AP booted and is DHCPing on %s, but the server is on "
        "%s -- rerun with WAN_IF=%s" % (other_if, WAN_IF, other_if))
elif len(raw) == 0:
    say("  => FAIL: rails up but AP console silent and no DHCP anywhere -- "
        "AP did not reach netboot")
else:
    say("  => FAIL: AP booted but never reached DHCP -- read %s" % AP_OUT)
say("  ---- last 800 chars of AP console ----")
say(txt[-800:])
say("AUTONOMOUS_BOOT_TEST_DONE")
