# Puck Sheet Live-Data Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-pass sync of live puck data (LLDP upstream, 7 wifi BSSIDs, hostname) into the Google WiFi Pucks sheet, with the stale `eth0/eth1/wlan0/wlan1` headers renamed to real gale interface names.

**Architecture:** A new ssh collector (`collect_puck_live.py`) merges live fields into the existing `inventory/<serial>.json` records; the existing `sync_sheet.py` pushes them in one write, extended with guarded header renames and a fixed (non-truncating) read range. All column logic stays pure in `galeflash/sheetmap.py`.

**Tech Stack:** Python 3.10+ (uv script deps: `google-auth`, `requests`), pytest, ssh (OpenSSH), lldpd/`iw`/iproute2 on the pucks.

**Spec:** `docs/superpowers/specs/2026-07-22-puck-sheet-live-sync-design.md`

**Working directory for all commands:** `tools/fleet/` in the `puck-sheet-live-sync` worktree.

---

### Task 1: sheetmap — retarget MAC fields + rename map + live fields

**Files:**
- Modify: `tools/fleet/galeflash/sheetmap.py`
- Test: `tools/fleet/tests/test_sheetmap.py`

- [ ] **Step 1.1: Write the failing tests**

Append to `tests/test_sheetmap.py`:

```python
# ---------------------------------------------------------------------------
# Real 28-column header (live sheet 2026-07-22) — positions matter for the
# rename tests; matching stays name-based.
# ---------------------------------------------------------------------------

from galeflash.sheetmap import (
    LIVE_OVERWRITE_FIELDS,
    RENAME_HEADERS,
    compute_header_renames,
)

REAL_HEADER = [
    "#", "Name", "Location", "Upstream", "Controlled By", "Model", "Firmware",
    "Serial", "MAC", "Setup Network", "Setup Code",
    "eth0", "eth1", "wlan0", "wlan1",
    "MLB Serial", "Region", "HWID", "RO Firmware", "RW Firmware",
    "Depthcharge", "EC Firmware", "Flash Date", "Flash Status",
    "Backup", "Backup SHA256", "Image Archive", "Image SHA256",
]

RENAMED_HEADER = [
    "wan" if h == "eth0" else "lan" if h == "eth1"
    else "wl-main-2g4" if h == "wlan0" else "wl-main-5g" if h == "wlan1"
    else h
    for h in REAL_HEADER
]


def test_rename_headers_fresh_sheet():
    """All four stale headers produce rename entries at their positions."""
    renames, rename_conflicts = compute_header_renames(REAL_HEADER)
    assert rename_conflicts == []
    assert sorted(renames) == sorted([
        (11, "eth0", "wan"),
        (12, "eth1", "lan"),
        (13, "wlan0", "wl-main-2g4"),
        (14, "wlan1", "wl-main-5g"),
    ])


def test_rename_headers_already_renamed_is_noop():
    renames, rename_conflicts = compute_header_renames(RENAMED_HEADER)
    assert renames == []
    assert rename_conflicts == []


def test_rename_headers_missing_both_is_conflict():
    """Neither old nor new name present → conflict (sheet changed under us)."""
    header = [h for h in REAL_HEADER if h != "wlan1"]
    renames, rename_conflicts = compute_header_renames(header)
    assert any("wlan1" in c for c in rename_conflicts)


def test_rename_headers_both_present_is_conflict():
    """Old AND new name present → conflict (rename would create a duplicate)."""
    header = REAL_HEADER + ["wan"]
    renames, rename_conflicts = compute_header_renames(header)
    assert any("eth0" in c and "wan" in c for c in rename_conflicts)
    assert (11, "eth0", "wan") not in renames


def test_ethernet_macs_target_renamed_columns():
    """ethernet_mac0/1 land in the wan/lan columns of a post-rename header —
    no duplicate eth0/eth1 columns are appended."""
    extended = get_extended_header(RENAMED_HEADER)
    assert "eth0" not in extended
    assert "eth1" not in extended
    rows = [["1", "", "", "", "", "AC-1304", "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "ethernet_mac0": "AA:BB:CC:DD:EE:01",
                "ethernet_mac1": "AA:BB:CC:DD:EE:02"}]
    updates, conflicts, unmatched = compute_updates(records, RENAMED_HEADER, rows)
    assert conflicts == [] and unmatched == []
    by_col = {u.col: u.value for u in updates}
    assert by_col[RENAMED_HEADER.index("wan")] == "AA:BB:CC:DD:EE:01"
    assert by_col[RENAMED_HEADER.index("lan")] == "AA:BB:CC:DD:EE:02"


def test_wifi_fields_land_in_renamed_wlan_columns():
    """wl-main BSSIDs go to the renamed wlan0/wlan1 columns; the other five
    wifi columns are appended after the current right edge."""
    rows = [["1", "", "", "", "", "AC-1304", "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "wifi_wl_main_2g4": "44:07:0B:01:A2:28",
                "wifi_wl_main_5g": "42:07:0B:01:A2:24",
                "wifi_mesh_5g": "44:07:0B:01:A2:24"}]
    updates, conflicts, _ = compute_updates(records, RENAMED_HEADER, rows)
    assert conflicts == []
    by_col = {u.col: u.value for u in updates}
    assert by_col[RENAMED_HEADER.index("wl-main-2g4")] == "44:07:0B:01:A2:28"
    assert by_col[RENAMED_HEADER.index("wl-main-5g")] == "42:07:0B:01:A2:24"
    mesh_cols = [c for c in by_col if c >= len(RENAMED_HEADER)]
    assert len(mesh_cols) == 1
    ext = get_extended_header(RENAMED_HEADER)
    assert ext[mesh_cols[0]] == "mesh-5g"


def test_name_and_upstream_fields_map_to_existing_columns():
    rows = [["1", "", "", "", "", "AC-1304", "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "name": "puck12",
                "upstream": "sw-netgear-gsm7252ps-s1 port 1/0/46"}]
    updates, conflicts, _ = compute_updates(records, RENAMED_HEADER, rows)
    assert conflicts == []
    by_col = {u.col: u.value for u in updates}
    assert by_col[RENAMED_HEADER.index("Name")] == "puck12"
    assert by_col[RENAMED_HEADER.index("Upstream")].startswith("sw-netgear-gsm7252ps-s1")


def test_update_live_allows_upstream_overwrite_only():
    """LIVE_OVERWRITE_FIELDS unlocks a differing Upstream cell but not Name."""
    rows = [["1", "puck-old-name", "", "sw-old port 1", "", "AC-1304",
             "OpenWrt", "SER001"]]
    records = [{"serial_number": "SER001",
                "name": "puck12",
                "upstream": "sw-netgear-gsm7252ps-s1 port 1/0/46"}]
    updates, conflicts, _ = compute_updates(
        records, RENAMED_HEADER, rows, allow_overwrite=LIVE_OVERWRITE_FIELDS)
    up_col = RENAMED_HEADER.index("Upstream")
    name_col = RENAMED_HEADER.index("Name")
    assert any(u.col == up_col for u in updates)
    assert any(c.col == name_col for c in conflicts)
    assert not any(u.col == name_col for u in updates)
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sheetmap.py -q`
Expected: ImportError (`LIVE_OVERWRITE_FIELDS`, `RENAME_HEADERS`, `compute_header_renames` not defined).

