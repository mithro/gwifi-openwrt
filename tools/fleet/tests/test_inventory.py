# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.inventory — flash bookkeeping helper."""
import hashlib

import pytest

from galeflash.inventory import bookkeeping
from galeflash.sheetmap import FIELD_TO_HEADER


def _call(tmp_path, **overrides):
    """Invoke bookkeeping() with valid defaults; override as needed."""
    image = overrides.pop("image", None) or (tmp_path / "fleet.bin")
    if not image.exists():
        image.write_bytes(b"built-image-bytes")
    backup = overrides.pop("backup", None) or (tmp_path / "pre-flash.bin")
    if not backup.exists():
        backup.write_bytes(b"captured-stock-firmware-bytes")
    kwargs = dict(
        ec_version="gale_v1.1.5337-0115719",
        rw_fwid="Google_Gale.8281.47.0",
        depthcharge_version="c02e0cd (elf:0c668f128926)",
        capture_archive="big-storage.welland.mithis.com:/backups/machines/gwifi/cap.bin",
        image_archive="big-storage.welland.mithis.com:/backups/machines/gwifi/img.bin",
    )
    kwargs.update(overrides)
    return bookkeeping(image, backup, "2026-07-07", "flashed+boot-verified", **kwargs)


def test_backup_sha256_is_over_the_capture_file(tmp_path):
    """backup_sha256 hashes the pre-flash CAPTURE, not the built image."""
    backup = tmp_path / "pre-flash.bin"
    content = b"captured-stock-firmware-bytes-unique"
    backup.write_bytes(content)
    r = _call(tmp_path, backup=backup)
    assert r["backup_sha256"] == hashlib.sha256(content).hexdigest()


def test_image_sha256_is_over_the_built_image(tmp_path):
    image = tmp_path / "fleet.bin"
    content = b"the-exact-dev-key-image-flashed"
    image.write_bytes(content)
    r = _call(tmp_path, image=image)
    assert r["image_sha256"] == hashlib.sha256(content).hexdigest()


def test_backup_path_records_the_offsite_archive(tmp_path):
    """The 'Backup' field is the big-storage archive path, not the local file."""
    r = _call(tmp_path)
    assert r["backup_path"].startswith("big-storage.welland.mithis.com:")
    assert r["image_archive"].startswith("big-storage.welland.mithis.com:")


def test_firmware_fields_passed_through(tmp_path):
    r = _call(tmp_path)
    assert r["ec_version"] == "gale_v1.1.5337-0115719"
    assert r["rw_fwid"] == "Google_Gale.8281.47.0"
    assert r["depthcharge_version"] == "c02e0cd (elf:0c668f128926)"


def test_date_and_status(tmp_path):
    r = _call(tmp_path)
    assert r["flash_date"] == "2026-07-07"
    assert r["flash_status"] == "flashed+boot-verified"


def test_bookkeeping_keys_are_subset_of_sheetmap(tmp_path):
    """Every producer key must map to a sheet column (producer/consumer agree)."""
    r = _call(tmp_path)
    orphans = set(r.keys()) - set(FIELD_TO_HEADER.keys())
    assert not orphans, f"bookkeeping() keys not in FIELD_TO_HEADER: {orphans}"
