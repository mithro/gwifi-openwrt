#!/usr/bin/env python3
"""verify-tenvm-image.py — validate the built ten64 Wi-Fi VM image.

Checks, against the rootfs (the *-rootfs.tar.gz emitted by CONFIG_TARGET_ROOTFS_TARGZ,
or the build staging root-* dir as fallback):
  - /etc/config/openwisp   : real URL + shared_secret, no placeholders
  - /etc/config/wireless   : mesh mode + real MESH_ID + SAE key, no placeholders
  - /etc/uci-defaults/99-tenvm-bootstrap : executable; eth0 trunk; cron line; no placeholders
  - /usr/sbin/gwifi-radio-setup, gwifi-backhaul-gate, hotplug hook : present + executable
  - package manifest       : required packages incl. ath11k/ath10k driver+firmware
  - a bootable combined-efi.img artifact exists

Reads expected values from <repo-root>/fleet-secrets.conf (or $FLEET_SECRETS). Never
prints secrets. Usage: uv run python tenvm-image/verify-tenvm-image.py
"""
import glob
import os
import re
import stat
import sys
import tarfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/armsr/armv8")
FLEET_SECRETS = os.environ.get(
    "FLEET_SECRETS", os.path.join(SCRIPT_DIR, "..", "fleet-secrets.conf"))

REQUIRED_PACKAGES = [
    "openwisp-config", "openwisp-monitoring", "kmod-batman-adv",
    "wpad-mesh-mbedtls", "usteer", "batctl-default",
    "kmod-ath11k-pci", "ath11k-firmware-qcn9074",
    "kmod-ath10k", "ath10k-firmware-qca9377",
]
OVERLAY_EXEC = [
    "etc/uci-defaults/99-tenvm-bootstrap",
    "usr/sbin/gwifi-radio-setup",
    "usr/sbin/gwifi-backhaul-gate",
    "etc/hotplug.d/net/30-gwifi-backhaul",
]


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


def read_rootfs(image_dir):
    """Return ({relpath: text}, {relpath: mode}, label) from the rootfs tarball
    (preferred) or the build staging root-* dir (fallback)."""
    want = tuple(["etc/config/openwisp", "etc/config/wireless",
                  "etc/uci-defaults/99-tenvm-bootstrap"] + OVERLAY_EXEC[1:])
    tarballs = glob.glob(os.path.join(image_dir, "*rootfs.tar.gz"))
    if tarballs:
        tarball = max(tarballs, key=os.path.getmtime)   # newest, in case a stale one lingers
        files, modes = {}, {}
        with tarfile.open(tarball, "r:gz") as tf:
            for m in tf.getmembers():
                rel = m.name.lstrip("./")
                if rel in want and m.isfile():
                    files[rel] = tf.extractfile(m).read().decode(errors="replace")
                    modes[rel] = m.mode
        return files, modes, "tarball %s" % os.path.basename(tarball)
    roots = glob.glob(os.path.join(OWRT, "build_dir", "target-*", "root-*"))
    if roots:
        files, modes = {}, {}
        for rel in want:
            p = os.path.join(roots[0], rel)
            if os.path.isfile(p):
                with open(p, errors="replace") as fh:
                    files[rel] = fh.read()
                modes[rel] = os.stat(p).st_mode
        return files, modes, "staging %s" % roots[0]
    return None, None, None


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

    files, modes, src = read_rootfs(IMAGE_DIR)
    if not files:
        sys.exit("ERROR: no rootfs tarball or staging dir found; build with "
                 "CONFIG_TARGET_ROOTFS_TARGZ=y (in tenvm.config)")
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

    wl = files.get("etc/config/wireless")
    if wl is None:
        failures.append("FAIL wireless: not in rootfs")
    else:
        if "mode 'mesh'" in wl or "mode='mesh'" in wl:
            print("  PASS wireless: mesh mode present")
        else:
            failures.append("FAIL wireless: mesh mode not found")
        check_value(wl, "MESH_ID", "wireless")
        check_value(wl, "MESH_SAE_KEY", "wireless")
        check_no_ph(wl, "wireless")

    bs = files.get("etc/uci-defaults/99-tenvm-bootstrap")
    if bs is None:
        failures.append("FAIL bootstrap: not in rootfs")
    else:
        if "UPLINK=eth0" in bs:
            print("  PASS bootstrap: eth0 trunk")
        else:
            failures.append("FAIL bootstrap: eth0 trunk uplink not found")
        if "gwifi-backhaul-gate --once" in bs:
            print("  PASS bootstrap: cron line installed")
        else:
            failures.append("FAIL bootstrap: cron-install snippet missing")
        check_no_ph(bs, "bootstrap")

    for rel in OVERLAY_EXEC:
        if rel not in files:
            failures.append("FAIL exec: %s missing from rootfs" % rel)
        elif modes.get(rel, 0) & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS exec: %s present and executable" % rel)
        else:
            failures.append("FAIL exec: %s present but not executable" % rel)

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
