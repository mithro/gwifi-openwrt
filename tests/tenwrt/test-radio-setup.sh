#!/bin/sh
# Unit tests for gwifi-radio-setup pure functions against a fake sysfs tree.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
GWIFI_RADIO_SOURCED=1 . "$HERE/../../tenwrt-image/files/usr/sbin/gwifi-radio-setup"

fails=0
eq() { if [ "$2" = "$3" ]; then printf '  PASS %s\n' "$1";
       else printf '  FAIL %s (want [%s] got [%s])\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

# Build a fake /sys/class/ieee80211. Real sysfs models phyN/device as a SYMLINK to the
# PCI <BDF> dir, and <BDF>/driver as a symlink to the bus driver — mirror that exactly.
SCRATCH="$HERE/../../tmp"; mkdir -p "$SCRATCH"   # project-local tmp (never /tmp), CWD-independent
SB=$(mktemp -d "$SCRATCH/radio-test.XXXXXX") || { echo "FAIL: cannot create scratch dir"; exit 1; }
[ -d "$SB" ] || { echo "FAIL: empty scratch dir (mktemp)"; exit 1; }   # guard: never operate on /
trap 'rm -rf "$SB"' EXIT INT TERM   # clean up even if an assertion path exits early
mkdir -p "$SB/phy0" "$SB/phy1" \
         "$SB/bus/ath11k_pci" "$SB/bus/ath10k_pci" \
         "$SB/devices/0000:00:03.0" "$SB/devices/0000:00:02.0"
# phy0 -> ath10k_pci at BDF 0000:00:03.0 ; phy1 -> ath11k_pci at BDF 0000:00:02.0
ln -s ../devices/0000:00:03.0 "$SB/phy0/device"
ln -s ../devices/0000:00:02.0 "$SB/phy1/device"
ln -s ../../bus/ath10k_pci "$SB/devices/0000:00:03.0/driver"
ln -s ../../bus/ath11k_pci "$SB/devices/0000:00:02.0/driver"
GWIFI_RADIO_SYSFS="$SB"

eq "phys present"      "1" "$(any_phy_present)"
eq "bdf of phy1"       "0000:00:02.0" "$(bdf_of_phy phy1)"
eq "bdf of phy0"       "0000:00:03.0" "$(bdf_of_phy phy0)"

# Empty sysfs dir (exists, no phy* entries): the glob stays literal -> empty, exit 0.
mkdir -p "$SB/empty"
GWIFI_RADIO_SYSFS="$SB/empty"
eq "empty sysfs -> none" "" "$(any_phy_present)"

# No-sysfs case: empty result, exit 0 (image-first no-op).
GWIFI_RADIO_SYSFS="$SB/nonexistent"
eq "no sysfs -> none" "" "$(any_phy_present)"

eq "swap 5g:2g"    "1" "$(radio_swap_needed 5g 2g)"
eq "swap 6g:2g"    "1" "$(radio_swap_needed 6g 2g)"
eq "no swap 2g:5g" ""  "$(radio_swap_needed 2g 5g)"
eq "no swap 2g:"   ""  "$(radio_swap_needed 2g "")"
eq "no swap :"     ""  "$(radio_swap_needed "" "")"

[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
