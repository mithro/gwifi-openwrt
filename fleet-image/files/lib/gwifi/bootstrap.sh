#!/bin/sh
# lib/gwifi/bootstrap.sh — shared first-boot wisp-connectivity functions
# (docs/fleet-image-base-design.md §4.2). Sourced by each image's
# /etc/uci-defaults/99-*-bootstrap driver. Everything here is the MINIMUM to
# reach the OpenWISP controller; APs, client VLAN legs, steering, lldpd and
# syslog are delivered by OpenWISP templates after the agent registers
# (gwifi-base post-reload-hook). Idempotent: fixed UCI section names.
# STP stays OFF everywhere: netifd's default bridge priority (0x7FFF)
# undercuts the switch fabric's 0x8000, so a fleet bridge speaking 802.1D
# would win STP root of the site L2 (bit the pucks on 2026-07-22).
# Tests stub `uci` in PATH and diff the recorded op sequence
# (tests/fleet-image/).

GWIFI_MGMT_VID=${GWIFI_MGMT_VID:-4}

# gwifi_find_device NAME -> echo "@device[i]" whose name option equals NAME;
# rc 1 when absent. (Board device sections are anonymous; index varies.)
gwifi_find_device() {
	_i=0
	while _n=$(uci -q get "network.@device[$_i].name"); do
		if [ "$_n" = "$1" ]; then echo "@device[$_i]"; return 0; fi
		_i=$((_i + 1))
	done
	return 1
}

# gwifi_adopt_board_bridge TRUNK — take the board-generated br-lan device
# section and turn it into vlan-aware br0 with TRUNK as its only port.
# rc 1 when br-lan does not exist yet (caller exits nonzero so uci-defaults
# keeps the script and retries next boot; a silent skip would self-delete it
# half-done).
gwifi_adopt_board_bridge() {
	GWIFI_BRDEV=$(gwifi_find_device br-lan) || return 1
	uci set "network.$GWIFI_BRDEV.name"='br0'
	uci set "network.$GWIFI_BRDEV.vlan_filtering"='1'
	uci set "network.$GWIFI_BRDEV.stp"='0'
	uci -q delete "network.$GWIFI_BRDEV.ports"
	uci add_list "network.$GWIFI_BRDEV.ports"="$1"
}

# gwifi_create_bridge TRUNK — create br0 from scratch (VM: a QEMU guest
# matches no armsr board case, so no board network config exists).
gwifi_create_bridge() {
	uci set network.br0dev="device"
	uci set network.br0dev.name='br0'
	uci set network.br0dev.type='bridge'
	uci set network.br0dev.vlan_filtering='1'
	uci set network.br0dev.stp='0'
	uci -q delete network.br0dev.ports
	uci add_list network.br0dev.ports="$1"
	GWIFI_BRDEV=br0dev
}

# gwifi_pin_bridge_mac FROMNAME — pin br0's MAC to FROMNAME's macaddr (gale:
# the label MAC lives on the eth-blue device section; the bridge otherwise
# picks a MAC by member-join timing, and BOTH the DHCP identity and the
# openwisp registration MAC come from the mgmt bridge). No-op when absent.
gwifi_pin_bridge_mac() {
	_from=$(gwifi_find_device "$1") || return 0
	_mac=$(uci -q get "network.$_from.macaddr")
	[ -n "$_mac" ] && uci set "network.$GWIFI_BRDEV.macaddr"="$_mac"
	return 0
}

# gwifi_mgmt_vlan PORTSPEC — mgmt bridge-vlan on br0. PORTSPEC e.g.
# 'eth-black:u*' (untagged+pvid; puck switch ports untag VLAN 4) or 'eth0:t'
# (tagged; ten64's br-raw trunk floods tagged frames).
gwifi_mgmt_vlan() {
	uci set network.brvlan_mgmt="bridge-vlan"
	uci set network.brvlan_mgmt.device='br0'
	uci set network.brvlan_mgmt.vlan="$GWIFI_MGMT_VID"
	uci -q delete network.brvlan_mgmt.ports
	uci add_list network.brvlan_mgmt.ports="$1"
}

# gwifi_mgmt_iface — default lan/wan/wan6 go away (the trunk lives in br0);
# mgmt = DHCP on br0.<vid> (wisp serves the lease).
gwifi_mgmt_iface() {
	uci -q delete network.lan
	uci -q delete network.wan
	uci -q delete network.wan6
	uci set network.mgmt="interface"
	uci set network.mgmt.device="br0.$GWIFI_MGMT_VID"
	uci set network.mgmt.proto='dhcp'
	uci commit network
}

# gwifi_dns_dhcp — no local DHCP server (wisp serves the mgmt VLAN); DNS
# rebind protection drops RFC1918 A answers from upstream — including the
# OpenWISP controller's — so whitelist the site domain (without this the
# agent cannot resolve wisp and never registers).
gwifi_dns_dhcp() {
	uci -q set dhcp.lan.ignore='1'
	uci -q del_list dhcp.@dnsmasq[0].rebind_domain='mithis.com'
	uci add_list dhcp.@dnsmasq[0].rebind_domain='mithis.com'
	uci -q commit dhcp
}

# gwifi_firewall_mgmt — mgmt joins the trusted zone (zone 0 = 'lan' in the
# default config) so ssh + the openwisp agent work; the stale 'lan' member is
# removed with the interface it referenced.
gwifi_firewall_mgmt() {
	uci -q del_list firewall.@zone[0].network='lan'
	uci -q del_list firewall.@zone[0].network='mgmt'
	uci add_list firewall.@zone[0].network='mgmt'
	uci commit firewall
}

# gwifi_openwisp_mac IFACE — per-image device-identity MAC source; the shared
# etc/config/openwisp ships without mac_interface (spec §4.2).
gwifi_openwisp_mac() {
	uci set openwisp.http.mac_interface="$1"
	uci commit openwisp
}
