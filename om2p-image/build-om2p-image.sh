#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
SECRETS_VARS="OPENWISP_SHARED_SECRET MESH_SAE_KEY MESH_ID OPENWISP_URL"
# om2p is still mesh-era: own overlay + the shared fleet-files (backhaul gate
# + hotplug hook), NO fleet-image/files — its render must stay byte-identical
# until the simple-profile conversion (design spec D6/§4.1).
OVERLAYS="$HERE/files $HERE/../fleet-files"
CHMOD_FILES="etc/uci-defaults/99-om2p-bootstrap usr/sbin/gwifi-backhaul-gate
             etc/hotplug.d/net/30-gwifi-backhaul"
# shellcheck disable=SC1091
. "$HERE/../fleet-image/build-lib.sh"
fleet_require_secrets
fleet_render
fleet_render_only_gate

# ath79/generic + the 4 OM2P profiles (multi-profile). Set DEVICES="..." to
# override (e.g. a single profile for a per-device build).
om2p_targets() {
	printf 'CONFIG_TARGET_ath79=y\nCONFIG_TARGET_ath79_generic=y\nCONFIG_TARGET_MULTI_PROFILE=y\n'
	for d in ${DEVICES:-openmesh_om2p-lc openmesh_om2p-v1 openmesh_om2p-v2 openmesh_om2p-v4}; do
		printf 'CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_%s=y\n' "$d"
	done
}
fleet_seed_config om2p_targets om2p.config
fleet_build
echo "images: $OWRT/bin/targets/ath79/generic/"
