# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.fmapdiff — per-region image diff."""
from galeflash import fmapdiff, const


def test_diff_detects_only_mutated_leaf(stock_g4):
    a = stock_g4
    b = bytearray(a)
    off, _ = const.FMAP["FW_MAIN_A"]
    b[off] ^= 0xFF
    changed = fmapdiff.changed_regions(bytes(a), bytes(b))
    assert "FW_MAIN_A" in changed
    assert "RW_SECTION_A" not in changed          # composite excluded by design
    assert "RO_VPD" not in changed and "GBB" not in changed
