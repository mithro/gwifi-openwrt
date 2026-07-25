#!/bin/sh
# Integration test: gwifi_normalize_radios op sequence against the shared
# uci-stub (tests/fleet-image/uci-stub) — the rename triple must fire when
# radio0 comes up 5/6 GHz and radio1 is 2.4 GHz, and must NOT fire otherwise.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
mkdir -p "$ROOT/tmp"
SB=$(mktemp -d "$ROOT/tmp/radio-swap-ops.XXXXXX") || exit 1
trap 'rm -rf "$SB"' EXIT INT TERM
mkdir -p "$SB/bin"
cp "$ROOT/tests/fleet-image/uci-stub" "$SB/bin/uci"; chmod 0755 "$SB/bin/uci"

# Driver: source gwifi-radio-setup (GWIFI_RADIO_SOURCED=1 skips main) and run
# JUST the normalize function — no wifi config/enable involved.
cat > "$SB/driver.sh" <<DRV
GWIFI_RADIO_SOURCED=1 . "$ROOT/tenwrt-image/files/usr/sbin/gwifi-radio-setup"
gwifi_normalize_radios
DRV

fails=0
eq() { if [ "$2" = "$3" ]; then printf '  PASS %s\n' "$1";
       else printf '  FAIL %s (want [%s] got [%s])\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

# run_normalize BAND0 BAND1 -> op log contents (uci-stub: get reads
# $UCI_STATE, rename is log-only) after running gwifi_normalize_radios once.
run_normalize() {
	: > "$SB/state"; : > "$SB/ops.log"
	printf 'wireless.radio0.band=%s\nwireless.radio1.band=%s\n' "$1" "$2" > "$SB/state"
	env PATH="$SB/bin:$PATH" UCI_STATE="$SB/state" UCI_LOG="$SB/ops.log" sh "$SB/driver.sh"
	cat "$SB/ops.log"
}

got=$(run_normalize 5g 2g)
want='rename wireless.radio0=radiotmp
rename wireless.radio1=radio0
rename wireless.radiotmp=radio1'
eq "swap ops 5g/2g" "$want" "$got"

got=$(run_normalize 2g 5g)
eq "no swap ops 2g/5g" "" "$got"

[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
