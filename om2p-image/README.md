# om2p-image — auto-provisioning OpenWrt overlay for Open-Mesh OM2P

This directory builds OpenWrt images for the welland Open-Mesh / CloudTrax **OM2P**
nodes (4× OM2P-LC + 2× OM2P) that auto-provision from the OpenWISP controller on
first boot and fall back to the fleet 802.11s + batman-adv mesh when the wired
uplink is lost — the OM2P sibling of [`../gale-image/`](../gale-image/).

Built for target **`ath79/generic`**, devices `openmesh_om2p-{lc,v1,v2,v4}`. One
multi-profile `make` emits all four images (shared rootfs). See the design in
[`../docs/om2p-autoprovision-mesh-design.md`](../docs/om2p-autoprovision-mesh-design.md)
and the first-install runbook in
[`../docs/om2p-openwrt-install.md`](../docs/om2p-openwrt-install.md).

## How it differs from gale (small hardware)

- **Single 2.4 GHz radio** — the client AP(s) and the 802.11s mesh share `radio0`.
- **Two Ethernet ports, per-model uplink** — the WAN/PoE jack is `eth1` on
  lc/v2 but `eth0` on v1/v4, so the first-boot bootstrap picks the uplink from
  `/tmp/sysinfo/board_name`. The trunk rides the uplink; the **other port is a
  wired-client access port on the roam VLAN (20)**.
- **Bootstrap-generated wireless** — the per-SoC radio `path` differs (ar9330 AHB
  vs ar7240 PCI vs qca9533), so `radio0` is configured *by name* at first boot
  rather than from a static `/etc/config/wireless`.
- **~7 MB firmware budget** (`IMAGE_SIZE := 7168k`) — slimmed package set (no
  LuCI / tcpdump); the verifier enforces the fit.

## Prerequisites

- OpenWrt build tree at `$OWRT` (default `/home/tim/local/gwifi/openwrt`), feeds
  updated + installed (`./scripts/feeds update -a && ./scripts/feeds install -a`).
- `unsquashfs` (squashfs-tools) — not strictly needed (the verifier reads the
  rootfs tarball), but handy.

## Build

1. Fill the **shared** fleet secrets (one file for gale + om2p + templates):
   ```sh
   cp fleet-secrets.conf.example fleet-secrets.conf   # at the repo root
   chmod 600 fleet-secrets.conf
   $EDITOR fleet-secrets.conf
   ```
   Set `OPENWISP_SHARED_SECRET` (org `default` shared secret) and `MESH_SAE_KEY`
   (the ONE fleet mesh key — must match the deployed pucks / gale image).
   `MESH_ID` and `OPENWISP_URL` are pre-filled.

2. Build (from the repo root):
   ```sh
   ./om2p-image/build-om2p-image.sh
   ```
   The first run compiles the `ath79` (mips_24kc) toolchain — budget ~30–60 min.
   To build a single revision instead of all four (per-device fallback):
   ```sh
   DEVICES="openmesh_om2p-lc" ./om2p-image/build-om2p-image.sh
   ```
   `OWRT=`, `FLEET_SECRETS=`, `JOBS=`, and `RENDER_ONLY=1` (render the overlay
   only, no build) are honored as env overrides.

## Outputs

```
$OWRT/bin/targets/ath79/generic/openwrt-…-openmesh_om2p-{lc,v1,v2,v4}-squashfs-sysupgrade.bin
```
These bake fleet secrets and are **sensitive — not published** (gitignored).
The `openmesh-image`-wrapped sysupgrade is also the first-install (ap51-flash)
artifact (there is no separate factory image).

## Verify

```sh
uv run python om2p-image/verify-om2p-image.py
```
Checks the rendered overlay (substituted secret *values*, no placeholders,
bootstrap executable, mesh + per-model port selection present), the package
manifest, and that each image is **≤ 7168 KiB**. Never prints secrets.

## Secret handling

`fleet-secrets.conf` is untracked (gitignored, shared with gale). Committed
overlay files contain only placeholders (`__OPENWISP_SHARED_SECRET__`, etc.).
Built `.bin`s contain the substituted secrets and must not be published.
