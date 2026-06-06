#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""Pre-provision the Open-Mesh APs as OpenWISP devices (org `default`).

Mirrors how the 11 Google WiFi pucks were registered: create a Device per node
keyed on (org, name), set mac_address + model, leave config=none. OpenWISP binds
each real device to its pre-created record BY MAC when it later auto-registers.

Source of truth = the gdoc2netcfg inventory on ten64 (network.csv). Like
build-templates.py reads WiFi passphrases at runtime, this reads the node list
(names/MACs/driver) from ten64 at runtime and never stores it in this file.

    uv run python openwisp/provision-openmesh.py            # dry-run (default)
    uv run python openwisp/provision-openmesh.py --apply    # create on the box

Flow: ssh ten64 -> parse network.csv -> build a Django ORM snippet -> pipe it to
`manage.py shell` on the wisp VM. Idempotent: re-running updates in place.
"""
import argparse
import json
import subprocess
import sys

TEN64 = "ten64.welland.mithis.com"
WISP = "wisp.welland.mithis.com"
NETWORK_CSV = "/opt/gdoc2netcfg/.cache/network.csv"

# gdoc "Driver" value -> OpenWrt model string the device reports (must match the
# `boards` entries added to OPENWISP_CUSTOM_OPENWRT_IMAGES in playbook.yml). The
# bare "OM2P" has no h/w revision in the gdoc; onboarding refines it to a
# revision-specific string (OpenMesh OM2P v{1,2,4}), which the map also covers.
DRIVER_TO_MODEL = {
    "OM2P-LC": "OpenMesh OM2P-LC",
    "OM2P": "OpenMesh OM2P",
}

# Inline parser executed on ten64 (no deps); prints JSON list of nodes.
REMOTE_PARSER = r'''
import csv, json
C_MACHINE, C_NOTES, C_MAC, C_DRIVER = 1, 3, 7, 15
rows = list(csv.reader(open("%s", newline="", encoding="utf-8", errors="replace")))
nodes = {}
for r in rows:
    if len(r) <= C_DRIVER:
        continue
    name = r[C_MACHINE].strip()
    if not name.lower().startswith("openmesh"):
        continue
    n = nodes.setdefault(name, {"name": name, "mac": "", "driver": "", "note": ""})
    # base MAC = the "lan" interface (lowest MAC, matches the label / name suffix)
    if r[2].strip() == "lan" and r[C_MAC].strip():
        n["mac"] = r[C_MAC].strip().upper()
    if r[C_DRIVER].strip():
        n["driver"] = r[C_DRIVER].strip()
    if r[C_NOTES].strip() and "cloudtrax" in r[C_NOTES].lower():
        n["note"] = r[C_NOTES].strip()
print(json.dumps(sorted(nodes.values(), key=lambda d: d["name"])))
''' % NETWORK_CSV


def fetch_nodes():
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", TEN64, "python3 -"],
        input=REMOTE_PARSER, capture_output=True, text=True, check=True,
    )
    nodes = json.loads(out.stdout.strip().splitlines()[-1])
    for n in nodes:
        if not n["mac"]:
            sys.exit(f"ERROR: {n['name']} has no base (lan) MAC in {NETWORK_CSV}")
        model = DRIVER_TO_MODEL.get(n["driver"])
        if not model:
            sys.exit(f"ERROR: {n['name']} unknown driver {n['driver']!r}")
        n["model"] = model
    return nodes


def build_orm(nodes):
    payload = [
        {"name": n["name"], "mac": n["mac"], "model": n["model"],
         "notes": f"Open-Mesh {n['driver']} (CloudTrax). {n['note']}".strip()}
        for n in nodes
    ]
    return (
        "import json\n"
        "from openwisp_controller.config.models import Device\n"
        "from openwisp_users.models import Organization\n"
        f"NODES = json.loads(r'''{json.dumps(payload)}''')\n"
        "org = Organization.objects.get(slug='default')\n"
        "for n in NODES:\n"
        "    dev, created = Device.objects.get_or_create(\n"
        "        organization=org, name=n['name'],\n"
        "        defaults={'mac_address': n['mac'], 'model': n['model'],\n"
        "                  'notes': n['notes']})\n"
        "    changed = []\n"
        "    if not created:\n"
        "        for attr, val in (('mac_address', n['mac']), ('model', n['model']),\n"
        "                          ('notes', n['notes'])):\n"
        "            if getattr(dev, attr) != val:\n"
        "                setattr(dev, attr, val); changed.append(attr)\n"
        "        if changed:\n"
        "            dev.full_clean(); dev.save()\n"
        "    tag = 'CREATED' if created else ('UPDATED(' + ','.join(changed) + ')'\n"
        "                                     if changed else 'OK')\n"
        "    print(f\"{tag}: {dev.name}  {dev.mac_address}  {dev.model}\")\n"
        "print('total devices in org default:',\n"
        "      Device.objects.filter(organization=org).count())\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="create/update on the wisp VM (default: dry-run)")
    args = ap.parse_args()

    nodes = fetch_nodes()
    print(f"== {len(nodes)} Open-Mesh nodes from ten64 ({NETWORK_CSV}) ==")
    for n in nodes:
        print(f"  {n['name']:16} {n['mac']:18} {n['model']}")
    orm = build_orm(nodes)

    if not args.apply:
        print("\n-- DRY RUN: Django ORM snippet that WOULD run on wisp --\n")
        print(orm)
        print("Re-run with --apply to create the devices.")
        return

    print("\n-- applying on wisp via manage.py shell --")
    # The OpenWISP app + SQLite DB are owned by www-data (the supervisor run-as
    # user); run manage.py as www-data so DB file ownership/permissions stay sane.
    cmd = ["ssh", "-o", "BatchMode=yes", WISP,
           "sudo -u www-data /opt/openwisp2/env/bin/python "
           "/opt/openwisp2/manage.py shell"]
    res = subprocess.run(cmd, input=orm, capture_output=True, text=True)
    sys.stdout.write(res.stdout)
    if res.stderr.strip():
        sys.stderr.write("\n[stderr]\n" + res.stderr)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
