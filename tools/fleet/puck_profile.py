#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Switch gale pucks between network/wireless profiles.

Profiles:
  mesh    — the advanced batman-adv mesh architecture (the per-puck
            snapshot taken before the first switch to 'simple').
  simple  — 2026-07-22 simple AP profile:
              * wan = uplink trunk (VLAN 4 untagged/pvid + 20/90/99 tagged),
                carries the mgmt IP; lan = disabled (no link) after finalize.
              * six APs: ansells-iot (VLAN 90, high-compat/low-bandwidth),
                ansells (VLAN 20, high-bandwidth), ansells-guest (VLAN 99,
                high-bandwidth + client isolation) — each on 2.4 + 5 GHz.
              * no mesh/batman; usteer client steering on ansells +
                ansells-guest, talking over the mgmt network (uplink jack).
              * wireless is OpenWISP-managed: the 'gwifi-aps' template
                (openwisp/build-templates.py) carries this same six-AP
                set; the preserved mesh AP layer is 'gwifi-mesh-aps'
                (detached). Switching profiles later = puck_profile.py
                mesh/simple locally PLUS swapping which template is
                attached in OpenWISP.

Existing WPA keys are reused IN PLACE on each puck (read into the remote
shell only; they never leave the device).

Usage:
  uv run puck_profile.py status   [--puck NN]...
  uv run puck_profile.py simple   [--puck NN]...   # phase A: keeps lan up
  uv run puck_profile.py finalize [--puck NN]...   # phase B: after the cable
                                                   #   moved to the wan jack
  uv run puck_profile.py mesh     [--puck NN]...   # restore mesh snapshot
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from galeflash.livecollect import parse_pucks_conf

REGISTRY_HOST = "tim@10.1.4.2"
REGISTRY_PATH = "/etc/dnsmasq.d/gwifi-generated/pucks.conf"
SNAP_DIR = "/etc/gale-profiles"

SSH = ["ssh", "-4", "-o", "ConnectTimeout=30",
       "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=12",
       "-o", "StrictHostKeyChecking=accept-new"]


def ssh_run(ip: str, script: str, timeout: int = 180) -> subprocess.CompletedProcess:
    r = subprocess.run([*SSH, f"root@{ip}", script],
                       capture_output=True, text=True, timeout=timeout)
    if r.stderr.strip():
        print(r.stderr.rstrip(), file=sys.stderr)
    return r


# --------------------------------------------------------------------------
# Remote scripts (POSIX sh, executed on the puck)
# --------------------------------------------------------------------------

SNAPSHOT_SH = f"""
set -e
mkdir -p {SNAP_DIR}
if [ ! -f {SNAP_DIR}/mesh-network.uci ]; then
    uci export network  > {SNAP_DIR}/mesh-network.uci
    uci export wireless > {SNAP_DIR}/mesh-wireless.uci
    uci export usteer   > {SNAP_DIR}/mesh-usteer.uci || true
    echo "mesh snapshot taken"
else
    echo "mesh snapshot already present"
fi
"""

