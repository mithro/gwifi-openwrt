#!/bin/sh
# netns + batman-adv integration harness for gwifi-backhaul-gate.
#
# Runs the REAL control script (fleet-files/usr/sbin/gwifi-backhaul-gate) inside
# `ip netns` namespaces against a REAL batman-adv mesh built over veth, with only
# `ubus` stubbed (tests/backhaul-gating/fake-ubus). The gate's decision is thus
# driven by genuine `batctl gwl` / `batctl gw` state, not mocks.
#
# Topology — a real 3-node LINE (two separate veth pairs, n2 relays):
#     n1 --(veth a12/a21)-- n2 --(veth b23/b32)-- n3
# n3 is 2 hops from n1, reachable only via n2; this is NOT a shared segment, so
# the multi-hop assertion (B) cannot pass trivially.
#
# Assertions exercised LIVE here:
#   A. Gateway visible (1 hop)  -> gate sets `batctl gw client` + enables SSIDs.
#   B. Multi-hop / Q7 (2 hops)  -> after real convergence, same on n3.
#   C. Islanded (fail-closed)   -> no gateway; after grace exhausted the gate
#                                   disables SSIDs and stays `client`.
#   D. Wired-server / Q1 / FDB  -> a separate node with a real br-mgmt (VLAN-5
#                                   sub-iface to a `ten64` netns that answers
#                                   ping/ARP, so the bridge FDB learns ten64's
#                                   MAC on the wired port, plus a default route)
#                                   -> gate sets `batctl gw server` + enables.
#                                   This is the Q1 path the design marks
#                                   bench-to-confirm; it is exercised LIVE here.
#
# Nodes n1/n2/n3 carry an EMPTY br-mgmt (no VLAN-5 wired member), so
# `discover_uplink_member` is empty and `wired_reaches_gw` is false -> the role
# is decided purely by the real mesh gateway list. (An empty bridge, rather than
# no bridge at all, matches a real node where br-mgmt always exists and keeps the
# gate's `ls .../brif` probe from erroring.) Node D builds a POPULATED br-mgmt to
# drive the wired path.
#
# Requires root (netns + modprobe batman-adv) and batctl/bridge. POSIX sh.
# Idempotent: an EXIT trap deletes every netns we created and best-effort
# `rmmod batman-adv`, and cleans the project-local ./tmp/ scratch.

set -u

# ---- locations ------------------------------------------------------------
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
GATE="$ROOT/fleet-files/usr/sbin/gwifi-backhaul-gate"
TMP="$ROOT/tmp"

[ -x "$GATE" ] || { echo "FATAL: gate not executable at $GATE"; exit 2; }
[ -f "$HERE/fake-ubus" ] || { echo "FATAL: fake-ubus missing at $HERE/fake-ubus"; exit 2; }

if [ "$(id -u)" != 0 ]; then
	echo "FATAL: must run as root (netns + modprobe). Try: sudo sh $0"
	exit 2
fi

# Namespaces this harness owns (teardown deletes exactly these).
NS_LIST="gw_n1 gw_n2 gw_n3 gw_wnode gw_ten64"

