# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.inventory — pure flash bookkeeping helper."""
import hashlib

import pytest

from galeflash.inventory import bookkeeping
from galeflash.sheetmap import FIELD_TO_HEADER


def test_bookkeeping_returns_correct_sha256(tmp_path):
    """bookkeeping() computes SHA-256 over the image file bytes."""
    image = tmp_path / "fleet.bin"
    content = b"fake firmware image bytes for sha256 test"
    image.write_bytes(content)
    backup = tmp_path / "pre-flash.bin"

    result = bookkeeping(image, backup, "2026-06-30", "flashed")

    expected_sha256 = hashlib.sha256(content).hexdigest()
    assert result["image_sha256"] == expected_sha256


def test_bookkeeping_returns_all_four_fields(tmp_path):
    """bookkeeping() returns backup_path, image_sha256, flash_date, flash_status."""
    image = tmp_path / "fleet.bin"
    image.write_bytes(b"x")
    backup = tmp_path / "pre-flash.bin"

    result = bookkeeping(image, backup, "2026-06-30", "flashed")

    assert result["backup_path"] == str(backup)
    assert result["flash_date"] == "2026-06-30"
    assert result["flash_status"] == "flashed"
    assert "image_sha256" in result


def test_bookkeeping_keys_are_subset_of_sheetmap(tmp_path):
    """Producer keys must be a subset of FIELD_TO_HEADER so consumer agrees."""
    image = tmp_path / "fleet.bin"
    image.write_bytes(b"x")
    backup = tmp_path / "pre-flash.bin"

    result = bookkeeping(image, backup, "2026-06-30", "flashed")

    orphans = set(result.keys()) - set(FIELD_TO_HEADER.keys())
    assert not orphans, (
        f"bookkeeping() keys not in FIELD_TO_HEADER (producer/consumer mismatch): {orphans}"
    )