# Phase A: wan becomes the trunk but lan STAYS bridged so the puck remains
# reachable until the cable is physically moved to the wan jack.
SIMPLE_SH = f"""
set -e
MAC=$(uci -q get network.device_br0.macaddr || cat /sys/class/net/wan/address)
K_IOT=$(uci get wireless.wifi_wl_iot_2g4.key)
K_MAIN=$(uci get wireless.wifi_wl_main_2g4.key)
K_GUEST=$(uci get wireless.wifi_wl_guest_2g4.key)

# --- network: rebuild from scratch --------------------------------------
rm -f /etc/config/network
touch /etc/config/network
uci batch <<EOF
set network.loopback=interface
set network.loopback.device='lo'
set network.loopback.proto='static'
set network.loopback.ipaddr='127.0.0.1'
set network.loopback.netmask='255.0.0.0'
set network.globals=globals
set network.device_br0=device
set network.device_br0.name='br0'
set network.device_br0.type='bridge'
set network.device_br0.vlan_filtering='1'
set network.device_br0.stp='0'
set network.device_br0.macaddr='$MAC'
add_list network.device_br0.ports='wan'
add_list network.device_br0.ports='lan'
set network.brvlan4=bridge-vlan
set network.brvlan4.device='br0'
set network.brvlan4.vlan='4'
add_list network.brvlan4.ports='wan:u*'
add_list network.brvlan4.ports='lan:u*'
set network.brvlan20=bridge-vlan
set network.brvlan20.device='br0'
set network.brvlan20.vlan='20'
add_list network.brvlan20.ports='wan:t'
add_list network.brvlan20.ports='lan:t'
set network.brvlan90=bridge-vlan
set network.brvlan90.device='br0'
set network.brvlan90.vlan='90'
add_list network.brvlan90.ports='wan:t'
add_list network.brvlan90.ports='lan:t'
set network.brvlan99=bridge-vlan
set network.brvlan99.device='br0'
set network.brvlan99.vlan='99'
add_list network.brvlan99.ports='wan:t'
add_list network.brvlan99.ports='lan:t'
set network.mgmt=interface
set network.mgmt.device='br0.4'
set network.mgmt.proto='dhcp'
set network.roam=interface
set network.roam.device='br0.20'
set network.roam.proto='none'
set network.iot=interface
set network.iot.device='br0.90'
set network.iot.proto='none'
set network.guest=interface
set network.guest.device='br0.99'
set network.guest.proto='none'
EOF
uci commit network

# --- wireless: rebuild the wifi-ifaces (radios kept as-is) ---------------
for s in $(uci show wireless | grep -oE 'wireless\\.[a-z_0-9]+=wifi-iface' | cut -d. -f2 | cut -d= -f1); do
    uci delete wireless.$s
done
uci batch <<EOF
set wireless.wifi_wl_iot_2g4=wifi-iface
set wireless.wifi_wl_iot_2g4.device='radio0'
set wireless.wifi_wl_iot_2g4.ifname='wl-iot-2g4'
set wireless.wifi_wl_iot_2g4.mode='ap'
set wireless.wifi_wl_iot_2g4.ssid='ansells-iot'
set wireless.wifi_wl_iot_2g4.encryption='psk2+ccmp'
set wireless.wifi_wl_iot_2g4.key='$K_IOT'
set wireless.wifi_wl_iot_2g4.network='iot'
set wireless.wifi_wl_iot_2g4.dtim_period='3'
set wireless.wifi_wl_iot_2g4.legacy_rates='1'
set wireless.wifi_wl_iot_2g4.disassoc_low_ack='0'
set wireless.wifi_wl_iot_2g4.ieee80211w='0'
set wireless.wifi_wl_iot_5g=wifi-iface
set wireless.wifi_wl_iot_5g.device='radio1'
set wireless.wifi_wl_iot_5g.ifname='wl-iot-5g'
set wireless.wifi_wl_iot_5g.mode='ap'
set wireless.wifi_wl_iot_5g.ssid='ansells-iot'
set wireless.wifi_wl_iot_5g.encryption='psk2+ccmp'
set wireless.wifi_wl_iot_5g.key='$K_IOT'
set wireless.wifi_wl_iot_5g.network='iot'
set wireless.wifi_wl_iot_5g.dtim_period='3'
set wireless.wifi_wl_iot_5g.disassoc_low_ack='0'
set wireless.wifi_wl_iot_5g.ieee80211w='0'
set wireless.wifi_wl_main_2g4=wifi-iface
set wireless.wifi_wl_main_2g4.device='radio0'
set wireless.wifi_wl_main_2g4.ifname='wl-main-2g4'
set wireless.wifi_wl_main_2g4.mode='ap'
set wireless.wifi_wl_main_2g4.ssid='ansells'
set wireless.wifi_wl_main_2g4.encryption='psk2+ccmp'
set wireless.wifi_wl_main_2g4.key='$K_MAIN'
set wireless.wifi_wl_main_2g4.network='roam'
set wireless.wifi_wl_main_2g4.ieee80211w='1'
set wireless.wifi_wl_main_2g4.ieee80211k='1'
set wireless.wifi_wl_main_2g4.bss_transition='1'
set wireless.wifi_wl_main_5g=wifi-iface
set wireless.wifi_wl_main_5g.device='radio1'
set wireless.wifi_wl_main_5g.ifname='wl-main-5g'
set wireless.wifi_wl_main_5g.mode='ap'
set wireless.wifi_wl_main_5g.ssid='ansells'
set wireless.wifi_wl_main_5g.encryption='psk2+ccmp'
set wireless.wifi_wl_main_5g.key='$K_MAIN'
set wireless.wifi_wl_main_5g.network='roam'
set wireless.wifi_wl_main_5g.ieee80211w='1'
set wireless.wifi_wl_main_5g.ieee80211k='1'
set wireless.wifi_wl_main_5g.bss_transition='1'
set wireless.wifi_wl_guest_2g4=wifi-iface
set wireless.wifi_wl_guest_2g4.device='radio0'
set wireless.wifi_wl_guest_2g4.ifname='wl-guest-2g4'
set wireless.wifi_wl_guest_2g4.mode='ap'
set wireless.wifi_wl_guest_2g4.ssid='ansells-guest'
set wireless.wifi_wl_guest_2g4.encryption='psk2+ccmp'
set wireless.wifi_wl_guest_2g4.key='$K_GUEST'
set wireless.wifi_wl_guest_2g4.network='guest'
set wireless.wifi_wl_guest_2g4.isolate='1'
set wireless.wifi_wl_guest_2g4.ieee80211w='1'
set wireless.wifi_wl_guest_2g4.ieee80211k='1'
set wireless.wifi_wl_guest_2g4.bss_transition='1'
set wireless.wifi_wl_guest_5g=wifi-iface
set wireless.wifi_wl_guest_5g.device='radio1'
set wireless.wifi_wl_guest_5g.ifname='wl-guest-5g'
set wireless.wifi_wl_guest_5g.mode='ap'
set wireless.wifi_wl_guest_5g.ssid='ansells-guest'
set wireless.wifi_wl_guest_5g.encryption='psk2+ccmp'
set wireless.wifi_wl_guest_5g.key='$K_GUEST'
set wireless.wifi_wl_guest_5g.network='guest'
set wireless.wifi_wl_guest_5g.isolate='1'
set wireless.wifi_wl_guest_5g.ieee80211w='1'
set wireless.wifi_wl_guest_5g.ieee80211k='1'
set wireless.wifi_wl_guest_5g.bss_transition='1'
EOF
uci commit wireless

# --- usteer: steer only the high-bandwidth SSIDs over mgmt/wan -----------
uci -q delete usteer.@usteer[0].ssid_list || true
uci batch <<EOF
set usteer.@usteer[0].network='mgmt'
add_list usteer.@usteer[0].ssid_list='ansells'
add_list usteer.@usteer[0].ssid_list='ansells-guest'
set usteer.@usteer[0].local_mode='0'
set usteer.@usteer[0].assoc_steering='1'
set usteer.@usteer[0].load_balancing_threshold='0'
EOF
uci commit usteer

# --- services: openwisp stays enabled (the simple profile's wireless is
# --- delivered by the 'gwifi-aps' OpenWISP template since 2026-07-22 —
# --- see openwisp/build-templates.py; this local wireless write is just
# --- the bootstrap the agent then converges on), enable usteer ----------
/etc/init.d/openwisp-config enable
/etc/init.d/openwisp-monitoring enable
/etc/init.d/usteer enable
# gwifi-topology expects bat0 (mesh-only) — off in simple
/etc/init.d/gwifi-topology stop
/etc/init.d/gwifi-topology disable

# --- apply ---------------------------------------------------------------
/etc/init.d/network restart
sleep 8
wifi
sleep 8
/etc/init.d/usteer restart
echo SIMPLE-APPLIED
"""

