#!/usr/bin/env python3
"""verify-tenwrt-image.py — validate the built ten64 Wi-Fi VM image.

Simple-profile reality (docs/fleet-image-base-design.md, fleet-image-base-plan.md
Task 7-9): the image bakes ONLY what is needed to reach the OpenWISP controller
on first boot — APs, client VLAN legs and steering all arrive later via
OpenWISP templates. There is no mesh, no usteer, no backhaul gate in this
image; those are om2p/gale-only.

Checks, against the rootfs (the *-rootfs.tar.gz emitted by CONFIG_TARGET_ROOTFS_TARGZ,
or the build staging root-* dir as fallback):
  - /etc/config/openwisp   : real URL + shared_secret, management_interface
                             'br0.4', NO `option mac_interface` line (the
                             bootstrap driver sets it per-image), no placeholders
  - /etc/uci-defaults/99-tenwrt-bootstrap : executable; gwifi_create_bridge eth0;
                             TENVM-BOOTSTRAP-COMPLETE marker; no placeholders
  - /lib/gwifi/bootstrap.sh : present (shared bootstrap function library)
  - /usr/sbin/gwifi-radio-setup : executable; radio_swap_needed (band normalizer)
  - mesh/gate leftovers ABSENT: /etc/config/wireless, /etc/config/usteer,
    /usr/sbin/gwifi-backhaul-gate, /etc/hotplug.d/net/30-gwifi-backhaul
  - MediaTek mt7915 firmware blobs present (tar member names, not decoded):
    lib/firmware/mediatek/{mt7915_wa,mt7915_wm,mt7915_rom_patch}.bin
  - package manifest       : required packages incl. all in-tree PCIe Wi-Fi
                             drivers+firmware, plus VM guest tools (acpid, qemu-ga)
  - a bootable combined-efi.img artifact exists

Reads expected values from <repo-root>/fleet-secrets.conf (or $FLEET_SECRETS). Never
prints secrets. Usage: uv run python tenwrt-image/verify-tenwrt-image.py
"""
import glob
import os
import re
import stat
import sys
import tarfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "fleet-image"))
from verify_lib import parse_secrets

OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt-armsr")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/armsr/armv8")
FLEET_SECRETS = os.environ.get(
    "FLEET_SECRETS", os.path.join(SCRIPT_DIR, "..", "fleet-secrets.conf"))

REQUIRED_PACKAGES = [
    "openwisp-config", "openwisp-monitoring",
    # VM guest tools: ACPI graceful-shutdown handler + qemu guest agent
    "acpid", "qemu-ga",
    # PCIe Wi-Fi drivers — all in-tree families (any card that may be passed through)
    "kmod-ath9k", "kmod-ath10k", "kmod-ath11k-pci", "kmod-ath12k",
    "kmod-mt76x0e", "kmod-mt76x2", "kmod-mt7615e", "kmod-mt7915e",
    "kmod-mt7921e", "kmod-mt7925e", "kmod-mt7996e",
    "kmod-rtw88-8723de", "kmod-rtw88-8814ae", "kmod-rtw88-8821ce",
    "kmod-rtw88-8822be", "kmod-rtw88-8822ce",
    "kmod-rtw89-pci", "kmod-rtw89-8851be", "kmod-rtw89-8852ae",
    "kmod-rtw89-8852be", "kmod-rtw89-8852ce", "kmod-rtw89-8922ae",
    # Representative firmware (ath explicit; mt76 is split kmod-mtXXXX-firmware
    # packages below; rtw auto per-chip)
    "ath10k-firmware-qca9377", "ath11k-firmware-qcn9074",
    "ath12k-firmware-qcn9274", "rtl8852ce-firmware",
    "kmod-mt7615-firmware", "kmod-mt7915-firmware", "kmod-mt7916-firmware",
    "kmod-mt7921-firmware", "kmod-mt7922-firmware", "kmod-mt7925-firmware",
    "kmod-mt7996-firmware",
]
OVERLAY_EXEC = [
    "etc/uci-defaults/99-tenwrt-bootstrap",
    "usr/sbin/gwifi-radio-setup",
]
# Content we need to inspect (read into memory).
WANT_CONTENT = (
    "etc/config/openwisp",
    "etc/uci-defaults/99-tenwrt-bootstrap",
    "usr/sbin/gwifi-radio-setup",
)
# Present-only (existence, no content read needed).
WANT_PRESENCE = (
    "lib/gwifi/bootstrap.sh",
)
# Mesh/backhaul-gate leftovers that must NOT be in a simple-profile rootfs.
ABSENT = [
    "etc/config/wireless",
    "etc/config/usteer",
    "usr/sbin/gwifi-backhaul-gate",
    "etc/hotplug.d/net/30-gwifi-backhaul",
]
FIRMWARE_BLOBS = [
    "lib/firmware/mediatek/mt7915_wa.bin",
    "lib/firmware/mediatek/mt7915_wm.bin",
    "lib/firmware/mediatek/mt7915_rom_patch.bin",
]
# Every path we ever care about the presence of (used to scope the tarball
# scan / staging-dir lookups without decoding the whole tree).
CANDIDATE_PATHS = (
    set(WANT_CONTENT) | set(WANT_PRESENCE) | set(OVERLAY_EXEC)
    | set(ABSENT) | set(FIRMWARE_BLOBS)
)
# The exec-check loop presence-tests each OVERLAY_EXEC entry via `files.get`,
# which only holds content for WANT_CONTENT paths — so every OVERLAY_EXEC
# entry must also be read as content, or the presence test silently breaks.
assert set(OVERLAY_EXEC) <= set(WANT_CONTENT), \
    "OVERLAY_EXEC entries must be in WANT_CONTENT"


