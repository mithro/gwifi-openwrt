# OM2P auto-provisioning mesh-AP firmware — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build OpenWISP auto-provisioning, mesh-failover OpenWrt firmware for the 6 Open-Mesh OM2P nodes (4× OM2P-LC + 2× OM2P), plus the single-radio OpenWISP template that manages them — the OM2P sibling of `gale-image/`.

**Architecture:** A new `om2p-image/` directory (parallel sibling to `gale-image/`) renders a secrets overlay into the shared OpenWrt tree (`/home/tim/local/gwifi/openwrt`) and builds the four `ath79/generic` OM2P sysupgrade images in one multi-profile `make`. A first-boot `uci-defaults` script picks the WAN/PoE uplink port **per model** from `/tmp/sysinfo/board_name` (eth1 on lc/v2, eth0 on v1/v4), builds the 802.1q trunk + batman-adv mesh + per-VLAN bridges, makes the second port a wired-client access port on roam/VLAN 20, and configures the single 2.4 GHz radio + 802.11s mesh by name. Fleet secrets move to one shared `fleet-secrets.conf`; `build-templates.py` is extended with a single-radio `gwifi-om2p` template that uses `{{ uplink_port }}`/`{{ client_port }}` per-device variables and reads the mesh key from `fleet-secrets.conf` (never regenerating it).

**Tech Stack:** OpenWrt 25.12.x (`ath79/generic`, kernel 6.12), busybox `sh` + UCI, batman-adv, `wpad-mesh-mbedtls`, `openwisp-config`/`openwisp-monitoring`, Python 3 (`uv run`) for verifiers, netjsonconfig/OpenWISP (Django ORM over SSH).

**Spec:** `docs/om2p-autoprovision-mesh-design.md` (read it; section refs below are to it).

**Working dir:** the worktree `/home/tim/local/gwifi/gwifi-openwrt/.worktrees/openwisp-controller` (branch `openwisp-controller`). The OpenWrt build tree is OUTSIDE the repo at `$OWRT` (default `/home/tim/local/gwifi/openwrt`).

---

## Conventions for every task

- **Secrets never enter the worktree.** All build/render *tests* in this plan use a **fixture** `fleet-secrets.conf` with dummy values via the `FLEET_SECRETS=` env var (e.g. under the project-local `./tmp/`). The real `fleet-secrets.conf` lives only in the primary checkout and is filled at deploy time (Task 1, migration note). Fit/build behavior does not depend on secret *values*, so dummy values fully exercise the build.
- **Python**: always `uv run` (never bare `python`/`pip`). Verifiers declare deps via PEP-723 headers where needed.
- **No `2>/dev/null`**, no files in `/tmp` (use `./tmp`), no American date formats.
- **Commit** after each task with a focused message ending in the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.
- **Build time:** the first OM2P build compiles a second toolchain (mips_24kc) — budget ~30–60 min. Switching the tree between `ipq40xx` (gale) and `ath79` (om2p) is expected; each target's `bin/targets/` outputs persist independently.

## File structure (created / modified)

```
fleet-secrets.conf.example          CREATE  (repo root) — shared fleet secret template
.gitignore                          MODIFY  add fleet-secrets.conf
gale-image/build-gale-image.sh      MODIFY  source fleet-secrets.conf; add RENDER_ONLY
om2p-image/                         CREATE
  files/etc/config/openwisp         CREATE  controller stanza (placeholders)
  files/etc/uci-defaults/99-om2p-bootstrap  CREATE  per-model ports + VLAN/mesh bootstrap
  om2p.config                       CREATE  package + ROOTFS_TARGZ fragment
  build-om2p-image.sh               CREATE  render + seed .config (4 profiles) + make
  verify-om2p-image.py              CREATE  rootfs /etc + manifest + 7168k fit gate
  README.md                         CREATE
openwisp/build-templates.py         MODIFY  read mesh_key from fleet-secrets.conf; add gwifi-om2p
docs/om2p-openwrt-install.md        CREATE  (Task 6) ap51-flash first-install note (brief)
tests/ (ad-hoc, ./tmp)              run-and-delete render/case tests
```

---

## Task 1: Shared `fleet-secrets.conf` + repoint gale

**Files:**
- Create: `fleet-secrets.conf.example` (repo root)
- Modify: `.gitignore`
- Modify: `gale-image/build-gale-image.sh`

- [ ] **Step 1: Create the shared secrets template**

Create `fleet-secrets.conf.example`:
```sh
# fleet-secrets.conf.example — copy to fleet-secrets.conf (untracked, 0600) and fill in.
# Fleet-wide secrets shared by BOTH firmware builds (gale + om2p) AND the OpenWISP
# templates. Substituted into overlays at build time; NEVER commit the filled file.
OPENWISP_SHARED_SECRET=""   # org "default" shared secret (OpenWISP admin -> Organizations -> config settings)
MESH_SAE_KEY=""             # WPA3-SAE key for the 802.11s backhaul; the ONE fleet mesh key (images + templates)
MESH_ID="gwifi-mesh"        # 802.11s mesh id (fleet-wide)
OPENWISP_URL="https://wisp.welland.mithis.com"
```

- [ ] **Step 2: Ignore the real file**

Add to `.gitignore` after the existing `gale-secrets.conf` line:
```
fleet-secrets.conf
```
(Keep the `gale-secrets.conf` line so any leftover stays ignored.)

- [ ] **Step 3: Repoint gale build + add a RENDER_ONLY seam**

