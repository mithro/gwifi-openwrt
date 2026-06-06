# gale-image — auto-provisioning OpenWrt overlay for Google Wifi (gale)

This directory produces a single generic OpenWrt image for the gale (Google Wifi)
puck that auto-provisions from an OpenWISP controller on first boot and falls back
to an 802.11s + batman-adv mesh uplink when no managed config is yet applied.

The image is built from a stock OpenWrt ipq40xx/chromium/google_wifi target with
this overlay baked into the rootfs (`files/`), plus extra packages from `gale.config`.
Real secret values (OpenWISP shared secret, mesh SAE key) are substituted at build
time and are never committed to this repository.

## Prerequisites

- OpenWrt build tree checked out at `/home/tim/local/gwifi/openwrt` (v25.12.4).
  Feeds must already be updated and installed (`scripts/feeds update -a && scripts/feeds install -a`).
- `unsquashfs` (squashfs-tools) installed for `verify-gale-image.py`.

## Build

1. Copy the secrets template and fill in the two real secret values:

   ```sh
   cp gale-image/gale-secrets.conf.example gale-image/gale-secrets.conf
   $EDITOR gale-image/gale-secrets.conf
   ```

   Set `OPENWISP_SHARED_SECRET` (from OpenWISP admin → Organizations → config settings)
   and `MESH_SAE_KEY` (must match the gwifi-puck OpenWISP template's mesh key).
   `MESH_ID` and `OPENWISP_URL` are pre-filled with fleet defaults and rarely change.

2. Run the build script from the repo root:

   ```sh
   ./gale-image/build-gale-image.sh
   ```

   The script renders secrets into a temporary `files/` tree in the build directory,
   seeds `.config` with the target + package fragment, runs `make defconfig`, then
   builds with `make -j6`.

## Outputs

Built images land in:

    /home/tim/local/gwifi/openwrt/bin/targets/ipq40xx/chromium/

**Important:** built `.bin` images contain baked-in secrets and must NOT be published.

## Secret handling

`gale-image/gale-secrets.conf` is untracked (gitignored). Committed overlay files
under `files/` contain only placeholders (`__OPENWISP_SHARED_SECRET__`, etc.).

## Verification

After a successful build, run:

    python3 gale-image/verify-gale-image.py

This checks that all expected packages and config stanzas appear in the built image.
