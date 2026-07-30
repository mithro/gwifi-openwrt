#!/bin/bash
# Validate the netboot reboot-retry SELF-HEALING loop.
#
# The gale MUST be on NORMAL USB-C PD power (its stock adapter / a switched PD
# supply), NOT the USB-A SuzyQ rig -- only then does cold_reboot() reboot the AP
# autonomously (the SuzyQ rig gates AP power via the EC, so a SoC self-reset
# wedges instead). This script only sniffs the WAN and counts DHCP-discover
# BURSTS (optionally power-cycling the gale first via a Tasmota plug). Each boot
# cycle with no netboot server emits one burst; a working reboot-retry loop emits
# MANY evenly-spaced bursts. See ../../docs/reboot-retry-validation.md.
#
# Preconditions (else there is no loop to observe):
#   * reboot-retry firmware flashed (patches/vboot_reference-netboot-reboot-retry)
#   * NO netboot/DHCP server on this WAN segment (netboot must FAIL each cycle)
#   * eMMC blank / no bootable OS (the eMMC fallback must FAIL too)
#
# Usage: ./reboot_loop_validate.sh [IFACE] [DURATION_S] [MAC_PREFIX] [PLUG_HOST]
#   IFACE       WAN iface cabled to the gale WAN port  (default eth-gwan)
#   DURATION_S  sniff window in seconds                (default 300)
#   MAC_PREFIX  puck MAC filter                        (default 44:07:0b, gale OUI)
#   PLUG_HOST   optional Tasmota plug host/IP powering the gale's USB-C PD. If
#               given, the gale is power-cycled (off 5s, on) for a clean fresh
#               boot before sniffing; otherwise the sniff is fully passive.
set -u
IFACE="${1:-eth-gwan}"
DUR="${2:-300}"
MAC="${3:-44:07:0b}"
PLUG="${4:-}"
GAP=15              # a WAN-silent gap > GAP s delimits boot cycles
MINBURSTS=3         # >= this many evenly-spaced bursts => self-healing loop
PROGRESS_INTERVAL=30   # print a live status line this often during the sniff
CAP="$HOME/reboot-loop-cap.$$.txt"
: > "$CAP"

command -v tcpdump >/dev/null || { echo "FATAL: tcpdump not found"; exit 1; }
[ -e "/sys/class/net/$IFACE" ] || { echo "FATAL: no interface $IFACE"; exit 1; }

# Burst analysis, single source of truth. MODE=progress prints a one-line live
# count; MODE=final prints the per-burst breakdown + VERDICT and sets $?.
run_analysis() {  # $1 = progress|final ; reads $CAP
  grep -aiE "$MAC.*BOOTP/DHCP.*Request from" "$CAP" | awk '{print $1}' \
    | MODE="$1" GAP="$GAP" MINB="$MINBURSTS" python3 - <<'PY'
import os, sys
gap = float(os.environ["GAP"]); minb = int(os.environ["MINB"]); mode = os.environ["MODE"]
ts = sorted(float(x) for x in sys.stdin if x.strip())
bursts = []
for t in ts:
    if bursts and t - bursts[-1][-1] <= gap:
        bursts[-1].append(t)
    else:
        bursts.append([t])
if mode == "progress":
    print("%d DHCP frame(s) in %d burst(s)/boot-cycle(s)" % (len(ts), len(bursts)))
    sys.exit(0)
if not ts:
    print("  DHCP frames from the puck: 0")
    print("VERDICT: FAIL -- the puck emitted NO DHCP. It did not boot, the WAN is not")
    print("         cabled/carrier-down, or it is not PD-powered. (If a netboot server")
    print("         WAS present it may simply have netbooted successfully -- remove it.)")
    sys.exit(2)
print("  DHCP frames: %d in %d burst(s)" % (len(ts), len(bursts)))
for i, b in enumerate(bursts, 1):
    print("    burst %d: %d frames / %.0fs long, at +%.0fs" % (i, len(b), b[-1] - b[0], b[0] - ts[0]))
if len(bursts) > 1:
    iv = [bursts[i][0] - bursts[i - 1][0] for i in range(1, len(bursts))]
    print("  inter-burst gaps (s): %s  (~one boot cycle each)" % ", ".join("%.0f" % x for x in iv))
ok = len(bursts) >= minb
print("VERDICT: %s -- %d burst(s); need >=%d evenly-spaced for a self-healing loop."
      % ("PASS" if ok else "FAIL", len(bursts), minb))
print("  1 burst then silence = STUCK (pre-fix behavior, or not on PD power).")
print("  Many evenly-spaced bursts = netboot->eMMC->reboot->netboot self-heals.")
sys.exit(0 if ok else 3)
PY
}

plug_cmd() {  # $1 = "Power On" | "Power Off" | "Power" ; echoes the JSON reply
  curl -s -m 8 "http://$PLUG/cm?cmnd=$(printf '%s' "$1" | sed 's/ /%20/g')"
}

echo "== reboot-retry loop validation =="
echo "  iface=$IFACE  window=${DUR}s  puck-mac~=${MAC}*  carrier=$(cat /sys/class/net/$IFACE/carrier 2>&1)"
if pgrep -x dnsmasq >/dev/null || ip -4 addr show "$IFACE" 2>&1 | grep -qa 'inet '; then
  echo "  WARNING: a DHCP server / IP looks present on $IFACE -- the gale would"
  echo "           SUCCEED netbooting and never loop. Stop any netboot server first."
fi

if [ -n "$PLUG" ]; then
  echo "== power-cycling the gale via Tasmota plug $PLUG for a clean fresh boot =="
  echo "  off: $(plug_cmd 'Power Off')"
  sleep 5
  echo "  on:  $(plug_cmd 'Power On')"
  echo "  (gale booting; first DHCP expected ~10-20s after power-on)"
else
  echo "  (passive mode: no plug control; gale must already be powered on PD)"
  echo "  Reminder: gale on NORMAL USB-C PD power (NOT SuzyQ), eMMC blank, NO netboot server."
fi

echo "== sniffing $IFACE for ${DUR}s; live status every ${PROGRESS_INTERVAL}s =="
# shellcheck disable=SC2024  # $CAP is under $HOME (user-writable); redirect-as-user is correct
sudo timeout "$DUR" tcpdump -i "$IFACE" -n -e -tt -l 'udp port 67 or udp port 68' > "$CAP" 2>&1 &
TCPD=$!

start=$SECONDS
while kill -0 "$TCPD" 2>/dev/null; do
  sleep "$PROGRESS_INTERVAL"
  kill -0 "$TCPD" 2>/dev/null || break
  el=$((SECONDS - start))
  echo "  [+${el}s/${DUR}s] $(run_analysis progress)"
done
wait "$TCPD" 2>/dev/null

echo "== analysis =="
run_analysis final
rc=$?
rm -f "$CAP"
echo "REBOOT_LOOP_VALIDATE_DONE (rc=$rc)"
exit $rc