In `gale-image/build-gale-image.sh`, replace the secrets block:
```sh
SECRETS="$HERE/gale-secrets.conf"
[ -f "$SECRETS" ] || { echo "missing $SECRETS (copy from .example)"; exit 1; }
# shellcheck disable=SC1090
. "$SECRETS"
```
with:
```sh
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
[ -f "$FLEET_SECRETS" ] || { echo "missing $FLEET_SECRETS (copy from fleet-secrets.conf.example)"; exit 1; }
# shellcheck disable=SC1090
. "$FLEET_SECRETS"
```
And immediately after the `chmod 0755 …/99-gale-bootstrap` line (before "# 2) seed config"), insert:
```sh
[ "${RENDER_ONLY:-0}" = "1" ] && { echo "rendered overlay to $OWRT/files (RENDER_ONLY)"; exit 0; }
```

- [ ] **Step 4: Write the render regression test (fixture secrets, no real values)**

Create `./tmp/fleet-secrets.fixture` (dummy values that contain sed metacharacters to exercise `esc()`):
```sh
OPENWISP_SHARED_SECRET="dummy&secret|with\\meta"
MESH_SAE_KEY="dummyMeshKey123"
MESH_ID="gwifi-mesh"
OPENWISP_URL="https://example.invalid"
```
Run (render-only, into a throwaway OWRT files dir):
```sh
mkdir -p ./tmp/owrt-gale
OWRT=$(pwd)/tmp/owrt-gale FLEET_SECRETS=$(pwd)/tmp/fleet-secrets.fixture RENDER_ONLY=1 sh gale-image/build-gale-image.sh
grep -RF 'dummy&secret|with\meta' ./tmp/owrt-gale/files/etc/config/openwisp
grep -RrowE '__[A-Z_]+__' ./tmp/owrt-gale/files || echo "OK: no placeholders"
```
Expected: the shared_secret appears verbatim in the rendered `openwisp` file; "OK: no placeholders".

- [ ] **Step 5: Verify gale render is unchanged (no regression)**

Expected output from Step 4: the grep for the literal secret succeeds (proves `esc()` + sed still substitutes correctly through the new `FLEET_SECRETS` path) and no `__PLACEHOLDER__` remains. (A full gale image rebuild is **not** required — the make path is byte-identical; only the secrets source moved. A full `./gale-image/build-gale-image.sh` rebuild + `verify-gale-image.py` can be run at gale deploy time for belt-and-suspenders.)

