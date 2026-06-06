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
| `data/gale-optionbytes.bin` (see above) | — |
| `run_one.py` | Boots one image headless, reports final PC / instr count / halt + unmodeled-peripheral worklist. |
| `capture_console.py` | Boots one image, injects console commands, prints the USART1 transcript. |
| `battery.py` | Command-driven equivalence battery + trace-diff (console output), per-test PASS/XFAIL/FAIL. |
| `trace_diff.py` | **Execution-trace** equivalence — logs the MMIO register-access sequence of both images and compares by longest-common-prefix + order-independent multiset coverage (hardware-level, build-independent). |
| `peripherals/GaleDma.cs` / `GaleSpiFlash.cs` | DMA1 (UART-TX path) / W25Q64 (SPI bridge — readback gap, see file). |

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

**Equivalence result — command-driven tests only:**
`7 PASS` (version, sysinfo, taskinfo, gpioget, panicinfo, adc, gettime),
`2 XFAIL` documented deltas (chan, flashinfo), `0 unexpected FAIL`, no crashes.
This portion also caught a real reconstruction bug (`CONFIG_TASK_PROFILING`), which
was **fixed in the firmware**, not normalized away.

**NOT yet done — this is what the comparison does NOT cover (do not overread the
7 PASS):**
- **The comparison is console-output equivalence, not full execution-trace
  equivalence.** It diffs USART1 text only; no instruction / register / peripheral-
  access trace is captured or compared. Two images could diverge internally yet
  print identical tables. (Highest-priority depth gap.)
- **Raiden SPI bridge — not validated.** `GaleSpiFlash.cs` is wired to SPI2/PB12 and
  the model itself returns JEDEC `EF 40 17` correctly, BUT the EC reads back
  `ff0000`: gale's SPI is full-duplex DMA-driven and `GaleDma` does instant,
  independent per-channel transfers, so SPI TX/RX don't interleave (and the stock
  STM32SPI has no RX FIFO). No battery command yet exercises `spixfer`/`gale`.
- **USB enumeration — not modeled** (no STM32 USB-FS device model).
- **USB-PD negotiation — not modeled** (no COMP / bit-banged PD-PHY; PD async state
  is time-evolving and currently filtered out of the diff).
- **Power-sequencing, soak/stability, `gale` subcommands — not yet in the battery.**

**Independent verification (run on the command-driven portion):** tracing-
comprehensive = RED (the gaps above); traces-identical = GREEN (PASSes byte-
identical, XFAILs justified); no-shortcuts = GREEN (models RM0091-faithful, gaps
disclosed). Not yet 3× green.

**Next (toward green):** capture per-command instruction/peripheral-access traces
(make it a real execution-trace diff); SPI TX/RX DMA interleaving → wire `spixfer`
(raiden); `gale` subcommands + longer-settle taskinfo + soak; then USB-FS device
and COMP/PD-PHY for USB/PD; then re-run the 3-agent gate to convergence.
