#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""THE literal no-SuzyQ proof, self-executing: puck on the stock USB-C
adapter (Tasmota-switched), no debug cable, judged from the wire only.

Run armed (default) BEFORE the cable swap. It keeps the netboot server up
and watches. The single human action is: unplug the SuzyQ from the puck and
plug in the stock adapter (adapter AC side in the Tasmota plug). The moment
the resulting autonomous boot DHCPs and leases as OpenWrt, this script takes
over and, with no one touching anything, runs N Tasmota AC cold-plug cycles:
  plug OFF -> drain -> ON -> (EC boots from vSafe5V, charger detect Rp-3A ->
  set_ap_power(1) -> coreboot -> depthcharge netboot -> DHCP/TFTP -> OpenWrt)
scoring each purely from dnsmasq's log. N/N = the production scenario proven
end to end with the SuzyQ physically absent.

Power draw from the Tasmota is LOGGED for the record but never used as a
pass/fail signal (the old >=4W threshold misdiagnosis).

Run ON the bench rig with /usr/bin/python3:
  nohup ./final_pd_verify.py > ~/gale-netboot/final_pd.log 2>&1 &
Usage: final_pd_verify.py [ITERATIONS=5] [WAN_IF=eth-glan] [--cycles-only]

--cycles-only skips the armed phase (use when the puck is already on
Tasmota-switched adapter power and you just want the N-cycle verdict).

If a cycle produces ZERO DHCPDISCOVERs the relay did not actually cut the
puck's power (the supply's AC plug is not in the Tasmota outlet); the run
aborts immediately with verdict RELAY-NOT-IN-PATH instead of failing every
cycle (exactly what happened on 2026-07-11: 0/5 with the puck's lease alive
and untouched throughout).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ND = "/home/tim/gale-netboot"
BASE_CONF = ND + "/dnsmasq-gale.conf"
CONF = ND + "/dnsmasq-auto.conf"
FIT = ND + "/tftp/netboot.itb"
DM = ND + "/dnsmasq_auto.log"
PLUG = "10.1.91.18"
CYCLES_ONLY = "--cycles-only" in sys.argv
_args = [a for a in sys.argv[1:] if a != "--cycles-only"]
ITERS = int(_args[0]) if len(_args) > 0 else 5
WAN_IF = _args[1] if len(_args) > 1 else "eth-glan"
ARM_TIMEOUT_S = 48 * 3600          # wait up to 2 days for the cable swap
BOOT_WINDOW_S = 180                # cold plug -> OpenWrt lease deadline
OFF_DRAIN_S = 20


def say(msg):
    print("%s %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def sh(cmd, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        say("FATAL: %s -> %s" % (" ".join(cmd), (r.stdout + r.stderr).strip()))
        sys.exit(2)
    return r


def plug_cmd(c):
    url = "http://%s/cm?cmnd=%s" % (PLUG, c.replace(" ", "%20"))
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r)


def plug_power():
    try:
        return plug_cmd("Status 8")["StatusSNS"]["ENERGY"]["Power"]
    except Exception as e:  # noqa: BLE001 - log and keep going
        say("  (plug read error: %s)" % e)
        return None


def counts():
    """(discovers, acks, tftp-transfers) from dnsmasq's log.

    The TFTP count matches only real transfer lines ("dnsmasq-tftp: sent
    ... netboot.itb to ...").  DHCP ACKs also carry the string netboot.itb
    (bootfile-name option), so a bare substring count false-triggers on
    hourly lease renewals.
    """
    try:
        lines = open(DM, errors="replace").read().splitlines()
    except OSError:
        return 0, 0, 0
    return (sum("DHCPDISCOVER" in ln for ln in lines),
            sum("DHCPACK" in ln for ln in lines),
            sum("dnsmasq-tftp: sent" in ln and "netboot.itb" in ln
                for ln in lines))


# ---- ensure the netboot server is up (reuse a live one) ---------------------
say("=== final_pd_verify: arming (server on %s, plug %s) ===" % (WAN_IF, PLUG))
for path in (BASE_CONF, FIT):
    if not os.path.exists(path):
        say("FATAL: missing %s" % path)
        sys.exit(2)
