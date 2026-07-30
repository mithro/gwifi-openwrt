# WiFi Presence (OpenWrt → HA device_tracker) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare (code + templates + tooling, fully tested) the per-puck wifi-client presence integration so that, once the MQTT credential gate opens, deployment is a short ordered runbook.

**Architecture:** Each puck runs the vendored upstream `presence-detector` (ubus hostapd events + 60 s fallback sync) publishing HA MQTT-discovery `device_tracker` entities per (puck, client MAC) with per-device `wifi-puckNN` credentials. Delivery = new `ansells-presence` OpenWISP template (files only) + `tools/fleet/deploy_presence.py` (apk install + verify) + per-device `Config.context` variables set from a new `gdoc2netcfg wifi show-login` subcommand. See `docs/superpowers/specs/2026-07-29-wifi-presence-design.md` (approved).

**Tech Stack:** Python 3 / uv / pytest; OpenWISP (`manage.py shell` over ssh, netjson `files`); OpenWrt apk (`python3`, `python3-paho-mqtt`); upstream rmoesbergen/openwrt-ha-device-tracker pinned at `a81e6642ed86e53ffed691b91af9e661829ecd53` (main, 2026-07-26).

**Worktrees:**
- Part A (Tasks 1–6): `gwifi-openwrt/.worktrees/wifi-presence`, branch `wifi-presence` (exists; `main` already merged in).
- Part B (Task 7): `gdoc2netcfg/.worktrees/wifi-show-login`, branch `wifi-show-login` stacked on `wifi-sheet-hosts` (create in Task 7; `wifi_credentials.py` exists only there until PR #18 merges).
- Part C (Task 8): GATED live deployment runbook — **do NOT execute during implementation**.

**Conventions that apply to every task:** `uv run` for all Python; never `2>/dev/null`; commit after each task with trailers:

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EHZYoaQFrwZ1exgFiyHheo
```

---

## File map

| File | Responsibility |
|---|---|
| `openwisp/presence/presence-detector.py` | vendored upstream, byte-exact at pinned commit |
| `openwisp/presence/init.d-presence-detector` | vendored init, paths adapted (documented diff) |
| `openwisp/presence/UPSTREAM` | provenance: repo URL, commit, per-file sha256 |
| `openwisp/build-templates.py` | + `netjson_presence()`, `ansells-presence` upsert/attach, base-hook service enable, PUCKS fix |
| `tools/fleet/galeflash/presencedeploy.py` | pure logic: remote install/verify script builder + result parser |
| `tools/fleet/deploy_presence.py` | CLI: per-puck apk install + service + MQTT verify (pattern: `check_vlan_reach.py`) |
| `tools/fleet/set_device_vars.py` | CLI: ten64 `wifi show-login --json` → wisp `Config.context` (secrets via stdin pipes only) |
| `tools/fleet/tests/test_presencedeploy.py` | tests for presencedeploy pure logic |
| `tools/fleet/tests/test_presence_template.py` | tests for build-templates presence pieces (importlib) |
| gdoc2netcfg `src/gdoc2netcfg/cli/main.py` | + `wifi show-login` subcommand |
| gdoc2netcfg `tests/test_cli/test_wifi_show_login.py` | tests for the subcommand |

---

## Part A — gwifi-openwrt (worktree `.worktrees/wifi-presence`)

> **Status 2026-07-29: Tasks 1–5 are COMPLETE** (implemented + locally
> tested; commits d302e60, 1b387bc+33d4b2f, 474c92e+bd5c854+26e6a10,
> c7644d9+b544859+725f456, 0f1548b+4ec0273). Nothing has been deployed —
> Part C remains gated. Task 6 (this docs pass) is in progress; Task 7 is
> Part B, in the `gdoc2netcfg` repo.

### Task 1: Vendor upstream presence-detector (pinned)

**Files:**
- Create: `openwisp/presence/presence-detector.py`
- Create: `openwisp/presence/init.d-presence-detector`
- Create: `openwisp/presence/UPSTREAM`

- [ ] **Step 1: Fetch both files at the pinned commit**

```bash
cd /home/tim/local/gwifi/gwifi-openwrt/.worktrees/wifi-presence
mkdir -p openwisp/presence
PIN=a81e6642ed86e53ffed691b91af9e661829ecd53
curl -fsS -o openwisp/presence/presence-detector.py \
  https://raw.githubusercontent.com/rmoesbergen/openwrt-ha-device-tracker/$PIN/presence-detector.py
curl -fsS -o openwisp/presence/init.d-presence-detector \
  https://raw.githubusercontent.com/rmoesbergen/openwrt-ha-device-tracker/$PIN/init.d/presence-detector
sha256sum openwisp/presence/*
```

Expected: both files download; note the two sha256 values.

- [ ] **Step 2: Sanity-check the vendored script**

```bash
(cd tools/fleet && uv run python -m py_compile ../../openwisp/presence/presence-detector.py) && echo COMPILES
grep -n "add_argument" openwisp/presence/presence-detector.py
```

Expected: `COMPILES`, and the argparse block shows the config-file argument
(README/source indicate a `--config`-style flag with an upstream default
path). Record the exact flag/default — Step 3 and Task 5's settings path
depend on it. If there is NO config-path argument, STOP and re-read the
script's `Settings(...)` construction to find how the path is chosen; adapt
Step 3 accordingly (do not guess).

- [ ] **Step 3: Adapt the init script paths**

Upstream init (verbatim) is:

```sh
#!/bin/sh /etc/rc.common

START=90
STOP=1
USE_PROCD=1
NAME=devices
PROG=/etc/config/presence-detector.py

start_service() {
	procd_open_instance
	procd_set_param command "$PROG"
	procd_set_param stdout 1
	procd_set_param stderr 1
	procd_set_param respawn
	procd_set_param term_timeout 300
	procd_close_instance
}
```

Edit `openwisp/presence/init.d-presence-detector` to:
- `NAME=presence-detector`
- `PROG=/opt/presence-detector/presence-detector.py`
- command line: `procd_set_param command /usr/bin/python3 "$PROG" <config-flag> /etc/presence-detector/settings.json` using the flag verified in Step 2 (invoke via python3 explicitly — don't rely on the shebang/execute bit).

Add a trailing comment block: `# Local changes vs upstream $PIN: NAME, PROG path, explicit python3 + config path.`

- [ ] **Step 4: Write `openwisp/presence/UPSTREAM`**

```
Source: https://github.com/rmoesbergen/openwrt-ha-device-tracker
Commit: a81e6642ed86e53ffed691b91af9e661829ecd53 (main, 2026-07-26)
presence-detector.py: <sha256 from Step 1> (byte-exact)
init.d-presence-detector: upstream init.d/presence-detector (sha256 <from Step 1>) + local path adaptations (see file footer)
Update procedure: re-fetch at a new pin, re-apply the documented init diff, update this file.
Known upstream behavior: interface auto-detect shells `ubus list hostapd.*` with
check=True at startup — a start racing a `wifi` reload can raise; procd respawn covers it.
```

- [ ] **Step 5: Commit**

```bash
git add openwisp/presence/
git commit -m "presence: vendor upstream presence-detector @ a81e664"
```

### Task 2: presencedeploy pure logic (TDD)

**Files:**
- Create: `tools/fleet/galeflash/presencedeploy.py`
- Test: `tools/fleet/tests/test_presencedeploy.py`

- [ ] **Step 1: Write the failing tests**

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.presencedeploy — pure script-builder/parser logic."""
import pytest

from galeflash.presencedeploy import PACKAGES, build_install_script, parse_results


def test_packages():
    assert PACKAGES == ("python3", "python3-paho-mqtt")


def test_install_script_contents():
    s = build_install_script()
    assert "apk update" in s
    assert "apk add python3 python3-paho-mqtt" in s
    # must check the template delivered its files before starting anything
    assert "/opt/presence-detector/presence-detector.py" in s
    assert "/etc/presence-detector/settings.json" in s
    assert "/etc/init.d/presence-detector" in s
    # verification: service registered with procd + recent syslog errors
    assert "service list" in s
    assert "logread" in s
    # results protocol: the script emits via the result() helper, so the
    # literal text in the script is the lowercase call sites
    assert 'echo "RESULT $1 $2 $3"' in s
    for step in ("files", "apk", "service", "mqtt"):
        assert f"result {step} " in s


def test_parse_results_ok():
    text = "junk\nRESULT files OK -\nRESULT apk OK installed\nRESULT service OK running\nRESULT mqtt OK no-errors\n"
    assert parse_results(text) == {
        "files": (True, "-"),
        "apk": (True, "installed"),
        "service": (True, "running"),
        "mqtt": (True, "no-errors"),
    }


def test_parse_results_failure_detail():
    text = ("RESULT files OK -\nRESULT apk OK installed\n"
            "RESULT service FAIL not-registered\nRESULT mqtt FAIL connect-refused\n")
    r = parse_results(text)
    assert r["service"] == (False, "not-registered")


def test_parse_results_missing_step_raises():
    with pytest.raises(ValueError, match="mqtt"):
        parse_results("RESULT files OK -\nRESULT apk OK x\nRESULT service OK x\n")


def test_parse_results_duplicate_raises():
    with pytest.raises(ValueError, match="duplicate"):
        parse_results("RESULT apk OK a\nRESULT apk OK b\n"
                      "RESULT files OK -\nRESULT service OK x\nRESULT mqtt OK x\n")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools/fleet && uv run pytest tests/test_presencedeploy.py -q`
Expected: FAIL (`ModuleNotFoundError: galeflash.presencedeploy`)

- [ ] **Step 3: Implement `presencedeploy.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Pure logic for the presence-detector fleet deploy.

deploy_presence.py does the ssh I/O; this module builds the remote sh script
and parses its RESULT lines.  Fail loud on malformed output (house rule).
"""

PACKAGES: tuple[str, ...] = ("python3", "python3-paho-mqtt")
STEPS: tuple[str, ...] = ("files", "apk", "service", "mqtt")

_SCRIPT = """\
set -u
result() {{ echo "RESULT $1 $2 $3"; }}

# 1. template files must already be delivered (runbook orders template first)
missing=""
for f in /opt/presence-detector/presence-detector.py \\
         /etc/presence-detector/settings.json \\
         /etc/init.d/presence-detector; do
    [ -e "$f" ] || missing="$missing $f"
done
if [ -n "$missing" ]; then
    result files FAIL "missing:$missing"
else
    result files OK -
fi

# 2. packages (apk exit code is authoritative; output goes to stderr for the log)
if apk update >&2 && apk add {packages} >&2; then
    result apk OK installed
else
    result apk FAIL "apk-exit=$?"
fi

# 3. service enabled + registered with procd
/etc/init.d/presence-detector enable
/etc/init.d/presence-detector restart
sleep 3
if ubus call service list '{{"name":"presence-detector"}}' | grep -q presence-detector; then
    result service OK running
else
    result service FAIL not-registered
fi

# 4. no fresh presence-detector errors in syslog (MQTT auth/connect failures land here)
errs=$(logread | grep presence-detector | tail -n 20 | grep -ci error)
if [ "$errs" = "0" ]; then
    result mqtt OK no-errors
else
    result mqtt FAIL "syslog-errors=$errs"
fi
"""


def build_install_script() -> str:
    """The sh script run on each puck over ssh (stdin)."""
    return _SCRIPT.format(packages=" ".join(PACKAGES))


def parse_results(text: str) -> dict[str, tuple[bool, str]]:
    """Parse RESULT lines into {step: (ok, detail)}; raise on drift."""
    out: dict[str, tuple[bool, str]] = {}
    for line in text.splitlines():
        if not line.startswith("RESULT "):
            continue
        parts = line.split(None, 3)
        if len(parts) != 4 or parts[2] not in ("OK", "FAIL"):
            raise ValueError(f"malformed RESULT line: {line!r}")
        _, step, verdict, detail = parts
        if step in out:
            raise ValueError(f"duplicate RESULT for step {step!r}")
        out[step] = (verdict == "OK", detail)
    missing = [s for s in STEPS if s not in out]
    if missing:
        raise ValueError(f"missing RESULT for step(s): {', '.join(missing)}")
    return out
```

- [ ] **Step 4: Run tests**

Run: `cd tools/fleet && uv run pytest tests/test_presencedeploy.py -q`
Expected: 6 passed. Then full suite: `uv run pytest -q` → 123 passed (117 + 6).

- [ ] **Step 5: Commit**

```bash
git add tools/fleet/galeflash/presencedeploy.py tools/fleet/tests/test_presencedeploy.py
git commit -m "fleet: presence deploy script builder + result parser"
```

### Task 3: deploy_presence.py CLI

**Files:**
- Create: `tools/fleet/deploy_presence.py` (mode 0755)

Thin I/O wrapper — copy the structure of `tools/fleet/check_vlan_reach.py`
verbatim: same registry acquisition (its `REGISTRY_HOST = "tim@10.1.4.2"` +
`sudo -n cat /etc/dnsmasq.d/gwifi-generated/pucks.conf`, parsed with
`galeflash.livecollect.parse_pucks_conf`), same PEP-723 `# /// script` header
so `uv run` resolves it identically, `--puck NN` repeatable, per-puck
`ssh root@<ip> "sh -s"` with the script on stdin, summary matrix, exit
non-zero on any failure. No new pure logic here (all tested in Task 2), so
no new tests — same convention as `check_vlan_reach.py`.

**Spec deviation (accepted, recorded in Task 6):** the per-puck `mqtt` verify
is a syslog-error check on the puck (auth/connect failures surface there);
the on-broker "state message actually arrived" check happens once fleet-wide
in runbook step 4 rather than per puck inside this CLI.

- [ ] **Step 1: Implement** — reuse `check_vlan_reach.py`'s `main()`/registry/ssh helpers shape verbatim, substituting `build_install_script()`/`parse_results()` and a `files/apk/service/mqtt` summary table. Docstring must state: "Run AFTER the ansells-presence template is attached and device vars are set (see runbook in the design spec)."
- [ ] **Step 2: Smoke-check (no puck contact)**

Run: `cd tools/fleet && uv run python deploy_presence.py --help`
Expected: usage text; exit 0.

- [ ] **Step 3: Commit**

```bash
git add tools/fleet/deploy_presence.py
git commit -m "fleet: deploy_presence CLI (apk install + service + mqtt verify)"
```

### Task 4: set_device_vars.py CLI (secrets via pipes only)

**Files:**
- Create: `tools/fleet/set_device_vars.py` (mode 0755)
- Test: `tools/fleet/tests/test_set_device_vars.py`

Flow: `ssh ten64.welland.mithis.com sh -c 'cd /opt/gdoc2netcfg && exec sudo
/opt/gdoc2netcfg/.venv/bin/gdoc2netcfg wifi show-login --json "$@"' _
<machine>...` (the `cd` is required: gdoc2netcfg's config file and CSV cache
both resolve relative to CWD with no env/install-dir fallback, but a
non-interactive `ssh host cmd` starts in the connecting user's `$HOME`, not
`/opt/gdoc2netcfg`; machine names ride as shlex-quoted `sh -c '...' _
<names>` positional args, never interpolated into the script text) →
`{machine: {"username":…, "password":…}}` → embed into a Django snippet →
pipe over `ssh wisp… manage.py shell` stdin (the exact secret path
build-templates.py already uses) → set each device's
`Config.context["mqtt_username"/"mqtt_password"]`. Print counts only; pass
every captured output through a redactor before printing.

- [ ] **Step 1: Write the failing tests** (pure helpers only)

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for set_device_vars pure helpers (no ssh)."""
import json

import pytest

from set_device_vars import build_django_script, redact, validate_logins


LOGINS = {"puck06": {"username": "wifi-puck06", "password": "s3cret1"},
          "puck12": {"username": "wifi-puck12", "password": "s3cret2"}}


def test_validate_logins_passes():
    validate_logins(LOGINS)


@pytest.mark.parametrize("bad", [
    {},                                                      # empty
    {"puck06": {"username": "wifi-puck06"}},                 # missing password
    {"puck06": {"username": "tas-puck06", "password": "x"}}, # wrong prefix
    {"puck06": {"username": "wifi-puck06", "password": ""}}, # empty password
])
def test_validate_logins_fails_loud(bad):
    with pytest.raises(ValueError):
        validate_logins(bad)


def test_django_script_embeds_logins_and_updates_context():
    s = build_django_script(LOGINS)
    blob = json.dumps(LOGINS)
    assert blob in s                        # embedded (stdin transit only)
    assert "Config" in s and "context" in s
    assert "full_clean" in s
    # password VALUES appear only inside the embedded blob, never elsewhere
    rest = s.replace(blob, "")
    assert "s3cret1" not in rest and "s3cret2" not in rest


def test_redact_removes_every_password():
    out = "set puck06 s3cret1 ok; s3cret2 too"
    assert "s3cret" not in redact(out, LOGINS)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools/fleet && uv run pytest tests/test_set_device_vars.py -q`
Expected: FAIL (import error)

- [ ] **Step 3: Implement `set_device_vars.py`**

Helpers exactly as tested: `validate_logins` (dict non-empty; every entry has
`username` starting `wifi-` and non-empty `password`), `build_django_script`
(json-embed logins; per machine `Device.objects.get(name=…)` →
`Config.objects.get_or_create` → `c.context.update(...)` → `full_clean/save`;
print `context-set: <n>/<n> missing: [...]` only), `redact(text, logins)`
(replace every password value with `<REDACTED>`). `main()`: argparse
(`--puck NN` repeatable; default = all registered pucks reported by the wisp
side), the two ssh subprocess calls (`SSH_TEN64`/`SSH_WISP` command lists
copied from `openwisp/build-templates.py:54-58`), redact both stdout and
stderr before printing, exit non-zero unless `missing` is empty.

- [ ] **Step 4: Run tests**

Run: `cd tools/fleet && uv run pytest -q`
Expected: 130 passed (123 from Task 2 + 7 new: 1+4 parametrized+1+1).

- [ ] **Step 5: Commit**

```bash
git add tools/fleet/set_device_vars.py tools/fleet/tests/test_set_device_vars.py
git commit -m "fleet: set_device_vars CLI (wifi show-login -> OpenWISP context)"
```

### Task 5: ansells-presence template in build-templates.py

**Files:**
- Modify: `openwisp/build-templates.py`
- Test: `tools/fleet/tests/test_presence_template.py`

- [ ] **Step 1: Write the failing tests** (load the script by path — it is not a package)

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ansells-presence pieces of openwisp/build-templates.py."""
import importlib.util
from pathlib import Path

BT_PATH = Path(__file__).resolve().parents[3] / "openwisp" / "build-templates.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_templates", BT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pucks_includes_puck03():
    assert "puck03" in _load().PUCKS


def test_presence_files():
    files = _load().netjson_presence()["files"]
    paths = {f["path"]: f for f in files}
    assert set(paths) == {
        "/opt/presence-detector/presence-detector.py",
        "/etc/presence-detector/settings.json",
        "/etc/init.d/presence-detector",
    }
    assert paths["/etc/presence-detector/settings.json"]["mode"] == "0600"
    assert paths["/etc/init.d/presence-detector"]["mode"] == "0755"
    assert paths["/opt/presence-detector/presence-detector.py"]["mode"] == "0755"


def test_presence_settings_uses_context_vars_no_secrets():
    import json
    files = _load().netjson_presence()["files"]
    settings = next(f for f in files
                    if f["path"] == "/etc/presence-detector/settings.json")
    c = settings["contents"]
    for var in ("{{ mqtt_username }}", "{{ mqtt_password }}", "{{ name }}"):
        assert var in c
    # valid JSON once vars are substituted with dummies
    parsed = json.loads(c.replace("{{ mqtt_username }}", "u")
                         .replace("{{ mqtt_password }}", "p")
                         .replace("{{ name }}", "puck99"))
    assert parsed["mqtt_host"] == "ha.welland.mithis.com"
    assert parsed["fallback_sync_interval"] == 60
    assert parsed["filter_is_denylist"] is True and parsed["filter"] == []
    assert parsed["interfaces"] == []
    assert parsed["source_type"] == "router"


def test_presence_script_matches_vendored_copy():
    mod = _load()
    vendored = (BT_PATH.parent / "presence" / "presence-detector.py").read_text()
    files = mod.netjson_presence()["files"]
    script = next(f for f in files
                  if f["path"] == "/opt/presence-detector/presence-detector.py")
    assert script["contents"] == vendored


def test_base_hook_guards_presence_service():
    hook = _load().POST_RELOAD_HOOK
    assert "/etc/init.d/presence-detector" in hook
    assert "[ -x /usr/bin/python3 ]" in hook   # no-op until deploy installs python


def test_django_script_upserts_and_attaches_presence():
    d = _load().DJANGO
    assert "ansells-presence" in d
    assert "PRESENCE" in d
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools/fleet && uv run pytest tests/test_presence_template.py -q`
Expected: FAIL (`AttributeError: netjson_presence` / puck03 assertion)

- [ ] **Step 3: Implement in `build-templates.py`**

1. `from pathlib import Path` (top). `PRESENCE_DIR = Path(__file__).resolve().parent / "presence"`.
2. `PUCKS`: insert `"puck03"` (full 01–12); update the stale “No puck03 exists” comment (fresh install registered 2026-07-25).
3. Settings constant + builder:

```python
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
```

4. `POST_RELOAD_HOOK`: before the final `exit 0` add:

```sh
# presence-detector (ansells-presence template); python3 arrives via
# tools/fleet/deploy_presence.py — silently skip until both pieces exist.
if [ -x /etc/init.d/presence-detector ] && [ -x /usr/bin/python3 ]; then
	/etc/init.d/presence-detector enable
	/etc/init.d/presence-detector restart
fi
```

5. `DJANGO` script: add `PRESENCE = json.loads({presence!r})` beside the other loads; upsert after the mesh block:

```python
pr, prcreated = Template.objects.update_or_create(
    organization=org, name="ansells-presence",
    defaults=dict(type="generic", backend="netjsonconfig.OpenWrt",
                  config=PRESENCE, default=False),
)
pr.full_clean(); pr.save()
print("ansells-presence:", "created" if prcreated else "updated", "id=", pr.id)
```

In the attach loop change `want = (b, tw) if name == "tenwrt" else (b, t)` to
`want = (b, tw) if name == "tenwrt" else (b, t, pr)` and, mirroring the
tenwrt/puck-template guard, remove `pr` from tenwrt if present (spec: tenwrt
out of scope). In `main()`, pass `presence=json.dumps(netjson_presence())`
into `DJANGO.format(...)`.

- [ ] **Step 4: Run tests**

Run: `cd tools/fleet && uv run pytest -q`
Expected: 136 passed (130 from Task 4 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add openwisp/build-templates.py tools/fleet/tests/test_presence_template.py
git commit -m "openwisp: ansells-presence template + puck03 in PUCKS + hook enable"
```

### Task 6: Docs

**Files:**
- Modify: `openwisp/README.md` (if it documents the template family — add ansells-presence one-liner)
- Modify: `docs/superpowers/specs/2026-07-29-wifi-presence-design.md` (status line: implementation complete, deployment pending gate)

- [ ] **Step 1: Make both edits** (template list + status). Keep to a few lines each. The spec status edit must also record two implementation deviations: (a) the per-puck broker verify is a puck-side syslog check, with the on-broker check done once fleet-wide in the runbook (Task 3 note); (b) `ap_name` uses `{{ name }}` — OpenWISP's built-in device-name variable — not the spec's `{{hostname}}` (which is not a default device variable).
- [ ] **Step 2: Commit**

```bash
git add openwisp/README.md docs/superpowers/specs/2026-07-29-wifi-presence-design.md
git commit -m "docs: ansells-presence template + spec status"
```

---

## Part B — gdoc2netcfg: `wifi show-login`

### Task 7: `gdoc2netcfg wifi show-login` subcommand (TDD)

**Files:**
- Worktree: create `gdoc2netcfg/.worktrees/wifi-show-login` (branch `wifi-show-login` from `wifi-sheet-hosts`)
- Modify: `src/gdoc2netcfg/cli/main.py` (beside `cmd_wifi_register_broker`, ~line 2317)
- Test: `tests/test_cli/test_wifi_show_login.py`

- [ ] **Step 1: Create the worktree + baseline**

```bash
cd /home/tim/local/gwifi/gdoc2netcfg
git worktree add .worktrees/wifi-show-login -b wifi-show-login wifi-sheet-hosts
cd .worktrees/wifi-show-login && uv run pytest -q
```

Expected: baseline green (~1963 tests per PR #18 state; record the exact number).

- [ ] **Step 2: Write the failing tests**

Model fixtures on `tests/test_cli/test_tasmota_register_broker.py` (Host +
PipelineConfig construction) but with `sheet_type="WiFi"` hosts, patching
`_build_pipeline` and `_load_config`. Cover:

```python
def test_show_login_all_hosts_json(capsys):  # no positional args -> every WiFi host
def test_show_login_single_host_text(capsys):  # "puck06" -> one "wifi-puck06 <password>" line
def test_show_login_unknown_host_errors():     # exit 1, message names the unknown machine
def test_show_login_never_touches_broker():    # register_logins is NOT imported/called
def test_show_login_json_shape(capsys):        # {machine: {"username","password"}}
```

Assertions derive expected values with the same
`derivations.wifi_credentials.build_logins` / shared `username(PREFIX, host)`
the implementation uses (no hardcoded fake hashes).

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_cli/test_wifi_show_login.py -q`
Expected: FAIL (no `cmd_wifi_show_login`)

- [ ] **Step 4: Implement**

```python
def cmd_wifi_show_login(args: argparse.Namespace) -> int:
    """Print derived WiFi-device broker logins (device-side out-of-band config).

    Same derivation as `wifi register-broker` (single source of truth); reads
    mqtt_secret from the site toml, so on prod this runs as root like
    `password`.  Never contacts the broker.
    """
    from gdoc2netcfg.derivations.mqtt_credentials import username
    from gdoc2netcfg.derivations.wifi_credentials import (
        PREFIX, build_logins, select_wifi_hosts)

    config = _load_config(args)
    _records, hosts, _inventory, _result = _build_pipeline(config)
    selected = select_wifi_hosts(hosts)
    logins = build_logins(config.wifi.mqtt_secret, hosts)   # collision-checked
    by_machine = {h.machine_name: username(PREFIX, h) for h in selected}
    wanted = args.hosts or sorted(by_machine)
    unknown = [m for m in wanted if m not in by_machine]
    if unknown:
        print(f"Error: not WiFi-sheet hosts: {', '.join(unknown)}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({m: {"username": by_machine[m],
                              "password": logins[by_machine[m]]}
                          for m in wanted}, indent=2))
    else:
        for m in wanted:
            print(by_machine[m], logins[by_machine[m]])
    return 0
```

(Adjust the import of `username` to wherever `wifi_credentials` actually
re-exports it from — mirror `build_logins`'s own imports. Add a local
`import json` inside the function — `main.py` does not import json at module
level.) **Wiring — the file does NOT use `set_defaults(func=…)`;** it uses
explicit dispatch: add a `show-login` parser under the existing
`wifi_subparsers` (~line 3121, beside `register-broker`) with positional
`hosts` (`nargs="*"`) and `--json`, then add an
`elif args.wifi_command == "show-login": return cmd_wifi_show_login(args)`
branch in the `args.command == "wifi"` dispatch block (~line 3310) — without
that branch the subcommand parses but silently falls through to
`wifi_parser.print_help()`. Update `CLAUDE.md`'s command list with one line.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_cli/test_wifi_show_login.py -q && uv run pytest -q`
Expected: new tests + whole suite green; `uv run ruff check src/ tests/` clean.

- [ ] **Step 6: Commit**

```bash
git add src/gdoc2netcfg/cli/main.py tests/test_cli/test_wifi_show_login.py CLAUDE.md
git commit -m "feat(cli): wifi show-login — emit derived device-side broker logins"
```

Note: merges into PR #18's branch or follows it — either way it deploys with
the gate, so Part C's step 0 covers it.

---

## Part C — GATED deployment runbook (execute ONLY after the gate)

**GATE: do not run any step below until PR #18 rollout ③ is done** —
`[wifi]`/`[wisp]` `mqtt_secret` set on ten64, `gdoc2netcfg wifi
register-broker` run (not `--dry-run`), logins verified against the broker —
and the `wifi show-login` code (Task 7) is deployed to `/opt/gdoc2netcfg` on
ten64.

- [ ] 0. Preconditions: gate above; `wifi-presence` branch merged or checked out wherever the tools run; spot-check `ssh ten64… sh -c 'cd /opt/gdoc2netcfg && exec sudo /opt/gdoc2netcfg/.venv/bin/gdoc2netcfg wifi show-login puck12'` prints one login (do not paste output anywhere) — the `cd` is required, see Task 4.
- [ ] 1. `uv run tools/fleet/set_device_vars.py` → `context-set: N/N missing: [] failed: []`. The tool itself enforces `updated + missing + failed == N` and exits non-zero on any shortfall, so a clean exit is the real gate; a mismatch means the remote loop did not finish and the run must not be trusted.
- [ ] 2. `uv run openwisp/build-templates.py` → ansells-presence created + attached to registered pucks, renders OK. **Beacon gotcha**: after agents apply, run the fleet beacon check / `wifi` reload per [[gwifi-openwisp-apply-breaks-beacon]].
      **This run is also puck03's first-ever wireless onboarding, not just a
      presence change**: Task 5 added `puck03` to `PUCKS`, so this is the
      first `build-templates.py` run that attaches `ansells-aps-base` +
      `ansells-aps-puck` to puck03 — the same event class as onboarding
      puck01/02. Treat it with the same care: verify puck03's SSIDs/beacons
      after the apply, not only the presence pieces.
      **Watch the output** for `WARNING: presence attached but mqtt context
      vars MISSING on: [...]`. If it appears, step 1 (`set_device_vars.py`)
      did not cover those devices — re-run it before letting the config
      apply reach them.
- [ ] 3. `uv run tools/fleet/deploy_presence.py` → all-OK matrix (files/apk/service/mqtt per puck). Re-run note: the `mqtt` check greps the last 20 presence-detector syslog lines, so after fixing a failure restart that puck's service (`ssh root@<ip> /etc/init.d/presence-detector restart`) to age out old error lines before re-running.
- [ ] 4. Broker-side verify (creds from ten64's sensors2mqtt env; never echo them):
      `ssh ten64.welland.mithis.com 'sudo sh -c ". /etc/sensors2mqtt/env; mosquitto_sub -h ha.welland.mithis.com -u $MQTT_USER -P $MQTT_PASSWORD -t \"homeassistant/device_tracker/+/config\" -C 5 -W 30"'`
      Expected: discovery payloads with `puckNN_` slugs. Then flip a known client (toggle wifi on a phone) and watch its state topic go home/not_home.
- [ ] 5. HA UI: confirm entities exist; assign phone trackers to Persons (user step).
- [ ] 6. Update memory (`wisp-homeassistant-integration.md`) + task #1; flag the image-bake follow-up (python3+paho+files into the gale fleet image).
