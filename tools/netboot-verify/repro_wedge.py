#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce the intermittent netboot RX-only wedge with console visibility.

Loops: EC cold reboot -> autonomous_boot_test (dual-port, server on WAN_IF)
-> classify. Stops the moment a run fails to DHCP (the wedge), preserving
that run's early-attach AP console as ap_wedge_<i>.txt. PASS runs just loop.

Run ON THE BENCH with /usr/bin/python3.
Usage: repro_wedge.py [ITERATIONS=8] [WAN_IF=eth-glan]
"""
import shutil
import subprocess
import sys
import time

ND = "/home/tim/gale-netboot"
TOOLS = "/home/tim/local/gwifi/gwifi-openwrt/tools"
ITERS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
WAN_IF = sys.argv[2] if len(sys.argv) > 2 else "eth-glan"
WATCH_S = 120


def say(msg):
    print(msg, flush=True)


def run(cmd, timeout):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


for i in range(1, ITERS + 1):
    say("=== iteration %d/%d: EC cold reboot ===" % (i, ITERS))
    # The EC drops off USB mid-command; a non-zero exit is expected.
    run(["/usr/bin/python3", TOOLS + "/flash_puck_usb.py", "ec", "reboot",
         "--deadline", "2"], timeout=30)
    time.sleep(6)
    st = run(["/usr/bin/python3", TOOLS + "/flash_puck_usb.py", "ec", "sysinfo"],
             timeout=30)
    if "Copy:   RO" not in st.stdout or "unlocked" not in st.stdout:
        say("FATAL: EC not in fresh RO/unlocked state after reboot:\n" + st.stdout)
        sys.exit(2)

    log = "%s/repro_%02d.log" % (ND, i)
    say("  running autonomous_boot_test %ds %s -> %s" % (WATCH_S, WAN_IF, log))
    with open(log, "w") as f:
        subprocess.run(["/usr/bin/python3",
                        TOOLS + "/netboot-verify/autonomous_boot_test.py",
                        str(WATCH_S), WAN_IF],
                       stdout=f, stderr=subprocess.STDOUT,
                       timeout=WATCH_S + 120)
    txt = open(log, errors="replace").read()
    verdict = next((l.strip() for l in txt.splitlines() if l.startswith("  =>")),
                   "(no verdict)")
    say("  " + verdict)
    if "PASS" in verdict:
        continue
    # Wedge (or any non-PASS): preserve the evidence and stop.
    keep = "%s/ap_wedge_%02d.txt" % (ND, i)
    shutil.copy(ND + "/ap_auto.txt", keep)
    say("WEDGE CAUGHT on iteration %d -- console saved to %s" % (i, keep))
    say("REPRO_WEDGE_DONE caught=%d" % i)
    sys.exit(0)

say("no wedge in %d iterations -- all PASS" % ITERS)
say("REPRO_WEDGE_DONE caught=0")