- [ ] **Step 1.3: Implement in `galeflash/sheetmap.py`**

Retarget the two existing entries and add the new fields at the end of `FIELD_TO_HEADER` (order = new-column append order):

```python
    "ethernet_mac0":       "wan",         # renamed from stale 'eth0' header
    "ethernet_mac1":       "lan",         # renamed from stale 'eth1' header
```

and after `"image_sha256": "Image SHA256",`:

```python
    # --- live-collected data (collect_puck_live.py) ---
    "name":                "Name",         # puck hostname, existing col B
    "upstream":            "Upstream",     # LLDP switch+port, existing col D
    "wifi_wl_main_2g4":    "wl-main-2g4",  # renamed from stale 'wlan0'
    "wifi_wl_main_5g":     "wl-main-5g",   # renamed from stale 'wlan1'
    "wifi_wl_guest_2g4":   "wl-guest-2g4",
    "wifi_wl_guest_5g":    "wl-guest-5g",
    "wifi_wl_iot_2g4":     "wl-iot-2g4",
    "wifi_mesh_2g4":       "mesh-2g4",
    "wifi_mesh_5g":        "mesh-5g",
```

Delete the superseded comment block ("Note: the generic user-label "MAC" column (E)… absent from FIELD_TO_HEADER.") and replace with:

```python
# Note: the generic user-label "MAC" column is left untouched — it holds the
# operator's chosen MAC, not an inventory field.  The CPU-side eth0 netdev MAC
# is randomized every boot (observed 2026-07-22) and is deliberately not
# recorded.  Column positions are matched by header NAME, never by letter.
```

Add after `FLASH_AUDIT_FIELDS`:

```python
# Live-collected fields that legitimately change over time.  'upstream'
# changes when a puck is recabled; --update-live unlocks overwriting it.
# 'name' and all MAC fields stay identity-guarded.
LIVE_OVERWRITE_FIELDS: frozenset[str] = frozenset({"upstream"})

# Stale sheet headers → real gale interface names.  Applied by
# compute_header_renames(); matching is case-insensitive and renames only a
# cell whose current value still equals the old name.
RENAME_HEADERS: dict[str, str] = {
    "eth0":  "wan",
    "eth1":  "lan",
    "wlan0": "wl-main-2g4",
    "wlan1": "wl-main-5g",
}
```

