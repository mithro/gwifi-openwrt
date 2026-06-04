# Regenerating the `gale` EC firmware from source

Reconstruct the missing `board/gale/` source in the ChromiumOS EC tree so the
Google Wifi (`gale`) embedded-controller firmware — **`gale_v1.1.5337-0115719`**
— can be **rebuilt from source**, then verify the rebuild against the on-device
dump.

## Goal, fidelity, and scope

- **Goal:** a buildable `board/gale/` such that `make BOARD=gale` regenerates the
  EC firmware (RO + RW), plus a documented build recipe and a fidelity report.
- **Fidelity target — *functional + diff-verified*.** The rebuild must compile
  cleanly and match the dump **structurally**: reset/vector table, FMAP geometry,
  `RO_FRID`/`RW_FWID`, symbol/function layout, string table, and RO/RW section
  sizes. **Byte-exactness is a non-goal** — the image embeds a 2016 build
  timestamp + builder host (`2016-10-03 15:55:36 hywu@hywu-z620…google.com`) and
  the exact `gcc-arm-none-eabi` version/flags are unknown, so codegen differs
  cosmetically.
- **Scope boundary — build + *static* diff-verify only.** Flashing the rebuild
  onto hardware is **out of scope**: the EC console exposes no flash-write
  command, so flashing would require SWD/OpenOCD (feasible — option bytes read
  RDP=0xAA, Level 0 — but deferred to a later, separately-scoped effort).

## Background — what we already have

- **The dump** (read read-only over the EC `md` console; the `gale-ec-*.bin`
  files in this repo):
  - `gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin` — 131072 B, STM32F072CB
    internal flash @`0x08000000`. sha256 `602a461444fc96c17fcac3534ea0cf93dcc645d7327e53de330c2a1c82c20497`.
    **RO = `0x00000–0x0FFFF`, RW = `0x10000–0x1FFFF`** (EC_FMAP @`0xE280`;
    `RO_FRID` == `RW_FWID` == `gale_v1.1.5337-0115719`).
  - `gale-ec-systemmem-bootloader-2026-06-04.bin` — 12288 B, ST system bootloader
    ROM @`0x1FFFC800` (generic STM32F0 mask ROM; reference only, not part of the
    rebuild). sha256 `766738a466b90ab944fadfdc47902db4513c6321ac3870404aec6a8278ee78d8`.
  - `gale-ec-optionbytes-2026-06-04.bin` — 16 B @`0x1FFFF800` (RDP=0xAA). sha256
    `cdb247d463ca13714fd6941d172ad5bbbbc3c7438f485eb4caf5fefd5d772619`.
- **The source tree:** `chromiumos/platform/ec` @ branch **`firmware-gale-8281.B`**
  (rev `7c97ab0`). `common/`, `chip/stm32/`, `core/cortex-m0`, `driver/`, and the
  Makefiles are all present. **`board/gale/` is empty** — stripped on the public
  branch. The board layer is therefore the *only* missing source.
- **Live, read-only EC facts** (chip `stm stm32f07x`; `flashinfo` → `Usable: 128 KB`):
  the full `gpioget` signal list, the console command set, and — to be captured —
  `taskinfo`.

## Approach — differential reconstruction

~95% of the 128 KB image compiles from the **public** `common`/`chip`/`core`/
`driver` at this exact revision. Rather than decompile everything, compile the
public tree and use its symbols to **subtract** identifiable library code from the
dump; the unexplained remainder is the board layer — exactly the files we must
write. The dump also yields most board facts directly (GPIO list, task list, chip
variant, console commands, FMAP). True decompilation is then needed only for
board-specific logic (`board.c`: GPIO/SPI/PD tables, the `gale` console command,
PD policy).

**Rejected alternatives:** full clean-room decompilation of the whole image
(wasteful — re-derives public code, error-prone); pure config-inference with no
decompilation (insufficient for `board.c` logic — folded in here as the cheap
first pass, with the diff loop revealing where real decompilation is required).

## Files to reconstruct (`board/gale/`)

Modeled on the minimal board set (`board/servo_micro/` — the closest analog:
STM32F072 + USB-serial consoles + raiden SPI bridge — and `board/ryu/`, whose USB
PID gale reuses):

| File | Primary source of truth |
|---|---|
| `gpio.inc` | recovered `gpio_list[]` / alternate-function tables (decompiled), cross-checked against the live `gpioget` names + order |
| `build.mk` | `CHIP:=stm32`, `CHIP_FAMILY:=stm32f0`, `CHIP_VARIANT:=stm32f07x` + board obj list (from the decompiled link map) |
| `board.h` | `CONFIG_*` flags matching observed features: USB-PD dual-role, TCPC, raiden USB-SPI bridge, USB consoles, crystalless USB, FMAP/flash params, enabled console commands |
| `board.c` | GPIO / I²C / SPI tables, `spi_devices[]` (the W25Q64 AP-flash bridge), PD/TCPC policy, the `gale` console command, hooks/init |
| `ec.tasklist` | live `taskinfo` + decompiled task table |
| `Makefile` | standard one-line board Makefile |

