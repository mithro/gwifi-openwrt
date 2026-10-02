# SPDX-License-Identifier: Apache-2.0
"""Pucks accept public-key SSH only (openwisp/build-templates.py)."""
import importlib.util
import json
import re
from pathlib import Path

BT_PATH = Path(__file__).resolve().parents[3] / "openwisp" / "build-templates.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_templates", BT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hook():
    files = _load().netjson_base()["files"]
    return next(f for f in files if f["path"] == "/etc/openwisp/post-reload-hook")["contents"]


def test_admin_keys_are_public_keys():
    keys = _load().ADMIN_SSH_PUBKEYS
    assert len(keys) >= 1
    for k in keys:
        assert re.match(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-\S+) AAAA\S+ \S", k), k
        assert "\n" not in k
        assert "PRIVATE" not in k


def test_hook_disables_password_auth():
    hook = _hook()
    assert "PasswordAuth" in hook and "RootPasswordAuth" in hook
    assert "uci commit dropbear" in hook
    assert "/etc/init.d/dropbear reload" in hook


def test_hook_never_disables_passwords_without_a_key():
    """Turning passwords off on a puck with no authorized key would leave it
    reachable only through the openwisp agent: the hook must gate on a key."""
    hook = _hook()
    gate = hook.index('grep -q \'^ssh-\' "$AK"')
    assert "AK=/etc/dropbear/authorized_keys" in hook
    assert gate < hook.index("uci set dropbear")
    assert "pw=on" in hook and "pw=off" in hook


def test_hook_does_not_hide_stderr():
    assert "2>/dev/null" not in _hook()


def test_django_script_carries_keys_and_attaches_ssh_keys_template():
    mod = _load()
    script = mod.DJANGO.format(
        active="{}", tenwrt="{}", preserved="{}", base="{}", presence="{}",
        defaults="{}", admin_keys=json.dumps(list(mod.ADMIN_SSH_PUBKEYS)),
        pucks=["puck99"], extra=[], render=[])
    assert "/etc/dropbear/authorized_keys" in script
    assert "ADMIN_KEYS" in script
    # never creates the template: it must already hold OpenWISP's own key
    assert "SSH Keys" in script
    compile(script, "<django>", "exec")
