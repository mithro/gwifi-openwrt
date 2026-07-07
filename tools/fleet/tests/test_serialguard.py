# SPDX-License-Identifier: Apache-2.0
from galeflash import serialguard


def test_guard_blocks_mismatch():
    assert serialguard.ok("2831HW00VZA", "2831HW00VZA") is True
    assert serialguard.ok("2831HW00VZA", "1605HW000GM") is False


def test_guard_strips_whitespace():
    assert serialguard.ok("2831HW00VZA\n", "2831HW00VZA") is True
    assert serialguard.ok("  2831HW00VZA  ", "2831HW00VZA") is True


def test_external_tool_paths_exist():
    # Guards the TOOLS path-derivation: an off-by-one in parents[] would break
    # the no-cover hardware path invisibly in CI — this catches it at test time.
    assert serialguard.TOOLS.name == "tools"
    assert (serialguard.TOOLS / "flash_puck_usb.py").exists()
