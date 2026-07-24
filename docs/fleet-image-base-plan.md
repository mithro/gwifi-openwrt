# Fleet image base + tenwrt VM parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared `fleet-image/` base, respecialize gale/om2p onto it with
byte-diff no-regression gates, and rewrite `tenwrt-image/` to simple-profile parity
(mt7915 firmware fix, acpid + qemu-ga, minimal wisp bootstrap) plus the small
wisp-side template edits — per `docs/fleet-image-base-design.md`.

**Architecture:** `fleet-image/` holds a shared config fragment (`base.config`), a
shared overlay (`files/`: openwisp UCI + `lib/gwifi/bootstrap.sh` first-boot
functions), a sourceable build library (`build-lib.sh`) and shared verifier helpers
(`verify_lib.py`). Each image dir keeps a thin build wrapper + its own config
fragment + its own overlay. Bootstrap equivalence is enforced by a `uci`-stub
harness that diffs recorded op sequences; render/config regressions are enforced by
byte-diff gates against the pre-refactor tree.

**Tech Stack:** POSIX sh, OpenWrt v25.12.4 buildroot (two trees: existing
`/home/tim/local/gwifi/openwrt` stays untouched for pucks; new
`/home/tim/local/gwifi/openwrt-armsr` for this branch's builds), Python 3 via `uv`,
QEMU aarch64 for smoke boot.

**Ground rules (from user conventions + memory):**
- Work ONLY in `/home/tim/local/gwifi/gwifi-openwrt/.worktrees/tenwrt-vm-parity`
  (branch `tenwrt-vm-parity`). NEVER touch ten64. NEVER build in
  `/home/tim/local/gwifi/openwrt` (shared with live puck work).
- Any command that can exceed 60 s (feeds, `make`): run in background with output
  `tee`'d to a log file and report progress every ~60 s. Never suppress
  stdout/stderr (no `/dev/null`).
- Python always via `uv run`. Temp files under the repo-local `tmp/` (never `/tmp`).
- Commit after every task (small, discrete commits).
- Never redirect output to `/dev/null` — not in ad-hoc commands (a hook blocks
  it) and not in test files either: capture expected-failure stderr to a log
  file under the test scratch dir instead (suppressed output = lost evidence).

**Paths used throughout:**
- `ROOT` = `/home/tim/local/gwifi/gwifi-openwrt/.worktrees/tenwrt-vm-parity`
- `ARMSR` = `/home/tim/local/gwifi/openwrt-armsr` (created in Task 0)
- Pre-refactor pin: the merge commit `71acaac` (contains the untouched
  gale/om2p/tenwrt trees).

---

### Task 0: Dedicated armsr build tree (start first; runs in background)

**Files:** none in repo (creates `/home/tim/local/gwifi/openwrt-armsr`).

- [ ] **Step 0.1: Local clone + checkout the pinned commit**

```bash
cd /home/tim/local/gwifi
git clone --no-checkout /home/tim/local/gwifi/openwrt openwrt-armsr
cd openwrt-armsr
git checkout 2b1b3b2266
cp -al ../openwrt/dl dl   # hardlink copy: reuses 1.3G of tarballs, no interference
```

(No feeds.conf copy needed: the source tree has no untracked `feeds.conf` — the
pinned feed commits live in the tracked `feeds.conf.default`, which the clone
already carries.)

Expected: checkout at `2b1b3b2266` ("ipq40xx: fix qca8k…" — the ipq40xx patch is
irrelevant to armsr but keeps both trees at the identical commit).

- [ ] **Step 0.2: Feeds update + install (background, logged)**

```bash
cd /home/tim/local/gwifi/openwrt-armsr
(./scripts/feeds update -a && ./scripts/feeds install -a) 2>&1 | tee feeds-setup.log
```

Run in background; poll the log every ~60 s. Expected tail: `Installing all packages
from feed …` with no errors. Verify: `./scripts/feeds list -i | grep -c openwisp`
returns ≥ 2 (openwisp-config, openwisp-monitoring exist as installable packages).

Later tasks that need `make defconfig` (Tasks 4, 5, 7) and builds (Tasks 11, 12)
depend on this task; Tasks 1–3 do not — start Task 0, then continue with Task 1
while it runs.

---

### Task 1: Pre-refactor RENDER_ONLY seam + BEFORE captures

**Files:**
- Modify: `gale-image/build-gale-image.sh` (insert seam after the chmod block,
  BEFORE the image-id stamp — a timestamped id in the render would dirty every diff)
- Create (untracked, under `tmp/`): `tmp/gate/before-{gale,om2p}/` render trees

- [ ] **Step 1.1: Ensure `tmp/` is git-ignored**

```bash
cd $ROOT
git check-ignore -q tmp || { echo 'tmp/' >> .gitignore; git add .gitignore; }
```

- [ ] **Step 1.2: Add the RENDER_ONLY seam to the gale build script**

In `gale-image/build-gale-image.sh`, directly after the `chmod 0755 …` command and
BEFORE the `# 1b) stamp the image id` comment block, insert:

```sh
# RENDER_ONLY=1: stop after rendering the overlay (no image-id stamp, no build).
# Used by the refactor no-regression gate (docs/fleet-image-base-design.md §4.8.1).
[ "${RENDER_ONLY:-0}" = "1" ] && { echo "rendered overlay to $OWRT/files (RENDER_ONLY)"; exit 0; }
```

- [ ] **Step 1.3: Commit the seam (this is the "pre-refactor" reference point)**

```bash
git add gale-image/build-gale-image.sh
git commit -m "gale-image: add RENDER_ONLY seam (pre-refactor gate reference)"
```

- [ ] **Step 1.4: Capture BEFORE renders for gale and om2p**

The render step only writes `$OWRT/files`, so a scratch dir works as `OWRT` — no
build tree needed. Secrets: the pre-refactor gale script hardcodes
`$HERE/gale-secrets.conf`, and the FILLED file is untracked so it exists only in
the MAIN worktree — copy it into this worktree first (it is gitignored here;
never edit the pre-refactor script to work around a missing secrets file):

```bash
cp /home/tim/local/gwifi/gwifi-openwrt/.worktrees/wisp-netboot-install/gale-image/gale-secrets.conf \
   $ROOT/gale-image/
```

(The FILLED 5-var file — including TOPOLOGY_RECEIVE_URL — lives in the
wisp-netboot-install worktree, where production gale builds ran. The main
worktree's copy and /home/tim/local/gwifi/fleet-secrets.conf are stale 4-var
versions; Step 4.8 brings fleet-secrets.conf up to the 5-var set so BEFORE
(gale-secrets) and AFTER (fleet-secrets) renders compare equal values.)

```bash
cd $ROOT
mkdir -p tmp/gate/before-gale tmp/gate/before-om2p
OWRT=$ROOT/tmp/gate/before-gale RENDER_ONLY=1 sh gale-image/build-gale-image.sh
OWRT=$ROOT/tmp/gate/before-om2p RENDER_ONLY=1 \
  FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf sh om2p-image/build-om2p-image.sh
```

Expected: both print `rendered overlay to … (RENDER_ONLY)`; `tmp/gate/before-gale/files`
and `tmp/gate/before-om2p/files` are populated. These trees contain rendered secrets —
they stay in gitignored `tmp/` and are deleted in Task 15.

- [ ] **Step 1.5: Capture BEFORE `.config`s (after Task 0 finishes)**

Once `openwrt-armsr` feeds are installed, run each pre-refactor seeding through
`make defconfig` there and save the result:

```bash
cd $ROOT
# gale seed (mirror the script's seeding without building):
{ printf 'CONFIG_TARGET_ipq40xx=y\nCONFIG_TARGET_ipq40xx_chromium=y\nCONFIG_TARGET_ipq40xx_chromium_DEVICE_google_wifi=y\n'; \
  cat gale-image/gale.config; } > /home/tim/local/gwifi/openwrt-armsr/.config
( cd /home/tim/local/gwifi/openwrt-armsr && make defconfig )
cp /home/tim/local/gwifi/openwrt-armsr/.config tmp/gate/before-gale.config

DEVICES="openmesh_om2p-lc openmesh_om2p-v1 openmesh_om2p-v2 openmesh_om2p-v4"
{ printf 'CONFIG_TARGET_ath79=y\nCONFIG_TARGET_ath79_generic=y\nCONFIG_TARGET_MULTI_PROFILE=y\n'; \
  for d in $DEVICES; do printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_%s=y\n' "$d"; done; \
  cat om2p-image/om2p.config; } > /home/tim/local/gwifi/openwrt-armsr/.config
( cd /home/tim/local/gwifi/openwrt-armsr && make defconfig )
cp /home/tim/local/gwifi/openwrt-armsr/.config tmp/gate/before-om2p.config
```

Expected: two saved `.config` files. (This may interleave with Tasks 2–3 while
waiting for Task 0.)

---

### Task 2: uci-stub harness + gale bootstrap equivalence test

**Files:**
- Create: `tests/fleet-image/uci-stub`
- Create: `tests/fleet-image/test-gale-bootstrap-equivalence.sh`

- [ ] **Step 2.1: Write the uci stub**

`tests/fleet-image/uci-stub` (mode 0755):

```sh
#!/bin/sh
# uci-stub — stand-in `uci` for bootstrap tests: answers `get` from a flat
# state file ($UCI_STATE, key=value lines) and appends every MUTATING call to
# $UCI_LOG. Supports exactly the subset the bootstrap scripts use. Reads are
# not logged (read patterns may differ between implementations; only the
# write sequence must match).
set -u
[ "${1:-}" = "-q" ] && shift
cmd=${1:-}; [ $# -gt 0 ] && shift
log() { printf '%s\n' "$*" >> "$UCI_LOG"; }
state_get() {  # $1=key -> value on stdout, rc 1 if absent (awk: exact prefix)
	awk -v k="$1=" 'index($0, k) == 1 { print substr($0, length(k) + 1); f = 1; exit }
	                END { exit f ? 0 : 1 }' "$UCI_STATE"
}
state_del() { awk -v k="$1=" 'index($0, k) != 1' "$UCI_STATE" > "$UCI_STATE.new" && \
	mv "$UCI_STATE.new" "$UCI_STATE"; }
case "$cmd" in
get)      state_get "$1" ;;
set)      log "set $1"; k=${1%%=*}; state_del "$k"; printf '%s\n' "$1" >> "$UCI_STATE" ;;
add_list) log "add_list $1" ;;
del_list) log "del_list $1" ;;
delete)   log "delete $1"; state_del "$1" ;;
rename)   log "rename $1" ;;
commit)   log "commit ${1:-}" ;;
batch)    log "batch"; cat >> "$UCI_LOG" ;;   # keep the payload: it IS the op evidence
*)        echo "uci-stub: unsupported: $cmd $*" >&2; exit 2 ;;
esac
```

- [ ] **Step 2.2: Write the equivalence test**

`tests/fleet-image/test-gale-bootstrap-equivalence.sh` (mode 0755):

```sh
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
if diff -u "$SB/old.log" "$SB/new.filtered"; then echo "ALL PASS"; exit 0
else echo "FAIL: uci op sequences diverge"; exit 1; fi
```

- [ ] **Step 2.3: Also assert the retry-path (missing br-lan → nonzero exit)**

Append to the test, before the final PASS line — the NEW bootstrap must exit
nonzero when the board section is absent (uci-defaults keeps + retries; the old
monolith is frozen history and needs no assertion):

```sh
printf 'network.@device[0].name=something-else\n' > "$SB/state"
: > "$SB/retry.log"
if env PATH="$SB/bin:$PATH" UCI_STATE="$SB/state" UCI_LOG="$SB/retry.log" \
	sh "$SB/new.sh" 2> "$SB/retry.stderr"; then
	echo "FAIL: new bootstrap must exit nonzero without br-lan"; exit 1
fi
```

(Adjust placement so the retry check runs before `ALL PASS`.)

- [ ] **Step 2.4: Run it — must pass against the unrefactored tree**

Run: `sh tests/fleet-image/test-gale-bootstrap-equivalence.sh`
Expected: `ALL PASS` (old == current file, filter removes nothing).

- [ ] **Step 2.5: Commit**

```bash
git add tests/fleet-image/
git commit -m "tests(fleet-image): uci-stub harness + gale bootstrap equivalence gate"
```

---

### Task 3: fleet-image/build-lib.sh (TDD)

**Files:**
- Create: `fleet-image/build-lib.sh`
- Create: `tests/fleet-image/test-build-lib.sh`

- [ ] **Step 3.1: Write the failing test**

`tests/fleet-image/test-build-lib.sh` (mode 0755):

```sh
#!/bin/sh
# build-lib.sh: overlay merge order (image overrides base), placeholder
# substitution (incl. sed metachars in secrets), chmod list, required-var
# enforcement, RENDER_ONLY gate.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
mkdir -p "$ROOT/tmp"
SB=$(mktemp -d "$ROOT/tmp/buildlib.XXXXXX") || exit 1
trap 'rm -rf "$SB"' EXIT INT TERM
fails=0
eq() { if [ "$2" = "$3" ]; then printf '  PASS %s\n' "$1"; \
       else printf '  FAIL %s (want [%s] got [%s])\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

mkdir -p "$SB/base/etc" "$SB/img/etc" "$SB/owrt"
printf 'base __OPENWISP_URL__\n' > "$SB/base/etc/shared"     # image overrides this
printf 'img __OPENWISP_SHARED_SECRET__\n' > "$SB/img/etc/shared"
printf 'only __OPENWISP_URL__\n' > "$SB/base/etc/baseonly"
cat > "$SB/secrets.conf" <<'EOF'
OPENWISP_URL="https://wisp.example"
OPENWISP_SHARED_SECRET="p&ss|w\0rd"
EOF

run_render() { (
	set -e
	HERE="$SB/img"; OWRT="$SB/owrt"; FLEET_SECRETS="$SB/secrets.conf"
	OVERLAYS="$SB/base $SB/img"; SECRETS_VARS="OPENWISP_URL OPENWISP_SHARED_SECRET"
	CHMOD_FILES="etc/baseonly"
	. "$ROOT/fleet-image/build-lib.sh"
	fleet_require_secrets
	fleet_render
) }
run_render || { echo "FAIL: render rc!=0"; exit 1; }

eq "image overrides base"  'img p&ss|w\0rd' "$(cat "$SB/owrt/files/etc/shared")"
eq "base-only substituted" 'only https://wisp.example' "$(cat "$SB/owrt/files/etc/baseonly")"
perms=$(stat -c %a "$SB/owrt/files/etc/baseonly")
eq "chmod applied" "755" "$perms"

# missing required var -> hard fail
if ( HERE="$SB/img" OWRT="$SB/owrt" FLEET_SECRETS="$SB/secrets.conf" \
     OVERLAYS="$SB/base" SECRETS_VARS="OPENWISP_URL NOSUCH_VAR" CHMOD_FILES=""; \
     . "$ROOT/fleet-image/build-lib.sh"; fleet_require_secrets ) 2> "$SB/missing-var.stderr"; then
	echo "  FAIL missing-var not rejected"; fails=$((fails+1))
else printf '  PASS missing var rejected\n'; fi

[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
```

- [ ] **Step 3.2: Run it — must fail (no build-lib.sh yet)**

Run: `sh tests/fleet-image/test-build-lib.sh`
Expected: FAIL (`build-lib.sh: No such file`).

- [ ] **Step 3.3: Write `fleet-image/build-lib.sh`**

```sh
#!/bin/sh
# fleet-image/build-lib.sh — shared build steps for the fleet images
# (docs/fleet-image-base-design.md §4.1/§4.3). Sourced by each image's build
# wrapper AFTER it sets:
#   HERE          image dir (absolute)
#   OWRT          OpenWrt build tree
#   FLEET_SECRETS secrets file path
#   OVERLAYS      ordered overlay dirs (later wins on same path)
#   SECRETS_VARS  required variable names; rendered as __NAME__ placeholders
#   CHMOD_FILES   render-root-relative files to chmod 0755 (may be empty)
# Steps every image runs: fleet_require_secrets, fleet_render,
# fleet_render_only_gate, fleet_seed_config, fleet_build.
# OPT-IN steps (today: gale only — spec §4.1): fleet_image_id,
# fleet_force_rootfs_rebuild, fleet_out. fleet_image_id must come AFTER the
# RENDER_ONLY gate (a timestamped id would dirty the render byte-diff gates).

fleet_require_secrets() {
	[ -f "$FLEET_SECRETS" ] || {
		echo "missing $FLEET_SECRETS (copy from fleet-secrets.conf.example)" >&2
		exit 1
	}
	# shellcheck disable=SC1090
	. "$FLEET_SECRETS"
	for _v in $SECRETS_VARS; do
		eval "_val=\${$_v:-}"
		[ -n "$_val" ] || { echo "missing $_v in $FLEET_SECRETS" >&2; exit 1; }
	done
}

# Escape sed replacement metacharacters (\, &, |) so a secret containing them
# substitutes literally (backslash first, to avoid double-escaping).
fleet_esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/&/\\&/g' -e 's/|/\\|/g'; }

fleet_render() {
	rm -rf "$OWRT/files"
	mkdir -p "$OWRT/files"
	for _d in $OVERLAYS; do cp -a "$_d/." "$OWRT/files/"; done
	for _v in $SECRETS_VARS; do
		eval "_val=\${$_v}"
		_e=$(fleet_esc "$_val")
		find "$OWRT/files" -type f -exec sed -i "s|__${_v}__|$_e|g" {} +
	done
	for _f in ${CHMOD_FILES:-}; do chmod 0755 "$OWRT/files/$_f"; done
}

fleet_render_only_gate() {
	if [ "${RENDER_ONLY:-0}" = "1" ]; then
		echo "rendered overlay to $OWRT/files (RENDER_ONLY)"
		exit 0
	fi
}

fleet_image_id() {  # $1 = image name prefix (e.g. gale-openwrt). OPT-IN.
	IMAGE_ID="$1-$(date -u +%Y%m%d%H%M%S)-g$(git -C "$HERE" rev-parse --short HEAD)"
	printf '%s\n' "$IMAGE_ID" > "$OWRT/files/etc/gwifi-image-id"
	echo "image id: $IMAGE_ID"
}

fleet_seed_config() {  # $1 = function printing target lines; $2 = per-image fragment (relative to $HERE)
	{ "$1"; cat "$HERE/../fleet-image/base.config"; cat "$HERE/$2"; } > "$OWRT/.config"
	( cd "$OWRT" && make defconfig )
}

fleet_build() { ( cd "$OWRT" && make -j"${JOBS:-6}" ); }
```

- [ ] **Step 3.4: Run the test — must pass**

Run: `sh tests/fleet-image/test-build-lib.sh`
Expected: `ALL PASS` (4 PASS lines).

- [ ] **Step 3.5: Commit**

```bash
git add fleet-image/build-lib.sh tests/fleet-image/test-build-lib.sh
git commit -m "fleet-image: shared build library (render/seed/build + opt-in steps) with tests"
```

---

### Task 4: Shared base + gale respecialization + gale gates

**Files:**
- Create: `fleet-image/base.config`
- Create: `fleet-image/files/etc/config/openwisp`
- Create: `fleet-image/files/lib/gwifi/bootstrap.sh`
- Modify: `gale-image/files/etc/uci-defaults/99-gale-bootstrap` (becomes thin driver)
- Delete: `gale-image/files/etc/config/openwisp` (replaced by the shared one)
- Modify: `gale-image/gale.config` (drop lines now in base.config)
- Modify: `gale-image/build-gale-image.sh` (thin wrapper over build-lib)

- [ ] **Step 4.1: `fleet-image/base.config`**

```
# fleet-image/base.config — the shared "managed feature set" every fleet image
# ships: OpenWISP agent + monitoring, batman-adv (mesh-CAPABLE; unconfigured on
# simple-profile images — the fleet's mesh returns via OpenWISP if flipped
# back), SAE-capable wpad, usteer, and ops tooling. Per-image fragments are
# concatenated AFTER this file, so an image may turn any of these off with an
# explicit "# CONFIG_PACKAGE_x is not set" line (kconfig keeps the LAST
# assignment) — om2p does exactly that for its 7168k slot.
CONFIG_PACKAGE_openwisp-config=y
CONFIG_PACKAGE_openwisp-monitoring=y
CONFIG_PACKAGE_kmod-batman-adv=y
CONFIG_PACKAGE_batctl-default=y
# 802.11s SAE: swap the basic wpad for the mesh (SAE-capable) variant.
# CONFIG_PACKAGE_wpad-basic-mbedtls is not set
CONFIG_PACKAGE_wpad-mesh-mbedtls=y
CONFIG_PACKAGE_usteer=y
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_ip-full=y
CONFIG_PACKAGE_tcpdump-mini=y
CONFIG_PACKAGE_ethtool=y
```

- [ ] **Step 4.2: Shared `fleet-image/files/etc/config/openwisp`**

Copy `gale-image/files/etc/config/openwisp` and (a) delete the
`option mac_interface 'wan'` line and its comment block, (b) replace with:

```
	# mac_interface (device-identity MAC source) is per-image: each image's
	# uci-defaults bootstrap driver sets it (gale: 'wan' = printed label MAC
	# the OpenWISP devices are pre-created with; tenwrt: 'eth0' = the virtio
	# MAC fixed by the libvirt domain XML). The default (br-lan) no longer
	# exists on any fleet image and fell back to a random bridge MAC,
	# creating junk devices (found live on puck12, 2026-07-12).
```

Everything else (url/secret placeholders, interval, verify_ssl,
management_interface 'br0.4' + its comment, uuid) stays byte-identical.

- [ ] **Step 4.3: `fleet-image/files/lib/gwifi/bootstrap.sh`**

```sh
#!/bin/sh
# lib/gwifi/bootstrap.sh — shared first-boot wisp-connectivity functions
# (docs/fleet-image-base-design.md §4.2). Sourced by each image's
# /etc/uci-defaults/99-*-bootstrap driver. Everything here is the MINIMUM to
# reach the OpenWISP controller; APs, client VLAN legs, steering, lldpd and
# syslog are delivered by OpenWISP templates after the agent registers
# (gwifi-base post-reload-hook). Idempotent: fixed UCI section names.
# STP stays OFF everywhere: netifd's default bridge priority (0x7FFF)
# undercuts the switch fabric's 0x8000, so a fleet bridge speaking 802.1D
# would win STP root of the site L2 (bit the pucks on 2026-07-22).
# Tests stub `uci` in PATH and diff the recorded op sequence
# (tests/fleet-image/).

GWIFI_MGMT_VID=${GWIFI_MGMT_VID:-4}

# gwifi_find_device NAME -> echo "@device[i]" whose name option equals NAME;
# rc 1 when absent. (Board device sections are anonymous; index varies.)
gwifi_find_device() {
	_i=0
	while _n=$(uci -q get "network.@device[$_i].name"); do
		if [ "$_n" = "$1" ]; then echo "@device[$_i]"; return 0; fi
		_i=$((_i + 1))
	done
	return 1
}

# gwifi_adopt_board_bridge TRUNK — take the board-generated br-lan device
# section and turn it into vlan-aware br0 with TRUNK as its only port.
# rc 1 when br-lan does not exist yet (caller exits nonzero so uci-defaults
# keeps the script and retries next boot; a silent skip would self-delete it
# half-done).
gwifi_adopt_board_bridge() {
	GWIFI_BRDEV=$(gwifi_find_device br-lan) || return 1
	uci set "network.$GWIFI_BRDEV.name"='br0'
	uci set "network.$GWIFI_BRDEV.vlan_filtering"='1'
	uci set "network.$GWIFI_BRDEV.stp"='0'
	uci -q delete "network.$GWIFI_BRDEV.ports"
	uci add_list "network.$GWIFI_BRDEV.ports"="$1"
}

# gwifi_create_bridge TRUNK — create br0 from scratch (VM: a QEMU guest
# matches no armsr board case, so no board network config exists).
gwifi_create_bridge() {
	uci set network.br0dev="device"
	uci set network.br0dev.name='br0'
	uci set network.br0dev.type='bridge'
	uci set network.br0dev.vlan_filtering='1'
	uci set network.br0dev.stp='0'
	uci -q delete network.br0dev.ports
	uci add_list network.br0dev.ports="$1"
	GWIFI_BRDEV=br0dev
}

# gwifi_pin_bridge_mac FROMNAME — pin br0's MAC to FROMNAME's macaddr (gale:
# the label MAC lives on the eth-blue device section; the bridge otherwise
# picks a MAC by member-join timing, and BOTH the DHCP identity and the
# openwisp registration MAC come from the mgmt bridge). No-op when absent.
gwifi_pin_bridge_mac() {
	_from=$(gwifi_find_device "$1") || return 0
	_mac=$(uci -q get "network.$_from.macaddr")
	[ -n "$_mac" ] && uci set "network.$GWIFI_BRDEV.macaddr"="$_mac"
	return 0
}

# gwifi_mgmt_vlan PORTSPEC — mgmt bridge-vlan on br0. PORTSPEC e.g.
# 'eth-black:u*' (untagged+pvid; puck switch ports untag VLAN 4) or 'eth0:t'
# (tagged; ten64's br-raw trunk floods tagged frames).
gwifi_mgmt_vlan() {
	uci set network.brvlan_mgmt="bridge-vlan"
	uci set network.brvlan_mgmt.device='br0'
	uci set network.brvlan_mgmt.vlan="$GWIFI_MGMT_VID"
	uci -q delete network.brvlan_mgmt.ports
	uci add_list network.brvlan_mgmt.ports="$1"
}

# gwifi_mgmt_iface — default lan/wan/wan6 go away (the trunk lives in br0);
# mgmt = DHCP on br0.<vid> (wisp serves the lease).
gwifi_mgmt_iface() {
	uci -q delete network.lan
	uci -q delete network.wan
	uci -q delete network.wan6
	uci set network.mgmt="interface"
	uci set network.mgmt.device="br0.$GWIFI_MGMT_VID"
	uci set network.mgmt.proto='dhcp'
	uci commit network
}

# gwifi_dns_dhcp — no local DHCP server (wisp serves the mgmt VLAN); DNS
# rebind protection drops RFC1918 A answers from upstream — including the
# OpenWISP controller's — so whitelist the site domain (without this the
# agent cannot resolve wisp and never registers).
gwifi_dns_dhcp() {
	uci -q set dhcp.lan.ignore='1'
	uci -q del_list dhcp.@dnsmasq[0].rebind_domain='mithis.com'
	uci add_list dhcp.@dnsmasq[0].rebind_domain='mithis.com'
	uci -q commit dhcp
}

# gwifi_firewall_mgmt — mgmt joins the trusted zone (zone 0 = 'lan' in the
# default config) so ssh + the openwisp agent work; the stale 'lan' member is
# removed with the interface it referenced.
gwifi_firewall_mgmt() {
	uci -q del_list firewall.@zone[0].network='lan'
	uci -q del_list firewall.@zone[0].network='mgmt'
	uci add_list firewall.@zone[0].network='mgmt'
	uci commit firewall
}

# gwifi_openwisp_mac IFACE — per-image device-identity MAC source; the shared
# etc/config/openwisp ships without mac_interface (spec §4.2).
gwifi_openwisp_mac() {
	uci set openwisp.http.mac_interface="$1"
	uci commit openwisp
}
```

- [ ] **Step 4.4: Rewrite `99-gale-bootstrap` as a thin driver**

```sh
#!/bin/sh
# 99-gale-bootstrap — first-boot setup: the MINIMUM needed to reach the
# OpenWISP controller (wisp). Everything else — APs, radios, client VLANs,
# steering, lldpd, syslog — is delivered by OpenWISP templates after the
# agent registers. Shared logic: /lib/gwifi/bootstrap.sh (fleet-image).
#
# Ports are named after the case markings (eth-black = globe-icon jack =
# uplink; eth-blue = the other jack, unbridged and link-down here).
# Network shape: ONE VLAN-aware bridge br0 with the single trunk port
# eth-black; mgmt VLAN 4 untagged+pvid, DHCP from wisp (10.1.4.2).
# Per-VLAN software bridges over 8021q uppers of a DSA port do not work
# when the port is also hw-offload-bridged untagged (qca8k claims tagged
# ingress); the supported DSA pattern is vlan_filtering=1 + bridge-vlans.
. /lib/gwifi/bootstrap.sh

# On the true first boot this can run before the board network config exists:
# exit NONZERO so uci-defaults keeps the script and retries next boot.
if ! gwifi_adopt_board_bridge eth-black; then
	echo "gale-bootstrap: br-lan device not found (board config not" \
	     "generated yet?) — will retry next boot" >&2
	exit 1
fi
gwifi_pin_bridge_mac eth-blue
gwifi_mgmt_vlan 'eth-black:u*'
gwifi_mgmt_iface
gwifi_dns_dhcp
gwifi_firewall_mgmt
# Device identity MAC = the wan port (the printed label MAC that OpenWISP
# devices are pre-created with).
gwifi_openwisp_mac wan
exit 0
```

- [ ] **Step 4.5: Run the equivalence test — must pass**

Run: `sh tests/fleet-image/test-gale-bootstrap-equivalence.sh`
Expected: `ALL PASS`. If the diff shows divergence, fix `bootstrap.sh` /the driver
until the op sequence matches — do NOT widen the filter beyond the two
mac_interface lines.

- [ ] **Step 4.6: Slim `gale-image/gale.config`**

Delete exactly these lines (now in base.config): `CONFIG_PACKAGE_openwisp-config=y`,
`CONFIG_PACKAGE_openwisp-monitoring=y`, `CONFIG_PACKAGE_kmod-batman-adv=y`,
`CONFIG_PACKAGE_batctl-default=y`, the wpad swap pair (comment line
`# CONFIG_PACKAGE_wpad-basic-mbedtls is not set` + `CONFIG_PACKAGE_wpad-mesh-mbedtls=y`
and its `# 802.11s SAE…` comment), `CONFIG_PACKAGE_usteer=y`,
`CONFIG_PACKAGE_luci=y`, `CONFIG_PACKAGE_ip-full=y`, `CONFIG_PACKAGE_tcpdump-mini=y`,
`CONFIG_PACKAGE_ethtool=y`. KEEP (gale-only): kmod-netconsole (+comment), the
batman re-enable history comment (reattach it to the top of the file as historical
context), alfred + ALFRED_VIS (+comment), the 8021q note, lldpd (+comment),
kmod-cros-ec (+comment block). Add at the top:
`# Layered over fleet-image/base.config (shared managed feature set).`

- [ ] **Step 4.7: Rewrite `build-gale-image.sh` as a thin wrapper**

```sh
#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
# fleet-secrets.conf lives OUTSIDE the repo (om2p/tenwrt convention; gale moved
# off gale-secrets.conf — design spec §4.2). The in-repo default path never
# exists, so runs always say FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf
# and fleet_require_secrets' error explains that when forgotten.
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
SECRETS_VARS="OPENWISP_SHARED_SECRET MESH_SAE_KEY MESH_ID OPENWISP_URL TOPOLOGY_RECEIVE_URL"
OVERLAYS="$HERE/../fleet-image/files $HERE/files"
# gale-netconsole is a parity ADDITION to the old chmod list (it is already
# 100755 in git, so this is a no-op belt-and-braces line).
CHMOD_FILES="etc/uci-defaults/99-gale-bootstrap etc/init.d/gwifi-topology
             usr/sbin/gwifi-topology-push usr/sbin/gale-mesh-bootstrap
             etc/init.d/gale-netconsole"
# shellcheck disable=SC1091
. "$HERE/../fleet-image/build-lib.sh"
fleet_require_secrets
fleet_render
fleet_render_only_gate

# image id — the netboot installer's idempotence marker; sidecar emitted at
# the out/ step so publish (gwifi-netboot publish) keeps manifest and baked
# marker in sync. See docs/wisp-netboot-install-design.md §5.5.
fleet_image_id gale-openwrt

gale_targets() {
	printf 'CONFIG_TARGET_ipq40xx=y\nCONFIG_TARGET_ipq40xx_chromium=y\nCONFIG_TARGET_ipq40xx_chromium_DEVICE_google_wifi=y\n'
}
fleet_seed_config gale_targets gale.config

# Force the rootfs image to regenerate: OpenWrt caches root.squashfs and does
# NOT rebuild it when only files/ changes — it shipped a squashfs baked with a
# STALE image-id marker on 2026-07-18 (installer post-flash check failed every
# reflash). Removing the outputs makes make rebuild them from the current
# staging, which carries the marker just written above.
rm -f "$OWRT"/build_dir/target-*/linux-ipq40xx_chromium/root.squashfs \
      "$OWRT"/bin/targets/ipq40xx/chromium/*-google_wifi-squashfs-factory.bin
fleet_build

# out/ artifacts + sidecar: bin/targets is SHARED with other builds (the
# installer build regenerates factory.bin there with stock files). Publishing
# from bin/targets shipped a stock image to the fleet on 2026-07-12. Always
# publish from out/.
BIN="$OWRT/bin/targets/ipq40xx/chromium/openwrt-ipq40xx-chromium-google_wifi-squashfs-factory.bin"
OUT="$HERE/out"
mkdir -p "$OUT"
cp "$BIN" "$OUT/factory-$IMAGE_ID.bin"
ln -sf "factory-$IMAGE_ID.bin" "$OUT/factory.bin"
printf '%s\n' "$IMAGE_ID" > "$OUT/factory.bin.image-id"
echo "artifact: $OUT/factory-$IMAGE_ID.bin"
echo "sidecar: $OUT/factory.bin.image-id ($IMAGE_ID)"
echo "publish from $OUT - never from bin/targets"
```

- [ ] **Step 4.8: Migrate the local secrets file (repo-external, this box only)**

The untracked FILLED secrets (5 vars) live in the wisp-netboot-install worktree
(`.worktrees/wisp-netboot-install/gale-image/gale-secrets.conf` — Step 1.4
already copied it into this worktree's `gale-image/`, also gitignored):

```bash
grep -q '^TOPOLOGY_RECEIVE_URL=' /home/tim/local/gwifi/fleet-secrets.conf || \
  grep '^TOPOLOGY_RECEIVE_URL=' \
    /home/tim/local/gwifi/gwifi-openwrt/.worktrees/wisp-netboot-install/gale-image/gale-secrets.conf \
  >> /home/tim/local/gwifi/fleet-secrets.conf
```

Verify: `grep -c '^TOPOLOGY_RECEIVE_URL=' /home/tim/local/gwifi/fleet-secrets.conf`
→ `1`. Never print the value. Leave `gale-secrets.conf` itself in place
(deprecated; the README note in Task 15 says so).

- [ ] **Step 4.9: Delete the per-image openwisp file + old example**

```bash
git rm gale-image/files/etc/config/openwisp gale-image/gale-secrets.conf.example
```

Then update `fleet-secrets.conf.example`: extend the header comment to
"gale + om2p + tenwrt", and append the `TOPOLOGY_RECEIVE_URL` entry with its
comment block copied from `gale-secrets.conf.example`.

- [ ] **Step 4.10: AFTER render + byte-diff gate**

```bash
cd $ROOT
mkdir -p tmp/gate/after-gale
OWRT=$ROOT/tmp/gate/after-gale RENDER_ONLY=1 \
  FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf sh gale-image/build-gale-image.sh
diff -r tmp/gate/before-gale/files tmp/gate/after-gale/files
```

Expected diff — EXACTLY this allowlist, judged semantically (diff -r prints the
topmost new directory, i.e. `Only in …/after-gale/files: lib`, since the before
tree has no `lib/` at all):
1. the new `lib/` subtree (only content: `lib/gwifi/bootstrap.sh`),
2. `files/etc/uci-defaults/99-gale-bootstrap` differs (monolith → driver),
3. `files/etc/config/openwisp` differs (mac_interface option + comment moved out,
   replacement comment in).
Any other file appearing in the diff = regression; fix before proceeding.

- [ ] **Step 4.11: `.config` gate**

Re-run the gale seeding via the new wrapper's pieces in `openwrt-armsr`
(requires Task 0 + Step 1.5 done):

```bash
{ printf 'CONFIG_TARGET_ipq40xx=y\nCONFIG_TARGET_ipq40xx_chromium=y\nCONFIG_TARGET_ipq40xx_chromium_DEVICE_google_wifi=y\n'; \
  cat fleet-image/base.config; cat gale-image/gale.config; } > /home/tim/local/gwifi/openwrt-armsr/.config
( cd /home/tim/local/gwifi/openwrt-armsr && make defconfig )
diff /home/tim/local/gwifi/openwrt-armsr/.config tmp/gate/before-gale.config
```

Expected: NO diff (identical post-defconfig config). Any diff = a package line was
lost/added in the base/fragment split; fix.

- [ ] **Step 4.12: Run all fleet-image tests + commit**

```bash
sh tests/fleet-image/test-build-lib.sh          # ALL PASS
sh tests/fleet-image/test-gale-bootstrap-equivalence.sh   # ALL PASS
git add fleet-image/ gale-image/ fleet-secrets.conf.example
git commit -m "fleet-image: shared base (config+overlay+bootstrap lib); gale becomes a thin specialization

Render byte-diff vs pre-refactor: only the allowlisted lib/bootstrap/openwisp
moves. Post-defconfig .config identical. Bootstrap uci op-sequence equal
modulo the mac_interface move (tests/fleet-image)."
```

---

### Task 5: om2p respecialization + om2p gates

**Files:**
- Modify: `om2p-image/build-om2p-image.sh` (thin wrapper; overlay list = own
  `files/` + `fleet-files/`, NO base overlay — spec §4.1)
- Modify: `om2p-image/om2p.config` (drop base-duplicated lines; add the four
  fit disables)

- [ ] **Step 5.1: Rewrite `build-om2p-image.sh`**

```sh
#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
SECRETS_VARS="OPENWISP_SHARED_SECRET MESH_SAE_KEY MESH_ID OPENWISP_URL"
# om2p is still mesh-era: own overlay + the shared fleet-files (backhaul gate
# + hotplug hook), NO fleet-image/files — its render must stay byte-identical
# until the simple-profile conversion (design spec D6/§4.1).
OVERLAYS="$HERE/files $HERE/../fleet-files"
CHMOD_FILES="etc/uci-defaults/99-om2p-bootstrap usr/sbin/gwifi-backhaul-gate
             etc/hotplug.d/net/30-gwifi-backhaul"
# shellcheck disable=SC1091
. "$HERE/../fleet-image/build-lib.sh"
fleet_require_secrets
fleet_render
fleet_render_only_gate

# ath79/generic + the 4 OM2P profiles (multi-profile). Set DEVICES="..." to
# override (e.g. a single profile for a per-device build).
om2p_targets() {
	printf 'CONFIG_TARGET_ath79=y\nCONFIG_TARGET_ath79_generic=y\nCONFIG_TARGET_MULTI_PROFILE=y\n'
	for d in ${DEVICES:-openmesh_om2p-lc openmesh_om2p-v1 openmesh_om2p-v2 openmesh_om2p-v4}; do
		printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_%s=y\n' "$d"
	done
}
fleet_seed_config om2p_targets om2p.config
fleet_build
echo "images: $OWRT/bin/targets/ath79/generic/"
```

- [ ] **Step 5.2: Slim `om2p-image/om2p.config`**

New content (keep `CONFIG_TARGET_ROOTFS_TARGZ=y` and the slim-block comment;
drop the base-duplicated managed-set lines; ADD explicit disables for the four
base packages om2p never shipped):

```
# om2p.config — ath79 fragment layered over fleet-image/base.config.
CONFIG_TARGET_ROOTFS_TARGZ=y
# --- slim to the 7168k OM2P slot: drop daemons unused on an L2 mesh AP ---
# These nodes are pure L2 bridges; ten64 routes, firewalls, and serves DHCP/DNS.
# Dropping these frees ~0.9 MB and keeps every managed feature (openwisp +
# monitoring + mesh + batman + steering). firewall4 pulls in nftables/libnftables
# (~0.7 MB); they cascade out when it is deselected.
# CONFIG_PACKAGE_dnsmasq is not set
# CONFIG_PACKAGE_firewall4 is not set
# CONFIG_PACKAGE_ppp is not set
# CONFIG_PACKAGE_ppp-mod-pppoe is not set
# CONFIG_PACKAGE_odhcpd-ipv6only is not set
# base.config extras that do not fit the 7168k slot (om2p never shipped them):
# CONFIG_PACKAGE_luci is not set
# CONFIG_PACKAGE_ip-full is not set
# CONFIG_PACKAGE_tcpdump-mini is not set
# CONFIG_PACKAGE_ethtool is not set
```

- [ ] **Step 5.3: Render gate — must be byte-IDENTICAL (no allowlist)**

```bash
cd $ROOT
mkdir -p tmp/gate/after-om2p
OWRT=$ROOT/tmp/gate/after-om2p RENDER_ONLY=1 \
  FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf sh om2p-image/build-om2p-image.sh
diff -r tmp/gate/before-om2p/files tmp/gate/after-om2p/files && echo IDENTICAL
```

Expected: `IDENTICAL` (empty diff). Note the overlay ORDER preserved: own files
then fleet-files on top.

- [ ] **Step 5.4: `.config` gate**

```bash
{ printf 'CONFIG_TARGET_ath79=y\nCONFIG_TARGET_ath79_generic=y\nCONFIG_TARGET_MULTI_PROFILE=y\n'; \
  for d in openmesh_om2p-lc openmesh_om2p-v1 openmesh_om2p-v2 openmesh_om2p-v4; do \
    printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_%s=y\n' "$d"; done; \
  cat fleet-image/base.config; cat om2p-image/om2p.config; } > /home/tim/local/gwifi/openwrt-armsr/.config
( cd /home/tim/local/gwifi/openwrt-armsr && make defconfig )
diff /home/tim/local/gwifi/openwrt-armsr/.config tmp/gate/before-om2p.config
```

Expected: NO diff. Also verify the DEVICES override still works:
`DEVICES=openmesh_om2p-lc RENDER_ONLY=0` dry check is covered by the full build
in Task 12 — at minimum re-run the seeding with
`DEVICES=openmesh_om2p-lc` and confirm the generated `.config` contains exactly
one `DEVICE_openmesh` line before `defconfig`.

- [ ] **Step 5.5: Commit**

```bash
git add om2p-image/
git commit -m "om2p-image: specialize from fleet-image base (build-lib + layered config)

Render byte-identical to pre-refactor; post-defconfig .config identical;
overlay content stays mesh-era (own files + fleet-files, no base overlay)."
```

---

### Task 6: verify_lib.py — shared verifier helpers

**Files:**
- Create: `fleet-image/verify_lib.py`
- Modify: `gale-image/verify-gale-image.py`, `om2p-image/verify-om2p-image.py`,
  `tenwrt-image/verify-tenwrt-image.py` (import shared helpers; behavior unchanged)

- [ ] **Step 6.1: Write `fleet-image/verify_lib.py`**

Move the three duplicated helpers verbatim from the existing verifiers (they are
already near-identical); keep each verifier's rootfs reader local (they genuinely
differ: squashfs vs tarball vs etc-extract):

```python
"""fleet-image/verify_lib.py — checks shared by the image verifiers.

Import from a sibling image dir:
    sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "fleet-image"))
    from verify_lib import parse_secrets, check_no_placeholders, find_manifest, require_packages
"""
import glob
import os
import re

PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")


def parse_secrets(path):
    """KEY=VALUE lines -> dict (quotes stripped, comments/blank skipped)."""
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
            if not m:
                continue
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def check_no_placeholders(text, label, failures):
    for m in sorted(set(PLACEHOLDER_RE.findall(text))):
        failures.append("%s: unrendered placeholder %s" % (label, m))


def find_manifest(image_dir):
    """Newest *.manifest under image_dir, or None."""
    manifests = glob.glob(os.path.join(image_dir, "*.manifest"))
    return max(manifests, key=os.path.getmtime) if manifests else None


def manifest_packages(path):
    """manifest 'name - version' lines -> set of package names."""
    pkgs = set()
    with open(path) as f:
        for line in f:
            name = line.split(" - ")[0].strip()
            if name:
                pkgs.add(name)
    return pkgs


def require_packages(manifest_path, required, failures):
    pkgs = manifest_packages(manifest_path)
    for want in required:
        if want not in pkgs:
            failures.append("manifest: missing required package %s" % want)
    return pkgs
```

- [ ] **Step 6.2: Repoint the three verifiers**

In each verifier: add the `sys.path.insert` + import, delete the local
`parse_secrets` (all three) and any local placeholder-regex/manifest-glob duplicate
that verify_lib now covers, keeping the verifier-specific assertions untouched. The
existing manifest-check loops keep their own REQUIRED_PACKAGES lists. Where a
verifier's local helper differs in behavior (e.g. gale's `find_manifest(image_dir,
tar_path)` two-arg variant), KEEP the local one and only replace exact-equivalent
code — this task must not change any verifier's verdict.