# A PATH where `ubus` is our fake and batctl/bridge/ip are the real tools.
# (sudo's secure_path drops /sbin from the caller's env, so name them.)
mkdir -p "$TMP/bin"
ln -sf "$HERE/fake-ubus" "$TMP/bin/ubus"
chmod +x "$HERE/fake-ubus"
RUNPATH="$TMP/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# ---- teardown -------------------------------------------------------------
# Idempotent and quiet by CONSTRUCTION (existence-guarded), not by hiding stderr:
# every action is gated on the thing actually being present, so a clean teardown
# emits nothing and surfaces genuine errors instead of swallowing them.
teardown() {
	for ns in $NS_LIST; do
		# `ip netns list` may print "name (id: N)"; match the first field only.
		ip netns list | awk '{print $1}' | grep -qxF "$ns" && ip netns del "$ns"
	done
	# veth ends live inside the netns and die with them; clean any stragglers
	# that ended up back in the root ns (e.g. on a mid-setup abort).
	for v in a12 a21 b23 b32 wup t64; do
		[ -e "/sys/class/net/$v" ] && ip link del "$v"
	done
	[ -e "$TMP/bin/ubus" ] && rm -f "$TMP/bin/ubus"
	[ -d "$TMP/bin" ] && rmdir "$TMP/bin"
	for f in "$TMP"/ubuslog.* "$TMP"/state.*; do [ -e "$f" ] && rm -f "$f"; done
	[ -d "$TMP" ] && rmdir "$TMP"
	lsmod | grep -q '^batman_adv ' && rmmod batman_adv
	return 0
}
trap teardown EXIT INT TERM

# Start from a clean slate (in case a previous run aborted before its trap).
teardown
mkdir -p "$TMP/bin"
ln -sf "$HERE/fake-ubus" "$TMP/bin/ubus"

# ---- result tracking ------------------------------------------------------
FAILED=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILED=1; }
note() { printf '      %s\n' "$1"; }
# check "label" expected actual
check() {
	if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (want [$2] got [$3])"; fi
}
die_if_failed() {
	[ "$FAILED" = 0 ] || { echo; echo "STOPPING on first failure."; exit 1; }
}

# ---- batman helpers -------------------------------------------------------
modprobe batman-adv || { echo "FATAL: cannot load batman-adv"; exit 2; }

# bat0_up NS IF1 [IF2 ...] — attach mesh hardifs and bring bat0 up.
bat0_up() {
	_ns=$1; shift
	for _if in "$@"; do
		ip netns exec "$_ns" batctl meshif bat0 interface add "$_if"
		ip netns exec "$_ns" ip link set "$_if" up
	done
	ip netns exec "$_ns" ip link set bat0 up
}

# gwl_count NS -> number of gateways NS currently sees (banner-stripped).
gwl_count() {
	ip netns exec "$1" batctl gwl \
		| grep -vE '^\[' | grep -cE '([0-9a-f]{2}:){5}[0-9a-f]{2}' || true
}

# wait_gwl NS WANT TIMEOUT_DECISEC — poll until gwl_count >= WANT or timeout.
# Returns 0 on convergence. batman multi-hop needs a few seconds; we poll.
wait_gwl() {
	_ns=$1; _want=$2; _max=$3; _i=0
	while [ "$_i" -lt "$_max" ]; do
		_c=$(gwl_count "$_ns")
		[ "$_c" -ge "$_want" ] && { note "$_ns saw $_c gateway(s) after $((_i*5))ds"; return 0; }
		_i=$((_i + 1))
		sleep 0.5
	done
	note "$_ns gwl did not reach $_want within $((_max*5))ds (last=$(gwl_count "$_ns"))"
	return 1
}

# gw_mode NS -> first token of `batctl gw` (server|client|off).
gw_mode() { ip netns exec "$1" batctl gw | awk '{print $1}'; }

# run_gate NS STATEFILE LOGFILE [K] — run the real gate once in NS with the
# fake ubus on PATH and NO br-mgmt (so wired_reaches_gw is false).
run_gate() {
	_ns=$1; _state=$2; _log=$3; _k=${4:-3}
	env FAKE_HOSTAPD_OBJS='hostapd.ap-roam hostapd.ap-iot' \
		FAKE_UBUS_LOG="$_log" \
		GWIFI_GATE_STATE="$_state" \
		GWIFI_GATE_K="$_k" \
		PATH="$RUNPATH" \
		ip netns exec "$_ns" sh "$GATE" --once
}

# ============================================================================
# Build the 3-node LINE: n1 -- n2 -- n3 (two distinct veth pairs).
# ============================================================================
echo "== building 3-node batman line (n1 -- n2 -- n3) =="
for ns in gw_n1 gw_n2 gw_n3; do ip netns add "$ns"; done

