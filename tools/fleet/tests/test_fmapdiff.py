# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.fmapdiff — per-region image diff."""
from galeflash import fmapdiff, const


def test_diff_detects_only_mutated_leaf(stock_g4):
    a = stock_g4
    b = bytearray(a)
    off, _ = const.FMAP["FW_MAIN_A"]
    b[off] ^= 0xFF
    changed = fmapdiff.changed_regions(bytes(a), bytes(b))
    # exact set: the mutation is fully controlled, so only FW_MAIN_A may differ.
    # (composite RW_SECTION_A is excluded by design; no other leaf is touched.)
    assert changed == {"FW_MAIN_A"}
