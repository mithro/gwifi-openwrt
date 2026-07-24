#!/usr/bin/env python3
"""Upload an OpenWrt sysupgrade image to the OpenWISP firmware-upgrader via the
REST API: ensures a Category + Build exist, then uploads the artifact as a
FirmwareImage with the given board image-type key. Re-runnable: reuses an
existing Category/Build and skips an image type already present on the Build.

The image-type key must already be registered (stock board map or
OPENWISP_CUSTOM_OPENWRT_IMAGES in playbook.yml §9). Never prints secrets.

Usage:
  uv run --with requests python openwisp/upload-firmware.py \
    --image /path/openwrt-ipq40xx-chromium-google_wifi-squashfs-sysupgrade.bin \
    --type ipq40xx-chromium-google_wifi-squashfs-sysupgrade.bin \
    --version 25.12.4-openwisp-2026-06-06 \
    --credentials /home/tim/local/gwifi/openwisp/.admin-credentials
"""
import argparse
import os
import sys

import requests


def load_creds(path):
    d = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def listing(resp):
    """Normalize a DRF list response (paginated dict or bare list)."""
    j = resp.json()
    return j.get("results", j) if isinstance(j, dict) else j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="path to the *-sysupgrade.bin")
    ap.add_argument("--type", required=True, help="firmware image-type key (board)")
    ap.add_argument("--version", required=True, help="Build version string")
    ap.add_argument("--category", default="Google WiFi (gale)")
    ap.add_argument("--os", default="", help="Build os string (for auto-matching)")
    ap.add_argument("--org", default="default", help="organization slug")
    ap.add_argument("--credentials",
                    default=os.environ.get("OPENWISP_ADMIN_CREDENTIALS",
                                           ".admin-credentials"))
    a = ap.parse_args()

    if not os.path.isfile(a.image):
        sys.exit("image not found: %s" % a.image)
    creds = load_creds(a.credentials)
    base = creds.get("url", "https://wisp.welland.mithis.com/admin").rsplit("/admin", 1)[0]
    api = base + "/api/v1"

    s = requests.Session()
    r = s.post(api + "/users/token/",
               data={"username": creds["username"], "password": creds["password"]},
               timeout=30)
    if r.status_code != 200:
        sys.exit("token request failed %d: %s" % (r.status_code, r.text[:300]))
    s.headers["Authorization"] = "Bearer " + r.json()["token"]

    # organization uuid
    org = next((o for o in listing(s.get(api + "/users/organization/", timeout=30))
                if o.get("slug") == a.org), None)
    if not org:
        sys.exit("organization slug %r not found" % a.org)
    org_id = org["id"]
    print("org %s -> %s" % (a.org, org_id))

    # category (find or create). NOTE: the list endpoint's ?organization= filter
    # returns empty (it does not match), so fetch unfiltered and match
    # client-side on the returned name + organization fields.
    cats = listing(s.get(api + "/firmware-upgrader/category/", timeout=30))
    cat = next((c for c in cats if c.get("name") == a.category
                and c.get("organization") == org_id), None)
    if cat:
        cat_id = cat["id"]
        print("category exists -> %s" % cat_id)
    else:
        r = s.post(api + "/firmware-upgrader/category/",
                   data={"name": a.category, "organization": org_id}, timeout=30)
        if r.status_code not in (200, 201):
            sys.exit("category create failed %d: %s" % (r.status_code, r.text[:300]))
        cat_id = r.json()["id"]
        print("category created -> %s" % cat_id)

    # build (find or create). Same filter caveat as category: fetch unfiltered
    # and match client-side on the returned category + version fields.
    builds = listing(s.get(api + "/firmware-upgrader/build/", timeout=30))
    build = next((b for b in builds if b.get("category") == cat_id
                  and str(b.get("version")) == a.version), None)
    if build:
        build_id = build["id"]
        print("build exists -> %s (version %s)" % (build_id, a.version))
    else:
        payload = {"category": cat_id, "version": a.version}
        if a.os:
            payload["os"] = a.os
        r = s.post(api + "/firmware-upgrader/build/", data=payload, timeout=30)
        if r.status_code not in (200, 201):
            sys.exit("build create failed %d: %s" % (r.status_code, r.text[:300]))
        build_id = r.json()["id"]
        print("build created -> %s (version %s)" % (build_id, a.version))

    # image (skip if this type already present on the build)
    imgs = listing(s.get(api + "/firmware-upgrader/build/%s/image/" % build_id,
                         timeout=30))
    existing = next((i for i in imgs if i.get("type") == a.type), None)
    if existing:
        print("image type already present -> %s (file %s)"
              % (existing.get("id"), existing.get("file")))
        print("RESULT: OK (no upload needed)")
        return

    fn = os.path.basename(a.image)
    with open(a.image, "rb") as fh:
        r = s.post(api + "/firmware-upgrader/build/%s/image/" % build_id,
                   data={"type": a.type},
                   files={"file": (fn, fh, "application/octet-stream")},
                   timeout=180)
    if r.status_code not in (200, 201):
        sys.exit("image upload failed %d: %s" % (r.status_code, r.text[:500]))
    img = r.json()
    print("image uploaded -> %s  type=%s  file=%s"
          % (img.get("id"), img.get("type"), img.get("file")))
    print("RESULT: OK  category=%r build=%s version=%s" % (a.category, build_id, a.version))


if __name__ == "__main__":
    main()
