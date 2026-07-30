#!/usr/bin/env python3
"""Power-cycle the gale via its Tasmota plug and watch real-power draw as an
AP-boot signal -- no EC/console/SuzyQ needed.

On a PD-only gale, ~2W means only the EC + WAN PHY are powered (AP OFF); a
booting/running IPQ4019 AP draws ~5-12W. A short power blip can leave a parked
EC parked, so this drains AC for OFF_S (default 60s) to force a clean EC reboot,
then polls real power every 10s. Prints progress lines and a PEAK verdict.

Usage: plug_power_probe.py [PLUG_HOST] [OFF_S] [POLL_S]
"""
import sys
import time
import json
import urllib.request

PLUG = sys.argv[1] if len(sys.argv) > 1 else "10.1.91.18"
OFF = int(sys.argv[2]) if len(sys.argv) > 2 else 60
POLL = int(sys.argv[3]) if len(sys.argv) > 3 else 150
ON_THRESH_W = 4  # >= this real-power draw => the AP is actually booting


def cmd(c):
    url = "http://%s/cm?cmnd=%s" % (PLUG, c.replace(" ", "%20"))
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r)


def power_w():
    try:
        return cmd("Status 10")["StatusSNS"]["ENERGY"]["Power"]
    except Exception as e:  # noqa: BLE001 - report and keep polling
        print("  (plug read error: %s)" % e, flush=True)
        return None


print("plug=%s  drain=%ds  poll=%ds  AP-on threshold=%dW" % (PLUG, OFF, POLL, ON_THRESH_W), flush=True)
print("baseline power = %sW" % power_w(), flush=True)
print("plug OFF for %ds (full AC drain to reset a parked EC)..." % OFF, flush=True)
cmd("Power Off")
time.sleep(OFF)
print("plug ON -- watching for the AP to draw power:", flush=True)
cmd("Power On")

peak = 0
for i in range(POLL // 10):
    time.sleep(10)
    p = power_w()
    if isinstance(p, (int, float)):
        peak = max(peak, p)
    tag = "  <-- AP BOOTING (>=%dW)" % ON_THRESH_W if isinstance(p, (int, float)) and p >= ON_THRESH_W else ""
    print("  [+%3ds] power=%sW%s" % ((i + 1) * 10, p, tag), flush=True)

booted = peak >= ON_THRESH_W
print("PEAK = %sW => %s" % (
    peak,
    "AP POWERED (a boot happened) -- now run reboot_loop_validate.sh" if booted
    else "AP STAYED OFF (~2W EC+PHY only) -- parked EC not cleared by AC drain"), flush=True)
print("PLUG_POWER_PROBE_DONE (booted=%d)" % (1 if booted else 0), flush=True)
sys.exit(0 if booted else 1)
