# gale EC firmware — state of the work

This is the **top-level status** of the effort to (1) reconstruct an open-source EC firmware for the
Google WiFi (gale) that is functionally equivalent to the shipped proprietary firmware, and (2) prove
that equivalence with a Renode emulation + branch-coverage harness. It is meant to be read on its own:
every table links out to the detailed documentation, but you should not need to open those docs to
understand where the project stands.

> **Scope.** The EC is an **STM32F072CB** (Cortex-M0, 128 KB flash) running a build of ChromeOS
> `platform/ec`. The captured reference is the on-device dump
> [`gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin`](gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin)
> (RO @ `0x08000000`, RW @ `0x08010000`). The reconstruction re-writes only the **`board/gale/`**
> files; everything else is upstream `platform/ec` at the pinned factory branch.

## At a glance

| Dimension | State |
|---|---|
| **Functional equivalence** | ✅ Equivalent on every path the harness exercises. All 10 ledger divergences resolved. See [EQUIVALENCE-STATUS.md](EQUIVALENCE-STATUS.md). |
| **Console commands** | **27 / 27** present; **25 / 27** byte-identical branch counts; handler bodies **84.2%** both-dirs covered. |
| **Branch coverage (captured fw)** | **2256 / 3328 = 67.8%** both-directions; **3134 / 3328 = 94.2%** reached. Verified by [`verify_named_report.py`](renode/verify_named_report.py). |
| **Renode emulation** | Both images boot to the console; **9** deterministic RM0091-faithful peripheral models. |
| **Build** | Reproducible & in-repo: [`build-firmware.sh`](build-firmware.sh) (pinned upstream + one tracked patch + `board/gale/`). |
| **Independent review** | Multiple 3-agent adversarial rounds, all-green, with falsification controls. |
| **Remaining** | Coverage tail is structurally-bounded (AP host-commands = dead code, HW-can't-fail returns, reset-only faults) + a reducible driveable set. See [WHY-UNCOVERED.md](renode/WHY-UNCOVERED.md). |

**Headline numbers are live-verifiable**, not asserted:
`cd gale-ec/renode && uv run --python .venv python verify_named_report.py` → `ALL CHECKS PASSED`.

---

## 1. What was reconstructed vs. what is upstream

The proprietary firmware = upstream `platform/ec` + a proprietary `board/gale/` overlay that was never
published. The reconstruction re-creates that overlay and pins the rest:

| Layer | Source | In this repo? |
|---|---|---|
| Board overlay | [`board/gale/`](board/gale/) — `board.c`, `board.h`, `usb_pd_policy.c`, `usb_pd_config.h`, `gpio.inc`, `build.mk`, `ec.tasklist` | ✅ tracked (the reconstruction) |
| One common-code patch | [`firmware-patches/0001-usb_pd-restore-PD_STATE_SNK_ACCESSORY.patch`](firmware-patches/) | ✅ tracked |
| Upstream EC | `platform/ec` @ `firmware-gale-8281.B` (`7c97ab0…`) | fetched (pinned) |
| Toolchain | `arm-none-eabi` **2016q3** | fetched (pinned URL) |

Reconstruction method, fidelity evidence and the two independent equivalence reviews:
[FIDELITY.md](FIDELITY.md) · [EQUIVALENCE-REVIEW-1.md](EQUIVALENCE-REVIEW-1.md) ·
[EQUIVALENCE-REVIEW-2.md](EQUIVALENCE-REVIEW-2.md). Build details: [BUILD.md](BUILD.md).

---

## 2. Equivalence verdict & divergence ledger

Every divergence ever found between the reconstruction and the dump is tracked to closure in
[EQUIVALENCE-STATUS.md](EQUIVALENCE-STATUS.md). Summary:

| # | Area | Status |
|---|---|---|
| 1 | `pd_select_polarity` COMP INSEL ref | ✅ fixed (byte-equiv) |
| 2 | `board_no_charger` dual-role vs comm-enable | ✅ fixed |
| 3 | `pd_tx_enable` CC sense-pin drive | ✅ fixed |
| 4 | `pd_custom_vdm` CCD VDM case | ✅ fixed |
| 5 | `PD_STATE_SNK_ACCESSORY` missing | ✅ fixed (the tracked patch) |
| 6 | `CONFIG_CASE_CLOSED_DEBUG` / USB absent | ✅ fixed (descriptors byte-identical) |
| 7 | raiden SPI endpoint EP4 vs captured EP3 | ✅ fixed + verified |
| 8 | source-path `timer_cancel` assert | characterized — emulation context-switch artifact; recon logic proven equivalent |
| 9 | `gale polarity` default 0 vs 1 | immaterial (arbitrary symmetric tie-break) |
| 10 | USB up at no-force boot | resolved — emulation artifact (phantom-accessory CC band) |

**Two intentional command-body deltas remain** — `version` (captured 6 branches / rebuilt 0) and
`flashwp` (5 / 6). Both live in upstream *common* code, not `board/gale/`: the shipped device was built
from a slightly different common-code revision than the pinned base. The reconstruction deliberately
keeps all changes board-confined, so these are **not** patched. Everything else matches (§4).

---

## 3. Peripherals — Renode model × proprietary use × reconstruction

Renode's stock STM32F072 platform models the CPU + common digital blocks but leaves several as
non-deterministic stubs or bare Tags. Each row below is a **deterministic, RM0091-faithful** model
added so the firmware runs; determinism is mandatory (trace-equivalence needs every peripheral read to
return the same value on both images). "Proprietary use" links to where that use is documented from the
dump; "reconstruction" links to the open-source driver that drives it identically.

| Peripheral | Renode model | How the proprietary fw uses it | Reconstruction driver + status |
|---|---|---|---|
| **RCC** (clocks) | [`GaleRcc.cs`](renode/peripherals/GaleRcc.cs) — ENABLE→READY, reset-cause, fixes `LSION→LSIRDY` boot deadlock | Clock/PLL bring-up + `LSI` for the RTC; reset-cause sampling | [`clock-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/clock-stm32f0.c) — ✅ boots identically |
| **Flash IF** | [`GaleFlash.cs`](renode/peripherals/GaleFlash.cs) — `WRPR=0xFFFFFFFF`, `BSY=0`, KEYR/OPTKEYR unlock, RDP 0 | `flash_pre_init` WP reconciliation, `flashinfo`/`flashwp`, vboot | [`flash-f.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/flash-f.c) — ✅ no reset loop |
| **DMA1** | [`GaleDma.cs`](renode/peripherals/GaleDma.cs) — instant block xfer; UART-TX + full-duplex SPI TX/RX interleave | Console UART TX; AP-flash SPI2 transfers; PD RX capture | [`dma.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/dma.c) — ✅ console + raiden work |
| **SPI2 (master)** | [`GaleSpi.cs`](renode/peripherals/GaleSpi.cs) — SR with `ForceBusy` knob (drives `spi_dma_wait` timeout arm) | AP external-flash bridge transport | [`spi_master.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/spi_master.c) — ✅ timeout path drivable |
| **SPI-flash (W25Q64)** | [`GaleSpiFlash.cs`](renode/peripherals/GaleSpiFlash.cs) — JEDEC `ef4017`, READ/RDSR, PB12-CS framed | The AP's 8 MiB NOR bridged over the EC (`spixfer`, raiden) | [`usb_spi.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb_spi.c) — ✅ `ef4017` end-to-end on both |
| **I2C1 (slave)** | [`GaleI2c.cs`](renode/peripherals/GaleI2c.cs) — slave-RX ISR sequence + AP host-command injector | AP↔EC host commands (`OAR1=0x803C`, addr `0x3C`) | [`i2c-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c) — ✅ transport restored |
| **ADC (12-bit)** | [`GaleAdc.cs`](renode/peripherals/GaleAdc.cs) — dynamic CC divider (role-switched Rd/Rp) | CC1/CC2 sensing for USB-PD attach; `adc` command | [`adc-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/adc-stm32f0.c) — ✅ drives DRP toggle |
| **EXTI + COMP** | [`GaleExti.cs`](renode/peripherals/GaleExti.cs) — `FireComp()` injects BMC edges → NVIC 12 | Comparator BMC edge capture → `pd_rx_handler` | [`usb_pd_phy.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb_pd_phy.c) — ✅ live PD RX ([STATUS-PD-PHY.md](renode/STATUS-PD-PHY.md)) |
| **USB FS device** | [`GaleUsb.cs`](renode/peripherals/GaleUsb.cs) — EPnR toggle/rc_w0 semantics + 1 KB PMA | Enumeration; USB UART consoles (if00/if01); raiden (if03) | [`usb.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb.c) — ✅ enumerates ([FINDINGS-usb-ccd.md](renode/FINDINGS-usb-ccd.md)) |

**Deliberately unmodeled** (benign — reads return 0, writes ignored; observed by [`run_one.py`](renode/run_one.py)):
`PWR`, `SYSCFG/COMP` cfg, `DBGMCU`, and `IWDG` (rebuilt only). None gate a functional path.
Peripherals are registered by the platform overlay [`gale.repl`](renode/gale.repl); the machine + option
bytes are built by [`base.resc`](renode/base.resc) (real device option bytes in
[`data/gale-optionbytes.bin`](renode/data/)).

---

## 4. Console commands — replication & test state

All **27** commands in the device's `__cmds` table are present in the reconstruction. "Branch parity"
compares the handler's conditional-branch count captured-vs-rebuilt (a structural-equivalence check,
[`compare_cmds.py`](renode/compare_cmds.py)); "handler coverage" is both-directions coverage of the
handler body from the campaign ([`cmdtable.py`](renode/cmdtable.py)). Handler-body totals: **215
branches, 181 both-dirs (84.2%), 12 / 27 handlers fully covered.**

