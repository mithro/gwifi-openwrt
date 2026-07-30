<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fleet SPI-firmware flash — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the proven one-puck `tmp/` prototypes into a tested `tools/fleet/`
toolkit + runbook that flashes the stock `gale` fleet's SPI with a dev-key-re-keyed,
TFTP-first/eMMC-fallback depthcharge — firmware only, eMMC untouched.

**Architecture:** Two phases. **Phase 0 (offline, TDD)** builds + unit-tests every
script against on-disk SPI dumps with NO hardware — the build/verify/diff pipeline is
proven against fixtures before any puck is touched. **Phase 1/2 (hardware)** runs the
pilot then the fleet using those tools, with observable serial-console exit criteria.

**Tech stack:** Python 3 + `uv` (inline-dep scripts, matching `gwifi-openwrt/tools/`);
`futility` + `cbfstool` (built in `depthcharge-ipq4019/`); the EC-raiden SuzyQ bridge
tools (`chunk_read.py`, `raiden_write_region.py`, `raiden_sr.py`, `ec_console.py`);
`pytest` via `uv run pytest`. Sheet sync via `gcloud` service account.

**Spec:** [`gale-fleet-firmware-flash-design.md`](gale-fleet-firmware-flash-design.md).
Read it first — this plan assumes its region table, signing model, and decisions.

---

## Conventions for the implementer

- **`uv` only.** Run scripts with `uv run <script>.py`; tests with `uv run pytest`.
  Never bare `python`/`pip`. Scripts carry a `# /// script` inline-deps header.
- **No `/tmp`.** Use a project-local `tmp/` and clean up.
- **Never `2>/dev/null`.** Keep stderr visible.
- **Commit after every green step.** Small commits.
- All paths below are absolute or relative to the repo root
  `/home/tim/local/gwifi/gwifi-openwrt/` unless noted. The umbrella dir is
  `/home/tim/local/gwifi/` (holds `depthcharge-ipq4019/`, the fixtures, and `tmp/`).

## Reference constants (verified — §4 of the spec)

```python
# tools/fleet/galeflash/const.py
from pathlib import Path
UMBRELLA = Path("/home/tim/local/gwifi")
DC       = UMBRELLA / "depthcharge-ipq4019"
FUTILITY = DC / "vboot_reference/build/futility/futility"
CBFSTOOL = DC / "coreboot/util/cbfstool/cbfstool"
DEVKEYS  = DC / "vboot_reference/tests/devkeys"
PAYLOAD_ELF = DC / "depthcharge/build/depthcharge.elf"   # TFTP-first standard payload

# FMAP regions (offset, size) — confirmed via fmap_dump.py on a real dump
FMAP = {
    "GBB":          (0x301000, 0x0DEF00),
    "RO_FRID":      (0x3DFF00, 0x000100),
    "RO_VPD":       (0x3E0000, 0x020000),
    "VBLOCK_A":     (0x400000, 0x002000),
    "FW_MAIN_A":    (0x402000, 0x14DF00),
    "RW_SECTION_A": (0x400000, 0x160000),
    "VBLOCK_B":     (0x580000, 0x002000),
    "FW_MAIN_B":    (0x582000, 0x14DF00),
    "RW_SECTION_B": (0x580000, 0x160000),
    "RW_VPD":       (0x6E0000, 0x008000),
}
GBB_ROFRID_SPAN = (0x301000, 0x0DF000)   # GBB + RO_FRID, stops exactly at RO_VPD

# RW_SECTION_A/B are COMPOSITES enclosing their VBLOCK_*+FW_MAIN_* leaves; the
# offline diff-gate compares LEAVES only (composites would double-report them).
COMPOSITE_REGIONS = {"RW_SECTION_A", "RW_SECTION_B"}
LEAF_FMAP = {k: v for k, v in FMAP.items() if k not in COMPOSITE_REGIONS}
# regions the build is permitted to change (the gate asserts: changed <= this).
# RO_FRID is allowed-but-unchanged-by-build (the flash step rewrites it identical).
ALLOWED_CHANGED = {"GBB", "RO_FRID", "FW_MAIN_A", "VBLOCK_A", "FW_MAIN_B", "VBLOCK_B"}
```

