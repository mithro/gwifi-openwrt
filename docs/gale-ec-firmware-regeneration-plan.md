# gale EC firmware regeneration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruct the missing `board/gale/` source so `make BOARD=gale` rebuilds the gale EC firmware (`gale_v1.1.5337-0115719`), statically diff-verified against the on-device dump.

**Completion criterion (hardened 2026-06-05):** done ONLY when `make BOARD=gale` compiles a firmware that an **independent reviewer certifies is 100% functionally equivalent** to the dumped image (cosmetic build-banner/timestamp and benign-codegen deltas excepted). See Task 8.

**Architecture:** Differential reverse-engineering. Build the *public* EC tree (`common`/`chip`/`core`/`driver` @ `firmware-gale-8281.B`) to subtract identifiable library code from the dump; reconstruct only the board layer (6 files), seeded by live read-only EC facts and `servo_micro`/`ryu` templates; iterate a build→diff loop against the dump until structurally matched.

**Tech Stack:** ChromiumOS EC build system (`make BOARD=…`), `gcc-arm-none-eabi`, Ghidra (headless, Cortex-M0), Python 3 (`uv`), `arm-none-eabi-{nm,objdump}`, `futility`/`dump_fmap`.

**Companion spec:** [`gale-ec-firmware-regeneration.md`](gale-ec-firmware-regeneration.md) — read it first (goal, fidelity, 7-point DoD).

---

## Conventions for this plan

- `$EC` = a full checkout of `chromiumos/platform/ec` @ `firmware-gale-8281.B`.
- `$DUMP` = `gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin` (repo root, 131072 B, sha256 `602a4614…20497`).
- All new tooling/artifacts live under `gale-ec/` in this repo. The reconstructed `board/gale/` is BSD-3-Clause (matches `platform/ec`), not the repo's Apache-2.0.
- Run Python with `uv run python …`. Console captures are **read-only** (`version`/`gpioget`/`taskinfo`/`flashinfo` only).

## File Structure

```
gale-ec/
  README.md              # how to reproduce: clone $EC, overlay board/gale, build, verify
  board/gale/            # DELIVERABLE: reconstructed source (BSD-3-Clause)
    Makefile  build.mk  board.h  board.c  gpio.inc  ec.tasklist
  tools/
    split_image.py       # carve $DUMP -> ec-RO.bin / ec-RW.bin
    capture_facts.py      # read-only EC console capture -> board-facts.md
    extract_gpio.py      # decode gpio_list[] from ec-RO.bin
    gpio_verify.py       # gpio.inc  <->  facts (the gpio verifier)
    build_map.py         # public-symbol vs board-specific partition
    diff_verify.py       # rebuilt image vs $DUMP -> FIDELITY report (the P4 gate)
  board-facts.md         # P2 output (committed)
  FIDELITY.md            # P4/P5 output (committed)
```

---

## Task 0: EC build environment & baseline build  (spec P0)

**Files:** `gale-ec/README.md` (create, env notes); `$EC` checkout (external).

- [ ] **Step 1:** Full-checkout the EC tree (the local `tmp/ec-gale` is blobless). Run:
  `git clone --branch firmware-gale-8281.B --single-branch https://chromium.googlesource.com/chromiumos/platform/ec "$EC"`
  Expected: `$EC/common`, `$EC/chip/stm32`, `$EC/core/cortex-m0`, `$EC/board/servo_micro` exist; `$EC/board/gale` is **empty/absent**.
- [ ] **Step 2:** Identify the toolchain. Run: `sed -n '1,40p' "$EC/Makefile.toolchain"` and `arm-none-eabi-gcc --version`. Record the available version in `gale-ec/README.md` (exact-version match is **not** required per the spec).
- [ ] **Step 3:** Build a known-good template board. Run: `make -C "$EC" BOARD=servo_micro -j`
  Expected: `$EC/build/servo_micro/ec.bin`, `ec.RO.flat`, `ec.RW.flat`, `RO/ec.RO.elf`, `RW/ec.RW.elf`.
- [ ] **Step 4 (verify):** Confirm the build emits an FMAP. Run: `futility dump_fmap "$EC/build/servo_micro/ec.bin"` (or `grep -aob __FMAP__`).
  Expected: `EC_RO`/`EC_RW` regions listed. If this fails, the environment is wrong — stop and fix before continuing.
- [ ] **Step 5: Commit** `git add gale-ec/README.md && git commit -m "gale-ec: P0 build environment notes + baseline build recipe"`

## Task 1: Image split + differential function map  (spec P1)