| Command | Implemented in | Branch parity | Handler coverage |
|---|---|---|---|
| `adc` | [`common/adc.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/adc.c) | ✅ 8 = 8 | 5/8 (62%) |
| `chan` | [`common/console_output.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console_output.c) | ✅ 6 = 6 | 100% |
| `crash` | [`common/panic_output.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c) | ✅ 7 = 7 | 5/7 (71%) |
| `flashinfo` | [`common/flash.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c) | ✅ 11 = 11 | 9/11 (82%) |
| `flashwp` | [`common/flash.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c) | ⚠ 5 vs 6 (common-code rev) | 100% |
| `gale` | [`board/gale/board.c`](board/gale/board.c) | ✅ 4 = 4 | 100% |
| `gettime` | [`common/timer.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/timer.c) | ✅ 0 = 0 | 100% |
| `gpioget` | [`common/gpio_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c) | ✅ 4 = 4 | 100% |
| `gpioset` | [`common/gpio_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c) | ✅ 2 = 2 | 100% |
| `hash` | [`common/vboot_hash.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/vboot_hash.c) | ✅ 13 = 13 | 9/13 (69%) |
| `hcdebug` | [`common/host_command.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c) | ✅ 3 = 3 | 100% |
| `help` | [`common/console.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console.c) | ✅ 9 = 9 | 8/9 (89%) |
| `history` | [`common/console.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console.c) | ✅ 2 = 2 | 100% |
| `md` | [`common/memory_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/memory_commands.c) | ✅ 17 = 17 | 15/17 (88%) |
| `panicinfo` | [`common/panic_output.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c) | ✅ 2 = 2 | 1/2 (50%) |
| `pd` | [`common/usb_pd_protocol.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c) | ✅ 49 = 49 | 44/49 (90%) |
| `reboot` | [`common/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c) | ✅ 8 = 8 | 6/8 (75%) |
| `rw` | [`common/memory_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/memory_commands.c) | ✅ 13 = 13 | 100% |
| `spixfer` | [`common/spi_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/spi_commands.c) | ✅ 8 = 8 | 7/8 (88%) |
| `sysinfo` | [`common/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c) | ✅ 5 = 5 | 0/5 (0%) |
| `sysjump` | [`common/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c) | ✅ 7 = 7 | 6/7 (86%) |
| `syslock` | [`common/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c) | ✅ 0 = 0 | 100% |
| `taskinfo` | [`core/cortex-m0/task.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/task.c) | ✅ 0 = 0 | 100% |
| `tcpc` | [`common/usb_pd_tcpc.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_tcpc.c) | ✅ 12 = 12 | 100% |
| `typec` | [`driver/usb_mux.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/driver/usb_mux.c) | ✅ 12 = 12 | 9/12 (75%) |
| `version` | [`common/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c) | ⚠ 6 vs 0 (common-code rev) | 4/6 (67%) |
| `waitms` | [`common/timer.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/timer.c) | ✅ 2 = 2 | 100% |