## On-disk test fixtures (NOT in git — skip tests if absent)

| Path | What it is | Use |
|---|---|---|
| `/home/tim/local/gwifi/gale-spi-stock-2026-05-28.bin` | **puck G4** stock dump (serial `2831HW00VZA`, eth0 `44:07:0B:01:87:B4`) | parser + build input fixture |
| `/home/tim/local/gwifi/tmp/gale-live-2026-06-08-pre-devkey.bin` | bring-up unit pre-rekey live dump | second build input fixture |
| `/home/tim/local/gwifi/tmp/gale-devkey-bringup.bin` | prototype dev-key output | diff/verify oracle |
| `/home/tim/local/gwifi/tmp/gale-depthcharge-tftpfirst.bin` | prototype tftp-first output | diff/verify oracle |

## File structure (`tools/fleet/`)

```
tools/fleet/
  galeflash/
    __init__.py
    const.py            # paths + FMAP table above
    vpd.py              # Google VPD 2.0 TLV decoder (pure)
    fmapdiff.py         # per-region diff between two 8 MiB images (port of tmp/diff_regions.py)
    cbfs.py             # extend FW_MAIN_A CBFS empty trailer (port of tmp/extend_cbfs_empty.py)
    identity.py         # dump -> identity dict (vpd + HWID + RO_FRID)
    imagebuild.py       # the combined re-key + payload + mirror + dual-sign build
    serialguard.py      # read live RO_VPD over bridge -> serial (for the flash guard)
    flashplan.py        # pure: region write-order (RO-last) for the flasher
    orchestrator.py     # pure: per-puck step plan (backup/extract/build/flash names)
  extract_identity.py   # CLI: dump -> inventory/<serial>.json
  build_gale_fleet_image.py  # CLI: <live.bin> <out.bin>
  flash_gale_fleet.py   # CLI: <out.bin> <expected-serial>  (RO-last, serial-guarded)
  flash_one_puck.py     # CLI orchestrator: backup -> extract -> build -> flash -> verify
  sync_sheet.py         # CLI: push inventory/*.json to the sheet (gcloud SA auth)
  tests/
    conftest.py         # fixture-path discovery + skip-if-missing
    test_vpd.py
    test_fmapdiff.py
    test_identity.py
    test_imagebuild.py
    test_serialguard.py
    test_flash_order.py
  README.md
```

Backups + `inventory/` live **outside git** at `/home/tim/local/gwifi/fleet-flash/{backups,inventory}/`.

---

## Phase 0 — Offline tooling (TDD, no hardware)

### Task 1: Scaffold the package + test harness

**Files:**
- Create: `tools/fleet/galeflash/__init__.py`, `tools/fleet/galeflash/const.py`
- Create: `tools/fleet/tests/conftest.py`
- Create: `tools/fleet/README.md`

- [ ] **Step 1: Write `const.py`** with the Reference-constants block above.

- [ ] **Step 2: Write `conftest.py`** that discovers fixtures and skips when missing:

```python
import os, pytest
from pathlib import Path
UMBRELLA = Path("/home/tim/local/gwifi")
def _fx(p): 
    p = UMBRELLA / p
    return p if p.exists() else None
@pytest.fixture
def stock_g4():
    p = _fx("gale-spi-stock-2026-05-28.bin")
    if not p: pytest.skip("G4 stock fixture absent")
    return p.read_bytes()
@pytest.fixture
def devkey_proto():
    p = _fx("tmp/gale-devkey-bringup.bin")
    if not p: pytest.skip("devkey prototype fixture absent")
    return p.read_bytes()
@pytest.fixture
def prerekey_live():
    p = _fx("tmp/gale-live-2026-06-08-pre-devkey.bin")
    if not p: pytest.skip("pre-devkey live fixture absent")
    return p.read_bytes()
@pytest.fixture
def tftpfirst_proto():
    p = _fx("tmp/gale-depthcharge-tftpfirst.bin")
    if not p: pytest.skip("tftp-first prototype fixture absent")
    return p.read_bytes()
```

