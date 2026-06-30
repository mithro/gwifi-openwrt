# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.orchestrator — pure planning logic."""
from pathlib import Path

import pytest

from galeflash import orchestrator


# ---------------------------------------------------------------------------
# Happy-path: stock puck (uses real G4 fixture + futility)
# ---------------------------------------------------------------------------

def test_plan_for_stock_puck(stock_g4, tmp_path):
    backup = tmp_path / "gale-2831HW00VZA-2026-06-30-pre-flash.bin"
    backup.write_bytes(stock_g4)
    p = orchestrator.plan(backup, date="2026-06-30")
    assert p.steps == ["backup", "extract", "build", "flash", "poweron", "verify"]
    assert p.expected_serial == "2831HW00VZA"
    assert p.is_stock is True
    assert p.refuse is False
    assert p.image_path.name == "gale-2831HW00VZA-2026-06-30-fleet.bin"


def test_plan_stock_has_no_refuse_reason(stock_g4, tmp_path):
    """A stock puck must have refuse=False and an empty refuse_reason."""
    backup = tmp_path / "gale-2831HW00VZA-2026-06-30-pre-flash.bin"
    backup.write_bytes(stock_g4)
    p = orchestrator.plan(backup, date="2026-06-30")
    assert p.refuse is False
    assert p.refuse_reason == ""


def test_plan_image_path_is_alongside_backup(stock_g4, tmp_path):
    """image_path must live in the same directory as the backup."""
    subdir = tmp_path / "backups"
    subdir.mkdir()
    backup = subdir / "gale-2831HW00VZA-2026-06-30-pre-flash.bin"
    backup.write_bytes(stock_g4)
    p = orchestrator.plan(backup, date="2026-06-30")
    assert p.image_path.parent == subdir


# ---------------------------------------------------------------------------
# Refuse logic (monkeypatched — deterministic, no futility needed)
# ---------------------------------------------------------------------------

def test_plan_refuses_non_stock_without_override(prerekey_live, tmp_path, monkeypatch):
    # prerekey_live's is_stock may be True or False depending on the dump.
    # Construct the refuse case deterministically by monkeypatching identity.from_dump
    # to report is_stock=False, and assert refuse is True without rekeyed_ok and
    # False with rekeyed_ok=True.
    import galeflash.orchestrator as orch
    monkeypatch.setattr(orch.identity, "from_dump",
                        lambda p: {"serial_number": "TESTSERIAL", "is_stock": False})
    b = tmp_path / "gale-TESTSERIAL-2026-06-30-pre-flash.bin"
    b.write_bytes(b"x")
    assert orch.plan(b, date="2026-06-30").refuse is True
    assert orch.plan(b, date="2026-06-30", rekeyed_ok=True).refuse is False


def test_plan_refuse_reason_contains_serial(tmp_path, monkeypatch):
    """The refuse_reason must name the serial so the operator knows which puck."""
    import galeflash.orchestrator as orch
    monkeypatch.setattr(orch.identity, "from_dump",
                        lambda p: {"serial_number": "XYZTEST", "is_stock": False})
    b = tmp_path / "gale-XYZTEST-2026-06-30-pre-flash.bin"
    b.write_bytes(b"x")
    p = orch.plan(b, date="2026-06-30")
    assert p.refuse is True
    assert "XYZTEST" in p.refuse_reason


def test_plan_rekeyed_ok_clears_refuse(tmp_path, monkeypatch):
    """rekeyed_ok=True must suppress the refuse flag even for a dev-keyed puck."""
    import galeflash.orchestrator as orch
    monkeypatch.setattr(orch.identity, "from_dump",
                        lambda p: {"serial_number": "DEV123", "is_stock": False})
    b = tmp_path / "gale-DEV123-2026-07-01-pre-flash.bin"
    b.write_bytes(b"x")
    p = orch.plan(b, date="2026-07-01", rekeyed_ok=True)
    assert p.refuse is False
    assert p.refuse_reason == ""


def test_plan_image_path_alongside_backup_monkeypatched(tmp_path, monkeypatch):
    """image_path is always in the same dir as the backup (no futility needed)."""
    import galeflash.orchestrator as orch
    monkeypatch.setattr(orch.identity, "from_dump",
                        lambda p: {"serial_number": "SN123", "is_stock": True})
    subdir = tmp_path / "backups"
    subdir.mkdir()
    b = subdir / "gale-SN123-2026-07-01-pre-flash.bin"
    b.write_bytes(b"x")
    p = orch.plan(b, date="2026-07-01")
    assert p.image_path.parent == subdir
    assert p.image_path.name == "gale-SN123-2026-07-01-fleet.bin"


def test_plan_steps_always_full_sequence(tmp_path, monkeypatch):
    """plan() always returns the full six-step sequence regardless of puck state."""
    import galeflash.orchestrator as orch
    for is_stock in (True, False):
        monkeypatch.setattr(orch.identity, "from_dump",
                            lambda p, s=is_stock: {"serial_number": "S", "is_stock": s})
        b = tmp_path / "gale-S-2026-07-01-pre-flash.bin"
        b.write_bytes(b"x")
        p = orch.plan(b, date="2026-07-01", rekeyed_ok=True)
        assert p.steps == ["backup", "extract", "build", "flash", "poweron", "verify"]


def test_plan_carries_identity_dict(tmp_path, monkeypatch):
    """The full identity dict rides on the plan so callers never re-read the dump."""
    import galeflash.orchestrator as orch
    idv = {"serial_number": "SN9", "is_stock": True, "hwid": "GALE TEST"}
    monkeypatch.setattr(orch.identity, "from_dump", lambda p: idv)
    b = tmp_path / "gale-SN9-2026-07-01-pre-flash.bin"
    b.write_bytes(b"x")
    p = orch.plan(b, date="2026-07-01")
    assert p.identity == idv


def test_flashplan_is_frozen(tmp_path, monkeypatch):
    """FlashPlan is immutable — the refuse interlock cannot be mutated post-gate."""
    import dataclasses

    import galeflash.orchestrator as orch
    monkeypatch.setattr(orch.identity, "from_dump",
                        lambda p: {"serial_number": "SNF", "is_stock": False})
    b = tmp_path / "gale-SNF-2026-07-01-pre-flash.bin"
    b.write_bytes(b"x")
    p = orch.plan(b, date="2026-07-01")
    assert p.refuse is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.refuse = False
