# tenwrt-image — OpenWISP-managed aarch64 OpenWrt VM image for ten64

This directory produces an OpenWrt VM image for the `armsr/armv8` target that
runs as a KVM guest (`tenwrt`) on the **ten64** (LS1088A arm64) host and will
own ten64's PCIe MT7915 Wi-Fi radio (14c3:7915, DBDC 2.4+5 GHz) once passed
through. It is a `fleet-image/` specialization — see
`../fleet-image/README.md` and `docs/fleet-image-base-design.md`.

## Architecture: simple profile, exact puck parity

This image bakes **only wisp-connectivity** — the minimum needed to reach the
OpenWISP controller — the same shape the fleet's pucks run since the
2026-07-22 simple-profile restructure. No mesh, no usteer config, no radios
baked in.

`etc/uci-defaults/99-tenwrt-bootstrap` (a thin driver over the shared
`fleet-image/files/lib/gwifi/bootstrap.sh` functions):

- creates `br0` from scratch (a QEMU guest matches no armsr board case, so
  there is no board-generated bridge to edit, unlike gale which edits
  `br-lan`),
- puts mgmt VLAN 4 **TAGGED** on the virtio trunk `eth0:t` — this differs
  from the pucks, which get VLAN 4 **untagged/pvid** from their switch port.
  Why: ten64's `tenwrt` libvirt domain has a single virtio trunk NIC on
  `br-raw`, and `br-raw` **floods all tagged frames** to every guest sharing
  it — an untagged mgmt leg here would either not exist as a distinct VLAN
  or would leak into other guests' traffic. Tagging VLAN 4 keeps it a
  proper, isolated leg through the flooding bridge.
- sets DHCP-on-mgmt, dnsmasq-off + `mithis.com` rebind whitelist, firewall
  mgmt zone, hostname `tenwrt`, and `mac_interface eth0` (device identity =
  the virtio NIC MAC, fixed by the libvirt domain XML),
- runs `/usr/sbin/gwifi-radio-setup` (no-op with no phy attached; see
  "Radio story" below),
- writes `TENVM-BOOTSTRAP-COMPLETE uplink=eth0` to `/dev/console`.

Everything else — SSH keys, the `gwifi-base` template (lldpd + usteer
configs, crontab, and the `post-reload-hook` that creates the roam=20 /
iot=90 / guest=99 bridge-vlans + interfaces), and `gwifi-aps` (radios + six
APs) — arrives from OpenWISP **after registration**, exactly like a puck.
`post-reload-hook`'s trunk detection tries `eth-black` → `lan` → **`eth0`**
(final fallback, added for this VM; pucks always match one of the first two
names, so ordering is safe — gale's own `eth0` is the DSA conduit and must
not match first).

Mesh-era design (batman-adv, 802.11s, baked usteer, the backhaul-gate cron)
is **not** in this image; it remains in git history
(`docs/ten64-vm-image-design.md`, now superseded for content) and returns
fleet-wide via OpenWISP if the fleet ever flips back to a mesh profile.

## Dedicated `openwrt-armsr` build tree

tenwrt builds use a **separate** OpenWrt checkout so they never disturb
concurrent gale/om2p builds in the shared `/home/tim/local/gwifi/openwrt`
tree used for live puck work. **Never build tenwrt in
`/home/tim/local/gwifi/openwrt`.**

One-time setup:

```sh
cd /home/tim/local/gwifi
git clone --no-checkout /home/tim/local/gwifi/openwrt openwrt-armsr
cd openwrt-armsr
git checkout 2b1b3b2266
cp -al ../openwrt/dl dl              # hardlink copy: reuses cached tarballs
./scripts/feeds update -a && ./scripts/feeds install -a
```

(No `feeds.conf` copy needed — the pinned feed commits live in the tracked
`feeds.conf.default`, which the clone already carries.)

The wrapper defaults `OWRT` to this tree; override with `OWRT=` if you keep
it elsewhere.

