#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
SECRETS="$HERE/gale-secrets.conf"
[ -f "$SECRETS" ] || { echo "missing $SECRETS (copy from .example)"; exit 1; }
# shellcheck disable=SC1090
. "$SECRETS"
: "${OPENWISP_SHARED_SECRET:?}"; : "${MESH_SAE_KEY:?}"; : "${MESH_ID:?}"; : "${OPENWISP_URL:?}"
: "${TOPOLOGY_RECEIVE_URL:?}"

# 1) render overlay into the build tree (gitignored there)
rm -rf "$OWRT/files"
cp -a "$HERE/files" "$OWRT/files"
# Escape sed replacement metacharacters (\, &, |) so a secret containing them
# substitutes literally rather than corrupting the rendered config (backslash
# first, to avoid double-escaping).
esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/&/\\&/g' -e 's/|/\\|/g'; }
ss=$(esc "$OPENWISP_SHARED_SECRET"); mk=$(esc "$MESH_SAE_KEY")
mi=$(esc "$MESH_ID"); ou=$(esc "$OPENWISP_URL")
tu=$(esc "$TOPOLOGY_RECEIVE_URL")
find "$OWRT/files" -type f -exec sed -i \
	-e "s|__OPENWISP_SHARED_SECRET__|$ss|g" \
	-e "s|__MESH_SAE_KEY__|$mk|g" \
	-e "s|__MESH_ID__|$mi|g" \
	-e "s|__OPENWISP_URL__|$ou|g" \
	-e "s|__TOPOLOGY_RECEIVE_URL__|$tu|g" {} +
chmod 0755 "$OWRT/files/etc/uci-defaults/99-gale-bootstrap" \
	"$OWRT/files/etc/init.d/gwifi-topology" \
	"$OWRT/files/usr/sbin/gwifi-topology-push"

# 1b) stamp the image id — the netboot installer's idempotence marker.
# The same id is emitted as a sidecar next to factory.bin so the publish
# step (gwifi-netboot publish) keeps manifest and baked marker in sync.
# See docs/wisp-netboot-install-design.md section 5.5.
IMAGE_ID="gale-openwrt-$(date -u +%Y%m%d%H%M%S)-g$(git -C "$HERE" rev-parse --short HEAD)"
printf '%s\n' "$IMAGE_ID" > "$OWRT/files/etc/gwifi-image-id"
echo "image id: $IMAGE_ID"

# 2) seed config: stock device config + our fragment
{ printf 'CONFIG_TARGET_ipq40xx=y\nCONFIG_TARGET_ipq40xx_chromium=y\nCONFIG_TARGET_ipq40xx_chromium_DEVICE_google_wifi=y\n';
	cat "$HERE/gale.config"; } > "$OWRT/.config"
( cd "$OWRT" && make defconfig )

# 3) build
( cd "$OWRT" && make -j"${JOBS:-6}" )

# 4) copy artifacts to a build-private out/ dir + sidecar for publish.
# bin/targets is SHARED with other builds: the installer build regenerates
# factory.bin there with stock files (no marker, no bootstrap). Publishing
# from bin/targets after another build shipped a stock image to the fleet
# on 2026-07-12 ("post-flash marker ''"). Always publish from out/.
BIN="$OWRT/bin/targets/ipq40xx/chromium/openwrt-ipq40xx-chromium-google_wifi-squashfs-factory.bin"
OUT="$HERE/out"
mkdir -p "$OUT"
cp "$BIN" "$OUT/factory-$IMAGE_ID.bin"
ln -sf "factory-$IMAGE_ID.bin" "$OUT/factory.bin"
printf '%s\n' "$IMAGE_ID" > "$OUT/factory.bin.image-id"
echo "artifact: $OUT/factory-$IMAGE_ID.bin"
echo "sidecar: $OUT/factory.bin.image-id ($IMAGE_ID)"
echo "publish from $OUT - never from bin/targets"
