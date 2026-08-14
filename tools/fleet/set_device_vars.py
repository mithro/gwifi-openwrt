#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Set per-device MQTT credentials (Config.context) for presence-detector.

Flow (secrets travel over ssh **stdin** only — never argv, never disk, never
an unredacted print):

  1. ``ssh ten64 sh -c 'cd /opt/gdoc2netcfg && exec sudo gdoc2netcfg wifi
     show-login --json "$@"' _ <machine>...`` (the cd is required --
     gdoc2netcfg's config + CSV cache both resolve relative to CWD, and a
     non-interactive ssh command starts in $HOME, not /opt/gdoc2netcfg; see
     ``build_show_login_cmd``) -> ``{machine: {"username": ...,
     "password": ...}}`` captured in memory.
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
import shlex
import subprocess
import sys

# Per-site endpoints. Mirrors the SITES table in openwisp/build-templates.py;
# kept as its own literal rather than imported because that module's filename
# is hyphenated and it is not on the path from here.
SITES = {
    "welland": {"ten64": "ten64.welland.mithis.com",
                "wisp": "wisp.welland.mithis.com"},
    "monarto": {"ten64": "ten64.monarto.mithis.com",
                "wisp": "wisp.monarto.mithis.com"},
}

# Set from --site in main(); module-level so the helpers keep their signatures.
SITE = "welland"


def ssh_ten64():
    return ["ssh", "-o", "ConnectTimeout=30", SITES[SITE]["ten64"]]


def ssh_wisp():
    return [
        "ssh", "-o", "ConnectTimeout=30", SITES[SITE]["wisp"],
        "sudo", "/opt/openwisp2/env/bin/python",
        "/opt/openwisp2/manage.py", "shell",
    ]


GDOC2NETCFG_DIR = "/opt/gdoc2netcfg"
GDOC2NETCFG = f"{GDOC2NETCFG_DIR}/.venv/bin/gdoc2netcfg"

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
# in a password -- quotes, backslashes, newlines -- can never break out of
# the snippet) -- the same idiom openwisp/build-templates.py uses for its
# passphrase dict. Locked in by
# test_build_django_script_handles_nasty_password_injection_safe.
#
# manage.py shell reads this piped script statement-by-statement (like a
# REPL) and does NOT abort later top-level statements just because one
# earlier statement raised -- so if any single device's Device.objects.get
# /Config save could raise uncaught, the for-loop could die partway through
# and the final print() would still run, reporting a false "clean" count.
# The per-device try/except below must therefore catch every Exception (not
# just Device.DoesNotExist) so the loop always finishes len(LOGINS)
# iterations and `updated + len(missing) + len(failed) == len(LOGINS)`
# always holds -- set_device_vars.py's local gate re-checks that invariant
# as a backstop (see main()).
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
failed = []
for name, creds in LOGINS.items():
    try:
        d = Device.objects.get(organization=org, name=name)
    except Device.DoesNotExist:
        missing.append(name)
        continue
    try:
        c, _ = Config.objects.get_or_create(
            device=d, defaults=dict(backend="netjsonconfig.OpenWrt"))
        if c.context is None:
            c.context = {{}}
        c.context.update(dict(mqtt_username=creds["username"],
                              mqtt_password=creds["password"]))
        c.full_clean()
        c.save()
    except Exception:
        failed.append(name)
        continue
    updated += 1
print("context-set: " + str(updated) + "/" + str(len(LOGINS)) +
      " missing: " + str(missing) + " failed: " + str(failed))
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


def partition_puck_names(names: list[str]) -> tuple[list[str], list[str]]:
    """Split registered device names into (pucks, skipped) by the puckNN
    shape. Pure and unit-tested on its own -- not just exercised indirectly
    via a live ssh call -- because the "skipped" half is exactly the set of
    devices a bare-default run would otherwise drop with no trace (house
    rule: never silently discard data).
    """
    pucks = sorted(n for n in names if PUCK_NAME_RE.match(n))
    skipped = sorted(n for n in names if not PUCK_NAME_RE.match(n))
    return pucks, skipped


