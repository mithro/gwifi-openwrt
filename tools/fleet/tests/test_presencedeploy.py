# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.presencedeploy — pure script-builder/parser logic."""
import pytest

from galeflash.presencedeploy import PACKAGES, build_install_script, parse_results


def test_packages():
    assert PACKAGES == ("python3", "python3-paho-mqtt")


def test_install_script_contents():
    s = build_install_script()
    assert "apk update" in s
    assert "apk add python3 python3-paho-mqtt" in s
    # must check the template delivered its files before starting anything
    assert "/opt/presence-detector/presence-detector.py" in s
    assert "/etc/presence-detector/settings.json" in s
    assert "/etc/init.d/presence-detector" in s
    # verification: service registered with procd + recent syslog errors
    assert "service list" in s
    assert "logread" in s
    # results protocol: the script emits via the result() helper, so the
    # literal text in the script is the lowercase call sites
    assert 'echo "RESULT $1 $2 $3"' in s
    for step in ("files", "apk", "service", "mqtt"):
        assert f"result {step} " in s
    # service check polls instead of a fixed sleep (startup is not instant)
    assert "while" in s
    assert "-lt 15" in s
    # mqtt check requires positive log evidence, not just an absence of errors
    assert "no-log-evidence" in s
    assert "errors-after-last-success" in s
    assert "no-success-evidence" in s
    assert "log-evidence" in s
    assert "offline, sleeping" in s
    # ...and judges by RECENCY: "broker seems to be offline" is logged at
    # startup before the connection completes, so a puck that hiccupped and
    # then connected is healthy (observed on puck03/06/07, 2026-07-30).
    assert "last_err" in s and "last_ok" in s
    assert "is now at home" in s
    # ...and POLLS for it: the daemon logs only after procd reports it
    # registered, so sampling once races startup and calls a healthy deploy
    # no-log-evidence (observed fleet-wide on 2026-07-30).
    assert "-lt 20" in s


def test_parse_results_ok():
    text = "junk\nRESULT files OK -\nRESULT apk OK installed\nRESULT service OK running\nRESULT mqtt OK no-errors\n"
    assert parse_results(text) == {
        "files": (True, "-"),
        "apk": (True, "installed"),
        "service": (True, "running"),
        "mqtt": (True, "no-errors"),
    }


def test_parse_results_failure_detail():
    text = ("RESULT files OK -\nRESULT apk OK installed\n"
            "RESULT service FAIL not-registered\nRESULT mqtt FAIL connect-refused\n")
    r = parse_results(text)
    assert r["service"] == (False, "not-registered")


def test_parse_results_missing_step_raises():
    with pytest.raises(ValueError, match="mqtt"):
        parse_results("RESULT files OK -\nRESULT apk OK x\nRESULT service OK x\n")


def test_parse_results_duplicate_raises():
    with pytest.raises(ValueError, match="duplicate"):
        parse_results("RESULT apk OK a\nRESULT apk OK b\n"
                      "RESULT files OK -\nRESULT service OK x\nRESULT mqtt OK x\n")


def _load_deploy_presence():
    """deploy_presence.py is a CLI script, not a package module."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "deploy_presence.py"
    spec = importlib.util.spec_from_file_location("deploy_presence", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_deploy_presence_knows_both_sites():
    assert set(_load_deploy_presence().SITES) == {"welland", "monarto"}


def test_each_site_registry_is_its_own_wisp():
    # the registry host is that site's wisp VM at <net>.4.2; a copy-paste
    # slip here would deploy monarto using welland's puck list
    sites = _load_deploy_presence().SITES
    assert sites["welland"] == "tim@10.1.4.2"
    assert sites["monarto"] == "tim@10.2.4.2"
