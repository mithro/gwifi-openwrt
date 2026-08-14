# SPDX-License-Identifier: Apache-2.0
"""Per-site addressing for the gwifi netboot stack.

Every address this stack uses was hardcoded to welland's 10.1.4.2 -- in the
two systemd units, the CLI's --bind default, the netconsole receiver's
DEFAULT_BIND, and deploy.py (including its HostKeyAlias, which would have
made a monarto deploy check welland's SSH host key). This module is the one
place a site's numbering lives.

It also renders ``/etc/dnsmasq.d/gwifi.conf``. That file is what actually
serves DHCP + TFTP on the wifi VLAN, and it had never been captured in the
repository at all: welland's was hand-written on the box. monarto therefore
had NOTHING answering DHCP on VLAN 4 -- the site router deliberately sets
``no-dhcp-interface=br-wifi`` because serving that VLAN is wisp's job.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    """One site's wisp addressing."""

    name: str
    fqdn: str
    wisp_ip: str          # wisp's address on the wifi VLAN (VLAN 4)
    gateway: str          # the site router on that VLAN; also its DNS
    dhcp_range: tuple[str, str]
    # How the DEPLOYER reaches this wisp. welland's 10.1.4.2 routes from the
    # desktop over the VPN; monarto's does not -- monarto is IPv6-direct-only
    # (its A record is a reverse proxy on a DIFFERENT machine), so its deploy
    # must pin -6 and go by name.
    ssh_target: str = ""
    ssh_opts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.ssh_target:
            object.__setattr__(self, "ssh_target", f"tim@{self.wisp_ip}")


SITES: dict[str, Site] = {
    "welland": Site(
        name="welland",
        fqdn="wisp.welland.mithis.com",
        wisp_ip="10.1.4.2",
        gateway="10.1.4.1",
        dhcp_range=("10.1.4.100", "10.1.4.199"),
    ),
    "monarto": Site(
        name="monarto",
        fqdn="wisp.monarto.mithis.com",
        wisp_ip="10.2.4.2",
        gateway="10.2.4.1",
        dhcp_range=("10.2.4.100", "10.2.4.199"),
        ssh_target="tim@wisp.monarto.mithis.com",
        ssh_opts=("-6",),
    ),
}


def dnsmasq_conf(site: Site) -> str:
    """Render ``/etc/dnsmasq.d/gwifi.conf`` for a site.

    Mirrors the file running on wisp.welland. Two details are load-bearing:

    ``port=0`` -- wisp serves DHCP and TFTP only, NEVER DNS. Without it
    dnsmasq would bind :53 and shadow systemd-resolved on the box and the
    site router's resolver for anything that asked wisp.

    The ``.100-.199`` range -- the low addresses are statically reserved
    (.2 wisp, .3 tenwrt) and per-puck pins land in
    ``/etc/dnsmasq.d/gwifi-generated``, which gwifi-netboot owns and rewrites;
    never hand-edit that directory.
    """
    lo, hi = site.dhcp_range
    return f"""\
# gale puck netboot -- wisp serves DHCP + TFTP on the wifi VLAN ONLY; DNS and
# routing belong to the site router ({site.gateway}). Rendered by
# gwifi_netboot.sites for site {site.name!r} -- do not hand-edit.
port=0
# ^ no DNS at all: never shadows systemd-resolved, never answers :53.
bind-dynamic
interface=net0

# DHCP -- .3-.99 reserved static/infra, .100-.199 pucks (fixed via dhcp-host
# from gwifi-generated/) + dynamic fallback for an unknown gale.
dhcp-range={lo},{hi},255.255.255.0,1h
dhcp-authoritative
dhcp-rapid-commit
dhcp-option=option:router,{site.gateway}
dhcp-option=option:dns-server,{site.gateway}
log-dhcp

# TFTP for the installer FIT
enable-tftp
tftp-root=/srv/gwifi/tftp

# Per-puck identity + arming state -- owned by gwifi-netboot, never edit
conf-dir=/etc/dnsmasq.d/gwifi-generated
"""


