#!/usr/bin/env python3
"""Build the OpenWISP AP config templates + attach them to the fleet.

Template family (renamed 2026-07-26 from the gwifi-* names; the script renames
in place so existing attachments — which reference template ids — ride along):

  ansells-aps-base    (was gwifi-base)     lldpd/usteer/cron + post-reload-hook
  ansells-aps-puck    (was gwifi-aps)      six-AP dual-band puck layer (ACTIVE)
  ansells-aps-tenwrt  (new)                three-AP 5 GHz-only VM layer
  ansells-aps-mesh    (was gwifi-mesh-aps) preserved mesh-era layer, unattached

Two puck profiles exist (2026-07-22 restructure):

  simple (ACTIVE, template 'ansells-aps-puck') — the fleet's current config.
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

  mesh-aps (PRESERVED, template 'ansells-aps-mesh', attached to nothing) —
    the advanced-mesh-era 5-AP layer (WPA3 + 802.11r fast-roam main, no
    iot-5g). Kept so devices & network can be switched back to the mesh
    architecture later: restore the per-puck network snapshot with
    puck_profile.py mesh, then attach this template instead of
    ansells-aps-puck.

Secret handling: the 3 WiFi passphrases are read from ten64's hostapd configs;
none are ever printed or committed. They go into the templates' default_values
(OpenWISP DB on wisp, internal) as {{ }} substitutions and are piped to wisp
over SSH stdin (not argv). The verification render redacts all `option key`.

tenwrt VM parity (fleet-image-base-plan.md Task 13, revised 2026-07-26): the
ten64 VM (device name 'tenwrt') attaches to ansells-aps-base +
ansells-aps-tenwrt. Its MT7915 is hardware-bonded non-DBDC (MT_HW_BOUND bit 5
clear -> ONE phy, 4x4, one band at a time), so the VM serves the three SSIDs
on 5 GHz only — 2.4 GHz coverage stays with the pucks. It has no physical
jacks, so the base post-reload-hook falls back to the virtio trunk eth0 when
neither puck jack name (eth-black/lan) exists.
"""
import json
import subprocess
import sys
from pathlib import Path

PRESENCE_DIR = Path(__file__).resolve().parent / "presence"

SSH_TEN64 = ["ssh", "ten64.welland.mithis.com"]
SSH_WISP = [
    "ssh", "-o", "ConnectTimeout=30", "wisp.welland.mithis.com",
    "sudo", "/opt/openwisp2/env/bin/python", "/opt/openwisp2/manage.py", "shell",
]