# pair a: n1 <-> n2
ip link add a12 type veth peer name a21
ip link set a12 netns gw_n1
ip link set a21 netns gw_n2
# pair b: n2 <-> n3
ip link add b23 type veth peer name b32
ip link set b23 netns gw_n2
ip link set b32 netns gw_n3

bat0_up gw_n1 a12
bat0_up gw_n2 a21 b23     # n2 is the relay: both veths in its mesh
bat0_up gw_n3 b32

# Give each an EMPTY br-mgmt (exists, but no VLAN-5 wired member) so the gate's
# wired probe runs cleanly and resolves to "no wired uplink" -> mesh-only path.
for ns in gw_n1 gw_n2 gw_n3; do
	ip netns exec "$ns" ip link add name br-mgmt type bridge
	ip netns exec "$ns" ip link set br-mgmt up
done

# ============================================================================
# A. Gateway visible (1 hop): n1 is a gw server, n2 should go client + enable.
# ============================================================================
echo
echo "== A. gateway visible -> client + SSIDs enabled (n2, 1 hop) =="
ip netns exec gw_n1 batctl gw server 100mbit/100mbit
note "n1 set to gw server"

if wait_gwl gw_n2 1 60; then
	A_log=$(mktemp -p "$TMP" ubuslog.XXXXXX)
	A_state=$(mktemp -p "$TMP" state.XXXXXX)
	run_gate gw_n2 "$A_state" "$A_log"
	check "A: n2 batctl gw == client" "client" "$(gw_mode gw_n2)"
	# fake-ubus log: one 'enable' line per configured BSS, mode order-independent.
	A_en=$(grep -c 'enable$' "$A_log" || true)
	A_dis=$(grep -c 'disable$' "$A_log" || true)
	check "A: ubus enabled both BSSes" "2" "$A_en"
	check "A: ubus disabled none" "0" "$A_dis"
	check "A: persisted serve state == on" "on 0" "$(cat "$A_state")"
	rm -f "$A_log" "$A_state"
else
	fail "A: n2 never saw n1's gateway (convergence)"
fi
die_if_failed

# ============================================================================
# B. Multi-hop (Q7): n3 is 2 hops from n1 via n2 -> client + enable.
# ============================================================================
echo
echo "== B. multi-hop (2 hops via n2 relay) -> client + SSIDs enabled (n3) =="
# n3 has no direct veth to n1 (separate pairs), so any gateway it sees is reached
# through n2 — verified below by the relayed gwl row (Router != Next Hop).
if wait_gwl gw_n3 1 60; then
	B_log=$(mktemp -p "$TMP" ubuslog.XXXXXX)
	B_state=$(mktemp -p "$TMP" state.XXXXXX)
	run_gate gw_n3 "$B_state" "$B_log"
	check "B: n3 batctl gw == client" "client" "$(gw_mode gw_n3)"
	B_en=$(grep -c 'enable$' "$B_log" || true)
	check "B: ubus enabled both BSSes (2 hops)" "2" "$B_en"
	check "B: persisted serve state == on" "on 0" "$(cat "$B_state")"
	# Prove it really is multi-hop, not a shared segment: in a gwl row
	#   "<Router> ( TQ) <NextHop> [outIf]: bw"  ($1=Router originator MAC,
	# $4=Next Hop MAC), a DIRECT gateway has Router==NextHop, whereas a 2-hop
	# gateway via the n2 relay has Router (n1) != NextHop (n2). (Confirmed: n2's
	# own 1-hop row shows $1==$4; n3's 2-hop row shows $1!=$4.)
	B_gwl=$(ip netns exec gw_n3 batctl gwl | grep -vE '^\[' | grep -E '([0-9a-f]{2}:){5}')
	note "n3 gwl row: $B_gwl"
	B_router=$(printf '%s\n' "$B_gwl" | awk '{print $1}')
	B_nexthop=$(printf '%s\n' "$B_gwl" | awk '{print $4}')
	if [ -n "$B_router" ] && [ "$B_router" != "$B_nexthop" ]; then
		pass "B: gateway relayed (Router $B_router != NextHop $B_nexthop) -> genuinely 2 hops"
	else
		fail "B: gateway not relayed (Router=$B_router NextHop=$B_nexthop); shared segment?"
	fi
	rm -f "$B_log" "$B_state"