- [ ] **Step 3: Add a trivial import test** `tests/test_smoke.py`:

```python
def test_const_imports():
    from galeflash import const
    assert const.FMAP["FW_MAIN_A"] == (0x402000, 0x14DF00)
```

- [ ] **Step 4: Run** `cd tools/fleet && uv run pytest -q` → 1 passed.
- [ ] **Step 5: Commit** `feat(fleet): scaffold galeflash package + test harness`.

---

### Task 2: Google VPD 2.0 decoder (`vpd.py`)

The VPD blob (RO_VPD/RW_VPD) is a Google VPD 2.0 container: after the
`gVpdInfo`/`Google VPD 2.0` header, entries are TLV — type byte (`0x01` =
string pair, `0x00` = terminator, `0xff` = padding/end), then a length-prefixed
key and length-prefixed value. Lengths use the VPD "pad-len" varint (7 bits per
byte, high bit = continue). Decode the whole region, returning `{key: value}`.

**Files:** Create `galeflash/vpd.py`, `tests/test_vpd.py`.

- [ ] **Step 1: Failing test** — parse RO_VPD out of the G4 stock image:

```python
from galeflash import vpd, const
def test_vpd_decodes_g4_identity(stock_g4):
    off, size = const.FMAP["RO_VPD"]
    kv = vpd.decode(stock_g4[off:off+size])
    assert kv["serial_number"] == "2831HW00VZA"
    assert kv["ethernet_mac0"] == "44070B0187B4"
    assert kv["ethernet_mac1"] == "44070B0187B5"
    assert kv["mlb_serial_number"] == "NJOKI350392FX01"
    assert kv["model_name"] == "AC1304"
    assert "region" in kv
```

- [ ] **Step 2: Run → FAIL** (`uv run pytest tests/test_vpd.py -q`), no `decode`.

- [ ] **Step 3: Implement `vpd.decode`.** Locate the `Google VPD 2.0` container,
  then walk TLV entries from the start of the gVpdInfo payload:

```python
def _pad_len(buf, i):
    # VPD pad-len varint: 7 bits/byte, MSB=more
    v = 0
    while True:
        b = buf[i]; i += 1
        v = (v << 7) | (b & 0x7f)
        if not (b & 0x80): return v, i
def decode(region: bytes) -> dict:
    # find the VPD 2.0 info block; entries follow the fixed google_vpd_info header
    start = region.find(b"gVpdInfo")
    if start < 0:
        return {}                      # erased/empty region (e.g. blank RW_VPD)
    i = start + 16                     # skip header (magic[8]+size[4]+reserved[4]);
                                       # adjust if the G4 oracle misaligns
    out = {}
    while i < len(region):
        t = region[i]; i += 1
        if t in (0x00, 0xff): break          # terminator / end
        if t != 0x01: break                  # unknown type -> stop
        klen, i = _pad_len(region, i); key = region[i:i+klen].decode(); i += klen
        vlen, i = _pad_len(region, i); val = region[i:i+vlen].decode(errors="replace"); i += vlen
        out[key] = val
    return out
```
> If the offset math needs tuning, iterate against the G4 fixture until the test
> passes — the fixture's expected values are authoritative. Keep the parser pure
> (bytes in, dict out) so it's trivially testable.

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5:** Add a second test parsing `RW_VPD` — asserts `decode` returns a
  dict (possibly `{}` if the region is erased) and never raises. The magic-absent
  guard in Step 3 handles the erased case. Run → PASS.
- [ ] **Step 6: Commit** `feat(fleet): Google VPD 2.0 decoder`.

