#!/usr/bin/env python3
"""verify-om2p-image.py — validate the built OM2P images.

Checks, against the shared rootfs (the *-rootfs.tar.gz emitted by
CONFIG_TARGET_ROOTFS_TARGZ, or the build staging root-ath79 dir as fallback):
  - /etc/config/openwisp        : real URL + shared_secret, no placeholders
  - /etc/uci-defaults/99-om2p-bootstrap : executable; real MESH_ID + SAE key;
                                  mesh mode; board_name port selection; no placeholders
  - package manifest            : required packages present
  - each *-openmesh_om2p-*-squashfs-sysupgrade.bin <= 7168 KiB (the fit gate)

Reads expected values from <repo-root>/fleet-secrets.conf. Never prints secrets.

Usage: uv run python om2p-image/verify-om2p-image.py
"""
import glob
import os
import re
import stat
import sys
import tarfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/ath79/generic")
FLEET_SECRETS = os.environ.get("FLEET_SECRETS",
                               os.path.join(SCRIPT_DIR, "..", "fleet-secrets.conf"))
IMAGE_SIZE_LIMIT = 7168 * 1024  # design C1 (IMAGE_SIZE := 7168k)

REQUIRED_PACKAGES = ["openwisp-config", "openwisp-monitoring", "kmod-batman-adv",
                     "wpad-mesh-mbedtls", "usteer", "batctl"]
PROFILES = ["openmesh_om2p-lc", "openmesh_om2p-v1",
            "openmesh_om2p-v2", "openmesh_om2p-v4"]


def parse_secrets(path):
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
            if not m:
                continue
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def read_etc_files(image_dir):
    """Return ({relpath: text}, {relpath: mode}, source-label) for the two overlay
    files, from the rootfs tarball (preferred) or the build staging dir (fallback)."""
    want = ("etc/config/openwisp", "etc/uci-defaults/99-om2p-bootstrap")
    tarballs = glob.glob(os.path.join(image_dir, "*rootfs.tar.gz"))
    if tarballs:
        files, modes = {}, {}
        with tarfile.open(tarballs[0], "r:gz") as tf:
            for m in tf.getmembers():
                rel = m.name.lstrip("./")
                if rel in want and m.isfile():
                    files[rel] = tf.extractfile(m).read().decode(errors="replace")
                    modes[rel] = m.mode
        return files, modes, "tarball %s" % os.path.basename(tarballs[0])
    roots = glob.glob(os.path.join(OWRT, "build_dir", "target-*", "root-ath79"))
    if roots:
        files, modes = {}, {}
        for rel in want:
            p = os.path.join(roots[0], rel)
            if os.path.isfile(p):
                files[rel] = open(p, errors="replace").read()
                modes[rel] = os.stat(p).st_mode
        return files, modes, "staging %s" % roots[0]
    return None, None, None


def find_manifest(image_dir):
    for name in sorted(os.listdir(image_dir)):
        if name.endswith(".manifest"):
            return open(os.path.join(image_dir, name)).read()
    return None


def main():
    if not os.path.isdir(IMAGE_DIR):
        sys.exit("ERROR: image dir not found: %s (build first)" % IMAGE_DIR)
    if not os.path.isfile(FLEET_SECRETS):
        sys.exit("ERROR: secrets not found: %s" % FLEET_SECRETS)
    secrets = parse_secrets(FLEET_SECRETS)
    failures = []

    files, modes, src = read_etc_files(IMAGE_DIR)
    if not files:
        sys.exit("ERROR: no rootfs tarball or staging dir found; build with "
                 "CONFIG_TARGET_ROOTFS_TARGZ=y (in om2p.config)")
    print("Rootfs source: %s\n" % src)

    def check_value(content, key, label):
        v = secrets.get(key)
        if not v:
            failures.append("FAIL %s: %s missing/empty in fleet-secrets.conf" % (label, key))
        elif v not in content:
            failures.append("FAIL %s: %s value not present" % (label, key))
        else:
            print("  PASS %s: %s rendered" % (label, key))

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
        check_no_ph(ow, "openwisp")

    bs = files.get("etc/uci-defaults/99-om2p-bootstrap")
    if bs is None:
        failures.append("FAIL bootstrap: not in rootfs")
    else:
        if modes.get("etc/uci-defaults/99-om2p-bootstrap", 0) & (
                stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS bootstrap: executable")
        else:
            failures.append("FAIL bootstrap: not executable")
        check_value(bs, "MESH_ID", "bootstrap")
        check_value(bs, "MESH_SAE_KEY", "bootstrap")
        for needle, label in (("mode 'mesh'", "mesh mode"), ("board_name", "port selection")):
            if needle in bs:
                print("  PASS bootstrap: %s present" % label)
            else:
                failures.append("FAIL bootstrap: %s ('%s') missing" % (label, needle))
        check_no_ph(bs, "bootstrap")

    manifest = find_manifest(IMAGE_DIR)
    if manifest is None:
        failures.append("FAIL manifest: none found")
    else:
        for pkg in REQUIRED_PACKAGES:
            if pkg in manifest:
                print("  PASS manifest: '%s'" % pkg)
            else:
                failures.append("FAIL manifest: '%s' missing" % pkg)

    print()
    for prof in PROFILES:
        hits = glob.glob(os.path.join(IMAGE_DIR, "*%s-squashfs-sysupgrade.bin" % prof))
        if not hits:
            failures.append("FAIL fit: no sysupgrade image for %s" % prof)
            continue
        size = os.path.getsize(hits[0])
        if size <= IMAGE_SIZE_LIMIT:
            print("  PASS fit: %s = %d B (<= %d)" % (prof, size, IMAGE_SIZE_LIMIT))
        else:
            failures.append("FAIL fit: %s = %d B EXCEEDS %d (trim ladder, design "
                            "section 10)" % (prof, size, IMAGE_SIZE_LIMIT))

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
