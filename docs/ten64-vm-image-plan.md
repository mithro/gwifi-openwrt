# ten64 Wi-Fi VM — aarch64 OpenWrt VM image — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an OpenWISP-managed aarch64 OpenWrt VM image (`armsr/armv8`,
`combined-efi.img`) that boots under QEMU/KVM and will own ten64's two PCIe radios once
they are passed through — a sibling of `gale-image`/`om2p-image`.

**Architecture:** New `tenwrt-image/` directory mirroring `gale-image/`: a package
fragment (`tenwrt.config`), per-image overlay configs, a first-boot bootstrap adapted to a
virtio trunk NIC (`eth0`), the DRY shared `fleet-files/` overlay (backhaul-gate + hook), a
build script, a Python rootfs verifier, and a headless QEMU smoke-boot. Radios are
identified at first boot **by driver** (ath11k_pci → 5 GHz mesh anchor; ath10k_pci → 2.4
GHz), a no-op when no radio is attached so the image boots & provisions before passthrough.

**Tech Stack:** OpenWrt 25.12.4 build tree at `/home/tim/local/gwifi/openwrt`; POSIX sh
(busybox ash) for overlay scripts; Python 3 (run via `uv`) for the verifier and smoke-boot;
`qemu-system-aarch64` + edk2/AAVMF for the boot test.

**Spec:** `docs/ten64-vm-image-design.md`. **Branch:** `openwisp-controller` (already a
feature branch — do NOT touch main). All commits end with the trailer
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

**Conventions (hard rules):** never `2>/dev/null`; never create files in `/tmp` (use a
project-local `./tmp` and clean up); use `uv` for all Python; small discrete commits per
task; never American date formats; never print/commit secret *values*.

---

## Confirmed environment facts (do not re-derive)

- Target exists: `CONFIG_TARGET_armsr=y` + `CONFIG_TARGET_armsr_armv8=y`; device `generic`
  (EFI). `FILESYSTEMS := ext4 squashfs`. Image recipes include `combined-efi.img(.gz)` and
  `rootfs.img(.gz)`. `CONFIG_TARGET_IMAGES_GZIP` defaults **y** (so disable it for a raw
  bootable `.img`).
- Kernel has `CONFIG_VIRTIO_BLK/NET/CONSOLE/PCI=y` (all built-in) — virtio disk, `eth0`,
  and serial work with no extra packages.
- Packages all present in the tree: `kmod-ath11k-pci`, `ath11k-firmware-qcn9074`,
  `kmod-ath10k`, `ath10k-firmware-qca9377`, `openwisp-config`, `openwisp-monitoring`,
  `wpad-mesh-mbedtls`, `usteer`, `batctl-default`, `kmod-batman-adv`, `luci`, `ip-full`,
  `tcpdump-mini`, `ethtool`.
- Secrets file: `/home/tim/local/gwifi/fleet-secrets.conf` (0600, outside git). Required
  keys: `OPENWISP_SHARED_SECRET`, `MESH_SAE_KEY`, `MESH_ID`, `OPENWISP_URL`. It is NOT in
  the worktree, so build & verify must receive `FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf`.
- Build output dir: `/home/tim/local/gwifi/openwrt/bin/targets/armsr/armv8/`.
- Reference files to mirror (read them; do not re-invent): `gale-image/build-gale-image.sh`,
  `gale-image/files/etc/config/{openwisp,usteer,wireless}`,
  `gale-image/files/etc/uci-defaults/99-gale-bootstrap`, `om2p-image/verify-om2p-image.py`.
- DRY: `fleet-files/` holds ONLY `usr/sbin/gwifi-backhaul-gate` and
  `etc/hotplug.d/net/30-gwifi-backhaul`. `etc/config/openwisp` is per-image.

---

## File Structure (decomposition — locked here)

```
tenwrt-image/
  tenwrt.config                          # T1  target/rootfs + packages + radio stacks
  files/
    etc/config/openwisp                 # T2  controller stanza (placeholders)
    etc/config/usteer                   # T2  copy of gale's
    etc/config/wireless                 # T2  minimal mesh0 template (no fixed radio paths)
    usr/sbin/gwifi-radio-setup          # T3  driver-based radio role assignment (+unit test)
    etc/uci-defaults/99-tenwrt-bootstrap # T4  eth0 trunk + bat0 + bridges + cron + radio-setup
  build-tenwrt-image.sh                  # T5  render overlay + seed .config + make
  verify-tenwrt-image.py                 # T6  rootfs.tar.gz asserts (mirror om2p verify)
  qemu-smoke-boot.py                    # T7  headless boot of combined-efi.img
  README.md                             # T8  build + verify + smoke-boot instructions
tests/tenwrt/
  test-radio-setup.sh                   # T3  unit tests for phy_for_driver (fake sysfs)
docs/
  ten64-vm-image-design.md              # (done) spec
  ten64-vm-image-plan.md                # (this file)
```

---

## Task 1: Package/target fragment `tenwrt-image/tenwrt.config`

**Files:** Create `tenwrt-image/tenwrt.config`

