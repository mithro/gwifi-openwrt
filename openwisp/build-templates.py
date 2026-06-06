#!/usr/bin/env python3
"""Build the OpenWISP 'gwifi-puck' config template + attach to the 11 pucks.

Secret handling: the 3 WiFi passphrases are read from ten64's hostapd configs
and a fresh mesh key is generated; none are ever printed. They go into the
template's default_values (OpenWISP DB on wisp, internal) and are piped to wisp
over SSH stdin (not argv). The verification render redacts all `option key`.
"""
import json
import re
import secrets
import subprocess
import sys

SSH_TEN64 = ["ssh", "ten64.welland.mithis.com"]
SSH_WISP = [
    "ssh", "-J", "ten64.welland.mithis.com",
    "-i", "/home/tim/.ssh/keys/new_misc_key",
    "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=30",
    "tim@10.1.5.2",
    "sudo", "/opt/openwisp2/env/bin/python", "/opt/openwisp2/manage.py", "shell",
]
SECRETS_FILE = "/home/tim/local/gwifi/openwisp/.wifi-secrets"

PUCKS = ["G1", "G2", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12"]


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
    need = {"ansells": "ansells_key", "ansells-iot": "iot_key", "ansells-guest": "guest_key"}
    vals = {}
    for ssid, var in need.items():
        if ssid not in cfgs or not cfgs[ssid]:
            raise SystemExit(f"could not find passphrase for SSID {ssid!r}")
        vals[var] = cfgs[ssid]
    return vals


def netjson():
    def wpa3(key):
        return {"protocol": "wpa3_personal", "cipher": "ccmp", "ieee80211w": "2", "key": key}

    def wpa2(key):
        return {"protocol": "wpa2_personal", "cipher": "ccmp", "key": key}

    roam = {"ieee80211r": True, "mobility_domain": "a1b2",
            "ft_psk_generate_local": True, "ieee80211k": True, "bss_transition": True}
    return {
        "radios": [
            {"name": "radio0", "protocol": "802.11n", "channel": 6, "channel_width": 20,
             "phy": "phy0", "country": "AU"},
            {"name": "radio1", "protocol": "802.11ac", "channel": 36, "channel_width": 80,
             "phy": "phy1", "country": "AU"},
        ],
        "interfaces": [
            {"type": "8021q", "vid": 5, "name": "wan"},
            {"type": "8021q", "vid": 20, "name": "wan"},
            {"type": "8021q", "vid": 90, "name": "wan"},
            {"type": "8021q", "vid": 99, "name": "wan"},
            {"type": "8021q", "vid": 5, "name": "bat0"},
            {"type": "8021q", "vid": 20, "name": "bat0"},
            {"type": "8021q", "vid": 90, "name": "bat0"},
            {"type": "8021q", "vid": 99, "name": "bat0"},
            {"name": "br-mgmt", "type": "bridge", "bridge_members": ["wan.5", "bat0.5"],
             "addresses": [{"proto": "dhcp", "family": "ipv4"}]},
            {"name": "br-roam", "type": "bridge", "bridge_members": ["wan.20", "bat0.20", "lan"]},
            {"name": "br-iot", "type": "bridge", "bridge_members": ["wan.90", "bat0.90"]},
            {"name": "br-guest", "type": "bridge", "bridge_members": ["wan.99", "bat0.99"]},
            {"name": "wl-ans-5", "type": "wireless", "wireless": dict(
                radio="radio1", mode="access_point", ssid="ansells", network=["br-roam"],
                encryption=wpa3("{{ ansells_key }}"), **roam)},
            {"name": "wl-ans-2", "type": "wireless", "wireless": dict(
                radio="radio0", mode="access_point", ssid="ansells", network=["br-roam"],
                encryption=wpa3("{{ ansells_key }}"), **roam)},
            {"name": "wl-iot", "type": "wireless", "wireless": dict(
                radio="radio0", mode="access_point", ssid="ansells-iot", network=["br-iot"],
                encryption=wpa2("{{ iot_key }}"))},
            {"name": "wl-guest", "type": "wireless", "wireless": dict(
                radio="radio1", mode="access_point", ssid="ansells-guest", network=["br-guest"],
                encryption=wpa2("{{ guest_key }}"), isolate=True)},
            {"name": "mp0", "type": "wireless", "wireless": dict(
                radio="radio0", mode="802.11s", mesh_id="gwifi-mesh", network=["mesh0"],
                encryption=wpa3("{{ mesh_key }}"))},
            {"name": "mp1", "type": "wireless", "wireless": dict(
                radio="radio1", mode="802.11s", mesh_id="gwifi-mesh", network=["mesh1"],
                encryption=wpa3("{{ mesh_key }}"))},
        ],
        "network": [
            {"config_name": "interface", "config_value": "bat0", "proto": "batadv",
             "routing_algo": "BATMAN_IV", "bridge_loop_avoidance": "1",
             "distributed_arp_table": "1"},
            {"config_name": "interface", "config_value": "mesh0",
             "proto": "batadv_hardif", "master": "bat0"},
            {"config_name": "interface", "config_value": "mesh1",
             "proto": "batadv_hardif", "master": "bat0"},
        ],
    }


DJANGO = r'''
import json, re
from swapper import load_model
Template = load_model("config", "Template")
Config = load_model("config", "Config")
Org = load_model("openwisp_users", "Organization")
Device = load_model("config", "Device")
org = Org.objects.get(slug="default")
CONFIG = json.loads({cfg!r})
DEFAULTS = json.loads({defaults!r})
PUCKS = {pucks!r}

t, created = Template.objects.update_or_create(
    organization=org, name="gwifi-puck",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=CONFIG, default=True, default_values=DEFAULTS),
)
t.full_clean(); t.save()
print("template:", "created" if created else "updated", "id=", t.id, "default=", t.default)

attached = 0
for name in PUCKS:
    d = Device.objects.get(organization=org, name=name)
    c, _ = Config.objects.get_or_create(device=d, defaults=dict(backend="netjsonconfig.OpenWrt"))
    if t not in c.templates.all():
        c.templates.add(t)
    c.full_clean(); c.save()
    attached += 1
print("configs attached:", attached, "/", len(PUCKS))

# verification render of G1, passphrases redacted
d = Device.objects.get(organization=org, name="G1")
rendered = d.config.backend_instance.render()
rendered = re.sub(r"(option key ').*?(')", r"\g<1><REDACTED>\g<2>", rendered)
print("=" * 60)
print("G1 rendered config (keys redacted):")
print("=" * 60)
print(rendered)
'''


def main() -> int:
    vals = read_passphrases()
    vals["mesh_key"] = secrets.token_urlsafe(18)
    # record only the NEW mesh key (others live in ten64); 0600
    import os
    with open(SECRETS_FILE, "w") as f:
        f.write("# gwifi WiFi secrets — SENSITIVE, do not publish\n"
                "# ansells/iot/guest passphrases come from ten64 hostapd (not copied here).\n"
                f"mesh_key (802.11s/batman, generated): {vals['mesh_key']}\n")
    os.chmod(SECRETS_FILE, 0o600)

    cfg = json.dumps(netjson())
    defaults = json.dumps(vals)
    script = DJANGO.format(cfg=cfg, defaults=defaults, pucks=PUCKS)
    p = subprocess.run(SSH_WISP, input=script, text=True, capture_output=True, timeout=180)
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
    print(f"\n(secrets: ansells/iot/guest sourced from ten64; mesh_key generated + saved 0600 to {SECRETS_FILE})")
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
