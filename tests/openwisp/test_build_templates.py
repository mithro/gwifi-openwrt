"""Checks on openwisp/build-templates.py.

Two kinds of assertion here:

* text-level, for the post-reload hook — it is a shell blob inside the module
  and there is nothing importable to poke at;
* module-level, for the per-site wiring — loaded via importlib because the
  filename is hyphenated and so not a legal module name.
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATH = REPO / "openwisp/build-templates.py"
SRC = PATH.read_text()


def _load():
    spec = importlib.util.spec_from_file_location("build_templates", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bt = _load()


def _render(site):
    """Build the remote Django script for a site, with dummy passphrases."""
    cfg = bt.SITES[site]
    return bt.DJANGO.format(
        active=json.dumps(bt.netjson_simple()),
        tenwrt=json.dumps(bt.netjson_tenwrt_aps()),
        preserved=json.dumps(bt.netjson_mesh_aps()),
        base=json.dumps(bt.netjson_base()),
        presence=json.dumps(bt.netjson_presence(cfg["mqtt_host"])),
        defaults=json.dumps({"ansells_key": "x", "iot_key": "y",
                             "guest_key": "z",
                             "syslog_ip": cfg["syslog_ip"]}),
        pucks=cfg["pucks"], extra=cfg["extra"], render=cfg["render"])


# --------------------------------------------------------------- post-reload

def test_hook_targets_syslog_ip_variable_on_514():
    assert "uci set system.@system[0].log_ip='{{ syslog_ip }}'" in SRC
    assert "uci set system.@system[0].log_port='514'" in SRC


def test_hook_no_longer_hardcodes_wisp_syslog_target():
    assert "log_ip='10.1.4.2'" not in SRC
    assert "log_port='6666'" not in SRC


def test_hook_restarts_logd_after_committing_the_target():
    # logd reads log_ip only at start; committing without a restart leaves
    # the new target unused until reboot.
    commit = SRC.index("uci commit system")
    restart = SRC.index("/etc/init.d/log restart")
    assert restart > commit, "log restart must follow the system commit"


# --------------------------------------------------------------- site wiring

def test_both_sites_are_defined():
    assert set(bt.SITES) == {"welland", "monarto"}


def test_every_site_defines_every_key():
    keys = {"ten64", "wisp", "pucks", "extra", "syslog_ip", "mqtt_host",
            "render"}
    for site, cfg in bt.SITES.items():
        assert set(cfg) == keys, f"{site} has {set(cfg) ^ keys} mismatched"


def test_site_endpoints_point_at_their_own_site():
    # the whole point of the refactor: no cross-site references
    for site, cfg in bt.SITES.items():
        for field in ("ten64", "wisp", "mqtt_host"):
            assert f".{site}." in cfg[field], \
                f"{site}.{field} = {cfg[field]!r} is not a {site} host"


def test_ssh_helpers_target_the_requested_site():
    assert "ten64.monarto.mithis.com" in bt.ssh_ten64("monarto")
    assert "wisp.monarto.mithis.com" in bt.ssh_wisp("monarto")
    assert "ten64.welland.mithis.com" in bt.ssh_ten64("welland")
    assert "wisp.welland.mithis.com" in bt.ssh_wisp("welland")


def test_syslog_ip_is_the_sites_router_wifi_leg():
    # rsyslog binds imudp 514/6666 to this address on each site's ten64
    assert bt.SITES["welland"]["syslog_ip"] == "10.1.4.1"
    assert bt.SITES["monarto"]["syslog_ip"] == "10.2.4.1"


def test_tenwrt_vm_is_welland_only():
    assert bt.SITES["welland"]["extra"] == ["tenwrt"]
    assert bt.SITES["monarto"]["extra"] == []


def test_monarto_roster_holds_the_pucks_installed_there():
    assert set(bt.SITES["monarto"]["pucks"]) == {
        "puck05", "puck13", "puck14", "puck15"}


def test_no_puck_is_claimed_by_both_sites():
    w = set(bt.SITES["welland"]["pucks"])
    m = set(bt.SITES["monarto"]["pucks"])
    # puck05 moved to monarto 2026-08-03 and must not linger in welland's
    # roster, or welland would keep re-attaching templates to absent hardware
    assert not (w & m), f"pucks claimed by both sites: {sorted(w & m)}"


def test_render_targets_are_devices_the_site_actually_has():
    for site, cfg in bt.SITES.items():
        known = set(cfg["pucks"]) | set(cfg["extra"])
        assert set(cfg["render"]) <= known, \
            f"{site} renders devices it does not manage"


# ----------------------------------------------------------------- presence

def test_presence_settings_carry_the_sites_mqtt_host():
    for site, cfg in bt.SITES.items():
        cfgjson = bt.netjson_presence(cfg["mqtt_host"])
        settings = next(f for f in cfgjson["files"]
                        if f["path"] == "/etc/presence-detector/settings.json")
        assert json.loads(settings["contents"])["mqtt_host"] == cfg["mqtt_host"]


def test_presence_settings_keep_their_jinja_placeholders():
    # credentials arrive per-device via Config.context; substituting them here
    # would bake one puck's secrets into the shared template
    contents = next(
        f["contents"]
        for f in bt.netjson_presence("ha.monarto.mithis.com")["files"]
        if f["path"] == "/etc/presence-detector/settings.json")
    assert "{{ mqtt_username }}" in contents
    assert "{{ mqtt_password }}" in contents
    assert "{{ name }}" in contents


# ------------------------------------------------------------ django script

def test_django_script_formats_for_every_site():
    """The remote script is built with str.format; a placeholder added to the
    template without a matching kwarg raises KeyError only at runtime, after
    the passphrase SSH has already happened. Render both sites here instead."""
    for site, cfg in bt.SITES.items():
        script = _render(site)
        assert f"DEVICES = PUCKS + {cfg['extra']!r}" in script
        assert cfg["syslog_ip"] in script


def test_monarto_script_targets_no_welland_endpoint():
    # prose may mention welland (the comments explain the split); what must
    # never appear is a welland host or address the pucks would actually talk to
    script = _render("monarto")
    for host in ("wisp.welland.mithis.com", "ten64.welland.mithis.com",
                 "ha.welland.mithis.com"):
        assert host not in script, f"monarto script points at {host}"
    assert "10.1.4." not in script, "monarto script carries a welland address"


# ------------------------------------------------------------------- usteer

def test_usteer_section_is_named_so_merges_are_idempotent():
    """openwisp-config MERGES /etc/config/* instead of overwriting them, and a
    merge matches sections by NAME. An anonymous `config usteer` has no name to
    match, so every apply appended another copy -- five sections per welland
    puck and four per monarto puck by 2026-08-04, auto-named usteer2/3/4.

    Naming it 'usteer1' (the section the gale image itself ships) makes the
    merge an in-place update, so applying N times is the same as applying once.
    """
    first = bt.USTEER_CONFIG.strip().splitlines()[0]
    assert first == "config usteer 'usteer1'", (
        f"usteer section must be named 'usteer1', got: {first!r}. "
        "An anonymous section makes every openwisp apply add a duplicate.")


def test_usteer_config_declares_one_section_only():
    assert bt.USTEER_CONFIG.count("config usteer") == 1


def test_usteer_carries_the_options_the_image_sets():
    """The image's usteer1 sets these on most pucks; pinning them in the
    template stops the live config depending on which image a puck was
    flashed with."""
    for opt in ("load_kick_enabled", "syslog", "network", "local_mode",
                "assoc_steering", "load_balancing_threshold"):
        assert f"option {opt} " in bt.USTEER_CONFIG, f"missing option {opt}"
    assert bt.USTEER_CONFIG.count("list ssid_list") == 2
