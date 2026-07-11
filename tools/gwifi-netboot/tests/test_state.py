# SPDX-License-Identifier: Apache-2.0
"""Tests for the runtime state store (armed flags, phone-home records)."""

import json
from pathlib import Path

from gwifi_netboot.state import StateStore

MAC = "44:07:0b:01:a2:21"


def make_store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "state.json")


def test_fresh_store_empty(tmp_path):
    store = make_store(tmp_path)
    assert store.armed_macs() == set()
    assert store.puck_state(MAC) == {}


def test_arm_disarm_idempotent(tmp_path):
    store = make_store(tmp_path)
    store.arm([MAC])
    store.arm([MAC])
    assert store.armed_macs() == {MAC}
    store.disarm([MAC])
    store.disarm([MAC])
    assert store.armed_macs() == set()


def test_state_persists_across_instances(tmp_path):
    make_store(tmp_path).arm([MAC])
    assert make_store(tmp_path).armed_macs() == {MAC}


def test_phone_home_success_disarms_and_records(tmp_path):
    store = make_store(tmp_path)
    store.arm([MAC])
    store.record_phone_home(MAC, result="success", image_id="gale-x",
                            serial="2831HW00WGD", detail="flashed+verified")
    assert store.armed_macs() == set()
    st = store.puck_state(MAC)
    assert st["installed_image_id"] == "gale-x"
    assert st["last_phone_home"]["result"] == "success"


def test_phone_home_already_current_disarms(tmp_path):
    store = make_store(tmp_path)
    store.arm([MAC])
    store.record_phone_home(MAC, result="already-current", image_id="gale-x",
                            serial="s", detail="marker match")
    assert store.armed_macs() == set()
    assert store.puck_state(MAC)["installed_image_id"] == "gale-x"


def test_phone_home_failed_stays_armed(tmp_path):
    store = make_store(tmp_path)
    store.arm([MAC])
    store.record_phone_home(MAC, result="failed", image_id="gale-x",
                            serial="s", detail="sha mismatch")
    assert store.armed_macs() == {MAC}
    assert "installed_image_id" not in store.puck_state(MAC)


def test_unknown_mac_recorded_without_crash(tmp_path):
    store = make_store(tmp_path)
    store.record_phone_home("de:ad:be:ef:00:01", result="success",
                            image_id="x", serial="s", detail="d")
    assert store.puck_state("de:ad:be:ef:00:01")["installed_image_id"] == "x"


def test_history_bounded(tmp_path):
    store = make_store(tmp_path)
    for i in range(30):
        store.record_phone_home(MAC, result="failed", image_id=f"img{i}",
                                serial="s", detail=f"attempt {i}")
    assert len(store.puck_state(MAC)["history"]) == 20
    assert store.puck_state(MAC)["history"][-1]["detail"] == "attempt 29"


def test_atomic_write_no_partial_file(tmp_path):
    store = make_store(tmp_path)
    store.arm([MAC])
    # The state file must always be valid JSON (tmp+rename), and no tmp
    # leftovers linger.
    assert json.loads((tmp_path / "state.json").read_text())
    assert list(tmp_path.glob("*.tmp*")) == []


def test_events_have_timestamps(tmp_path):
    store = make_store(tmp_path)
    store.record_phone_home(MAC, result="success", image_id="x",
                            serial="s", detail="d")
    assert "time" in store.puck_state(MAC)["last_phone_home"]
