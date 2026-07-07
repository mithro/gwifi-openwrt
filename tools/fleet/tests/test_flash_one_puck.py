# SPDX-License-Identifier: Apache-2.0
"""CLI wiring tests for flash_one_puck.py — no hardware required.

All hardware seams (_backup_spi, _flash_image, _verify_boot) and the build
step (imagebuild.build) are monkeypatched so main() wiring runs in-process.
identity.from_dump is patched via the orchestrator module reference so no
real SPI dump or futility binary is needed.
"""
import pytest

import flash_one_puck
import galeflash.imagebuild as imagebuild
import galeflash.orchestrator as orchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STOCK_FALSE_IDV = {
    "serial_number": "SN-TEST-01",
    "mlb_serial_number": "MLB-TEST-01",
    "region": "US",
    "ethernet_mac0": "AABBCCDDEEFF",
    "ethernet_mac1": "AABBCCDDEEF0",
    "model_name": "AC1304",
    "hwid": "GALE TEST",
    "ro_frid": "google_gale.test",
    "is_stock": False,  # already dev-keyed → refuse without --rekeyed-ok
}

_COMMON_ARGV = [
    "--serial-hint", "SN-TEST-01",
    "--date", "2026-06-30",
]


def _patch_hw(monkeypatch, tmp_path, verify_calls=None, sheet_calls=None):
    """Patch all hardware/build seams; return (build_calls, flash_calls) recorders."""
    build_calls = []
    flash_calls = []

    monkeypatch.setattr(orchestrator.identity, "from_dump", lambda p: dict(_STOCK_FALSE_IDV))
    monkeypatch.setattr(flash_one_puck, "_backup_spi", lambda backup: None)
    monkeypatch.setattr(
        flash_one_puck, "_verify_boot",
        lambda log_path: None if verify_calls is None else verify_calls.append(log_path))
    monkeypatch.setattr(
        flash_one_puck, "_sync_sheet",
        lambda inv_dir: None if sheet_calls is None else sheet_calls.append(inv_dir))

    def fake_build(live, out):
        # Create the output file so inventory.bookkeeping() can hash it.
        out.write_bytes(b"fake-firmware-for-test")
        build_calls.append((live, out))

    def fake_flash(img, serial):
        flash_calls.append((img, serial))

    monkeypatch.setattr(imagebuild, "build", fake_build)
    monkeypatch.setattr(flash_one_puck, "_flash_image", fake_flash)

    return build_calls, flash_calls


# ---------------------------------------------------------------------------
# Refuse-gate: is_stock=False without --rekeyed-ok
# ---------------------------------------------------------------------------

def test_refuse_gate_raises_system_exit(tmp_path, monkeypatch):
    """is_stock=False without --rekeyed-ok → SystemExit non-zero."""
    build_calls, flash_calls = _patch_hw(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path)])

    assert exc_info.value.code not in (None, 0)


def test_refuse_gate_build_not_called(tmp_path, monkeypatch):
    """is_stock=False without --rekeyed-ok → imagebuild.build must not be called."""
    build_calls, flash_calls = _patch_hw(monkeypatch, tmp_path)

    with pytest.raises(SystemExit):
        flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path)])

    assert build_calls == [], f"build should not run when refused, got: {build_calls}"


def test_refuse_gate_flash_not_called(tmp_path, monkeypatch):
    """is_stock=False without --rekeyed-ok → _flash_image must not be called."""
    build_calls, flash_calls = _patch_hw(monkeypatch, tmp_path)

    with pytest.raises(SystemExit):
        flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path)])

    assert flash_calls == [], f"flash should not run when refused, got: {flash_calls}"


# ---------------------------------------------------------------------------
# Proceed: --rekeyed-ok overrides the refuse gate
# ---------------------------------------------------------------------------

