#!/bin/bash
# Passively validate the netboot reboot-retry SELF-HEALING loop.
#
# The gale MUST be on NORMAL USB-C PD power (its stock adapter), NOT the USB-A
# SuzyQ rig -- only then does cold_reboot() reboot the AP autonomously (the
# SuzyQ rig gates AP power via the EC, so a SoC self-reset wedges instead). This
# script does NOT touch the EC/power at all: it only sniffs the WAN and counts
# DHCP-discover BURSTS. Each boot cycle with no netboot server emits one burst;
# a working reboot-retry loop emits MANY evenly-spaced bursts. See
# ../../docs/reboot-retry-validation.md.
#
# Preconditions (else there is no loop to observe):
#   * reboot-retry firmware flashed (patches/vboot_reference-netboot-reboot-retry)
#   * NO netboot/DHCP server on this WAN segment (netboot must FAIL each cycle)
#   * eMMC blank / no bootable OS (the eMMC fallback must FAIL too)
#
# Usage: sudo ./reboot_loop_validate.sh [IFACE] [DURATION_S] [MAC_PREFIX]
#   IFACE       WAN iface cabled to the gale WAN port  (default eth-gwan)
#   DURATION_S  sniff window in seconds                (default 300)
#   MAC_PREFIX  puck MAC filter                        (default 44:07:0b, gale OUI)
set -u
IFACE="${1:-eth-gwan}"
DUR="${2:-300}"
MAC="${3:-44:07:0b}"
GAP=15            # a WAN-silent gap > GAP s delimits boot cycles
MINBURSTS=3       # >= this many evenly-spaced bursts => self-healing loop
CAP="$HOME/reboot-loop-cap.$$.txt"

command -v tcpdump >/dev/null || { echo "FATAL: tcpdump not found"; exit 1; }
[ -e "/sys/class/net/$IFACE" ] || { echo "FATAL: no interface $IFACE"; exit 1; }

echo "== reboot-retry loop validation =="
echo "  iface=$IFACE  window=${DUR}s  puck-mac~=${MAC}*  carrier=$(cat /sys/class/net/$IFACE/carrier 2>&1)"
if pgrep -x dnsmasq >/dev/null || ip -4 addr show "$IFACE" 2>&1 | grep -qa 'inet '; then
  echo "  WARNING: a DHCP server / IP looks present on $IFACE -- the gale would"
  echo "           SUCCEED netbooting and never loop. Stop any netboot server first."
fi
echo "  Reminder: gale on NORMAL USB-C PD power (NOT SuzyQ), eMMC blank, NO netboot server."
echo "  Sniffing ${DUR}s for the puck's DHCP-discover bursts (Ctrl-C to stop early)..."

# shellcheck disable=SC2024  # $CAP is under $HOME (user-writable); redirect-as-user is correct
sudo timeout "$DUR" tcpdump -i "$IFACE" -n -e -tt -l 'udp port 67 or udp port 68' > "$CAP" 2>&1 || true

echo "== analysis =="
grep -aiE "$MAC.*BOOTP/DHCP.*Request from" "$CAP" | awk '{print $1}' | python3 - "$GAP" "$MINBURSTS" <<'PY'
import sys
gap = float(sys.argv[1]); minb = int(sys.argv[2])
ts = sorted(float(x) for x in sys.stdin if x.strip())
if not ts:
    print("  DHCP frames from the puck: 0")
    print("VERDICT: FAIL -- the puck emitted NO DHCP. It did not boot, the WAN is not")
    print("         cabled/carrier-down, or it is not PD-powered. (If a netboot server")
    print("         WAS present it may simply have netbooted successfully -- remove it.)")
    sys.exit(2)
bursts = [[ts[0]]]
for t in ts[1:]:
    (bursts.append([t]) if t - bursts[-1][-1] > gap else bursts[-1].append(t))
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
rc=$?
rm -f "$CAP"
echo "REBOOT_LOOP_VALIDATE_DONE (rc=$rc)"
exit $rc