---

### Task 3: Identity extraction (`identity.py` + `extract_identity.py`)

**Files:** Create `galeflash/identity.py`, `tools/fleet/extract_identity.py`, `tests/test_identity.py`.

- [ ] **Step 1: Failing test** — full identity dict from the G4 dump:

```python
from galeflash import identity, const
def test_identity_from_g4(stock_g4, tmp_path):
    dump = tmp_path/"g4.bin"; dump.write_bytes(stock_g4)
    idv = identity.from_dump(dump)
    assert idv["serial_number"] == "2831HW00VZA"
    assert idv["ethernet_mac0"] == "44070B0187B4"
    assert idv["ro_frid"].startswith("google_gale")    # RO_FRID region string
    assert idv["hwid"]                                  # non-empty (futility gbb)
    assert idv["is_stock"] is True                      # GBB still Google rootkey
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `identity.from_dump(path)`:**
  - VPD: `vpd.decode(buf[RO_VPD])` merged with `vpd.decode(buf[RW_VPD])`.
  - `ro_frid`: `buf[0x3DFF00:0x3DFF00+0x100].split(b"\x00")[0].decode()`.
  - `hwid`: `futility gbb_utility --get --hwid <path>` (parse `hardware_id: X`).
  - `is_stock`: `futility show <path>` → Root Key sha1sum == the **Google**
    rootkey (stock) vs the dev rootkey (`futility show DEVKEYS/root_key.vbpubk`).
    Return `True` when it's NOT the dev key.
  - Select/rename the fields we map to the sheet (§8 of spec): `serial_number`,
    `mlb_serial_number`, `region`, `ethernet_mac0`, `ethernet_mac1`,
    `model_name`, `hwid`, `ro_frid`, `is_stock`.
  - VPD stores MACs as **bare hex** (`44070B0187B4`), matching the Task 2 test;
    colon-format (`44:07:0B:01:87:B4`) only when writing to the sheet, not in the
    raw identity dict.

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Write the CLI** `extract_identity.py <dump> [--out DIR]` →
  writes `fleet-flash/inventory/<serial>.json` (default DIR
  `/home/tim/local/gwifi/fleet-flash/inventory`). Print the dict.

- [ ] **Step 6:** Test the CLI writes a well-formed JSON keyed by serial (run on
  fixture into `tmp_path`). Run → PASS.
- [ ] **Step 7: Commit** `feat(fleet): dump -> identity extraction + inventory json`.

---

### Task 4: Region diff + CBFS extend (ports)

**Files:** Create `galeflash/fmapdiff.py`, `galeflash/cbfs.py`, `tests/test_fmapdiff.py`.
Source: port `tmp/diff_regions.py` and `tmp/extend_cbfs_empty.py` (read them first).

- [ ] **Step 1: Failing test** — diff stock G4 vs the devkey prototype shows only
  the expected regions changed:

```python
from galeflash import fmapdiff, const
def test_diff_detects_only_mutated_leaf(stock_g4):
    # Hermetic: mutate ONE byte inside FW_MAIN_A; the diff must report that leaf
    # and NOT its enclosing composite RW_SECTION_A, nor untouched regions.
    a = stock_g4
    b = bytearray(a); off, _ = const.FMAP["FW_MAIN_A"]; b[off] ^= 0xFF
    changed = fmapdiff.changed_regions(bytes(a), bytes(b))
    assert "FW_MAIN_A" in changed
    assert "RW_SECTION_A" not in changed          # composite excluded (the fix)
    assert "RO_VPD" not in changed and "GBB" not in changed
