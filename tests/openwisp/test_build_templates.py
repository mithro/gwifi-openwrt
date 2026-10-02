"""Checks on openwisp/build-templates.py.

Two kinds of assertion here:

* text-level, for the post-reload hook — it is a shell blob inside the module
  and there is nothing importable to poke at;
* module-level, for the per-site wiring — loaded via importlib because the
  filename is hyphenated and so not a legal module name.
"""

import importlib.util
import json
import re
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
        active=json.dumps(bt.netjson_simple(cfg["main_2g4"])),
        tenwrt=json.dumps(bt.netjson_tenwrt_aps()),
        preserved=json.dumps(bt.netjson_mesh_aps()),
        base=json.dumps(bt.netjson_base()),
        presence=json.dumps(bt.netjson_presence(cfg["mqtt_host"])),
        ft_test=json.dumps(bt.netjson_ft_test()),
        ft_test_devices=cfg["ft_test"],
        defaults=json.dumps({"ansells_key": "x", "iot_key": "y",
                             "guest_key": "z",
                             "syslog_ip": cfg["syslog_ip"]}),
        admin_keys=json.dumps(list(bt.ADMIN_SSH_PUBKEYS)),
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
            "render", "main_2g4", "ft_test"}
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


# --------------------------------------------------- usteer client steering
#
# Until 2026-08-26 usteer was a pure observer on this fleet: it published
# 802.11k neighbour reports and never moved a single client. 2026-08-26 turned
# steering on, 2026-08-29 took the association path back off after it denied
# every association, and 2026-09-19 made usteer MONITOR-ONLY again: usteerd
# runs and logs, but every actuator is off.  These tests pin each gate closed.


def _uci_option(name):
    m = re.search(rf"^\toption {name} '([^']*)'$", bt.USTEER_CONFIG, re.MULTILINE)
    return m and m.group(1)


def test_usteer_roam_state_machine_is_off():
    """usteer_local_node_roam_check() (policy.c) reads:

        if (config.roam_scan_snr)         min_signal = config.roam_scan_snr;
        else if (config.roam_trigger_snr) min_signal = config.roam_trigger_snr;
        else                              return;

    Both 0 => it returns before looking at a client: no roam state machine,
    no BSS-TM requests, no roam kicks.  Pinned explicitly at '0' (not merely
    absent) because openwisp-config MERGES /etc/config/usteer, so an omitted
    option would keep whatever the puck already had -- e.g. the '34' that
    shipped 2026-08-26.
    """
    assert _uci_option("roam_trigger_snr") == "0"
    assert _uci_option("roam_scan_snr") == "0"


def test_usteer_band_steering_is_off():
    """usteer_band_steering_perform_steer() returns early only when
    band_steering_interval is 0 -- and usteer's DEFAULT is 120000, so band
    steering (2.4 -> 5 GHz BSS-TM) was live on every puck until 2026-09-19
    even though no version of this file ever mentioned it."""
    assert _uci_option("band_steering_interval") == "0"


def test_usteer_does_not_kick_clients():
    """min_snr kicks a client purely for being weak (usteer_local_node_snr_kick
    returns early only at 0) and also denies associations below it; load kicks
    have their own switch.  Both pinned off for the same merge reason as
    above."""
    assert _uci_option("min_snr") == "0"
    assert _uci_option("min_connect_snr") == "0"
    assert _uci_option("load_kick_enabled") == "0"


def test_usteer_association_path_stays_off_after_the_denial_regression():
    """The association path must stay disabled -- it broke the fleet.

    Enabling all three of these together on 2026-08-26 made every AP at
    welland DENY associations (hostapd status_code=17, usteer
    reason=better_candidate) and it was reverted by hand on the controller on
    2026-08-29.  Mechanism: usteer's signal compare is band-blind and its
    n_assoc compare ignores signal, so every AP concludes some other AP is
    the better candidate and defers; with nobody willing to accept, clients
    associate nowhere.
    """
    assert _uci_option("assoc_steering") == "0"
    assert _uci_option("load_balancing_threshold") == "0"
    assert "option signal_diff_threshold" not in bt.USTEER_CONFIG


