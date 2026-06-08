# Backhaul-gated SSID advertisement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow @superpowers:test-driven-development for every task that has tests.

**Goal:** Make every gale/OM2P node advertise its client SSIDs only while it has a working path to ten64, using batman-adv's gateway mechanism as a distributed signal — implemented as one shared POSIX-sh control script plus cron/hotplug wiring, with no new daemon.

**Architecture:** Per spec `docs/backhaul-gated-ssids-design.md` ("Approach D"). Each node: if its **own wired uplink reaches ten64** → `batctl gw server`; else → `batctl gw client`. Client SSIDs are enabled iff *(own wired reaches ten64)* **OR** *(`batctl gwl` lists ≥1 gateway reachable over the existing wireless `bat0` mesh)*; otherwise disabled via `hostapd` ubus. A pure `decide()` function holds the state machine (unit-tested); shell probes/actuators wrap existing tools; cron (1-min) + `/etc/hotplug.d/net` drive it. The client data path, bridges, BLA, and ten64 are untouched.

**Tech Stack:** POSIX `sh` (busybox ash on-device), `batctl`, `hostapd` ubus, `cron`/`hotplug.d`, OpenWrt 25.12.4 image overlays; Python 3 (`uv`) for the verifiers; `ip netns` + mainline `batman-adv` for the integration harness. Tests: dependency-free `sh` assert harness + a sudo netns harness.

---

## File Structure (decomposition — locked here)

**New — shared overlay (canonical source, merged into both images at build time):**
- `fleet-files/usr/sbin/gwifi-backhaul-gate` — the control script (board-agnostic; all logic). One responsibility: decide + actuate backhaul gating.
- `fleet-files/etc/hotplug.d/net/30-gwifi-backhaul` — carrier-event trigger → runs the script `--once`.

**New — tests (repo root `tests/backhaul-gating/`):**
- `tests/backhaul-gating/test-decide.sh` — dependency-free unit tests for the pure functions (`decide`, parsers).
- `tests/backhaul-gating/netns-harness.sh` — `ip netns`+batman integration harness (3-node line), runs the real script with a stubbed `ubus`.
- `tests/backhaul-gating/fake-ubus` — recording stub used by the harness (and unit tests) in place of on-device `ubus`.

**Modified:**
- `gale-image/files/etc/uci-defaults/99-gale-bootstrap` — append idempotent cron-install + enable crond.
- `om2p-image/files/etc/uci-defaults/99-om2p-bootstrap` — same append.
- `gale-image/build-gale-image.sh` / `om2p-image/build-om2p-image.sh` — merge `fleet-files/` into the rendered overlay; chmod the two new files.
- `gale-image/verify-gale-image.py` / `om2p-image/verify-om2p-image.py` — assert the two files are present+executable and the bootstrap carries the cron-install snippet.
- `docs/backhaul-gated-ssids-design.md` — append "Spike findings & locked decisions" (Task 0); flip Status at the end.

**Why this shape:** the script is the only non-trivial unit, so it is one file with a clean internal split (pure decision/parsers vs. system probes/actuators) — the pure half is unit-tested, the system half is netns-tested. The shared files live in `fleet-files/` so there is exactly one copy (DRY), mirroring `fleet-secrets.conf`. Cron/fail-closed wiring is per-image (the bootstraps already differ), but is a one-line-ish idempotent append.

---

## Task 0: Spike — close design questions Q1–Q7

**Goal:** Lock the system-dependent details before writing the script, so later tasks have no open unknowns. Investigation only; no production code.

**Files:**
- Create (throwaway): `tmp/spike-batman-netns.sh`
- Modify: `docs/backhaul-gated-ssids-design.md` (append findings)