- [ ] **Step 6.3: Syntax-check all three + run the only runnable one**

```bash
uv run python -m py_compile fleet-image/verify_lib.py gale-image/verify-gale-image.py \
  om2p-image/verify-om2p-image.py tenwrt-image/verify-tenwrt-image.py
```

Expected: silent success. (gale/om2p/tenwrt verifiers need built artifacts — full
runs happen in Tasks 11/12; gale's has no build on this branch and is
code-review-only, per spec §5 the gale rebuild is Tim's call.)

- [ ] **Step 6.4: Commit**

```bash
git add fleet-image/verify_lib.py gale-image/verify-gale-image.py \
  om2p-image/verify-om2p-image.py tenwrt-image/verify-tenwrt-image.py
git commit -m "fleet-image: shared verify_lib (secrets/placeholders/manifest); verifiers repointed"
```

---

### Task 7: tenwrt.config rewrite — firmware fix + guest tools + base layering

**Files:**
- Modify: `tenwrt-image/tenwrt.config`

- [ ] **Step 7.1: Rewrite `tenwrt.config`**

Replace the managed-set block (now in base.config) and the wrong firmware comment.
Full new content:

```
# tenwrt.config — armsr/armv8 fragment for the ten64 Wi-Fi VM, layered over
# fleet-image/base.config. TARGET lines are emitted by build-tenwrt-image.sh.
CONFIG_TARGET_ROOTFS_EXT4FS=y
# Enlarged from 256: holds the full in-tree PCIe Wi-Fi driver+firmware set below.
CONFIG_TARGET_ROOTFS_PARTSIZE=1024
CONFIG_TARGET_ROOTFS_TARGZ=y
# Raw (un-gzipped) disk image so qemu can boot it directly.
# CONFIG_TARGET_IMAGES_GZIP is not set
# --- VM guest tools: hypervisor-initiated graceful shutdown + guest agent ---
# acpid's default handler maps the ACPI power button to /sbin/poweroff — which
# is exactly what `virsh shutdown` (mode=acpi; tenwrt.xml has <acpi/>) sends.
# qemu-ga needs a virtio-serial <channel org.qemu.guest_agent.0> in the domain
# XML (STAGED in ten64-host/tenwrt.xml, not yet applied); inert until then.
# CONFIG_VIRTIO_CONSOLE=y is built into the armsr kernel.
CONFIG_PACKAGE_acpid=y
CONFIG_PACKAGE_qemu-ga=y
# --- PCIe Wi-Fi: ALL in-tree drivers + their firmware for any card that may
#     be passed through to this VM (2.4/5/6 GHz + WiFi 7). HaLow (802.11ah)
#     has no mainline driver — deferred, see README.
# Qualcomm/Atheros drivers
CONFIG_PACKAGE_kmod-ath9k=y
CONFIG_PACKAGE_kmod-ath10k=y
CONFIG_PACKAGE_kmod-ath11k-pci=y
CONFIG_PACKAGE_kmod-ath12k=y
# ath10k firmware (PCIe chips)
CONFIG_PACKAGE_ath10k-firmware-qca988x=y
CONFIG_PACKAGE_ath10k-firmware-qca9887=y
CONFIG_PACKAGE_ath10k-firmware-qca9888=y
CONFIG_PACKAGE_ath10k-firmware-qca9984=y
CONFIG_PACKAGE_ath10k-firmware-qca99x0=y
CONFIG_PACKAGE_ath10k-firmware-qca6174=y
CONFIG_PACKAGE_ath10k-firmware-qca9377=y
# ath11k firmware (WiFi 6 / 6E)
CONFIG_PACKAGE_ath11k-firmware-qcn9074=y
CONFIG_PACKAGE_ath11k-firmware-qca6390=y
CONFIG_PACKAGE_ath11k-firmware-qca2066=y
# ath12k firmware (WiFi 7)
CONFIG_PACKAGE_ath12k-firmware-qcn9274=y
CONFIG_PACKAGE_ath12k-firmware-wcn7850=y
# MediaTek mt76 DRIVERS. NOTE: mt76 kmods do NOT bundle firmware — the blobs
# live in separate kmod-mtXXXX-firmware packages (the pre-2026-07 image
# shipped mt7915e with no firmware and the MT7915 could not load). ten64's
# card IS an MT7915 (14c3:7915).
CONFIG_PACKAGE_kmod-mt76x0e=y
CONFIG_PACKAGE_kmod-mt76x2=y
CONFIG_PACKAGE_kmod-mt7615e=y
CONFIG_PACKAGE_kmod-mt7915e=y
CONFIG_PACKAGE_kmod-mt7921e=y
CONFIG_PACKAGE_kmod-mt7925e=y
CONFIG_PACKAGE_kmod-mt7996e=y
# MediaTek mt76 FIRMWARE (split packages; one per chip family)
CONFIG_PACKAGE_kmod-mt7615-firmware=y
CONFIG_PACKAGE_kmod-mt7915-firmware=y
CONFIG_PACKAGE_kmod-mt7916-firmware=y
CONFIG_PACKAGE_kmod-mt7921-firmware=y
CONFIG_PACKAGE_kmod-mt7922-firmware=y
CONFIG_PACKAGE_kmod-mt7925-firmware=y
CONFIG_PACKAGE_kmod-mt7996-firmware=y
# Realtek rtw88 (PCIe 11n/11ac; per-chip kmod pulls firmware+bus glue)
CONFIG_PACKAGE_kmod-rtw88-8723de=y
CONFIG_PACKAGE_kmod-rtw88-8814ae=y
CONFIG_PACKAGE_kmod-rtw88-8821ce=y
CONFIG_PACKAGE_kmod-rtw88-8822be=y
CONFIG_PACKAGE_kmod-rtw88-8822ce=y
# Realtek rtw89 (PCIe WiFi 6/6E/7; per-chip kmod auto-selects its firmware)
CONFIG_PACKAGE_kmod-rtw89-pci=y
CONFIG_PACKAGE_kmod-rtw89-8851be=y
CONFIG_PACKAGE_kmod-rtw89-8852ae=y
CONFIG_PACKAGE_kmod-rtw89-8852be=y
CONFIG_PACKAGE_kmod-rtw89-8852ce=y
CONFIG_PACKAGE_kmod-rtw89-8922ae=y
```

- [ ] **Step 7.2: Verify the firmware selections resolve (defconfig check)**

```bash
{ printf 'CONFIG_TARGET_armsr=y\nCONFIG_TARGET_armsr_armv8=y\nCONFIG_TARGET_armsr_armv8_DEVICE_generic=y\n'; \
  cat fleet-image/base.config; cat tenwrt-image/tenwrt.config; } > /home/tim/local/gwifi/openwrt-armsr/.config
( cd /home/tim/local/gwifi/openwrt-armsr && make defconfig )
for p in mt7615 mt7915 mt7916 mt7921 mt7922 mt7925 mt7996; do
  grep "^CONFIG_PACKAGE_kmod-$p-firmware=y" /home/tim/local/gwifi/openwrt-armsr/.config \
    || echo "MISSING kmod-$p-firmware"
done
grep -E '^CONFIG_PACKAGE_(acpid|qemu-ga)=y' /home/tim/local/gwifi/openwrt-armsr/.config
```

Expected: all seven firmware lines survive defconfig (none deselected by
unmet deps); acpid + qemu-ga present. If any firmware line vanished, inspect
`package/kernel/mt76/Makefile` in the tree for the real symbol name and fix the
fragment (do not guess) — also check whether `kmod-mt7996-firmware` pulls a
`-common` sibling automatically (it should via DEPENDS; if defconfig shows
`kmod-mt7996-firmware-common=y` appearing on its own, that is fine).

- [ ] **Step 7.3: Commit**

```bash
git add tenwrt-image/tenwrt.config
git commit -m "tenwrt-image: mt76 split firmware (mt7915 fix), acpid+qemu-ga, layer over base.config"
```

---

### Task 8: tenwrt overlay rewrite — simple-profile parity

**Files:**
- Modify: `tenwrt-image/files/etc/uci-defaults/99-tenwrt-bootstrap` (thin driver)
- Modify: `tenwrt-image/files/usr/sbin/gwifi-radio-setup` (slim: band-normalize)
- Delete: `tenwrt-image/files/etc/config/wireless`, `tenwrt-image/files/etc/config/usteer`,
  `tenwrt-image/files/etc/config/openwisp` (shared overlay provides openwisp)
- Modify: `tenwrt-image/build-tenwrt-image.sh` (thin wrapper; drops fleet-files)
- Create: `tests/fleet-image/test-tenwrt-bootstrap-ops.sh` + golden
  `tests/fleet-image/tenwrt-bootstrap.oplog`
- Modify: `tests/tenwrt/test-radio-setup.sh` (band-normalization cases)

- [ ] **Step 8.1: Write the golden-oplog test FIRST (fails: old bootstrap differs)**

`tests/fleet-image/test-tenwrt-bootstrap-ops.sh` (mode 0755):

```sh
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
```

Golden `tests/fleet-image/tenwrt-bootstrap.oplog` (this IS the expected write
sequence of the new driver — derive: hostname, create_bridge eth0, mgmt_vlan
eth0:t, mgmt_iface, dns_dhcp, firewall, openwisp mac):

```
set system.@system[0].hostname=tenwrt
commit system
set network.br0dev=device
set network.br0dev.name=br0
set network.br0dev.type=bridge
set network.br0dev.vlan_filtering=1
set network.br0dev.stp=0
delete network.br0dev.ports
add_list network.br0dev.ports=eth0
set network.brvlan_mgmt=bridge-vlan
set network.brvlan_mgmt.device=br0
set network.brvlan_mgmt.vlan=4
delete network.brvlan_mgmt.ports
add_list network.brvlan_mgmt.ports=eth0:t
delete network.lan
delete network.wan
delete network.wan6
set network.mgmt=interface
set network.mgmt.device=br0.4
set network.mgmt.proto=dhcp
commit network
set dhcp.lan.ignore=1
del_list dhcp.@dnsmasq[0].rebind_domain=mithis.com
add_list dhcp.@dnsmasq[0].rebind_domain=mithis.com
commit dhcp
del_list firewall.@zone[0].network=lan
del_list firewall.@zone[0].network=mgmt
add_list firewall.@zone[0].network=mgmt
commit firewall
set openwisp.http.mac_interface=eth0
commit openwisp
```

Run: `sh tests/fleet-image/test-tenwrt-bootstrap-ops.sh`
Expected: FAIL (current bootstrap is the mesh-era monolith).

- [ ] **Step 8.2: Rewrite `99-tenwrt-bootstrap`**

```sh
#!/bin/sh
# 99-tenwrt-bootstrap — first-boot wisp-connectivity for the ten64 Wi-Fi VM
# (KVM guest 'tenwrt'): exact simple-profile parity with the pucks — bake ONLY
# what reaches the OpenWISP controller. APs and the client VLAN legs arrive
# via OpenWISP templates after registration (gwifi-base post-reload-hook keys
# on the eth0 trunk). Shared logic: /lib/gwifi/bootstrap.sh (fleet-image).
#
# Uplink: single virtio TRUNK NIC eth0 on ten64's br-raw (floods all tagged
# frames), so mgmt VLAN 4 rides TAGGED here — pucks get it untagged from
# their switch port. A QEMU guest matches no armsr board case, so no board
# network exists: create br0 from scratch (no retry path needed).
. /lib/gwifi/bootstrap.sh

uci set system.@system[0].hostname='tenwrt'
uci commit system

gwifi_create_bridge eth0
gwifi_mgmt_vlan 'eth0:t'
gwifi_mgmt_iface
gwifi_dns_dhcp
gwifi_firewall_mgmt
# Device identity MAC = the virtio NIC (fixed by the libvirt domain XML).
gwifi_openwisp_mac eth0

# Radios (VFIO passthrough) may already be present at first boot: normalize
# radio0=2.4GHz / radio1=5GHz so the OpenWISP gwifi-aps template binds.
# No-op with no phy (pre-passthrough / smoke boot).
[ -x /usr/sbin/gwifi-radio-setup ] && /usr/sbin/gwifi-radio-setup || true

# First-boot completion marker. uci-defaults stdout is captured by logd, NOT
# shown on the serial console, so write it to /dev/console explicitly —
# visible to an operator and observable by qemu-smoke-boot.py.
if [ -w /dev/console ]; then
	echo "TENVM-BOOTSTRAP-COMPLETE uplink=eth0" > /dev/console
else
	echo "TENVM-BOOTSTRAP-COMPLETE uplink=eth0"
fi
exit 0
```

Note: in the sandbox test `/dev/console` is not writable by a regular user, so the
marker lands on stdout — which the test asserts. On a real boot it goes to the
console, same as before.

- [ ] **Step 8.3: Run the ops test — must pass**

Run: `sh tests/fleet-image/test-tenwrt-bootstrap-ops.sh` → `ALL PASS`.

- [ ] **Step 8.4: Slim `gwifi-radio-setup`**

Keep the header block (rewrite the description: enable + band-normalize, no mesh),
keep `any_phy_present`, `bdf_of_phy`, `wifi_devices` and the sourcing guard
unchanged. Add one pure function and replace `main`:

```sh
# radio_swap_needed BAND0 BAND1 -> "1" when radio0 came up 5/6 GHz while
# radio1 is 2.4 GHz (the gwifi-aps template binds radio0=2g4, radio1=5g).
radio_swap_needed() {
	case "${1:-}:${2:-}" in 5g:2g|6g:2g) echo 1 ;; esac
}

main() {
	if [ -z "$(any_phy_present)" ]; then
		logger -t "$LOG_TAG" "no Wi-Fi phys present; skipping radio setup"
		return 0
	fi
	_sysfs=${GWIFI_RADIO_SYSFS:-/sys/class/ieee80211}
	for _p in "$_sysfs"/phy*; do
		[ -e "$_p/device" ] || continue
		_pn=${_p##*/}
		if [ -e "$_p/device/driver" ]; then _drv=$(readlink "$_p/device/driver"); _drv=${_drv##*/}; else _drv="(unbound)"; fi
		logger -t "$LOG_TAG" "present: $_pn driver=$_drv bdf=$(bdf_of_phy "$_pn")"
	done
	# Generate radioN sections (+ PCI paths + auto-detected band) for whatever
	# card(s) are present.
	wifi config
	# wifi config emits a default AP per radio (ssid=OpenWrt) — never beacon it.
	uci -q delete wireless.default_radio0
	uci -q delete wireless.default_radio1
	for _r in $(wifi_devices); do
		uci set "wireless.$_r.channel=auto"
		uci set "wireless.$_r.disabled=0"
		logger -t "$LOG_TAG" "enabled $_r (band=$(uci -q get "wireless.$_r.band"))"
	done
	# Normalize radio0=2.4GHz / radio1=5GHz for the gwifi-aps template (DBDC
	# phy order is not guaranteed; paths travel with the renamed sections).
	_b0=$(uci -q get wireless.radio0.band); _b1=$(uci -q get wireless.radio1.band)
	if [ -n "$(radio_swap_needed "$_b0" "$_b1")" ]; then
		uci rename wireless.radio0=radiotmp
		uci rename wireless.radio1=radio0
		uci rename wireless.radiotmp=radio1
		logger -t "$LOG_TAG" "swapped radio0<->radio1 (radio0 was $_b0)"
	fi
	uci commit wireless
	wifi reload
}
```

- [ ] **Step 8.5: Extend `tests/tenwrt/test-radio-setup.sh`**

After the existing `bdf_of_phy` assertions, add:

```sh
eq "swap 5g:2g"    "1" "$(radio_swap_needed 5g 2g)"
eq "swap 6g:2g"    "1" "$(radio_swap_needed 6g 2g)"
eq "no swap 2g:5g" ""  "$(radio_swap_needed 2g 5g)"
eq "no swap 2g:"   ""  "$(radio_swap_needed 2g "")"
eq "no swap :"     ""  "$(radio_swap_needed "" "")"
```

Run: `sh tests/tenwrt/test-radio-setup.sh` → `ALL PASS`.

- [ ] **Step 8.6: Delete the mesh-era overlay files**

```bash
git rm tenwrt-image/files/etc/config/wireless tenwrt-image/files/etc/config/usteer \
       tenwrt-image/files/etc/config/openwisp
```

(usteer config now comes from the wisp `gwifi-base` template; openwisp UCI from
`fleet-image/files`; no baked wireless at all.)

- [ ] **Step 8.7: Rewrite `build-tenwrt-image.sh` as a thin wrapper**

```sh
#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
# Dedicated build tree (design D7): NEVER the shared /home/tim/local/gwifi/openwrt,
# which the live gale/puck builds use.
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt-armsr}
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
SECRETS_VARS="OPENWISP_SHARED_SECRET OPENWISP_URL"
OVERLAYS="$HERE/../fleet-image/files $HERE/files"
CHMOD_FILES="etc/uci-defaults/99-tenwrt-bootstrap usr/sbin/gwifi-radio-setup"
# shellcheck disable=SC1091
. "$HERE/../fleet-image/build-lib.sh"
fleet_require_secrets
fleet_render
fleet_render_only_gate

tenwrt_targets() {
	printf 'CONFIG_TARGET_armsr=y\nCONFIG_TARGET_armsr_armv8=y\nCONFIG_TARGET_armsr_armv8_DEVICE_generic=y\n'
}
fleet_seed_config tenwrt_targets tenwrt.config
fleet_build
echo "images: $OWRT/bin/targets/armsr/armv8/"
```

- [ ] **Step 8.8: Run every touched suite + commit**

```bash
sh tests/fleet-image/test-tenwrt-bootstrap-ops.sh   # ALL PASS
sh tests/tenwrt/test-radio-setup.sh                 # ALL PASS
sh tests/fleet-image/test-gale-bootstrap-equivalence.sh  # still ALL PASS
git add tenwrt-image/ tests/
git commit -m "tenwrt-image: simple-profile parity overlay (thin bootstrap driver, band-normalize radio-setup, no baked mesh)"
```

---

### Task 9: tenwrt verifier update

**Files:**
- Modify: `tenwrt-image/verify-tenwrt-image.py`

- [ ] **Step 9.1: Update the assertions**

- `OWRT` default → `/home/tim/local/gwifi/openwrt-armsr`.
- REQUIRED_PACKAGES: add `"acpid", "qemu-ga", "kmod-mt7615-firmware",
  "kmod-mt7915-firmware", "kmod-mt7916-firmware", "kmod-mt7921-firmware",
  "kmod-mt7922-firmware", "kmod-mt7925-firmware", "kmod-mt7996-firmware"`;
  drop the stale "mt76 bundled in kmod" comment.
- Rootfs content checks: REPLACE the wireless-mesh and backhaul checks with:
  - `etc/config/openwisp`: real URL + secret, `management_interface 'br0.4'`,
    NO `mac_interface` line (bootstrap sets it), no placeholders.
  - `etc/uci-defaults/99-tenwrt-bootstrap`: executable; contains
    `gwifi_create_bridge eth0` and `TENVM-BOOTSTRAP-COMPLETE`; no placeholders.
  - `lib/gwifi/bootstrap.sh` present.
  - `usr/sbin/gwifi-radio-setup` executable; contains `radio_swap_needed`.
  - ABSENT (fail if present): `etc/config/wireless`, `etc/config/usteer`,
    `usr/sbin/gwifi-backhaul-gate`, `etc/hotplug.d/net/30-gwifi-backhaul`.
  - Firmware blobs present in the rootfs tarball:
    `lib/firmware/mediatek/mt7915_wa.bin`, `mt7915_wm.bin`, `mt7915_rom_patch.bin`
    (presence via tar member names; do not decode binary).
- Keep: combined-efi artifact check, newest-tarball selection, secrets handling
  (never print values).

- [ ] **Step 9.2: Syntax check + commit**

```bash
uv run python -m py_compile tenwrt-image/verify-tenwrt-image.py
git add tenwrt-image/verify-tenwrt-image.py
git commit -m "tenwrt-image: verifier asserts mt7915 firmware blobs, guest tools, no mesh leftovers"
```

(The full run happens in Task 11 after the build.)

---

### Task 10: qemu-smoke-boot — ACPI graceful-shutdown assertion

**Files:**
- Modify: `tenwrt-image/qemu-smoke-boot.py`

- [ ] **Step 10.1: Add the QMP powerdown phase**

- `OWRT` default → `/home/tim/local/gwifi/openwrt-armsr` (follows the image dir).
- Add near the top: `SHUTDOWN_TIMEOUT = int(os.environ.get("SMOKE_SHUTDOWN_TIMEOUT", "180"))`.
- Add the QMP helper:

```python
def qmp_powerdown(sock_path):
    """Connect to the QMP socket and inject the ACPI power button."""
    import json
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    f = s.makefile("rw")
    f.readline()                                              # greeting banner
    f.write(json.dumps({"execute": "qmp_capabilities"}) + "\n"); f.flush()
    f.readline()                                              # {"return": {}}
    f.write(json.dumps({"execute": "system_powerdown"}) + "\n"); f.flush()
    s.close()
```

- Extend the qemu command:
  `qmp_sock = os.path.join(TMP, "smoke-qmp.sock")` (unlink stale first);
  `cmd += ["-qmp", "unix:%s,server,nowait" % qmp_sock]`.
- Rework the read loop into two phases:
  1. Boot phase (existing): wait for `MARKER`. On seeing it, set `ok = True` but do
     NOT break — keep reading until `BOOT_FALLBACK` ("procd: - init complete -",
     i.e. all initscripts incl. acpid have started) or 30 s pass, then call
     `qmp_powerdown(qmp_sock)`.
  2. Shutdown phase: keep draining output up to `SHUTDOWN_TIMEOUT`; success =
     `proc.poll() is not None` (with `-no-reboot`, guest poweroff exits qemu).
     Set `shutdown_ok = True`.
- Verdicts: PASS requires `ok and shutdown_ok`. New failure text when boot
  succeeded but shutdown timed out:
  `"RESULT: FAIL — guest ignored ACPI power button within %ds (acpid missing or not running?)"`.
- Env escape hatch `SMOKE_ACPI=0` skips the powerdown phase (behaves as before) —
  documented in the README.

- [ ] **Step 10.2: Syntax check + commit**

```bash
uv run python -m py_compile tenwrt-image/qemu-smoke-boot.py
git add tenwrt-image/qemu-smoke-boot.py
git commit -m "tenwrt-image: smoke-boot asserts ACPI graceful shutdown via QMP (the virsh shutdown path)"
```

---

### Task 11: tenwrt full build + verify + smoke (LONG — background + progress)

Depends on: Tasks 0, 7, 8, 9, 10.

- [ ] **Step 11.1: Build**

```bash
cd $ROOT
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  sh tenwrt-image/build-tenwrt-image.sh 2>&1 | tee tmp/build-tenwrt.log
```

Run in background. First armsr build in the fresh tree compiles the toolchain —
expect **hours**. Report progress every ~60 s (grep the log tail for the current
package). Expected end: `images: /home/tim/local/gwifi/openwrt-armsr/bin/targets/armsr/armv8/`.

- [ ] **Step 11.2: Verify**

```bash
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  uv run python tenwrt-image/verify-tenwrt-image.py
```

Expected: all checks PASS, including the three `mt7915_*.bin` blobs, acpid,
qemu-ga, and the absence list. Fix and rebuild on failure.

- [ ] **Step 11.3: Smoke boot (x86 host → TCG, slow; give it time)**

```bash
uv run python tenwrt-image/qemu-smoke-boot.py 2>&1 | tee tmp/smoke-tenwrt.log
```

Expected: `RESULT: PASS` — marker seen AND clean ACPI poweroff. On x86 TCG the
boot can take minutes; `SMOKE_TIMEOUT`/`SMOKE_SHUTDOWN_TIMEOUT` env raise limits
if needed.

- [ ] **Step 11.4: Commit build-log-derived fixes (if any) + record results**

Append actual results (image name, verify PASS, smoke PASS) to
`tenwrt-image/README.md`'s results section in Task 14. Commit any fixes made:
`git commit -m "tenwrt-image: <specific fix> (found by build/verify/smoke)"`.

---

### Task 12: om2p full build + verifier (fit gate) (LONG — background + progress)

Depends on: Tasks 0, 5, 6.

- [ ] **Step 12.1: Build in the dedicated tree**

```bash
cd $ROOT
OWRT=/home/tim/local/gwifi/openwrt-armsr \
  FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  sh om2p-image/build-om2p-image.sh 2>&1 | tee tmp/build-om2p.log
```

Background + progress. First ath79 build compiles that toolchain too (hours).

- [ ] **Step 12.2: Run the om2p verifier (7168k fit gate)**

```bash
OWRT=/home/tim/local/gwifi/openwrt-armsr \
  FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  uv run python om2p-image/verify-om2p-image.py
```

Expected: PASS incl. the fit gate — proves the base.config layering did not grow
the image. If the fit gate fails, diff the manifest against a pre-refactor
`.config` expectation (Step 5.4 guaranteed identical config, so a failure here
means the tree/feeds differ — investigate, do not paper over).

- [ ] **Step 12.3: Commit any fixes**

---

### Task 13: wisp-side — build-templates.py (edit only; DO NOT run)

**Files:**
- Modify: `openwisp/build-templates.py`

Running this script SSHes to ten64 (reads hostapd passphrases) and mutates wisp —
both out of bounds for this branch. Edit + syntax-check only; running it is a
deploy-runbook step (after the VM's first registration).

- [ ] **Step 13.1: Hook trunk fallback**

In `POST_RELOAD_HOOK`, change:

```
TRUNK=eth-black
[ -e /sys/class/net/eth-black ] || TRUNK=lan
```

to:

```
TRUNK=eth-black
[ -e /sys/class/net/eth-black ] || TRUNK=lan
# tenwrt VM: no physical jacks; the virtio trunk is eth0. Pucks always match
# one of the two names above (gale's own eth0 is the DSA conduit — order
# matters), so only the VM falls through to here.
[ -e "/sys/class/net/$TRUNK" ] || TRUNK=eth0
```

- [ ] **Step 13.2: Attach set**

⚠️ There are TWO `PUCKS` bindings in this file: the module-level list (~line 44)
and `PUCKS = {pucks!r}` INSIDE the `DJANGO` heredoc template (~line 248) that is
executed remotely on wisp. The attach loop (`for name in PUCKS:`) and its
summary print live inside that template string — `py_compile` cannot see them.
Add the new line **inside the DJANGO template, immediately after
`PUCKS = {pucks!r}`**:

```python
# Devices the templates attach to: the pucks + the ten64 VM. The attach loop
# skips names that have not registered yet — re-run this script after the
# tenwrt VM's first successful registration (design spec §4.6).
DEVICES = PUCKS + ["tenwrt"]
```

Then, in the same template, change the attach loop `for name in PUCKS:` →
`for name in DEVICES:` and the summary print to use `len(DEVICES)`. Update the
module docstring (one paragraph: tenwrt attaches to the same gwifi-aps +
gwifi-base; hook trunk fallback).

- [ ] **Step 13.3: Syntax check + commit**

```bash
uv run python -m py_compile openwisp/build-templates.py
git add openwisp/build-templates.py
git commit -m "openwisp: gwifi-base hook eth0 trunk fallback + attach templates to the tenwrt VM (deploy: re-run after first registration)"
```

---

### Task 14: Staged host-side qemu-ga channel (local file only — NOT deployed)

**Files (outside the repo, local dir `/home/tim/local/gwifi/ten64-host/`):**
- Modify: `ten64-host/tenwrt.xml`
- Modify: `ten64-host/README.md`

- [ ] **Step 14.1: Add the virtio-serial channel to the domain XML**

Inside `<devices>` (before `</devices>`), add:

```xml
    <!-- qemu-ga channel — STAGED with the acpid+qemu-ga image (gwifi-openwrt
         branch tenwrt-vm-parity); takes effect on the next manual
         `virsh define tenwrt.xml`. libvirt auto-fills the source path. -->
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
```

- [ ] **Step 14.2: Note it in ten64-host/README.md**

Add to the "Already staged" list: qemu-ga channel staged in `tenwrt.xml`, pending
`virsh define`; graceful shutdown works WITHOUT it (`virsh shutdown` → ACPI →
acpid), qemu-ga adds `virsh shutdown --mode=agent`, guest-info and fsfreeze.

- [ ] **Step 14.3: No commit (dir is outside the repo)** — report the diff to the
  user in the task summary instead.

---

### Task 15: Docs, cleanup, final sweep

**Files:**
- Create: `fleet-image/README.md`
- Modify: `tenwrt-image/README.md`, `gale-image/README.md`, `om2p-image/README.md`,
  `docs/fleet-image-base-design.md` (status), `.gitignore` (already done in T1)

- [ ] **Step 15.1: `fleet-image/README.md`** — layout, the wrapper contract
  (variables each wrapper sets), opt-in steps, how the gates work, how to add a new
  image. Keep it short (~60 lines); link the design spec.

- [ ] **Step 15.2: `tenwrt-image/README.md` rewrite** — simple-profile architecture,
  dedicated `openwrt-armsr` tree (with setup steps from Task 0), build/verify/smoke
  commands, recorded results from Task 11, and the DEPLOY RUNBOOK:
  1. copy the built `combined-efi.img` to ten64 (`/var/lib/libvirt/images/tenwrt.img`) — manual;
  2. `virsh define ten64-host/tenwrt.xml` (picks up the staged qemu-ga channel) — manual;
  3. VFIO bind + `virsh start` per `ten64-host/README.md` — manual;
  4. watch first boot: DHCP on VLAN 4 → openwisp registration as `tenwrt`;
  5. re-run `openwisp/build-templates.py` to attach `gwifi-aps` + `gwifi-base`;
  6. `virsh shutdown tenwrt` must gracefully power off (acpid).
  Note the mesh-era design remains in git history; mesh returns via OpenWISP.

- [ ] **Step 15.3: gale/om2p README tweaks** — secrets file moved to
  `/home/tim/local/gwifi/fleet-secrets.conf` (FLEET_SECRETS env), base.config
  layering note, RENDER_ONLY gate mention. Update the design spec status line:
  `> Status: implemented on branch tenwrt-vm-parity (YYYY-MM-DD)`.

- [ ] **Step 15.4: Cleanup + full final sweep**

```bash
cd $ROOT
rm -rf tmp/gate tmp/build-*.log tmp/smoke-*.log        # rendered secrets die here
sh tests/fleet-image/test-build-lib.sh                  # ALL PASS
sh tests/fleet-image/test-gale-bootstrap-equivalence.sh # ALL PASS
sh tests/fleet-image/test-tenwrt-bootstrap-ops.sh       # ALL PASS
sh tests/tenwrt/test-radio-setup.sh                     # ALL PASS
sh tests/backhaul-gating/test-decide.sh                 # ALL PASS (untouched)
( cd tools/gwifi-netboot && uv run pytest -q )          # 54 passed (untouched)
git status --short                                      # clean (no stray files)
```

- [ ] **Step 15.5: Final commit**

```bash
git add fleet-image/README.md tenwrt-image/README.md gale-image/README.md \
  om2p-image/README.md docs/fleet-image-base-design.md
git commit -m "docs: fleet-image base READMEs + tenwrt deploy runbook; spec marked implemented"
```

Then use superpowers:finishing-a-development-branch (merge/PR decision is Tim's).

---

## Deferred / explicitly NOT in this plan

- Running `openwisp/build-templates.py` against wisp (deploy step; also SSHes ten64).
- Anything on ten64 (image copy, virsh define/start, VFIO bind) — Tim's manual gate.
- Rebuilding/publishing the gale image from the refactored base — Tim's call; the
  render+config gates prove it would be identical.
- om2p simple-profile conversion + `fleet-files/` retirement (design §5).
- 802.11ax uplift of gwifi-aps; VM LLDP visibility (design §5).