- [ ] **Step 1: Write the fragment** (exact content):

```
# tenwrt.config — package + rootfs fragment for the ten64 Wi-Fi VM image.
# The armsr/armv8 TARGET lines are prepended by build-tenwrt-image.sh (mirroring gale).
CONFIG_TARGET_ROOTFS_EXT4FS=y
CONFIG_TARGET_ROOTFS_PARTSIZE=256
CONFIG_TARGET_ROOTFS_TARGZ=y
# Raw (un-gzipped) disk image so qemu can boot it directly.
# CONFIG_TARGET_IMAGES_GZIP is not set
# --- managed feature set (mirrors gale.config) ---
CONFIG_PACKAGE_openwisp-config=y
CONFIG_PACKAGE_openwisp-monitoring=y
CONFIG_PACKAGE_kmod-batman-adv=y
CONFIG_PACKAGE_batctl-default=y
# CONFIG_PACKAGE_wpad-basic-mbedtls is not set
CONFIG_PACKAGE_wpad-mesh-mbedtls=y
CONFIG_PACKAGE_usteer=y
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_ip-full=y
CONFIG_PACKAGE_tcpdump-mini=y
CONFIG_PACKAGE_ethtool=y
# --- radios passed through from the host (VFIO): drivers + firmware ---
CONFIG_PACKAGE_kmod-ath11k-pci=y
CONFIG_PACKAGE_ath11k-firmware-qcn9074=y
CONFIG_PACKAGE_kmod-ath10k=y
CONFIG_PACKAGE_ath10k-firmware-qca9377=y
```

- [ ] **Step 2: Commit**

```bash
git add tenwrt-image/tenwrt.config
git commit -m "feat(tenwrt): package/target fragment for armsr/armv8 VM image"
```

---

## Task 2: Per-image overlay configs

**Files:** Create `tenwrt-image/files/etc/config/{openwisp,usteer,wireless}`

- [ ] **Step 1: openwisp** — copy `gale-image/files/etc/config/openwisp` **verbatim**
  (it already has `management_interface 'br-mgmt'` and the `__OPENWISP_*__` placeholders).

- [ ] **Step 2: usteer** — copy `gale-image/files/etc/config/usteer` **verbatim**.

- [ ] **Step 3: wireless** — minimal mesh template (NO fixed `wifi-device`/path; those are
  generated at first boot by `gwifi-radio-setup`). Exact content:

```
# Minimal wireless seed for the ten64 Wi-Fi VM. wifi-device radioN stanzas and the
# mesh0 'device' binding are generated at first boot by /usr/sbin/gwifi-radio-setup
# (radios arrive via VFIO at guest-assigned PCI slots). Client APs come from OpenWISP.
config wifi-iface 'mesh0'
	option mode 'mesh'
	option mesh_id '__MESH_ID__'
	option encryption 'sae'
	option key '__MESH_SAE_KEY__'
	option network 'mesh_hardif'
	option mesh_fwding '0'
	option mesh_rssi_threshold '0'
	option disabled '0'
```

- [ ] **Step 4: Commit**

```bash
git add tenwrt-image/files/etc/config
git commit -m "feat(tenwrt): per-image openwisp/usteer/wireless overlay configs"
```

---

## Task 3: `gwifi-radio-setup` — driver-based radio roles (TDD)

**Files:** Create `tenwrt-image/files/usr/sbin/gwifi-radio-setup`,
`tests/tenwrt/test-radio-setup.sh`

The only non-declarative logic in this image is "which detected phy is the WiFi-6 radio
that should anchor the mesh." Isolate it as the pure, unit-tested function `phy_for_driver`
(+ helper `bdf_of_phy`). The uci/`wifi` wiring around it is runtime/hardware and is a
**no-op without phys** (so the image-first smoke-boot passes); its live validation is
deferred to passthrough bring-up (design OQ1).

- [ ] **Step 1: Write the failing test** `tests/tenwrt/test-radio-setup.sh`:

```sh
#!/bin/sh
# Unit tests for gwifi-radio-setup pure functions against a fake sysfs tree.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
GWIFI_RADIO_SOURCED=1 . "$HERE/../../tenwrt-image/files/usr/sbin/gwifi-radio-setup"

fails=0
eq() { if [ "$2" = "$3" ]; then printf '  PASS %s\n' "$1";
       else printf '  FAIL %s (want [%s] got [%s])\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

# Build a fake /sys/class/ieee80211. Real sysfs models phyN/device as a SYMLINK to the
# PCI <BDF> dir, and <BDF>/driver as a symlink to the bus driver — mirror that exactly.
SB=$(mktemp -d ./tmp/radio-test.XXXXXX)
mkdir -p "$SB/phy0" "$SB/phy1" \
         "$SB/bus/ath11k_pci" "$SB/bus/ath10k_pci" \
         "$SB/devices/0000:00:03.0" "$SB/devices/0000:00:02.0"
# phy0 -> ath10k_pci at BDF 0000:00:03.0 ; phy1 -> ath11k_pci at BDF 0000:00:02.0
ln -s ../devices/0000:00:03.0 "$SB/phy0/device"
ln -s ../devices/0000:00:02.0 "$SB/phy1/device"
ln -s ../../bus/ath10k_pci "$SB/devices/0000:00:03.0/driver"
ln -s ../../bus/ath11k_pci "$SB/devices/0000:00:02.0/driver"
GWIFI_RADIO_SYSFS="$SB"

eq "ath11k phy"        "phy1" "$(phy_for_driver ath11k_pci)"
eq "ath10k phy"        "phy0" "$(phy_for_driver ath10k_pci)"
eq "missing driver"    ""     "$(phy_for_driver rtw88_pci)"
eq "bdf of mesh phy"   "0000:00:02.0" "$(bdf_of_phy phy1)"

# No-sysfs case: empty result, exit 0 (image-first no-op).
GWIFI_RADIO_SYSFS="$SB/nonexistent"
eq "no sysfs -> empty" "" "$(phy_for_driver ath11k_pci)"

rm -rf "$SB"
[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
```

