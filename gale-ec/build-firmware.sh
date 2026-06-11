#!/usr/bin/env bash
#
# Build the reconstructed gale EC firmware from TRACKED sources, in a TRACKED location.
#
# Everything the build needs is either in this repo (tracked) or fetched reproducibly from a
# pinned reference into the gitignored .build/ workspace next to this script:
#
#   tracked, in-repo (source of truth):
#     board/gale/*                 reconstructed board files
#     firmware-patches/*.patch     local platform/ec patches applied on the pinned base
#     this script                  the recipe + the pinned upstream rev
#   fetched into ./.build/ (gitignored, reproducible from the pins above):
#     platform/ec @ $EC_REV        upstream ChromeOS EC (branch firmware-gale-8281.B)
#     arm-none-eabi 2016q3         the period toolchain (system gcc-14 mis-builds the 2016 tree)
#
# Output: build/gale/ec.bin in the workspace, and the RO/RW ELFs copied to the vendored
#         analysis references renode/data/rebuilt-R{O,W}.elf.
#
# Usage:   ./build-firmware.sh
#          GALE_EC_TOOLCHAIN=/path/to/gcc-arm-none-eabi-5_4-2016q3 ./build-firmware.sh   # reuse a TC
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$HERE/.build"
EC="$WORK/ec"
BOARD="$HERE/board/gale"
PATCHES="$HERE/firmware-patches"

EC_URL="https://chromium.googlesource.com/chromiumos/platform/ec"
EC_BRANCH="firmware-gale-8281.B"
EC_REV="7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb"   # firmware-gale-8281.B tip (factory branch)

TC_TARBALL="gcc-arm-none-eabi-5_4-2016q3-20160926-linux.tar.bz2"
TC_URL="https://launchpad.net/gcc-arm-embedded/5.0/5-2016-q3-update/+download/$TC_TARBALL"
TC="${GALE_EC_TOOLCHAIN:-$WORK/gcc-arm-none-eabi-5_4-2016q3}"

BOARD_FILES=(board.c board.h build.mk ec.tasklist gpio.inc usb_pd_config.h usb_pd_policy.c)

mkdir -p "$WORK"

# 1. platform/ec at the pinned rev (cached clone; refetch the branch if the rev is missing).
if [ ! -d "$EC/.git" ]; then
	echo ">> cloning platform/ec into $EC"
	git clone "$EC_URL" "$EC"
fi
if ! git -C "$EC" cat-file -e "${EC_REV}^{commit}" 2>/dev/null; then
	echo ">> fetching $EC_BRANCH"
	git -C "$EC" fetch origin "$EC_BRANCH"
fi
echo ">> checkout pinned base $EC_REV"
git -C "$EC" checkout -q -f "$EC_REV"
git -C "$EC" clean -qfdx -e /build      # keep build/ for incremental; drop overlay + scratch

# 2. apply the tracked local patches on top of the pinned base.
shopt -s nullglob
for p in "$PATCHES"/*.patch; do
	echo ">> apply $(basename "$p")"
	git -C "$EC" apply --whitespace=nowarn "$p"
done
shopt -u nullglob

# 3. overlay the tracked board files (symlinks back to the in-repo source of truth).
mkdir -p "$EC/board/gale"
for f in "${BOARD_FILES[@]}"; do
	ln -sf "$BOARD/$f" "$EC/board/gale/$f"
done
ln -sf ../../Makefile "$EC/board/gale/Makefile"

# 4. toolchain: reuse $GALE_EC_TOOLCHAIN, else a prior download, else fetch the pinned 2016q3.
if [ ! -x "$TC/bin/arm-none-eabi-gcc" ]; then
	echo ">> 2016q3 toolchain not found at $TC — downloading (~89 MB, one time)"
	curl -fL "$TC_URL" -o "$WORK/$TC_TARBALL"
	tar -C "$WORK" -xjf "$WORK/$TC_TARBALL"
	rm -f "$WORK/$TC_TARBALL"
	TC="$WORK/gcc-arm-none-eabi-5_4-2016q3"
fi
"$TC/bin/arm-none-eabi-gcc" --version >/dev/null   # sanity: toolchain runs

# 5. build.
echo ">> building gale (BOARD=gale)"
make -C "$EC" BOARD=gale CROSS_COMPILE="$TC/bin/arm-none-eabi-" -j"$(nproc)" build/gale/ec.bin

# 6. vendor the reference ELFs the analysis tooling reads (renode/data/).
cp "$EC/build/gale/RO/ec.RO.elf" "$HERE/renode/data/rebuilt-RO.elf"
cp "$EC/build/gale/RW/ec.RW.elf" "$HERE/renode/data/rebuilt-RW.elf"

echo ">> OK: $EC/build/gale/ec.bin ($(stat -c%s "$EC/build/gale/ec.bin") bytes)"
echo ">> vendored: renode/data/rebuilt-R{O,W}.elf"
