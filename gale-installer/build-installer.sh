#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Build the gale netboot INSTALLER image (raw initramfs FIT + autoinstall
# overlay). Minimal config — no mesh/openwisp packages, no secrets; the
# installer only fetches + writes the real factory image.
# See docs/wisp-netboot-install-design.md section 5.5.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OWRT=${OWRT:-/home/tim/local/gwifi/openwrt}
OUT=${OUT:-$HERE/out}

# 1) overlay (no secrets, no substitution)
rm -rf "$OWRT/files"
cp -a "$HERE/files" "$OWRT/files"
chmod 0755 "$OWRT/files/usr/sbin/gale-autoinstall" \
           "$OWRT/files/etc/init.d/gale-autoinstall"

BUILD_ID="gale-installer-$(date -u +%Y%m%d%H%M%S)-g$(git -C "$HERE" rev-parse --short HEAD)"

# 2) stock device config only (initramfs FIT comes from the tree's
#    netboot patch; see ../openwrt-patches/)
printf 'CONFIG_TARGET_ipq40xx=y\nCONFIG_TARGET_ipq40xx_chromium=y\nCONFIG_TARGET_ipq40xx_chromium_DEVICE_google_wifi=y\n' \
    > "$OWRT/.config"
( cd "$OWRT" && make defconfig )

# 3) build
( cd "$OWRT" && make -j"${JOBS:-6}" )

# 4) collect + sanity-check the raw FIT (d00dfeed, NOT the .vboot)
ITB="$OWRT/bin/targets/ipq40xx/chromium/openwrt-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb"
magic=$(od -An -tx1 -N4 "$ITB" | tr -d ' ')
[ "$magic" = "d00dfeed" ] || { echo "BAD FIT magic: $magic"; exit 1; }
mkdir -p "$OUT"
cp "$ITB" "$OUT/$BUILD_ID.itb"
ln -sf "$BUILD_ID.itb" "$OUT/gale-installer.itb"
echo "installer: $OUT/$BUILD_ID.itb (symlink: $OUT/gale-installer.itb)"
