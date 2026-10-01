# SPDX-License-Identifier: Apache-2.0
"""Admin SSH keys for the pucks (openwisp/build-templates.py)."""
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


def test_admin_keys_are_public_keys():
    keys = _load().ADMIN_SSH_PUBKEYS
    assert len(keys) >= 1
    for k in keys:
        assert re.match(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-\S+) AAAA\S+ \S", k), k
        assert "\n" not in k
        assert "PRIVATE" not in k


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
