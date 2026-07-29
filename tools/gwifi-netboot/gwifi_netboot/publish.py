# SPDX-License-Identifier: Apache-2.0
"""Publish a gale factory image: content-addressed copy + manifest.json.

The image id comes from the ``<factory.bin>.image-id`` sidecar written by
the image build — the same id is baked into the image as
``/etc/gwifi-image-id``, so manifest and on-eMMC marker always match (the
installer's idempotence check compares them). A missing sidecar is an
error, never guessed around.

The manifest is written last (atomically), after the image copy exists —
an interrupted publish leaves the previous manifest intact and pointing
at a still-present image.

The manifest is a FLAT json object: the installer extracts fields with
busybox sed (no jq), so no field may contain nested objects and no field
other than the "force" MAC list may contain MAC-address text.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


class PublishError(Exception):
    """The factory image or its sidecar is missing/invalid."""


def publish(factory_bin: Path, images_dir: Path,
            image_id_file: Path | None = None,
            force: list[str] | None = None) -> dict:
    """Publish factory_bin into images_dir; returns the manifest dict."""
    factory_bin = Path(factory_bin)
    if not factory_bin.is_file():
        raise PublishError(f"factory image not found: {factory_bin}")

    sidecar = image_id_file or factory_bin.with_name(
        factory_bin.name + ".image-id")
    try:
        image_id = Path(sidecar).read_text().strip()
    except OSError as e:
        raise PublishError(
            f"image-id sidecar missing ({sidecar}): built without the "
            f"stamping build script?") from e
    if not image_id:
        raise PublishError(f"image-id sidecar {sidecar} is empty")

    data = factory_bin.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    filename = f"factory-{digest[:12]}.bin"

    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    target = images_dir / filename
    if not target.exists() or target.stat().st_size != len(data):
        tmp = target.with_name(target.name + ".partial")
        tmp.write_bytes(data)
        os.replace(tmp, target)

    manifest = {
        "version": 1,
        "image_id": image_id,
        "filename": filename,
        "sha256": digest,
        "size": len(data),
        "force": force or [],
    }
    fd, tmp_name = tempfile.mkstemp(dir=images_dir, prefix=".manifest.")
    with os.fdopen(fd, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_name, images_dir / "manifest.json")
    return manifest
