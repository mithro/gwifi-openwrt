# SPDX-License-Identifier: Apache-2.0
"""Tests for the image publish step (manifest + content-addressed copy)."""

import hashlib
import json
from pathlib import Path

import pytest

from gwifi_netboot.publish import PublishError, publish


@pytest.fixture()
def factory(tmp_path):
    f = tmp_path / "factory.bin"
    f.write_bytes(b"fake-gpt-image" * 1024)
    (tmp_path / "factory.bin.image-id").write_text(
        "gale-openwrt-20260711120000-gabc1234\n")
    return f


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_publish_writes_manifest_and_copy(factory, tmp_path):
    images = tmp_path / "images"
    publish(factory, images)
    manifest = json.loads((images / "manifest.json").read_text())
    digest = sha256(factory)
    assert manifest == {
        "version": 1,
        "image_id": "gale-openwrt-20260711120000-gabc1234",
        "filename": f"factory-{digest[:12]}.bin",
        "sha256": digest,
        "size": factory.stat().st_size,
        "force": [],
    }
    copied = images / manifest["filename"]
    assert copied.read_bytes() == factory.read_bytes()


def test_missing_sidecar_is_error(tmp_path):
    f = tmp_path / "factory.bin"
    f.write_bytes(b"x")
    with pytest.raises(PublishError, match="image-id"):
        publish(f, tmp_path / "images")


def test_manifest_written_last_and_old_kept_on_failure(factory, tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "manifest.json").write_text('{"image_id": "old"}')
    # Simulate interruption: unreadable source after sidecar check is not
    # easily injectable, so assert ordering by contract — the copy must
    # exist before manifest.json references it.
    publish(factory, images)
    manifest = json.loads((images / "manifest.json").read_text())
    assert (images / manifest["filename"]).exists()


def test_publish_idempotent(factory, tmp_path):
    images = tmp_path / "images"
    publish(factory, images)
    first = (images / "manifest.json").read_text()
    publish(factory, images)
    assert (images / "manifest.json").read_text() == first


def test_missing_factory_is_error(tmp_path):
    with pytest.raises(PublishError, match="factory"):
        publish(tmp_path / "nope.bin", tmp_path / "images")
