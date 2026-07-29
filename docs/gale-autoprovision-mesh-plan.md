# Gale auto-provisioning mesh-AP image — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a generic gale OpenWrt 25.12.4 image that auto-provisions from OpenWISP (pull mode) and fails its uplink over from a wired 802.1q trunk to an 802.11s + batman-adv mesh, carrying mgmt + all client VLANs.

**Architecture:** A versioned overlay (config fragment + `files/` tree + build script) in the `gwifi-openwrt` repo, built against the existing `openwrt/` v25.12.4 tree. Network/bridge/batman setup is created by a DRY `uci-defaults` bootstrap script; secrets are substituted from an untracked `gale-secrets.conf` at build time. The image is validated by extracting its squashfs rootfs and asserting overlay+package presence; final acceptance is a hardware bench test.

**Tech Stack:** OpenWrt 25.12.4 (ipq40xx/chromium), UCI/netifd, DSA, batman-adv (BLA), 802.11s/SAE (wpad-mesh), openwisp-config/-monitoring, usteer, POSIX shell.

**Spec:** `docs/gale-autoprovision-mesh-design.md`

**Conventions:** All paths relative to `/home/tim/local/gwifi`. Repo = `gwifi-openwrt` (branch `gale-autoprovision-mesh`). Build tree = `openwrt`. Overlay source-of-truth lives in the repo under `gale-image/`; the build script renders it into `openwrt/files/` (gitignored in the build tree). Commit after each task (repo only — never commit secrets or `.bin`s).

---

## File Structure

In the **`gwifi-openwrt`** repo, under a new `gale-image/` directory:

| Path | Responsibility |
|---|---|
| `gale-image/README.md` | How to build; secrets handling |
| `gale-image/gale.config` | Config fragment: extra `CONFIG_PACKAGE_*` + wpad swap (seed merged into `.config`) |
| `gale-image/gale-secrets.conf.example` | Template documenting required secret keys (committed) |
| `gale-image/files/etc/config/wireless` | 802.11s mesh + radio defaults (placeholders for SAE key/mesh-id) |
| `gale-image/files/etc/config/openwisp` | openwisp-config agent (placeholder shared_secret) |
| `gale-image/files/etc/config/usteer` | usteer safe defaults |
| `gale-image/files/etc/uci-defaults/99-gale-bootstrap` | Idempotent first-boot setup of batman + VLAN sub-ifaces + per-VLAN bridges (DRY loop) |
| `gale-image/build-gale-image.sh` | Render secrets → `openwrt/files/`, merge config, run `make`, emit image |
| `gale-image/verify-gale-image.py` | Extract built rootfs; assert overlay + substituted secrets + packages present |
| `gale-image/gale-secrets.conf` | **UNTRACKED** real secrets (gitignored) |

Built images land in `openwrt/bin/targets/ipq40xx/chromium/` (gitignored).

---

## Task 1: Repo scaffolding + secrets template

**Files:**
- Create: `gwifi-openwrt/gale-image/README.md`
- Create: `gwifi-openwrt/gale-image/gale-secrets.conf.example`
- Create (untracked): `gwifi-openwrt/gale-image/gale-secrets.conf`

- [ ] **Step 1: Write `gale-secrets.conf.example`** (committed template)

```sh
# gale-image/gale-secrets.conf.example — copy to gale-secrets.conf (untracked) and fill in.
# These are substituted into the overlay at build time; NEVER commit the filled file.
OPENWISP_SHARED_SECRET=""   # org "default" shared secret (OpenWISP admin → Organizations → config settings)
MESH_SAE_KEY=""             # WPA3-SAE passphrase for the 802.11s backhaul (generate: openssl rand -hex 24)
MESH_ID="gale-mesh-welland" # 802.11s mesh id (fleet-wide; safe to keep here)
OPENWISP_URL="https://wisp.welland.mithis.com"
```

- [ ] **Step 2: Create the real (untracked) `gale-secrets.conf`** with generated values

Run: `cp gale-image/gale-secrets.conf.example gale-image/gale-secrets.conf` then fill `OPENWISP_SHARED_SECRET` (from OpenWISP) and `MESH_SAE_KEY=$(openssl rand -hex 24)`.