- [ ] **Step 0: Prerequisite — install batman tooling on the dev box.** The spike (below) and the Task 7 harness both need `batctl`, which is not installed: `sudo apt install batctl` (Debian trixie main). The `batman-adv` kernel module is already available (`modprobe batman-adv`).
- [ ] **Step 1: Batman signal spike (Q2, Q7) in network namespaces.** Write `tmp/spike-batman-netns.sh` that (as root) creates 3 netns `n1 n2 n3` joined in a **line** by veth pairs (n1—n2 and n2—n3), loads `batman-adv`, adds each node's veth(s) to `bat0`, sets `n1` `batctl gw server 100mbit/100mbit` and `n2`,`n3` `batctl gw client`, then prints `batctl -m bat0 gwl` on n2 and n3. Run it: `sudo sh tmp/spike-batman-netns.sh`.
  - Expected/confirm: **Q2** — `gwl` on a client lists n1 while the server runs, and becomes **empty** within a few seconds after `n1` does `batctl gw off`. **Q7** — n3 (2 hops from n1) also lists the gateway, confirming multi-hop propagation over a relayed batman path.
- [ ] **Step 2: Record device-only decisions (Q1, Q3, Q4).** These need real OpenWrt/wifi (deferred to bench) but get a safe **default that does not depend on them**:
  - **Q1 wired-isolation:** baseline = carrier check + **FDB-port confirmation** after a priming ping (no extra package); `arping -I <uplink>.5` is the preferred upgrade *if* the bench confirms it egresses a bridge-enslaved sub-iface. The script isolates this in one function `wired_reaches_gw()` so the bench can swap the method without touching logic.
  - **Q3/Q4 hostapd:** AP BSSes register `hostapd.<ifname>` ubus objects; the 802.11s mesh is wpa_supplicant-managed (no `hostapd.*` object). `ubus call hostapd.<bss> disable`/`enable` brings the BSS down/up without a radio reload. Keep the explicit mesh-mode guard regardless. Confirm on bench.
- [ ] **Step 3: Append findings.** Add a "## Spike findings & locked decisions (Task 0)" section to `docs/backhaul-gated-ssids-design.md` summarizing the netns results (paste the `gwl` outputs) and the locked Q1/Q3/Q4 defaults.
- [ ] **Step 4: Remove the throwaway spike script** (per the project's tmp-cleanup rule) once findings are recorded.
- [ ] **Step 5: Commit.**
```bash
git add docs/backhaul-gated-ssids-design.md
git commit -m "docs(backhaul): spike findings — batman gwl propagation + locked Q1/Q3/Q4 defaults

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 1: Pure `decide()` state machine (TDD)

**Goal:** The fail-safe, hysteretic decision logic as a pure, sourceable function with exhaustive unit tests.

**Files:**
- Create: `fleet-files/usr/sbin/gwifi-backhaul-gate`
- Create: `tests/backhaul-gating/test-decide.sh`

- [ ] **Step 1: Write the failing test.** Create `tests/backhaul-gating/test-decide.sh`:
```sh
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
```

- [ ] **Step 2: Run it; verify it fails.**
Run: `sh tests/backhaul-gating/test-decide.sh`
Expected: FAIL (file `fleet-files/usr/sbin/gwifi-backhaul-gate` does not exist yet → source error).

- [ ] **Step 3: Create the script skeleton with `decide()`.** Create `fleet-files/usr/sbin/gwifi-backhaul-gate`:
```sh
#!/bin/sh
# gwifi-backhaul-gate — gate client SSIDs on backhaul reachability to ten64,
# using batman-adv gateway mode as a distributed signal. Board-agnostic.
# Invoked by cron (--once) and /etc/hotplug.d/net. See
# docs/backhaul-gated-ssids-design.md. Sourceable for tests via GWIFI_GATE_SOURCED=1.
set -u

K=${GWIFI_GATE_K:-3}                 # consecutive no-backhaul cycles before gating off
GW_BW=${GWIFI_GATE_BW:-100mbit/100mbit}
STATE=${GWIFI_GATE_STATE:-/tmp/gwifi-backhaul.state}   # "CUR_SERVE FAIL_COUNT"
MGMT_BR=${GWIFI_GATE_MGMT_BR:-br-mgmt}
MGMT_VID=${GWIFI_GATE_MGMT_VID:-5}
LOG_TAG=gwifi-backhaul

# ---- pure decision logic (unit-tested) ------------------------------------
# decide WIRED_OK GW_PRESENT FAIL_COUNT K CUR_SERVE -> "ROLE SERVE NEW_FAIL"
decide() {
	_wired=$1; _gw=$2; _fail=$3; _k=$4; _cur=$5
	if [ "$_wired" = 1 ]; then echo "server on 0"; return; fi
	if [ "$_gw" = 1 ]; then echo "client on 0"; return; fi
	_fail=$((_fail + 1))
	if [ "$_cur" = on ] && [ "$_fail" -lt "$_k" ]; then
		echo "client on $_fail"        # debounce: was serving, still in grace
	else
		echo "client off $_fail"       # cold start, or grace exhausted -> fail-closed
	fi
}

main() { :; }   # filled in Task 3

case "${GWIFI_GATE_SOURCED:-}" in
	1) : ;;            # sourced (tests) — do not run
	*) main "$@" ;;
