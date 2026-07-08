#!/bin/bash
# Netboot OpenWrt, capture the normal-boot console, and wait properly for
# dropbear so we can SSH in (a live shell = strongest boot proof).
set -u
ND=/home/tim/gale-netboot
DM=$ND/dnsmasq.log; TD=$ND/tcpdump.log; AP=$ND/apboot.log
: > "$DM"; : > "$TD"; : > "$AP"; rm -f "$ND/leases"

echo "=== [1] eth-gwan 192.168.50.1/24 ==="
sudo ip addr del 192.168.50.1/24 dev eth-gwan 2>&1 | head -1
sudo ip link set eth-gwan up
sudo ip addr add 192.168.50.1/24 dev eth-gwan
sleep 2; ip -4 addr show eth-gwan | grep -a inet

echo "=== [2] dnsmasq + tcpdump ==="
sudo timeout 300 tcpdump -i eth-gwan -n -e -l -s0 > "$TD" 2>&1 &
sudo /usr/sbin/dnsmasq -d -C "$ND/dnsmasq-gale.conf" > "$DM" 2>&1 &
sleep 3; grep -aiE "IP range|no address" "$DM" | head -1

echo "=== [3] boot AP via verify-boot (captures normal-boot console) ==="
cd /home/tim/local/gwifi/gwifi-openwrt/tools
/usr/bin/python3 flash_puck_usb.py verify-boot --boot-log "$AP" > "$ND/vb.log" 2>&1 &
VB=$!

echo "=== [4] watch for TFTP of the FIT (up to 150s) ==="
for i in $(seq 1 30); do sleep 5; grep -aqiE "sent .*netboot.itb" "$DM" && { echo "  TFTP SEEN ~$((i*5))s"; break; }; done
grep -aiE "DHCPACK|sent .*netboot.itb|tftp" "$DM" | tail -6

echo "=== [5] normal-boot console captured? (apboot.log) ==="
echo "  console bytes: $(wc -c < "$AP")"
grep -aiE "coreboot|depthcharge|dhcp|bootfile|tftp|starting|fit|kernel|no kernel|recovery" "$AP" 2>&1 | tr -d "\000" | head -8

echo "=== [6] find the OpenWrt DHCP lease + wait for dropbear (SSH), up to 150s ==="
owip=""
for i in $(seq 1 30); do
  sleep 5
  owip=$(grep -a "OpenWrt" "$ND/leases" 2>&1 | awk "{print \$3}" | head -1)
  [ -n "$owip" ] && { echo "  OpenWrt lease: $owip (at ~$((i*5))s)"; break; }
done
if [ -z "$owip" ]; then owip=$(grep -aE "192.168.50" "$ND/leases" | awk "{print \$3}" | tail -1); echo "  no OpenWrt-hostname lease; trying last lease $owip"; fi

ssh_ok=0
if [ -n "$owip" ]; then
  for i in $(seq 1 24); do
    ping -c1 -W1 -n "$owip" >/dev/null 2>&1
    if timeout 6 ssh -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new -o BatchMode=yes "root@$owip" "echo SSH_OK" 2>&1 | grep -qa SSH_OK; then ssh_ok=1; echo "  dropbear SSH up at ~$((i*5))s ($owip)"; break; fi
    sleep 5
  done
fi

echo "=== [7] live shell on the netbooted OpenWrt ==="
if [ "$ssh_ok" = 1 ]; then
  timeout 15 ssh -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new -o BatchMode=yes "root@$owip" \
    "cat /etc/openwrt_release | grep -iE DISTRIB_DESCRIPTION; uname -srmo; cat /proc/device-tree/model; echo; echo -n uptime:; cut -d. -f1 /proc/uptime; echo -n dropbear:; pgrep -c dropbear; echo -n rootfs:; df -h / | tail -1" 2>&1 | grep -aviE "clipboard"
else
  echo "  SSH did not come up on $owip; ping check:"; ping -c2 -W2 -n "$owip" 2>&1 | grep -aE "bytes from|loss"
fi
echo "owip=$owip ssh_ok=$ssh_ok console_bytes=$(wc -c < "$AP")"

echo "=== [8] cleanup ==="
kill "$VB" 2>&1 | head -1
sudo pkill -f "dnsmasq-gale.conf"
sudo ip addr del 192.168.50.1/24 dev eth-gwan 2>&1 | head -1
echo NETBOOT_TEST3_DONE
