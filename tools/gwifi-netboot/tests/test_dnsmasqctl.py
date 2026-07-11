# SPDX-License-Identifier: Apache-2.0
"""Tests for the dnsmasq config install + restart gate."""

import subprocess

import pytest

from gwifi_netboot.dnsmasqctl import DnsmasqctlError, install_fragment


class FakeRunner:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, argv: list[str]) -> None:
        self.calls.append(argv)
        if self.fail_on and self.fail_on in " ".join(argv):
            raise subprocess.CalledProcessError(1, argv)


def test_happy_path_tests_installs_restarts(tmp_path):
    target = tmp_path / "gwifi-generated" / "pucks.conf"
    target.parent.mkdir()
    runner = FakeRunner()
    install_fragment("dhcp-host=aa:bb:cc:dd:ee:ff,10.1.4.104,puck04\n",
                     target, run=runner)
    assert target.read_text().startswith("dhcp-host=")
    assert runner.calls[0][:2] == ["dnsmasq", "--test"]
    assert runner.calls[1] == ["systemctl", "restart", "dnsmasq"]
    # restart, not reload: SIGHUP does NOT re-read conf-dir files.


def test_test_failure_keeps_old_config_no_restart(tmp_path):
    target = tmp_path / "pucks.conf"
    target.write_text("# old good config\n")
    runner = FakeRunner(fail_on="--test")
    with pytest.raises(DnsmasqctlError, match="test"):
        install_fragment("garbage=\n", target, run=runner)
    assert target.read_text() == "# old good config\n"
    assert ["systemctl", "restart", "dnsmasq"] not in runner.calls


def test_atomic_install_no_tmp_leftovers(tmp_path):
    target = tmp_path / "pucks.conf"
    install_fragment("# ok\n", target, run=FakeRunner())
    assert list(tmp_path.glob(".*tmp*")) == []


def test_restart_failure_raises(tmp_path):
    target = tmp_path / "pucks.conf"
    runner = FakeRunner(fail_on="restart")
    with pytest.raises(DnsmasqctlError, match="restart"):
        install_fragment("# ok\n", target, run=runner)
