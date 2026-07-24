#!/bin/sh
# The refactored 99-gale-bootstrap (thin driver + lib/gwifi/bootstrap.sh) must
# issue the SAME uci write sequence as the pre-refactor monolith (pinned at the
# merge commit), modulo the ALLOWED new ops (the mac_interface move — design
# spec §4.2). Before the refactor lands this compares the file to itself and
# passes trivially; after, it is the semantic half of the §4.8.1 gate.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
OLD_COMMIT=${OLD_COMMIT:-71acaac}
mkdir -p "$ROOT/tmp"
SB=$(mktemp -d "$ROOT/tmp/bootstrap-eq.XXXXXX") || exit 1
trap 'rm -rf "$SB"' EXIT INT TERM
mkdir -p "$SB/bin"
cp "$HERE/uci-stub" "$SB/bin/uci"; chmod 0755 "$SB/bin/uci"

git -C "$ROOT" show "$OLD_COMMIT:gale-image/files/etc/uci-defaults/99-gale-bootstrap" \
	> "$SB/old.sh" || { echo "FAIL: cannot extract old bootstrap"; exit 1; }
# The new driver sources /lib/gwifi/bootstrap.sh (device-absolute); rebind it
# to the worktree copy. A pre-refactor monolith has no such line -> no-op sed.
sed "s|^\. /lib/gwifi/bootstrap.sh|. $ROOT/fleet-image/files/lib/gwifi/bootstrap.sh|" \
	"$ROOT/gale-image/files/etc/uci-defaults/99-gale-bootstrap" > "$SB/new.sh"

run_one() {  # $1=script $2=oplog
	cat > "$SB/state" <<-'EOF'
	network.@device[0].name=br-lan
	network.@device[1].name=eth-blue
	network.@device[1].macaddr=00:11:22:33:44:55
	EOF
	: > "$2"
	env PATH="$SB/bin:$PATH" UCI_STATE="$SB/state" UCI_LOG="$2" sh "$1"
}
run_one "$SB/old.sh" "$SB/old.log" || { echo "FAIL: old bootstrap rc!=0"; exit 1; }
run_one "$SB/new.sh" "$SB/new.log" || { echo "FAIL: new bootstrap rc!=0"; exit 1; }
grep -v -e '^set openwisp\.http\.mac_interface=' -e '^commit openwisp' \
	"$SB/new.log" > "$SB/new.filtered"
diff -u "$SB/old.log" "$SB/new.filtered" || { echo "FAIL: uci op sequences diverge"; exit 1; }

# Retry-path: the NEW bootstrap must exit nonzero when br-lan is absent
# (uci-defaults keeps the script and retries next boot).
printf 'network.@device[0].name=something-else\n' > "$SB/state"
: > "$SB/retry.log"
if env PATH="$SB/bin:$PATH" UCI_STATE="$SB/state" UCI_LOG="$SB/retry.log" \
	sh "$SB/new.sh" 2> "$SB/retry.stderr"; then
	echo "FAIL: new bootstrap must exit nonzero without br-lan"; exit 1
fi
echo "ALL PASS"
