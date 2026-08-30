# usteer Band Steering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make 802.11v band steering actually work on `ansells` / `ansells-guest`, and build the instrument that proves it.

**Architecture:** Two config values in the existing openwisp `USTEER_CONFIG` template fix the inert association path and turn on event logging. A new pure-logic module (`galeflash/steerreport.py`) parses usteer's `connected_clients` ubus output, with a thin CLI (`tools/fleet/steer_report.py`) doing the ssh I/O — the same split every other fleet tool uses. Rollout is a runtime-only `ubus update_config` canary first, then the template.

**Tech Stack:** Python 3.12 + pytest via `uv`; OpenWrt `ubus`; usteer 2025.10.04~1d6524c6; OpenWISP templates.

**Spec:** `docs/superpowers/specs/2026-08-24-usteer-band-steering-design.md`

---

---

## STATUS 2026-08-30 — partially executed, association half REVERTED

This plan was executed out of order and is **not** a live to-do list. Actual
state, verified against both controllers and the pucks on 2026-08-30:

| Task | State |
|---|---|
| 1–4 `steerreport.py` / `steer_report.py` audit tooling | **never built** — no such files exist |
| 5 fix the inert config | done 2026-08-26 → **association half reverted 2026-08-29** |
| 6 live canary on one puck | done (puck07) — did **not** catch the regression; see below |
| 7 functional test with `rpi4-pmod` | **never run** |
| 8 roll out to both sites | done 2026-08-26; welland reverted 2026-08-29, monarto still carries the 2026-08-26 config |

**The regression:** `assoc_steering=1` + `load_balancing_threshold=1` +
`signal_diff_threshold=10` made every AP at welland deny associations
(`status_code=17`, `reason=better_candidate`). Reverted by hand on the welland
controller. `roam_trigger_snr '34'` and the two `event_log_types` were kept.
Full analysis: the 2026-08-29 addendum in the design doc.

**Why Task 6 missed it:** the failure denies *new* associations and leaves
existing ones alone, and the deadlock requires several APs running the config
at once. A single-puck canary watching an already-connected laptop was
structurally incapable of seeing it.

**Do not resume Tasks 1–4 as written.** Their premise is that the association
path is on and needs an instrument to prove it works. The instrument is still
worth building, but its job is now the opposite: measure association
*success* and detect mutual deferral. Re-read the design addendum first.

**Monarto is still on the unreverted config** — a known divergence, not an
oversight. It has ~4 clients across 4 APs, too few to trigger the deadlock.

---

## Essential context (read before starting)

You are working in the worktree `.worktrees/usteer-band-steering` on branch
`usteer-band-steering`. Baseline is 237 fleet + 19 openwisp tests passing.

**Run tests like this** — the fleet suite has its own `uv` project:

```bash
cd tools/fleet && uv run pytest -q                  # 237 tests
cd <repo-root> && uv run --with pytest pytest tests/openwisp -q   # 19 tests
```

**Five facts that will otherwise cost you an hour each:**

1. **usteer reports all times in milliseconds.** `connected`, `age`,
   `last-kick` are ms since the event. Divide by 1000. A live sample showed
   `"connected": 7093002` for a ~2 hour association.

2. **`age == 0` means "never", not "just now".** usteer writes literal 0 when
   the timestamp is unset (`ubus.c:437`:
   `si->bss_transition_response.timestamp ? current_time - ... : 0`). Map 0 to
   `None`, never to "0 seconds ago". This distinction is the entire point of
   the tool.

3. **Guest VLAN 99 has no DHCP by design.** See the comment block in
   `tools/fleet/galeflash/vlanreach.py:24-33` — the ten64 offers no L3 service
   on guest at all. A client on `ansells-guest` gets **no IP**. That is
   expected and is not a failure of your test. Association alone is what
   usteer acts on.

4. **`update_config` merges scalars but REPLACES lists — always restate every
   array field.** `set_config` is worse (it calls `usteer_init_defaults()`
   first, `ubus.c:259`), but `update_config` is not the safe merge it looks
   like. At `ubus.c:262-283` the BOOL/I32/U32 cases `continue` when the field
   is absent, while `CFG_ARRAY_CB`/`CFG_STRING_CB` call
   `config_data[i].ptr.CB.set(tb[i])` unconditionally — so an omitted list is
   set from NULL and ends up **empty**. Proven on puck07 2026-08-26: a call
   carrying two integers silently emptied `ssid_list`, leaving usteer tracking
   nothing. Always include `ssid_list` and `interfaces`, and always diff
   `get_config` before/after. Recovery: `/etc/init.d/usteer restart`.