**Files:** Create `gale-ec/tools/split_image.py`, `gale-ec/tools/build_map.py`; output `gale-ec/function-map.json`.

- [ ] **Step 1: Write `split_image.py`** — carve `$DUMP` into `ec-RO.bin` (0x0–0xFFFF) and `ec-RW.bin` (0x10000–0x1FFFF):

```python
import sys, pathlib
d = pathlib.Path(sys.argv[1]).read_bytes()
assert len(d) == 0x20000, len(d)
pathlib.Path("ec-RO.bin").write_bytes(d[0:0x10000])
pathlib.Path("ec-RW.bin").write_bytes(d[0x10000:0x20000])
print("RO/RW 65536 each")
```

- [ ] **Step 2 (verify):** Run `uv run python gale-ec/tools/split_image.py "$DUMP"`. Expected: two 65536-byte files; `ec-RO.bin` first words `c0 04 00 20 ed 00 00 08` (the known RO reset vector).
- [ ] **Step 3:** Build the template RW ELF symbol list: `arm-none-eabi-nm -nS "$EC/build/servo_micro/RW/ec.RW.elf" > servo_micro.syms`. Expected: hundreds of `common/`/`chip/` symbols (e.g. `hook_task`, `console_task`, `usb_spi_*`).
- [ ] **Step 4:** Load `ec-RW.bin` in Ghidra headless — Cortex-M0 (`ARM:LE:32:Cortex`), image base `0x08010000`, apply STM32F072 SVD, set entry from the RW vector table, auto-analyze. Document the exact `analyzeHeadless` invocation in `build_map.py`'s header.
- [ ] **Step 5: Write `build_map.py`** — match dump functions to public symbols (string-xref anchoring + the `servo_micro.syms` names that share string usage), emit `function-map.json` = `{addr: {name|null, source: "public"|"board"|"unknown", size}}`.
- [ ] **Step 6 (verify):** Run it. Expected: the **board-specific** set is small (tens, not hundreds) and includes the handlers for the `gale` console command and the raiden SPI bridge (cross-check: their addresses are reachable from the `gale`/`spixfer` console string xrefs).
- [ ] **Step 7: Commit** `git add gale-ec/tools/split_image.py gale-ec/tools/build_map.py gale-ec/function-map.json && git commit -m "gale-ec: P1 image split + public-vs-board function map"`

## Task 2: Harvest board facts  (spec P2)

**Files:** Create `gale-ec/tools/capture_facts.py`, `gale-ec/tools/extract_gpio.py`; output `gale-ec/board-facts.md`.

- [ ] **Step 1: Write `capture_facts.py`** — reuse the read-only console client (`md`/`version` pattern from the dump tooling) to run and record: `version`, `gpioget`, `taskinfo`, `flashinfo`, `help`. (Read-only; no state change.)
- [ ] **Step 2 (verify):** Run against the live EC. Expected: `gpioget` returns the full signal list (≈26 names incl. `WP_L`, `SPI_FLASH_*`, `VDD_*`, `USB_CC*`); `taskinfo` returns the RTOS task table. **`taskinfo` is the hard prerequisite for `ec.tasklist`.**
- [ ] **Step 3: Write `extract_gpio.py`** — locate the `gpio_list[]` table in `ec-RO.bin` (the EC compiles `gpio.inc` into a `struct gpio_info[]`: port base, pin mask, flags) and decode per-signal `(port, pin, flags)`; align count/order to the `gpioget` names.
- [ ] **Step 4 (verify):** Run it. Expected: decoded entry count == `gpioget` signal count; ports/pins are plausible STM32F072 GPIO (GPIOA–F).
- [ ] **Step 5:** Record everything (console captures, decoded GPIO table, `spi_devices[]`, I²C/PD config addresses from `function-map.json`) in `board-facts.md`.
- [ ] **Step 6: Commit** `git add gale-ec/tools/capture_facts.py gale-ec/tools/extract_gpio.py gale-ec/board-facts.md && git commit -m "gale-ec: P2 board facts (gpio/tasks/flash/PD) harvested"`

## Task 3: Reconstruct `gpio.inc` (verifier-first)  (spec P3)

**Files:** Create `gale-ec/tools/gpio_verify.py`, `gale-ec/board/gale/gpio.inc`.