# The pucks (OpenWISP device names). puck03 registered 2026-07-25 (fresh install).
PUCKS = ["puck01", "puck02", "puck03", "puck04", "puck05", "puck06",
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


# Per-BSS tuning shared by the puck and tenwrt AP templates.
STEER = {"ieee80211k": True, "bss_transition": True, "ieee80211w": "1"}
IOT = {"dtim_period": 3, "disassoc_low_ack": False, "ieee80211w": "0"}


def _ap(name, radio, ssid, network, key, **extra):
    return {"name": name, "type": "wireless", "wireless": dict(
        radio=radio, mode="access_point", ssid=ssid,
        network=[network], encryption=_wpa2(key), **extra)}


def netjson_simple():
    """Six-AP simple profile — must render to the same effective config
    puck_profile.py applies locally (psk2+ccmp everywhere; matching per-BSS
    tuning) so agent applies converge instead of churning."""
    radios = [
        {"name": "radio0", "driver": "mac80211", "protocol": "802.11n",
         "channel": 6, "channel_width": 20},
        {"name": "radio1", "driver": "mac80211", "protocol": "802.11ac",
         "channel": 36, "channel_width": 80},
    ]
    return {"radios": radios, "interfaces": [
        _ap("wl-main-5g", "radio1", SSID_MAIN, "roam", "{{ ansells_key }}", **STEER),
        _ap("wl-main-2g4", "radio0", SSID_MAIN, "roam", "{{ ansells_key }}", **STEER),
        _ap("wl-iot-5g", "radio1", SSID_IOT, "iot", "{{ iot_key }}", **IOT),
        _ap("wl-iot-2g4", "radio0", SSID_IOT, "iot", "{{ iot_key }}",
            legacy_rates=True, **IOT),
        _ap("wl-guest-5g", "radio1", SSID_GUEST, "guest", "{{ guest_key }}",
            isolate=True, **STEER),
        _ap("wl-guest-2g4", "radio0", SSID_GUEST, "guest", "{{ guest_key }}",
            isolate=True, **STEER),
    ]}


def netjson_tenwrt_aps():
    """tenwrt VM AP layer: single 5 GHz-only radio (MT7915 bonded non-DBDC),
    same SSIDs/keys/zones/tuning as the puck template minus the 2.4 GHz BSSes.
    802.11ax: the VM's mt7915 does HE80 (the pucks' IPQ4019 is ac-only), and
    channel 36 matches the fleet-wide 5 GHz roaming plan."""
    radios = [
        {"name": "radio0", "driver": "mac80211", "protocol": "802.11ax",
         "channel": 36, "channel_width": 80},
    ]
    return {"radios": radios, "interfaces": [
        _ap("wl-main-5g", "radio0", SSID_MAIN, "roam", "{{ ansells_key }}", **STEER),
        _ap("wl-iot-5g", "radio0", SSID_IOT, "iot", "{{ iot_key }}", **IOT),
        _ap("wl-guest-5g", "radio0", SSID_GUEST, "guest", "{{ guest_key }}",
            isolate=True, **STEER),
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
# openwisp post-reload-hook (delivered by the ansells-aps-base template):
# device state the agent cannot express as plain uci-file templates.

# Client VLANs tagged on the trunk (mgmt VLAN 4 is baked in the image).
TRUNK=eth-black
[ -e /sys/class/net/eth-black ] || TRUNK=lan
# tenwrt VM: no physical jacks; the virtio trunk is eth0. Pucks always match
# one of the two names above (gale's own eth0 is the DSA conduit — order
# matters), so only the VM falls through to here.
[ -e "/sys/class/net/$TRUNK" ] || TRUNK=eth0
[ "$TRUNK" = eth0 ] && logger -t post-reload-hook "trunk fell through to eth0 (expected only on the tenwrt VM)"
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

# Remote syslog to the site router's wifi leg (per-net remote syslog
# design, gdoc2netcfg 2026-07-30): /var/log/wifi/<hostname>.log on ten64.
# {{ syslog_ip }} comes from the template default_values (site default
# 10.1.4.1; override per device/group for other sites). Kernel netconsole
# to wisp:6666 is separate and unchanged.
uci set system.@system[0].log_ip='{{ syslog_ip }}'
uci set system.@system[0].log_port='514'
uci set system.@system[0].log_proto='udp'
uci commit system
# logd reads log_ip/log_port only at start — without this restart the
# committed target sits unused until the next reboot (proven live on
# puck07 2026-08-01: nothing reached the ten64 leg until `log` restarted).
/etc/init.d/log restart

# lldpd announces on the physical jacks (config file from this template);
# ensure the detected trunk is in the list — no-op on pucks (their jacks are
# pre-listed), adds the virtio eth0 on the tenwrt VM. Runs after every apply
# because the template rewrites /etc/config/lldpd each time.
if ! uci -q get lldpd.config.interface | tr ' ' '\n' | grep -qx "$TRUNK"; then
	uci add_list lldpd.config.interface="$TRUNK"
	uci commit lldpd
fi
/etc/init.d/lldpd enable
/etc/init.d/lldpd restart
/etc/init.d/usteer enable
/etc/init.d/usteer restart
/etc/init.d/cron enable
/etc/init.d/cron restart

# presence-detector (ansells-presence template); python3 arrives via
# tools/fleet/deploy_presence.py — silently skip until both pieces exist.
if [ -x /etc/init.d/presence-detector ] && [ -x /usr/bin/python3 ]; then
	/etc/init.d/presence-detector enable
	/etc/init.d/presence-detector restart
fi
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


PRESENCE_SETTINGS = """{
  "mqtt_host": "ha.welland.mithis.com",
  "mqtt_port": 1883,
  "mqtt_username": "{{ mqtt_username }}",
  "mqtt_password": "{{ mqtt_password }}",
  "mqtt_retain_state": true,
  "interfaces": [],
  "filter_is_denylist": true,
  "filter": [],
  "params": {},
  "ap_name": "{{ name }}",
  "fallback_sync_interval": 60,
  "source_type": "router",
  "debug": false
}
"""


def netjson_presence():
    """presence-detector delivery: vendored script + per-device settings + init.

    Credentials arrive per device via Config.context (set_device_vars.py);
    {{ name }} is OpenWISP's built-in device-name variable, so ap_name gives
    the per-puck entity prefix (design spec 'Entity model')."""
    return {"files": [
        {"path": "/opt/presence-detector/presence-detector.py", "mode": "0755",
         "contents": (PRESENCE_DIR / "presence-detector.py").read_text()},
        {"path": "/etc/presence-detector/settings.json", "mode": "0600",
         "contents": PRESENCE_SETTINGS},
        {"path": "/etc/init.d/presence-detector", "mode": "0755",
         "contents": (PRESENCE_DIR / "init.d-presence-detector").read_text()},
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
TENWRT = json.loads({tenwrt!r})
PRESERVED = json.loads({preserved!r})
BASE = json.loads({base!r})
PRESENCE = json.loads({presence!r})
DEFAULTS = json.loads({defaults!r})
PUCKS = {pucks!r}
# Devices the templates attach to: the pucks + the ten64 VM. The attach loop
# skips names that have not registered yet — re-run this script after the
# tenwrt VM's first successful registration (design spec §4.6).
DEVICES = PUCKS + ["tenwrt"]

# One-time rename of the pre-2026-07-26 gwifi-* template names. Must run
# before the upserts: update_or_create keys on name, so without this the new
# names would CREATE duplicates while the old templates stayed attached.
# Renaming in place keeps ids, so existing puck attachments ride along.
RENAMES = [("gwifi-base", "ansells-aps-base"),
           ("gwifi-aps", "ansells-aps-puck"),
           ("gwifi-mesh-aps", "ansells-aps-mesh")]
for old, new in RENAMES:
    oldq = Template.objects.filter(organization=org, name=old)
    if not oldq.exists():
        continue
    if Template.objects.filter(organization=org, name=new).exists():
        print("WARNING: both", old, "and", new, "exist; leaving", old,
              "alone — resolve the duplicate by hand")
        continue
    tpl = oldq.get()
    tpl.name = new
    tpl.full_clean(); tpl.save()
    print("renamed template:", old, "->", new)

b, bcreated = Template.objects.update_or_create(
    organization=org, name="ansells-aps-base",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=BASE, default=False),
)
b.full_clean(); b.save()
print("ansells-aps-base:", "created" if bcreated else "updated", "id=", b.id)

# Active puck template: 'ansells-aps-puck' (already attached fleet-wide)
# carries the simple six-AP dual-band profile.
t, created = Template.objects.update_or_create(
    organization=org, name="ansells-aps-puck",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=ACTIVE, default=False, default_values=DEFAULTS),
)
t.full_clean(); t.save()
print("ansells-aps-puck:", "created" if created else "updated", "id=", t.id)

# tenwrt template: three-AP 5 GHz-only layer for the single-phy MT7915 VM.
tw, twcreated = Template.objects.update_or_create(
    organization=org, name="ansells-aps-tenwrt",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=TENWRT, default=False, default_values=DEFAULTS),
)
tw.full_clean(); tw.save()
print("ansells-aps-tenwrt:", "created" if twcreated else "updated", "id=", tw.id)

# Preserved template: 'ansells-aps-mesh' exists but is attached to nothing.
m, mcreated = Template.objects.update_or_create(
    organization=org, name="ansells-aps-mesh",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=PRESERVED, default=False, default_values=DEFAULTS),
)
m.full_clean(); m.save()
detached = 0
for c in Config.objects.filter(templates=m):
    c.templates.remove(m); detached += 1
print("ansells-aps-mesh:", "created" if mcreated else "updated",
      "id=", m.id, "detached-from:", detached)

# presence-detector template: attaches to the pucks (tenwrt out of scope —
# design spec §4.6, the VM has no wifi-presence deployment).
pr, prcreated = Template.objects.update_or_create(
    organization=org, name="ansells-presence",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=PRESENCE, default=False),
)
pr.full_clean(); pr.save()
print("ansells-presence:", "created" if prcreated else "updated", "id=", pr.id)