esac
```

- [ ] **Step 4: Run the test; verify it passes.**
Run: `sh tests/backhaul-gating/test-decide.sh`
Expected: `ALL PASS`.

- [ ] **Step 5: Commit.**
```bash
git add fleet-files/usr/sbin/gwifi-backhaul-gate tests/backhaul-gating/test-decide.sh
git commit -m "feat(backhaul): pure decide() state machine + unit tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Pure parsers — uplink, gateway, gwl, hostapd list (TDD)

**Goal:** Factor every "parse text → value" step out of the system calls so it is unit-testable with fixtures.

**Files:**
- Modify: `fleet-files/usr/sbin/gwifi-backhaul-gate`
- Modify: `tests/backhaul-gating/test-decide.sh` (add cases)

- [ ] **Step 1: Add failing tests** to `test-decide.sh` (before the summary line):
```sh
# parse_uplink_member: from `ls br-mgmt/brif`, the non-bat0 member on the mgmt VID
eq "uplink member (gale)"  "wan.5"  "$(printf 'bat0.5\nwan.5\n' | parse_uplink_member 5)"
eq "uplink member (om2p)"  "eth1.5" "$(printf 'eth1.5\nbat0.5\n' | parse_uplink_member 5)"
eq "uplink member none"    ""       "$(printf 'bat0.5\n'        | parse_uplink_member 5)"
# parse_gateway: nexthop from `ip route show default dev br-mgmt`
eq "gateway parse" "10.1.5.1" "$(echo 'default via 10.1.5.1 proto dhcp src 10.1.5.7' | parse_gateway)"
# parse_gwl_count: number of gateways in `batctl gwl` output (header lines ignored)
eq "gwl two"  "2" "$(printf 'B.A.T.M.A.N. ... Gateway ...\n  aa:bb:cc:dd:ee:01 ( 80) ...\n* aa:bb:cc:dd:ee:02 (120) ...\n' | parse_gwl_count)"
eq "gwl none" "0" "$(printf 'No gateways in range ...\n' | parse_gwl_count)"
# parse_hostapd_objs: hostapd.<iface> objects from `ubus list`
eq "hostapd objs" "hostapd.ap-roam hostapd.ap-iot" \
   "$(printf 'hostapd\nhostapd.ap-roam\nhostapd.ap-iot\nnetwork\n' | parse_hostapd_objs | tr '\n' ' ' | sed 's/ $//')"
```

- [ ] **Step 2: Run; verify new cases fail.**
Run: `sh tests/backhaul-gating/test-decide.sh`
Expected: FAIL on the new lines (functions not defined).

- [ ] **Step 3: Implement the parsers** in `gwifi-backhaul-gate` (above `main`):
```sh
# parse_uplink_member MGMT_VID  (stdin = brif names)  -> the *.VID member not on bat0
parse_uplink_member() {
	awk -v vid=".$1\$" '$0 !~ /^bat0\./ && $0 ~ vid {print; exit}'
}
# parse_gateway  (stdin = `ip route show default ...`) -> nexthop IP
parse_gateway() { awk '/via/ {for(i=1;i<NF;i++) if($i=="via"){print $(i+1); exit}}'; }
# parse_gwl_count (stdin = `batctl gwl`) -> count of gateway rows (MAC-bearing lines)
parse_gwl_count() { grep -c -E '([0-9a-f]{2}:){5}[0-9a-f]{2}' || true; }
# parse_hostapd_objs (stdin = `ubus list`) -> hostapd.<iface> object names
parse_hostapd_objs() { grep -E '^hostapd\.' || true; }
```

