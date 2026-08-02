# SPDX-License-Identifier: Apache-2.0
"""The netboot stack must be site-parameterised, not welland-only."""
import pytest

from gwifi_netboot import sites


def test_both_sites_present():
    assert set(sites.SITES) == {"welland", "monarto"}


def test_welland_matches_the_deployed_values():
    """Pins what wisp.welland actually runs today, so parameterising cannot
    silently change the working site."""
    s = sites.SITES["welland"]
    assert s.wisp_ip == "10.1.4.2"
    assert s.gateway == "10.1.4.1"
    assert s.fqdn == "wisp.welland.mithis.com"
    assert s.dhcp_range == ("10.1.4.100", "10.1.4.199")


def test_monarto_mirrors_welland_on_its_own_subnet():
    s = sites.SITES["monarto"]
    assert s.wisp_ip == "10.2.4.2"
    assert s.gateway == "10.2.4.1"
    assert s.fqdn == "wisp.monarto.mithis.com"
    assert s.dhcp_range == ("10.2.4.100", "10.2.4.199")


def test_every_site_is_internally_consistent():
    """gateway/.2/range must all sit in the same /24 -- a typo here would
    hand pucks a lease they cannot route from."""
    for name, s in sites.SITES.items():
        prefix = s.wisp_ip.rsplit(".", 1)[0]
        assert s.gateway.startswith(prefix + "."), name
        assert s.dhcp_range[0].startswith(prefix + "."), name
        assert s.dhcp_range[1].startswith(prefix + "."), name


def test_dhcp_range_does_not_collide_with_infrastructure():
    """.2 is wisp itself and .3 is tenwrt; the dynamic pool must start above
    the statically-reserved low addresses."""
    for name, s in sites.SITES.items():
        first = int(s.dhcp_range[0].rsplit(".", 1)[1])
        last = int(s.dhcp_range[1].rsplit(".", 1)[1])
        assert first > 3, name
        assert first < last < 255, name


# --- dnsmasq config rendering ------------------------------------------------
# welland's /etc/dnsmasq.d/gwifi.conf was hand-written on the box and never
# captured here, which is why monarto had nothing serving DHCP/TFTP on VLAN 4.


def test_dnsmasq_conf_serves_dhcp_and_tftp_but_never_dns():
    """port=0 is load-bearing: wisp must never answer :53 and shadow the
    site router's resolver."""
    conf = sites.dnsmasq_conf(sites.SITES["monarto"])
    assert "port=0" in conf
    assert "enable-tftp" in conf
    assert "tftp-root=/srv/gwifi/tftp" in conf
    assert "dhcp-range=10.2.4.100,10.2.4.199,255.255.255.0,1h" in conf


def test_dnsmasq_conf_points_clients_at_the_site_router():
    conf = sites.dnsmasq_conf(sites.SITES["monarto"])
    assert "dhcp-option=option:router,10.2.4.1" in conf
    assert "dhcp-option=option:dns-server,10.2.4.1" in conf


def test_dnsmasq_conf_is_authoritative_and_binds_one_interface():
    conf = sites.dnsmasq_conf(sites.SITES["monarto"])
    assert "dhcp-authoritative" in conf
    assert "bind-dynamic" in conf
    assert "interface=net0" in conf


def test_dnsmasq_conf_includes_the_generated_dir():
    """gwifi-netboot owns per-puck identity/arming fragments in there."""
    conf = sites.dnsmasq_conf(sites.SITES["monarto"])
    assert "conf-dir=/etc/dnsmasq.d/gwifi-generated" in conf


def test_dnsmasq_conf_is_site_specific():
    """A welland render must not leak into monarto's file."""
    conf = sites.dnsmasq_conf(sites.SITES["monarto"])
    assert "10.1.4." not in conf


def test_welland_dnsmasq_conf_reproduces_the_live_file():
    conf = sites.dnsmasq_conf(sites.SITES["welland"])
    assert "dhcp-range=10.1.4.100,10.1.4.199,255.255.255.0,1h" in conf
    assert "dhcp-option=option:router,10.1.4.1" in conf


# --- nginx image-server vhost ------------------------------------------------
# The installer fetches the factory image over plain HTTP on :80 by IP
# literal.  welland served that from a hand-written vhost that was never in
# the repo; monarto had none AND its OpenWISP vhost claimed the bare IP, so
# the fetch got a 301 to HTTPS the installer cannot follow.


def test_images_vhost_owns_the_bare_ip_on_port_80():
    conf = sites.gwifi_images_vhost(sites.SITES["monarto"])
    assert "listen 80;" in conf
    assert "server_name 10.2.4.2;" in conf


def test_images_vhost_serves_the_published_image_dir():
    conf = sites.gwifi_images_vhost(sites.SITES["monarto"])
    assert "root /srv/gwifi/images;" in conf


def test_images_vhost_never_redirects_to_https():
    """A 301 to https:// is exactly what broke monarto: the minimal
    installer has no TLS stack, and a cert cannot match an IP."""
    conf = sites.gwifi_images_vhost(sites.SITES["monarto"])
    assert "return 301" not in conf
    assert "https" not in conf


def test_images_vhost_is_site_specific():
    conf = sites.gwifi_images_vhost(sites.SITES["monarto"])
    assert "10.1.4." not in conf


def test_welland_images_vhost_reproduces_the_live_file():
    """Pins the file that is already serving welland's installs."""
    conf = sites.gwifi_images_vhost(sites.SITES["welland"])
    assert "server_name 10.1.4.2;" in conf
    assert "root /srv/gwifi/images;" in conf
    assert "autoindex off;" in conf


def test_images_vhost_does_not_list_a_hostname():
    """If it also answered to the FQDN it would shadow OpenWISP's vhost."""
    for name in sites.SITES:
        conf = sites.gwifi_images_vhost(sites.SITES[name])
        assert "mithis.com" not in conf.split("server {")[1]


# --- systemd unit rendering --------------------------------------------------


def test_netboot_unit_binds_the_sites_address():
    unit = sites.netboot_unit(sites.SITES["monarto"])
    assert "--bind 10.2.4.2:8080" in unit
    assert "10.1.4.2" not in unit


def test_netconsole_unit_binds_the_sites_address():
    unit = sites.netconsole_unit(sites.SITES["monarto"])
    assert "--bind 10.2.4.2:6666" in unit
    assert "10.1.4.2" not in unit


def test_units_keep_their_ordering_and_restart_policy():
    unit = sites.netboot_unit(sites.SITES["monarto"])
    assert "After=network-online.target dnsmasq.service" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=multi-user.target" in unit


def test_unknown_site_raises():
    with pytest.raises(KeyError):
        _ = sites.SITES["nowhere"]


# --- deploy transport --------------------------------------------------------


def test_welland_deploys_over_its_routable_address():
    s = sites.SITES["welland"]
    assert s.ssh_target == "tim@10.1.4.2"
    assert s.ssh_opts == ()


def test_monarto_deploys_by_name_over_ipv6():
    """monarto's 10.2.4.2 does not route from the desktop, and its A record is
    a reverse proxy on a DIFFERENT machine -- so the deploy must pin -6."""
    s = sites.SITES["monarto"]
    assert s.ssh_target == "tim@wisp.monarto.mithis.com"
    assert "-6" in s.ssh_opts
