# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.imagebuild — combined dev-key TFTP-first SPI builder."""
import subprocess
from pathlib import Path

import pytest

from galeflash import imagebuild, fmapdiff, const


def _assert_invariants(src: bytes, out: Path):
    # (a) offline vboot verify passes
    subprocess.run([str(const.FUTILITY), "verify", str(out)], check=True)
    # (b) only allowed leaf regions changed; per-device VPD untouched
    changed = fmapdiff.changed_regions(src, out.read_bytes())
    assert changed <= const.ALLOWED_CHANGED
    assert "RO_VPD" not in changed and "RW_VPD" not in changed
    # (c) both slots carry the identical payload body
    a0, aL = const.FMAP["FW_MAIN_A"]
    b0, bL = const.FMAP["FW_MAIN_B"]
    buf = out.read_bytes()
    assert buf[a0:a0 + aL] == buf[b0:b0 + bL]


def test_build_from_g4(stock_g4, tmp_path):
    live = tmp_path / "live.bin"
    live.write_bytes(stock_g4)
    out = tmp_path / "out.bin"
    imagebuild.build(live, out)
    _assert_invariants(stock_g4, out)


def test_build_from_prerekey_live(prerekey_live, tmp_path):
    # A DIFFERENT unit's live dump — proves the builder is per-puck-generic,
    # not G4-specific. Same (a)(b)(c) invariants must hold.
    live = tmp_path / "live.bin"
    live.write_bytes(prerekey_live)
    out = tmp_path / "out.bin"
    imagebuild.build(live, out)
    _assert_invariants(prerekey_live, out)


def test_build_rejects_live_equals_out(tmp_path):
    # Aliasing live==out would re-read the modified output as the "original" at
    # the diff-gate, silently defeating VPD/ALLOWED_CHANGED protection. Guard it.
    p = tmp_path / "same.bin"
    p.write_bytes(b"\x00" * 8)
    with pytest.raises(ValueError):
        imagebuild.build(p, p)
