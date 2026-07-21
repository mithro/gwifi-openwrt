#!/usr/bin/env python3
"""Build the OpenWISP 'gwifi-aps' config template + attach it to the pucks.

Architecture (post 2026-07 migration): the gale IMAGE provides all networking
— radios, the vlan-aware br0 wired trunk, bat0 + per-VLAN legs, the bridges,
and the mesh backhaul (mesh-2g4 + mesh-5g, see gale-image/files/etc/config/
wireless + 99-gale-bootstrap). OpenWISP layers ONLY the access-point SSIDs on
top, via this minimal template. (The old monolithic 'gwifi-puck' template that
also carried networking/mesh was retired 2026-07-21; its redundant bridges +
mp0/mp1 mesh were the source of the fleet's mesh-redundancy + link-local
management-IP problems.)

Interfaces (each an AP bridged to an image-provided br0.<vid> via network=):
  wl-main-5g / wl-main-2g4  -> roam  (VLAN 20, WPA3, 802.11r/k/v fast-roam)
  wl-iot-2g4                -> iot   (VLAN 90, WPA2)
  wl-guest-5g / wl-guest-2g4-> guest (VLAN 99, WPA2, client isolation)
Radios (radio0=2.4G, radio1=5G) come from the image; the template just
references them.

SSIDs are the placeholder 'test' set; the production 'ansells' names are a
separate, deliberate flip.

Secret handling: the 3 WiFi passphrases are read from ten64's hostapd configs;
none are ever printed or committed. They go into the template's default_values
(OpenWISP DB on wisp, internal) as {{ }} substitutions and are piped to wisp
over SSH stdin (not argv). The verification render redacts all `option key`.
"""
import json
import re
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

# SSID -> passphrase source in ten64 hostapd. The var names are historical
# (the passphrases are the real home-network keys); the broadcast SSID is the
# placeholder 'test*' set for now.
SSID_MAIN, SSID_IOT, SSID_GUEST = "test", "test-iot", "test-guest"


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


def netjson():
    def wpa3(key):
        return {"protocol": "wpa3_personal", "cipher": "ccmp",
                "ieee80211w": "2", "key": key}

    def wpa2(key):
        return {"protocol": "wpa2_personal", "cipher": "ccmp", "key": key}

    roam = {"ieee80211r": True, "mobility_domain": "a1b2",
            "ft_psk_generate_local": True, "ieee80211k": True,
            "bss_transition": True}
    return {
        "interfaces": [
            {"name": "wl-main-5g", "type": "wireless", "wireless": dict(
                radio="radio1", mode="access_point", ssid=SSID_MAIN,
                network=["roam"], encryption=wpa3("{{ ansells_key }}"), **roam)},
            {"name": "wl-main-2g4", "type": "wireless", "wireless": dict(
                radio="radio0", mode="access_point", ssid=SSID_MAIN,
                network=["roam"], encryption=wpa3("{{ ansells_key }}"), **roam)},
            {"name": "wl-iot-2g4", "type": "wireless", "wireless": dict(
                radio="radio0", mode="access_point", ssid=SSID_IOT,
                network=["iot"], encryption=wpa2("{{ iot_key }}"))},
            {"name": "wl-guest-5g", "type": "wireless", "wireless": dict(
                radio="radio1", mode="access_point", ssid=SSID_GUEST,
                network=["guest"], encryption=wpa2("{{ guest_key }}"),
                isolate=True)},
            {"name": "wl-guest-2g4", "type": "wireless", "wireless": dict(
                radio="radio0", mode="access_point", ssid=SSID_GUEST,
                network=["guest"], encryption=wpa2("{{ guest_key }}"),
                isolate=True)},
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
    organization=org, name="gwifi-aps",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=CONFIG, default=False, default_values=DEFAULTS),
)
t.full_clean(); t.save()
print("template:", "created" if created else "updated", "id=", t.id, "default=", t.default)

attached = 0
missing = []
for name in PUCKS:
    try:
        d = Device.objects.get(organization=org, name=name)
    except Device.DoesNotExist:
        missing.append(name); continue
    c, _ = Config.objects.get_or_create(device=d, defaults=dict(backend="netjsonconfig.OpenWrt"))
    if t not in c.templates.all():
        c.templates.add(t)
    c.full_clean(); c.save()
    attached += 1
print("configs attached:", attached, "/", len(PUCKS), "missing:", missing)

# verification render of an online puck, passphrases redacted
d = Device.objects.get(organization=org, name="puck06")
rendered = d.config.backend_instance.render()
rendered = re.sub(r"(option key ').*?(')", r"\g<1><REDACTED>\g<2>", rendered)
print("=" * 60)
print("puck06 rendered config (keys redacted):")
print("=" * 60)
print(rendered)
'''


def main() -> int:
    vals = read_passphrases()
    cfg = json.dumps(netjson())
    defaults = json.dumps(vals)
    script = DJANGO.format(cfg=cfg, defaults=defaults, pucks=PUCKS)
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