- [ ] **Step 3: Verify it is gitignored**

Run: `cd gwifi-openwrt && git check-ignore gale-image/gale-secrets.conf`
Expected: prints the path (ignored). If not, add `gale-image/gale-secrets.conf` to `.gitignore`.

- [ ] **Step 4: Write `gale-image/README.md`** (build + secrets instructions; ~20 lines).

- [ ] **Step 5: Commit** (template + README only)

```bash
git add gale-image/README.md gale-image/gale-secrets.conf.example
git commit -m "gale-image: secrets template + build README"
```

---

## Task 2: Build config fragment (package selection)

**Files:**
- Create: `gwifi-openwrt/gale-image/gale.config`

- [ ] **Step 1: Write `gale.config`** — the per-spec §9 package set as a config seed

```
CONFIG_PACKAGE_openwisp-config=y
CONFIG_PACKAGE_openwisp-monitoring=y
CONFIG_PACKAGE_kmod-batman-adv=y
CONFIG_PACKAGE_batctl-default=y
# 802.11s SAE: swap basic wpad for the mesh variant
# CONFIG_PACKAGE_wpad-basic-mbedtls is unset
CONFIG_PACKAGE_wpad-mesh-mbedtls=y
CONFIG_PACKAGE_usteer=y
# NOTE: 802.1q is built into the kernel (CONFIG_VLAN_8021Q=y) — there is no
# kmod-8021q package, so no line is needed for VLAN sub-interface support.
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_ip-full=y
CONFIG_PACKAGE_tcpdump-mini=y
CONFIG_PACKAGE_ethtool=y
```

- [ ] **Step 2: Validate the feed package names exist** (typo guard)

Feed packages must appear in the feeds index; base/variant packages
(`wpad-mesh-mbedtls`, `ip-full`, `tcpdump-mini`, `ethtool`, `luci`) live in the
core `package/` tree and are validated post-defconfig in Task 8 Step 1 (the only
reliable check that a `CONFIG_PACKAGE_*` symbol actually resolved).

Run: `cd openwrt && ./scripts/feeds list | grep -wE 'openwisp-config|openwisp-monitoring|usteer|batctl-default|kmod-batman-adv'`
Expected: a line for each of the five feed packages.

- [ ] **Step 3: Commit**

```bash
git add gale-image/gale.config
git commit -m "gale-image: build config fragment (package set)"
```

---

## Task 3: uci-defaults bootstrap — batman + VLANs + bridges (the core)

**Files:**
- Create: `gwifi-openwrt/gale-image/files/etc/uci-defaults/99-gale-bootstrap`

This is the heart of the design (spec §6/§7.4). DRY loop over the VLAN map; idempotent.

- [ ] **Step 1: Write the bootstrap script**

```sh
#!/bin/sh
# 99-gale-bootstrap — first-boot network/mesh setup for gale auto-provisioning.
# Idempotent: uses fixed UCI section names so re-runs overwrite, not duplicate.
# VLAN map: NAME=VID. mgmt(5) gets DHCP; the rest are L2-only (APs attach later).
VLANS="mgmt=5 int=10 roam=20 iot=90 guest=99"

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
    # tagged sub-iface on the wired DSA trunk port 'wan'
    uci set network.wan_$vid="device"
    uci set network.wan_$vid.type='8021q'
    uci set network.wan_$vid.ifname='wan'
    uci set network.wan_$vid.vid="$vid"
    uci set network.wan_$vid.name="wan.$vid"
    # tagged sub-iface on the batman mesh
    uci set network.bat_$vid="device"
    uci set network.bat_$vid.type='8021q'
    uci set network.bat_$vid.ifname='bat0'
    uci set network.bat_$vid.vid="$vid"
    uci set network.bat_$vid.name="bat0.$vid"
    # per-VLAN bridge: wired + mesh (APs auto-attach via wifi-iface network=)
    uci set network.br_$name="device"
    uci set network.br_$name.type='bridge'
    uci set network.br_$name.name="br-$name"
    uci -q delete network.br_$name.ports
    uci add_list network.br_$name.ports="wan.$vid"
    uci add_list network.br_$name.ports="bat0.$vid"
    # interface on the bridge
    uci set network.$name="interface"
    uci set network.$name.device="br-$name"
    if [ "$name" = "mgmt" ]; then
        uci set network.$name.proto='dhcp'
    else
        uci set network.$name.proto='none'
    fi
done
uci commit network
exit 0
```