Add the pure function (near `get_extended_header`):

```python
def compute_header_renames(
    header: list[str],
) -> tuple[list[tuple[int, str, str]], list[str]]:
    """Compute header-cell renames per RENAME_HEADERS.

    Three-way outcome per (old, new) entry, matched case-insensitively:
      - old present, new absent  → rename entry ``(col_idx, old, new)``
      - new present, old absent  → no-op (already renamed)
      - both present             → conflict (rename would duplicate a header)
      - neither present          → conflict (the sheet changed under us)

    Returns (renames, conflicts); conflicts are human-readable strings and the
    caller must refuse to write while any exist.  Data cells are never touched.
    """
    lower_to_idx = {h.lower(): i for i, h in enumerate(header)}
    renames: list[tuple[int, str, str]] = []
    conflicts: list[str] = []
    for old, new in RENAME_HEADERS.items():
        old_idx = lower_to_idx.get(old.lower())
        new_idx = lower_to_idx.get(new.lower())
        if old_idx is not None and new_idx is not None:
            conflicts.append(
                f"header has BOTH {old!r} (col {old_idx}) and {new!r} "
                f"(col {new_idx}) — rename would duplicate"
            )
        elif old_idx is not None:
            renames.append((old_idx, header[old_idx], new))
        elif new_idx is None:
            conflicts.append(
                f"header has neither {old!r} nor {new!r} — sheet layout changed"
            )
    return renames, conflicts
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sheetmap.py -q`
Expected: all pass (existing 85-suite members included; note
`test_get_extended_header_adds_new_columns` asserts `extended.count("eth0") == 1`
against the OLD synthetic header — it still passes because that header contains
`eth0` and the retargeted map now appends a NEW `wan` column for it; verify the
assertion still holds, and update that test's comment if misleading).

- [ ] **Step 1.5: Run the full fleet suite**

Run: `uv run pytest tests/ -q`
Expected: no regressions (>= 85 + new tests, 0 failures).

- [ ] **Step 1.6: Commit**

```bash
git add galeflash/sheetmap.py tests/test_sheetmap.py
git commit -m "sheetmap: header renames, live fields, retarget MAC columns"
```

---

### Task 2: sync_sheet — range fix, rename batch, wifi flatten, --update-live

**Files:**
- Modify: `tools/fleet/sync_sheet.py`

No unit-test file covers `sync_sheet.py` (I/O layer, tested live via dry-run);
keep every change thin — logic stays in sheetmap.

- [ ] **Step 2.1: Fix the truncating read range**

Replace the comment + read at `sync_sheet.py:290-294`:

```python
    # Initial read: A1:ZZ1000 (702 columns) — far past any plausible schema
    # width, and a values GET safely returns only what exists.  The sheet is
    # 28 columns today; the old A1:Z1000 range silently truncated AA/AB.
    all_rows = _sheets_get(token, f"'{title}'!A1:ZZ1000")
```

and the read-back at `sync_sheet.py:418`:

```python
    last_col = _col_letter(len(extended_header) - 1)
    back = _sheets_get(token, f"'{title}'!A1:{last_col}1000")
```

- [ ] **Step 2.2: Apply header renames**

After `header`/`rows` are split (line ~301), insert:

```python
    # --- Header renames (stale eth0/eth1/wlan0/wlan1 → real interfaces) -----
    renames, rename_conflicts = compute_header_renames(header)
    if rename_conflicts:
        print(f"\nHEADER CONFLICTS ({len(rename_conflicts)}):", file=sys.stderr)
        for c in rename_conflicts:
            print(f"  {c}", file=sys.stderr)
        sys.exit(2)
    for col_idx, old, new in renames:
        print(f"Header rename: {_a1_header(title, col_idx)} {old!r} -> {new!r}")
        header[col_idx] = new  # rename in-memory BEFORE computing updates
```

(import `compute_header_renames` in the existing `from galeflash.sheetmap import (…)` block.)

- [ ] **Step 2.3: Rename batch survives the nothing-to-write exit**

Change the early-exits (line ~379-386) to account for renames:

```python
    if not args.write:
        print(f"\nDry run complete ({len(updates)} update(s), "
              f"{len(renames)} header rename(s) pending). "
              f"Re-run with --write to apply.")
        return

    if not updates and not renames:
        print("\nNothing to write — sheet is already up to date.")
        return
```

and add the rename cells to the batch (before new-column headers):

```python
    batch: list[dict] = []

    # Header renames first (guarded upstream by compute_header_renames)
    for col_idx, _old, new in renames:
        batch.append({
            "range":  _a1_header(title, col_idx),
            "values": [[new]],
        })
```

- [ ] **Step 2.4: Flatten wifi_macs in record prep + --update-live**

Extend `prepare_records` to flatten the collector's `wifi_macs` dict:

```python
def prepare_records(records: list[dict]) -> list[dict]:
    """Format MACs and flatten collector fields for sheet presentation.

    - ``ethernet_mac0``/``ethernet_mac1`` are colon-formatted (uppercase).
    - ``wifi_macs`` ({iface: mac}) is flattened to ``wifi_<iface>`` fields
      (dashes → underscores, e.g. wl-main-2g4 → wifi_wl_main_2g4), values
      colon-formatted, and the dict removed so compute_updates only sees
      scalar fields.
    """
    prepared: list[dict] = []
    for rec in records:
        rec = dict(rec)
        for field in MAC_FIELDS:
            if rec.get(field):
                rec[field] = format_mac(rec[field])
        wifi = rec.pop("wifi_macs", None)
        if wifi:
            for iface, mac in wifi.items():
                rec[f"wifi_{iface.replace('-', '_')}"] = format_mac(mac)
        prepared.append(rec)
    return prepared
```

Add the CLI flag after `--update-flash`:

```python
    parser.add_argument(
        "--update-live",
        action="store_true",
        help="Overwrite differing LIVE cells (Upstream) instead of treating "
             "them as conflicts.  Name and MAC columns stay conflict-guarded.",
    )
```

and combine the allow-sets (replacing the existing `allow =` line):

```python
    allow: frozenset[str] = frozenset()
    if args.update_flash:
        allow |= FLASH_AUDIT_FIELDS
        print("Reflash mode: differing flash-audit cells will be OVERWRITTEN.")
    if args.update_live:
        allow |= LIVE_OVERWRITE_FIELDS
        print("Live mode: differing Upstream cells will be OVERWRITTEN.")
```

(import `LIVE_OVERWRITE_FIELDS` too.)

- [ ] **Step 2.5: Sanity-run the suite + a read-only dry run**

Run: `uv run pytest tests/ -q` — expected: all pass.
Run: `uv run sync_sheet.py` (dry run; needs VPN + SA key) — expected: loads 28
header columns (not 26), reports the 4 pending header renames + pending
updates from existing inventory, exits 0 without writing.

- [ ] **Step 2.6: Commit**

```bash
git add sync_sheet.py
git commit -m "sync_sheet: ZZ read range, guarded header renames, wifi flatten, --update-live"
```

---

### Task 3: collector — pure parsers with fixtures

**Files:**
- Create: `tools/fleet/galeflash/livecollect.py` (pure logic)
- Create: `tools/fleet/tests/test_livecollect.py`
- Create: `tools/fleet/tests/fixtures/` (captured live outputs)

- [ ] **Step 3.1: Capture live fixtures from puck12 + wisp**

```bash
mkdir -p tests/fixtures
ssh -4 root@10.1.4.112 "ip -j link" > tests/fixtures/puck12_ip_link.json
ssh -4 root@10.1.4.112 "iw dev" > tests/fixtures/puck12_iw_dev.txt
ssh -4 root@10.1.4.112 "lldpcli -f json0 show neighbors ports lan" \
    > tests/fixtures/puck12_lldp.json
ssh -4 root@10.1.4.107 "lldpcli -f json0 show neighbors ports lan" \
    > tests/fixtures/puck07_lldp_dumb_switch.json
ssh -4 tim@10.1.4.2 "sudo -n cat /etc/dnsmasq.d/gwifi-generated/pucks.conf" \
    > tests/fixtures/pucks.conf
```

Verify each file is non-empty and well-formed (`jq . tests/fixtures/*.json`,
visual check of the .txt/.conf). Commit fixtures:

```bash
git add tests/fixtures
git commit -m "tests: live fixtures from puck12/puck07/wisp for the collector"
```

- [ ] **Step 3.2: Write the failing parser tests**

`tests/test_livecollect.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.livecollect — pure parsing/merge logic on live fixtures."""
import json
from pathlib import Path

import pytest

from galeflash.livecollect import (
    PuckReg,
    ethernet_macs_from_ip_link,
    parse_iw_dev,
    parse_pucks_conf,
    upstream_from_lldp,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pucks_conf():
    regs = parse_pucks_conf((FIXTURES / "pucks.conf").read_text())
    assert regs["puck12"] == PuckReg(
        name="puck12", wan_mac="44:07:0b:01:a2:21",
        lan_mac="44:07:0b:01:a2:22", ip="10.1.4.112")
    assert len(regs) == 9  # puck04..puck12
    assert set(regs) == {f"puck{n:02d}" for n in range(4, 13)}


def test_parse_iw_dev():
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    assert macs == {
        "mesh-5g":      "44:07:0b:01:a2:24",
        "wl-main-5g":   "42:07:0b:01:a2:24",
        "wl-guest-5g":  "46:07:0b:01:a2:24",
        "wl-iot-2g4":   "42:07:0b:01:a2:28",
        "mesh-2g4":     "4e:07:0b:01:a2:28",
        "wl-guest-2g4": "46:07:0b:01:a2:28",
        "wl-main-2g4":  "44:07:0b:01:a2:28",
    }


def test_ethernet_macs_from_ip_link():
    doc = json.loads((FIXTURES / "puck12_ip_link.json").read_text())
    lan, wan = ethernet_macs_from_ip_link(doc)
    assert lan == "44:07:0b:01:a2:22"
    assert wan == "44:07:0b:01:a2:21"


def test_upstream_from_lldp_managed_switch():
    doc = json.loads((FIXTURES / "puck12_lldp.json").read_text())
    up = upstream_from_lldp(doc)
    assert up == "sw-netgear-gsm7252ps-s1 port 1/0/46"


def test_upstream_from_lldp_dumb_switch_returns_none():
    doc = json.loads((FIXTURES / "puck07_lldp_dumb_switch.json").read_text())
    assert upstream_from_lldp(doc) is None


def test_missing_wifi_interface_detected():
    """A puck missing one of the 7 expected wifi interfaces must fail loud."""
    from galeflash.livecollect import EXPECTED_WIFI_IFACES, check_wifi_complete
    macs = parse_iw_dev((FIXTURES / "puck12_iw_dev.txt").read_text())
    check_wifi_complete("puck12", macs)  # complete — no raise
    incomplete = dict(macs)
    del incomplete["mesh-5g"]
    with pytest.raises(ValueError, match="mesh-5g"):
        check_wifi_complete("puck12", incomplete)
```

- [ ] **Step 3.3: Run to verify failure**

Run: `uv run pytest tests/test_livecollect.py -q`
Expected: ImportError (module doesn't exist).

- [ ] **Step 3.4: Implement `galeflash/livecollect.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Pure parsing + merge logic for the live puck collector.

No I/O here — collect_puck_live.py does ssh/file I/O and calls these.
Fail loud: unexpected shapes raise, nothing is fabricated or skipped.
"""

import re
from typing import NamedTuple

# The 7 wireless interfaces every production gale puck runs (2026-07-22
# image).  A live puck missing one is an error, not a gap to skip.
EXPECTED_WIFI_IFACES: frozenset[str] = frozenset({
    "wl-main-2g4", "wl-main-5g",
    "wl-guest-2g4", "wl-guest-5g",
    "wl-iot-2g4",
    "mesh-2g4", "mesh-5g",
})


class PuckReg(NamedTuple):
    """One row of the wisp dnsmasq puck registry."""
    name:    str
    wan_mac: str
    lan_mac: str
    ip:      str


_DHCP_HOST_RE = re.compile(
    r"^dhcp-host=([0-9a-f:]{17}),([0-9a-f:]{17}),([0-9.]+),(puck\d+)\s*$"
)


def parse_pucks_conf(text: str) -> dict[str, PuckReg]:
    """Parse wisp's gwifi-generated/pucks.conf into {puck_name: PuckReg}.

    Lines are ``dhcp-host=<wan_mac>,<lan_mac>,<ip>,<puckNN>``.  Any
    non-comment, non-blank line that isn't a well-formed dhcp-host line
    raises — the registry is machine-generated, drift means trouble.
    """
    regs: dict[str, PuckReg] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _DHCP_HOST_RE.match(line)
        if not m:
            raise ValueError(f"unparseable pucks.conf line: {line!r}")
        wan_mac, lan_mac, ip, name = m.groups()
        if name in regs:
            raise ValueError(f"duplicate registry entry for {name}")
        regs[name] = PuckReg(name=name, wan_mac=wan_mac,
                             lan_mac=lan_mac, ip=ip)
    if not regs:
        raise ValueError("pucks.conf contained no dhcp-host entries")
    return regs


def parse_iw_dev(text: str) -> dict[str, str]:
    """Parse ``iw dev`` output into {interface_name: mac}.

    Only Interface/addr pairs are extracted; an addr with no preceding
    Interface raises.
    """
    macs: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Interface "):
            current = line.split(None, 1)[1]
        elif line.startswith("addr "):
            if current is None:
                raise ValueError(f"addr line with no Interface: {line!r}")
            macs[current] = line.split(None, 1)[1]
            current = None
    if not macs:
        raise ValueError("iw dev output contained no interfaces")
    return macs


def check_wifi_complete(puck: str, macs: dict[str, str]) -> None:
    """Raise if any expected wireless interface is missing."""
    missing = EXPECTED_WIFI_IFACES - set(macs)
    if missing:
        raise ValueError(
            f"{puck}: missing wifi interface(s): {', '.join(sorted(missing))}"
        )
    unexpected = set(macs) - EXPECTED_WIFI_IFACES
    if unexpected:
        raise ValueError(
            f"{puck}: unexpected wifi interface(s): {', '.join(sorted(unexpected))}"
        )


def ethernet_macs_from_ip_link(doc: list[dict]) -> tuple[str, str]:
    """Return (lan_mac, wan_mac) from an ``ip -j link`` document."""
    by_name = {i["ifname"]: i for i in doc}
    try:
        return by_name["lan"]["address"], by_name["wan"]["address"]
    except KeyError as exc:
        raise ValueError(f"ip -j link missing interface: {exc}") from exc


def upstream_from_lldp(doc: dict) -> str | None:
    """Extract 'shortname port <id>' from lldpcli -f json0 output.

    A neighbor qualifies as the upstream switch iff its port id type is
    ``local`` (managed-switch behaviour) AND it advertises a chassis name.
    Returns None when no neighbor qualifies (puck behind an unmanaged
    switch); raises if MORE than one qualifies (ambiguous topology).
    """
    interfaces = doc.get("lldp", [{}])[0].get("interface", [])
    candidates: list[str] = []
    for iface in interfaces:
        for chassis in iface.get("chassis", []):
            names = [n.get("value") for n in chassis.get("name", [])
                     if n.get("value")]
            if not names:
                continue
            for port in iface.get("port", []):
                for pid in port.get("id", []):
                    if pid.get("type") == "local" and pid.get("value"):
                        short = names[0].split(".")[0]
                        candidates.append(f"{short} port {pid['value']}")
    if len(candidates) > 1:
        raise ValueError(f"multiple upstream switch candidates: {candidates}")
    return candidates[0] if candidates else None
```

NOTE: the exact json0 nesting must be validated against the captured fixture
in Step 3.1 — adjust `upstream_from_lldp` field access to the real structure
(keep the local-port-type + chassis-name rule), and keep the tests green.

- [ ] **Step 3.5: Run tests to verify they pass**

Run: `uv run pytest tests/test_livecollect.py -q`
Expected: all pass. If the lldp fixture structure differs from the sketch,
fix the implementation (never the assertion values — those came from the
live probes).

- [ ] **Step 3.6: Commit**

```bash
git add galeflash/livecollect.py tests/test_livecollect.py
git commit -m "livecollect: pure parsers for registry, iw, ip-link, lldp"
```

---

### Task 4: collector — merge + CLI

**Files:**
- Create: `tools/fleet/collect_puck_live.py`
- Modify: `tools/fleet/tests/test_livecollect.py` (merge tests)

- [ ] **Step 4.1: Write the failing merge tests**

Append to `tests/test_livecollect.py`:

```python
from galeflash.livecollect import merge_live_fields


def test_merge_live_fields_preserves_flash_data(tmp_path):
    inv = tmp_path / "SER001.json"
    inv.write_text(json.dumps({"serial_number": "SER001",
                               "flash_status": "ok",
                               "rw_fwid": "Google_Gale.8743.85.14"}))
    merge_live_fields(tmp_path, "SER001",
                      name="puck12",
                      upstream="sw-netgear-gsm7252ps-s1 port 1/0/46",
                      wifi_macs={"mesh-5g": "44:07:0b:01:a2:24"})
    data = json.loads(inv.read_text())
    assert data["flash_status"] == "ok"          # untouched
    assert data["rw_fwid"] == "Google_Gale.8743.85.14"
    assert data["name"] == "puck12"
    assert data["wifi_macs"]["mesh-5g"] == "44:07:0b:01:a2:24"


def test_merge_live_fields_creates_minimal_record(tmp_path):
    merge_live_fields(tmp_path, "SERNEW", name="puck11",
                      upstream=None, wifi_macs={"mesh-5g": "aa:bb:cc:dd:ee:ff"})
    data = json.loads((tmp_path / "SERNEW.json").read_text())
    assert data["serial_number"] == "SERNEW"
    assert data["name"] == "puck11"
    assert "upstream" not in data                # None → field absent


def test_merge_live_fields_none_upstream_does_not_erase(tmp_path):
    """A puck moved behind a dumb switch must not lose its recorded upstream."""
    inv = tmp_path / "SER001.json"
    inv.write_text(json.dumps({"serial_number": "SER001",
                               "upstream": "sw-old port 3"}))
    merge_live_fields(tmp_path, "SER001", name="puck07",
                      upstream=None, wifi_macs={})
    data = json.loads(inv.read_text())
    assert data["upstream"] == "sw-old port 3"
```

- [ ] **Step 4.2: Run to verify failure**

Run: `uv run pytest tests/test_livecollect.py -q`
Expected: ImportError on `merge_live_fields`.

- [ ] **Step 4.3: Implement `merge_live_fields` in `livecollect.py`**

```python
import json
from pathlib import Path


def merge_live_fields(
    inventory_dir: Path,
    serial: str,
    *,
    name: str,
    upstream: str | None,
    wifi_macs: dict[str, str],
) -> Path:
    """Merge live-collected fields into inventory/<serial>.json.

    Creates a minimal record for never-flashed pucks.  Flash fields are never
    touched.  ``upstream=None`` (no managed switch visible) leaves any
    existing recorded upstream in place — absence of LLDP is not evidence of
    recabling.  Returns the path written.
    """
    path = Path(inventory_dir) / f"{serial}.json"
    if path.exists():
        data = json.loads(path.read_text())
        if data.get("serial_number") != serial:
            raise ValueError(
                f"{path}: serial_number {data.get('serial_number')!r} "
                f"!= filename serial {serial!r}"
            )
    else:
        data = {"serial_number": serial}
    data["name"] = name
    if upstream is not None:
        data["upstream"] = upstream
    if wifi_macs:
        data["wifi_macs"] = dict(sorted(wifi_macs.items()))
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path
```

- [ ] **Step 4.4: Run tests, expect pass; commit**

```bash
uv run pytest tests/test_livecollect.py -q
git add galeflash/livecollect.py tests/test_livecollect.py
git commit -m "livecollect: merge_live_fields — non-destructive inventory merge"
```

- [ ] **Step 4.5: Implement the CLI `collect_puck_live.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Collect live data from gale pucks into the fleet inventory.

Per reachable puck (registry: wisp's dnsmasq gwifi-generated/pucks.conf):
serial (VPD sysfs), hostname, lan/wan MACs, the 7 wifi BSSIDs, and the LLDP
upstream switch+port.  Merges into inventory/<serial>.json for sync_sheet.py.

Usage:
    uv run collect_puck_live.py                 # whole registry
    uv run collect_puck_live.py --puck 12       # just puck12
    uv run collect_puck_live.py --inventory DIR # override inventory dir
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from galeflash.livecollect import (
    check_wifi_complete,
    ethernet_macs_from_ip_link,
    merge_live_fields,
    parse_iw_dev,
    parse_pucks_conf,
    upstream_from_lldp,
)

DEFAULT_INVENTORY = Path("/home/tim/local/gwifi/fleet-flash/inventory")
REGISTRY_HOST = "tim@10.1.4.2"  # wisp.welland.mithis.com
REGISTRY_PATH = "/etc/dnsmasq.d/gwifi-generated/pucks.conf"

SSH_OPTS = ["-4", "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new"]

# One ssh round-trip per puck: emit every section with markers.  The pucks
# are cross-site (~250 ms RTT) — batching matters.
_MARKER = "@@SECTION@@"
_PUCK_SCRIPT = (
    f"echo {_MARKER}serial;   cat /sys/firmware/vpd/ro/serial_number; echo;"
    f"echo {_MARKER}hostname; uname -n;"
    f"echo {_MARKER}iplink;   ip -j link;"
    f"echo {_MARKER}iwdev;    iw dev;"
    f"echo {_MARKER}lldp;     lldpcli -f json0 show neighbors ports lan"
)


def ssh(host: str, command: str, timeout: int = 30) -> str:
    """Run a command over ssh; raise (with stderr shown) on failure."""
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, command],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)   # never suppress stderr
    if result.returncode != 0:
        raise RuntimeError(f"ssh {host} failed (rc={result.returncode})")
    return result.stdout


def split_sections(raw: str) -> dict[str, str]:
    """Split marker-delimited ssh output into {section_name: content}."""
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith(_MARKER):
            if current is not None:
                sections[current] = "\n".join(lines)
            current = line[len(_MARKER):].strip()
            lines = []
        else:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines)
    expected = {"serial", "hostname", "iplink", "iwdev", "lldp"}
    missing = expected - set(sections)
    if missing:
        raise ValueError(f"ssh output missing section(s): {sorted(missing)}")
    return sections


def collect_one(reg, inventory_dir: Path) -> str:
    """Collect one puck; returns the serial.  Raises on any inconsistency."""
    raw = ssh(f"root@{reg.ip}", _PUCK_SCRIPT)
    s = split_sections(raw)

    serial = s["serial"].strip()
    hostname = s["hostname"].strip()
    if not serial:
        raise ValueError(f"{reg.name}: empty VPD serial_number")
    if hostname != reg.name:
        raise ValueError(
            f"{reg.name}: device hostname {hostname!r} != registry name")

    lan_mac, wan_mac = ethernet_macs_from_ip_link(json.loads(s["iplink"]))
    if (lan_mac.lower(), wan_mac.lower()) != (reg.lan_mac, reg.wan_mac):
        raise ValueError(
            f"{reg.name}: live MACs lan={lan_mac} wan={wan_mac} do not match "
            f"registry lan={reg.lan_mac} wan={reg.wan_mac} — identity mismatch")

    wifi_macs = parse_iw_dev(s["iwdev"])
    check_wifi_complete(reg.name, wifi_macs)

    upstream = upstream_from_lldp(json.loads(s["lldp"]))
    if upstream is None:
        print(f"  {reg.name}: no managed switch visible via LLDP "
              f"(unmanaged upstream) — Upstream not recorded")

    path = merge_live_fields(inventory_dir, serial, name=hostname,
                             upstream=upstream, wifi_macs=wifi_macs)
    print(f"  {reg.name}: serial={serial} upstream={upstream!r} -> {path}")
    return serial


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect live puck data into the fleet inventory.")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY,
                        metavar="DIR")
    parser.add_argument("--puck", action="append", type=int, metavar="NN",
                        help="Collect only puckNN (repeatable).")
    args = parser.parse_args()

    print(f"Fetching registry from {REGISTRY_HOST}:{REGISTRY_PATH}")
    regs = parse_pucks_conf(ssh(REGISTRY_HOST, f"sudo -n cat {REGISTRY_PATH}"))
    if args.puck:
        wanted = {f"puck{n:02d}" for n in args.puck}
        unknown = wanted - set(regs)
        if unknown:
            sys.exit(f"ERROR: not in registry: {', '.join(sorted(unknown))}")
        regs = {k: v for k, v in regs.items() if k in wanted}
    print(f"Registry: {len(regs)} puck(s): {', '.join(sorted(regs))}")

    collected: list[str] = []
    unreachable: list[str] = []
    for name in sorted(regs):
        reg = regs[name]
        print(f"Collecting {name} ({reg.ip}) …", flush=True)
        try:
            collected.append(collect_one(reg, args.inventory))
        except (subprocess.TimeoutExpired, RuntimeError) as exc:
            # ssh-level failure = puck offline; report loudly, keep going.
            print(f"  {name}: UNREACHABLE ({exc})", file=sys.stderr)
            unreachable.append(name)
        # ValueError (bad/incomplete data from a REACHABLE puck) propagates:
        # that is a hard failure, not a gap to skip.

    print(f"\nCollected {len(collected)} puck(s): {', '.join(collected)}")
    if unreachable:
        print(f"UNREACHABLE ({len(unreachable)}): {', '.join(unreachable)}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4.6: Smoke-test the CLI against one puck**

Run: `uv run collect_puck_live.py --puck 12 --inventory /tmp-NO --help` first
(arg parsing), then for real:
`uv run collect_puck_live.py --puck 12`
Expected: puck12 collected, `2831HW00WGD.json` gains `name`, `upstream`,
`wifi_macs` (verify with `jq . /home/tim/local/gwifi/fleet-flash/inventory/2831HW00WGD.json`);
flash fields untouched (compare with `git -C … diff` no — inventory is not in
git; instead re-run `uv run sync_sheet.py` dry-run later).

- [ ] **Step 4.7: Commit**

```bash
git add collect_puck_live.py
git commit -m "collect_puck_live: ssh collector — registry, identity gate, one round-trip"
```

---

### Task 5: live rollout

**Files:** none (operational)

- [ ] **Step 5.1: Full-suite green**

Run: `uv run pytest tests/ -q` — 0 failures.

- [ ] **Step 5.2: Collect the whole fleet**

Run: `uv run collect_puck_live.py`
Expected: puck06/07/11/12 collected (puck07 reports no-managed-switch),
puck04/05/08/09/10 listed UNREACHABLE. Two NEW inventory files appear for
puck06/puck11 serials.

- [ ] **Step 5.3: Dry-run the sheet sync and review**

Run: `uv run sync_sheet.py`
Review: 4 header renames pending; Name/Upstream/wifi updates for the 4 live
pucks; NO conflicts expected (Name/Upstream cells are empty today except
row 7's manual Upstream, and puck07 collects upstream=None so that cell
isn't written). Any conflict → stop, investigate, resolve with the operator.

- [ ] **Step 5.4: Write + verify**

Run: `uv run sync_sheet.py --write`
Expected: renames + header cells + data cells written; read-back shows the
4 rows with new values; re-run `uv run sync_sheet.py` reports
"Nothing to write" (idempotent), proving renames + data landed.

- [ ] **Step 5.5: Commit any final tweaks; update task list + memory**

Mark session tasks 2+3 completed; update the two OPEN-TASK memory files
(gwifi-sheet-lldp-upstream, gwifi-sheet-ap-mac-columns) to DONE-with-date,
and fold the outcome into MEMORY.md.

---

### Task 6: branch finish

- [ ] Use superpowers:finishing-a-development-branch — present merge/PR options
  for `puck-sheet-live-sync` (5 commits + spec/plan docs).