## Prerequisites

- `openwrt-armsr` set up as above.
- `fleet-secrets.conf` — the fleet-wide secrets file. It lives **outside
  this repo** at `/home/tim/local/gwifi/fleet-secrets.conf`. Build and
  verify take it via the `FLEET_SECRETS=` environment variable.
- For the smoke-boot: `qemu-system-aarch64` (Debian: `qemu-system-arm`) and
  an aarch64 UEFI firmware (Debian: `qemu-efi-aarch64`). On ten64 (aarch64)
  it runs under KVM; on an x86 dev host it runs under TCG (slower).

## Build

Run from the repo root:

```sh
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf ./tenwrt-image/build-tenwrt-image.sh
```

Only `OPENWISP_URL` and `OPENWISP_SHARED_SECRET` are required (no mesh
secrets — this image never renders `MESH_SAE_KEY`/`MESH_ID`/
`TOPOLOGY_RECEIVE_URL`). The script renders the shared `fleet-image/files/`
overlay then this directory's `files/`, seeds `.config` (target lines +
`fleet-image/base.config` + `tenwrt.config`), runs `make defconfig`, then
builds.

`RENDER_ONLY=1` renders the overlay (with secrets substituted) without
building — used by the fleet-image no-regression gates and useful to
inspect the rendered tree. `JOBS=N` controls parallelism (default 6).
`OWRT=` overrides the build tree.

## Outputs

Built images land in:

    /home/tim/local/gwifi/openwrt-armsr/bin/targets/armsr/armv8/

- `*-combined-efi.img` — bootable disk image (UEFI + GRUB + rootfs)
- `*-rootfs.tar.gz` — rootfs tarball used by the verifier
- `*.manifest` — installed package list

**Important:** built images contain baked-in secrets and must NOT be
published.

## Verify

```sh
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf uv run python tenwrt-image/verify-tenwrt-image.py
```

Checks: required packages present (including `acpid`, `qemu-ga`, the
`kmod-mt76xx-firmware` split packages) and no unrendered placeholders — both
via `fleet-image/verify_lib.py`'s `find_manifest`/`manifest_packages`/
`require_packages` and `check_no_placeholders` (this is the first verifier to
consume the shared helpers directly, rather than a locally-diverged copy).
Also, with tenwrt-specific local checks: `mediatek/mt7915_{wa,wm,rom_patch}.bin`
present in the rootfs, no mesh/wireless/usteer leftovers in the baked overlay
(including that the mesh-era `fleet-files/` pieces are absent), `usteer`
resolving to the stock package default (not a mesh-era baked copy), and that
a `combined-efi` artifact exists.

## Smoke-boot

```sh
uv run python tenwrt-image/qemu-smoke-boot.py
```

Boots the `combined-efi.img` headlessly under `qemu-system-aarch64 -M virt`.
PASS requires the serial console to emit `TENVM-BOOTSTRAP-COMPLETE` from
`99-tenwrt-bootstrap`, followed by a graceful ACPI shutdown: a QMP
`system_powerdown` is injected and the guest must power itself off via
`acpid` (the same mechanism `virsh shutdown` uses) — proven with no ten64
involvement. SKIPs cleanly if `qemu-system-aarch64` or an aarch64 UEFI
firmware is not installed.

Env knobs: `SMOKE_TIMEOUT` (boot phase, default 360s),
`SMOKE_SHUTDOWN_TIMEOUT` (shutdown phase, default 180s), `SMOKE_ACPI=0` to
skip the shutdown assertion and PASS on the boot marker alone.

## Recorded results (2026-07-25, branch `tenwrt-vm-parity`)

