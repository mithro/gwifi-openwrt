"""fleet-image/verify_lib.py — checks shared by the image verifiers.

Import from a sibling image dir:
    sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "fleet-image"))
    from verify_lib import parse_secrets, check_no_placeholders, find_manifest, require_packages
"""
import glob
import os
import re

PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")


def parse_secrets(path):
    """KEY=VALUE lines -> dict (quotes stripped, comments/blank skipped)."""
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


def check_no_placeholders(text, label, failures):
    for m in sorted(set(PLACEHOLDER_RE.findall(text))):
        failures.append("%s: unrendered placeholder %s" % (label, m))


def find_manifest(image_dir):
    """Newest *.manifest under image_dir, or None."""
    manifests = glob.glob(os.path.join(image_dir, "*.manifest"))
    return max(manifests, key=os.path.getmtime) if manifests else None


def manifest_packages(path):
    """manifest 'name - version' lines -> set of package names."""
    pkgs = set()
    with open(path) as f:
        for line in f:
            name = line.split(" - ")[0].strip()
            if name:
                pkgs.add(name)
    return pkgs


def require_packages(manifest_path, required, failures):
    pkgs = manifest_packages(manifest_path)
    for want in required:
        if want not in pkgs:
            failures.append("manifest: missing required package %s" % want)
    return pkgs