- [ ] **Step 4: Run; verify all pass.**
Run: `sh tests/backhaul-gating/test-decide.sh`
Expected: `ALL PASS`.

- [ ] **Step 5: Commit.**
```bash
git add fleet-files/usr/sbin/gwifi-backhaul-gate tests/backhaul-gating/test-decide.sh
git commit -m "feat(backhaul): pure parsers (uplink/gateway/gwl/hostapd) + tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: System probes, actuators, and `main()`

**Goal:** Wire the parsers to real tools and implement the run-once `main()`. (Validated in the netns harness, Task 7; pure parts already covered.)

**Files:**
- Modify: `fleet-files/usr/sbin/gwifi-backhaul-gate`

- [ ] **Step 1: Implement probes + actuators + main** (replace the stub `main`):
```sh
# ---- system probes --------------------------------------------------------
discover_uplink_member() {
	ls "/sys/class/net/$MGMT_BR/brif" 2>/dev/null | parse_uplink_member "$MGMT_VID"
}
discover_gateway() { ip -4 route show default dev "$MGMT_BR" 2>/dev/null | parse_gateway; }

# wired_reaches_gw  -> 0 (true) if ten64 is reachable specifically via the wired uplink.
# Q1: baseline = carrier + FDB-port confirmation after a priming ping; arping upgrade per spike.
wired_reaches_gw() {
	_member=$(discover_uplink_member); [ -n "$_member" ] || return 1
	_uplink=${_member%.*}
	[ "$(cat "/sys/class/net/$_uplink/carrier" 2>/dev/null || echo 0)" = 1 ] || return 1
	_gw=$(discover_gateway); [ -n "$_gw" ] || return 1
	ping -c1 -w2 -I "$MGMT_BR" "$_gw" >/dev/null 2>&1 || return 1   # prime neigh; any path
	_mac=$(ip neigh show "$_gw" dev "$MGMT_BR" | awk '/lladdr/{print $5; exit}')
	[ -n "$_mac" ] || return 1
	bridge fdb show br "$MGMT_BR" | grep -iq "$_mac dev $_member"   # learned on the wired port?
}
gw_present() { [ "$(batctl gwl 2>/dev/null | parse_gwl_count)" -gt 0 ]; }

# ---- actuators (idempotent) ----------------------------------------------
apply_role() {  # $1 = server|client
	_want=$1; _cur=$(batctl gw 2>/dev/null | awk '{print $1}')
	case "$_cur" in "$_want"*) return 0;; esac
	if [ "$_want" = server ]; then batctl gw server "$GW_BW"; else batctl gw client; fi
	logger -t "$LOG_TAG" "gw_mode -> $_want"
}
apply_serve() {  # $1 = on|off  (acts on AP BSSes only; mesh is supplicant-managed)
	_want=$1; _act=disable; [ "$_want" = on ] && _act=enable
	for obj in $(ubus list 2>/dev/null | parse_hostapd_objs); do
		_mode=$(ubus call "$obj" get_status 2>/dev/null | grep -o '"mode":"[a-z]*"' | cut -d'"' -f4)
		[ "$_mode" = mesh ] && continue          # belt-and-suspenders guard
		ubus call "$obj" "$_act" >/dev/null 2>&1
	done
	logger -t "$LOG_TAG" "serve -> $_want"
}

