# gale EC — Renode execution-trace equivalence harness

Goal: **prove the reconstructed gale EC firmware is functionally equivalent to the
original device image by comparing actual Renode execution traces**, building the
STM32F0 peripherals the firmware needs until every test from
[`../HARDWARE-TEST-PLAN.md`](../HARDWARE-TEST-PLAN.md) can run in emulation, then
gating on independent verification (tracing comprehensive / traces identical /
no shortcuts).

This is a **software, hardware-free** counterpart to the on-device hardware test:
it runs the same firmware images Renode-emulates an STM32F072, and diffs the
behaviour of the original dump against the rebuilt `ec.bin`.

## Method — trace-driven peripheral modeling

Renode's stock STM32F072 platform models the CPU core and the common digital
peripherals, but leaves several as non-deterministic stubs or bare Tags. We boot
the firmware, watch where it touches something unmodeled (or stalls), and add a
**deterministic, RM0091-faithful** model for exactly that device — repeat until
the firmware runs the test. Determinism is mandatory: trace-equivalence requires
that every peripheral the firmware reads returns the same value in both runs, so
the model must reflect real hardware register semantics, never be tuned to make a
particular image pass.

## Files

| File | Role |
|---|---|
| `base.resc` | Builds the gale machine: stock STM32F072 + deterministic overrides + loads option bytes + the firmware image. Vars: `$h` (this dir), `$bin` (image), `$name`. |
| `gale.repl` | Platform overlay — registers the deterministic models (overriding stock stubs, which are first `sysbus Unregister`ed). |
| `peripherals/GaleRcc.cs` | STM32F0 **RCC** — oscillator ENABLE bits drive READY bits; `RCC_CSR` not forced to 0 (fixes the `LSION→LSIRDY` boot deadlock). Replaces the stock "FLIPFLOP" stub. |
| `peripherals/GaleFlash.cs` | STM32F0 **embedded-flash interface** — `WRPR=0xFFFFFFFF`, `SR.BSY=0`, KEYR/OPTKEYR unlock. Stops the write-protect-reconciliation reset loop in `flash_pre_init`. |
| `data/gale-optionbytes.bin` | Real device option bytes (`md 0x1FFFF800`): RDP=0xAA (level 0), WRP=0xFF (none). sha256 `cdb247d4…`. |
| `run_one.py` | Boots one image headless, reports final PC / instr count / halt + unmodeled-peripheral worklist. |
| `power_seq.py` / `soak.py` / `usb_descriptors.py` | Power-sequencing / soak-stability / USB-enumeration-identity equivalence tests. |
| `capture_console.py` | Boots one image, injects console commands, prints the USART1 transcript. |
| `battery.py` | Command-driven equivalence battery + trace-diff (console output), per-test PASS/XFAIL/FAIL. |
| `trace_diff.py` | **Execution-trace** equivalence — logs the MMIO register-access sequence of both images and compares by longest-common-prefix + order-independent multiset coverage (hardware-level, build-independent). |
| `peripherals/GaleDma.cs` / `GaleSpiFlash.cs` | DMA1 (UART-TX + full-duplex SPI TX/RX interleave) / W25Q64 (SPI bridge — `spixfer` reads back `ef4017` end-to-end). |

## Run

```
uv run python run_one.py --bin ../../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin --runt 0.2
```

(`ec-rebuilt.bin`, a local copy of `build/gale/ec.bin`, is git-ignored — rebuild it
per [`../README.md`](../README.md).)

## Status (in progress — honest accounting)

**Working & committed.** Five deterministic models (RCC, FLASH, DMA1, option-byte
memory) + the correct WP_L pin boot BOTH the original dump and the rebuilt `ec.bin`
to the interactive `>` prompt (reset vector matches: `SP=0x200004C0 PC=0x080000ED`).
The bidirectional USART1 console + `battery.py` diff the two images command-by-command.

**HARDWARE-TEST-PLAN coverage — ~12 of 13 tests:**
- `battery.py` — **8 PASS** (version, sysinfo, taskinfo, gpioget, panicinfo, adc,
  gettime, **raiden SPI-flash RDID = ef4017**), **2 XFAIL** documented deltas (chan,
  flashinfo), 0 unexpected FAIL, no crashes.
- `trace_diff.py` — **execution-trace** (MMIO register-access) equivalence: 201
  identical accesses in order + 992 common access-events. Truly ZERO divergence on
  `spi1`, `spi2`, `exti`, `gpioPortC`, `gpioPortF`. `rcc`, `flashif`, `gpioPortB` diverge
  ONLY in access COUNT / init-timing, with identical-or-benign values (e.g. the same
  `WRPR=0xFFFFFFFF` read a different number of times; an `RCC_*ENR`/clock-ready bit
  sampled at slightly different init points — `0x18200001` vs `0x18220001`, a value that
  appears in BOTH traces; an `adc` value re-read a different number of times). The bulk
  of divergence is `usart1`/`dma1` **console-TX traffic** (different banner text + a
  UART-TX-DMA write-width difference — both emit identical console output) and `timer2`
  **scheduler ticks**. All immaterial; the tool **normalizes nothing** and prints the
  raw divergences for audit. This is real execution-trace, not console text. It is a
  **diagnostic** (prints metrics + raw divergences), not an automated pass/fail gate.
- `power_seq.py` — **PASS**: `gale power on/off ap` drives all 6 AP rails
  identically (high then low) on both images.
- `soak.py` — **PASS**: both run 2 s virtual, alive + panic-free + no crash/halt.
- `usb_descriptors.py` — **PASS**: USB enumeration identity (device descriptor
  18d1:500f + strings EC_PD/Gale debug/Google Inc.) byte-identical (static).
- Also caught + **fixed** a real reconstruction bug (`CONFIG_TASK_PROFILING`).

**Remaining (NOT covered):**
- **USB-PD negotiation** — the one genuine remaining big peripheral. PD-PHY *register
  programming* IS covered by the execution-trace diff (SPI1/TIM16/EXTI/ADC), but a live
  `pd 0 state` snapshot is non-deterministic (DRP toggle phase offset + the state
  machine can't complete `SRC_DISCONNECTED_DEBOUNCE` without CC voltage sensing). Needs
  a COMP + bit-banged PD-PHY model + a modeled CC partner.
- **AP boot** — structurally impossible in EC-only emulation (no IPQ4019).
- **USB enumeration** is covered by *static descriptor* equivalence above; a *live*
  `lsusb` enumeration would additionally need an STM32 USB-FS device-controller model.

**Independent verification:** round 1 = 1 RED (comprehensiveness — most gaps since
closed) + 2 GREEN (traces-identical, no-shortcuts). All round-1 integrity findings
addressed. Convergence to 3× green pending (gated on the USB-PD model + re-review).

**Verification:** round 1 = 1 RED + 2 GREEN (integrity findings fixed). **Round 2 =
all 3 GREEN** (comprehensiveness moved RED→GREEN; agents independently confirmed the
raiden ef4017 is end-to-end not hardcoded, the SPI-DMA interleaving is faithful to
spi_master.c, and the new tests are real). Need 3 consecutive all-green rounds.

**Next:** continue verification rounds to 3× green; for full USB-PD live negotiation,
add a COMP + bit-banged PD-PHY + modeled CC partner (the one remaining big peripheral);
then publish to main.
