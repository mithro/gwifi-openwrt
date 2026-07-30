# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.firmware — firmware-version identifiers for the sheet."""
import hashlib

import pytest

from galeflash import const, firmware


def test_depthcharge_version_pairs_git_rev_and_elf_sha(tmp_path, monkeypatch):
    """depthcharge_version() = '<git> (elf:<sha12>)' over the real PAYLOAD_ELF."""
    elf = tmp_path / "depthcharge.elf"
    body = b"fake depthcharge payload bytes"
    elf.write_bytes(body)
    monkeypatch.setattr(const, "PAYLOAD_ELF", elf)
    monkeypatch.setattr(const, "DEPTHCHARGE_GIT", "abc1234")

    got = firmware.depthcharge_version()

    sha12 = hashlib.sha256(body).hexdigest()[:12]
    assert got == f"abc1234 (elf:{sha12})"


def test_depthcharge_version_fails_loud_when_payload_missing(tmp_path, monkeypatch):
    """A missing payload ELF must fail loud, not silently mislabel the sheet."""
    monkeypatch.setattr(const, "PAYLOAD_ELF", tmp_path / "nope.elf")
    with pytest.raises(FileNotFoundError):
        firmware.depthcharge_version()


def test_parse_ec_version_picks_ro_line():
    """parse_ec_version() extracts the RO firmware id from `ec version` output."""
    out = (
        "version\n"
        "Chip:    stm stm32f07x \n"
        "Board:   0\n"
        "RO:      gale_v1.1.5337-0115719\n"
        "RW:      gale_v1.1.5337-0115719\n"
        "Build:   gale_v1.1.5337-0115719\n"
        "> \n"
    )
    assert firmware.parse_ec_version(out) == "gale_v1.1.5337-0115719"


def test_parse_ec_version_fails_loud_on_garbage():
    with pytest.raises(ValueError):
        firmware.parse_ec_version("no version here\n> ")