# ---- main -----------------------------------------------------------------
main() {
	cur=off; fail=0
	[ -r "$STATE" ] && read -r cur fail < "$STATE" 2>/dev/null || true
	case "$cur" in on|off) : ;; *) cur=off ;; esac
	case "$fail" in ''|*[!0-9]*) fail=0 ;; esac

	wired=0; gw=0
	wired_reaches_gw && wired=1
	[ "$wired" = 1 ] || { gw_present && gw=1; }

	set -- $(decide "$wired" "$gw" "$fail" "$K" "$cur")
	role=$1; serve=$2; newfail=$3

	apply_role "$role"
	apply_serve "$serve"
	printf '%s %s\n' "$serve" "$newfail" > "$STATE"
}
```

- [ ] **Step 2: Lint with shellcheck (advisory).**
Run: `shellcheck -s sh fleet-files/usr/sbin/gwifi-backhaul-gate || true`
Expected: no errors that change behavior (POSIX-sh warnings acceptable; fix real bugs).

- [ ] **Step 3: Re-run unit tests** (ensure refactor didn't break pure functions).
Run: `sh tests/backhaul-gating/test-decide.sh`
Expected: `ALL PASS`.

- [ ] **Step 4: Commit.**
```bash
git add fleet-files/usr/sbin/gwifi-backhaul-gate
git commit -m "feat(backhaul): system probes, idempotent actuators, run-once main

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Hotplug trigger + cron/crond wiring (both bootstraps)

**Goal:** Run the gate at boot + on carrier change (hotplug) and every minute (cron), idempotently, with fail-closed default.

**Files:**
- Create: `fleet-files/etc/hotplug.d/net/30-gwifi-backhaul`
- Modify: `gale-image/files/etc/uci-defaults/99-gale-bootstrap`
- Modify: `om2p-image/files/etc/uci-defaults/99-om2p-bootstrap`

- [ ] **Step 1: Create the hotplug hook** `fleet-files/etc/hotplug.d/net/30-gwifi-backhaul`:
```sh
# Re-evaluate backhaul gating when an interface comes up or changes carrier.
# Fires at boot (ifaces appear) and on uplink carrier transitions.
[ "$ACTION" = add ] || [ "$ACTION" = ifup ] || [ "$ACTION" = ifupdate ] || exit 0
[ -x /usr/sbin/gwifi-backhaul-gate ] && /usr/sbin/gwifi-backhaul-gate --once
```

- [ ] **Step 2: Insert the idempotent cron+crond block into BOTH bootstraps** — same snippet, but **mind placement** (the two bootstraps differ): in `99-gale-bootstrap` put it just before the final `exit 0`; in `99-om2p-bootstrap` put it **immediately after `uci commit network` (line ~69), before the wireless section** — that bootstrap has an earlier `exit 1` (the "radio0 not present yet; deferring to next boot" path, line ~78), so a block before the final `exit 0` would be skipped on any boot where radio0 isn't ready, and the periodic re-assert (the self-heal / re-gate-after-OpenWISP-reload mechanism) might never install. Snippet:
```sh
# --- backhaul-gating: 1-min cron re-assert + ensure crond runs (idempotent) ---
CRON=/etc/crontabs/root
LINE='* * * * * /usr/sbin/gwifi-backhaul-gate --once'
mkdir -p /etc/crontabs
grep -qF "$LINE" "$CRON" 2>/dev/null || echo "$LINE" >> "$CRON"
/etc/init.d/cron enable 2>/dev/null || true
/etc/init.d/cron restart 2>/dev/null || true
# Fail-closed boot: the gate defaults serve=OFF until it confirms backhaul; the
# hotplug hook fires as interfaces come up, so the first evaluation runs at boot.
```

- [ ] **Step 3: Manual sanity (dev box) — the gate accepts `--once` and is a no-op off-device.** The script's `--once` is consumed by `main "$@"` (args ignored beyond presence); confirm sourcing still parses:
Run: `sh -n fleet-files/usr/sbin/gwifi-backhaul-gate && sh -n fleet-files/etc/hotplug.d/net/30-gwifi-backhaul`
Expected: no syntax errors (exit 0).