def test_usteer_does_not_claim_a_probe_steering_switch():
    """probe_steering is a struct field hardcoded to 0 in main.c; it is not in
    usteer's ubus config table or the init script's whitelist, so a UCI line
    for it is silently dropped.  Don't write a setting that does nothing."""
    assert "probe_steering" not in bt.USTEER_CONFIG


def test_usteer_logs_assoc_decisions_but_not_probes():
    """Probe logging on a fleet this size would flood the per-net rsyslog."""
    for evt in ("assoc_req_accept", "assoc_req_deny"):
        assert f"list event_log_types '{evt}'" in bt.USTEER_CONFIG
    assert "probe_req" not in bt.USTEER_CONFIG


def test_usteer_options_are_all_recognised_by_the_init_script():
    """/etc/init.d/usteer whitelists the UCI options it forwards; anything
    outside that list is silently DROPPED rather than erroring. Whitelist
    transcribed from the live init script on puck10, 2026-08-26."""
    known = {
        "network", "enabled",
        "syslog", "ipv6", "local_mode", "load_kick_enabled", "assoc_steering",
        "node_up_script", "ssid_list", "event_log_types",
        "debug_level", "sta_block_timeout", "local_sta_timeout",
        "local_sta_update", "max_neighbor_reports", "max_retry_band",
        "seen_policy_timeout", "measurement_report_timeout",
        "load_balancing_threshold", "band_steering_threshold",
        "remote_update_interval", "remote_node_timeout", "min_connect_snr",
        "min_snr", "min_snr_kick_delay", "signal_diff_threshold",
        "initial_connect_delay", "steer_reject_timeout", "roam_process_timeout",
        "roam_kick_delay", "roam_scan_tries", "roam_scan_timeout",
        "roam_scan_snr", "roam_scan_interval", "roam_trigger_snr",
        "roam_trigger_interval", "band_steering_interval",
        "band_steering_min_snr", "link_measurement_interval",
        "load_kick_threshold", "load_kick_delay", "load_kick_min_clients",
        "load_kick_reason_code",
    }
    used = set(re.findall(r"^\t(?:option|list) (\w+) ", bt.USTEER_CONFIG,
                          re.MULTILINE))
    assert used <= known, f"init script would silently drop: {used - known}"
# ---------------------------------------------------------------------------
# ath10k fwcfg — the association-limit raise
# ---------------------------------------------------------------------------
#
# puck12 hit the QCA4019 10.4 default of 32 stations per radio on the IoT
# SSID.  These pin the shape of the fix and, more importantly, guard the two
# values that are handed to the FIRMWARE.

def _fwcfg_files():
    paths = {f["path"]: f for f in bt.netjson_base()["files"]}
    return {p: f for p, f in paths.items() if "fwcfg" in p}


def test_base_template_ships_fwcfg_for_both_radios():
    """Both QCA4019 radios need their own file: fwcfg-<bus>-<dev>.txt."""
    got = set(_fwcfg_files())
    assert got == {
        "/lib/firmware/ath10k/fwcfg-ahb-a000000.wifi.txt",
        "/lib/firmware/ath10k/fwcfg-ahb-a800000.wifi.txt",
    }


def test_fwcfg_raises_stations_above_the_default_32():
    for f in _fwcfg_files().values():
        assert "stations=64" in f["contents"]


def test_fwcfg_avoids_the_values_that_broke_firmware_init():
    """peers=144/tids=288 made the firmware miss its ready event on puck12.

    'could not init core (-110)' and NO phy registered -- i.e. the AP off the
    air.  peers/tids are sent to the firmware (wmi.c) and resize its tables,
    so they are the dangerous knobs; keep them at the values proven stable.
    """
    for f in _fwcfg_files().values():
        assert "peers=144" not in f["contents"]
        assert "tids=288" not in f["contents"]
        assert "peers=80" in f["contents"]
        assert "tids=160" in f["contents"]


