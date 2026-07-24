#!/usr/bin/env python3
"""verify-gale-image.py — validate a built gale sysupgrade image.

Usage:
    python3 verify-gale-image.py [sysupgrade.bin]

Reads expected values from <script_dir>/gale-secrets.conf and asserts the
rendered overlay + package manifest match. Never prints secret values.
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "fleet-image"))
from verify_lib import parse_secrets

# Mirror build-gale-image.sh: derive the image dir from $OWRT (default below).
DEFAULT_IMAGE_DIR = os.path.join(
    os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt"),
    "bin/targets/ipq40xx/chromium",
)

REQUIRED_PACKAGES = [
    "openwisp-config",
    "openwisp-monitoring",
    "kmod-batman-adv",
    "wpad-mesh-mbedtls",
    "usteer",
    "batctl",   # matched as substring to tolerate the -default suffix
]


def find_image(image_dir, kind):
    """Find the google_wifi squashfs image of the given kind (sysupgrade/factory)."""
    if not os.path.isdir(image_dir):
        return None
    for name in os.listdir(image_dir):
        if ("google_wifi" in name and "squashfs-%s" % kind in name
                and name.endswith(".bin")):
            return os.path.join(image_dir, name)
    return None


def extract_rootfs_member(tar_path, dest_dir):
    """Extract the root/rootfs member from a sysupgrade tar. Returns its path."""
    with tarfile.open(tar_path, "r") as tf:
        rootfs_member = None
        for m in tf.getnames():
            if m.endswith("root") or m.endswith("rootfs"):
                rootfs_member = m
                break
        if rootfs_member is None:
            return None
        try:
            tf.extract(rootfs_member, dest_dir, set_attrs=False, filter="data")
        except TypeError:  # filter= added in Python 3.12
            tf.extract(rootfs_member, dest_dir, set_attrs=False)
        return os.path.join(dest_dir, rootfs_member)


def unsquash(squashfs_file, dest_dir):
    # Extract only the trees the assertions read (/etc + /usr/sbin) — this
    # avoids the device nodes under /dev that unsquashfs cannot create as
    # non-root.
    out = os.path.join(dest_dir, "squashfs-root")
    r = subprocess.run(["unsquashfs", "-d", out, squashfs_file,
                        "/etc", "/usr/sbin"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("unsquashfs failed:\n%s" % r.stderr)
    return out


def find_manifest(image_dir, tar_path):
    """Return package-manifest text: prefer the sysupgrade tar's control manifest,
    else a *.manifest in the image dir. Surfaces (not swallows) tar read errors."""
    try:
        with tarfile.open(tar_path, "r") as tf:
            for member in tf.getnames():
                base = member.rsplit("/", 1)[-1]
                if base == "manifest":
                    f = tf.extractfile(member)
                    if f:
                        return f.read().decode(errors="replace")
    except (tarfile.TarError, OSError) as e:
        sys.stderr.write("warning: could not read manifest from tar: %s\n" % e)
    for name in os.listdir(image_dir):
        if name.endswith(".manifest"):
            with open(os.path.join(image_dir, name)) as f:
                return f.read()
    return None


def check_no_placeholders(text, label, failures):
    found = re.findall(r'__[A-Z_]+__', text)
    if found:
        failures.append("FAIL %s: unreplaced placeholders: %s" % (label, found))
    else:
        print("  PASS %s: no placeholders" % label)


def check_value(content, secrets, key, label, failures):
    """Assert secrets[key]'s value appears in content. Fails (not skips) if the
    key is missing/empty from gale-secrets.conf. Never prints the value."""
    val = secrets.get(key)
    if not val:
        failures.append("FAIL %s: expected key %s missing/empty in gale-secrets.conf"
                        % (label, key))
    elif val not in content:
        failures.append("FAIL %s: %s value not present in rendered config"
                        % (label, key))
    else:
        print("  PASS %s: %s rendered" % (label, key))


def run_assertions(rootfs_dir, secrets, image_dir, sysupgrade_path):
    failures = []

    # 1) /etc/config/openwisp — URL + the real shared_secret, no placeholders.
    openwisp_path = os.path.join(rootfs_dir, "etc", "config", "openwisp")
    if not os.path.isfile(openwisp_path):
        failures.append("FAIL openwisp: /etc/config/openwisp not found")
    else:
        content = open(openwisp_path).read()
        check_value(content, secrets, "OPENWISP_URL", "openwisp", failures)
        check_value(content, secrets, "OPENWISP_SHARED_SECRET", "openwisp", failures)
        check_no_placeholders(content, "openwisp", failures)

    # 2) /etc/config/wireless — the image ships NO wireless config at all:
    # radios + APs are delivered by OpenWISP after the agent registers.
    wireless_path = os.path.join(rootfs_dir, "etc", "config", "wireless")
    if os.path.isfile(wireless_path):
        failures.append("FAIL wireless: /etc/config/wireless present — the "
                        "image must ship no wireless config (wisp-managed)")
    else:
        print("  PASS wireless: no baked wireless config")

    # 2a) bootstrap uses the case-marking port names.
    bs_path = os.path.join(rootfs_dir, "etc", "uci-defaults", "99-gale-bootstrap")
    if os.path.isfile(bs_path) and "eth-black" in open(bs_path).read():
        print("  PASS bootstrap: eth-black trunk port")
    else:
        failures.append("FAIL bootstrap: eth-black trunk port not found")

    # 2b) /usr/sbin/gale-mesh-bootstrap — the preserved mesh profile:
    # executable, mesh mode + real MESH_ID + SAE key rendered.
    meshboot = os.path.join(rootfs_dir, "usr", "sbin", "gale-mesh-bootstrap")
    if not os.path.isfile(meshboot):
        failures.append("FAIL mesh-bootstrap: gale-mesh-bootstrap not found")
    else:
        if os.stat(meshboot).st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS mesh-bootstrap: present and executable")
        else:
            failures.append("FAIL mesh-bootstrap: present but not executable")
        content = open(meshboot).read()
        if "mode='mesh'" in content or "mode 'mesh'" in content:
            print("  PASS mesh-bootstrap: mesh mode present")
        else:
            failures.append("FAIL mesh-bootstrap: mesh mode not found")
        check_value(content, secrets, "MESH_ID", "mesh-bootstrap", failures)
        check_value(content, secrets, "MESH_SAE_KEY", "mesh-bootstrap", failures)
        check_no_placeholders(content, "mesh-bootstrap", failures)

    # 3) /etc/uci-defaults/99-gale-bootstrap exists and is executable.
    bootstrap = os.path.join(rootfs_dir, "etc", "uci-defaults", "99-gale-bootstrap")
    if not os.path.isfile(bootstrap):
        failures.append("FAIL bootstrap: 99-gale-bootstrap not found")
    elif os.stat(bootstrap).st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        print("  PASS bootstrap: present and executable")
    else:
        failures.append("FAIL bootstrap: present but not executable")

    # 4) Package manifest lists the required packages.
    manifest = find_manifest(image_dir, sysupgrade_path)
    if manifest is None:
        failures.append("FAIL manifest: no package manifest found")
    else:
        for pkg in REQUIRED_PACKAGES:
            if pkg in manifest:
                print("  PASS manifest: '%s' present" % pkg)
            else:
                failures.append("FAIL manifest: package '%s' not found" % pkg)

    return failures


def main():
    if len(sys.argv) > 1:
        sysupgrade_path = sys.argv[1]
        image_dir = os.path.dirname(os.path.abspath(sysupgrade_path))
    else:
        image_dir = DEFAULT_IMAGE_DIR
        sysupgrade_path = find_image(image_dir, "sysupgrade")
        if sysupgrade_path is None:
            sys.exit("ERROR: no *-google_wifi-squashfs-sysupgrade.bin in %s" % image_dir)

    print("Image:   %s" % sysupgrade_path)

    secrets_path = os.path.join(SCRIPT_DIR, "gale-secrets.conf")
    if not os.path.isfile(secrets_path):
        sys.exit("ERROR: secrets file not found: %s (copy from .example)" % secrets_path)
    secrets = parse_secrets(secrets_path)
    print("Secrets: loaded (%d keys)" % len(secrets))

    if shutil.which("unsquashfs") is None:
        sys.exit("ERROR: 'unsquashfs' not in PATH (install squashfs-tools)")

    tmpdir = tempfile.mkdtemp(prefix="verify-gale-")
    try:
        rootfs = extract_rootfs_member(sysupgrade_path, tmpdir)
        if rootfs is None:
            factory = find_image(image_dir, "factory")
            if factory:
                rootfs = extract_rootfs_member(factory, tmpdir)
        if rootfs is None:
            sys.exit("ERROR: could not extract a rootfs member from the image tar")
        rootfs_dir = unsquash(rootfs, tmpdir)
        print("Rootfs:  unsquashed\n")
        failures = run_assertions(rootfs_dir, secrets, image_dir, sysupgrade_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print()
    if failures:
        print("Failures:")
        for f in failures:
            print("  %s" % f)
        print("\nRESULT: FAIL")
        sys.exit(1)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