5. **The usteer UCI section must stay named `usteer1`.** openwisp merges
   `/etc/config/*` by section name; an anonymous section appends a fresh copy
   on every apply. There is already a regression test for this
   (`tests/openwisp/test_build_templates.py:170`).

**Project conventions that apply here:** never create files in `/tmp` (use a
project-local `tmp/`, and clean up only files you created, by name); never
redirect stderr to `/dev/null`; always `uv run`, never bare `python`; ISO or
day-first dates only; small discrete commits.

---

## File structure

| File | Responsibility |
|---|---|
| `tools/fleet/galeflash/steerreport.py` | **Create.** Pure logic: parse one puck's `connected_clients` JSON into `ClientState` records; classify band; summarise. No I/O. |
| `tools/fleet/tests/test_steerreport.py` | **Create.** Unit tests for the above, using inline JSON fixtures captured from live pucks. |
| `tools/fleet/steer_report.py` | **Create.** CLI: ssh to each puck, `ubus call usteer connected_clients`, hand payloads to the module, print the table. |
| `openwisp/build-templates.py` | **Modify** `USTEER_CONFIG` at line 261. Two added options. |
| `tests/openwisp/test_build_templates.py` | **Modify.** Assert the two new options and that `ansells-iot` is still absent. |
| `tools/fleet/README.md` | **Modify.** Document `steer_report.py`. |

---

### Task 1: `steerreport.py` — band classification

**Files:**
- Create: `tools/fleet/galeflash/steerreport.py`
- Test: `tools/fleet/tests/test_steerreport.py`

usteer node keys look like `hostapd.wl-guest-2g4` for a local node and
`10.1.4.103#hostapd.wl-main-2g4` for a remote one. `connected_clients` only
emits local nodes, but strip the `ip#` prefix defensively.

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.steerreport — usteer connected_clients parsing."""
import pytest

from galeflash.steerreport import iface_from_node, band_of


def test_iface_from_node_strips_hostapd_prefix():
    assert iface_from_node("hostapd.wl-guest-2g4") == "wl-guest-2g4"


def test_iface_from_node_strips_remote_ip_prefix():
    assert iface_from_node("10.1.4.103#hostapd.wl-main-2g4") == "wl-main-2g4"


def test_band_of_classifies_both_bands():
    assert band_of("wl-guest-2g4") == "2g4"
    assert band_of("wl-main-5g") == "5g"


def test_band_of_rejects_unknown_suffix():
    with pytest.raises(ValueError, match="cannot classify"):
        band_of("wl-weird-6g")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/fleet && uv run pytest tests/test_steerreport.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'galeflash.steerreport'`

- [ ] **Step 3: Write minimal implementation**

```python
# SPDX-License-Identifier: Apache-2.0
"""Pure logic for the usteer band-steering audit.

Parses `ubus call usteer connected_clients` into records that answer one
question: is band steering actually happening?  All ssh I/O lives in
tools/fleet/steer_report.py.  Fail loud: unrecognised shapes raise.