- [ ] **Step 1: Write the verifier `gpio_verify.py`** — parse a `gpio.inc` into `(name, port, pin, flags)` and diff against `board-facts.md` (names+order from `gpioget`, ports/pins/flags from `extract_gpio.py`). Exit non-zero on any mismatch, printing the offending signals.
- [ ] **Step 2 (red):** Run `uv run python gale-ec/tools/gpio_verify.py gale-ec/board/gale/gpio.inc`. Expected: **FAIL** ("no such file").
- [ ] **Step 3:** Write `board/gale/gpio.inc` from the decoded table + `board/servo_micro/gpio.inc` structure (GPIO/UNUSED/ALTERNATE macros, IRQ handlers for the USB/SPI lines).
- [ ] **Step 4 (green):** Re-run the verifier. Expected: **PASS** (every signal name/port/pin/flag matches).
- [ ] **Step 5: Commit** `git add gale-ec/tools/gpio_verify.py gale-ec/board/gale/gpio.inc && git commit -m "gale-ec: P3 reconstruct board/gale/gpio.inc (verified vs dump+gpioget)"`

## Task 4: Reconstruct `build.mk`, `board.h`, `ec.tasklist`, `Makefile`  (spec P3)

**Files:** Create `gale-ec/board/gale/{build.mk,board.h,ec.tasklist,Makefile}`.

- [ ] **Step 1:** `Makefile` + `build.mk` — copy the standard one-liner `Makefile`; in `build.mk` set `CHIP:=stm32`, `CHIP_FAMILY:=stm32f0`, `CHIP_VARIANT:=stm32f07x`, and `board-y` = objects implied by `function-map.json` (start: `board.o`; add `usb_pd_policy.o` if the map shows PD-policy symbols).
- [ ] **Step 2:** `ec.tasklist` — transcribe the task set from `board-facts.md` `taskinfo` (e.g. `HOOKS`, `USB_CHG`, `PD`, `PD_INT`, `HOSTCMD`, `CONSOLE`) in priority order.
- [ ] **Step 3:** `board.h` — enable the `CONFIG_*` that match observed features: USB-PD dual-role + TCPC, raiden USB-SPI bridge (`CONFIG_USB_SPI`), USB consoles, crystalless USB (`CONFIG_STM32_CLOCK_HSI`/USB), `CONFIG_FLASH`/FMAP params for 128 KB, and the `CONFIG_CMD_*` matching the dump's console command list (`md`, `rw`, `spixfer`, `flashinfo`, `flashwp`, `gpioget/set`, `hash`, `sysinfo`, `gettime`, `waitms`, `gale`).
- [ ] **Step 4 (verify):** Sanity-build to surface missing symbols: `make -C "$EC" BOARD=gale -j` (with `board/gale` overlaid — see Task 6 Step 1). Expected at this stage: compiles further than before; remaining errors point to `board.c` gaps (next task). Record the error list.
- [ ] **Step 5: Commit** `git add gale-ec/board/gale/{build.mk,board.h,ec.tasklist,Makefile} && git commit -m "gale-ec: P3 reconstruct build.mk/board.h/ec.tasklist/Makefile"`

## Task 5: Reconstruct `board.c`  (spec P3 — the decompilation-heavy task)

**Files:** Create `gale-ec/board/gale/board.c`.

- [ ] **Step 1:** Scaffold from `board/servo_micro/board.c`: include set, `gpio_alt_func`/alternate-function arrays, `i2c_ports[]`, `spi_devices[]` (the W25Q64 AP-flash device), and `void board_config_pre_init`/hooks.
- [ ] **Step 2:** Reconstruct the **board-specific functions** flagged in `function-map.json` by reading their Ghidra decompilation: the `gale` console command (`command_gale` — power on/off AP, GPIO bridge), the raiden/`usb_spi` board glue, and the PD policy (`pd_check_*`, src/snk caps observed via `pd` console). Translate decompiled logic to idiomatic EC C against the public APIs.
- [ ] **Step 3 (verify):** `make -C "$EC" BOARD=gale -j`. Expected: **RO + RW build cleanly** (`build/gale/ec.bin` produced). Fix until it links.
- [ ] **Step 4 (verify):** Quick string parity check: `arm-none-eabi-strings build/gale/RW/ec.RW.elf` contains `gale_v1.1` build banner slot, `command_gale`'s help text, and the PD state strings. 
- [ ] **Step 5: Commit** `git add gale-ec/board/gale/board.c && git commit -m "gale-ec: P3 reconstruct board/gale/board.c (gale cmd + raiden SPI + PD policy)"`

## Task 6: Build & static diff-verify loop  (spec P4 — the fidelity gate)

**Files:** Create `gale-ec/tools/diff_verify.py`; output `gale-ec/FIDELITY.md`.

