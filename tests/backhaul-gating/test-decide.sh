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

[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
