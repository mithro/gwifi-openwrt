# SPDX-License-Identifier: Apache-2.0
"""FMAP-aware per-region byte diff between two SPI flash images.

Uses LEAF_FMAP (composites RW_SECTION_A/B excluded) so each byte is
compared exactly once and composite regions are never double-reported.
"""
from __future__ import annotations

from galeflash import const


def changed_regions(a: bytes, b: bytes) -> set[str]:
    """Return names of LEAF_FMAP regions that differ between *a* and *b*.

    Composites (RW_SECTION_A, RW_SECTION_B) are intentionally excluded
    from the comparison set — their leaves are compared individually.
    """
    changed: set[str] = set()
    for name, (off, size) in const.LEAF_FMAP.items():
        if a[off : off + size] != b[off : off + size]:
            changed.add(name)
    return changed


def print_diff(a: bytes, b: bytes) -> None:
    """Print a human-readable per-region diff summary to stdout.

    Output mirrors the style of tmp/diff_regions.py:
        region                       offset         size   diff_bytes
    Regions are sorted by offset; changed regions are flagged with <-- DIFF.
    """
    print(f"{'region':<24} {'offset':>12} {'size':>12} {'diff_bytes':>12}")
    for name, (off, size) in sorted(const.LEAF_FMAP.items(), key=lambda x: x[1][0]):
        delta = sum(1 for x, y in zip(a[off : off + size], b[off : off + size]) if x != y)
        tag = "  <-- DIFF" if delta else ""
        print(f"{name:<24} 0x{off:08x}   0x{size:08x}   {delta:>12}{tag}")