attached = 0
missing = []
# netjsonconfig's evaluate_vars leaves the LITERAL '{{ mqtt_username }}' text
# in place when a var is absent from Config.context -- it does not raise and
# does not substitute empty. So a device attached to ansells-presence without
# both context keys silently ships a settings.json full of placeholders; that
# can't raise/abort here (attaching is still correct), it just needs a loud
# warning so the operator runs set_device_vars.py before the config applies.
context_missing = []
for name in DEVICES:
    try:
        d = Device.objects.get(organization=org, name=name)
    except Device.DoesNotExist:
        missing.append(name); continue
    c, _ = Config.objects.get_or_create(device=d, defaults=dict(backend="netjsonconfig.OpenWrt"))
    want = (b, tw) if name == "tenwrt" else (b, t, pr)
    for tpl in want:
        if tpl not in c.templates.all():
            c.templates.add(tpl)
    # the dual-band puck AP template must never ride on the single-phy VM
    if name == "tenwrt" and t in c.templates.all():
        c.templates.remove(t)
        print("detached ansells-aps-puck from tenwrt")
    # presence-detector is out of scope for the tenwrt VM (design spec §4.6)
    if name == "tenwrt" and pr in c.templates.all():
        c.templates.remove(pr)
        print("detached ansells-presence from tenwrt")
    elif pr in c.templates.all():
        ctx = c.context or {{}}
        if "mqtt_username" not in ctx or "mqtt_password" not in ctx:
            context_missing.append(name)
    c.full_clean(); c.save()
    attached += 1
print("configs attached:", attached, "/", len(DEVICES), "missing:", missing)
if context_missing:
    print("WARNING: presence attached but mqtt context vars MISSING on:",
          context_missing,
          "— run tools/fleet/set_device_vars.py before the config applies")

# verification renders, passphrases redacted
for name in ("puck12", "tenwrt"):
    try:
        d = Device.objects.get(organization=org, name=name)
    except Device.DoesNotExist:
        print("render skipped (unregistered):", name)
        continue
    rendered = d.config.backend_instance.render()
    rendered = re.sub(r"(option key ').*?(')", r"\g<1><REDACTED>\g<2>", rendered)
    print("=" * 60)
    print(name, "rendered config (keys redacted):")
    print("=" * 60)
    print(rendered)
'''


def main() -> int:
    vals = read_passphrases()
    script = DJANGO.format(active=json.dumps(netjson_simple()),
                           tenwrt=json.dumps(netjson_tenwrt_aps()),
                           preserved=json.dumps(netjson_mesh_aps()),
                           base=json.dumps(netjson_base()),
                           presence=json.dumps(netjson_presence()),
                           defaults=json.dumps(
                               {**vals, "syslog_ip": "10.1.4.1"}),
                           pucks=PUCKS)
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
