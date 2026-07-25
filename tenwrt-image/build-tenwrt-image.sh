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