def test_rekeyed_ok_build_is_called(tmp_path, monkeypatch):
    """is_stock=False with --rekeyed-ok → imagebuild.build is called exactly once."""
    build_calls, flash_calls = _patch_hw(monkeypatch, tmp_path)

    flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok"])

    assert len(build_calls) == 1, f"Expected 1 build call, got: {build_calls}"


def test_rekeyed_ok_flash_is_called(tmp_path, monkeypatch):
    """is_stock=False with --rekeyed-ok → _flash_image is called exactly once."""
    build_calls, flash_calls = _patch_hw(monkeypatch, tmp_path)

    flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok"])

    assert len(flash_calls) == 1, f"Expected 1 flash call, got: {flash_calls}"


def test_rekeyed_ok_flash_called_with_correct_serial(tmp_path, monkeypatch):
    """_flash_image receives the serial from the identity dict, not the hint."""
    build_calls, flash_calls = _patch_hw(monkeypatch, tmp_path)

    flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok"])

    _, serial = flash_calls[0]
    assert serial == "SN-TEST-01"


# ---------------------------------------------------------------------------
# Boot verification wiring
# ---------------------------------------------------------------------------

def test_verify_boot_called_with_log_under_out_dir(tmp_path, monkeypatch):
    """A successful flash triggers _verify_boot with a log path in out-dir/logs."""
    verify_calls = []
    _patch_hw(monkeypatch, tmp_path, verify_calls)

    flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok"])

    assert len(verify_calls) == 1
    assert verify_calls[0].parent == tmp_path / "logs"
    assert "SN-TEST-01" in verify_calls[0].name


def test_skip_verify_skips_boot_verification(tmp_path, monkeypatch):
    """--skip-verify leaves the puck parked and never calls _verify_boot."""
    verify_calls = []
    _patch_hw(monkeypatch, tmp_path, verify_calls)

    flash_one_puck.main(
        _COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok", "--skip-verify"])

    assert verify_calls == []


def test_verify_boot_upgrades_inventory_status(tmp_path, monkeypatch):
    """After verification the inventory status becomes flashed+boot-verified."""
    import json
    _patch_hw(monkeypatch, tmp_path, [])

    flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok"])

    inv = json.loads((tmp_path / "inventory" / "SN-TEST-01.json").read_text())
    assert inv["flash_status"] == "flashed+boot-verified"


# ---------------------------------------------------------------------------
# Sheet-sync wiring (Step 6)
# ---------------------------------------------------------------------------

def test_sheet_synced_by_default(tmp_path, monkeypatch):
    """A successful flow ends by syncing the inventory dir to the sheet."""
    sheet_calls = []
    _patch_hw(monkeypatch, tmp_path, sheet_calls=sheet_calls)

    flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok"])

    assert len(sheet_calls) == 1
    assert sheet_calls[0] == tmp_path / "inventory"


def test_no_sheet_flag_skips_sync(tmp_path, monkeypatch):
    """--no-sheet suppresses the sheet sync entirely."""
    sheet_calls = []
    _patch_hw(monkeypatch, tmp_path, sheet_calls=sheet_calls)

    flash_one_puck.main(
        _COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok", "--no-sheet"])

    assert sheet_calls == []


def test_sheet_synced_after_inventory_written(tmp_path, monkeypatch):
    """Sheet sync must see the FINAL inventory (status flashed+boot-verified)
    already on disk — i.e. it runs after the bookkeeping write."""
    import json
    seen_status = {}

    def spy_sync(inv_dir):
        inv = json.loads((inv_dir / "SN-TEST-01.json").read_text())
        seen_status["status"] = inv["flash_status"]

    _patch_hw(monkeypatch, tmp_path, [])
    monkeypatch.setattr(flash_one_puck, "_sync_sheet", spy_sync)

    flash_one_puck.main(_COMMON_ARGV + ["--out-dir", str(tmp_path), "--rekeyed-ok"])

    assert seen_status["status"] == "flashed+boot-verified"