> **Migration note (deploy-time, primary checkout only — not this worktree):** copy the real values from `gale-image/gale-secrets.conf` into `fleet-secrets.conf` (`chmod 600`), then the old `gale-secrets.conf` can be retired. `MESH_SAE_KEY` must equal the currently-deployed key (it already does: `gale-secrets.conf` == the pucks' live key).

- [ ] **Step 6: Clean up + commit**
```sh
rm -rf ./tmp/owrt-gale ./tmp/fleet-secrets.fixture
git add fleet-secrets.conf.example .gitignore gale-image/build-gale-image.sh
git commit -m "om2p: add shared fleet-secrets.conf; repoint gale build + RENDER_ONLY seam"
```

---

## Task 2: OM2P overlay (openwisp config + per-model bootstrap) + package fragment

**Files:**
- Create: `om2p-image/files/etc/config/openwisp`
- Create: `om2p-image/files/etc/uci-defaults/99-om2p-bootstrap`
- Create: `om2p-image/om2p.config`

- [ ] **Step 1: Controller stanza (identical to gale)**

Create `om2p-image/files/etc/config/openwisp`:
```
config controller 'http'
	option url '__OPENWISP_URL__'
	option shared_secret '__OPENWISP_SHARED_SECRET__'
	option interval '120'
	option verify_ssl '1'
	option management_interface 'br-mgmt'
	option uuid ''
```

- [ ] **Step 2: First-boot bootstrap (per-model ports + VLAN/mesh)**

Create `om2p-image/files/etc/uci-defaults/99-om2p-bootstrap` (design §8.2/§8.4; heredocs quoted so substituted secret values are always literal):
```sh
#!/bin/sh
# 99-om2p-bootstrap — first-boot network/mesh setup for OM2P auto-provisioning.
# Idempotent: fixed UCI section names so re-runs overwrite, not duplicate.
# Two ethernet ports; the WAN/PoE uplink is a different GMAC per revision, so
# select UP/CLIENT from the board name (design C4). Trunk on UP; CLIENT = wired
# client access port on the roam VLAN (matches the gale puck lan in br-roam).
. /lib/functions.sh

case "$(board_name)" in
	openmesh,om2p-lc|openmesh,om2p-v2) UP=eth1; CLIENT=eth0 ;;
	openmesh,om2p-v1|openmesh,om2p-v4) UP=eth0; CLIENT=eth1 ;;
	*) UP=eth0; CLIENT=eth1 ;;   # safe default for any other OM2P revision
esac

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
	# tagged sub-iface on the wired uplink trunk port (UP)
	uci set network.up_$vid="device"
	uci set network.up_$vid.type='8021q'
	uci set network.up_$vid.ifname="$UP"
	uci set network.up_$vid.vid="$vid"
	uci set network.up_$vid.name="$UP.$vid"
	# tagged sub-iface on the batman mesh
	uci set network.bat_$vid="device"
	uci set network.bat_$vid.type='8021q'
	uci set network.bat_$vid.ifname='bat0'
	uci set network.bat_$vid.vid="$vid"
	uci set network.bat_$vid.name="bat0.$vid"
	# per-VLAN bridge: wired uplink + mesh (APs auto-attach later via wifi-iface network=)
	uci set network.br_$name="device"
	uci set network.br_$name.type='bridge'
	uci set network.br_$name.name="br-$name"
	uci -q delete network.br_$name.ports
	uci add_list network.br_$name.ports="$UP.$vid"
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

# wired client access port (CLIENT) untagged into br-roam (VLAN 20)
uci add_list network.br_roam.ports="$CLIENT"
uci commit network

# --- wireless: single 2.4 GHz radio0 + 802.11s mesh on it (design C5) ---
# radio0's per-SoC `path` is supplied by board detection; we configure by name.
[ -f /etc/config/wireless ] || /sbin/wifi config
uci -q batch <<'EOF'
set wireless.radio0.disabled='0'
set wireless.radio0.band='2g'
set wireless.radio0.channel='6'
set wireless.radio0.htmode='HT20'
set wireless.mesh0=wifi-iface
set wireless.mesh0.device='radio0'
set wireless.mesh0.mode='mesh'
set wireless.mesh0.mesh_id='__MESH_ID__'
set wireless.mesh0.encryption='sae'
set wireless.mesh0.key='__MESH_SAE_KEY__'
set wireless.mesh0.network='mesh_hardif'
set wireless.mesh0.mesh_fwding='0'
set wireless.mesh0.mesh_rssi_threshold='0'
EOF
uci commit wireless

exit 0
```

- [ ] **Step 3: Package + image fragment**

Create `om2p-image/om2p.config` (design §10/§11; `ROOTFS_TARGZ` gives the verifier a clean rootfs artifact; `wpad-basic` is swapped for the mesh/SAE supplicant):
```
CONFIG_TARGET_ROOTFS_TARGZ=y
CONFIG_PACKAGE_openwisp-config=y
CONFIG_PACKAGE_openwisp-monitoring=y
CONFIG_PACKAGE_kmod-batman-adv=y
CONFIG_PACKAGE_batctl-default=y
# CONFIG_PACKAGE_wpad-basic-mbedtls is not set
CONFIG_PACKAGE_wpad-mesh-mbedtls=y
CONFIG_PACKAGE_usteer=y
```

- [ ] **Step 4: Test the bootstrap — shellcheck + per-model port mapping**

Run shellcheck (POSIX sh):
```sh
shellcheck -s sh om2p-image/files/etc/uci-defaults/99-om2p-bootstrap
```
Expected: no errors (warnings about `. /lib/functions.sh` not found are acceptable — add `# shellcheck disable=SC1091` on that line if shellcheck flags it).

Test the port-selection logic in isolation. Create `./tmp/test-ports.sh`:
```sh
#!/bin/sh
board_name() { echo "$STUB_BOARD"; }
pick() {
  case "$(board_name)" in
    openmesh,om2p-lc|openmesh,om2p-v2) UP=eth1; CLIENT=eth0 ;;
    openmesh,om2p-v1|openmesh,om2p-v4) UP=eth0; CLIENT=eth1 ;;
    *) UP=eth0; CLIENT=eth1 ;;
  esac
  echo "$STUB_BOARD -> UP=$UP CLIENT=$CLIENT"
}
fail=0
check() { got=$(STUB_BOARD="$1" ; pick); [ "$got" = "$1 -> $2" ] || { echo "MISMATCH: $got (want $2)"; fail=1; }; }
check openmesh,om2p-lc "UP=eth1 CLIENT=eth0"
check openmesh,om2p-v2 "UP=eth1 CLIENT=eth0"
check openmesh,om2p-v1 "UP=eth0 CLIENT=eth1"
check openmesh,om2p-v4 "UP=eth0 CLIENT=eth1"
check openmesh,unknown "UP=eth0 CLIENT=eth1"
[ $fail = 0 ] && echo "ALL PORT MAPPINGS OK"
```
Run: `sh ./tmp/test-ports.sh`
Expected: `ALL PORT MAPPINGS OK`. (If you edit the case in the bootstrap, keep this test in sync — they must match.)

- [ ] **Step 5: Clean up + commit**
```sh
rm -f ./tmp/test-ports.sh
git add om2p-image/files om2p-image/om2p.config
git commit -m "om2p: overlay (openwisp stanza, per-model uci-defaults bootstrap) + package fragment"
```

---

## Task 3: Build script + verifier

**Files:**
- Create: `om2p-image/build-om2p-image.sh`
- Create: `om2p-image/verify-om2p-image.py`

- [ ] **Step 1: Build script (multi-profile, shared secrets, RENDER_ONLY)**

Create `om2p-image/build-om2p-image.sh`:
```sh
#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
[ -f "$FLEET_SECRETS" ] || { echo "missing $FLEET_SECRETS (copy from fleet-secrets.conf.example)"; exit 1; }
# shellcheck disable=SC1090
. "$FLEET_SECRETS"
: "${OPENWISP_SHARED_SECRET:?}"; : "${MESH_SAE_KEY:?}"; : "${MESH_ID:?}"; : "${OPENWISP_URL:?}"

# 1) render overlay into the build tree (gitignored there)
rm -rf "$OWRT/files"
cp -a "$HERE/files" "$OWRT/files"
# Escape sed replacement metacharacters (\, &, |) so secrets substitute literally.
esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/&/\\&/g' -e 's/|/\\|/g'; }
ss=$(esc "$OPENWISP_SHARED_SECRET"); mk=$(esc "$MESH_SAE_KEY")
mi=$(esc "$MESH_ID"); ou=$(esc "$OPENWISP_URL")
find "$OWRT/files" -type f -exec sed -i \
	-e "s|__OPENWISP_SHARED_SECRET__|$ss|g" \
	-e "s|__MESH_SAE_KEY__|$mk|g" \
	-e "s|__MESH_ID__|$mi|g" \
	-e "s|__OPENWISP_URL__|$ou|g" {} +
chmod 0755 "$OWRT/files/etc/uci-defaults/99-om2p-bootstrap"

[ "${RENDER_ONLY:-0}" = "1" ] && { echo "rendered overlay to $OWRT/files (RENDER_ONLY)"; exit 0; }

# 2) seed config: ath79/generic + the 4 OM2P profiles (multi-profile) + fragment
{ printf 'CONFIG_TARGET_ath79=y\nCONFIG_TARGET_ath79_generic=y\nCONFIG_TARGET_MULTI_PROFILE=y\n';
	printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_openmesh_om2p-lc=y\n';
	printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_openmesh_om2p-v1=y\n';
	printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_openmesh_om2p-v2=y\n';
	printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_openmesh_om2p-v4=y\n';
	cat "$HERE/om2p.config"; } > "$OWRT/.config"
( cd "$OWRT" && make defconfig )

# 3) build
( cd "$OWRT" && make -j"${JOBS:-6}" )
echo "images: $OWRT/bin/targets/ath79/generic/"
```

- [ ] **Step 2: Verifier (rootfs /etc + manifest + 7168k fit gate)**

Create `om2p-image/verify-om2p-image.py` (reads expected values from `../fleet-secrets.conf`; checks the shared rootfs tarball — falling back to the build staging dir — never prints secrets):
```python
#!/usr/bin/env python3
"""verify-om2p-image.py — validate the built OM2P images.

Checks, against the shared rootfs (the *-rootfs.tar.gz emitted by
CONFIG_TARGET_ROOTFS_TARGZ, or the build staging root-ath79 dir as fallback):
  - /etc/config/openwisp        : real URL + shared_secret, no placeholders
  - /etc/uci-defaults/99-om2p-bootstrap : executable; real MESH_ID + SAE key;
                                  mesh mode; board_name port selection; no placeholders
  - package manifest            : required packages present
  - each *-openmesh_om2p-*-squashfs-sysupgrade.bin <= 7168 KiB (the fit gate)

Reads expected values from <repo-root>/fleet-secrets.conf. Never prints secrets.

Usage: uv run python om2p-image/verify-om2p-image.py
"""
import glob
import os
import re
import stat
import sys
import tarfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/ath79/generic")
FLEET_SECRETS = os.environ.get("FLEET_SECRETS",
                               os.path.join(SCRIPT_DIR, "..", "fleet-secrets.conf"))
IMAGE_SIZE_LIMIT = 7168 * 1024  # design C1 (IMAGE_SIZE := 7168k)

REQUIRED_PACKAGES = ["openwisp-config", "openwisp-monitoring", "kmod-batman-adv",
                     "wpad-mesh-mbedtls", "usteer", "batctl"]
PROFILES = ["openmesh_om2p-lc", "openmesh_om2p-v1",
            "openmesh_om2p-v2", "openmesh_om2p-v4"]


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


def read_etc_files(image_dir):
    """Return {relpath: text} for the two overlay files, from the rootfs tarball
    (preferred) or the build staging dir (fallback)."""
    want = ("etc/config/openwisp", "etc/uci-defaults/99-om2p-bootstrap")
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
    # fallback: build staging rootfs
    roots = glob.glob(os.path.join(OWRT, "build_dir", "target-*", "root-ath79"))
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
        sys.exit("ERROR: secrets not found: %s" % FLEET_SECRETS)
    secrets = parse_secrets(FLEET_SECRETS)
    failures = []

    files, modes, src = read_etc_files(IMAGE_DIR)
    if not files:
        sys.exit("ERROR: no rootfs tarball or staging dir found; build with "
                 "CONFIG_TARGET_ROOTFS_TARGZ=y (in om2p.config)")
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
        (failures.append("FAIL %s: placeholders %s" % (label, ph)) if ph
         else print("  PASS %s: no placeholders" % label))

    ow = files.get("etc/config/openwisp")
    if ow is None:
        failures.append("FAIL openwisp: not in rootfs")
    else:
        check_value(ow, "OPENWISP_URL", "openwisp")
        check_value(ow, "OPENWISP_SHARED_SECRET", "openwisp")
        check_no_ph(ow, "openwisp")

    bs = files.get("etc/uci-defaults/99-om2p-bootstrap")
    if bs is None:
        failures.append("FAIL bootstrap: not in rootfs")
    else:
        if modes.get("etc/uci-defaults/99-om2p-bootstrap", 0) & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS bootstrap: executable")
        else:
            failures.append("FAIL bootstrap: not executable")
        check_value(bs, "MESH_ID", "bootstrap")
        check_value(bs, "MESH_SAE_KEY", "bootstrap")
        for needle, label in (("mode 'mesh'", "mesh mode"), ("board_name", "port selection")):
            (print("  PASS bootstrap: %s present" % label) if needle in bs
             else failures.append("FAIL bootstrap: %s ('%s') missing" % (label, needle)))
        check_no_ph(bs, "bootstrap")

    manifest = find_manifest(IMAGE_DIR)
    if manifest is None:
        failures.append("FAIL manifest: none found")
    else:
        for pkg in REQUIRED_PACKAGES:
            (print("  PASS manifest: '%s'" % pkg) if pkg in manifest
             else failures.append("FAIL manifest: '%s' missing" % pkg))

    print()
    for prof in PROFILES:
        hits = glob.glob(os.path.join(IMAGE_DIR, "*%s-squashfs-sysupgrade.bin" % prof))
        if not hits:
            failures.append("FAIL fit: no sysupgrade image for %s" % prof)
            continue
        size = os.path.getsize(hits[0])
        if size <= IMAGE_SIZE_LIMIT:
            print("  PASS fit: %s = %d B (<= %d)" % (prof, size, IMAGE_SIZE_LIMIT))
        else:
            failures.append("FAIL fit: %s = %d B EXCEEDS %d (trim ladder, design §10)"
                            % (prof, size, IMAGE_SIZE_LIMIT))

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

- [ ] **Step 3: Render smoke-test the build script (no full build)**
```sh
printf 'OPENWISP_SHARED_SECRET="d&s|x"\nMESH_SAE_KEY="meshKEY"\nMESH_ID="gwifi-mesh"\nOPENWISP_URL="https://example.invalid"\n' > ./tmp/fleet.fixture
mkdir -p ./tmp/owrt-om2p
OWRT=$(pwd)/tmp/owrt-om2p FLEET_SECRETS=$(pwd)/tmp/fleet.fixture RENDER_ONLY=1 sh om2p-image/build-om2p-image.sh
grep -F 'meshKEY' ./tmp/owrt-om2p/files/etc/uci-defaults/99-om2p-bootstrap
grep -F 'https://example.invalid' ./tmp/owrt-om2p/files/etc/config/openwisp
grep -RowE '__[A-Z_]+__' ./tmp/owrt-om2p/files || echo "OK: no placeholders"
test -x ./tmp/owrt-om2p/files/etc/uci-defaults/99-om2p-bootstrap && echo "OK: bootstrap executable"
```
Expected: mesh key + URL substituted into the right files; "OK: no placeholders"; "OK: bootstrap executable".

- [ ] **Step 4: Lint the verifier (no run yet — needs a build)**
```sh
uv run python -c "import ast,sys; ast.parse(open('om2p-image/verify-om2p-image.py').read()); print('syntax OK')"
```
Expected: `syntax OK`.

- [ ] **Step 5: Clean up + commit**
```sh
rm -rf ./tmp/owrt-om2p ./tmp/fleet.fixture
chmod +x om2p-image/build-om2p-image.sh
git add om2p-image/build-om2p-image.sh om2p-image/verify-om2p-image.py
git commit -m "om2p: build script (multi-profile ath79) + verifier (etc + manifest + 7168k fit gate)"
```

---

## Task 4: Build the four images + verify (fit gate)

**Files:** none created — exercises Tasks 2–3 against the real OpenWrt tree.

> Uses a **fixture** `fleet-secrets.conf` (dummy values) so no real secrets touch the worktree; the build/fit is value-independent. Requires `$OWRT` feeds updated (`cd $OWRT && ./scripts/feeds update -a && ./scripts/feeds install -a`).

- [ ] **Step 1: Provide fixture secrets + build (long)**
```sh
printf 'OPENWISP_SHARED_SECRET="testsecret"\nMESH_SAE_KEY="testmeshkey0123456789"\nMESH_ID="gwifi-mesh"\nOPENWISP_URL="https://wisp.welland.mithis.com"\n' > ./tmp/fleet.fixture
FLEET_SECRETS=$(pwd)/tmp/fleet.fixture sh om2p-image/build-om2p-image.sh
```
Expected: ends with `images: …/bin/targets/ath79/generic/`. (First run builds the mips_24kc toolchain — slow. If `make` errors on a missing host tool, install it and re-run; if it errors `Image too big`, that's the fit overflow → Step 3.)

- [ ] **Step 2: Verify (overlay + manifest + fit) — expect PASS**
```sh
FLEET_SECRETS=$(pwd)/tmp/fleet.fixture uv run python om2p-image/verify-om2p-image.py
```
Expected: `RESULT: PASS`, including a `PASS fit: …` line for each of lc/v1/v2/v4 ≤ 7340032 B.

- [ ] **Step 3: IF the build overflowed or a fit check FAILED — apply the trim ladder (design §10)**

In order, re-running build+verify after each, until it fits; **log every trim taken** (no silent truncation):
1. Drop `usteer`: comment `CONFIG_PACKAGE_usteer=y` in `om2p-image/om2p.config`.
2. `batctl-default` → `batctl-tiny` (swap the lines).
3. Trim optional `collectd-mod-*` plugins (add the unwanted ones as `# CONFIG_PACKAGE_collectd-mod-… is not set`) to the monitoring essentials.
4. **Last resort:** stop and report to the user that monitoring + gale-parity networking cannot co-reside in 7 MB; ask whether to drop `openwisp-monitoring`. Do not silently ship a reduced image.

If a trim was needed, commit the `om2p.config` change with a message recording the measured overflow and the trim applied.

- [ ] **Step 4: Confirm the firmware map still resolves (artifacts now exist)**
```sh
GWIFI_OPENWRT=$OWRT uv run --with pyyaml python openwisp/validate-firmware-images.py
```
Expected: `VALIDATION PASSED` — the four `ath79-generic-openmesh_om2p-*` image-type keys map to the OM2P boards and (now) the device profiles exist in the tree.

- [ ] **Step 5: Record the result + clean up (images are gitignored — nothing to commit unless om2p.config changed in Step 3)**
```sh
rm -f ./tmp/fleet.fixture
```
Note the four image sizes from Step 2 in the task report (the fit headroom matters for future package additions).

---

## Task 5: Extend `build-templates.py` — single-radio `gwifi-om2p` template

**Files:**
- Modify: `openwisp/build-templates.py`

> The template build/apply touches the **live controller** over SSH and uses real secrets — it is a **deploy-time** action run from the primary checkout, not from this worktree. This task writes and *unit-tests* the code (pure netjson + port map + mesh-key sourcing); the live apply is a documented deploy step (Task 6 / DEVELOPMENT.md).

- [ ] **Step 1: Read the mesh key from `fleet-secrets.conf` (stop regenerating)**

In `openwisp/build-templates.py`, add a parser and replace the generation. Near the top (after imports) add:
```python
FLEET_SECRETS = os.environ.get("FLEET_SECRETS",
                               os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "..", "fleet-secrets.conf"))


def read_fleet_mesh_key():
    """The ONE fleet mesh key — read from fleet-secrets.conf, never generated
    (regenerating would invalidate deployed pucks + baked images; design §15.7)."""
    import re
    with open(FLEET_SECRETS) as f:
        for line in f:
            m = re.match(r'^\s*MESH_SAE_KEY=(.*)$', line)
            if m:
                v = m.group(1).strip()
                if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
                    v = v[1:-1]
                if v:
                    return v
    raise SystemExit("MESH_SAE_KEY not set in %s" % FLEET_SECRETS)
```
In `main()`, replace:
```python
    vals["mesh_key"] = secrets.token_urlsafe(18)
```
with:
```python
    vals["mesh_key"] = read_fleet_mesh_key()
```
And **remove the `.wifi-secrets` write block** (the `with open(SECRETS_FILE, "w")…` + `os.chmod`) — `fleet-secrets.conf` is now the sole source (design §15.7). Drop the now-unused `import secrets` if nothing else uses it (leave `import os`).

- [ ] **Step 2: Add the OM2P netjson + per-model port map**

Add a function mirroring `netjson()` but single-radio, with `{{ uplink_port }}`/`{{ client_port }}` (design §12):
```python
def om2p_netjson():
    def wpa3(key):
        return {"protocol": "wpa3_personal", "cipher": "ccmp", "ieee80211w": "2", "key": key}

    def wpa2(key):
        return {"protocol": "wpa2_personal", "cipher": "ccmp", "key": key}

    roam = {"ieee80211r": True, "mobility_domain": "a1b2",
            "ft_psk_generate_local": True, "ieee80211k": True, "bss_transition": True}
    return {
        "radios": [
            {"name": "radio0", "protocol": "802.11n", "channel": 6, "channel_width": 20,
             "phy": "phy0", "country": "AU"},
        ],
        "interfaces": [
            {"type": "8021q", "vid": 5,  "name": "{{ uplink_port }}"},
            {"type": "8021q", "vid": 20, "name": "{{ uplink_port }}"},
            {"type": "8021q", "vid": 90, "name": "{{ uplink_port }}"},
            {"type": "8021q", "vid": 5,  "name": "bat0"},
            {"type": "8021q", "vid": 20, "name": "bat0"},
            {"type": "8021q", "vid": 90, "name": "bat0"},
            {"name": "br-mgmt", "type": "bridge",
             "bridge_members": ["{{ uplink_port }}.5", "bat0.5"],
             "addresses": [{"proto": "dhcp", "family": "ipv4"}]},
            {"name": "br-roam", "type": "bridge",
             "bridge_members": ["{{ uplink_port }}.20", "bat0.20", "{{ client_port }}"]},
            {"name": "br-iot", "type": "bridge",
             "bridge_members": ["{{ uplink_port }}.90", "bat0.90"]},
            {"name": "wl-ans-2", "type": "wireless", "wireless": dict(
                radio="radio0", mode="access_point", ssid="ansells", network=["br-roam"],
                encryption=wpa3("{{ ansells_key }}"), **roam)},
            {"name": "wl-iot", "type": "wireless", "wireless": dict(
                radio="radio0", mode="access_point", ssid="ansells-iot", network=["br-iot"],
                encryption=wpa2("{{ iot_key }}"))},
            {"name": "mp0", "type": "wireless", "wireless": dict(
                radio="radio0", mode="802.11s", mesh_id="gwifi-mesh", network=["mesh0"],
                encryption=wpa3("{{ mesh_key }}"))},
        ],
        "network": [
            {"config_name": "interface", "config_value": "bat0", "proto": "batadv",
             "routing_algo": "BATMAN_IV", "bridge_loop_avoidance": "1",
             "distributed_arp_table": "1"},
            {"config_name": "interface", "config_value": "mesh0",
             "proto": "batadv_hardif", "master": "bat0"},
        ],
    }


def om2p_ports(model):
    """Map an OpenWISP device.model string to its uplink/client GMAC (design C4).
    Returns None for the bare 'OpenMesh OM2P' (revision unknown until onboard)."""
    m = (model or "").lower()
    if "om2p-lc" in m or "om2p v2" in m:
        return {"uplink_port": "eth1", "client_port": "eth0"}
    if "om2p v1" in m or "om2p v4" in m:
        return {"uplink_port": "eth0", "client_port": "eth1"}
    return None
```

- [ ] **Step 3: Add the OM2P ORM (attach + per-device context) to the Django snippet**

Add a second Django snippet (sibling to `DJANGO`) that creates the `gwifi-om2p` template (NOT default), attaches it to org-`default` devices whose `model` starts with `OpenMesh OM2P`, and sets each device's `config.context` `uplink_port`/`client_port` from `om2p_ports(model)` (skipping + warning for the bare ones). Wire it into `main()` to render+apply after the puck template, reusing the same `vals` (so `mesh_key`/`ansells_key`/`iot_key` match). Use `om2p_ports` results computed in Python and embedded as a `{model_substr: ports}` lookup, or compute per device inside the ORM from `dev.model`. Keep the existing redaction of key values in printed output.

```python
DJANGO_OM2P = r'''
import json, re
from swapper import load_model
Template = load_model("config", "Template")
Config = load_model("config", "Config")
Org = load_model("openwisp_users", "Organization")
Device = load_model("config", "Device")
org = Org.objects.get(slug="default")
CONFIG = json.loads({cfg!r})
DEFAULTS = json.loads({defaults!r})

t, created = Template.objects.update_or_create(
    organization=org, name="gwifi-om2p",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=CONFIG, default=False, default_values=DEFAULTS),
)
t.full_clean(); t.save()
print("om2p template:", "created" if created else "updated", "id=", t.id)

def ports_for(model):
    m = (model or "").lower()
    if "om2p-lc" in m or "om2p v2" in m:
        return {{"uplink_port": "eth1", "client_port": "eth0"}}
    if "om2p v1" in m or "om2p v4" in m:
        return {{"uplink_port": "eth0", "client_port": "eth1"}}
    return None

attached = skipped = 0
for d in Device.objects.filter(organization=org, model__startswith="OpenMesh OM2P"):
    c, _ = Config.objects.get_or_create(device=d, defaults=dict(backend="netjsonconfig.OpenWrt"))
    if t not in c.templates.all():
        c.templates.add(t)
    p = ports_for(d.model)
    if p is None:
        skipped += 1
        print("WARN: %s model=%r -> set uplink/client after onboard" % (d.name, d.model))
    else:
        ctx = dict(c.context or {{}}); ctx.update(p); c.context = ctx
    c.full_clean(); c.save()
    attached += 1
print("om2p configs attached:", attached, " (ports-pending:", skipped, ")")

d = Device.objects.filter(organization=org, model__startswith="OpenMesh OM2P").first()
if d:
    rendered = d.config.backend_instance.render()
    rendered = re.sub(r"(option key ').*?(')", r"\g<1><REDACTED>\g<2>", rendered)
    print("=" * 60); print("OM2P sample render (keys redacted):"); print("=" * 60)
    print(rendered)
'''
```
In `main()`, after the puck snippet is applied, build + apply this one:
```python
    om2p_cfg = json.dumps(om2p_netjson())
    om2p_script = DJANGO_OM2P.format(cfg=om2p_cfg, defaults=defaults)
    p2 = subprocess.run(SSH_WISP, input=om2p_script, text=True, capture_output=True, timeout=180)
    out2 = p2.stdout
    for v in vals.values():
        out2 = out2.replace(v, "<REDACTED>")
    sys.stdout.write(out2)
    if p2.stderr.strip():
        sys.stderr.write("\n--- om2p stderr ---\n" + p2.stderr)
```

- [ ] **Step 4: Unit-test the pure pieces (no SSH, no live controller)**

Create `./tmp/test-om2p-netjson.py`:
```python
import importlib.util, json, os
spec = importlib.util.spec_from_file_location("bt", "openwisp/build-templates.py")
bt = importlib.util.module_from_spec(spec)
# build-templates.py runs only under __main__, so import is side-effect free
spec.loader.exec_module(bt)

nj = bt.om2p_netjson()
assert [r["name"] for r in nj["radios"]] == ["radio0"], "must be single-radio"
blob = json.dumps(nj)
for forbidden in ("radio1", "mp1", "br-guest", "wl-ans-5", "wl-guest", "ansells-guest"):
    assert forbidden not in blob, "leaked dual-radio construct: %s" % forbidden
assert "{{ uplink_port }}" in blob and "{{ client_port }}" in blob
assert bt.om2p_ports("OpenMesh OM2P-LC") == {"uplink_port": "eth1", "client_port": "eth0"}
assert bt.om2p_ports("OpenMesh OM2P v1") == {"uplink_port": "eth0", "client_port": "eth1"}
assert bt.om2p_ports("OpenMesh OM2P v4") == {"uplink_port": "eth0", "client_port": "eth1"}
assert bt.om2p_ports("OpenMesh OM2P") is None  # bare -> pending
print("om2p netjson + ports OK")
```
Run: `uv run python ./tmp/test-om2p-netjson.py`
Expected: `om2p netjson + ports OK`. (If import fails because the module does work at import time, guard that work under `if __name__ == "__main__":` — it already is.)

- [ ] **Step 5: Verify `{{ uplink_port }}` actually substitutes in device fields (design §15.8)**

If `netjsonconfig` is installable locally, confirm variables resolve inside `device`/`ifname` fields (the load-bearing assumption):
```sh
uv run --with netjsonconfig python - <<'PY'
from netjsonconfig import OpenWrt
import importlib.util
spec = importlib.util.spec_from_file_location("bt", "openwisp/build-templates.py")
bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
cfg = bt.om2p_netjson()
o = OpenWrt(cfg, context={"uplink_port": "eth1", "client_port": "eth0",
                          "ansells_key": "x", "iot_key": "y", "mesh_key": "z"})
out = o.render()
assert "eth1.20" in out and "eth1.5" in out, "uplink_port did NOT substitute in device fields"
assert "option ifname 'eth0'" in out or "list ports 'eth0'" in out, "client_port missing"
print("VARIABLE SUBSTITUTION OK")
PY
```
Expected: `VARIABLE SUBSTITUTION OK`. **If it fails**, switch to the §15.8 fallback: emit two concrete templates (`gwifi-om2p-a` = eth1/eth0 for lc/v2; `gwifi-om2p-b` = eth0/eth1 for v1/v4) attached by model, instead of variables. (Record the outcome in the task report either way.)

- [ ] **Step 6: Clean up + commit**
```sh
rm -f ./tmp/test-om2p-netjson.py
git add openwisp/build-templates.py
git commit -m "openwisp: gwifi-om2p single-radio template (per-device port vars) + mesh-key from fleet-secrets.conf"
```

---

## Task 6: README, install note, and finish

**Files:**
- Create: `om2p-image/README.md`
- Create: `docs/om2p-openwrt-install.md`

- [ ] **Step 1: om2p-image/README.md**

Mirror `gale-image/README.md`: prerequisites (OpenWrt tree at `$OWRT`, feeds updated, `unsquashfs`/python via `uv`), the shared `fleet-secrets.conf` (point to the repo-root `.example`; note it is shared with gale), `./om2p-image/build-om2p-image.sh`, outputs in `bin/targets/ath79/generic/` (four `…-openmesh_om2p-{lc,v1,v2,v4}-squashfs-sysupgrade.bin`, sensitive — gitignored), `uv run python om2p-image/verify-om2p-image.py` (incl. the 7168k fit gate), and the per-model uplink/wired-client behavior. Cross-link `docs/om2p-autoprovision-mesh-design.md` and `docs/om2p-openwrt-install.md`.

- [ ] **Step 2: docs/om2p-openwrt-install.md (brief, design §13)**

Short runbook: OM2P run CloudTrax/Open-Mesh stock; flash to OpenWrt via **`ap51-flash`** (host tool) pushing the produced `…-openmesh_om2p-<rev>-squashfs-sysupgrade.bin` over a direct Ethernet link while the device boots (it requests via TFTP/ap51). Note: there is no separate factory image (the openmesh-image-wrapped sysupgrade is the flashable artifact); after first flash, onboarding is automatic (mgmt VLAN 5 → DHCP → OpenWISP). Mark on-hardware flashing as bench work; cross-link the design + `gale-openwrt-netboot-install.md` for the analogous gale path.

- [ ] **Step 3: Commit docs**
```sh
git add om2p-image/README.md docs/om2p-openwrt-install.md
git commit -m "om2p: README + ap51-flash install note"
```

- [ ] **Step 4: Final review + branch finish**

- Dispatch a final code review over the whole branch diff (`superpowers:requesting-code-review` or the `feature-dev:code-reviewer` agent), focused on: the bootstrap's idempotency + per-model correctness, no secrets committed, the build-templates.py change not regenerating the mesh key, and the verifier's fit gate.
- Then use **`superpowers:finishing-a-development-branch`** to choose merge/PR (per DEVELOPMENT.md, `main` advances via PR; do not push to `main` directly).

- [ ] **Step 5: Deploy actions (run from the PRIMARY checkout, not this worktree — after merge)**

Documented hand-off, not executed here: (a) fill the real `fleet-secrets.conf` (migrate from `gale-secrets.conf`); (b) real `./om2p-image/build-om2p-image.sh` + `verify-om2p-image.py`; (c) `uv run python openwisp/build-templates.py` to create/attach `gwifi-om2p` + set port vars (sets the 4 LC now; set the 2 bare devices' `uplink_port`/`client_port` after they onboard and report v1/v2/v4); (d) register the four images in the firmware-upgrader via `openwisp/upload-firmware.py`; (e) bench-flash one unit (ap51-flash) and validate onboarding + mesh failover.

---

## Notes on key decisions (for the implementer)

- **Why a fixture secrets file for tests:** secrets never live in a worktree (DEVELOPMENT.md). Build/fit/substitution mechanics are value-independent, so dummy values fully validate them; the real build is a deploy step.
- **Why `board_name` (not `network.wan.device`) for port selection:** `/tmp/sysinfo/board_name` is written by board-detect *before* uci-defaults run, and is unambiguous; the default `wan`/`lan` roles are inconsistent across the family (design C4) and would mislead.
- **Why the rootfs tarball for verification:** the OM2P sysupgrade is an `openmesh-image` container (not a tar); the shared `*-rootfs.tar.gz` (from `CONFIG_TARGET_ROOTFS_TARGZ=y`) is the same rootfs baked into all four images and is trivially inspectable. The 7168k fit gate stats the real per-device `.bin`s.
- **Mesh-key single-sourcing is load-bearing:** `build-templates.py` must READ `MESH_SAE_KEY`; regenerating it (the old behavior) would orphan the deployed pucks and the baked images (design §15.7).
