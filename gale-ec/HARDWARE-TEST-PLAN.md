# gale EC — hardware functional-equivalence test plan

Validate on the real device that the reconstructed firmware (`board/gale/`, built
as `build/gale/ec.bin`) behaves identically to the original — beyond the static
[`FIDELITY.md`](FIDELITY.md) / [`EQUIVALENCE-REVIEW-2.md`](EQUIVALENCE-REVIEW-2.md)
certification.

## Core method — differential testing vs a golden reference
The device currently runs the original firmware. So: (1) **capture "golden"** —
record the original's observable behavior across a fixed battery; (2) **flash the
rebuilt** firmware; (3) **re-run the identical battery and diff**. Equivalent ⟺
every observable behavior matches, *modulo the three documented immaterial deltas*
(version-banner string, firmware hash, the 3 extra `chan` labels lpc/pwm/switch).

## The flashing challenge (the crux)
The EC console has **no `flashwrite`**, so flashing needs **SWD**. gale repurposes
**PA14 (SWCLK) for USART2** (the AP console), so once firmware runs the SWD clock
pin is gone — you must attach **under reset** (assert `NRST`, halt the Cortex-M0
*before* it reconfigures PA14). Needs `SWDIO(PA13)/SWCLK(PA14)/NRST/GND` access.
Probe: RPi4 GPIO bit-bang (OpenOCD `linuxgpiod`) or an ST-Link/J-Link.

## Safety / recoverability
Option byte **RDP=0xAA (Level 0)** → SWD read/write is always available, so *any*
bad flash is recoverable by re-writing the stock image (sha256 `602a4614…`). The
plan re-verifies RDP stays 0 after every write. Fallbacks: the STM32 DFU bootloader
(BOOT0 high → `dfu-util`) and the CH341A clip on the AP flash (separate chip).

## Phases
**P0 — Prep & safety.** Locate SWD pins + NRST on the gale debug header/test points;
confirm RDP=0; stage the stock restore image; record `sha256(build/gale/ec.bin)`.
**RWSIG:** flash the *full* self-consistent RO+RW image (both ours, signed together
with the dev key); an RW-only swap would fail RW verification.
**P1 — Capture golden** (original firmware, running now): run the battery; save
`golden_*.txt`; note test conditions (AP state, any PD partner) to reproduce later.
**P2 — Establish & validate SWD.** OpenOCD `stm32f0x`, `reset_config srst_only
connect_assert_srst`, low speed; connect-under-reset, verify IDCODE/halt; **read the
full 128 KB and compare to the dump** (validates SWD *and* re-confirms the dump).
**P3 — Flash rebuilt & verify boot.** Back up live flash via SWD →
`program build/gale/ec.bin 0x08000000 verify reset` → read-back == ec.bin →
**re-check RDP still 0** → release reset → EC re-enumerates `18d1:500f`, console
responds, `version` shows the rebuilt build.
**P4 — Differential battery** (re-run P1, diff vs golden) — matrix below.
**P5 — Integration.** Power-cycle; confirm the **AP (IPQ4019) boots** (coreboot →
depthcharge → OS) and the device functions — validates power sequencing + the whole
EC end-to-end.
**P6 — Soak & restore.** Soak (hours): poll `taskinfo`/`panicinfo`. Restore: flash
the stock dump via SWD; verify read-back `sha256 == 602a4614…`; smoke-test.

## Test matrix
| Test | How | Expected (rebuilt vs golden) |
|---|---|---|
| EC liveness | `version` | responds; version *string* differs (banner) — immaterial |
| Tasks | `taskinfo` | identical set/order/stacks (HOOKS/HOSTCMD/CONSOLE/PD_C0) |
| GPIO config | `gpioget` | identical, all 27 signals |
| Flash | `flashinfo`, `flashwp` | identical |
| Console chans | `chan` | rebuild has +3 (lpc/pwm/switch) — known immaterial |
| Board cmd | `gale` (status) + each subcommand | identical |
| **Power sequencing** | `gale power off/on ap` + `gpioget` before/after; watch AP | rails toggle identically; AP powers down/up |
| **Raiden SPI bridge** ⭐ | `gale power off ap`; `flashrom -p raiden_debug_spi` RDID + read sha256 | identical RDID `ef4017` + identical read (the key end-to-end test) |
| USB enum | `lsusb -v -d 18d1:500f` | identical interfaces/endpoints/strings (modulo serial) |
| **USB-PD** ⭐ | attach PD charger; `pd 0 state`; sink negotiation + ≥2.5 A→`gale power on ap` | identical — validates the 4 PD fixes on real silicon |
| ADC | `adc` | identical channels, plausible live values |
| Stability | `panicinfo` + soak | no panics/crashes |
| AP boot | power-cycle | AP boots, device functions |

## Acceptance criteria
Equivalence confirmed ⟺ every test matches golden except the documented immaterial
deltas; **the AP boots and the device works**; no crashes over soak; the original is
**restored cleanly** (read-back sha256 match).

## Risks & mitigations
- **SWCLK=PA14 conflict** → connect-under-reset (NRST). No NRST → DFU (BOOT0) or a
  servo/`flash_ec` path.
- **Bricking** → RDP=0 SWD recovery + stock dump + DFU (triple net).
- **EC controls AP rails** → monitor the AP during power tests.
- **RDP accidentally set** → re-read option bytes after every write; never write them.
- **USB-PD test can power the AP** (the input-current-limit→AP-on path) → run deliberately.

## Minimum-viable vs full
Fast confidence check: **flash → console responds → raiden bridge reads the AP flash
identically → AP boots**. Those four cover the EC's core jobs; the full matrix + soak
is the rigorous sign-off.

## Prerequisite gap
The EC USB console + CH341A clip are already wired on `rpi4-gwifi`; **SWD is not** —
P0 (locate SWD/NRST + a probe) is the one new hardware step. If NRST/SWD prove
inaccessible, the plan degrades to the DFU path or a "can't reflash in place" finding.