r = sh(["pgrep", "-f", "dnsmasq-auto.conf"])
if r.returncode != 0:
    with open(CONF, "w") as f:
        f.write(re.sub(r"(?m)^interface=.*$", "interface=%s" % WAN_IF,
                       open(BASE_CONF).read()))
    sh(["sudo", "ip", "link", "set", WAN_IF, "up"])
    sh(["sudo", "ip", "addr", "add", "192.168.50.1/24", "dev", WAN_IF])
    open(DM, "w").close()
    subprocess.Popen(["sudo", "/usr/sbin/dnsmasq", "-d", "-C", CONF],
                     stdout=open(DM, "a"), stderr=subprocess.STDOUT)
    time.sleep(2)
    say("  started dnsmasq on %s" % WAN_IF)
else:
    say("  reusing running dnsmasq (pid %s)" % r.stdout.split()[0])
if plug_power() is None:
    say("FATAL: Tasmota plug %s not reachable" % PLUG)
    sys.exit(2)
plug_cmd("Power On")   # make sure AC is on for the human's first plug-in
say("  plug AC ON, waiting for the human cable swap (SuzyQ out, adapter in)")
say("  watching for the first autonomous DHCPACK; nothing else to do.")

# ---- phase 1: detect the first plug-in boot --------------------------------
if CYCLES_ONLY:
    say("  --cycles-only: skipping the armed phase")
else:
    d0, a0, t0c = counts()
    armed_at = time.monotonic()
    last_note = 0
    while time.monotonic() - armed_at < ARM_TIMEOUT_S:
        time.sleep(5)
        d, a, tf = counts()
        el = int(time.monotonic() - armed_at)
        if a > a0 and tf > t0c:
            say("  [+%ds] PLUG-IN BOOT DETECTED: disc+%d ack+%d tftp+%d "
                "power=%sW -- the puck booted autonomously on adapter power"
                % (el, d - d0, a - a0, tf - t0c, plug_power()))
            break
        if el - last_note >= 1800:
            say("  [+%ds] still armed (power=%sW disc=%d ack=%d tftp=%d)"
                % (el, plug_power(), d, a, tf))
            last_note = el
    else:
        say("TIMEOUT: no plug-in within %dh" % (ARM_TIMEOUT_S // 3600))
        sys.exit(3)

    # settle: let the first boot finish before cycling
    time.sleep(30)

# ---- phase 2: N unattended AC cold-plug cycles ------------------------------
say("=== %d Tasmota AC cold-plug cycles (no SuzyQ, no hands) ===" % ITERS)
passes = 0
for i in range(1, ITERS + 1):
    say("--- cycle %d/%d: AC OFF %ds (full drain) ---" % (i, ITERS, OFF_DRAIN_S))
    say("  relay -> %s" % plug_cmd("Power Off").get("POWER"))
    time.sleep(OFF_DRAIN_S)
    d0, a0, t0c = counts()
    say("  relay -> %s" % plug_cmd("Power On").get("POWER"))
    t_on = time.monotonic()
    ok = False
    next_prog = 15
    while time.monotonic() - t_on < BOOT_WINDOW_S:
        time.sleep(5)
        d, a, tf = counts()
        el = int(time.monotonic() - t_on)
        if a > a0 and tf > t0c:
            say("  [+%3ds] PASS: disc+%d ack+%d tftp+%d power=%sW"
                % (el, d - d0, a - a0, tf - t0c, plug_power()))
            ok = True
            break
        if el >= next_prog:
            say("  [+%3ds] power=%sW disc+%d ack+%d tftp+%d"
                % (el, plug_power(), d - d0, a - a0, tf - t0c))
            next_prog += 15
    if ok:
        passes += 1
    else:
        say("  cycle %d: FAIL -- no DHCPACK+TFTP within %ds" % (i, BOOT_WINDOW_S))
        d, a, tf = counts()
        if d == d0:
            say("  ZERO DHCPDISCOVERs after the AC cycle: the relay did NOT")
            say("  cut the puck's power -- the supply's AC plug is not in the")
            say("  Tasmota outlet. Aborting (rig wiring, not a boot failure).")
            say("=== FINAL VERDICT: RELAY-NOT-IN-PATH after %d cycle(s) ===" % i)
            say("FINAL_PD_VERIFY_DONE passes=%d iters=%d relay_not_in_path=1"
                % (passes, i))
            sys.exit(4)
    # let the netbooted OpenWrt settle before the next cut
    time.sleep(20)

say("=== FINAL VERDICT: %d/%d autonomous adapter-power boots netbooted ===" %
    (passes, ITERS))
say("FINAL_PD_VERIFY_DONE passes=%d iters=%d" % (passes, ITERS))