else
	fail "B: n3 never saw the gateway across 2 hops (convergence)"
fi
die_if_failed

# ============================================================================
# C. Islanded -> fail-closed: remove the only gateway, exhaust grace, expect
#    SSIDs disabled and role stays client.
# ============================================================================
echo
echo "== C. islanded -> SSIDs disabled after grace (fail-closed) =="
ip netns exec gw_n1 batctl gw off
note "n1 gateway turned off (mesh now has no gateway)"

# Wait for n2 to lose the gateway from its gwl (announcements time out).
C_gone=0; C_i=0
while [ "$C_i" -lt 120 ]; do
	[ "$(gwl_count gw_n2)" -eq 0 ] && { C_gone=1; note "n2 gwl empty after $((C_i*5))ds"; break; }
	C_i=$((C_i + 1)); sleep 0.5
done
[ "$C_gone" = 1 ] || note "WARNING: n2 still lists a gateway; proceeding (decision will see it)."

# Seed state as 'on' (n2 was serving in A) so we exercise the grace path, then
# run the gate repeatedly with K=2 until grace is exhausted -> disable.
C_log=$(mktemp -p "$TMP" ubuslog.XXXXXX)
C_state=$(mktemp -p "$TMP" state.XXXXXX)
printf 'on 0\n' > "$C_state"
C_K=2
C_runs=0; C_disabled=0
while [ "$C_runs" -lt 6 ]; do
	: > "$C_log"                      # only inspect the latest cycle's actions
	run_gate gw_n2 "$C_state" "$C_log" "$C_K"
	C_runs=$((C_runs + 1))
	note "C cycle $C_runs: state=[$(cat "$C_state")] ubus=[$(tr '\n' ';' < "$C_log")]"
	if grep -q 'disable$' "$C_log"; then C_disabled=1; break; fi
done
check "C: ubus disabled both BSSes once grace exhausted" "1" "$C_disabled"
C_dis=$(grep -c 'disable$' "$C_log" || true)
check "C: latest cycle disabled both BSSes" "2" "$C_dis"
check "C: n2 batctl gw == client (mesh client, SSIDs off)" "client" "$(gw_mode gw_n2)"
check "C: persisted serve state == off" "off 2" "$(cat "$C_state")"
rm -f "$C_log" "$C_state"
die_if_failed

# ============================================================================
# D. Wired-server (Q1 / FDB): a node whose wired uplink reaches ten64.
#    Built as a SEPARATE pair: gw_wnode (with br-mgmt) <-> gw_ten64.
#    This is the path the design marks bench-to-confirm; exercised LIVE here.
# ============================================================================
echo
echo "== D. wired uplink reaches ten64 -> server + SSIDs enabled (Q1/FDB, LIVE) =="
ip netns add gw_wnode
ip netns add gw_ten64

# Wired uplink veth: wnode <-> ten64.
ip link add wup type veth peer name t64
ip link set wup netns gw_wnode
ip link set t64 netns gw_ten64

# ten64: VLAN-5 sub-iface with the gateway IP; answers ping/ARP.
ip netns exec gw_ten64 ip link set t64 up
ip netns exec gw_ten64 ip link add link t64 name t64.5 type vlan id 5
ip netns exec gw_ten64 ip link set t64.5 up
ip netns exec gw_ten64 ip addr add 10.1.5.1/24 dev t64.5

