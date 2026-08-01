"""Text-level checks on openwisp/build-templates.py (it runs at import,
so tests assert on the source, not the module)."""

from pathlib import Path

SRC = (Path(__file__).resolve().parents[2]
       / "openwisp/build-templates.py").read_text()


def test_hook_targets_syslog_ip_variable_on_514():
    assert "uci set system.@system[0].log_ip='{{ syslog_ip }}'" in SRC
    assert "uci set system.@system[0].log_port='514'" in SRC


def test_hook_no_longer_hardcodes_wisp_syslog_target():
    assert "log_ip='10.1.4.2'" not in SRC
    assert "log_port='6666'" not in SRC


def test_defaults_carry_the_syslog_ip_context():
    # the default MUST live in the same default_values the base template
    # uses, or devices render the literal {{ syslog_ip }} string
    assert '"syslog_ip": "10.1.4.1"' in SRC
