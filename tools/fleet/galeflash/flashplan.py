# SPDX-License-Identifier: Apache-2.0
"""Flash write order: RW regions first, RO span last.

Writing RO last means a partial failure leaves the puck in a stock-bootable
state (the stock GBB + RO_FRID remain intact until the very last step).
"""

from galeflash.const import GBB_ROFRID_SPAN


def regions_in_order() -> list[tuple[str, list[str]]]:
    """Return the ordered list of (region, extra_flags) pairs for flashing.

    RW slots are written first, then the GBB+RO_FRID span (with --allow-ro)
    last so a partial failure leaves the puck stock-bootable.

    Returns:
        List of (region_spec, extra_flags) tuples, where region_spec is either
        an FMAP region name or an "0xOFFSET:0xLEN" span string, and extra_flags
        is a list of additional CLI flags for raiden_write_region.py.
    """
    off, size = GBB_ROFRID_SPAN
    ro_span = f"{hex(off)}:{hex(size)}"
    return [
        ("RW_SECTION_A", []),
        ("RW_SECTION_B", []),
        (ro_span, ["--allow-ro"]),
    ]