- [ ] **Step 2: Run it to confirm it fails** (script doesn't exist yet):

```bash
mkdir -p ./tmp tests/tenwrt
sh tests/tenwrt/test-radio-setup.sh
```
Expected: error sourcing the missing script (FAIL).

- [ ] **Step 3: Write `tenwrt-image/files/usr/sbin/gwifi-radio-setup`:**

```sh
#!/bin/sh
# gwifi-radio-setup — assign mesh + band roles to the host's passed-through radios by
# DRIVER (path-independent: a VM gets guest-assigned PCI slots). The WiFi-6 ath11k radio
# anchors the 802.11s mesh + 5 GHz; the ath10k radio serves 2.4 GHz. Client APs come from
# OpenWISP. No-op when no radio/phy is present (image-first / pre-passthrough).
# Sourceable for tests via GWIFI_RADIO_SOURCED=1. See docs/ten64-vm-image-design.md §7.3.
set -u
LOG_TAG=gwifi-radio-setup

# ---- pure helpers (unit-tested) -------------------------------------------
# Each helper reads GWIFI_RADIO_SYSFS *live* (not a top-level snapshot) so tests can point
# it at a fake sysfs tree after sourcing.
# phy_for_driver DRIVER -> first phy whose device/driver basename == DRIVER ("" if none).
phy_for_driver() {
	_drv=$1; _sysfs=${GWIFI_RADIO_SYSFS:-/sys/class/ieee80211}
	[ -d "$_sysfs" ] || return 0
	for _p in "$_sysfs"/phy*; do
		[ -e "$_p/device/driver" ] || continue
		_l=$(readlink "$_p/device/driver") || continue
		case "${_l##*/}" in "$_drv") echo "${_p##*/}"; return 0 ;; esac
	done
}
# bdf_of_phy PHY -> the PCI BDF (basename of the resolved device dir), e.g. 0000:00:02.0.
bdf_of_phy() {
	_sysfs=${GWIFI_RADIO_SYSFS:-/sys/class/ieee80211}
	_t=$(readlink -f "$_sysfs/$1/device") || return 0
	echo "${_t##*/}"
}

# ---- runtime wiring (hardware; no-op without phys; bench-validated, OQ1) ---
# radio_with_bdf BDF -> the uci wifi-device section whose 'path' contains BDF ("" if none).
radio_with_bdf() {
	_bdf=$1
	for _s in $(uci show wireless | sed -n 's/^wireless\.\([^.]*\)=wifi-device/\1/p'); do
		case "$(uci -q get "wireless.$_s.path")" in
			*"$_bdf"*) echo "$_s"; return 0 ;;
		esac
	done
}

main() {
	_mesh_phy=$(phy_for_driver ath11k_pci)
	_ap24_phy=$(phy_for_driver ath10k_pci)
	if [ -z "$_mesh_phy$_ap24_phy" ]; then
		logger -t "$LOG_TAG" "no Wi-Fi phys present; skipping radio setup"
		return 0
	fi
	wifi config                                   # let OpenWrt derive correct radioN+path
	if [ -n "$_mesh_phy" ]; then
		_r=$(radio_with_bdf "$(bdf_of_phy "$_mesh_phy")")
		if [ -n "$_r" ]; then
			uci set "wireless.$_r.band=5g"
			uci set "wireless.$_r.channel=auto"
			uci set "wireless.$_r.disabled=0"
			uci set wireless.mesh0.device="$_r"   # bind the mesh to the WiFi-6 radio
			logger -t "$LOG_TAG" "mesh + 5GHz -> $_r ($_mesh_phy)"
		fi
	fi
	if [ -n "$_ap24_phy" ]; then
		_r=$(radio_with_bdf "$(bdf_of_phy "$_ap24_phy")")
		if [ -n "$_r" ]; then
			uci set "wireless.$_r.band=2g"
			uci set "wireless.$_r.channel=auto"
			uci set "wireless.$_r.disabled=0"
			logger -t "$LOG_TAG" "2.4GHz -> $_r ($_ap24_phy)"
		fi
	fi
	uci commit wireless
	wifi reload
}

case "${GWIFI_RADIO_SOURCED:-}" in
	1) : ;;            # sourced (tests) — do not run
	*) main "$@" ;;
esac
```

- [ ] **Step 4: Run the test to verify it passes:**

```bash
sh tests/tenwrt/test-radio-setup.sh
```
Expected: `ALL PASS`. (Also run with gawk/dash if available; it is plain POSIX sh.)

- [ ] **Step 5: Commit**

```bash
git add tenwrt-image/files/usr/sbin/gwifi-radio-setup tests/tenwrt/test-radio-setup.sh
git commit -m "feat(tenwrt): driver-based radio role assignment + unit test"
```

---

## Task 4: First-boot bootstrap `99-tenwrt-bootstrap`

**Files:** Create `tenwrt-image/files/etc/uci-defaults/99-tenwrt-bootstrap`

Mirror `gale-image/files/etc/uci-defaults/99-gale-bootstrap` exactly, with three changes:
(a) trunk port `eth0` instead of `wan`; (b) call `/usr/sbin/gwifi-radio-setup` after the
network is committed; (c) a final completion echo the smoke-boot can observe.

- [ ] **Step 1: Write the script** (exact content):

```sh
#!/bin/sh
# 99-tenwrt-bootstrap — first-boot network/mesh setup for the ten64 Wi-Fi VM.
# Idempotent: fixed UCI section names so re-runs overwrite, not duplicate.
# VLAN map: NAME=VID. mgmt(5) gets DHCP; the rest are L2-only (APs attach later).
# Uplink is a single virtio TRUNK NIC (eth0) carrying all VLANs (cf. gale's DSA 'wan').
VLANS="mgmt=5 int=10 roam=20 iot=90 guest=99"
UPLINK=eth0

# --- batman-adv core (bat0) + the 802.11s hardif join ---
uci -q batch <<'EOF'
set network.bat0=interface
set network.bat0.proto='batadv'
set network.bat0.routing_algo='BATMAN_IV'
set network.bat0.bridge_loop_avoidance='1'
set network.bat0.distributed_arp_table='1'
set network.bat0.gw_mode='client'
set network.mesh_hardif=interface
set network.mesh_hardif.proto='batadv_hardif'
set network.mesh_hardif.master='bat0'
set network.mesh_hardif.mtu='1536'
EOF

for kv in $VLANS; do
	name=${kv%=*}; vid=${kv#*=}
	uci set network.up_$vid="device"
	uci set network.up_$vid.type='8021q'
	uci set network.up_$vid.ifname="$UPLINK"
	uci set network.up_$vid.vid="$vid"
	uci set network.up_$vid.name="$UPLINK.$vid"
	uci set network.bat_$vid="device"
	uci set network.bat_$vid.type='8021q'
	uci set network.bat_$vid.ifname='bat0'
	uci set network.bat_$vid.vid="$vid"
	uci set network.bat_$vid.name="bat0.$vid"
	uci set network.br_$name="device"
	uci set network.br_$name.type='bridge'
	uci set network.br_$name.name="br-$name"
	uci -q delete network.br_$name.ports
	uci add_list network.br_$name.ports="$UPLINK.$vid"
	uci add_list network.br_$name.ports="bat0.$vid"
	uci set network.$name="interface"
	uci set network.$name.device="br-$name"
	if [ "$name" = "mgmt" ]; then
		uci set network.$name.proto='dhcp'
	else
		uci set network.$name.proto='none'
	fi
done
uci commit network

# --- backhaul-gating: 1-min cron re-assert + ensure crond runs (idempotent) ---
CRON=/etc/crontabs/root
LINE='* * * * * /usr/sbin/gwifi-backhaul-gate --once'
mkdir -p /etc/crontabs
{ [ -f "$CRON" ] && grep -qF "$LINE" "$CRON"; } || echo "$LINE" >> "$CRON"
/etc/init.d/cron enable || true
/etc/init.d/cron restart || true

# --- radios: assign mesh/band roles by driver (no-op until passthrough exists) ---
[ -x /usr/sbin/gwifi-radio-setup ] && /usr/sbin/gwifi-radio-setup || true

# Completion marker (visible on the boot serial console; observed by qemu-smoke-boot.py).
echo "TENVM-BOOTSTRAP-COMPLETE uplink=$UPLINK"
exit 0
```

Note: the uci device sections are named `up_<vid>` (not gale's `wan_<vid>`) since the port
is `eth0`; the backhaul-gate auto-discovers the uplink member from `br-mgmt`'s brif list,
so no gate change is needed.

- [ ] **Step 2: Commit**

```bash
git add tenwrt-image/files/etc/uci-defaults/99-tenwrt-bootstrap
git commit -m "feat(tenwrt): first-boot bootstrap (eth0 trunk + bat0 + cron + radio-setup)"
```

---

## Task 5: Build script `build-tenwrt-image.sh`

**Files:** Create `tenwrt-image/build-tenwrt-image.sh`

Mirror `gale-image/build-gale-image.sh`; differences: armsr/armv8 target lines, chmod the
extra `gwifi-radio-setup`, output path.

- [ ] **Step 1: Write the script** (exact content):

```sh
#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
[ -f "$FLEET_SECRETS" ] || { echo "missing $FLEET_SECRETS (set FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf)"; exit 1; }
# shellcheck disable=SC1090
. "$FLEET_SECRETS"
: "${OPENWISP_SHARED_SECRET:?}"; : "${MESH_SAE_KEY:?}"; : "${MESH_ID:?}"; : "${OPENWISP_URL:?}"

# 1) render overlay into the build tree (gitignored there)
rm -rf "$OWRT/files"
cp -a "$HERE/files" "$OWRT/files"
# merge the shared fleet overlay (canonical source for cross-image files: gate + hook)
cp -a "$HERE/../fleet-files/." "$OWRT/files/"
# Escape sed replacement metacharacters so secrets substitute literally.
esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/&/\\&/g' -e 's/|/\\|/g'; }
ss=$(esc "$OPENWISP_SHARED_SECRET"); mk=$(esc "$MESH_SAE_KEY")
mi=$(esc "$MESH_ID"); ou=$(esc "$OPENWISP_URL")
find "$OWRT/files" -type f -exec sed -i \
	-e "s|__OPENWISP_SHARED_SECRET__|$ss|g" \
	-e "s|__MESH_SAE_KEY__|$mk|g" \
	-e "s|__MESH_ID__|$mi|g" \
	-e "s|__OPENWISP_URL__|$ou|g" {} +
chmod 0755 "$OWRT/files/etc/uci-defaults/99-tenwrt-bootstrap" \
           "$OWRT/files/usr/sbin/gwifi-radio-setup" \
           "$OWRT/files/usr/sbin/gwifi-backhaul-gate" \
           "$OWRT/files/etc/hotplug.d/net/30-gwifi-backhaul"

[ "${RENDER_ONLY:-0}" = "1" ] && { echo "rendered overlay to $OWRT/files (RENDER_ONLY)"; exit 0; }

# 2) seed config: armsr/armv8 target + our fragment
{ printf 'CONFIG_TARGET_armsr=y\nCONFIG_TARGET_armsr_armv8=y\nCONFIG_TARGET_armsr_armv8_DEVICE_generic=y\n';
	cat "$HERE/tenwrt.config"; } > "$OWRT/.config"
( cd "$OWRT" && make defconfig )

# 3) build
( cd "$OWRT" && make -j"${JOBS:-6}" )
echo "images: $OWRT/bin/targets/armsr/armv8/"
```

- [ ] **Step 2: Verify the render path works (fast, no build):**

```bash
RENDER_ONLY=1 FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  ./tenwrt-image/build-tenwrt-image.sh
# confirm overlay rendered + no leftover placeholders + radio-setup executable
test -x /home/tim/local/gwifi/openwrt/files/usr/sbin/gwifi-radio-setup && echo "radio-setup +x OK"
grep -RIl '__[A-Z_]*__' /home/tim/local/gwifi/openwrt/files && echo "PLACEHOLDERS LEFT (bad)" || echo "no placeholders OK"
```
Expected: `radio-setup +x OK` and `no placeholders OK`.

- [ ] **Step 3: Commit**

```bash
chmod +x tenwrt-image/build-tenwrt-image.sh
git add tenwrt-image/build-tenwrt-image.sh
git commit -m "feat(tenwrt): build script (armsr/armv8 target + DRY fleet overlay merge)"
```

---

## Task 6: Verifier `verify-tenwrt-image.py`

**Files:** Create `tenwrt-image/verify-tenwrt-image.py`

Start from `om2p-image/verify-om2p-image.py` (it reads `fleet-secrets.conf` and extracts
from `*rootfs.tar.gz`). Changes: image dir `armsr/armv8`; drop the OM2P per-profile
fit-size gate; add a `combined-efi.img` existence check; add the ath11k/ath10k packages and
the radio-setup helper to the asserted set; assert mesh creds in `/etc/config/wireless`
(tenwrt bakes a wireless seed) rather than in the bootstrap.

- [ ] **Step 1: Write the verifier** (exact content):

```python
#!/usr/bin/env python3
"""verify-tenwrt-image.py — validate the built ten64 Wi-Fi VM image.

Checks, against the rootfs (the *-rootfs.tar.gz emitted by CONFIG_TARGET_ROOTFS_TARGZ,
or the build staging root-* dir as fallback):
  - /etc/config/openwisp   : real URL + shared_secret, no placeholders
  - /etc/config/wireless   : mesh mode + real MESH_ID + SAE key, no placeholders
  - /etc/uci-defaults/99-tenwrt-bootstrap : executable; eth0 trunk; cron line; no placeholders
  - /usr/sbin/gwifi-radio-setup, gwifi-backhaul-gate, hotplug hook : present + executable
  - package manifest       : required packages incl. ath11k/ath10k driver+firmware
  - a bootable combined-efi.img artifact exists

Reads expected values from <repo-root>/fleet-secrets.conf (or $FLEET_SECRETS). Never
prints secrets. Usage: uv run python tenwrt-image/verify-tenwrt-image.py
"""
import glob
import os
import re
import stat
import sys
import tarfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/armsr/armv8")
FLEET_SECRETS = os.environ.get(
    "FLEET_SECRETS", os.path.join(SCRIPT_DIR, "..", "fleet-secrets.conf"))

REQUIRED_PACKAGES = [
    "openwisp-config", "openwisp-monitoring", "kmod-batman-adv",
    "wpad-mesh-mbedtls", "usteer", "batctl-default",
    "kmod-ath11k-pci", "ath11k-firmware-qcn9074",
    "kmod-ath10k", "ath10k-firmware-qca9377",
]
OVERLAY_EXEC = [
    "etc/uci-defaults/99-tenwrt-bootstrap",
    "usr/sbin/gwifi-radio-setup",
    "usr/sbin/gwifi-backhaul-gate",
    "etc/hotplug.d/net/30-gwifi-backhaul",
]


def parse_secrets(path):
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


def read_rootfs(image_dir):
    """Return ({relpath: text}, {relpath: mode}, label) from the rootfs tarball
    (preferred) or the build staging root-* dir (fallback)."""
    want = tuple(["etc/config/openwisp", "etc/config/wireless",
                  "etc/uci-defaults/99-tenwrt-bootstrap"] + OVERLAY_EXEC[1:])
    tarballs = glob.glob(os.path.join(image_dir, "*rootfs.tar.gz"))
    if tarballs:
        files, modes = {}, {}
        with tarfile.open(tarballs[0], "r:gz") as tf:
            for m in tf.getmembers():
                rel = m.name.lstrip("./")
                if rel in want and m.isfile():
                    files[rel] = tf.extractfile(m).read().decode(errors="replace")
                    modes[rel] = m.mode
        return files, modes, "tarball %s" % os.path.basename(tarballs[0])
    roots = glob.glob(os.path.join(OWRT, "build_dir", "target-*", "root-*"))
    if roots:
        files, modes = {}, {}
        for rel in want:
            p = os.path.join(roots[0], rel)
            if os.path.isfile(p):
                files[rel] = open(p, errors="replace").read()
                modes[rel] = os.stat(p).st_mode
        return files, modes, "staging %s" % roots[0]
    return None, None, None


def find_manifest(image_dir):
    for name in sorted(os.listdir(image_dir)):
        if name.endswith(".manifest"):
            return open(os.path.join(image_dir, name)).read()
    return None


def main():
    if not os.path.isdir(IMAGE_DIR):
        sys.exit("ERROR: image dir not found: %s (build first)" % IMAGE_DIR)
    if not os.path.isfile(FLEET_SECRETS):
        sys.exit("ERROR: secrets not found: %s (set FLEET_SECRETS=...)" % FLEET_SECRETS)
    secrets = parse_secrets(FLEET_SECRETS)
    failures = []

    files, modes, src = read_rootfs(IMAGE_DIR)
    if not files:
        sys.exit("ERROR: no rootfs tarball or staging dir found; build with "
                 "CONFIG_TARGET_ROOTFS_TARGZ=y (in tenwrt.config)")
    print("Rootfs source: %s\n" % src)

    def check_value(content, key, label):
        v = secrets.get(key)
        if not v:
            failures.append("FAIL %s: %s missing/empty in fleet-secrets.conf" % (label, key))
        elif v not in content:
            failures.append("FAIL %s: %s value not present" % (label, key))
        else:
            print("  PASS %s: %s rendered" % (label, key))

    def check_no_ph(content, label):
        ph = re.findall(r'__[A-Z_]+__', content)
        if ph:
            failures.append("FAIL %s: placeholders %s" % (label, ph))
        else:
            print("  PASS %s: no placeholders" % label)

    ow = files.get("etc/config/openwisp")
    if ow is None:
        failures.append("FAIL openwisp: not in rootfs")
    else:
        check_value(ow, "OPENWISP_URL", "openwisp")
        check_value(ow, "OPENWISP_SHARED_SECRET", "openwisp")
        check_no_ph(ow, "openwisp")

    wl = files.get("etc/config/wireless")
    if wl is None:
        failures.append("FAIL wireless: not in rootfs")
    else:
        if "mode 'mesh'" in wl or "mode='mesh'" in wl:
            print("  PASS wireless: mesh mode present")
        else:
            failures.append("FAIL wireless: mesh mode not found")
        check_value(wl, "MESH_ID", "wireless")
        check_value(wl, "MESH_SAE_KEY", "wireless")
        check_no_ph(wl, "wireless")

    bs = files.get("etc/uci-defaults/99-tenwrt-bootstrap")
    if bs is None:
        failures.append("FAIL bootstrap: not in rootfs")
    else:
        if "UPLINK=eth0" in bs:
            print("  PASS bootstrap: eth0 trunk")
        else:
            failures.append("FAIL bootstrap: eth0 trunk uplink not found")
        if "gwifi-backhaul-gate --once" in bs:
            print("  PASS bootstrap: cron line installed")
        else:
            failures.append("FAIL bootstrap: cron-install snippet missing")
        check_no_ph(bs, "bootstrap")

    for rel in OVERLAY_EXEC:
        if rel not in files:
            failures.append("FAIL exec: %s missing from rootfs" % rel)
        elif modes.get(rel, 0) & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS exec: %s present and executable" % rel)
        else:
            failures.append("FAIL exec: %s present but not executable" % rel)

    manifest = find_manifest(IMAGE_DIR)
    if manifest is None:
        failures.append("FAIL manifest: none found")
    else:
        for pkg in REQUIRED_PACKAGES:
            if pkg in manifest:
                print("  PASS manifest: '%s'" % pkg)
            else:
                failures.append("FAIL manifest: '%s' missing" % pkg)

    imgs = glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img")) \
        + glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img.gz"))
    if imgs:
        print("  PASS image: %s" % os.path.basename(imgs[0]))
    else:
        failures.append("FAIL image: no *combined-efi.img(.gz) artifact")

    print()
    if failures:
        print("Failures:")
        for f in failures:
            print("  " + f)
        print("\nRESULT: FAIL")
        sys.exit(1)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add tenwrt-image/verify-tenwrt-image.py
git commit -m "feat(tenwrt): rootfs verifier (packages + overlay + combined-efi artifact)"
```

(The verifier is exercised against a real build in Task 9.)

---

## Task 7: Headless QEMU smoke-boot `qemu-smoke-boot.py`

**Files:** Create `tenwrt-image/qemu-smoke-boot.py`

Boot the raw `combined-efi.img` on `qemu-system-aarch64 -M virt`, capture the serial
console, and assert the kernel reaches userspace and `99-tenwrt-bootstrap` runs to
completion (the `TENVM-BOOTSTRAP-COMPLETE` marker). KVM is used automatically on an aarch64
host (ten64); otherwise TCG emulation. If qemu or UEFI firmware is absent, SKIP loudly
(exit 0) with install hints — do not hard-fail the pipeline on a missing optional tool.

- [ ] **Step 1: Write the script** (exact content):

```python
#!/usr/bin/env python3
"""qemu-smoke-boot.py — headless boot test for the ten64 Wi-Fi VM image.

Boots the built combined-efi.img under qemu-system-aarch64 (-M virt) and asserts the
image reaches first-boot: the kernel boots to userspace and 99-tenwrt-bootstrap prints its
completion marker on the serial console. No radio is required. KVM is used on aarch64
hosts; TCG otherwise. SKIPs (exit 0) if qemu or UEFI firmware is unavailable.

Usage: uv run python tenwrt-image/qemu-smoke-boot.py [path/to/combined-efi.img]
"""
import glob
import gzip
import os
import platform
import shutil
import subprocess
import sys
import time

OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/armsr/armv8")
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp")
MARKER = "TENVM-BOOTSTRAP-COMPLETE"
BOOT_FALLBACK = "procd: - init complete -"     # accept as a weaker "kernel booted" signal
TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "360"))

# Prefer unified firmware images (usable directly via -bios); the split AAVMF_CODE.fd is
# last because it really wants a paired varstore.
FIRMWARE_CANDIDATES = [
    "/usr/share/qemu-efi-aarch64/QEMU_EFI.fd",
    "/usr/share/edk2/aarch64/QEMU_EFI.fd",
    "/usr/share/AAVMF/QEMU_EFI.fd",
    "/usr/share/qemu/edk2-aarch64-code.fd",
    "/usr/share/AAVMF/AAVMF_CODE.fd",
]


def skip(msg):
    print("SKIP: %s" % msg)
    sys.exit(0)


def find_image(argv):
    if len(argv) > 1:
        return argv[1]
    raw = sorted(glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img")))
    if raw:
        return raw[0]
    gz = sorted(glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img.gz")))
    if gz:
        os.makedirs(TMP, exist_ok=True)
        out = os.path.join(TMP, os.path.basename(gz[0])[:-3])
        with gzip.open(gz[0], "rb") as fi, open(out, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        return out
    return None


def main():
    qemu = shutil.which("qemu-system-aarch64")
    if not qemu:
        skip("qemu-system-aarch64 not found (apt install qemu-system-arm), or run on ten64")
    fw = next((f for f in FIRMWARE_CANDIDATES if os.path.isfile(f)), None)
    if not fw:
        skip("no aarch64 UEFI firmware found (apt install qemu-efi-aarch64); tried %s"
             % ", ".join(FIRMWARE_CANDIDATES))
    img = find_image(sys.argv)
    if not img or not os.path.isfile(img):
        sys.exit("ERROR: no combined-efi.img found in %s (build first)" % IMAGE_DIR)

    os.makedirs(TMP, exist_ok=True)
    disk = os.path.join(TMP, "smoke-disk.img")
    shutil.copyfile(img, disk)           # writable copy (UEFI/grub may write vars/state)

    use_kvm = platform.machine() == "aarch64" and os.path.exists("/dev/kvm")
    cmd = [qemu, "-M", "virt", "-m", "512", "-no-reboot", "-nographic",
           "-bios", fw,
           "-drive", "file=%s,if=virtio,format=raw" % disk,
           "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0"]
    cmd += (["-cpu", "host", "-enable-kvm"] if use_kvm else ["-cpu", "cortex-a72"])
    print("Image:    %s" % img)
    print("Firmware: %s" % fw)
    print("Accel:    %s\n" % ("KVM" if use_kvm else "TCG (slow)"))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, bufsize=1)
    deadline = time.time() + TIMEOUT
    captured, ok, booted = [], False, False
    try:
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            captured.append(line)
            sys.stdout.write("  | " + line)
            if MARKER in line:
                ok = True
                break
            if BOOT_FALLBACK in line:
                booted = True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if os.path.isfile(disk):
            os.remove(disk)

    print()
    if ok:
        print("RESULT: PASS (saw %s)" % MARKER)
        sys.exit(0)
    if booted:
        print("RESULT: FAIL — kernel booted but %s not seen (bootstrap did not "
              "complete). Check 99-tenwrt-bootstrap." % MARKER)
        sys.exit(1)
    print("RESULT: FAIL — no boot output recognised within %ds. Likely a serial-console "
          "mismatch; try adding 'console=ttyAMA0,115200' to the image grub cmdline, or "
          "run on ten64 under KVM." % TIMEOUT)
    sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add tenwrt-image/qemu-smoke-boot.py
git commit -m "feat(tenwrt): headless QEMU smoke-boot (asserts first-boot completion)"
```

(Exercised against a real build in Task 9.)

---

## Task 8: README

**Files:** Create `tenwrt-image/README.md`

- [ ] **Step 1: Write a README** mirroring `gale-image/README.md`: purpose (aarch64 VM for
  ten64's radios, sibling of gale), prerequisites (OpenWrt tree + feeds; `qemu-system-arm`
  + `qemu-efi-aarch64` for the smoke-boot), the three commands with `FLEET_SECRETS=` set,
  the output path (`bin/targets/armsr/armv8/`), the "built images contain baked secrets —
  do NOT publish" warning, and a note that radios/passthrough are a deferred follow-on.

- [ ] **Step 2: Commit**

```bash
git add tenwrt-image/README.md
git commit -m "docs(tenwrt): build + verify + smoke-boot README"
```

---

## Task 9: Build, verify, and smoke-boot (acceptance run)

**Files:** none new (this runs the pipeline end-to-end and fixes any integration issues).

- [ ] **Step 1: Full build** (slow; armsr/armv8 from a tree already used for other targets):

```bash
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf JOBS=6 \
  ./tenwrt-image/build-tenwrt-image.sh
```
Expected: ends with `images: .../bin/targets/armsr/armv8/`. If a package is missing, run
`cd /home/tim/local/gwifi/openwrt && ./scripts/feeds update -a && ./scripts/feeds install -a`
and retry. Confirm artifacts:

```bash
ls -l /home/tim/local/gwifi/openwrt/bin/targets/armsr/armv8/ | grep -E 'combined-efi|rootfs.tar.gz|manifest'
```

- [ ] **Step 2: Verify the rootfs:**

```bash
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf \
  uv run python tenwrt-image/verify-tenwrt-image.py
```
Expected: `RESULT: PASS`. Fix any FAIL (missing package → add to `tenwrt.config`; missing
overlay file → check the build merge) and re-run from Step 1.

- [ ] **Step 3: Smoke-boot:**

```bash
uv run python tenwrt-image/qemu-smoke-boot.py
```
Expected: `RESULT: PASS (saw TENVM-BOOTSTRAP-COMPLETE)`. If `SKIP` (no qemu/firmware on
this host): `sudo apt install qemu-system-arm qemu-efi-aarch64` and retry, or run the same
command on ten64 (KVM, fast). If it FAILs on a console mismatch, add
`console=ttyAMA0,115200` to the image's grub cmdline and rebuild (see the script's hint).

- [ ] **Step 4: Clean up** any working files and commit fixups:

```bash
rm -rf ./tmp
git add -A && git commit -m "test(tenwrt): build + verify + smoke-boot green (acceptance)" || echo "no fixups needed"
```

- [ ] **Step 5: Final whole-feature review** (subagent-driven-development: dispatch the
  final code reviewer over the whole `tenwrt-image/` addition), then use
  superpowers:finishing-a-development-branch.

---

## Notes for the executor

- **TDD applies** to Task 3 (`phy_for_driver`) only; the rest are declarative config /
  build glue validated by Task 9's verify + smoke-boot (same as how gale/om2p were proven).
- **Do not** hardcode radio PCI paths anywhere — the whole point of `gwifi-radio-setup` is
  path-independence (design §7.3, OQ1). Live radio behaviour is a deferred bench item.
- **Secrets:** only ever reference `FLEET_SECRETS`; never echo a secret value; never commit
  a rendered `$OWRT/files` tree or any built `.img`/`.tar.gz` (the build writes them under
  the OpenWrt tree, which is outside this repo).
- **Scope:** stop at a green build+verify+smoke-boot. VFIO passthrough, the libvirt domain,
  cutover, and the OpenWISP device template are separate follow-on deliverables.
```