# Phase B — jack-naming reality (verified fleet-wide 2026-07-22): gale's
# DTS port names are INVERTED relative to the case labels. The physical
# WAN (globe) jack is the netdev OpenWrt calls 'lan'; the physical LAN
# jack is netdev 'wan'.  The uplink cable lives in the physical WAN jack
# = netdev 'lan', so finalize keeps netdev 'lan' as the trunk and
# disables netdev 'wan' (the physical LAN jack — spec: no link).
FINALIZE_SH = """
set -e
if [ "$(cat /sys/class/net/lan/carrier)" != "1" ]; then
    echo "REFUSE: the uplink jack (netdev lan / physical WAN) has no carrier"
    exit 3
fi
uci del_list network.device_br0.ports='wan'
for v in brvlan4 brvlan20 brvlan90 brvlan99; do
    uci -q del_list network.$v.ports='wan:u*' || true
    uci -q del_list network.$v.ports='wan:t' || true
done
uci commit network
/etc/init.d/network reload
sleep 3
ip link set wan down
echo FINALIZED uplink_carrier=$(cat /sys/class/net/lan/carrier) physical_lan_jack=$(cat /sys/class/net/wan/operstate)
"""

MESH_RESTORE_SH = f"""
set -e
[ -f {SNAP_DIR}/mesh-network.uci ] || {{ echo "no mesh snapshot"; exit 4; }}
rm -f /etc/config/network /etc/config/wireless
touch /etc/config/network /etc/config/wireless
uci import network  < {SNAP_DIR}/mesh-network.uci
uci import wireless < {SNAP_DIR}/mesh-wireless.uci
[ -f {SNAP_DIR}/mesh-usteer.uci ] && {{ rm -f /etc/config/usteer; touch /etc/config/usteer; uci import usteer < {SNAP_DIR}/mesh-usteer.uci; }}
uci commit
/etc/init.d/openwisp-config enable
/etc/init.d/openwisp-monitoring enable
/etc/init.d/gwifi-topology enable
/etc/init.d/network restart
sleep 8
wifi
echo MESH-RESTORED
"""