```
> Don't diff G4-stock against `devkey_proto` — that's a *different* puck (the
> bring-up unit), so their RO_VPD differs by identity and would falsely flag
> RO_VPD. Same-puck before/after is exercised in Task 5 (build from a dump, diff
> against that same dump).

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `fmapdiff.changed_regions(a, b)` → for each
  `const.LEAF_FMAP` region (composites `RW_SECTION_A/B` **excluded** so they don't
  double-report their enclosed leaves), compare byte slices, return the set whose
  bytes differ. Add a `print_diff(a, b)` for CLI/diagnostic use.
- [ ] **Step 4: Port `cbfs.extend_fw_main_a(path)`** from `tmp/extend_cbfs_empty.py`
  (grows FW_MAIN_A's CBFS empty trailer to the region size). No new test logic
  yet — it's exercised in Task 5.
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit** `feat(fleet): region diff + cbfs-extend helpers`.

---

### Task 5: Combined image builder (`imagebuild.py` + CLI) — the core

Generalizes `tmp/build_devkey_bringup.py` + `tmp/build_depthcharge_image_v2.py`
into one build. Read both prototypes first. Steps (spec §5): copy live → GBB
rootkey→dev → extend FW_MAIN_A CBFS → swap `fallback/payload`→`depthcharge.elf` →
**mirror `FW_MAIN_A`→`FW_MAIN_B`** (equal-size body copy) → sign **both** vblocks
(dev keyblock + `dev_firmware_data_key`, `--kernelkey kernel_subkey.vbpubk`,
`--flags 0`, FV=each slot's full FW_MAIN) → `futility verify` → diff-gate.

**Files:** Create `galeflash/imagebuild.py`, `tools/fleet/build_gale_fleet_image.py`, `tests/test_imagebuild.py`.

- [ ] **Step 1: Failing test** — build from G4 stock, assert the invariants:

```python
import subprocess
from galeflash import imagebuild, fmapdiff, const
def test_build_from_g4(stock_g4, tmp_path):
    live = tmp_path/"live.bin"; live.write_bytes(stock_g4)
    out  = tmp_path/"out.bin"
    imagebuild.build(live, out)
    # (a) futility verify passes
    subprocess.run([str(const.FUTILITY), "verify", str(out)], check=True)
    # (b) only the allowed regions changed vs the live input
    changed = fmapdiff.changed_regions(stock_g4, out.read_bytes())
    assert changed <= const.ALLOWED_CHANGED          # leaf-only; composites excluded
    assert "RO_VPD" not in changed and "RW_VPD" not in changed
    # (c) both slots carry the identical payload body
    a0,aL = const.FMAP["FW_MAIN_A"]; b0,bL = const.FMAP["FW_MAIN_B"]
    buf = out.read_bytes()
    assert buf[a0:a0+aL] == buf[b0:b0+bL]
```

- [ ] **Step 2: Run → FAIL** (no `build`).

- [ ] **Step 3: Implement `imagebuild.build(live, out)`** (subprocess `futility`/
  `cbfstool` per the prototypes). Key calls, in order:

```python
shutil.copy2(live, out)
run(FUTILITY, "gbb_utility", "--set", "-k", DEVKEYS/"root_key.vbpubk", out)
cbfs.extend_fw_main_a(out)
run(CBFSTOOL, out, "remove", "-r", "FW_MAIN_A", "-n", "fallback/payload")
run(CBFSTOOL, out, "add-payload", "-r", "FW_MAIN_A", "-n", "fallback/payload",
    "-f", PAYLOAD_ELF, "-c", "lzma")
# mirror body A -> B (equal size)
buf = bytearray(out.read_bytes())
a0,aL = FMAP["FW_MAIN_A"]; b0,_ = FMAP["FW_MAIN_B"]
buf[b0:b0+aL] = buf[a0:a0+aL]
out.write_bytes(buf)
# sign each slot: vbutil_firmware over that slot's FV, splice vblock
for slot in ("A","B"):
    sign_slot(out, slot)     # see Step 4