def test_fwcfg_peers_exceeds_stations():
    """Each vdev burns a self-peer, so peers must exceed the station ceiling
    or the peer check becomes the real (lower) limit."""
    for f in _fwcfg_files().values():
        vals = dict(
            line.split("=", 1)
            for line in f["contents"].splitlines()
            if "=" in line and not line.startswith("#")
        )
        assert int(vals["peers"]) > int(vals["stations"])


def test_fwcfg_is_mode_0644():
    for f in _fwcfg_files().values():
        assert f["mode"] == "0644"


# ------------------------------------------------------------ regulatory

def test_every_radio_declares_the_australian_regdomain():
    # Without a country the pucks run the driver default (US): wrong channel
    # set and power limits for where they are installed.
    for build in (bt.netjson_simple, bt.netjson_tenwrt_aps):
        radios = build()["radios"]
        assert radios, build.__name__
        assert [r.get("country") for r in radios] == ["AU"] * len(radios), \
            build.__name__


# ------------------------------------------------------- 'ansells' band plan

def _ifnames(netjson):
    return [i["name"] for i in netjson["interfaces"]]


def test_welland_serves_ansells_on_5ghz_only():
    assert bt.SITES["welland"]["main_2g4"] is False
    names = _ifnames(bt.netjson_simple(bt.SITES["welland"]["main_2g4"]))
    assert "wl-main-5g" in names
    assert "wl-main-2g4" not in names


def test_monarto_keeps_ansells_on_both_bands():
    # 56% of monarto's 'ansells' associations were on 2.4 GHz (2026-10-02)
    assert bt.SITES["monarto"]["main_2g4"] is True
    names = _ifnames(bt.netjson_simple(bt.SITES["monarto"]["main_2g4"]))
    assert {"wl-main-5g", "wl-main-2g4"} <= set(names)


def test_dropping_main_2g4_leaves_iot_and_guest_on_both_bands():
    # the IoT fleet lives on 2.4 GHz; only the 'ansells' BSS is band-limited
    names = _ifnames(bt.netjson_simple(False))
    assert names == ["wl-main-5g", "wl-iot-5g", "wl-iot-2g4",
                     "wl-guest-5g", "wl-guest-2g4"]


# ----------------------------------------------- 802.11r proof SSID (temporary)

def test_ft_test_ssid_is_ansells_plus_fast_transition():
    (iface,) = bt.netjson_ft_test()["interfaces"]
    w = iface["wireless"]
    main = bt.netjson_simple()["interfaces"][0]["wireless"]
    assert main["ssid"] == "ansells"
    # same radio, VLAN, key and tuning as 'ansells': the only variable in the
    # A/B is 802.11r
    for k in ("radio", "network", "encryption", "ieee80211k", "bss_transition",
              "ieee80211w"):
        assert w[k] == main[k], k
    assert w["ssid"] == "ansells-ft"
    assert w["ieee80211r"] is True
    assert w["ft_psk_generate_local"] is True
    assert w["ft_over_ds"] is False
    assert w["mobility_domain"] == "a137"


def test_ft_test_devices_are_pucks_of_their_own_site():
    for site, cfg in bt.SITES.items():
        assert set(cfg["ft_test"]) <= set(cfg["pucks"]), site
    assert bt.SITES["monarto"]["ft_test"] == []


def test_ft_test_template_is_detached_from_devices_not_listed():
    script = _render("welland")
    assert ("FT_TEST_DEVICES = ['puck03', 'puck06', 'puck07', 'puck12']"
            in script)
    assert "if c.device.name not in FT_TEST_DEVICES:" in script