STATUS_SH = """
echo "hostname=$(uname -n)"
echo "wan_carrier=$(cat /sys/class/net/wan/carrier 2>&1)"
echo "lan_state=$(cat /sys/class/net/lan/operstate 2>&1)"
echo "ssids=$(uci show wireless | grep ssid= | cut -d= -f2 | tr '\\n' ' ')"
echo "bat0=$(ip -br link show bat0 2>&1 | head -1)"
echo "usteer=$(/etc/init.d/usteer enabled && echo enabled || echo disabled)"
echo "openwisp=$(/etc/init.d/openwisp-config enabled && echo enabled || echo disabled)"
"""


def registry() -> dict:
    r = subprocess.run([*SSH, REGISTRY_HOST, f"sudo -n cat {REGISTRY_PATH}"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit("cannot read puck registry from wisp")
    return parse_pucks_conf(r.stdout)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["status", "simple", "finalize", "mesh"])
    ap.add_argument("--puck", action="append", type=int, metavar="NN")
    args = ap.parse_args()

    regs = registry()
    if args.puck:
        wanted = {f"puck{n:02d}" for n in args.puck}
        unknown = wanted - set(regs)
        if unknown:
            sys.exit(f"not in registry: {sorted(unknown)}")
        regs = {k: v for k, v in regs.items() if k in wanted}

    script = {"status": STATUS_SH, "simple": SNAPSHOT_SH + SIMPLE_SH,
              "finalize": FINALIZE_SH, "mesh": MESH_RESTORE_SH}[args.action]

    failed: list[str] = []
    for name in sorted(regs):
        ip = regs[name].ip
        print(f"===== {name} ({ip}) — {args.action}")
        try:
            r = ssh_run(ip, script)
            print(r.stdout.rstrip())
            if r.returncode == 255:
                print(f"  {name}: unreachable")
                failed.append(name)
            elif r.returncode != 0:
                print(f"  {name}: FAILED rc={r.returncode}")
                failed.append(name)
        except subprocess.TimeoutExpired:
            print(f"  {name}: TIMEOUT (may still be applying — check status)")
            failed.append(name)

    if failed:
        print(f"\nIncomplete on: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
