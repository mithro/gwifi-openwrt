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

## Run

```
uv run python run_one.py --bin ../../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin --runt 0.2
```

(`ec-rebuilt.bin`, a local copy of `build/gale/ec.bin`, is git-ignored — rebuild it
per [`../README.md`](../README.md).)

## Status (in progress)

**Done — boot bring-up.** With the RCC + FLASH + option-byte models, the firmware
boots cleanly past `system_pre_init` and `flash_pre_init` (no boot-reset loop) and
reaches console/USB initialization and the banner print (`system_get_build_info`,
`uart_vprintf`, `watchdog_init`). Reset vector matches the dump
(`SP=0x200004C0 PC=0x080000ED`). Remaining unmodeled accesses are deterministic
Tags (PWR/SYSCFG/DBGMCU, all return 0) — modeled later only if a test needs a
non-zero reply.

**Next.**
1. **DMA1** — the UART console TX and other paths use DMA; the stock DMA is a
   Python hack that throws (`'sysbus' is not defined`) on first use. Replace with
   a real STM32F0 DMA model (mem↔periph channels) — required to capture console
   output and to avoid the crash.
2. **Interrupt sources** (SysTick / timers) so the EC scheduler runs its normal
   loop instead of freezing in WFI.
3. **USART1 console** bidirectional (inject commands, capture responses).
4. **ADC**, **COMP + bit-banged PD PHY**, **USB-FS device**, **W25Q64 on the
   raiden bridge** — as the test battery reaches them.
5. **Test battery** mirroring `../HARDWARE-TEST-PLAN.md`, **trace-diff harness**,
   and the **independent 3×-green verification gate**.
