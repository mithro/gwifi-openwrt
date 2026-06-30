# SPDX-License-Identifier: Apache-2.0
"""CLI wiring tests for flash_gale_fleet.py — no hardware required.

All hardware seams (_run, _park, serialguard.read_live_serial) are
monkeypatched so the entire main() wiring runs in-process.
"""
import pytest

import flash_gale_fleet
from galeflash import serialguard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image(tmp_path):
    """Create a small dummy image file that passes the exists() guard."""
    img = tmp_path / "fleet.bin"
    img.write_bytes(b"\x00" * 64)
    return img


# ---------------------------------------------------------------------------
# Mismatch case: serial guard blocks all writes
# ---------------------------------------------------------------------------

def test_serial_mismatch_raises_system_exit_nonzero(tmp_path, monkeypatch):
    """Mismatching serial → SystemExit with code != 0."""
    img = _make_image(tmp_path)

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "WRONG-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_park", lambda label="re-park AP": None)
    monkeypatch.setattr(flash_gale_fleet, "_run", lambda cmd, label: None)

    with pytest.raises(SystemExit) as exc_info:
        flash_gale_fleet.main([str(img), "EXPECTED-SERIAL"])

    assert exc_info.value.code not in (None, 0)


def test_serial_mismatch_no_write_called(tmp_path, monkeypatch):
    """Mismatching serial → no raiden_write_region invocation (nothing written)."""
    img = _make_image(tmp_path)
    run_calls = []

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "WRONG-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_park", lambda label="re-park AP": None)
    monkeypatch.setattr(flash_gale_fleet, "_run",
                        lambda cmd, label: run_calls.append((cmd, label)))

    with pytest.raises(SystemExit):
        flash_gale_fleet.main([str(img), "EXPECTED-SERIAL"])

    # _run must never have been called at all — nothing was written.
    assert run_calls == [], f"Unexpected _run calls on mismatch: {run_calls}"


# ---------------------------------------------------------------------------
# Match case: write helper called in RO-last order
# ---------------------------------------------------------------------------

def test_serial_match_calls_write_three_times(tmp_path, monkeypatch):
    """Matching serial → _run called exactly three times (once per region)."""
    img = _make_image(tmp_path)
    run_calls = []

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "GOOD-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_park", lambda label="re-park AP": None)
    monkeypatch.setattr(flash_gale_fleet, "_run",
                        lambda cmd, label: run_calls.append((cmd, label)))

    flash_gale_fleet.main([str(img), "GOOD-SERIAL"])

    assert len(run_calls) == 3, f"Expected 3 _run calls, got {len(run_calls)}: {run_calls}"


def test_serial_match_ro_last_write_order(tmp_path, monkeypatch):
    """Matching serial → regions written in RO-last order: RW_A, RW_B, GBB-span."""
    img = _make_image(tmp_path)
    run_calls = []

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "GOOD-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_park", lambda label="re-park AP": None)
    monkeypatch.setattr(flash_gale_fleet, "_run",
                        lambda cmd, label: run_calls.append((cmd, label)))

    flash_gale_fleet.main([str(img), "GOOD-SERIAL"])

    labels = [label for _, label in run_calls]
    assert labels == [
        "flash RW_SECTION_A",
        "flash RW_SECTION_B",
        "flash 0x301000:0xdf000",
    ], f"Wrong write order: {labels}"


def test_serial_match_last_region_has_allow_ro(tmp_path, monkeypatch):
    """Matching serial → last write (GBB span) is invoked with --allow-ro."""
    img = _make_image(tmp_path)
    run_calls = []

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "GOOD-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_park", lambda label="re-park AP": None)
    monkeypatch.setattr(flash_gale_fleet, "_run",
                        lambda cmd, label: run_calls.append((cmd, label)))

    flash_gale_fleet.main([str(img), "GOOD-SERIAL"])

    last_cmd, _ = run_calls[-1]
    assert "--allow-ro" in last_cmd, (
        f"--allow-ro missing from last region cmd: {last_cmd}"
    )
    # RW regions must NOT carry --allow-ro
    for cmd, label in run_calls[:-1]:
        assert "--allow-ro" not in cmd, (
            f"--allow-ro must NOT appear in RW region cmd ({label}): {cmd}"
        )