- [ ] **Step 4: Re-run unit tests** (bootstraps/hook don't affect them, but confirm green).
Run: `sh tests/backhaul-gating/test-decide.sh`
Expected: `ALL PASS`.

- [ ] **Step 5: Commit.**
```bash
git add fleet-files/etc/hotplug.d/net/30-gwifi-backhaul \
        gale-image/files/etc/uci-defaults/99-gale-bootstrap \
        om2p-image/files/etc/uci-defaults/99-om2p-bootstrap
git commit -m "feat(backhaul): hotplug carrier trigger + idempotent cron wiring in both bootstraps

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: DRY shared-overlay merge in both build scripts

**Goal:** Both images pick up `fleet-files/` at build time (single source of truth), with the two new files executable, and no placeholders left behind.

**Files:**
- Modify: `gale-image/build-gale-image.sh`
- Modify: `om2p-image/build-om2p-image.sh`

- [ ] **Step 1: In `build-gale-image.sh`, after the `cp -a "$HERE/files" "$OWRT/files"` line, insert the shared-overlay merge:**
```sh
# merge the shared fleet overlay (canonical source for cross-image files)
cp -a "$HERE/../fleet-files/." "$OWRT/files/"
```
And after the existing `chmod 0755 .../99-gale-bootstrap` line, add:
```sh
chmod 0755 "$OWRT/files/usr/sbin/gwifi-backhaul-gate" \
           "$OWRT/files/etc/hotplug.d/net/30-gwifi-backhaul"
```

- [ ] **Step 2: Apply the identical two edits to `build-om2p-image.sh`** (same insert after its `cp -a "$HERE/files" "$OWRT/files"`, same `chmod` after its `chmod 0755 .../99-om2p-bootstrap`).

- [ ] **Step 3: Test the render seam (no full build needed).** Run each build script in render-only mode and assert the shared files land, are executable, and carry no placeholders:
```bash
RENDER_ONLY=1 FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf OWRT=$(mktemp -d) \
  sh gale-image/build-gale-image.sh && echo "gale render OK"
```
Run the same with `om2p-image/build-om2p-image.sh`. Then for each rendered `$OWRT/files`:
```bash
test -x "$OWRT/files/usr/sbin/gwifi-backhaul-gate" && \
test -x "$OWRT/files/etc/hotplug.d/net/30-gwifi-backhaul" && \
! grep -rl '__[A-Z_]*__' "$OWRT/files/usr/sbin/gwifi-backhaul-gate" && echo "shared overlay OK"
```
Expected: both `render OK` and `shared overlay OK`. (The mktemp `$OWRT` makes this safe and build-free; remove the temp dirs after.)

- [ ] **Step 4: Commit.**
```bash
git add gale-image/build-gale-image.sh om2p-image/build-om2p-image.sh
git commit -m "build(backhaul): merge shared fleet-files/ overlay into both images

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Extend the image verifiers

**Goal:** Both verifiers assert the gate script + hotplug hook are present and executable and that the bootstrap carries the cron-install snippet. (cron itself is busybox `crond` — not a manifest package, so not added to `REQUIRED_PACKAGES`.)

**Files:**
- Modify: `gale-image/verify-gale-image.py`
- Modify: `om2p-image/verify-om2p-image.py`

- [ ] **Step 1: gale verifier — extract the extra paths and assert.** In `unsquash()`, also extract `/usr/sbin/gwifi-backhaul-gate` and `/etc/hotplug.d` by adding them to the `unsquashfs` arg list (change the extract set from `"/etc"` to `"/etc" "/usr/sbin/gwifi-backhaul-gate"`). In `run_assertions()`, after the bootstrap check, add:
```python
    # 5) backhaul-gate script + hotplug hook present & executable; cron wired in bootstrap.
    gate = os.path.join(rootfs_dir, "usr", "sbin", "gwifi-backhaul-gate")
    hook = os.path.join(rootfs_dir, "etc", "hotplug.d", "net", "30-gwifi-backhaul")
    for path, label in ((gate, "backhaul-gate"), (hook, "backhaul-hotplug")):
        if not os.path.isfile(path):
            failures.append("FAIL %s: %s missing" % (label, path))
        elif os.stat(path).st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS %s: present and executable" % label)
        else:
            failures.append("FAIL %s: present but not executable" % label)
    if os.path.isfile(bootstrap) and "gwifi-backhaul-gate --once" in open(bootstrap).read():
        print("  PASS bootstrap: cron line installed")
    else:
        failures.append("FAIL bootstrap: cron-install snippet missing")
```

- [ ] **Step 2: om2p verifier — add the files to the extracted set and assert.** Extend `want` in `read_etc_files()` to include `"usr/sbin/gwifi-backhaul-gate"` and `"etc/hotplug.d/net/30-gwifi-backhaul"` (the function already returns `modes`, so executability is available). After the bootstrap block in `main()`, add:
```python
    for rel, label in (("usr/sbin/gwifi-backhaul-gate", "backhaul-gate"),
                       ("etc/hotplug.d/net/30-gwifi-backhaul", "backhaul-hotplug")):
        if rel not in files:
            failures.append("FAIL %s: %s missing from rootfs" % (label, rel))
        elif modes.get(rel, 0) & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS %s: present and executable" % label)
        else:
            failures.append("FAIL %s: present but not executable" % label)
    if bs and "gwifi-backhaul-gate --once" in bs:
        print("  PASS bootstrap: cron line installed")
    else:
        failures.append("FAIL bootstrap: cron-install snippet missing")
```

- [ ] **Step 3: Syntax-check both verifiers.**
Run: `uv run python -c "import ast,sys; [ast.parse(open(p).read()) for p in ('gale-image/verify-gale-image.py','om2p-image/verify-om2p-image.py')]; print('OK')"`
Expected: `OK`. (Full verifier runs require built images — deferred to the build step; these assertions are exercised end-to-end then.)

- [ ] **Step 4: Commit.**
```bash
git add gale-image/verify-gale-image.py om2p-image/verify-om2p-image.py
git commit -m "test(backhaul): verifiers assert gate script + hotplug + cron wiring

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Netns + batman integration harness

**Goal:** Exercise the real script's batman half (probes/actuators) against live `batctl` in namespaces, with a recording `ubus` stub for the hostapd half. Validates Approach D end-to-end without gale/OM2P hardware, including multi-hop `gwl` (3-node line).

**Files:**
- Create: `tests/backhaul-gating/fake-ubus`
- Create: `tests/backhaul-gating/netns-harness.sh`

- [ ] **Step 1: Create the recording `ubus` stub** `tests/backhaul-gating/fake-ubus`:
```sh
#!/bin/sh
# Minimal ubus stand-in for the harness. `list` prints configured hostapd objects
# (FAKE_HOSTAPD_OBJS, newline-sep); `call <obj> get_status` returns AP mode;
# `call <obj> enable|disable` records to FAKE_UBUS_LOG.
case "$1" in
  list) printf '%s\n' ${FAKE_HOSTAPD_OBJS:-} ;;
  call)
    case "$3" in
      get_status) echo '{"mode":"ap"}' ;;
      enable|disable) echo "$2 $3" >> "${FAKE_UBUS_LOG:-/dev/null}" ;;
    esac ;;