Uncovered handler branches are almost all **value-conditioned** (need a specific argument value or
device state, not just a new argument shape) — enumerated with the exact missing condition in
[UNCOVERED-BY-FUNCTION.md](renode/UNCOVERED-BY-FUNCTION.md).

---

## 5. Core "base" / OS-level functionality

The parts of the firmware that are not a console command — the RTOS, boot, I/O plumbing, and PD stack.

| Subsystem | Source | Role | Coverage |
|---|---|---|---|
| **Scheduler / tasks** | [`core/cortex-m0/task.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/task.c) | Cooperative RTOS: 4 tasks (HOOKS, HOSTCMD, CONSOLE, PD_C0) | 39/52 (75%) |
| **Boot / vectors** | [`init.S`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/init.S), [`main.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/main.c) | Reset vector, C runtime, task bring-up | init.S 100% |
| **Fault / panic** | [`panic.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/panic.c), [`panic_output.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c) | Hard-fault handlers, panic record, `crash`/`panicinfo` | panic.c 24/34 (71%) |
| **Timers** | [`timer.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/timer.c), [`hwtimer32.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/hwtimer32.c) | Software timers on a 32-bit HW timer tick | hwtimer 100%, timer 52% |
| **Hooks / deferred** | [`hooks.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/hooks.c) | init/tick/freq-change hooks, deferred work | 47/62 (76%) |
| **Console core** | [`console.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console.c), [`console_output.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console_output.c) | Line edit, command dispatch, output channels | console 93% |
| **UART / USART** | [`uart_buffering.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c), [`usart-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usart-stm32f0.c) | Buffered console UART, DMA/interrupt TX/RX | uart_buffering 53% |
| **System / image** | [`common/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c), [`chip/stm32/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/system.c) | RO/RW image state, reset cause, jump tags, sysjump | 47% / 66% |
| **Flash stack** | [`common/flash.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c), [`flash-f.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/flash-f.c) | Program/erase/protect, write-protect, region info | 64% / 53% |
| **Verified boot** | [`vboot_hash.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/vboot_hash.c), [`sha256.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/sha256.c) | SHA-256 image hashing for RW verification | vboot 61%, sha256 100% |
| **USB device stack** | [`usb.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb.c), [`usb_console.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb_console.c), [`case_closed_debug.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/case_closed_debug.c) | Enumeration, USB serial consoles, CCD mux | usb 53%, ccd 100% |
| **USB-PD stack** | [`usb_pd_protocol.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c), [`usb_pd_tcpc.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_tcpc.c), [`usb_pd_phy.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb_pd_phy.c) | TCPMv1 state machine, bit-banged TCPC + PHY (gale *is* the TCPC) | proto 65%, tcpc 82%, phy 68% |
| **Board policy** | [`board/gale/board.c`](board/gale/board.c), [`board/gale/usb_pd_policy.c`](board/gale/usb_pd_policy.c), [`board/gale/usb_pd_config.h`](board/gale/usb_pd_config.h) | gale rails, GPIO/ADC wiring, sink-pref PD policy, CCD VDM | 81% / 64% / 100% |

The RTOS design (4-task table, stack sizes) and how it was recovered from the dump is in
[FIDELITY.md](FIDELITY.md).

---

## 6. All EC source files — usage, coverage & provenance

Every `.c`/`.S` file compiled into the gale RO image, with its role and **both-directions branch
coverage** of the captured firmware. All files are compiled into *both* firmwares (the reconstruction
mirrors the proprietary build); `board/gale/*` is the reconstructed overlay (in-repo), everything else
is upstream `platform/ec` at the pinned rev. Regenerate this table with
`uv run --python .venv python renode/perfile_coverage.py --md`. Totals: **62 files carry branches;
3328 branches; 2256 both-dirs (67.8%); 3134 reached (94.2%).**

| Source file | Role | Branches | Both-dirs | Reached | Reconstructed? |
|---|---|--:|--:|--:|---|
| [`common/usb_pd_protocol.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c) | USB-PD TCPMv1 state machine + `pd` console command | 722 | 468 (65%) | 669 (93%) | upstream (pinned) |
| [`common/console.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console.c) | Console core: line editing, dispatch, `help`/`history` | 188 | 174 (93%) | 188 (100%) | upstream (pinned) |
| [`common/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c) | System/image state, reset, jump tags; `sysinfo`/`sysjump`/`syslock`/`reboot`/`version` | 186 | 87 (47%) | 159 (85%) | upstream (pinned) |
| [`common/usb_pd_tcpc.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_tcpc.c) | Bit-banged TCPC (Type-C port controller) + `tcpc` command | 154 | 127 (82%) | 152 (99%) | upstream (pinned) |
| [`common/printf.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/printf.c) | Formatted-print core (vfnprintf) | 148 | 132 (89%) | 148 (100%) | upstream (pinned) |
| [`common/flash.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c) | Flash abstraction, protection, `flashinfo`/`flashwp` commands | 146 | 94 (64%) | 138 (95%) | upstream (pinned) |
| [`common/util.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/util.c) | libc-style string/mem utilities | 138 | 125 (91%) | 136 (99%) | upstream (pinned) |
| [`common/host_command.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c) | Host-command dispatch core + `hcdebug` command | 112 | 93 (83%) | 112 (100%) | upstream (pinned) |
| [`common/vboot_hash.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/vboot_hash.c) | Verified-boot SHA-256 image hashing + `hash` command | 112 | 68 (61%) | 106 (95%) | upstream (pinned) |
| [`chip/stm32/flash-f.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/flash-f.c) | STM32F0 flash program/erase/option-byte driver | 98 | 52 (53%) | 89 (91%) | upstream (pinned) |
| [`chip/stm32/usb_pd_phy.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb_pd_phy.c) | Bit-banged PD PHY: BMC edge decode, TX/RX DMA | 80 | 54 (68%) | 72 (90%) | upstream (pinned) |
| [`chip/stm32/usb.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb.c) | STM32F0 USB device controller driver | 72 | 38 (53%) | 58 (81%) | upstream (pinned) |
| [`common/uart_buffering.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c) | Buffered UART TX/RX + console snapshot | 64 | 34 (53%) | 59 (92%) | upstream (pinned) |
| [`common/hooks.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/hooks.c) | Deferred-work + hook (init/tick/freq) dispatcher | 62 | 47 (76%) | 62 (100%) | upstream (pinned) |
| [`common/memory_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/memory_commands.c) | `md` (mem dump) / `rw` (read-word) console commands | 60 | 56 (93%) | 60 (100%) | upstream (pinned) |
| [`common/gpio_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c) | `gpioget` / `gpioset` console commands | 56 | 44 (79%) | 56 (100%) | upstream (pinned) |
| [`core/cortex-m0/task.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/task.c) | Cooperative RTOS scheduler + `taskinfo` command | 52 | 39 (75%) | 52 (100%) | upstream (pinned) |
| [`board/gale/board.c`](board/gale/board.c) | Reconstructed gale board init, GPIO/ADC/SPI wiring, rails, `gale` cmd | 48 | 39 (81%) | 48 (100%) | in-repo |
| [`chip/stm32/dma.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/dma.c) | STM32F0 DMA driver (UART/SPI channels) | 48 | 26 (54%) | 42 (88%) | upstream (pinned) |
| [`chip/stm32/spi_master.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/spi_master.c) | STM32F0 SPI master (AP-flash bridge transport) | 48 | 22 (46%) | 48 (100%) | upstream (pinned) |
| [`chip/stm32/usb_console.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb_console.c) | USB serial console endpoint | 48 | 27 (56%) | 41 (85%) | upstream (pinned) |
| [`common/timer.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/timer.c) | Software timers, `gettime`/`waitms` commands | 46 | 24 (52%) | 42 (91%) | upstream (pinned) |
| [`chip/stm32/system.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/system.c) | STM32F0 system/reset/backup-registers | 44 | 29 (66%) | 44 (100%) | upstream (pinned) |
| [`chip/stm32/usb_spi.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb_spi.c) | raiden USB↔SPI bridge (AP-flash access over USB) | 42 | 14 (33%) | 35 (83%) | upstream (pinned) |
| [`common/usb_pd_policy.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_policy.c) | Shared PD policy helpers (request/VDM/DR checks) | 40 | 28 (70%) | 34 (85%) | upstream (pinned) |
| [`driver/usb_mux.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/driver/usb_mux.c) | USB SuperSpeed mux driver + `typec` command | 40 | 24 (60%) | 38 (95%) | upstream (pinned) |
| [`chip/stm32/i2c-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c) | STM32F0 I2C master/slave (host-command transport) | 36 | 14 (39%) | 28 (78%) | upstream (pinned) |
| [`core/cortex-m0/panic.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/panic.c) | Cortex-M0 fault/panic handlers | 34 | 24 (71%) | 32 (94%) | upstream (pinned) |
| [`chip/stm32/gpio-f0-l.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/gpio-f0-l.c) | STM32F0 GPIO alt-function/flags | 32 | 27 (84%) | 32 (100%) | upstream (pinned) |
| [`board/gale/usb_pd_policy.c`](board/gale/usb_pd_policy.c) | Reconstructed gale USB-PD policy (sink-pref, CCD VDM, power supply) | 28 | 18 (64%) | 28 (100%) | in-repo |
| [`common/console_output.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console_output.c) | Console output channels + `chan` command | 28 | 23 (82%) | 28 (100%) | upstream (pinned) |
| [`common/panic_output.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c) | Panic record formatting; `crash`/`panicinfo` commands | 26 | 16 (62%) | 26 (100%) | upstream (pinned) |
| [`common/queue.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/queue.c) | Lock-free byte/word FIFO queue | 24 | 4 (17%) | 20 (83%) | upstream (pinned) |
| [`chip/stm32/clock-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/clock-stm32f0.c) | STM32F0 RCC clock/PLL bring-up | 22 | 9 (41%) | 21 (95%) | upstream (pinned) |
| [`chip/stm32/usb-stream.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb-stream.c) | USB stream endpoint plumbing | 20 | 4 (20%) | 20 (100%) | upstream (pinned) |
| [`common/gpio.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio.c) | GPIO name table + common accessors | 18 | 10 (56%) | 18 (100%) | upstream (pinned) |
| [`common/sha256.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/sha256.c) | SHA-256 implementation (used by vboot_hash) | 18 | 18 (100%) | 18 (100%) | upstream (pinned) |
| [`chip/stm32/adc-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/adc-stm32f0.c) | STM32F0 12-bit ADC driver | 16 | 5 (31%) | 14 (88%) | upstream (pinned) |
| [`common/adc.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/adc.c) | ADC abstraction + `adc` console command | 16 | 10 (62%) | 16 (100%) | upstream (pinned) |
| [`common/spi_commands.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/spi_commands.c) | `spixfer` SPI-transfer console command | 16 | 14 (88%) | 16 (100%) | upstream (pinned) |
| [`chip/stm32/gpio.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/gpio.c) | STM32F0 GPIO config/IRQ | 14 | 9 (64%) | 13 (93%) | upstream (pinned) |
| [`chip/stm32/hwtimer32.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/hwtimer32.c) | 32-bit hardware timer (scheduler tick) | 12 | 12 (100%) | 12 (100%) | upstream (pinned) |
| [`chip/stm32/usart-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usart-stm32f0.c) | STM32F0 USART variant glue | 12 | 4 (33%) | 6 (50%) | upstream (pinned) |
| [`driver/tcpm/stub.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/driver/tcpm/stub.c) | TCPM stub (gale IS the TCPC) + `tcpm_init` | 12 | 8 (67%) | 12 (100%) | upstream (pinned) |
| [`board/gale/usb_pd_config.h`](board/gale/usb_pd_config.h) | Reconstructed gale PD-PHY config (COMP refs, TX timing, CC pins) | 10 | 10 (100%) | 10 (100%) | in-repo |
| [`common/clz.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/clz.c) | Count-leading-zeros helper | 10 | 10 (100%) | 10 (100%) | upstream (pinned) |
| [`chip/stm32/usart_tx_interrupt.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usart_tx_interrupt.c) | USART TX-interrupt path | 8 | 3 (38%) | 8 (100%) | upstream (pinned) |
| [`common/queue_policies.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/queue_policies.c) | Queue add/remove notification policies | 8 | 4 (50%) | 8 (100%) | upstream (pinned) |
| [`common/shared_mem.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/shared_mem.c) | Shared scratch-memory allocator | 8 | 8 (100%) | 8 (100%) | upstream (pinned) |
| [`chip/stm32/uart.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/uart.c) | STM32F0 UART low-level | 6 | 2 (33%) | 6 (100%) | upstream (pinned) |
| [`common/case_closed_debug.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/case_closed_debug.c) | Closed-case-debug (CCD) USB endpoint mux | 6 | 6 (100%) | 6 (100%) | upstream (pinned) |
| [`core/cortex-m0/div.S`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/div.S) | Software divide (asm) | 6 | 6 (100%) | 6 (100%) | upstream (pinned) |
| [`core/cortex-m0/init.S`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/init.S) | Reset vector + startup (asm) | 6 | 6 (100%) | 6 (100%) | upstream (pinned) |
| [`chip/stm32/flash-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/flash-stm32f0.c) | STM32F0 flash geometry glue | 4 | 4 (100%) | 4 (100%) | upstream (pinned) |
| [`chip/stm32/usart_rx_interrupt-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usart_rx_interrupt-stm32f0.c) | USART RX-interrupt path | 4 | 0 (0%) | 2 (50%) | upstream (pinned) |
| [`chip/stm32/crc_hw.h`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/crc_hw.h) | Hardware CRC unit inline helpers | 2 | 0 (0%) | 2 (100%) | upstream (pinned) |
| [`chip/stm32/usart.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usart.c) | USART baud/config | 2 | 0 (0%) | 2 (100%) | upstream (pinned) |
| [`chip/stm32/usb-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/usb-stm32f0.c) | STM32F0 USB device init/PMA glue | 2 | 0 (0%) | 2 (100%) | upstream (pinned) |
| [`common/main.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/main.c) | EC entry point / task bring-up | 2 | 1 (50%) | 2 (100%) | upstream (pinned) |
| [`core/cortex-m0/atomic.h`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/atomic.h) | Atomic ops inline helpers | 2 | 0 (0%) | 0 (0%) | upstream (pinned) |
| [`core/cortex-m0/thumb_case.S`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/thumb_case.S) | Switch-table thunks (asm) | 2 | 0 (0%) | 2 (100%) | upstream (pinned) |
| [`include/task.h`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/include/task.h) | Task API inline helpers | 2 | 2 (100%) | 2 (100%) | upstream (pinned) |
------------------------------------------------------------------------
TOTAL  files=62  branches=3328  both-dirs=2256 (67.8%)  reached=3134 (94.2%)

**Compiled but branch-free** (config/data tables, pure-linear libc/asm, or fully inlined — present in
both firmwares, nothing to cover): `common/fmap.c`, `common/version.c`, `chip/stm32/gpio-stm32f0.c`,
`chip/stm32/jtag-stm32f0.c`, `chip/stm32/usart_rx_dma.c`, `chip/stm32/usart_tx_dma.c`,
`chip/stm32/usb_endpoints.c`, `chip/stm32/watchdog.c`,
`core/cortex-m0/{cpu,switch,ldivmod,lmul,uldivmod,watchdog}.c`.

---

## 7. Renode harness — models, scenes & verification tests

The emulation is validated by tests that either **diff the two firmwares** or **falsify** a claimed
result (edit a model so a "pass" must change). Full method: [renode/README.md](renode/README.md).

| Component | File | What it is / does | Verified by |
|---|---|---|---|
| Machine build | [`base.resc`](renode/base.resc) | STM32F072 + deterministic overrides + option bytes + image load | boots both images |
| Platform overlay | [`gale.repl`](renode/gale.repl) | Registers the 9 models (un-registers stock stubs) | — |
| 9 peripheral models | [`peripherals/*.cs`](renode/peripherals/) | RM0091-faithful RCC/Flash/DMA/SPI/SPI-flash/I2C/ADC/EXTI/USB (§3) | trace/battery/usb tests |
| Option bytes | [`data/gale-optionbytes.bin`](renode/data/) | Real device OB (RDP 0xAA, WRP 0xFF) | boot parity |
| Boot smoke test | [`run_one.py`](renode/run_one.py) | Headless boot; PC/instr/halt + unmodeled-peripheral worklist | both → console, no halt |
| Command battery | [`battery.py`](renode/battery.py) | Per-command console diff of the two images | 8 PASS, 2 XFAIL, 0 fail |
| Execution-trace diff | [`trace_diff.py`](renode/trace_diff.py) | MMIO register-access sequence equivalence (build-independent) | 201 in-order + 992 common; deltas immaterial |
| Power sequencing | [`power_seq.py`](renode/power_seq.py) | `gale power on/off ap` drives all 6 rails identically | PASS |
| Soak stability | [`soak.py`](renode/soak.py) | 2 s virtual run, alive + panic-free | PASS |
| USB identity | [`usb_descriptors.py`](renode/usb_descriptors.py) | Device/config descriptor + strings byte-identical | PASS |
| Live USB host | [`usb_host.py`](renode/usb_host.py) | Drives enumeration + USB UART + raiden `ef4017` live | PASS both (EP3/EP4) |
| Live PD partner | [`pd_inject.py`](renode/pd_inject.py) + [`pd_encode.py`](renode/pd_encode.py) | BMC/4b5b/CRC-encodes a CC-partner; drives real PD RX/decode | Source_Cap decoded, Request TX'd |
| Console capture | [`capture_console.py`](renode/capture_console.py) | Boots one image, injects commands, prints USART1 transcript | — |

Falsification controls (edit a copy, confirm the result changes): raiden JEDEC → sentinel propagates
end-to-end (not a constant); altered PD header → firmware returns the *changed* value; negative control
(rebuilt without the forced debug accessory) fails cleanly. See [renode/README.md](renode/README.md)
§ independent verification.

---

## 8. Analysis & coverage tooling

Everything under [`gale-ec/renode/`](renode/) is self-contained (vendored ELFs +
system `arm-none-eabi-*` binutils; no external paths). Families:

| Tool / family | Count | Purpose |
|---|---|---|
| [`rda.py`](renode/rda.py) | 1 | Recursive-descent ARMv6-M Thumb disassembler — enumerates the **branch denominator** (3328) |
| [`coverage_captured.py`](renode/coverage_captured.py) | 1 | External-stimulus Renode campaign → executed edges (captured fw) |
| [`fcall.py`](renode/fcall.py) + `fcall_*.py` | 1 + 18 | GDB-stub **direct function-call** harness + per-subsystem call sweeps |
| `cov_*.py` | 65 | Console/PD/flash/DMA/I2C/USB **stimulus levers** (each drives a specific branch family) |
| [`pd_encode.py`](renode/pd_encode.py) / [`pd_decode.py`](renode/pd_decode.py) / [`pd_inject.py`](renode/pd_inject.py) | 3 | USB-PD BMC/4b5b/CRC codec + live message injector |
| [`combine_coverage.py`](renode/combine_coverage.py) | 1 | Unions all campaign + sweep edges → `both-dirs` over the rda denominator |
| [`map_funcs.py`](renode/map_funcs.py) / [`symbolize.py`](renode/symbolize.py) | 2 | Captured→rebuilt function fingerprint match (names + DWARF source lines) |
| [`compare_cmds.py`](renode/compare_cmds.py) | 1 | Captured-vs-rebuilt **command-set + branch-count** equivalence (§4) |
| [`cmdtable.py`](renode/cmdtable.py) | 1 | Per-console-command coverage from the `__cmds` table |
| [`perfile_coverage.py`](renode/perfile_coverage.py) | 1 | Per-source-file coverage roll-up (§6; generates the table) |
| [`classify.py`](renode/classify.py) / [`classify_src.py`](renode/classify_src.py) | 2 | Bin uncovered branches by structural category / by source line |
| [`build_named_report.py`](renode/build_named_report.py) / [`uncovered_report.py`](renode/uncovered_report.py) / [`gen_why_uncovered.py`](renode/gen_why_uncovered.py) | 3 | Generate [UNCOVERED-BY-FUNCTION.md](renode/UNCOVERED-BY-FUNCTION.md) / [WHY-UNCOVERED.md](renode/WHY-UNCOVERED.md) |
| [`verify_named_report.py`](renode/verify_named_report.py) / [`rda_validate.py`](renode/rda_validate.py) | 2 | Independently re-derive & **verify** every reported number (partition, mnemonic, provenance) |
| [`concolic_solve.py`](renode/concolic_solve.py) | 1 | Solve branch input conditions for hard-to-reach arms |

(~123 Python tools + 9 C# models total; the `cov_*`/`fcall_*` families are individually small,
single-purpose stimulus scripts unioned by `combine_coverage.py`.)

---

## 9. Coverage ceiling & remaining work

Literal 100% both-directions is **not** reachable in EC-only emulation; the uncovered remainder is
enumerated and classified per branch (not hand-waved). Categories, from
[WHY-UNCOVERED.md](renode/WHY-UNCOVERED.md) / [COVERAGE.md](renode/COVERAGE.md):

| Class | Why unreachable / hard | Reducible? |
|---|---|---|
| PD state machine (R1, ~276) | Needs specific msg type+field while in an exact `pd_task` state | partly — needs richer live PD contracts |
| PD PHY bit-decode (R2, ~53) | Needs malformed BMC/4b5b/CRC bitstreams below the message layer | yes — extend PHY to feed raw edges |
| Peripheral-model gaps (R3, ~258) | Branch gated on a status/error event the model never generates | yes — **emulator work**, largest addressable bucket |
| Boot/init alt-precondition (R4, ~37) | `*_init` runs once; other arm needs a different reset/clock/OB state | partly — alternate boot presets |
| Flash fault/protect (R5, ~85) | WRPRT/PGERR/protect gates need specific WRP/OPTB state | partly — fault injection knobs |
| System/image/jump (R6, ~114) | Jump-tag magic/version/layout paths | partly — crafted sysjump/reboot |
| AP host-commands | **Unreachable dead code** — gale compiles no host-command transport | no (structural) |
| HW-can't-fail returns | `EC_ERROR_*` for deterministically-perfect models | no (structural) |
| Reset-only faults | Taking the other arm resets the CPU | no (structural) |

Rigorously-proven dead code is catalogued in [DEAD-CODE-PROVEN.md](renode/DEAD-CODE-PROVEN.md).
On-device tests reserved for real hardware (AP boot, full PD SNK_READY contract) are in
[HARDWARE-TEST-PLAN.md](HARDWARE-TEST-PLAN.md).

---

## 10. Reproduce & verify

```sh
cd gale-ec
./build-firmware.sh                        # build ec.bin + refresh renode/data/rebuilt-*.elf
cd renode
uv venv .venv && uv pip install --python .venv -r requirements.txt
uv run --python .venv python compare_cmds.py       # command-set equivalence (27=27)
uv run --python .venv python combine_coverage.py    # rebuild the coverage union
uv run --python .venv python verify_named_report.py # ALL CHECKS PASSED (2256/3328)
uv run --python .venv python cmdtable.py            # per-command coverage
uv run --python .venv python perfile_coverage.py    # per-file coverage
uv run --python .venv python run_one.py --bin ../../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin --runt 0.2
```

## Document map

- **Equivalence:** [EQUIVALENCE-STATUS.md](EQUIVALENCE-STATUS.md) · [EQUIVALENCE-REVIEW-1.md](EQUIVALENCE-REVIEW-1.md) · [EQUIVALENCE-REVIEW-2.md](EQUIVALENCE-REVIEW-2.md) · [FIDELITY.md](FIDELITY.md)
- **Coverage:** [renode/COVERAGE.md](renode/COVERAGE.md) · [renode/WHY-UNCOVERED.md](renode/WHY-UNCOVERED.md) · [renode/UNCOVERED-BY-FUNCTION.md](renode/UNCOVERED-BY-FUNCTION.md) · [renode/DEAD-CODE-PROVEN.md](renode/DEAD-CODE-PROVEN.md)
- **Harness:** [renode/README.md](renode/README.md) · [renode/STATUS-PD-PHY.md](renode/STATUS-PD-PHY.md) · [renode/FINDINGS-usb-ccd.md](renode/FINDINGS-usb-ccd.md)
- **Build / hardware:** [BUILD.md](BUILD.md) · [HARDWARE-TEST-PLAN.md](HARDWARE-TEST-PLAN.md)
- **R146 forward-port spike (separate effort):** [REBASE-PLAN.md](REBASE-PLAN.md) · [REBASE-GAP-ANALYSIS.md](REBASE-GAP-ANALYSIS.md) · [SPIKE-A-LEGACY-TAG.md](SPIKE-A-LEGACY-TAG.md) · [SPIKE-B-ZEPHYR.md](SPIKE-B-ZEPHYR.md)
