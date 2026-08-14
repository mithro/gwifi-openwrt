# SPDX-License-Identifier: Apache-2.0
"""The openwisp/ Ansible tree must be site-parameterised, not welland-only."""
import importlib.util
import sys
from pathlib import Path

import yaml

OW = Path(__file__).resolve().parents[3] / "openwisp"


def _load_script(filename, modname):
    """Load a hyphenated openwisp/ script as a module.

    Registering in sys.modules before exec_module is required, not optional --
    see the note in test_create_vm.py.
    """
    spec = importlib.util.spec_from_file_location(modname, OW / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_per_site_inventories_exist():
    assert (OW / "inventories" / "welland").is_file()
    assert (OW / "inventories" / "monarto").is_file()


def test_old_single_site_inventory_is_gone():
    assert not (OW / "inventory").exists()


def test_each_inventory_names_exactly_one_host_run_locally():
    """D2: ansible_connection=local configures whichever box the run is on,
    so an inventory must never list both sites."""
    for site, fqdn in (("welland", "wisp.welland.mithis.com"),
                       ("monarto", "wisp.monarto.mithis.com")):
        body = (OW / "inventories" / site).read_text()
        hosts = [ln.split()[0] for ln in body.splitlines()
                 if ln.strip() and not ln.startswith(("#", "["))]
        assert hosts == [fqdn], site
        assert "ansible_connection=local" in body


def test_allowed_hosts_never_lists_the_bare_wisp_ip():
    """The bare IP must belong to the gwifi-images vhost, NOT OpenWISP.

    This test used to assert the OPPOSITE -- that each site listed its own
    10.X.4.2 -- which is the assumption that broke every eMMC install at
    monarto.  The openwisp2 role derives nginx's server_name from this list:

        server_name {{ inventory_hostname }}{% for h in openwisp2_allowed_hosts %} {{ h }}{% endfor %};

    so listing the IP makes the OpenWISP vhost own Host <ip> on :80 and 301
    it to HTTPS.  The netbooted installer fetches the factory image as
    http://<ip>/<factory>.bin -- plain HTTP, by IP literal, with no TLS
    stack in the image -- so it cannot follow that redirect.

    Nothing needs OpenWISP by IP: the pucks' agent is configured with the
    FQDN, which is also the only name the certificate matches.
    """
    for fqdn, ip in (("wisp.welland.mithis.com", "10.1.4.2"),
                     ("wisp.monarto.mithis.com", "10.2.4.2")):
        v = yaml.safe_load((OW / "host_vars" / f"{fqdn}.yml").read_text())
        assert v["openwisp2_allowed_hosts"] == [], fqdn
        assert ip not in (v["openwisp2_allowed_hosts"] or []), fqdn


def _walk(node):
    """Yield every scalar in a parsed YAML document."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(k)
            yield from _walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)
    else:
        yield node


def test_stale_address_is_not_used_as_a_value_anywhere():
    """The VM lost 10.1.5.2 in the VLAN 4 migration; nothing may still
    resolve to it.

    Checks parsed VALUES, not raw text: the welland host_vars deliberately
    mentions the old address in a comment explaining the move, and that
    comment is what stops someone "correcting" it back.
    """
    for p in (list(OW.glob("*.yml"))
              + list((OW / "host_vars").glob("*.yml"))
              + list((OW / "group_vars").glob("*.yml"))):
        doc = yaml.safe_load(p.read_text())
        for scalar in _walk(doc):
            assert "10.1.5.2" not in str(scalar), f"{p}: {scalar!r}"


def test_from_email_is_site_specific():
    for fqdn in ("wisp.welland.mithis.com", "wisp.monarto.mithis.com"):
        v = yaml.safe_load((OW / "host_vars" / f"{fqdn}.yml").read_text())
        assert v["openwisp2_default_from_email"].endswith(f"@{fqdn}")


def test_certbot_domain_is_the_sites_own_fqdn():
    """A copy-paste slip here would request welland's cert on monarto."""
    for fqdn in ("wisp.welland.mithis.com", "wisp.monarto.mithis.com"):
        v = yaml.safe_load((OW / "host_vars" / f"{fqdn}.yml").read_text())
        assert v["certbot_certs"][0]["domains"] == [fqdn], fqdn


def test_shared_vars_hold_the_module_set_and_timezone():
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    assert g["openwisp2_monitoring"] is True
    assert g["openwisp2_network_topology"] is True
    assert g["openwisp2_firmware_upgrader"] is True
    assert g["openwisp2_radius"] is False
    assert g["openwisp2_controller_subnet_division"] is False
    assert g["openwisp2_time_zone"] == "Australia/Adelaide"


def test_tls_paths_follow_inventory_hostname_not_a_literal():
    """The cert path must track the site, so one shared value serves both."""
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    assert "{{ inventory_hostname }}" in g["openwisp2_ssl_cert"]
    assert "{{ inventory_hostname }}" in g["openwisp2_ssl_key"]


def test_nginx_ipv6_is_enabled():
    """The role defaults this off and emits IPv4-only listen lines.  monarto
    is reachable only over IPv6 from outside, so an IPv4-only nginx makes the
    admin UI unreachable; welland's IPv6 lines were added out-of-band and a
    re-run would have removed them."""
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    assert g["openwisp2_nginx_ipv6"] is True


def test_certbot_auto_renew_stays_off():
    """geerlingguy's cron would run as the wrong user; the packaged root
    certbot.timer does renewals instead."""
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    assert g["certbot_auto_renew"] is False


def test_playbook_has_no_site_specific_literals():
    body = (OW / "playbook.yml").read_text()
    for needle in ("welland", "monarto", "10.1.", "10.2."):
        assert needle not in body, needle


def test_playbook_still_runs_both_roles_in_order():
    """certbot FIRST: the cert must exist before openwisp's nginx points at
    it (role order = run order)."""
    pb = yaml.safe_load((OW / "playbook.yml").read_text())
    assert pb[0]["roles"] == ["geerlingguy.certbot", "openwisp.openwisp2"]


def test_firmware_map_survived_the_move():
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    blob = "\n".join(g["openwisp2_extra_django_settings_instructions"])
    for board in ("Google WiFi (Gale)", "Google Wifi", "OpenMesh OM2P-LC",
                  "OpenMesh OM2P v1", "OpenMesh OM2P v2", "OpenMesh OM2P v4"):
        assert board in blob


def test_firmware_validator_still_finds_the_map_after_the_move():
    """Regression guard: validate-firmware-images.py read the map out of
    playbook.yml's `vars:`.  Moving those vars to group_vars broke it with a
    bare KeyError, and nothing in the suite noticed -- asserting the map
    exists is not the same as asserting its CONSUMER can still load it."""
    vf = _load_script("validate-firmware-images.py", "validate_firmware_images")
    custom = vf.load_custom_images()
    _fw_map, reverse = vf.build_reverse_map(custom)
    for board, want in vf.EXPECT.items():
        assert reverse.get(board) == want, board


def test_influxdb_admin_password_is_never_set():
    """Setting it makes the sub-role create user `admin`, but
    openwisp-monitoring connects as `openwisp`, so writes fail."""
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    assert "influxdb_admin_password" not in g