def read_rootfs(image_dir):
    """Return ({relpath: text}, {relpath: mode}, {relpath present in rootfs}, label)
    from the rootfs tarball (preferred) or the build staging root-* dir
    (fallback). The member-name set enables absence checks (mesh/gate
    leftovers) without decoding file contents."""
    tarballs = glob.glob(os.path.join(image_dir, "*rootfs.tar.gz"))
    if tarballs:
        tarball = max(tarballs, key=os.path.getmtime)   # newest, in case a stale one lingers
        files, modes, members = {}, {}, set()
        with tarfile.open(tarball, "r:gz") as tf:
            for m in tf.getmembers():
                rel = m.name.lstrip("./")
                if rel not in CANDIDATE_PATHS or not m.isfile():
                    continue
                members.add(rel)
                if rel in OVERLAY_EXEC:
                    modes[rel] = m.mode
                if rel in WANT_CONTENT:
                    files[rel] = tf.extractfile(m).read().decode(errors="replace")
        return files, modes, members, "tarball %s" % os.path.basename(tarball)
    roots = glob.glob(os.path.join(OWRT, "build_dir", "target-*", "root-*"))
    if roots:
        files, modes, members = {}, {}, set()
        for rel in CANDIDATE_PATHS:
            p = os.path.join(roots[0], rel)
            if os.path.isfile(p):
                members.add(rel)
                if rel in OVERLAY_EXEC:
                    modes[rel] = os.stat(p).st_mode
                if rel in WANT_CONTENT:
                    with open(p, errors="replace") as fh:
                        files[rel] = fh.read()
        return files, modes, members, "staging %s" % roots[0]
    return None, None, None, None


# NOTE: intentionally NOT verify_lib's find_manifest — returns CONTENT of the
# sorted-first *.manifest, vs lib's PATH of the mtime-newest; same name+arity
# as verify_lib.find_manifest but different return type — importing it
# without deleting this local def would be silently shadowed. See
# fleet-image-base-plan.md Task 6.
def find_manifest(image_dir):
    for name in sorted(os.listdir(image_dir)):
        if name.endswith(".manifest"):
            with open(os.path.join(image_dir, name)) as fh:
                return fh.read()
    return None


