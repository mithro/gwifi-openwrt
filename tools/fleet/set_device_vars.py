#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Set per-device MQTT credentials (Config.context) for presence-detector.

Flow (secrets travel over ssh **stdin** only — never argv, never disk, never
an unredacted print):

  1. ``ssh ten64 sudo gdoc2netcfg wifi show-login --json <machine>...``
     -> ``{machine: {"username": ..., "password": ...}}`` captured in memory.
  2. That dict is json-embedded into a small Django snippet (the exact
     secret-safe pattern ``openwisp/build-templates.py`` already uses: a
     script piped to ``manage.py shell`` over ssh stdin, output redacted
     before printing).
  3. The snippet sets ``Config.context["mqtt_username"/"mqtt_password"]`` for
     each device on wisp (OpenWrt template variables
     ``{{ mqtt_username }}``/``{{ mqtt_password }}``, delivered by the
     ``ansells-presence`` template — see build-templates.py).

``--puck`` picks specific pucks; with no ``--puck`` the machine list is
whatever wisp itself reports as registered (a separate, secret-free
``manage.py shell`` query), so this CLI never has to keep its own puck
registry in sync.

Usage:
    uv run set_device_vars.py                 # all pucks registered on wisp
    uv run set_device_vars.py --puck 12        # just puck12
    uv run set_device_vars.py --puck 6 --puck 12
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys

SSH_TEN64 = ["ssh", "ten64.welland.mithis.com"]
SSH_WISP = [
    "ssh", "-o", "ConnectTimeout=30", "wisp.welland.mithis.com",
    "sudo", "/opt/openwisp2/env/bin/python", "/opt/openwisp2/manage.py", "shell",
]

GDOC2NETCFG = "/opt/gdoc2netcfg/.venv/bin/gdoc2netcfg"

PUCK_NAME_RE = re.compile(r"^puck\d{2}$")

# Secret-free: lists registered device names so the default (no --puck) case
# can ask wisp "what pucks exist" instead of hard-coding a registry here.
LIST_DEVICES_SCRIPT = r'''
import json
from swapper import load_model
Device = load_model("config", "Device")
Org = load_model("openwisp_users", "Organization")
org = Org.objects.get(slug="default")
names = sorted(Device.objects.filter(organization=org).values_list("name", flat=True))
print(json.dumps(names))
'''

# {logins!r} is the only substitution: json.dumps(logins) run through repr()
# so it embeds as a safe single Python string literal (arbitrary characters
# in a password can never break out of the snippet) -- the same idiom
# openwisp/build-templates.py uses for its passphrase dict.
DJANGO_TEMPLATE = r'''
import json
from swapper import load_model
Device = load_model("config", "Device")
Config = load_model("config", "Config")
Org = load_model("openwisp_users", "Organization")
org = Org.objects.get(slug="default")
LOGINS = json.loads({logins!r})

updated = 0
missing = []
for name, creds in LOGINS.items():
    try:
        d = Device.objects.get(organization=org, name=name)
    except Device.DoesNotExist:
        missing.append(name)
        continue
    c, _ = Config.objects.get_or_create(
        device=d, defaults=dict(backend="netjsonconfig.OpenWrt"))
    if c.context is None:
        c.context = {{}}
    c.context.update(dict(mqtt_username=creds["username"],
                          mqtt_password=creds["password"]))
    c.full_clean()
    c.save()
    updated += 1
print("context-set: " + str(updated) + "/" + str(len(LOGINS)) +
      " missing: " + str(missing))
'''


def validate_logins(logins: dict) -> None:
    """Fail loud on anything that would silently push a bad credential.

    Every entry must have a username starting with the ``wifi-`` prefix
    (mirrors the gwifi-wifi-sheet-migration credential convention) and a
    non-empty password. Never mentions the password value in the message.
    """
    if not logins:
        raise ValueError("no logins to validate (empty)")
    for name, creds in logins.items():
        if not isinstance(creds, dict):
            raise ValueError(
                f"{name}: expected a dict with username/password, "
                f"got {type(creds).__name__}")
        username = creds.get("username")
        password = creds.get("password")
        if not username or not username.startswith("wifi-"):
            raise ValueError(
                f"{name}: username must start with 'wifi-' (got {username!r})")
        if not password:
            raise ValueError(f"{name}: password missing/empty")


def build_django_script(logins: dict) -> str:
    """Embed `logins` (in-memory only) into the manage.py-shell snippet."""
    return DJANGO_TEMPLATE.format(logins=json.dumps(logins))


def redact(text: str, logins: dict) -> str:
    """Replace every password value from `logins` with <REDACTED>."""
    for creds in logins.values():
        password = creds.get("password") if isinstance(creds, dict) else None
        if password:
            text = text.replace(password, "<REDACTED>")
    return text


_HEX_RUN_RE = re.compile(r"[0-9a-fA-F]{32,}")