# wnode: real br-mgmt containing the VLAN-5 wired member (wup.5), an address,
# and a default route via ten64 — exactly what wired_reaches_gw probes.
ip netns exec gw_wnode ip link set wup up
ip netns exec gw_wnode ip link add link wup name wup.5 type vlan id 5
ip netns exec gw_wnode ip link set wup.5 up
ip netns exec gw_wnode ip link add name br-mgmt type bridge
ip netns exec gw_wnode ip link set wup.5 master br-mgmt
ip netns exec gw_wnode ip link set br-mgmt up
ip netns exec gw_wnode ip addr add 10.1.5.7/24 dev br-mgmt
ip netns exec gw_wnode ip route add default via 10.1.5.1 dev br-mgmt

# wnode also needs a bat0 for apply_role's `batctl gw`; a lone dummy hardif is
# enough (no mesh peer required for the wired-server assertion). Start as client
# to prove the gate flips it to server.
ip netns exec gw_wnode ip link add bmesh type dummy
bat0_up gw_wnode bmesh
ip netns exec gw_wnode batctl gw client
note "wnode br-mgmt built; uplink member wup.5, default via 10.1.5.1; bat0=client"

# Run the gate with GWIFI_GATE_MGMT_BR=br-mgmt so it probes the wired path.
D_log=$(mktemp -p "$TMP" ubuslog.XXXXXX)
D_state=$(mktemp -p "$TMP" state.XXXXXX)
env FAKE_HOSTAPD_OBJS='hostapd.ap-roam hostapd.ap-iot' \
	FAKE_UBUS_LOG="$D_log" \
	GWIFI_GATE_STATE="$D_state" \
	GWIFI_GATE_K=2 \
	GWIFI_GATE_MGMT_BR=br-mgmt \
	PATH="$RUNPATH" \
	ip netns exec gw_wnode sh "$GATE" --once

# Show the FDB evidence the gate relied on (ten64 MAC learned on the wired port).
D_mac=$(ip netns exec gw_wnode ip neigh show 10.1.5.1 dev br-mgmt \
	| awk '{for(i=1;i<NF;i++) if($i=="lladdr"){print $(i+1); exit}}')
note "ten64 MAC=$D_mac; FDB entry:"
note "  $(ip netns exec gw_wnode bridge fdb show br br-mgmt | grep -iF "$D_mac" | grep -F 'wup.5' | grep -vF permanent | head -1)"

check "D: wnode batctl gw == server (wired reaches ten64)" "server" "$(gw_mode gw_wnode)"
D_en=$(grep -c 'enable$' "$D_log" || true)
check "D: ubus enabled both BSSes (wired server)" "2" "$D_en"
check "D: persisted serve state == on" "on 0" "$(cat "$D_state")"
rm -f "$D_log" "$D_state"
die_if_failed

# ---- summary --------------------------------------------------------------
echo
echo "== coverage summary =="
echo "  LIVE (real batman over veth, real batctl, stubbed ubus only):"
echo "    A  gateway-visible 1-hop -> client + enable"
echo "    B  multi-hop 2-hop (Q7)  -> client + enable (relayed, real line)"
echo "    C  islanded fail-closed  -> disable + stays client (grace exhausted)"
echo "    D  wired-server Q1/FDB    -> server + enable (real br-mgmt+VLAN+FDB+route)"
echo "  BENCH-DEFERRED: none of A-D deferred. The wired path (D) is exercised LIVE"
echo "    via a netns br-mgmt whose FDB learns ten64's MAC on the VLAN wired port;"
echo "    on real hardware the same path additionally depends on physical carrier"
echo "    and switch VLAN config, which only the bench can fully confirm."
echo
if [ "$FAILED" = 0 ]; then
	echo "ALL PASS"
	exit 0
else
	echo "SOME FAILED"
	exit 1
fi
