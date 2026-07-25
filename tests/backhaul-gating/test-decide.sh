#!/bin/sh
# Unit tests for gwifi-backhaul-gate pure functions. No deps; run: sh test-decide.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
GWIFI_GATE_SOURCED=1 . "$HERE/../../fleet-files/usr/sbin/gwifi-backhaul-gate"

fails=0
ok()  { printf '  PASS %s\n' "$1"; }
no()  { printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }
eq()  { # eq "label" expected actual
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (want [$2] got [$3])"; fi; }

K=3
# decide WIRED_OK GW_PRESENT FAIL_COUNT K CUR_SERVE -> "ROLE SERVE NEW_FAIL"
eq "wired -> server/on/reset"        "server on 0" "$(decide 1 0 0 $K off)"
eq "wired beats grace counter"       "server on 0" "$(decide 1 1 2 $K on)"
eq "mesh-only -> client/on/reset"    "client on 0" "$(decide 0 1 0 $K on)"
eq "cold start, no backhaul -> off"  "client off 1" "$(decide 0 0 0 $K off)"
eq "lose backhaul, grace 1 -> on"    "client on 1" "$(decide 0 0 0 $K on)"
eq "lose backhaul, grace 2 -> on"    "client on 2" "$(decide 0 0 1 $K on)"
eq "grace exhausted (K) -> off"      "client off 3" "$(decide 0 0 2 $K on)"
eq "stay off while still no backhaul" "client off 4" "$(decide 0 0 3 $K off)"
eq "recovery resets counter"         "client on 0" "$(decide 0 1 3 $K off)"

# parse_uplink_member: from `ls br-mgmt/brif`, the non-bat0 member on the mgmt VID
eq "uplink member (gale)"  "wan.5"  "$(printf 'bat0.5\nwan.5\n' | parse_uplink_member 5)"
eq "uplink member (om2p)"  "eth1.5" "$(printf 'eth1.5\nbat0.5\n' | parse_uplink_member 5)"
eq "uplink member none"    ""       "$(printf 'bat0.5\n'        | parse_uplink_member 5)"
eq "uplink member ignores .15" "wan.5" "$(printf 'bat0.5\nwan.15\nwan.5\n' | parse_uplink_member 5)"
# parse_gateway: nexthop from `ip route show default dev br-mgmt`
eq "gateway parse" "10.1.5.1" "$(echo 'default via 10.1.5.1 proto dhcp src 10.1.5.7' | parse_gateway)"
# parse_gwl_count: count gateways, IGNORING the [B.A.T.M.A.N. adv ...] banner (it contains a MAC)
eq "gwl two"  "2" "$(printf '[B.A.T.M.A.N. adv 2024.2, MainIF/MAC: vA2/26:2a:01:4f:f6:9e (bat0 BATMAN_IV)]\n  Router ( TQ) Next Hop [outIf]\n  aa:bb:cc:dd:ee:01 ( 80) aa:bb:cc:dd:ee:01\n* aa:bb:cc:dd:ee:02 (120) aa:bb:cc:dd:ee:02\n' | parse_gwl_count)"
eq "gwl none (banner only)" "0" "$(printf '[B.A.T.M.A.N. adv 2024.2, MainIF/MAC: vA2/26:2a:01:4f:f6:9e (bat0 BATMAN_IV)]\nNo gateways in range ...\n' | parse_gwl_count)"
# parse_hostapd_objs: hostapd.<iface> objects from `ubus list`
eq "hostapd objs" "hostapd.ap-roam hostapd.ap-iot" \
   "$(printf 'hostapd\nhostapd.ap-roam\nhostapd.ap-iot\nnetwork\n' | parse_hostapd_objs | tr '\n' ' ' | sed 's/ $//')"

[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