- [ ] **Step 1:** Document + script the overlay+build: symlink/copy `gale-ec/board/gale` into `$EC/board/gale`, then `make -C "$EC" BOARD=gale -j`. Put this in `gale-ec/README.md`.
- [ ] **Step 2: Write `diff_verify.py`** — compare `build/gale/ec.bin` against `$DUMP` and emit a report:
  - FMAP regions (parse both, compare `EC_RO`/`EC_RW`/`RO_FRID`/`RW_FWID` offset+size) — **must be exact**.
  - Vector table: compare a **declared** slot list — SP+reset+NMI+HardFault require exact match; other handler slots may shift (codegen). Print per-slot exact/shifted.
  - `RO_FRID`/`RW_FWID` strings — exact.
  - String-table set parity (symmetric diff of `strings` sets) — list extras/missing.
  - RO/RW section sizes — print delta; tolerance set after first build (Step 4).
- [ ] **Step 3 (red→green loop):** Run `diff_verify.py`. For each non-cosmetic diff, fix `board/gale/*`, rebuild, re-run. Iterate until only build-banner/timestamp + within-tolerance codegen deltas remain.
- [ ] **Step 4:** After the first clean build, **fix** the RO/RW section-size tolerance and record it in `FIDELITY.md` so it can't drift.
- [ ] **Step 5 (verify):** Confirm the 7-point Definition of Done (spec) is met; write the residual-diff explanations into `FIDELITY.md`.
- [ ] **Step 6: Commit** `git add gale-ec/tools/diff_verify.py gale-ec/FIDELITY.md && git commit -m "gale-ec: P4 diff-verify gate + fidelity report (DoD met)"`

## Task 7: Deliverables & docs  (spec P5)

**Files:** Finalize `gale-ec/README.md`; update repo `README.md` "What's here".

- [ ] **Step 1:** Finish `gale-ec/README.md`: exact reproduce steps (clone `$EC`, overlay `board/gale`, build, run `diff_verify.py`), toolchain note, and a one-line BSD-3-Clause header note for `board/gale/`.
- [ ] **Step 2:** Add a "gale EC firmware (reconstructed source)" bullet to the repo `README.md` "What's here" section, linking `gale-ec/` and the two `docs/` files.
- [ ] **Step 3 (verify):** Fresh-clone dry run — from a clean `$EC`, follow `gale-ec/README.md` verbatim; expect a building, diff-verified image.
- [ ] **Step 4: Commit + push** `git add gale-ec/README.md README.md && git commit -m "gale-ec: P5 reproduce docs + repo README" && git push origin main`

---

## Task 8: Independent functional-equivalence certification  (THE completion gate)

**Files:** output `gale-ec/EQUIVALENCE-REVIEW.md`.

- [ ] **Step 1:** Assemble the evidence pack: rebuilt `build/gale/ec.bin` + `$DUMP`, `FIDELITY.md`, `function-map.json`, and a per-function correspondence table (decompiled-dump function ⇄ reconstructed-source function) for **every** board-specific symbol.
- [ ] **Step 2:** Dispatch an **independent reviewer** (fresh subagent, given the evidence pack and the dump as ground truth — never the reconstruction session history) charged to find ANY functional divergence: GPIO/alt-func config, task set + priorities, console-command set + handler behavior, USB-PD policy, the raiden SPI bridge, interrupt routing, clock/flash config. Verdict: `EQUIVALENT` or `DIVERGENCES FOUND` (enumerated, each tied to a function/region).
- [ ] **Step 3 (loop):** If divergences found, fix `board/gale/*`, rebuild, re-run Task 6 diff, and **re-dispatch a fresh reviewer**. Repeat until `EQUIVALENT` (escalate to the human if 3 reviewer rounds don't converge).
- [ ] **Step 4:** Record the certification (reviewer verdict + residual cosmetic deltas) in `EQUIVALENCE-REVIEW.md`. Commit + push. **This — a clean compile plus an independent `EQUIVALENT` verdict — is the definition of done.**

## Notes / risks (from spec)
- Verification is **symbol/structure-level, not byte-level** (toolchain unknown). Byte-exactness and on-hardware flashing are **non-goals**.
- Effort concentrates in **Task 5** (`board.c`). If `function-map.json` leaves large unexplained regions, revisit Task 1 matching before hand-decompiling.
- If `make BOARD=gale` needs files beyond the six (the `build.mk` obj list reveals this), add them under Task 4/5 and note in `FIDELITY.md`.
