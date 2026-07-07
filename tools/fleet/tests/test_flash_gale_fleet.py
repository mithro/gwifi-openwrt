# SPDX-License-Identifier: Apache-2.0
"""CLI wiring tests for flash_gale_fleet.py — no hardware required.

The hardware seams (_run, serialguard.read_live_serial) are monkeypatched so
the entire main() wiring runs in-process.  Region ordering / RO-last / erase
semantics live INSIDE flash_puck_usb.py (hardware-proven); the contract at
this level is: serial guard gates everything, and a match produces exactly
one invocation of the verified tool with the right flags.
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
    monkeypatch.setattr(flash_gale_fleet, "_run", lambda cmd, label: None)

    with pytest.raises(SystemExit) as exc:
        flash_gale_fleet.main([str(img), "GOOD-SERIAL"])
    assert exc.value.code not in (0, None)


def test_serial_mismatch_no_write_called(tmp_path, monkeypatch):
    """Mismatching serial → _run never invoked (nothing written)."""
    img = _make_image(tmp_path)
    run_calls = []

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "WRONG-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_run",
                        lambda cmd, label: run_calls.append((cmd, label)))

    with pytest.raises(SystemExit):
        flash_gale_fleet.main([str(img), "GOOD-SERIAL"])

    assert run_calls == [], f"Unexpected _run calls on mismatch: {run_calls}"


def test_missing_image_exits_before_serial_read(tmp_path, monkeypatch):
    """Nonexistent image → SystemExit before any hardware access."""
    reads = []
    monkeypatch.setattr(serialguard, "read_live_serial",
                        lambda: reads.append(1) or "GOOD-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_run", lambda cmd, label: None)

    with pytest.raises(SystemExit):
        flash_gale_fleet.main([str(tmp_path / "nope.bin"), "GOOD-SERIAL"])
    assert reads == [], "serial must not be read when the image is missing"


# ---------------------------------------------------------------------------
# Match case: exactly one invocation of the verified tool
# ---------------------------------------------------------------------------

def test_serial_match_single_call_uses_verified_tool(tmp_path, monkeypatch):
    """Matching serial → ONE _run call driving flash_puck_usb.py flash with
    --commit --allow-ro (the tool owns RO-last ordering + settled sessions)."""
    img = _make_image(tmp_path)
    run_calls = []

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "GOOD-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_run",
                        lambda cmd, label: run_calls.append((cmd, label)))

    flash_gale_fleet.main([str(img), "GOOD-SERIAL"])

    assert len(run_calls) == 1, f"Expected exactly 1 call, got: {run_calls}"
    cmd, _ = run_calls[0]
    cmd_str = [str(c) for c in cmd]
    assert any("flash_puck_usb.py" in c for c in cmd_str), cmd_str
    assert "flash" in cmd_str, cmd_str
    assert str(img) in cmd_str, cmd_str
    assert "--commit" in cmd_str, cmd_str
    assert "--allow-ro" in cmd_str, cmd_str


def test_serial_match_no_legacy_tools_invoked(tmp_path, monkeypatch):
    """The removed legacy tools must never appear in any invocation."""
    img = _make_image(tmp_path)
    run_calls = []

    monkeypatch.setattr(serialguard, "read_live_serial", lambda: "GOOD-SERIAL")
    monkeypatch.setattr(flash_gale_fleet, "_run",
                        lambda cmd, label: run_calls.append(cmd))

    flash_gale_fleet.main([str(img), "GOOD-SERIAL"])

    for cmd in run_calls:
        joined = " ".join(str(c) for c in cmd)
        for legacy in ("raiden", "chunk_read", "ec_park", "gflash", "gserial"):
            assert legacy not in joined, f"legacy tool {legacy!r} in: {joined}"
