# SPDX-License-Identifier: Apache-2.0
"""Offline tests for openwisp/create-vm.py."""
import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

CV_PATH = Path(__file__).resolve().parents[3] / "openwisp" / "create-vm.py"


def _load():
    """Load the hyphenated script as a module.

    ``sys.modules[spec.name] = mod`` BEFORE ``exec_module`` is required, not
    optional: a module defining a dataclass under ``from __future__ import
    annotations`` makes dataclasses resolve its string annotations via
    ``sys.modules[cls.__module__].__dict__``.  Unregistered, that lookup
    returns None and the import dies with a bare
    ``AttributeError: 'NoneType' object has no attribute '__dict__'``.
    This ordering is also what the importlib docs' own recipe uses.
    """
    spec = importlib.util.spec_from_file_location("create_vm", CV_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_mac_for_ipv4_encodes_the_address():
    cv = _load()
    assert cv.mac_for_ipv4("10.2.4.2") == "02:00:0a:02:04:02"
    assert cv.mac_for_ipv4("10.1.4.2") == "02:00:0a:01:04:02"


def test_mac_for_ipv4_rejects_non_ipv4():
    cv = _load()
    with pytest.raises(ValueError):
        cv.mac_for_ipv4("2404:e80:a137:204::2")


def test_both_sites_present():
    cv = _load()
    assert set(cv.SITES) == {"welland", "monarto"}


def test_site_macs_agree_with_their_ipv4():
    """The table cannot drift: every site's MAC must encode its own IPv4."""
    cv = _load()
    for name, site in cv.SITES.items():
        assert site.mac == cv.mac_for_ipv4(site.ipv4), name


def test_monarto_matches_the_live_reservation():
    """Pins the values ten64.monarto's dhcp-host line already commits to."""
    cv = _load()
    m = cv.SITES["monarto"]
    assert m.mac == "02:00:0a:02:04:02"
    assert m.ipv4 == "10.2.4.2"
    assert m.ipv6 == "2404:e80:a137:204::2"
    assert m.bridge == "br-wifi"
    assert m.fqdn == "wisp.monarto.mithis.com"


def test_monarto_pins_ipv6_transport():
    """D5: monarto's IPv4 is a reverse proxy on another host."""
    cv = _load()
    assert "-6" in cv.SITES["monarto"].ssh_opts


RESERVATION = (
    "# wisp — DHCP\n"
    "dhcp-host=02:00:0a:02:04:02,10.2.4.2,[2404:e80:a137:204::2],wisp\n"
)


def test_parse_reservation_extracts_mac_and_ips():
    cv = _load()
    r = cv.parse_reservation(RESERVATION)
    assert r.mac == "02:00:0a:02:04:02"
    assert r.ipv4 == "10.2.4.2"
    assert r.ipv6 == "2404:e80:a137:204::2"


def test_parse_reservation_is_case_insensitive_on_mac():
    cv = _load()
    r = cv.parse_reservation("dhcp-host=02:00:0A:02:04:02,10.2.4.2,wisp\n")
    assert r.mac == "02:00:0a:02:04:02"


def test_parse_reservation_raises_when_absent():
    cv = _load()
    with pytest.raises(cv.PreflightError, match="no dhcp-host"):
        cv.parse_reservation("# nothing here\n")


def test_check_reservation_accepts_matching(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_read_reservation", lambda site: RESERVATION)
    cv.check_reservation(cv.SITES["monarto"])          # must not raise


def test_check_reservation_refuses_mac_mismatch(monkeypatch):
    cv = _load()
    wrong = "dhcp-host=02:00:0a:02:04:99,10.2.4.2,wisp\n"
    monkeypatch.setattr(cv, "_read_reservation", lambda site: wrong)
    with pytest.raises(cv.PreflightError, match="MAC"):
        cv.check_reservation(cv.SITES["monarto"])


def test_check_reservation_refuses_ip_mismatch(monkeypatch):
    cv = _load()
    wrong = "dhcp-host=02:00:0a:02:04:02,10.2.4.99,wisp\n"
    monkeypatch.setattr(cv, "_read_reservation", lambda site: wrong)
    with pytest.raises(cv.PreflightError, match="IPv4"):
        cv.check_reservation(cv.SITES["monarto"])


def test_domain_xml_is_wellformed_and_named():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.findtext("name") == "wisp"


def test_domain_xml_matches_welland_shape():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.findtext("memory") == "4194304"          # 4 GiB, as welland
    assert root.findtext("vcpu") == "2"
    os_type = root.find("os/type")
    assert os_type.get("arch") == "aarch64"


def test_domain_xml_does_not_pin_machine_version():
    """D6: welland pins virt-10.2 but the hosts run different QEMU."""
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.find("os/type").get("machine") == "virt"


def test_domain_xml_uses_uefi_loader():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.findtext("os/loader") == "/usr/share/AAVMF/AAVMF_CODE.ms.fd"


def test_domain_xml_nic_is_on_the_right_bridge_with_the_right_mac():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    iface = root.find("devices/interface")
    assert iface.find("source").get("bridge") == "br-wifi"
    assert iface.find("mac").get("address") == "02:00:0a:02:04:02"
    assert iface.find("model").get("type") == "virtio"


def test_domain_xml_has_virtio_root_and_seed_cdrom():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    targets = {d.find("target").get("dev"): d for d in root.findall("devices/disk")}
    assert targets["vda"].find("target").get("bus") == "virtio"
    assert targets["vda"].find("source").get("file").endswith("/wisp.qcow2")
    assert targets["sda"].find("source").get("file").endswith("/wisp-seed.iso")


def test_welland_xml_carries_its_own_identity():
    """The generator must be site-driven, not monarto-hardcoded."""
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["welland"]))
    assert root.find("devices/interface/mac").get("address") == "02:00:0a:01:04:02"