def run_ssh(cmd: list[str], *, what: str, timeout: int,
            input: str | None = None,
            logins: dict | None = None) -> subprocess.CompletedProcess:
    """subprocess.run wrapper shared by every ssh call in this tool.

    Turns a hang into a clear, non-secret-leaking SystemExit instead of a
    raw traceback (`exc.stdout`/`exc.stderr` are never printed as-is):
    `what` names the operation for the message, and any partially-captured
    stderr is redact()ed against `logins` first if the caller already has
    it, then scrub_hex()ed as the fallback net for the known secret shape
    (sha256-hex mqtt passwords) before it is ever shown.
    """
    try:
        return subprocess.run(cmd, input=input, text=True,
                              capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr or ""
        if logins:
            stderr = redact(stderr, logins)
        stderr = scrub_hex(stderr).strip()
        detail = f": {stderr}" if stderr else ""
        raise SystemExit(f"{what} timed out after {exc.timeout:.0f}s{detail}")


def list_registered_pucks() -> list[str]:
    """Ask wisp which puckNN devices are registered (no secrets involved).

    Every registered device name is inspected; anything not shaped like
    puckNN (e.g. 'tenwrt', a mesh-era name) is deliberately excluded from the
    default run -- but per house rule "never silently discard data", that
    exclusion is always printed, so an operator can spot a puck that somehow
    registered under an unexpected name instead of it just vanishing.
    """
    p = run_ssh(ssh_wisp(), what="listing registered devices from wisp",
               timeout=60, input=LIST_DEVICES_SCRIPT)
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
    pucks, skipped = partition_puck_names(names)
    if skipped:
        print(f"skipping {len(skipped)} non-puck device(s): {', '.join(skipped)}")
    return pucks


def build_show_login_cmd(machines: list[str]) -> list[str]:
    """Build the ssh argv for `gdoc2netcfg wifi show-login --json <machines>`.

    A non-interactive `ssh host cmd` starts in the connecting user's HOME,
    not /opt/gdoc2netcfg -- but gdoc2netcfg's config loading resolves
    `Path("gdoc2netcfg.toml")` relative to CWD with no env/install-dir
    fallback (config.py:375-376), and `show-login` runs the full pipeline,
    which reads its CSV cache from `Path(".cache")` -- also CWD-relative,
    also no fallback (config.py:24). So the remote command MUST `cd` into
    /opt/gdoc2netcfg first, exactly like every production invocation
    documented in gdoc2netcfg's CLAUDE.md. Do not "simplify" this back to a
    bare command list -- that silently breaks on the very first live run.

    Machine names travel as `sh -c '<script>' _ <machines...>` positional
    arguments (each individually shlex-quoted), never interpolated into the
    script text itself, so an odd name can never break out into a second
    remote command -- even though today's names are always the safe
    `puckNN` shape.
    """
    script = (f"cd {GDOC2NETCFG_DIR} && exec sudo {GDOC2NETCFG} "
              f'wifi show-login --json "$@"')
    args = " ".join(shlex.quote(m) for m in machines)
    remote_cmd = f"sh -c {shlex.quote(script)} _ {args}"
    return ssh_ten64() + [remote_cmd]


def fetch_logins(machines: list[str]) -> dict:
    """ssh ten64 -> gdoc2netcfg wifi show-login --json <machines...>.

    Machine names are not secrets (argv is fine for them); the JSON response
    -- which does contain passwords -- is captured to memory only.
    """
    cmd = build_show_login_cmd(machines)
    p = run_ssh(cmd, what="wifi show-login on ten64", timeout=60)
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
    parser.add_argument("--site", choices=sorted(SITES), default="welland",
                        help="which deployment to act on (default: welland)")
    args = parser.parse_args()

    global SITE
    SITE = args.site
    print(f"site: {SITE}  ten64={SITES[SITE]['ten64']}  "
          f"wisp={SITES[SITE]['wisp']}")

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

    # Never implicitly trust that ten64's wifi show-login honored its own
    # argument list -- keep only what was actually requested, and say so if
    # it returned anything extra (house rule: never silently discard data).
    machine_set = set(machines)
    extra = sorted(set(logins) - machine_set)
    if extra:
        print(f"Ignoring {len(extra)} login(s) ten64 returned outside the "
              f"requested set: {', '.join(extra)}")
    logins = {name: creds for name, creds in logins.items() if name in machine_set}

    missing_from_ten64 = sorted(machine_set - set(logins))
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
    p = run_ssh(ssh_wisp(), what="setting context on wisp", timeout=180,
               input=script, logins=logins)
    out = scrub_hex(redact(p.stdout, logins))
    sys.stdout.write(out)
    if p.stderr.strip():
        sys.stderr.write("\n--- stderr ---\n" + scrub_hex(redact(p.stderr, logins)))

    if p.returncode != 0:
        return p.returncode

    m = re.search(
        r"context-set:\s*(\d+)/(\d+)\s*missing:\s*(\[[^\]]*\])\s*"
        r"failed:\s*(\[[^\]]*\])", out)
    if not m:
        print("ERROR: could not find context-set summary in wisp output",
              file=sys.stderr)
        return 1
    updated, total = int(m.group(1)), int(m.group(2))
    missing = ast.literal_eval(m.group(3))
    failed = ast.literal_eval(m.group(4))
    # manage.py shell does not abort later piped statements just because an
    # earlier one raised -- so a mid-loop crash on the remote side could
    # otherwise print a plausible-looking but incomplete summary (see
    # DJANGO_TEMPLATE's comment). Recomputing the invariant here is the
    # local backstop: any accounting mismatch means the remote loop did not
    # run to completion and this result must not be trusted.
    if updated + len(missing) + len(failed) != total:
        print(f"ERROR: context-set accounting mismatch: updated={updated} "
              f"missing={len(missing)} failed={len(failed)} but total={total} "
              f"-- the remote loop likely did not finish; do not trust this "
              f"run", file=sys.stderr)
        return 1
    if missing:
        print(f"ERROR: devices missing on wisp: {missing}", file=sys.stderr)
        return 1
    if failed:
        print(f"ERROR: devices failed to update on wisp: {failed}", file=sys.stderr)
        return 1
    print(f"OK: context set on {updated}/{total} device(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
