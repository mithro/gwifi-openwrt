# SPDX-License-Identifier: Apache-2.0
"""Tests for the gwifi-netboot CLI."""

import json
import shutil
from pathlib import Path

import pytest

from gwifi_netboot import cli

FIXTURE = Path(__file__).parent / "fixtures" / "pucks.json"
PUCK12_ETH0 = "44:07:0b:01:a2:21"


class FakeInstaller:
    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, content, target):
        self.calls.append(content)


@pytest.fixture()
def env(tmp_path):
    identity = tmp_path / "pucks.json"
    shutil.copy(FIXTURE, identity)
    installer = FakeInstaller()
    base = [
        "--identity", str(identity),
        "--state", str(tmp_path / "state.json"),
        "--fragment", str(tmp_path / "pucks.conf"),
        "--manifest", str(tmp_path / "manifest.json"),
    ]
    return base, installer, tmp_path


def run(base, installer, *argv) -> tuple[int, object]:
    return cli.main([*base, *argv], installer=installer)


def test_status_lists_pucks(env, capsys):
    base, installer, _ = env
    rc = cli.main([*base, "status"], installer=installer)
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert [p["name"] for p in doc["pucks"]] == ["puck04", "puck12"]


def test_arm_by_name_regenerates(env, capsys):
    base, installer, _ = env
    rc = cli.main([*base, "arm", "puck12"], installer=installer)
    assert rc == 0
    assert "set:install" in installer.calls[-1]
    capsys.readouterr()  # drain the arm message
    rc = cli.main([*base, "status"], installer=installer)
    doc = json.loads(capsys.readouterr().out)
    by_name = {p["name"]: p for p in doc["pucks"]}
    assert by_name["puck12"]["armed"] is True


def test_disarm(env, capsys):
    base, installer, _ = env
    cli.main([*base, "arm", "puck12"], installer=installer)
    rc = cli.main([*base, "disarm", "puck12"], installer=installer)
    assert rc == 0
    assert "set:install" not in installer.calls[-1]


def test_arm_all(env):
    base, installer, _ = env
    rc = cli.main([*base, "arm", "--all"], installer=installer)
    assert rc == 0
    assert installer.calls[-1].count("set:install") == 2


def test_arm_unknown_puck_fails(env, capsys):
    base, installer, _ = env
    rc = cli.main([*base, "arm", "puck99"], installer=installer)
    assert rc != 0
    assert "puck99" in capsys.readouterr().err
    assert installer.calls == []


def test_render_check_ok(env):
    base, installer, _ = env
    assert cli.main([*base, "render", "--check"], installer=installer) == 0


def test_render_check_fails_on_bad_identity(env, capsys):
    base, installer, tmp_path = env
    (tmp_path / "pucks.json").write_text("{broken")
    rc = cli.main([*base, "render", "--check"], installer=installer)
    assert rc != 0


def test_render_writes_fragment(env):
    base, installer, _ = env
    rc = cli.main([*base, "render"], installer=installer)
    assert rc == 0
    assert "dhcp-host=" in installer.calls[-1]
