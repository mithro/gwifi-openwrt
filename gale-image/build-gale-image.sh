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
