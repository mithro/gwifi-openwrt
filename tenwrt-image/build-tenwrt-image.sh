#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
# Dedicated build tree (design D7): NEVER the shared /home/tim/local/gwifi/openwrt,
# which the live gale/puck builds use.
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt-armsr}
FLEET_SECRETS=${FLEET_SECRETS:-$HERE/../fleet-secrets.conf}
SECRETS_VARS="OPENWISP_SHARED_SECRET OPENWISP_URL"
OVERLAYS="$HERE/../fleet-image/files $HERE/files"
CHMOD_FILES="etc/uci-defaults/99-tenwrt-bootstrap usr/sbin/gwifi-radio-setup"
# shellcheck disable=SC1091
. "$HERE/../fleet-image/build-lib.sh"
fleet_require_secrets
fleet_render
fleet_render_only_gate

tenwrt_targets() {
	printf 'CONFIG_TARGET_armsr=y\nCONFIG_TARGET_armsr_armv8=y\nCONFIG_TARGET_armsr_armv8_DEVICE_generic=y\n'
}
fleet_seed_config tenwrt_targets tenwrt.config
fleet_build
echo "images: $OWRT/bin/targets/armsr/armv8/"