The recovered `build.mk` obj list may pull in extra units (e.g. `usb_pd_policy.c`).

## Plan (phased)

### P0 — Toolchain & baseline build
Full-checkout `firmware-gale-8281.B` (the local clone is blobless — fetch blobs).
Pin `gcc-arm-none-eabi` per `Makefile.toolchain`. Prove the environment by
building a template board (`make BOARD=servo_micro`) and confirming it emits
`build/servo_micro/{RO,RW}/ec.{RO,RW}.flat`, the ELFs, and an FMAP. **Exit:** a
known-good board builds end-to-end.

### P1 — Public-vs-board partition (the differential map)
Load the dump in Ghidra (Cortex-M0; RO @`0x08000000`, RW @`0x08010000`; STM32F072
SVD for peripherals; entry points from the dumped vector tables). Build a template
board's ELF for symbols and match functions in the dump against known public code
(CFG/signature matching + string-xref anchoring). **Output:** a map flagging
board-specific functions (the RE target) and confirming anchors — FMAP,
`RO_FRID`/`RW_FWID`, and console-string → handler cross-references.

### P2 — Harvest board facts
Read-only, via the existing EC-console tooling: `gpioget` (GPIO names/order),
`taskinfo` (task list), `version` (chip variant), `flashinfo` (flash params), the
console-command list (→ `CONFIG_CMD_*` / board commands). From the binary: the
`gpio_list[]` + alt-func tables, `spi_devices[]`, PD/TCPC config, and
`command_gale`. **Output:** a structured board-facts sheet feeding P3.
`taskinfo` is a **hard prerequisite** for reconstructing `ec.tasklist`, so it
must be captured in this phase before P3 begins.

### P3 — Reconstruct the six files
Write `gpio.inc`, `build.mk`, `board.h`, `board.c`, `ec.tasklist`, `Makefile`
from the P1 map + P2 facts, using servo_micro/ryu as scaffolds. **Exit:**
`board/gale/` is complete enough to attempt a build.

### P4 — Build & static diff-verify loop (the fidelity gate)
`make BOARD=gale` → diff the rebuild against the dump on: reset/vector table,
FMAP region geometry, `RO_FRID`/`RW_FWID`, symbol/function layout (rebuilt ELF vs
the P1 map), string-table parity, and RO/RW section sizes. Iterate fixes to
`board/*` and rebuild until matched within tolerance. **Done =** all of those
align, with only the build-banner/timestamp (and documented toolchain-codegen)
deltas remaining.

### P5 — Deliverables
The reconstructed `board/gale/`, a pinned build recipe, the diff/verify scripts,
and a fidelity report (what matched + each residual diff explained).

## Verification / definition of done

1. `make BOARD=gale` builds RO + RW without errors.
2. Rebuilt FMAP regions (EC_RO/EC_RW/RO_FRID/RW_FWID + offsets/sizes) match the
   dump.
3. Reset vector + early vector-table entries match (modulo handler-address
   shifts from codegen). The P4 diff script declares which vector slots must
   match exactly vs. may shift, so the gate stays mechanically decidable.
4. The rebuilt console-command set and string table match the dump's.
5. Symbol/function layout corresponds to the P1 map (every board-specific
   function present; no unexplained gaps).
6. RO and RW section sizes are within a tolerance that is **fixed after the
   first successful P4 build** and recorded in the fidelity report (not pre-set,
   so it cannot drift during the iterate-until-matched loop).
7. A fidelity report enumerates every residual difference and why it is
   acceptable (build banner/timestamp, toolchain codegen).

## Risks & non-goals

- **Non-goal:** byte-identical reproduction; on-hardware flashing/boot test.
- **Toolchain unknown** → verification is **symbol/structure-level, not
  byte-level** (consistent with the chosen fidelity).
- **Decompilation effort concentrates in `board.c`** (PD policy, the `gale`
  command, the SPI bridge). `gpio.inc` correctness matters most for a genuinely
  buildable image.
- **`board/gale` may need files beyond the standard six** (e.g.
  `usb_pd_policy.c`); the recovered `build.mk` obj list resolves this.
- The public branch could differ subtly from the exact firmware revision; the
  build-diff loop surfaces any such divergence.

## References

- EC source: `chromiumos/platform/ec` @ `firmware-gale-8281.B` (`7c97ab0`).
- Templates: `board/servo_micro`, `board/ryu`.
- Dumps + sha256: the `gale-ec-*.bin` files in this repository.
- Dump method: read read-only over the EC USB debug console (`md 0x08000000`),
  documented in the EC-dump commit.