def scrub_hex(text: str) -> str:
    """Fallback scrub for output we cannot redact() against a known logins
    dict -- e.g. an ssh transport failure before any credentials have been
    fetched, so there is nothing yet to key redact() off. Production mqtt
    passwords are 64-char sha256 hex digests (see gdoc2netcfg
    derivations/mqtt_credentials.py), so blanking any run of 32+ hex
    characters catches a leaked credential surfacing in a traceback or error
    message while leaving ordinary error text (short hex-ish tokens, ids)
    readable.
    """
    return _HEX_RUN_RE.sub("<REDACTED-HEX>", text)


def list_registered_pucks() -> list[str]:
    """Ask wisp which puckNN devices are registered (no secrets involved).

    Every registered device name is inspected; anything not shaped like
    puckNN (e.g. 'tenwrt', a mesh-era name) is deliberately excluded from the
    default run -- but per house rule "never silently discard data", that
    exclusion is always printed, so an operator can spot a puck that somehow
    registered under an unexpected name instead of it just vanishing.
    """
    p = subprocess.run(SSH_WISP, input=LIST_DEVICES_SCRIPT, text=True,
                       capture_output=True, timeout=60)
    if p.stderr.strip():
        # No `logins` dict exists yet at this point (this call precedes
        # fetch_logins), so redact() has nothing to key off; scrub_hex() is
        # the fallback net for the known secret shape.
        print(scrub_hex(p.stderr), file=sys.stderr)
    if p.returncode != 0:
        raise SystemExit(
            f"failed to list registered devices from wisp (rc={p.returncode})")
    line = next((ln for ln in reversed(p.stdout.strip().splitlines()) if ln.strip()),
                None)
    if line is None:
        raise SystemExit("wisp returned no output while listing devices")
    try:
        names = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"could not parse device-list JSON from wisp: {exc}")
    pucks = sorted(n for n in names if PUCK_NAME_RE.match(n))
    skipped = sorted(n for n in names if not PUCK_NAME_RE.match(n))
    if skipped:
        print(f"skipping {len(skipped)} non-puck device(s): {', '.join(skipped)}")
    return pucks


def fetch_logins(machines: list[str]) -> dict:
    """ssh ten64 -> gdoc2netcfg wifi show-login --json <machines...>.

    Machine names are not secrets (argv is fine for them); the JSON response
    -- which does contain passwords -- is captured to memory only.
    """
    cmd = SSH_TEN64 + ["sudo", GDOC2NETCFG, "wifi", "show-login", "--json", *machines]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        # No `logins` dict exists yet -- this call is what would produce it
        # -- so redact() has nothing to key off; scrub_hex() is the fallback
        # net for the known secret shape (sha256-hex mqtt passwords) before
        # this ever reaches a terminal/log.
        sys.stderr.write(scrub_hex(p.stderr))
        raise SystemExit(f"wifi show-login failed on ten64 (rc={p.returncode})")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"could not parse wifi show-login JSON: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set MQTT device vars (Config.context) on wisp from "
                     "ten64's wifi show-login.")
    parser.add_argument("--puck", action="append", type=int, metavar="NN",
                        help="Only set puckNN (repeatable). Default: every "
                             "puck registered on wisp.")
    args = parser.parse_args()

    if args.puck:
        machines = sorted({f"puck{n:02d}" for n in args.puck})
    else:
        print("Fetching registered pucks from wisp...")
        machines = list_registered_pucks()
        if not machines:
            print("ERROR: wisp reports no registered pucks", file=sys.stderr)
            return 1
    print(f"Machines ({len(machines)}): {', '.join(machines)}")

    print("Fetching logins from ten64 (gdoc2netcfg wifi show-login)...")
    logins = fetch_logins(machines)

    missing_from_ten64 = sorted(set(machines) - set(logins))
    if missing_from_ten64:
        print(f"ERROR: ten64 did not return logins for: "
              f"{', '.join(missing_from_ten64)}", file=sys.stderr)
        return 1

    try:
        validate_logins(logins)
    except ValueError as exc:
        print(f"ERROR: invalid login data from ten64: {exc}", file=sys.stderr)
        return 1

    script = build_django_script(logins)
    p = subprocess.run(SSH_WISP, input=script, text=True, capture_output=True,
                       timeout=180)
    out = redact(p.stdout, logins)
    sys.stdout.write(out)
    if p.stderr.strip():
        sys.stderr.write("\n--- stderr ---\n" + redact(p.stderr, logins))

    if p.returncode != 0:
        return p.returncode

    m = re.search(r"context-set:\s*(\d+)/(\d+)\s*missing:\s*(\[[^\]]*\])", out)
    if not m:
        print("ERROR: could not find context-set summary in wisp output",
              file=sys.stderr)
        return 1
    missing = ast.literal_eval(m.group(3))
    if missing:
        print(f"ERROR: devices missing on wisp: {missing}", file=sys.stderr)
        return 1
    print(f"OK: context set on {m.group(1)}/{m.group(2)} device(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