run(FUTILITY, "verify", out)
# diff gate (leaf regions only; const.ALLOWED_CHANGED)
assert fmapdiff.changed_regions(live.read_bytes(), out.read_bytes()) <= const.ALLOWED_CHANGED
```

- [ ] **Step 4: Implement `sign_slot`** mirroring `build_depthcharge_image_v2.py`'s
  vbutil_firmware+splice, parameterized by slot (use `FMAP["VBLOCK_<slot>"]` /
  `FMAP["FW_MAIN_<slot>"]`), dev keyblock for both (bodies are identical):

```python
def sign_slot(img, slot):
    vb_off, vb_size = FMAP[f"VBLOCK_{slot}"]; fv_off, fv_size = FMAP[f"FW_MAIN_{slot}"]
    buf = img.read_bytes(); fv = TMP/f"_fv_{slot}.bin"; fv.write_bytes(buf[fv_off:fv_off+fv_size])
    nvb = TMP/f"_vb_{slot}.bin"
    run(FUTILITY, "vbutil_firmware", "--vblock", nvb,
        "--keyblock", DEVKEYS/"dev_firmware.keyblock",
        "--signprivate", DEVKEYS/"dev_firmware_data_key.vbprivk",
        "--version", "1", "--fv", fv,
        "--kernelkey", DEVKEYS/"kernel_subkey.vbpubk", "--flags", "0")
    nb = nvb.read_bytes(); assert len(nb) <= vb_size
    m = bytearray(buf); m[vb_off:vb_off+vb_size] = nb + b"\x00"*(vb_size-len(nb))
    img.write_bytes(bytes(m)); fv.unlink(); nvb.unlink()
```

- [ ] **Step 5: Run → PASS.** Iterate against the fixture until (a)/(b)/(c) hold.

- [ ] **Step 6:** Add a **second** build test from `tmp/gale-live-2026-06-08-pre-devkey.bin`
  (different unit) asserting the same invariants — proves it's per-puck-generic.

- [ ] **Step 7: Write CLI** `build_gale_fleet_image.py <live.bin> <out.bin>` →
  calls `imagebuild.build`, prints sha256 + the region diff. Non-zero exit if the
  verify or diff-gate fails (so it can never emit a bad image).

- [ ] **Step 8: Commit** `feat(fleet): combined dev-key tftp-first image builder`.

---

### Task 6: Flasher with serial guard + RO-last order (`flash_gale_fleet.py`)

**Files:** Create `galeflash/serialguard.py`, `galeflash/flashplan.py`,
`tools/fleet/flash_gale_fleet.py`, `tests/test_serialguard.py`, `tests/test_flash_order.py`.

- [ ] **Step 1: Failing test for the guard decision** (pure logic, no hardware):

```python
from galeflash import serialguard
def test_guard_blocks_mismatch():
    assert serialguard.ok("2831HW00VZA", "2831HW00VZA") is True
    assert serialguard.ok("2831HW00VZA", "1605HW000GM") is False
```

- [ ] **Step 2: Run → FAIL.** Implement `serialguard.ok(live_serial, expected)`.
  Add `serialguard.read_live_serial()` that does a **partial bridge read** of
  `RO_VPD` (`0x3E0000:0x20000`) via the existing toolkit, then `vpd.decode` →
  `serial_number`. (Reuse `raiden`/`chunk_read` read primitives; one short
  parking session. Mark hardware path `# pragma: no cover`.)
- [ ] **Step 3: Run → PASS.**

- [ ] **Step 4: Failing test for write ordering** (assert the planned region
  sequence is RO-last, via a dry-run that records calls):

```python
def test_write_order_is_ro_last(monkeypatch):
    from galeflash import flashplan
    calls = flashplan.regions_in_order()   # returns list of (name, extra_flags)
    names = [c[0] for c in calls]
    assert names == ["RW_SECTION_A","RW_SECTION_B","0x301000:0xdf000"]
    assert "--allow-ro" in calls[-1][1]    # GBB span only
```