esac
exit 0
```

- [ ] **Step 2: Create the harness** `tests/backhaul-gating/netns-harness.sh` (root required). It builds a 3-node line over veth, loads batman, and drives the script per node with `PATH` shimmed to the fake `ubus`, asserting role/serve transitions:
```sh
#!/bin/sh
# Integration harness for gwifi-backhaul-gate. Run: sudo sh netns-harness.sh
# Topology (line):  ten64ns --(wired)-- n1 --(mesh)-- n2 --(mesh)-- n3
# n1 has wired+mesh; n2,n3 mesh-only (n3 is 2 hops). Real batman; ubus stubbed.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
GATE="$HERE/../../fleet-files/usr/sbin/gwifi-backhaul-gate"
modprobe batman-adv
# ... create netns ten64ns,n1,n2,n3; veth pairs; bridges to emulate br-mgmt on n1;
#     add mesh veths to bat0 in n1/n2/n3; n1 batctl gw server; n2/n3 client ...
# Assertions (sketch — fill concrete commands):
#  A) n1: wired_reaches_gw true  -> decide => server/on
#  B) n2: gw_present true (sees n1) -> client/on ; fake-ubus log shows 'enable'
#  C) n3: gw_present true at 2 hops -> client/on   (multi-hop, Q7)
#  D) n1 batctl gw off + sever n1 wired -> n2,n3 gw_present false -> serve off
#     after K cycles ; fake-ubus log shows 'disable'
# Teardown: delete all netns; rmmod batman-adv (best-effort).
echo "harness: see inline assertions; exits non-zero on first failure"
```
Implement the elided sections concretely (one `ip netns exec` per probe; invoke the gate with `GWIFI_GATE_STATE=$tmp GWIFI_GATE_K=2 PATH=$HERE:$PATH ip netns exec nX sh "$GATE" --once`; assert against `FAKE_UBUS_LOG` and `batctl -m bat0 gwl`). Use a short `K` and a poll-with-timeout loop for `gwl` convergence. **Multi-hop caveat (Q7):** a flat single-segment veth mesh can populate `gwl` at every node regardless of hop count (spec §11.2), so assertion C must poll until n3 (2 hops) sees the gateway *after convergence*, and the topology must be a genuine line (wire n1—n2 and n2—n3 as separate veth pairs with n2 relaying), not a shared segment — otherwise the multi-hop check passes trivially.

- [ ] **Step 3: Run the harness.**
Run: `sudo sh tests/backhaul-gating/netns-harness.sh`
Expected: prints PASS for A–D and exits 0. (If batman multi-hop `gwl` needs a few seconds, the poll loop handles it.)

- [ ] **Step 4: Commit.**
```bash
git add tests/backhaul-gating/fake-ubus tests/backhaul-gating/netns-harness.sh
git commit -m "test(backhaul): netns+batman integration harness (3-node line, stubbed ubus)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Wire-up validation build + docs/status