usteer only tracks SSIDs listed in its `ssid_list`, so anything absent from
that list is invisible here -- an empty result may mean "not tracked" rather
than "no clients".
"""


def iface_from_node(node: str) -> str:
    """'10.1.4.103#hostapd.wl-main-2g4' -> 'wl-main-2g4'."""
    tail = node.split("#", 1)[-1]
    prefix = "hostapd."
    if not tail.startswith(prefix):
        raise ValueError(f"cannot parse usteer node name: {node!r}")
    return tail[len(prefix):]


def band_of(iface: str) -> str:
    """'wl-main-5g' -> '5g'.  Band drives the whole steering decision."""
    if iface.endswith("-5g"):
        return "5g"
    if iface.endswith("-2g4"):
        return "2g4"
    raise ValueError(f"cannot classify band for interface {iface!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/fleet && uv run pytest tests/test_steerreport.py -q`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add tools/fleet/galeflash/steerreport.py tools/fleet/tests/test_steerreport.py
git commit -m "fleet: steerreport band + node-name classification"
```

---

### Task 2: `steerreport.py` — parse a client record

**Files:**
- Modify: `tools/fleet/galeflash/steerreport.py`
- Test: `tools/fleet/tests/test_steerreport.py`

This is where facts 1 and 2 from the context section land. Get them wrong and
the tool reports the opposite of the truth.

- [ ] **Step 1: Write the failing test**

Append to `tools/fleet/tests/test_steerreport.py`:

```python
from galeflash.steerreport import ClientState, parse_connected_clients

# Shape captured live from puck10, 2026-08-24.
LIVE = {
    "hostapd.wl-main-5g": {
        "60:45:2e:47:77:96": {
            "signal": -54,
            "created": 7100000,
            "connected": 7093002,
            "snr-kick": {"seen-below": 0},
            "roam-state-machine": {
                "state": "ROAM_TRIGGER_IDLE", "tries": 0, "event": 0,
                "kick-count": 0, "last-kick": 0,
                "scan_start": 0, "scan_timeout_start": 0,
            },
            "bss-transition-response": {"status-code": 0, "age": 0},
            "beacon-measurement-modes": ["PASSIVE", "ACTIVE"],
            "link-measurement": 1,
            "bss-transition-management": 1,
            "multi-band-operation": 0,
            "measurements": [],
        }
    }
}


def test_parse_converts_milliseconds_to_seconds():
    [c] = parse_connected_clients("puck10", LIVE)
    assert c.connected_s == 7093        # 7093002 ms, not 7093002 s


def test_parse_maps_zero_age_to_never_not_now():
    """age==0 is usteer's 'never answered', NOT 'answered 0s ago'."""
    [c] = parse_connected_clients("puck10", LIVE)
    assert c.tm_age_s is None
    assert c.steered is False


def test_parse_reads_capability_and_identity():
    [c] = parse_connected_clients("puck10", LIVE)
    assert (c.puck, c.iface, c.band) == ("puck10", "wl-main-5g", "5g")
    assert c.mac == "60:45:2e:47:77:96"
    assert c.bss_tm is True             # advertises 802.11v
    assert c.signal == -54
    assert c.kick_count == 0
    assert c.roam_state == "ROAM_TRIGGER_IDLE"


def test_parse_marks_a_client_that_answered_a_transition_request():
    payload = {"hostapd.wl-guest-2g4": {"aa:bb:cc:dd:ee:ff": {
        "signal": -40, "connected": 120000,
        "roam-state-machine": {"state": "ROAM_TRIGGER_IDLE", "kick-count": 1},
        "bss-transition-response": {"status-code": 0, "age": 45000},
        "bss-transition-management": 1,
    }}}
    [c] = parse_connected_clients("puck12", payload)
    assert c.tm_age_s == 45             # 45000 ms
    assert c.steered is True            # a request WAS sent and answered
    assert c.tm_status == 0             # 0 = accepted


def test_parse_tolerates_missing_optional_blocks():
    payload = {"hostapd.wl-main-2g4": {"11:22:33:44:55:66": {"signal": -60}}}
    [c] = parse_connected_clients("puck03", payload)
    assert c.bss_tm is False
    assert c.tm_age_s is None
    assert c.kick_count == 0


