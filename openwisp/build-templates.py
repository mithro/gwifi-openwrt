#!/usr/bin/env python3
"""Build the OpenWISP AP config templates + attach the active one to the pucks.

Two profiles exist (2026-07-22 restructure):

  simple (ACTIVE, template 'gwifi-aps') — the fleet's current config.
    Six APs, no mesh. The gale image/local config provides the network
    shape (vlan-aware br0 with the WAN jack as uplink trunk: VLAN 4
    untagged/pvid + 20/90/99 tagged; lan disabled; no batman — see
    tools/fleet/puck_profile.py). OpenWISP layers the SSIDs:
      wl-main-5g/-2g4  -> roam  (VLAN 20) 'ansells'       high-bandwidth,
                                          802.11k/v steering hints
      wl-iot-5g/-2g4   -> iot   (VLAN 90) 'ansells-iot'   high-compat: DTIM 3,
                                          legacy rates on 2.4, no PMF, never
                                          kick weak clients, no steering
      wl-guest-5g/-2g4 -> guest (VLAN 99) 'ansells-guest' high-bandwidth,
                                          client isolation
    Client steering is usteer, configured locally by puck_profile.py
    (netjsonconfig has no usteer schema); it talks over mgmt (the wan
    trunk) and steers only 'ansells'/'ansells-guest'.

  mesh-aps (PRESERVED, template 'gwifi-mesh-aps', attached to nothing) —
    the advanced-mesh-era 5-AP layer (WPA3 + 802.11r fast-roam main, no
    iot-5g). Kept so devices & network can be switched back to the mesh
    architecture later: restore the per-puck network snapshot with
    puck_profile.py mesh, then attach this template instead of gwifi-aps.

Secret handling: the 3 WiFi passphrases are read from ten64's hostapd configs;
none are ever printed or committed. They go into the templates' default_values
(OpenWISP DB on wisp, internal) as {{ }} substitutions and are piped to wisp
over SSH stdin (not argv). The verification render redacts all `option key`.
"""
import json
import subprocess
import sys

SSH_TEN64 = ["ssh", "ten64.welland.mithis.com"]
SSH_WISP = [
    "ssh", "-o", "ConnectTimeout=30", "wisp.welland.mithis.com",
    "sudo", "/opt/openwisp2/env/bin/python", "/opt/openwisp2/manage.py", "shell",
]

# The pucks (OpenWISP device names). No puck03 exists.
PUCKS = ["puck01", "puck02", "puck04", "puck05", "puck06",
         "puck07", "puck08", "puck09", "puck10", "puck11", "puck12"]

SSID_MAIN, SSID_IOT, SSID_GUEST = "ansells", "ansells-iot", "ansells-guest"


def parse_hostapd(text):
    """Map ssid -> wpa_passphrase across the main section + each bss= block."""
    out, ssid, pw = {}, None, None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("bss="):
            if ssid and pw:
                out[ssid] = pw
            ssid, pw = None, None
        elif line.startswith("ssid="):
            ssid = line.split("=", 1)[1]
        elif line.startswith("wpa_passphrase="):
            pw = line.split("=", 1)[1]
    if ssid and pw:
        out[ssid] = pw
    return out


