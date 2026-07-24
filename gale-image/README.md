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

1. Fill the **shared** fleet secrets file (one file for gale + om2p + tenwrt +
   templates), outside this repo:

   ```sh
   cp fleet-secrets.conf.example /home/tim/local/gwifi/fleet-secrets.conf
   chmod 600 /home/tim/local/gwifi/fleet-secrets.conf
   $EDITOR /home/tim/local/gwifi/fleet-secrets.conf
   ```

   Set `OPENWISP_SHARED_SECRET` (from OpenWISP admin → Organizations → config
   settings), `MESH_SAE_KEY` (must match the gwifi-puck OpenWISP template's
   mesh key), and `TOPOLOGY_RECEIVE_URL` (batman-adv Topology receive URL —
   gale-only). `MESH_ID` and `OPENWISP_URL` are pre-filled with fleet defaults
   and rarely change.

   The old per-image `gale-image/gale-secrets.conf` path is **DEPRECATED**
   (values are identical to the ones now read from `fleet-secrets.conf` —
   verified during the migration); the build script no longer defaults to it.

2. Run the build script from the repo root:

   ```sh
   FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf ./gale-image/build-gale-image.sh
   ```

   The script renders secrets into a temporary `files/` tree in the build
   directory (merging the shared `fleet-image/files/` overlay first, then this
   directory's own `files/`), seeds `.config` as target lines +
   `fleet-image/base.config` + `gale.config`, runs `make defconfig`, then
   builds with `make -j6`. `RENDER_ONLY=1` renders the overlay only (no
   defconfig, no build) — this is the seam the fleet-image no-regression
   gates use to byte-diff the rendered tree against the pre-refactor image
   (see `../fleet-image/README.md`); it is also useful to inspect the
   rendered files directly.

## Outputs

Built images land in:

    /home/tim/local/gwifi/openwrt/bin/targets/ipq40xx/chromium/

**Important:** built `.bin` images contain baked-in secrets and must NOT be published.

## Secret handling

`/home/tim/local/gwifi/fleet-secrets.conf` is untracked and lives outside this
repo (the deprecated `gale-image/gale-secrets.conf` is also gitignored).
Committed overlay files under `files/` contain only placeholders
(`__OPENWISP_SHARED_SECRET__`, etc.). Built images bake real secret values and
must **never** be published from `bin/targets/` — the build script always
publishes from `gale-image/out/` (with an `IMAGE_ID` sidecar), which is the
only path the netboot installer/publish tooling should ever read from.

## Verification

After a successful build, run:

    FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf python3 gale-image/verify-gale-image.py

This checks that all expected packages and config stanzas appear in the built image.
The verifier takes the same `FLEET_SECRETS` env var as the build (defaults to
`<repo-root>/fleet-secrets.conf` if unset).