- [ ] **Step 2: shellcheck the script**

Run: `shellcheck -s sh gwifi-openwrt/gale-image/files/etc/uci-defaults/99-gale-bootstrap`
Expected: no errors (warnings about heredoc acceptable). Install shellcheck via apt if missing.

- [ ] **Step 3: Dry-run the UCI logic on the host** (catch obvious syntax errors without a device)

Run a host check that sources the loop logic against a throwaway UCI tree (or at minimum `sh -n` syntax check):
Run: `sh -n gwifi-openwrt/gale-image/files/etc/uci-defaults/99-gale-bootstrap && echo SYNTAX_OK`
Expected: `SYNTAX_OK`.

- [ ] **Step 4: Commit**

```bash
git add gale-image/files/etc/uci-defaults/99-gale-bootstrap
git commit -m "gale-image: uci-defaults bootstrap (batman + VLAN bridges)"
```

**Validation note:** exact DSA/batman/8021q UCI syntax for 25.12 must be confirmed on-device in Task 9/10 (bench). If `wan` is itself a bridge-vlan-filtered DSA port rather than accepting `8021q` device stacking, switch to `bridge-vlan` sections — decision deferred to first bench boot.

---

## Task 4: Wireless overlay — 802.11s mesh + radios

**Files:**
- Create: `gwifi-openwrt/gale-image/files/etc/config/wireless`

- [ ] **Step 1: Write `wireless`** — 5 GHz radio with an 802.11s mesh iface (SAE), 2.4 GHz radio enabled; placeholders for mesh-id/key. No client AP ifaces (OpenWISP adds them).

```
config wifi-device 'radio0'
    option type 'mac80211'
    option path 'platform/soc/a000000.wifi'
    option channel '36'
    option band '5g'
    option htmode 'VHT80'
    option disabled '0'

config wifi-iface 'mesh0'
    option device 'radio0'
    option mode 'mesh'
    option mesh_id '__MESH_ID__'
    option encryption 'sae'
    option key '__MESH_SAE_KEY__'
    option network 'mesh_hardif'
    option mesh_fwding '0'
    option mesh_rssi_threshold '0'

config wifi-device 'radio1'
    option type 'mac80211'
    option path 'platform/soc/a800000.wifi'
    option channel '6'
    option band '2g'
    option htmode 'HT20'
    option disabled '0'
```

- [ ] **Step 2: Confirm radio `path` values match the device**

The per-device DTS isn't in the OpenWrt target tree (it lives in the upstream
kernel, extracted only during the kernel build), so grep the ath10k caldata
hotplug script, which references both wifi node addresses:
Run: `grep -n "a000000.wifi\|a800000.wifi" openwrt/target/linux/ipq40xx/base-files/etc/hotplug.d/firmware/*-ath10k-caldata`
Expected: both `a000000.wifi` and `a800000.wifi` appear. If different, correct the `path` lines.

- [ ] **Step 3: Commit**

```bash
git add gale-image/files/etc/config/wireless
git commit -m "gale-image: 802.11s SAE mesh on 5GHz + 2.4GHz radio"
```

