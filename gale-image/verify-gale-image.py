#!/usr/bin/env python3
"""verify-gale-image.py — validate a built gale sysupgrade image.

Usage:
    python3 verify-gale-image.py [sysupgrade.bin]

Reads secret values from <script_dir>/gale-secrets.conf to verify the overlay
was rendered correctly. Never prints secret values.
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
DEFAULT_IMAGE_DIR = "/home/tim/local/gwifi/openwrt/bin/targets/ipq40xx/chromium"

REQUIRED_PACKAGES = [
    "openwisp-config",
    "kmod-batman-adv",
    "wpad-mesh-mbedtls",
    "usteer",
    "batctl",   # matched as substring to tolerate -default suffix
]


def parse_secrets(path):
    """Parse KEY="value" or KEY=value lines from a secrets file."""
    secrets = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
            if not m:
                continue
            key = m.group(1)
            val = m.group(2).strip()
            # Strip surrounding quotes
            if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                val = val[1:-1]
            elif len(val) >= 2 and val[0] == "'" and val[-1] == "'":
                val = val[1:-1]
            secrets[key] = val
    return secrets


def find_sysupgrade(image_dir):
    """Find the sysupgrade .bin for google_wifi in image_dir."""
    for name in os.listdir(image_dir):
        if "google_wifi" in name and "squashfs-sysupgrade" in name and name.endswith(".bin"):
            return os.path.join(image_dir, name)
    return None


def extract_rootfs_member(tar_path, dest_dir):
    """Extract the root/rootfs member from a sysupgrade tar to dest_dir.
    Returns the path to the extracted rootfs file, or None if not found.
    """
    with tarfile.open(tar_path, "r") as tf:
        members = tf.getnames()
        rootfs_member = None
        for m in members:
            if m.endswith("root") or m.endswith("rootfs"):
                rootfs_member = m
                break
        if rootfs_member is None:
            return None
        tf.extract(rootfs_member, dest_dir, set_attrs=False)
        return os.path.join(dest_dir, rootfs_member)


def unsquash(squashfs_file, dest_dir):
    """Run unsquashfs to extract squashfs_file into dest_dir/squashfs-root."""
    result = subprocess.run(
        ["unsquashfs", "-d", os.path.join(dest_dir, "squashfs-root"), squashfs_file],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"unsquashfs failed:\n{result.stderr}")
    return os.path.join(dest_dir, "squashfs-root")


def find_manifest(image_dir, tar_path):
    """Find a package manifest: first try control/manifest in the sysupgrade tar,
    then fall back to *.manifest files in the image dir."""
    # Try sysupgrade tar
    try:
        with tarfile.open(tar_path, "r") as tf:
            for member in tf.getnames():
                if "manifest" in member:
                    f = tf.extractfile(member)
                    if f:
                        return f.read().decode(errors="replace")
    except Exception:
        pass
    # Fall back to *.manifest in image dir
    for name in os.listdir(image_dir):
        if name.endswith(".manifest"):
            with open(os.path.join(image_dir, name)) as f:
                return f.read()
    return None


def check_no_placeholders(text, label):
    """Return True (ok) if no __TOKEN__ placeholders are found."""
    found = re.findall(r'__[A-Z_]+__', text)
    if found:
        return False, f"{label}: found unreplaced placeholders: {found}"
    return True, None


def run_assertions(rootfs_dir, secrets, image_dir, sysupgrade_path):
    """Run all assertions. Returns list of failure strings."""
    failures = []

    # 1) /etc/config/openwisp
    openwisp_path = os.path.join(rootfs_dir, "etc", "config", "openwisp")
    if not os.path.isfile(openwisp_path):
        failures.append("FAIL openwisp config: /etc/config/openwisp not found in rootfs")
    else:
        content = open(openwisp_path).read()
        openwisp_url = secrets.get("OPENWISP_URL", "")
        if openwisp_url and openwisp_url not in content:
            failures.append("FAIL openwisp config: OPENWISP_URL value not found")
        else:
            print("  PASS openwisp config: OPENWISP_URL present")
        ok, msg = check_no_placeholders(content, "openwisp config")
        if not ok:
            failures.append(f"FAIL {msg}")
        else:
            print("  PASS openwisp config: no placeholders")

    # 2) /etc/config/wireless
    wireless_path = os.path.join(rootfs_dir, "etc", "config", "wireless")
    if not os.path.isfile(wireless_path):
        failures.append("FAIL wireless config: /etc/config/wireless not found in rootfs")
    else:
        content = open(wireless_path).read()
        if "mode 'mesh'" not in content:
            failures.append("FAIL wireless config: 'mode mesh' stanza not found")
        else:
            print("  PASS wireless config: mesh mode present")
        mesh_id = secrets.get("MESH_ID", "")
        if mesh_id and mesh_id not in content:
            failures.append("FAIL wireless config: MESH_ID value not found")
        else:
            print("  PASS wireless config: MESH_ID present")
        ok, msg = check_no_placeholders(content, "wireless config")
        if not ok:
            failures.append(f"FAIL {msg}")
        else:
            print("  PASS wireless config: no placeholders")

    # 3) /etc/uci-defaults/99-gale-bootstrap exists and is executable
    bootstrap_path = os.path.join(rootfs_dir, "etc", "uci-defaults", "99-gale-bootstrap")
    if not os.path.isfile(bootstrap_path):
        failures.append("FAIL bootstrap: /etc/uci-defaults/99-gale-bootstrap not found in rootfs")
    else:
        mode = os.stat(bootstrap_path).st_mode
        if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            print("  PASS bootstrap: exists and is executable")
        else:
            failures.append(f"FAIL bootstrap: exists but is NOT executable (mode={oct(mode)})")

    # 4) Package manifest
    manifest_text = find_manifest(image_dir, sysupgrade_path)
    if manifest_text is None:
        failures.append("FAIL manifest: could not find package manifest")
    else:
        for pkg in REQUIRED_PACKAGES:
            if pkg in manifest_text:
                print(f"  PASS manifest: '{pkg}' found")
            else:
                failures.append(f"FAIL manifest: package '{pkg}' not found")

    return failures


def main():
    # Resolve sysupgrade image path
    if len(sys.argv) > 1:
        sysupgrade_path = sys.argv[1]
        image_dir = os.path.dirname(sysupgrade_path)
    else:
        image_dir = DEFAULT_IMAGE_DIR
        sysupgrade_path = find_sysupgrade(image_dir)
        if sysupgrade_path is None:
            print(f"ERROR: no *-google_wifi-squashfs-sysupgrade.bin found in {image_dir}")
            sys.exit(1)

    print(f"Image:   {sysupgrade_path}")
    print(f"Dir:     {image_dir}")

    # Load secrets
    secrets_path = os.path.join(SCRIPT_DIR, "gale-secrets.conf")
    if not os.path.isfile(secrets_path):
        print(f"ERROR: secrets file not found: {secrets_path}")
        print("       Copy gale-secrets.conf.example to gale-secrets.conf and fill it in.")
        sys.exit(1)
    secrets = parse_secrets(secrets_path)
    print(f"Secrets: loaded ({len(secrets)} keys)")

    # Check unsquashfs
    if shutil.which("unsquashfs") is None:
        print("ERROR: 'unsquashfs' not found in PATH (install squashfs-tools)")
        sys.exit(1)

    tmpdir = tempfile.mkdtemp(prefix="verify-gale-")
    try:
        # Extract rootfs from sysupgrade tar
        rootfs_squashfs = extract_rootfs_member(sysupgrade_path, tmpdir)
        if rootfs_squashfs is None:
            # Fallback: look for factory image rootfs in same dir
            factory_rootfs = None
            for name in os.listdir(image_dir):
                if "google_wifi" in name and "squashfs-factory" in name and name.endswith(".bin"):
                    candidate = os.path.join(image_dir, name)
                    extracted = extract_rootfs_member(candidate, tmpdir)
                    if extracted:
                        factory_rootfs = extracted
                        break
            if factory_rootfs is None:
                print("ERROR: could not extract rootfs member from sysupgrade (or factory) tar")
                sys.exit(1)
            rootfs_squashfs = factory_rootfs

        print(f"Rootfs squashfs: {rootfs_squashfs}")
        rootfs_dir = unsquash(rootfs_squashfs, tmpdir)
        print(f"Unsquashed to: {rootfs_dir}")
        print()

        failures = run_assertions(rootfs_dir, secrets, image_dir, sysupgrade_path)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print()
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  {f}")
        print()
        print("RESULT: FAIL")
        sys.exit(1)
    else:
        print("RESULT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
