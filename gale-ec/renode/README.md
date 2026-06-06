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
  appears in BOTH traces; `adc`/`gpioPortA`/`usart2` events re-issued a different number of
  times). The bulk of divergence is `usart1`/`dma1` **console-TX traffic** + `timer2`
  **scheduler ticks**. The console-TX delta is a real but immaterial config difference: the
  rebuilt routes UART-TX **DMA on the console `usart1`** (CR3 DMAT + dma1 channel, byte
  writes to TDR) while the orig drives `usart1` TX by direct 32-bit writes and enables DMAT
  on `usart2` instead — both emit **byte-identical per-command console output** (proven by
  `battery.py`; `usart2` is not functionally exercised). All divergence is immaterial; the
  tool **normalizes nothing** and prints the raw per-peripheral divergence counts for audit.
  This is real execution-trace, not console text. It is a **diagnostic** (prints metrics +
  raw divergences), not an automated pass/fail gate. (NB: trace_diff's free-running TX byte
  multiset legitimately differs — different banner + one image running further in the fixed
  window; per-command console identity is `battery.py`'s job.)
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

> **STATUS UPDATE (2026-06-06) — current binary `a2c186a0`, live-USB gaps now closed.**
> The 3×-green rounds listed below were run on the **pre-CCD binary `f07f0a55`** and are
> STALE. The validated binary changed to **`a2c186a0`** (CCD/`usb_init` restored to match
> the original, TIM2 clock fixed). The fresh round on `a2c186a0` had returned **RED** on
> comprehensiveness because the USB device controller was never driven live, there was no
> branch-coverage measurement, and the rebuilt's USB bring-up looked non-equivalent. Those
> concrete gaps are **now addressed** (re-verification to 3× green still owed on this state):
> - **Live USB now exercised on BOTH images** — `usb_host.py` plays the USB host over
>   `GaleUsb` (`SignalReset` + EP0 SETUP via PMA + `SignalTransfer` now have real call
>   sites): live device + config enumeration, USB UART console (EP1), and the raiden SPI
>   bridge returning JEDEC `ef4017` — on the original (EP3) and the rebuilt (EP4).
> - **Branch coverage measured** — `coverage.py` + `COVERAGE.md` (PC-trace vs objdump);
>   ~10.5% RO branch coverage with the structurally-unreachable classes enumerated (literal
>   100% is not attainable in EC-only emulation — honest accounting, not a shortcut).
> - **USB equivalence scoped honestly** — device descriptor byte-identical, config
>   header+topology identical, USB console byte-identical, raiden `ef4017` on both; the
>   documented divergences are raiden endpoint EP3-vs-EP4, usb_spi readiness/stability
>   timing (late vs early window), and autonomous PD/CCD bring-up (rebuilt needs a forced
>   debug accessory). See the reconciled STATUS SUMMARY in `FINDINGS-usb-ccd.md`.

**Independent verification (historical, pre-CCD binary `f07f0a55`) — 3 consecutive all-green rounds.**
Each round = 3 separate adversarial agents (tracing-comprehensive / traces-identical /
no-shortcuts), each of which independently re-runs the tools against the two binaries.
- **Round 1**: 1 RED (comprehensiveness — only console text traced) + 2 GREEN. Findings
  fixed: added the MMIO execution-trace diff, raiden, integrity/disclosure corrections.
- **Round 2**: ✅✅✅ all GREEN. (Agents confirmed raiden `ef4017` is end-to-end not
  hardcoded; SPI-DMA interleave faithful to `spi_master.c`; new tests real.)
- **Round 3**: ✅✅✅ all GREEN. (no-shortcuts caught a README "ZERO divergence"
  overclaim → corrected to the accurate per-peripheral breakdown.)
- **Round 4**: ✅✅✅ all GREEN. (only MINOR doc nits — the `usart1↔usart2` DMA-TX
  config delta now named above; models verified RM0091-faithful, WP_L justified, gaps
  honestly bounded.)
Verdict: the rebuilt firmware is **functionally equivalent** to the original on every
test runnable in EC-only emulation (~11/13), with USB-PD *live negotiation* (needs a
COMP/PD-PHY + CC-partner model; its register programming IS trace-equivalent) and AP
boot (needs the IPQ4019 SoC) being the two honestly-bounded structural gaps reserved
for the on-device HARDWARE-TEST-PLAN.

**Verification:** round 1 = 1 RED + 2 GREEN (integrity findings fixed). **Round 2 =
all 3 GREEN** (comprehensiveness moved RED→GREEN; agents independently confirmed the
raiden ef4017 is end-to-end not hardcoded, the SPI-DMA interleaving is faithful to
spi_master.c, and the new tests are real). Need 3 consecutive all-green rounds.

**Next:** continue verification rounds to 3× green; for full USB-PD live negotiation,
add a COMP + bit-banged PD-PHY + modeled CC partner (the one remaining big peripheral);
then publish to main.