**Validation note (Risk #1):** concurrent AP+mesh on radio0 is bench-validated in Task 10. `mesh_fwding '0'` because batman-adv (not 802.11s HWMP) does forwarding.

---

## Task 5: OpenWISP + usteer overlay

**Files:**
- Create: `gwifi-openwrt/gale-image/files/etc/config/openwisp`
- Create: `gwifi-openwrt/gale-image/files/etc/config/usteer`

- [ ] **Step 1: Write `openwisp`** (placeholders substituted at build)

```
config controller 'http'
    option url '__OPENWISP_URL__'
    option shared_secret '__OPENWISP_SHARED_SECRET__'
    option interval '120'
    option verify_ssl '1'
    option management_interface 'br0.4'
    option uuid ''
```

- [ ] **Step 2: Write `usteer`** (safe defaults; OpenWISP can override later)

```
config usteer
    option syslog '1'
    option network 'br-int br-roam'
    option load_kick_enabled '0'
```

- [ ] **Step 3: Validate placeholders are the only `__...__` tokens**

Run: `grep -rn "__[A-Z_]*__" gwifi-openwrt/gale-image/files | sort` — confirm only the four known tokens appear (`__MESH_ID__`, `__MESH_SAE_KEY__`, `__OPENWISP_URL__`, `__OPENWISP_SHARED_SECRET__`).

- [ ] **Step 4: Commit**

```bash
git add gale-image/files/etc/config/openwisp gale-image/files/etc/config/usteer
git commit -m "gale-image: openwisp-config + usteer overlay (placeholders)"
```

---

## Task 6: Build script (render secrets → build)

**Files:**
- Create: `gwifi-openwrt/gale-image/build-gale-image.sh`

- [ ] **Step 1: Write `build-gale-image.sh`**

```sh
#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
SECRETS="$HERE/gale-secrets.conf"
[ -f "$SECRETS" ] || { echo "missing $SECRETS (copy from .example)"; exit 1; }
# shellcheck disable=SC1090
. "$SECRETS"
: "${OPENWISP_SHARED_SECRET:?}"; : "${MESH_SAE_KEY:?}"; : "${MESH_ID:?}"; : "${OPENWISP_URL:?}"

# 1) render overlay into the build tree (gitignored there)
rm -rf "$OWRT/files"
cp -a "$HERE/files" "$OWRT/files"
find "$OWRT/files" -type f -exec sed -i \
  -e "s|__OPENWISP_SHARED_SECRET__|$OPENWISP_SHARED_SECRET|g" \
  -e "s|__MESH_SAE_KEY__|$MESH_SAE_KEY|g" \
  -e "s|__MESH_ID__|$MESH_ID|g" \
  -e "s|__OPENWISP_URL__|$OPENWISP_URL|g" {} +
chmod 0755 "$OWRT/files/etc/uci-defaults/99-gale-bootstrap"

# 2) seed config: stock device config + our fragment
{ printf 'CONFIG_TARGET_ipq40xx=y\nCONFIG_TARGET_ipq40xx_chromium=y\nCONFIG_TARGET_ipq40xx_chromium_DEVICE_google_wifi=y\n';
  cat "$HERE/gale.config"; } > "$OWRT/.config"
( cd "$OWRT" && make defconfig )

# 3) build
( cd "$OWRT" && make -j6 )
echo "images: $OWRT/bin/targets/ipq40xx/chromium/"
```

- [ ] **Step 2: shellcheck + syntax**

Run: `shellcheck gwifi-openwrt/gale-image/build-gale-image.sh && sh -n gwifi-openwrt/gale-image/build-gale-image.sh && echo OK`
Expected: `OK`.

- [ ] **Step 3: Confirm no secret leaks into the build tree's tracked files**

(The `openwrt/files` is in a separate repo/tree; ensure `openwrt/` isn't the gwifi-openwrt repo — it is not.) Run: `grep -rn "__OPENWISP_SHARED_SECRET__" gwifi-openwrt/gale-image/files` Expected: the placeholder present (proves committed source has no real secret).

- [ ] **Step 4: Commit**

```bash
git add gale-image/build-gale-image.sh
git commit -m "gale-image: build script (secret render + make)"
```

---

## Task 7: Image verification script

**Files:**
- Create: `gwifi-openwrt/gale-image/verify-gale-image.py`

- [ ] **Step 1: Write `verify-gale-image.py`** — extract the squashfs rootfs from the sysupgrade image and assert overlay + packages

Behavior (use `unsquashfs` on the `root` member of the sysupgrade tar; fall back to scanning the squashfs in the factory image):
- Assert `/etc/config/openwisp` exists and contains the real `OPENWISP_URL` and **no** `__...__` placeholders.
- Assert `/etc/config/wireless` contains `mode 'mesh'` and the real `MESH_ID`, no placeholders.
- Assert `/etc/uci-defaults/99-gale-bootstrap` exists and is executable.
- Assert the package manifest lists `openwisp-config`, `kmod-batman-adv`, `batctl-default`, `wpad-mesh-mbedtls`, `usteer` (match `batctl` as a substring to tolerate the `-default` suffix).
- Print PASS/FAIL; non-zero exit on FAIL. Read secrets from `gale-secrets.conf` to know the expected substituted values.

- [ ] **Step 2: `sh -n`/py-compile the script**

Run: `uv run --no-project python -m py_compile gwifi-openwrt/gale-image/verify-gale-image.py && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add gale-image/verify-gale-image.py
git commit -m "gale-image: post-build image verification"
```

---

## Task 8: First build + automated image verification

**Files:** none new (runs Tasks 6–7).

- [ ] **Step 1: After defconfig, confirm every selected package resolved** (the real package-name check; also verifies the wpad swap)

Run (after `build-gale-image.sh` runs `make defconfig`, or run defconfig standalone first):
`for s in openwisp-config openwisp-monitoring kmod-batman-adv batctl-default wpad-mesh-mbedtls usteer luci ip-full tcpdump-mini ethtool; do grep -q "CONFIG_PACKAGE_$s=y" openwrt/.config || echo "NOT RESOLVED: $s"; done; grep -E "wpad" openwrt/.config`
Expected: no `NOT RESOLVED` lines; `CONFIG_PACKAGE_wpad-mesh-mbedtls=y` present and `wpad-basic-mbedtls` not `=y`.

- [ ] **Step 2: Build**

Run: `gwifi-openwrt/gale-image/build-gale-image.sh` (background; ~35–45 min)
Expected: exit 0; images in `openwrt/bin/targets/ipq40xx/chromium/`.

- [ ] **Step 3: Run the image verifier**

Run: `uv run --no-project python gwifi-openwrt/gale-image/verify-gale-image.py`
Expected: `RESULT: PASS` (overlay present, secrets substituted, packages present).

- [ ] **Step 4: Confirm no secrets in the repo**

Run: `cd gwifi-openwrt && git status --short && git grep -nI "$(. gale-image/gale-secrets.conf; echo "$MESH_SAE_KEY")" || echo "no secret in tracked files"`
Expected: clean status; `no secret in tracked files`.

- [ ] **Step 5: Commit** (any verifier fixes only — never images/secrets)

```bash
git add -A gale-image
git commit -m "gale-image: verified build produces correct overlay + packages"
```

---

## Task 9: Hardware bench test (acceptance — requires a puck)

**Files:** none. This is the real acceptance gate (spec §12). Cannot be automated in this environment.

- [ ] **Step 1:** Flash the factory image to one gale puck (per existing depthcharge/netboot tooling).
- [ ] **Step 2:** Wired boot → confirm it gets a mgmt IP on VLAN 5 and auto-registers in OpenWISP (matched by MAC).
- [ ] **Step 3:** Push a test config from OpenWISP (one client SSID→VLAN) → confirm SSID appears and a client gets DHCP from ten64.
- [ ] **Step 4:** Bring up a 2nd puck on the mesh; unplug puck-1's `wan` → confirm it stays manageable via the mesh and the client SSID still passes traffic (Risk #1/#3 validation).
- [ ] **Step 5:** Re-plug `wan` → confirm wired path resumes. Record results in `gale-image/README.md` (bench log) and commit.

---

## Notes for the implementer
- **Do not** `git push` or publish `.bin`s without explicit user approval (images bake secrets; pushing exposes welland infra).
- If `gw_mode` misbehaves over tagged `bat0.V` (Risk #3), drop `gw_mode` and rely on DHCP broadcast over the bridged mesh (BLA still active).
- Keep commits in the `gwifi-openwrt` repo on branch `gale-autoprovision-mesh`.