def read_passphrases():
    cfgs = {}
    for fn in ("hostapd.wlan-roam.conf", "hostapd.wlan-iot.conf"):
        p = subprocess.run(SSH_TEN64 + ["sudo", "cat", f"/etc/hostapd/{fn}"],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            sys.stderr.write(p.stderr)
            raise SystemExit(f"failed to read {fn}")
        cfgs.update(parse_hostapd(p.stdout))
    need = {"ansells": "ansells_key", "ansells-iot": "iot_key",
            "ansells-guest": "guest_key"}
    vals = {}
    for ssid, var in need.items():
        if ssid not in cfgs or not cfgs[ssid]:
            raise SystemExit(f"could not find passphrase for SSID {ssid!r}")
        vals[var] = cfgs[ssid]
    return vals


def _wpa2(key):
    return {"protocol": "wpa2_personal", "cipher": "ccmp", "key": key}


def netjson_simple():
    """Six-AP simple profile — must render to the same effective config
    puck_profile.py applies locally (psk2+ccmp everywhere; matching per-BSS
    tuning) so agent applies converge instead of churning."""
    steer = {"ieee80211k": True, "bss_transition": True, "ieee80211w": "1"}
    iot = {"dtim_period": 3, "disassoc_low_ack": False, "ieee80211w": "0"}

    def ap(name, radio, ssid, network, key, **extra):
        return {"name": name, "type": "wireless", "wireless": dict(
            radio=radio, mode="access_point", ssid=ssid,
            network=[network], encryption=_wpa2(key), **extra)}

    radios = [
        {"name": "radio0", "driver": "mac80211", "protocol": "802.11n",
         "channel": 6, "channel_width": 20},
        {"name": "radio1", "driver": "mac80211", "protocol": "802.11ac",
         "channel": 36, "channel_width": 80},
    ]
    return {"radios": radios, "interfaces": [
        ap("wl-main-5g", "radio1", SSID_MAIN, "roam", "{{ ansells_key }}", **steer),
        ap("wl-main-2g4", "radio0", SSID_MAIN, "roam", "{{ ansells_key }}", **steer),
        ap("wl-iot-5g", "radio1", SSID_IOT, "iot", "{{ iot_key }}", **iot),
        ap("wl-iot-2g4", "radio0", SSID_IOT, "iot", "{{ iot_key }}",
           legacy_rates=True, **iot),
        ap("wl-guest-5g", "radio1", SSID_GUEST, "guest", "{{ guest_key }}",
           isolate=True, **steer),
        ap("wl-guest-2g4", "radio0", SSID_GUEST, "guest", "{{ guest_key }}",
           isolate=True, **steer),
    ]}


def netjson_mesh_aps():
    """The advanced-mesh-era AP layer (preserved, unattached): WPA3 +
    802.11r/k/v fast-roam main, single-band iot, WPA2 guest."""
    def wpa3(key):
        return {"protocol": "wpa3_personal", "cipher": "ccmp",
                "ieee80211w": "2", "key": key}

    roam = {"ieee80211r": True, "mobility_domain": "a1b2",
            "ft_psk_generate_local": True, "ieee80211k": True,
            "bss_transition": True}
    return {"interfaces": [
        {"name": "wl-main-5g", "type": "wireless", "wireless": dict(
            radio="radio1", mode="access_point", ssid=SSID_MAIN,
            network=["roam"], encryption=wpa3("{{ ansells_key }}"), **roam)},
        {"name": "wl-main-2g4", "type": "wireless", "wireless": dict(
            radio="radio0", mode="access_point", ssid=SSID_MAIN,
            network=["roam"], encryption=wpa3("{{ ansells_key }}"), **roam)},
        {"name": "wl-iot-2g4", "type": "wireless", "wireless": dict(
            radio="radio0", mode="access_point", ssid=SSID_IOT,
            network=["iot"], encryption=_wpa2("{{ iot_key }}"))},
        {"name": "wl-guest-5g", "type": "wireless", "wireless": dict(
            radio="radio1", mode="access_point", ssid=SSID_GUEST,
            network=["guest"], encryption=_wpa2("{{ guest_key }}"),
            isolate=True)},
        {"name": "wl-guest-2g4", "type": "wireless", "wireless": dict(
            radio="radio0", mode="access_point", ssid=SSID_GUEST,
            network=["guest"], encryption=_wpa2("{{ guest_key }}"),
            isolate=True)},
    ]}


LLDPD_CONFIG = """config lldpd 'config'
	# Announce on the physical jacks only (both port-name generations are
	# listed; the init resolves the ones that exist on this device).
	list interface 'eth-black'
	list interface 'eth-blue'
	list interface 'lan'
	list interface 'wan'
	option enable_cdp 1
	option enable_fdp 1
	option enable_sonmp 1
	option enable_edp 1
	option lldp_class 4
"""

USTEER_CONFIG = """config usteer
	option network 'mgmt'
	option local_mode '0'
	option assoc_steering '1'
	option load_balancing_threshold '0'
	list ssid_list 'ansells'
	list ssid_list 'ansells-guest'
"""

CRONTAB = """# lldpd snapshots the hostname at start; reassert so renames propagate.
*/5 * * * * lldpcli configure system hostname "$(uname -n)"
"""

POST_RELOAD_HOOK = """#!/bin/sh
# openwisp post-reload-hook (delivered by the gwifi-base template):
# device state the agent cannot express as plain uci-file templates.

# Client VLANs tagged on the trunk (mgmt VLAN 4 is baked in the image).
TRUNK=eth-black
[ -e /sys/class/net/eth-black ] || TRUNK=lan
for kv in roam=20 iot=90 guest=99; do
	name=${kv%=*}; vid=${kv#*=}
	uci set network.brvlan_$name="bridge-vlan"
	uci set network.brvlan_$name.device='br0'
	uci set network.brvlan_$name.vlan="$vid"
	uci -q delete network.brvlan_$name.ports
	uci add_list network.brvlan_$name.ports="$TRUNK:t"
	uci set network.$name="interface"
	uci set network.$name.device="br0.$vid"
	uci set network.$name.proto='none'
done
uci commit network

# wifi-detect's placeholder ifaces must never beacon the OpenWrt SSID.
uci -q delete wireless.default_radio0
uci -q delete wireless.default_radio1
uci -q commit wireless

# Remote syslog to wisp.
uci set system.@system[0].log_ip='10.1.4.2'
uci set system.@system[0].log_port='6666'
uci set system.@system[0].log_proto='udp'
uci commit system

/etc/init.d/lldpd enable
/etc/init.d/lldpd restart
/etc/init.d/usteer enable
/etc/init.d/usteer restart
/etc/init.d/cron enable
/etc/init.d/cron restart
exit 0
"""


def netjson_base():
    """Fleet-base config delivered by wisp: lldpd, steering, cron, and a
    post-reload hook for the pieces that are not uci-file templates."""
    return {"files": [
        {"path": "/etc/config/lldpd", "mode": "0644",
         "contents": LLDPD_CONFIG},
        {"path": "/etc/config/usteer", "mode": "0644",
         "contents": USTEER_CONFIG},
        {"path": "/etc/crontabs/root", "mode": "0600",
         "contents": CRONTAB},
        {"path": "/etc/openwisp/post-reload-hook", "mode": "0755",
         "contents": POST_RELOAD_HOOK},
    ]}


DJANGO = r'''
import json, re
from swapper import load_model
Template = load_model("config", "Template")
Config = load_model("config", "Config")
Org = load_model("openwisp_users", "Organization")
Device = load_model("config", "Device")
org = Org.objects.get(slug="default")
ACTIVE = json.loads({active!r})
PRESERVED = json.loads({preserved!r})
BASE = json.loads({base!r})
DEFAULTS = json.loads({defaults!r})
PUCKS = {pucks!r}

b, bcreated = Template.objects.update_or_create(
    organization=org, name="gwifi-base",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=BASE, default=False),
)
b.full_clean(); b.save()
print("gwifi-base:", "created" if bcreated else "updated", "id=", b.id)

# Active template: 'gwifi-aps' (already attached fleet-wide) now carries the
# simple six-AP profile.
t, created = Template.objects.update_or_create(
    organization=org, name="gwifi-aps",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=ACTIVE, default=False, default_values=DEFAULTS),
)
t.full_clean(); t.save()
print("gwifi-aps:", "created" if created else "updated", "id=", t.id)

# Preserved template: 'gwifi-mesh-aps' exists but is attached to nothing.
m, mcreated = Template.objects.update_or_create(
    organization=org, name="gwifi-mesh-aps",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=PRESERVED, default=False, default_values=DEFAULTS),
)
m.full_clean(); m.save()
detached = 0
for c in Config.objects.filter(templates=m):
    c.templates.remove(m); detached += 1
print("gwifi-mesh-aps:", "created" if mcreated else "updated",
      "id=", m.id, "detached-from:", detached)

attached = 0
missing = []
for name in PUCKS:
    try:
        d = Device.objects.get(organization=org, name=name)
    except Device.DoesNotExist:
        missing.append(name); continue
    c, _ = Config.objects.get_or_create(device=d, defaults=dict(backend="netjsonconfig.OpenWrt"))
    for tpl in (b, t):
        if tpl not in c.templates.all():
            c.templates.add(tpl)
    c.full_clean(); c.save()
    attached += 1
print("configs attached:", attached, "/", len(PUCKS), "missing:", missing)

# verification render of an online puck, passphrases redacted
d = Device.objects.get(organization=org, name="puck12")
rendered = d.config.backend_instance.render()
rendered = re.sub(r"(option key ').*?(')", r"\g<1><REDACTED>\g<2>", rendered)
print("=" * 60)
print("puck12 rendered config (keys redacted):")
print("=" * 60)
print(rendered)
'''


def main() -> int:
    vals = read_passphrases()
    script = DJANGO.format(active=json.dumps(netjson_simple()),
                           preserved=json.dumps(netjson_mesh_aps()),
                           base=json.dumps(netjson_base()),
                           defaults=json.dumps(vals), pucks=PUCKS)
    p = subprocess.run(SSH_WISP, input=script, text=True, capture_output=True,
                       timeout=180)
    # safety: redact any stray key values from the captured output before printing
    out = p.stdout
    for v in vals.values():
        out = out.replace(v, "<REDACTED>")
    sys.stdout.write(out)
    if p.stderr.strip():
        err = p.stderr
        for v in vals.values():
            err = err.replace(v, "<REDACTED>")
        sys.stderr.write("\n--- stderr ---\n" + err)
    print("\n(secrets: ansells/iot/guest sourced from ten64 hostapd; never "
          "printed or committed)")
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