def test_network_config_is_static_on_the_sites_addresses():
    cv = _load()
    nc = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))
    eth = nc["network"]["ethernets"]["net0"]
    assert eth["dhcp4"] is False
    assert "10.2.4.2/24" in eth["addresses"]
    assert "2404:e80:a137:204::2/64" in eth["addresses"]


def test_network_config_matches_on_mac_and_renames_to_net0():
    cv = _load()
    eth = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))["network"]["ethernets"]["net0"]
    assert eth["match"]["macaddress"] == "02:00:0a:02:04:02"
    assert eth["set-name"] == "net0"


def test_network_config_has_both_default_routes():
    cv = _load()
    eth = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))["network"]["ethernets"]["net0"]
    vias = {r["via"] for r in eth["routes"]}
    assert vias == {"10.2.4.1", "2404:e80:a137:204::1"}


def test_network_config_resolver_is_the_site_router():
    cv = _load()
    eth = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))["network"]["ethernets"]["net0"]
    assert eth["nameservers"]["addresses"] == ["10.2.4.1"]


def test_user_data_sets_hostname_to_the_fqdn():
    cv = _load()
    ud = yaml.safe_load(cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test"))
    assert ud["fqdn"] == "wisp.monarto.mithis.com"


def test_user_data_disables_cloud_init_network_regeneration():
    cv = _load()
    ud = yaml.safe_load(cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test"))
    paths = {f["path"]: f for f in ud["write_files"]}
    target = "/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"
    assert paths[target]["content"].strip() == "network: {config: disabled}"


def test_user_data_creates_tim_with_passwordless_sudo_and_key():
    cv = _load()
    ud = yaml.safe_load(cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test"))
    user = next(u for u in ud["users"] if u["name"] == "tim")
    assert "NOPASSWD:ALL" in user["sudo"]
    assert user["ssh_authorized_keys"] == ["ssh-ed25519 AAAA test"]


def test_user_data_carries_no_password():
    """Access is by key only; a seed ISO is world-readable on the host."""
    cv = _load()
    raw = cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test")
    assert "password" not in raw.lower()


def test_meta_data_instance_id_is_site_specific():
    cv = _load()
    md = yaml.safe_load(cv.meta_data(cv.SITES["monarto"]))
    assert md["instance-id"] == "wisp-monarto"
    assert md["local-hostname"] == "wisp"


def test_check_bridge_accepts_present(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-wifi", "br-net"])
    cv.check_bridge(cv.SITES["monarto"])


def test_check_bridge_refuses_absent(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-net"])
    with pytest.raises(cv.PreflightError, match="br-wifi"):
        cv.check_bridge(cv.SITES["monarto"])


def test_check_no_existing_domain_refuses_when_defined(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_domains", lambda s: ["homeassistant", "wisp"])
    with pytest.raises(cv.PreflightError, match="already exists"):
        cv.check_no_existing_domain(cv.SITES["monarto"])


def test_check_no_existing_domain_passes_when_absent(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_domains", lambda s: ["homeassistant"])
    cv.check_no_existing_domain(cv.SITES["monarto"])


def test_cli_rejects_unknown_site(capsys):
    cv = _load()
    with pytest.raises(SystemExit):
        cv.main(["--site", "nowhere"])


def test_dry_run_makes_no_changes(monkeypatch, capsys):
    """--dry-run runs every pre-flight but must never mutate the target."""
    cv = _load()
    monkeypatch.setattr(cv, "_read_reservation", lambda s: RESERVATION)
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-wifi"])
    monkeypatch.setattr(cv, "_list_domains", lambda s: ["homeassistant"])

    def _boom(*a, **k):
        raise AssertionError("dry-run must not mutate the target")

    monkeypatch.setattr(cv, "_apply", _boom)
    assert cv.main(["--site", "monarto", "--dry-run",
                    "--ssh-key", "ssh-ed25519 AAAA test"]) == 0
    out = capsys.readouterr().out
    assert "02:00:0a:02:04:02" in out
    assert "<name>wisp</name>" in out


def test_dry_run_still_reports_preflight_failure(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_read_reservation",
                        lambda s: "dhcp-host=02:00:0a:02:04:99,10.2.4.2,wisp\n")
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-wifi"])
    monkeypatch.setattr(cv, "_list_domains", lambda s: [])
    assert cv.main(["--site", "monarto", "--dry-run",
                    "--ssh-key", "k"]) != 0
