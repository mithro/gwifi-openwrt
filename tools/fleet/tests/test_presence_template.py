# SPDX-License-Identifier: Apache-2.0
"""Tests for the ansells-presence pieces of openwisp/build-templates.py."""
import importlib.util
from pathlib import Path

BT_PATH = Path(__file__).resolve().parents[3] / "openwisp" / "build-templates.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_templates", BT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pucks_includes_puck03():
    assert "puck03" in _load().PUCKS


def test_presence_files():
    files = _load().netjson_presence()["files"]
    paths = {f["path"]: f for f in files}
    assert set(paths) == {
        "/opt/presence-detector/presence-detector.py",
        "/etc/presence-detector/settings.json",
        "/etc/init.d/presence-detector",
    }
    assert paths["/etc/presence-detector/settings.json"]["mode"] == "0600"
    assert paths["/etc/init.d/presence-detector"]["mode"] == "0755"
    assert paths["/opt/presence-detector/presence-detector.py"]["mode"] == "0755"


def test_presence_settings_uses_context_vars_no_secrets():
    import json
    files = _load().netjson_presence()["files"]
    settings = next(f for f in files
                    if f["path"] == "/etc/presence-detector/settings.json")
    c = settings["contents"]
    for var in ("{{ mqtt_username }}", "{{ mqtt_password }}", "{{ name }}"):
        assert var in c
    # valid JSON once vars are substituted with dummies
    parsed = json.loads(c.replace("{{ mqtt_username }}", "u")
                         .replace("{{ mqtt_password }}", "p")
                         .replace("{{ name }}", "puck99"))
    assert parsed["mqtt_host"] == "ha.welland.mithis.com"
    assert parsed["fallback_sync_interval"] == 60
    assert parsed["filter_is_denylist"] is True and parsed["filter"] == []
    assert parsed["interfaces"] == []
    assert parsed["source_type"] == "router"


def test_presence_script_matches_vendored_copy():
    mod = _load()
    vendored = (BT_PATH.parent / "presence" / "presence-detector.py").read_text()
    files = mod.netjson_presence()["files"]
    script = next(f for f in files
                  if f["path"] == "/opt/presence-detector/presence-detector.py")
    assert script["contents"] == vendored


def test_base_hook_guards_presence_service():
    hook = _load().POST_RELOAD_HOOK
    assert "/etc/init.d/presence-detector" in hook
    assert "[ -x /usr/bin/python3 ]" in hook   # no-op until deploy installs python


def test_django_script_upserts_and_attaches_presence():
    d = _load().DJANGO
    assert "ansells-presence" in d
    assert "PRESENCE" in d


def test_django_script_attaches_presence_to_pucks_not_tenwrt():
    """Regression guard: a change that creates the ansells-presence Template
    but forgets to wire it into the attach tuple would still pass the two
    substring checks above while silently disabling the whole feature."""
    d = _load().DJANGO
    assert "(b, t, pr)" in d
    assert "detached ansells-presence from tenwrt" in d


def test_django_script_warns_on_missing_mqtt_context():
    """A device attached to ansells-presence without mqtt_username/password
    in its Config.context renders literal '{{ mqtt_username }}' placeholders
    into settings.json (netjsonconfig's evaluate_vars does not raise or
    substitute empty for missing vars) -- the operator must be warned."""
    d = _load().DJANGO
    assert "mqtt_username" in d and "mqtt_password" in d
    assert "MISSING on:" in d
    assert "set_device_vars.py" in d


def test_django_format_still_works_with_presence_placeholder():
    """Guard against DJANGO's r-string brace-escaping regressing when the
    PRESENCE placeholder / upsert block was added — .format() must not raise
    KeyError/IndexError on stray braces introduced by the new block."""
    import ast
    mod = _load()
    rendered = mod.DJANGO.format(
        active="{}", tenwrt="{}", preserved="{}", base="{}",
        defaults="{}", pucks=[], presence="{}",
    )
    assert "ansells-presence" in rendered
    # catch indentation/syntax errors locally instead of on the live wisp shell
    ast.parse(rendered)
    compile(rendered, "<djangosnippet>", "exec")
