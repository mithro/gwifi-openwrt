# SPDX-License-Identifier: Apache-2.0
from galeflash import flashplan


def test_write_order_is_ro_last():
    calls = flashplan.regions_in_order()
    names = [c[0] for c in calls]
    assert names == ["RW_SECTION_A", "RW_SECTION_B", "0x301000:0xdf000"]
    assert calls[-1][1] == ["--allow-ro"]      # ONLY the RO span gets --allow-ro
    assert all(c[1] == [] for c in calls[:-1])  # RW slots have no extra flags