- [ ] **Step 5: Run → FAIL.** Factor the ordering into `flashplan.regions_in_order()`
  and implement `flash_gale_fleet.py` to: (1) `ec_console.py "gale power off"`,
  (2) read+guard the serial (abort on mismatch), (3) for each region in order,
  re-park then `raiden_write_region.py <img> <region> --chunk <N> --commit`
  (GBB span adds `--allow-ro`). Default `--chunk 0x1000`; `--chunk 0x4000` opt-in.
- [ ] **Step 6: Run → PASS.**
- [ ] **Step 7: Commit** `feat(fleet): serial-guarded RO-last flasher`.

---

### Task 7: Single-puck orchestrator (`flash_one_puck.py`)

Wires Phase-0 tools into the operator entrypoint: **backup → extract identity →
build → (gate) → flash → power on**. Verification is observed by the operator on
serial (the script prints the exact things to watch).

**Files:** Create `galeflash/orchestrator.py`, `tools/fleet/flash_one_puck.py`, `tests/test_orchestrator.py`.

- [ ] **Step 1: Failing test** — orchestrator in `--dry-run` plans the right steps
  given a fixture as the "backup", and **refuses to flash** if `is_stock` is False
  unless `--rekeyed-ok` (don't re-key an already-keyed unit by accident):

```python
def test_dryrun_plan(stock_g4, tmp_path, monkeypatch):
    from galeflash import orchestrator
    plan = orchestrator.plan(backup=write_fixture(stock_g4, tmp_path), dry_run=True)
    assert plan.steps == ["backup","extract","build","verify","flash","poweron"]
    assert plan.expected_serial == "2831HW00VZA"
```

- [ ] **Step 2–4: TDD** the `orchestrator.plan()` pure logic (no hardware): chooses
  backup filename `gale-<serial>-<date>-pre-flash.bin`, the built image name, and
  the expected-serial passed to the guard. Real run shells out to Task 1–6 tools.
- [ ] **Step 5:** Implement the imperative `main()` (backup via `chunk_read.py all`,
  then `extract_identity`, `build_gale_fleet_image`, `flash_gale_fleet`,
  `ec_console "gale power on"`), printing the §7 serial exit-criteria to watch.
- [ ] **Step 6: Commit** `feat(fleet): single-puck flash orchestrator`.

---

### Task 8: Sheet sync (`sync_sheet.py`) — gcloud service account

`gcloud` is now installed. Auth path: create/identify a service account in the
**`gdoc2netcfg`** project, share the target sheet with its email, and have
`sync_sheet.py` use SA creds (google-auth) — decoupled from flashing.

**Files:** Create `tools/fleet/sync_sheet.py`, `tests/test_sheetmap.py`.

- [ ] **Step 1: TDD the mapping** (pure, no network): given an `inventory/<serial>.json`
  and the sheet's current rows, compute the cell writes — match dump `serial_number`
  to the Serial(D) column, fill the new columns (mlb_serial, region, MACs, HWID,
  RO firmware, backup path, sha256, date/status). Assert it refuses to overwrite a
  non-empty cell with a *different* value (same guard style as `fill_pucks.py`).
- [ ] **Step 2:** Implement `sheet_auth()` using a SA key
  (`GALE_SHEETS_SA_JSON` env → `google.oauth2.service_account.Credentials`),
  falling back to the legacy token path if present.
- [ ] **Step 3:** Implement `main()` — read all `inventory/*.json`, batch-update the
  sheet (dry-run default; `--write` to apply), then read back + print (mirror
  `fill_pucks.py`'s verify-after-write).
- [ ] **Step 4: Commit** `feat(fleet): inventory -> sheet sync (gcloud SA auth)`.

> **Separate prep step (not blocking Phase 1).** ✅ DONE 2026-06-30: SA
> `gale-fleet-sheets@gdoc2netcfg-appscript.iam.gserviceaccount.com` created in
> project `gdoc2netcfg-appscript` (the real project; "gdoc2netcfg" was the repo
> name), Sheets API enabled, key at `~/.config/gale-fleet/sheets-sa.json` (mode 600,
> dir 700). Sheet (gid `210946497`) shared with the SA as **Editor** ✅ and SA
> read-access verified 2026-06-30. For `sync_sheet.py`:
> `export GALE_SHEETS_SA_JSON=~/.config/gale-fleet/sheets-sa.json`.

---

## Phase 1 — Hardware pilot (operational; observe on serial)

### Task 9: Pre-flight (once)

- [ ] SuzyQ enumerates: `lsusb | grep 18d1:500f`; `uv run tools/ec_console.py "gale version"` responds.
- [ ] Flash array unprotected: `uv run tools/raiden_sr.py` shows `RDID==ef4017`, `BP=CMP=WPS=0`.
- [ ] Host NIC cabled to the puck **WAN** port (printed-MAC jack); bring it up:
  `sudo ip addr add 192.168.50.1/24 dev <nic>; sudo ip link set <nic> up`.
- [ ] dnsmasq staged with a known-good OpenWrt netboot FIT (e.g.
  `tmp/active-netboot.itb`) per `gale-openwrt-netboot-install.md` §1 — but **leave
  it stopped** until step 2 of the pilot verify.
- [ ] `mkdir -p /home/tim/local/gwifi/fleet-flash/{backups,inventory}` (outside git).
- [ ] Fleet inventory: list pucks; mark stock vs already-flashed; pick a **fresh
  stock** pilot (NOT the bring-up unit). G4 (`gale-spi-stock-2026-05-28.bin`) is a
  known fleet member and a fine pilot candidate if physically on hand & stock.

### Task 10: Pilot one puck + checkpoint

- [ ] **Before the power-on step**: start watching the AP serial console
  (`/dev/ttygwifi-ap`, 115200) — the §7 exit-criteria block is printed right
  before power-on, so the console must be open and ready to capture output.
- [ ] Run `uv run tools/fleet/flash_one_puck.py --serial-hint <S> --date <YYYY-MM-DD>
  [--rekeyed-ok] [--chunk 0x1000] [--dry-run]` (backs up →
  builds → serial-guards → flashes RO-last → powers on).
- [ ] **Verify on AP serial** (`/dev/ttygwifi-ap`-equiv, 115200):
  - boots **RW coreboot (Dec 2018) → depthcharge**, *not* immediate recovery
    (immediate recovery ⇒ vboot rejected our dev-keyed slot — STOP, investigate).
  - **netboot-first proven:** start dnsmasq → see DHCP→TFTP→OpenWrt RAM login.
  - **fallback proven:** stop dnsmasq, `reboot` → depthcharge waits the timeout,
    falls through to vboot/eMMC (lands in recovery; eMMC is stock — expected).
- [ ] Record result into `inventory/<serial>.json` (status, image sha256, backup path).
- [ ] **CHECKPOINT — stop. Review pilot with the human before any more pucks.**

## Phase 2 — Fleet rollout

### Task 11: Roll out remaining stock pucks
- [ ] For each remaining stock puck: `uv run tools/fleet/flash_one_puck.py
  --serial-hint <S> --date <YYYY-MM-DD> [--chunk 0x4000]` → light verify
  (boots dev-keyed slot + netboots). Consider `--chunk 0x4000` now that the
  pilot validated timing. Record each.

### Task 12: Finalize
- [ ] `uv run tools/fleet/sync_sheet.py --write` once the SA is set up.
- [ ] Write the operator runbook `docs/gale-fleet-firmware-flash-runbook.md`
  (condensed, hardware-only steps) from the proven pilot.
- [ ] Use superpowers:finishing-a-development-branch to merge/PR.

---

## Risks carried from the spec (§12)
Serial-match guard (wrong puck), per-device VPD preserved (build per-puck +
diff-gate), RO-last rollback, flash-time tuning (16 KiB after pilot), decoupled
sheet sync. SuzyQ recovery (re-flash the `pre-flash.bin`) is always available.
