#!/bin/bash
# Verify the reboot-retry fix: boot 2831 with NO netboot server + blank eMMC.
# OLD firmware -> one DHCP burst then stuck in "waiting for manual recovery".
# NEW firmware -> netboot fail -> reboot -> retry, so the WAN sees PERIODIC
# DHCP bursts (one per boot cycle) and the console shows "rebooting to retry
# netboot" and NEVER "waiting for manual recovery".
set -u
ND=/home/tim/gale-netboot
WAN=$ND/rr_wan.txt; AP=$ND/rr_ap.log
: > "$WAN"; : > "$AP"

echo "=== [1] ensure no netboot server is running (this is the failure case):"
sudo pkill -f "dnsmasq-gale.conf" 2>&1 | head -1
sudo ip addr del 192.168.50.1/24 dev eth-gwan 2>&1 | head -1
echo "  (eth-gwan has no server; netboot must fail every cycle)"

echo "=== [2] sniff WAN for DHCP bursts (280s):"
sudo timeout 280 tcpdump -i eth-gwan -n -e -l -tt > "$WAN" 2>&1 &

echo "=== [3] boot the AP via verify-boot (un-parks EC + powers AP + captures console):"
cd /home/tim/local/gwifi/gwifi-openwrt/tools
/usr/bin/python3 flash_puck_usb.py verify-boot --boot-log "$AP" > "$ND/rr_vb.log" 2>&1 &

echo "=== [4] let it run ~250s to watch several reboot cycles:"
sleep 250

echo "=== [5] WAN DHCP-discover bursts from the puck (44:07:0b), with timestamps:"
grep -aE "44:07:0b.*BOOTP/DHCP" "$WAN" | awk '{print $1}' > "$ND/rr_ts.txt"
python3 - "$ND/rr_ts.txt" <<'PY'
import sys
ts=[float(x) for x in open(sys.argv[1]) if x.strip()]
if not ts:
    print("  NO puck DHCP frames at all (AP never netbooted?)"); sys.exit()
bursts=1; last=ts[0]
for t in ts[1:]:
    if t-last>15: bursts+=1
    last=t
print("  total DHCP frames: %d" % len(ts))
print("  distinct bursts (gap>15s): %d  <-- one per boot cycle" % bursts)
print("  span: %.0fs  (first->last)" % (ts[-1]-ts[0]))
PY

echo "=== [6] console evidence:"
echo -n "  'rebooting to retry netboot' count: "; grep -ac "rebooting to retry netboot" "$AP"
echo -n "  'waiting for manual recovery' count (want 0): "; grep -ac "waiting for manual recovery" "$AP"
echo -n "  'bootblock start' count (reboot cycles seen on console): "; grep -ac "bootblock start" "$AP"
echo "  --- console tail:"; tail -8 "$AP" | tr -d "\000" | grep -avE "^[[:space:]]*$"

echo "=== [7] cleanup:"; sudo pkill -f "tcpdump -i eth-gwan" 2>&1 | head -1
echo REBOOT_RETRY_TEST_DONE