def gwifi_images_vhost(site: Site) -> str:
    """Render ``/etc/nginx/sites-available/gwifi-images`` for a site.

    The netbooted installer fetches the factory image with

        uclient-fetch -O /tmp/factory.bin "http://$SERVER/$FILENAME"

    -- plain HTTP on port 80, addressed by IP literal, because all the
    installer knows is the ``tftpserverip=`` it was handed on the kernel
    command line.  So *something* must own Host ``<wisp_ip>`` on :80 and
    serve /srv/gwifi/images.

    Like the dnsmasq config, this existed ONLY as a hand-written file on
    wisp.welland.  monarto had no such vhost, and worse, its OpenWISP
    vhost claimed the bare IP itself -- the role builds

        server_name {{ inventory_hostname }}{% for h in openwisp2_allowed_hosts %} {{ h }}{% endfor %};

    so listing the IP in ``openwisp2_allowed_hosts`` handed :80 to
    OpenWISP, which 301s to HTTPS.  The minimal installer image has no
    TLS stack (and a cert could never match an IP), so the image fetch
    died there.  See the host_vars files: the bare IP belongs to THIS
    vhost, and devices reach OpenWISP by FQDN anyway.
    """
    return f"""\
# gale puck installer artifact server -- /srv/gwifi/images (factory.bin,
# manifest.json). Netbooted installers fetch by IP literal, so this vhost
# owns Host "{site.wisp_ip}" on :80; name-based requests still go to the
# OpenWISP vhost (which must NOT list the bare IP in server_name).
# Rendered by gwifi_netboot.sites for site {site.name!r} -- do not hand-edit.
server {{
    listen 80;
    server_name {site.wisp_ip};
    root /srv/gwifi/images;
    autoindex off;
    add_header Cache-Control "no-cache";
    location / {{ try_files $uri =404; }}
}}
"""


def netboot_unit(site: Site) -> str:
    """Render gwifi-netboot.service with the site's bind address."""
    return f"""\
# SPDX-License-Identifier: Apache-2.0
# gale puck netboot state + phone-home API -- see gwifi-openwrt
# docs/wisp-netboot-install-design.md (section 5.4).
# Rendered by gwifi_netboot.sites for site {site.name!r} -- do not hand-edit.
[Unit]
Description=gwifi puck netboot state + phone-home API
After=network-online.target dnsmasq.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/gwifi-netboot
# Pure-stdlib tool: system python3, no venv. Root: writes
# /etc/dnsmasq.d/gwifi-generated and restarts dnsmasq.
ExecStart=/usr/bin/python3 -m gwifi_netboot.cli serve --bind {site.wisp_ip}:8080
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
"""


def netconsole_unit(site: Site) -> str:
    """Render gwifi-netconsole.service.

    Binds 0.0.0.0, NOT the site address, on purpose. A puck that boots but
    never gets a DHCP lease cannot know its own address or wisp's (wisp is
    derived from the puck's), so ``gale-netconsole`` falls back to
    broadcasting its kernel log from an IPv4 link-local source. A socket
    bound to a specific unicast address never receives broadcast, so
    binding ``{site.wisp_ip}`` here would silently drop exactly the logs
    that matter most -- a puck too broken to get an address.

    Per-puck separation is unaffected: the receiver files by SOURCE ip.
    """
    return f"""\
# SPDX-License-Identifier: Apache-2.0
# Netconsole receiver for the gale fleet's kernel logs (no field serial).
# Rendered by gwifi_netboot.sites for site {site.name!r} -- do not hand-edit.
[Unit]
Description=gale fleet netconsole receiver (UDP 6666 -> /var/log/gale-netconsole)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/gwifi-netboot
ExecStart=/usr/bin/python3 -m gwifi_netboot.netconsole_rx --bind 0.0.0.0:6666
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
"""