def test_parse_rejects_a_non_mapping_client_entry():
    with pytest.raises(ValueError, match="unexpected client entry"):
        parse_connected_clients("puck03", {"hostapd.wl-main-5g": {"m": 1}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/fleet && uv run pytest tests/test_steerreport.py -q`
Expected: FAIL, `ImportError: cannot import name 'ClientState'`

- [ ] **Step 3: Write minimal implementation**

Add to `tools/fleet/galeflash/steerreport.py`:

```python
from typing import NamedTuple


class ClientState(NamedTuple):
    """One connected station as usteer sees it."""
    puck:        str
    iface:       str
    band:        str          # "2g4" | "5g"
    mac:         str
    signal:      int
    connected_s: int
    bss_tm:      bool         # advertises 802.11v BSS Transition Management
    tm_status:   int | None   # last transition response status (0 = accepted)
    tm_age_s:    int | None   # seconds since that response; None = never
    kick_count:  int
    roam_state:  str

    @property
    def steered(self) -> bool:
        """True once this client has ever answered a transition request.

        That is the only positive proof usteer offers that a steer was
        actually transmitted -- there is no band-steering event type.
        """
        return self.tm_age_s is not None


def _ms_to_s(value) -> int:
    return int(value) // 1000


def parse_connected_clients(puck: str, payload: dict) -> list[ClientState]:
    """Parse one puck's `ubus call usteer connected_clients` output."""
    out: list[ClientState] = []
    for node, clients in (payload or {}).items():
        iface = iface_from_node(node)
        band = band_of(iface)
        for mac, info in (clients or {}).items():
            if not isinstance(info, dict):
                raise ValueError(
                    f"unexpected client entry for {mac!r} on {node!r}: {info!r}")
            resp = info.get("bss-transition-response") or {}
            rsm = info.get("roam-state-machine") or {}
            # age==0 is usteer's sentinel for "never answered" (ubus.c:437),
            # so it must become None rather than a real zero-second age.
            raw_age = resp.get("age", 0)
            out.append(ClientState(
                puck=puck,
                iface=iface,
                band=band,
                mac=mac,
                signal=int(info.get("signal", 0)),
                connected_s=_ms_to_s(info.get("connected", 0)),
                bss_tm=bool(info.get("bss-transition-management", 0)),
                tm_status=resp.get("status-code") if raw_age else None,
                tm_age_s=_ms_to_s(raw_age) if raw_age else None,
                kick_count=int(rsm.get("kick-count", 0)),
                roam_state=rsm.get("state", "?"),
            ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/fleet && uv run pytest tests/test_steerreport.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add tools/fleet/galeflash/steerreport.py tools/fleet/tests/test_steerreport.py
git commit -m "fleet: parse usteer connected_clients into ClientState"
```

---

### Task 3: `steerreport.py` — fleet summary

**Files:**
- Modify: `tools/fleet/galeflash/steerreport.py`
- Test: `tools/fleet/tests/test_steerreport.py`

- [ ] **Step 1: Write the failing test**

```python
from galeflash.steerreport import Summary, summarise


def _cs(**kw):
    base = dict(puck="p", iface="wl-main-2g4", band="2g4", mac="a", signal=-50,
                connected_s=100, bss_tm=False, tm_status=None, tm_age_s=None,
                kick_count=0, roam_state="ROAM_TRIGGER_IDLE")
    base.update(kw)
    return ClientState(**base)


def test_summarise_counts_capability_and_evidence():
    s = summarise([
        _cs(mac="a", bss_tm=True, band="5g", iface="wl-main-5g"),
        _cs(mac="b", bss_tm=True, tm_age_s=30, tm_status=0),
        _cs(mac="c", bss_tm=False),
    ])
    assert s == Summary(tracked=3, tm_capable=2, steered=1, on_2g4=2, on_5g=1)


def test_summarise_of_nothing_is_all_zero():
    assert summarise([]) == Summary(0, 0, 0, 0, 0)


def test_steering_is_unproven_when_nothing_ever_answered():
    """The fleet's state on 2026-08-24: capable clients, zero steers."""
    s = summarise([_cs(mac="a", bss_tm=True), _cs(mac="b", bss_tm=True)])
    assert s.tm_capable == 2
    assert s.steered == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/fleet && uv run pytest tests/test_steerreport.py -q`
Expected: FAIL, `ImportError: cannot import name 'Summary'`

- [ ] **Step 3: Write minimal implementation**

```python
class Summary(NamedTuple):
    tracked:    int
    tm_capable: int   # advertise 802.11v -- steerable at all
    steered:    int   # have answered a request -- proof a steer was sent
    on_2g4:     int
    on_5g:      int


def summarise(states) -> Summary:
    states = list(states)
    return Summary(
        tracked=len(states),
        tm_capable=sum(1 for c in states if c.bss_tm),
        steered=sum(1 for c in states if c.steered),
        on_2g4=sum(1 for c in states if c.band == "2g4"),
        on_5g=sum(1 for c in states if c.band == "5g"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/fleet && uv run pytest -q`
Expected: PASS, 250 tests (237 baseline + 13 new)

- [ ] **Step 5: Commit**

```bash
git add tools/fleet/galeflash/steerreport.py tools/fleet/tests/test_steerreport.py
git commit -m "fleet: summarise steering capability vs actual evidence"
```

---

### Task 4: `steer_report.py` CLI

**Files:**
- Create: `tools/fleet/steer_report.py`

Follow the I/O shape of `tools/fleet/check_vlan_reach.py`. No new tests —
this file is I/O only; the logic is already covered.

- [ ] **Step 1: Write the CLI**

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Report whether usteer band steering is actually happening.

Per reachable puck, reads `ubus call usteer connected_clients` and shows each
tracked station's 802.11v capability and whether it has ever answered a BSS
transition request.  Read-only: changes nothing.

usteer only tracks SSIDs in its `ssid_list`.  As of 2026-08-24 that is
'ansells' and 'ansells-guest' -- clients on 'ansells-iot' are invisible here
by design, so an empty table is not the same as "no clients".
"""
import argparse
import concurrent.futures
import json
import subprocess
import sys

from galeflash.steerreport import parse_connected_clients, summarise

WELLAND = [(f"puck{n:02d}", f"10.1.4.{100 + n}")
           for n in (3, 6, 7, 10, 11, 12)]
MONARTO = [("puck05", "10.2.4.105"), ("puck13", "10.2.4.113"),
           ("puck14", "10.2.4.114"), ("puck15", "10.2.4.115")]
SITES = {"welland": (None, WELLAND),
         "monarto": ("tim@ten64.monarto.mithis.com", MONARTO)}


def fetch(jump, puck, ip, timeout):
    cmd = ["ssh", "-o", "ConnectTimeout=12", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new"]
    if jump:
        cmd += ["-J", jump]
    cmd += [f"root@{ip}", "ubus call usteer connected_clients"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return puck, None, "timed out"
    if r.returncode != 0:
        return puck, None, (r.stderr or "").strip().splitlines()[-1:] or "failed"
    try:
        return puck, json.loads(r.stdout), None
    except json.JSONDecodeError as exc:
        return puck, None, f"unparseable ubus output: {exc}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", choices=sorted(SITES), default="welland")
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()

    jump, pucks = SITES[args.site]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pucks)) as ex:
        results = list(ex.map(
            lambda p: fetch(jump, p[0], p[1], args.timeout), pucks))

    states, unreachable = [], []
    for puck, payload, err in results:
        if err:
            unreachable.append((puck, err))
            continue
        states.extend(parse_connected_clients(puck, payload))

    print(f"{'puck':7} {'iface':14} {'mac':18} {'band':5} {'11v':3} "
          f"{'steered':7} {'tm_age':>7} {'kick':4} {'sig':>4} {'conn':>7}")
    print("-" * 88)
    for c in sorted(states):
        age = "never" if c.tm_age_s is None else f"{c.tm_age_s}s"
        print(f"{c.puck:7} {c.iface:14} {c.mac:18} {c.band:5} "
              f"{'yes' if c.bss_tm else 'no':3} "
              f"{'YES' if c.steered else 'no':7} {age:>7} "
              f"{c.kick_count:<4} {c.signal:>4} {c.connected_s:>6}s")

    s = summarise(states)
    print(f"\ntracked={s.tracked} 11v-capable={s.tm_capable} "
          f"steered={s.steered} 2g4={s.on_2g4} 5g={s.on_5g}")
    if s.tracked and not s.steered:
        print("NOTE: no client has ever answered a transition request -- "
              "band steering has not fired.")
    for puck, err in unreachable:
        print(f"  !! {puck}: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it runs against the live fleet**

Run: `cd tools/fleet && uv run steer_report.py --site welland`
Expected: a table plus the NOTE line — this is the documented pre-change
state (2 clients, both 11v-capable, `steered=0`). Capturing that baseline is
the point; do not treat it as an error.

- [ ] **Step 3: Commit**

```bash
git add tools/fleet/steer_report.py
git commit -m "fleet: steer_report.py CLI"
```

---

### Task 5: fix the inert config

**Files:**
- Modify: `openwisp/build-templates.py:261-270`
- Test: `tests/openwisp/test_build_templates.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/openwisp/test_build_templates.py`:

```python
def test_usteer_load_balancing_threshold_is_nonzero():
    """This is THE fix.  is_better_candidate() has three ways to return a
    candidate; two are gated on thresholds and one is an upstream bug that
    ANDs a predicate with its own negation.  With load_balancing_threshold
    at 0, below_assoc_threshold() returns false on its first line, so
    find_better_candidate() always returns NULL and assoc_steering never
    denies anything.  A non-zero value un-gates the comparison and lets the
    existing band_steering_threshold=5 bias apply.
    """
    assert "option load_balancing_threshold '0'" not in bt.USTEER_CONFIG
    assert "option load_balancing_threshold '1'" in bt.USTEER_CONFIG


def test_usteer_logs_assoc_decisions():
    for evt in ("assoc_req_accept", "assoc_req_deny"):
        assert f"list event_log_types '{evt}'" in bt.USTEER_CONFIG


def test_usteer_does_not_log_probe_events():
    """65 IoT devices probing would flood the per-net rsyslog."""
    assert "probe_req" not in bt.USTEER_CONFIG


def test_usteer_still_excludes_the_iot_ssid():
    """Phase 2.  The IoT BSSes also lack the AP-side bss_transition switch,
    so listing them here alone would steer nothing anyway."""
    assert "ansells-iot" not in bt.USTEER_CONFIG
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest pytest tests/openwisp -q`
Expected: FAIL — `load_balancing_threshold '1'` and `event_log_types` absent

- [ ] **Step 3: Edit `USTEER_CONFIG`**

Replace lines 261-270 of `openwisp/build-templates.py`:

```python
USTEER_CONFIG = """config usteer 'usteer1'
	option network 'mgmt'
	option local_mode '0'
	option assoc_steering '1'
	option load_balancing_threshold '1'
	option load_kick_enabled '0'
	option syslog '1'
	list event_log_types 'assoc_req_accept'
	list event_log_types 'assoc_req_deny'
	list ssid_list 'ansells'
	list ssid_list 'ansells-guest'
"""
```

Add above the existing comment block:

```python
# load_balancing_threshold was '0', which silently disabled the whole
# association-steering path: below_assoc_threshold() (policy.c:32) returns
# false on its first line when it is zero, better_signal_strength() likewise
# when signal_diff_threshold is zero, and the third reason at policy.c:110 is
# an upstream bug (`has_better_load(a,b) && !has_better_load(a,b)`).  With all
# three dead, find_better_candidate() always returned NULL and assoc_steering
# never denied anything.  '1' un-gates it so band_steering_threshold=5 -- the
# only band-preference control on that path, and dead config until now --
# finally applies.  Deliberately NOT signal_diff_threshold: 5 GHz has higher
# path loss, so that comparison would push clients toward 2.4 GHz.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest pytest tests/openwisp -q`
Expected: PASS, 23 tests

- [ ] **Step 5: Commit**

```bash
git add openwisp/build-templates.py tests/openwisp/test_build_templates.py
git commit -m "openwisp: un-gate usteer assoc steering, log assoc decisions"
```

---

### Task 6: live canary on one puck

**Files:** none — live change, runtime only.

usteer has no UCI write-back anywhere in its source, so `update_config` is
runtime-only and a reboot reverts it.

- [ ] **Step 1: Record the current config**

```bash
ssh root@10.1.4.112 'ubus call usteer get_config' > tmp/usteer-puck12-before.json
```

- [ ] **Step 2: Apply the canary**

Restate `ssid_list` and `interfaces` even though you are not changing them —
omitting an array field empties it (see fact 4).

```bash
ssh root@10.1.4.112 "ubus call usteer update_config \
  '{\"load_balancing_threshold\":1,\
    \"event_log_types\":[\"assoc_req_accept\",\"assoc_req_deny\"],\
    \"ssid_list\":[\"ansells\",\"ansells-guest\"],\
    \"interfaces\":[\"br0.4\"]}'"
```

- [ ] **Step 3: Verify it took, and that nothing else moved**

```bash
ssh root@10.1.4.112 'ubus call usteer get_config' > tmp/usteer-puck12-after.json
diff tmp/usteer-puck12-before.json tmp/usteer-puck12-after.json
```
Expected: exactly two changed keys. **If `ssid_list` or `network` changed you
used `set_config` — revert with `/etc/init.d/usteer restart` immediately.**

- [ ] **Step 4: Confirm the radios are unharmed**

```bash
ssh root@10.1.4.112 'iw dev | grep -c Interface; logread | grep -c "Failed to set beacon"'
```
Expected: `6` and `0`.

- [ ] **Step 5: Clean up the files you created**

```bash
rm -v tmp/usteer-puck12-before.json tmp/usteer-puck12-after.json
```

---

### Task 7: functional test with `rpi4-pmod`

**Files:** none — live test.

`rpi4-pmod` is a Raspberry Pi 4 Model B Rev 1.5, dual-band, and dual-homed
(holds both an `eth0` and a `wlan0` lease). Manage it over ethernet
throughout; guest's `isolate=1` then does not matter. Reachable as
`tim@rpi4-pmod.iot.welland.mithis.com`.

Remember: guest VLAN 99 has **no DHCP by design**. The Pi will associate and
get no IP. That is success, not failure.

- [ ] **Step 1: Get the guest passphrase**

Use `gdoc2netcfg wifi show-login`. Do not print it to the transcript, do not
commit it, and pass it via stdin or a file, never argv.

- [ ] **Step 2: Snapshot the Pi's wifi config and ARM THE AUTO-REVERT FIRST**

```bash
sudo cp /etc/wpa_supplicant/wpa_supplicant-wlan0.conf \
        /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.pre-steertest
sudo systemd-run --on-active=20min \
  /bin/sh -c 'cp /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.pre-steertest \
                 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf && \
              systemctl restart wpa_supplicant@wlan0'
```
Arm this **before** changing anything, so the Pi self-heals even if the path
is lost mid-test.

- [ ] **Step 3: Add a 2.4 GHz-pinned guest profile**

```
network={
    ssid="ansells-guest"
    psk="<from step 1>"
    freq_list=2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462 2467 2472
    priority=10
}
```
Then `sudo systemctl restart wpa_supplicant@wlan0`.

- [ ] **Step 4: Confirm it landed on 2.4 GHz**

```bash
cd tools/fleet && uv run steer_report.py --site welland
```
Expected: the Pi's `wlan0` MAC on a `wl-guest-2g4` iface, `11v=yes`,
`steered=no`. If `11v=no`, stop — the client cannot be steered and the test
is invalid.

- [ ] **Step 5: Wait, then look for the steer**

Wait ≥120 s (`roam_trigger_interval` is 60 s; `band_steering_interval` is
120 s), then re-run the report.
Expected: `steered=YES` with a non-zero `tm_age`, and the MAC now on
`wl-guest-5g`. **This is the acceptance criterion for the whole plan.**

Also check the new event logging:
```bash
ssh root@10.1.4.112 'logread | grep -i usteer | tail -20'
```

- [ ] **Step 6: Restore the Pi**

```bash
sudo cp /etc/wpa_supplicant/wpa_supplicant-wlan0.conf.pre-steertest \
        /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
sudo systemctl restart wpa_supplicant@wlan0
```
Then cancel the pending revert timer (`systemctl list-timers | grep run-`),
and confirm the Pi is back on `ansells-iot`.

- [ ] **Step 7: Record the result in the spec**

Add a short "Verified" section to
`docs/superpowers/specs/2026-08-24-usteer-band-steering-design.md` with the
observed sequence, and commit. If steering did **not** fire, record that
instead and stop — do not proceed to Task 8.

---

### Task 8: roll out to both sites

**Files:** none — deployment.

- [ ] **Step 1: Push the template to welland**

```bash
uv run openwisp/build-templates.py --site welland
```

- [ ] **Step 2: Verify the template really carries the new options**

Query `ansells-aps-base` on wisp and confirm the `/etc/config/usteer` file
contains `load_balancing_threshold '1'` and both `event_log_types` entries.
Do not infer this from the script exiting 0.

- [ ] **Step 3: Push to monarto**

```bash
uv run openwisp/build-templates.py --site monarto
```

- [ ] **Step 4: Verify pucks converge and radios are healthy**

```bash
cd tools/fleet && uv run steer_report.py --site welland
cd tools/fleet && uv run steer_report.py --site monarto
```
Plus per puck: 6 interfaces, 0 beacon errors, and exactly **one** `usteer`
section (`uci show usteer | grep -c '=usteer'` → 1). A count above 1 means
the merge appended a duplicate — the `usteer1` naming has regressed.

- [ ] **Step 5: Commit and update the README**

```bash
git add tools/fleet/README.md
git commit -m "docs: document steer_report.py"
```

---

## Definition of done

- 250+ fleet tests and 23 openwisp tests passing.
- `steer_report.py` runs against both sites.
- A client has been observed transitioning 2.4 GHz → 5 GHz with `steered=YES`,
  recorded in the spec.
- Both sites' templates carry the change; every puck has exactly one usteer
  section, 6 interfaces, 0 beacon errors.
- `ansells-iot` still absent from `ssid_list` (Phase 2).