def main():
    if not os.path.isdir(IMAGE_DIR):
        sys.exit("ERROR: image dir not found: %s (build first)" % IMAGE_DIR)
    if not os.path.isfile(FLEET_SECRETS):
        sys.exit("ERROR: secrets not found: %s (set FLEET_SECRETS=...)" % FLEET_SECRETS)
    secrets = parse_secrets(FLEET_SECRETS)
    failures = []

    files, modes, members, src = read_rootfs(IMAGE_DIR)
    if src is None:
        sys.exit("ERROR: no rootfs tarball or staging dir found; build with "
                 "CONFIG_TARGET_ROOTFS_TARGZ=y (in tenwrt.config)")
    print("Rootfs source: %s\n" % src)

    def check_value(content, key, label):
        v = secrets.get(key)
        if not v:
            failures.append("FAIL %s: %s missing/empty in fleet-secrets.conf" % (label, key))
        elif v not in content:
            failures.append("FAIL %s: %s value not present" % (label, key))
        else:
            print("  PASS %s: %s rendered" % (label, key))

    # NOTE: intentionally NOT verify_lib's check_no_placeholders — diverges
    # (regex __[A-Z_]+__ has no digits vs lib's __[A-Z][A-Z0-9_]*__; also
    # prints a PASS line, lib doesn't) — see fleet-image-base-plan.md Task 6.
    def check_no_ph(content, label):
        ph = re.findall(r'__[A-Z_]+__', content)
        if ph:
            failures.append("FAIL %s: placeholders %s" % (label, ph))
        else:
            print("  PASS %s: no placeholders" % label)

    ow = files.get("etc/config/openwisp")
    if ow is None:
        failures.append("FAIL openwisp: not in rootfs")
    else:
        check_value(ow, "OPENWISP_URL", "openwisp")
        check_value(ow, "OPENWISP_SHARED_SECRET", "openwisp")
        if "management_interface 'br0.4'" in ow:
            print("  PASS openwisp: management_interface 'br0.4' present")
        else:
            failures.append("FAIL openwisp: management_interface 'br0.4' not found")
        if "option mac_interface" in ow:
            failures.append("FAIL openwisp: option mac_interface present "
                             "(bootstrap driver must set it, not the shared overlay)")
        else:
            print("  PASS openwisp: no option mac_interface (per-image bootstrap sets it)")
        check_no_ph(ow, "openwisp")

    bs = files.get("etc/uci-defaults/99-tenwrt-bootstrap")
    if bs is None:
        failures.append("FAIL bootstrap: not in rootfs")
    else:
        if "gwifi_create_bridge eth0" in bs:
            print("  PASS bootstrap: gwifi_create_bridge eth0")
        else:
            failures.append("FAIL bootstrap: gwifi_create_bridge eth0 not found")
        if "TENVM-BOOTSTRAP-COMPLETE" in bs:
            print("  PASS bootstrap: TENVM-BOOTSTRAP-COMPLETE marker present")
        else:
            failures.append("FAIL bootstrap: TENVM-BOOTSTRAP-COMPLETE marker missing")
        check_no_ph(bs, "bootstrap")

    for rel in WANT_PRESENCE:
        if rel in members:
            print("  PASS present: %s" % rel)
        else:
            failures.append("FAIL present: %s missing from rootfs" % rel)

    rs = files.get("usr/sbin/gwifi-radio-setup")
    if rs is None:
        failures.append("FAIL radio-setup: not in rootfs")
    elif "radio_swap_needed" in rs:
        print("  PASS radio-setup: radio_swap_needed present")
    else:
        failures.append("FAIL radio-setup: radio_swap_needed not found")

    for rel in OVERLAY_EXEC:
        if rel not in files:
            failures.append("FAIL exec: %s missing from rootfs" % rel)
        elif modes.get(rel, 0) & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS exec: %s present and executable" % rel)
        else:
            failures.append("FAIL exec: %s present but not executable" % rel)

    for rel in ABSENT:
        if rel in members:
            failures.append("FAIL leftover: %s present (should be absent; "
                             "mesh/backhaul remnant)" % rel)
        else:
            print("  PASS leftover-free: %s" % rel)

    for rel in FIRMWARE_BLOBS:
        if rel in members:
            print("  PASS firmware: %s present" % rel)
        else:
            failures.append("FAIL firmware: %s missing from rootfs" % rel)

    manifest = find_manifest(IMAGE_DIR)
    if manifest is None:
        failures.append("FAIL manifest: none found")
    else:
        for pkg in REQUIRED_PACKAGES:
            if pkg in manifest:
                print("  PASS manifest: '%s'" % pkg)
            else:
                failures.append("FAIL manifest: '%s' missing" % pkg)

    imgs = glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img")) \
        + glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img.gz"))
    if imgs:
        print("  PASS image: %s" % os.path.basename(imgs[0]))
    else:
        failures.append("FAIL image: no *combined-efi.img(.gz) artifact")

    print()
    if failures:
        print("Failures:")
        for f in failures:
            print("  " + f)
        print("\nRESULT: FAIL")
        sys.exit(1)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
