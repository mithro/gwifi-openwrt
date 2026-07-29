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