**Goal:** Prove the feature lands in real images and close out the spec.

**Files:**
- Modify: `docs/backhaul-gated-ssids-design.md` (Status)
- (build artifacts — not committed)

- [ ] **Step 1: Build and verify end-to-end** (proves overlay merge + verifier assertions on a real rootfs). Build the **full OM2P multi-profile (all four)** — the verifier's fit gate checks every profile in `PROFILES`, so a single-profile build would make it report missing-image FAILs; do **not** restrict `DEVICES`:
```bash
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  sh om2p-image/build-om2p-image.sh
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  uv run python om2p-image/verify-om2p-image.py
```
Expected: build completes; verifier prints the new `PASS backhaul-gate / backhaul-hotplug / bootstrap: cron line installed` lines, all four `PASS fit:` lines, and `RESULT: PASS`. (Optional: also `sh gale-image/build-gale-image.sh` + `uv run python gale-image/verify-gale-image.py` to exercise the gale verifier's new assertions on a squashfs `.bin`.)

- [ ] **Step 2: Flip the spec Status** in `docs/backhaul-gated-ssids-design.md` from "Draft — pending …" to "Implemented (branch `openwisp-controller`); bench items: spike Q1/Q3/Q4 device-confirm + real-hardware §11.4."

- [ ] **Step 3: Commit.**
```bash
git add docs/backhaul-gated-ssids-design.md
git commit -m "docs(backhaul): mark design implemented; note remaining bench items

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Update project memory.** Add a `gwifi-backhaul-gating` memory (status, files, the Approach-D one-liner, remaining bench items) and a line in `MEMORY.md`. (Not a git action — the auto-memory store.)

---

## Done-when
- `sh tests/backhaul-gating/test-decide.sh` → ALL PASS (pure logic).
- `sudo sh tests/backhaul-gating/netns-harness.sh` → PASS A–D (batman half, incl. multi-hop).
- A real build + `verify-*.py` → PASS including the new backhaul assertions.
- ten64, the client data path, the bridges/BLA, and the OpenWISP templates are unchanged (diff review).
- Remaining (bench, hardware): spike Q1/Q3/Q4 device-confirm (`arping -I` egress, `hostapd` ubus disable/enable actually stops beacons), and the §11.4 real-fleet checks.