Built in the dedicated `openwrt-armsr` tree, v25.12.4 @ `2b1b3b2266`,
`JOBS=3`. Both `openwrt-armsr-armv8-generic-ext4-combined-efi.img` and
`openwrt-armsr-armv8-generic-squashfs-combined-efi.img` are emitted; the
**ext4 variant is the smoke-tested/deployed one** —
`qemu-smoke-boot.py`'s `find_image()` picks the alphabetically-first
`*combined-efi.img` match, which is `ext4` (`e` < `s`).

- `verify-tenwrt-image.py`: **PASS** — all 37 required packages present
  (incl. `acpid`, `qemu-ga`, the 7 `kmod-mt76xx-firmware` packages);
  `mt7915_{wa,wm,rom_patch}.bin` present; no mesh leftovers; `usteer`
  resolves to the stock package default.
- `qemu-smoke-boot.py`: **PASS** under TCG, against
  `openwrt-armsr-armv8-generic-ext4-combined-efi.img` — `TENVM-BOOTSTRAP-COMPLETE
  uplink=eth0` seen, then QMP `system_powerdown` → `acpid` → clean
  `reboot: Power down` (the `virsh shutdown` path, proven headless).

## Radio story

ten64's card is an MT7915A/D (`14c3:7915`), DBDC (dual-band, dual-concurrent:
2.4 + 5 GHz on one PCIe function). `gwifi-radio-setup` is driver-agnostic
(works for whatever card is passed through) and, after `wifi config`
auto-detects bands, **band-normalizes** the result: if `radio0` comes up as
the 5/6 GHz phy while `radio1` is 2.4 GHz, it swaps their UCI section names
so `radio0` is always 2.4 GHz / `radio1` is always 5 GHz — the binding the
`gwifi-aps` template expects. It is a no-op with no phy attached (image-first
boot, or this smoke test). **Open question:** DBDC phy enumeration order for
the MT7915 is only provable with the card physically passed through; the
normalization step exists precisely because that order is not guaranteed.

## Deploy runbook (manual — not run by this repo)

1. Copy the built image to ten64 — deploy what was proven (the
   smoke-tested ext4 variant, not the squashfs one that also gets built):
   `openwrt-armsr-armv8-generic-ext4-combined-efi.img` →
   `ten64:/var/lib/libvirt/images/tenwrt.img`.
2. `virsh define ten64-host/tenwrt.xml` — picks up the staged qemu-ga
   virtio-serial channel (see "Host-side, staged only" below).
3. VFIO-bind the MT7915 PCI function and `virsh start tenwrt`, per
   `ten64-host/README.md`.
4. Watch first boot: the guest DHCPs on VLAN 4 (tagged) and registers with
   OpenWISP as device `tenwrt`.
5. Re-run `openwisp/build-templates.py` to attach `gwifi-aps` +
   `gwifi-base` — **this must happen AFTER step 4**: the attach loop skips
   device names that don't exist yet on the controller, so a run before
   first registration silently attaches nothing to `tenwrt`.
6. `virsh shutdown tenwrt` must power the guest off gracefully (acpid ->
   `/sbin/poweroff`) — verified end-to-end by the smoke-boot ACPI phase.

Mesh-era design (`docs/ten64-vm-image-design.md`) is superseded for content
by this simple-profile image but preserved in git history; mesh comes back
fleet-wide via OpenWISP, not by rebuilding this image, if the fleet flips
back.

## Host-side, staged only

`ten64-host/tenwrt.xml` (local, outside this repo) has gained the qemu-ga
`<channel org.qemu.guest_agent.0>` edit, staged for the next manual `virsh
define`. Graceful shutdown already works without it via ACPI (`acpid`); the
channel only adds `qemu-ga` guest-agent functionality. Nothing on ten64 is
read, written, or restarted by this repo's build/verify/smoke steps.

## Secret handling

Committed overlay files contain only placeholders (`__OPENWISP_SHARED_SECRET__`,
`__OPENWISP_URL__`), substituted at build time from `FLEET_SECRETS`.
`fleet-secrets.conf` is never committed to this repository. Built `.img`
artifacts are never published.
