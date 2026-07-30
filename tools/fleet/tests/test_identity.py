# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys
from pathlib import Path

from galeflash import identity


def test_identity_from_g4(stock_g4, tmp_path):
    dump = tmp_path / "g4.bin"; dump.write_bytes(stock_g4)
    idv = identity.from_dump(dump)
    assert idv["serial_number"] == "2831HW00VZA"
    assert idv["ethernet_mac0"] == "44070B0187B4"
    assert idv["ro_frid"].lower().startswith("google_gale")
    assert idv["hwid"]                 # non-empty
    assert idv["is_stock"] is True     # GBB still has Google rootkey
    # privacy: the secret must NOT leak into the curated identity
    assert "stable_device_secret_DO_NOT_SHARE" not in idv
    assert "setup_psk" not in idv
    # exact allowlist: guards against silent narrowing or leakage of new keys
    assert set(idv.keys()) == {
        "serial_number", "mlb_serial_number", "region",
        "ethernet_mac0", "ethernet_mac1", "model_name",
        "hwid", "ro_frid", "is_stock",
    }


def test_cli_writes_inventory_json(stock_g4, tmp_path):
    """The CLI writes <serial_number>.json to --out DIR; secret must not appear."""
    dump = tmp_path / "g4.bin"
    dump.write_bytes(stock_g4)
    inv_dir = tmp_path / "inventory"

    cli = Path(__file__).parent.parent / "extract_identity.py"
    result = subprocess.run(
        [sys.executable, str(cli), str(dump), "--out", str(inv_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    # Inventory dir must have been created with one JSON file
    json_files = list(inv_dir.glob("*.json"))
    assert len(json_files) == 1, f"Expected 1 JSON, got: {json_files}"

    data = json.loads(json_files[0].read_text())

    # serial_number must round-trip and match the filename
    assert data["serial_number"] == "2831HW00VZA"
    assert json_files[0].name == "2831HW00VZA.json"

    # Sensitive keys must never enter the inventory JSON
    assert "stable_device_secret_DO_NOT_SHARE" not in data
    assert "setup_psk" not in data


def test_unverifiable_dump_raises_actionable_error(tmp_path, monkeypatch):
    """futility exiting non-zero (dump fails vboot verification — corrupt read
    or partially flashed puck) must surface as an actionable hard stop, and
    must never be silently treated as a parseable dump."""
    import pytest

    def fake_check_output(cmd, **kwargs):
        if "show" in cmd:
            # The failing call in the field: body verification of the dump.
            raise subprocess.CalledProcessError(1, cmd)
        return "hardware_id: GALE TEST\n"   # gbb_utility --get --hwid

    monkeypatch.setattr(identity.subprocess, "check_output", fake_check_output)
    dump = tmp_path / "corrupt.bin"
    dump.write_bytes(b"\x00" * 16)

    with pytest.raises(RuntimeError, match="does not vboot-verify"):
        identity.from_dump(dump)
