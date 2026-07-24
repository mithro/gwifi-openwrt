#!/bin/sh
# 99-tenwrt-bootstrap must issue exactly the golden uci write sequence
# (simple-profile parity — no mesh/batman/backhaul ops).
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
mkdir -p "$ROOT/tmp"
SB=$(mktemp -d "$ROOT/tmp/tenwrt-ops.XXXXXX") || exit 1
trap 'rm -rf "$SB"' EXIT INT TERM
mkdir -p "$SB/bin"
cp "$HERE/uci-stub" "$SB/bin/uci"; chmod 0755 "$SB/bin/uci"
sed "s|^\. /lib/gwifi/bootstrap.sh|. $ROOT/fleet-image/files/lib/gwifi/bootstrap.sh|" \
	"$ROOT/tenwrt-image/files/etc/uci-defaults/99-tenwrt-bootstrap" > "$SB/boot.sh"
: > "$SB/state"; : > "$SB/ops.log"
env PATH="$SB/bin:$PATH" UCI_STATE="$SB/state" UCI_LOG="$SB/ops.log" \
	sh "$SB/boot.sh" > "$SB/stdout" || { echo "FAIL: bootstrap rc!=0"; exit 1; }
grep -q '^TENVM-BOOTSTRAP-COMPLETE uplink=eth0$' "$SB/stdout" || {
	echo "FAIL: completion marker missing"; exit 1; }
if diff -u "$HERE/tenwrt-bootstrap.oplog" "$SB/ops.log"; then
	echo "ALL PASS"; exit 0
else echo "FAIL: op sequence != golden"; exit 1; fi
