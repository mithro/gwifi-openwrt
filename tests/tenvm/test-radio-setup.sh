#!/bin/sh
# Unit tests for gwifi-radio-setup pure functions against a fake sysfs tree.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
GWIFI_RADIO_SOURCED=1 . "$HERE/../../tenvm-image/files/usr/sbin/gwifi-radio-setup"

fails=0
eq() { if [ "$2" = "$3" ]; then printf '  PASS %s\n' "$1";
       else printf '  FAIL %s (want [%s] got [%s])\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

# Build a fake /sys/class/ieee80211. Real sysfs models phyN/device as a SYMLINK to the
# PCI <BDF> dir, and <BDF>/driver as a symlink to the bus driver — mirror that exactly.
SB=$(mktemp -d ./tmp/radio-test.XXXXXX)
mkdir -p "$SB/phy0" "$SB/phy1" \
         "$SB/bus/ath11k_pci" "$SB/bus/ath10k_pci" \
         "$SB/devices/0000:00:03.0" "$SB/devices/0000:00:02.0"
# phy0 -> ath10k_pci at BDF 0000:00:03.0 ; phy1 -> ath11k_pci at BDF 0000:00:02.0
ln -s ../devices/0000:00:03.0 "$SB/phy0/device"
ln -s ../devices/0000:00:02.0 "$SB/phy1/device"
ln -s ../../bus/ath10k_pci "$SB/devices/0000:00:03.0/driver"
ln -s ../../bus/ath11k_pci "$SB/devices/0000:00:02.0/driver"
GWIFI_RADIO_SYSFS="$SB"

eq "ath11k phy"        "phy1" "$(phy_for_driver ath11k_pci)"
eq "ath10k phy"        "phy0" "$(phy_for_driver ath10k_pci)"
eq "missing driver"    ""     "$(phy_for_driver rtw88_pci)"
eq "bdf of mesh phy"   "0000:00:02.0" "$(bdf_of_phy phy1)"

# No-sysfs case: empty result, exit 0 (image-first no-op).
GWIFI_RADIO_SYSFS="$SB/nonexistent"
eq "no sysfs -> empty" "" "$(phy_for_driver ath11k_pci)"

rm -rf "$SB"
[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
