# Rebasing the gale EC firmware onto the latest chromeos-ec stack — plan & feasibility

> Companion to [`README.md`](README.md) / [`FIDELITY.md`](FIDELITY.md). Evidence for the
> findings below is in [`REBASE-GAP-ANALYSIS.md`](REBASE-GAP-ANALYSIS.md).

## Decisive finding (gap-analysis spike, current `platform/ec` HEAD `37850ff`, 2026-06-04)

**A forward-port onto legacy `main` is not possible — the legacy ARM/STM32 firmware
stack has been excised from the tree.** Concretely:
- `board/` contains only `host` + `hyperdebug`; **zero** boards with `CHIP_VARIANT:=stm32f0`. `make BOARD=servo_micro` → "unable to locate BOARD".
- **`chip/stm32` deleted**, **`core/cortex-m0` deleted** — there is no `-mcpu=cortex-m0` build path at all (smoking gun: `common/build.mk` still guards `ifneq ($(CORE),cortex-m0)` for a core that no longer exists). All `STM32_*` register defs went with `chip/stm32/registers.h`.
- **TCPMv1 deleted** — `CONFIG_USB_PD_TCPMV1` is still in `config.h` and the policy-hook prototypes survive in `usb_pd.h`, but `common/usb_pd_protocol.c` (the state machine gale's hooks plug into) is gone and no board enables it. Modern PD is the TCPMv2 layered SM in `common/usbc/`.
- **`usb_spi` raiden bridge deleted** — `common/usb_spi.c` / `include/usb_spi.h` / `USB_SPI_CONFIG` / `usb_spi_board_enable` gone (`CONFIG_USB_SPI` symbol is vestigial). `CONFIG_STREAM_USART*` similarly hollowed.
- **The trap:** surviving `config.h` symbols (`TCPMV1`, `USB_SPI`, `STREAM_USART`) mask all of this until **link time**.
- **Intact / trivial:** `include/gpio.wrap` (GPIO/ALTERNATE/PIN_MASK), `include/task_filter.h` (TASK_ALWAYS/NOTEST), `util/getversion.sh`. CONFIG renames are mechanical (`SPI_MASTER→SPI_CONTROLLER`, `I2C_SLAVE→I2C_PERIPHERAL`, `USB_PD_PORT_COUNT→USB_PD_PORT_MAX_COUNT`).

**Conclusion: a "rebase" onto `main` is really a *re-port*, and 3 of its 6 subsystems
are hard blockers sharing one root cause (the legacy ARM stack is gone).**

## The realistic targets

| Target | What it is | Feasible? | "Latest"? |
|---|---|---|---|
| **A. Stay on `firmware-gale-8281.B`** (2016) | the current certified base | ✅ (done) | ❌ |
| **A′. Last legacy *tag* with the ARM stack** | rebase `board/gale` onto the most-recent legacy commit that still shipped `chip/stm32` + `core/cortex-m0` + TCPMv1 | ✅ same architecture, fits 128 KB/16 KB, picks up years of legacy fixes | partial (latest code that can *build* gale) |
| **B. Zephyr EC** | re-implement gale as a Zephyr cros-ec board | ⚠️ **feasibility-gated** | ✅ the only actively-maintained path |

## The verification spine (the asset that de-risks any re-port)
The certified legacy `board/gale` + the original dump + the differential test harness
(see `HARDWARE-TEST-PLAN.md`) is a **behavioral oracle**. For *any* target: port a
subsystem → build → **diff against golden** → independent-review → repeat. The hardest
question of a re-port — "did I preserve behavior?" — is answered mechanically.

## Recommended sequence (two cheap spikes decide everything)

1. **Pin the last-good legacy tag** (defines A′). On a full (non-shallow) clone,
   `git log --oneline -- chip/stm32 core/cortex-m0 common/usb_pd_protocol.c` to find the
   removal commits; the parent of the earliest removal is the newest legacy base that can
   build gale. Cost: ~1 hr.
2. **Zephyr footprint/feasibility spike** (defines B). Build a minimal cros-ec **Zephyr**
   image for the closest STM32 target and measure flash/RAM against gale's **128 KB / 16 KB**;
   determine whether the cros-ec Zephyr shim supports **Cortex-M0 / STM32F0** at all and
   whether **TCPMv2 + USB device + the kernel** fit that budget. This is the make-or-break:
   gale's legacy image already uses 64 KB RO + 64 KB RW, and Zephyr+TCPMv2 is heavy.
   Cost: ~0.5–1 day. **Do this before any Zephyr porting.**

3. **Decide:** if B fits → do the Zephyr port (the future); if B does not fit → A′ is the
   practical "as-modern-as-the-silicon-allows," and we **document that true-latest (Zephyr)
   does not fit gale's STM32F072** — an honest, defensible outcome.

## Plan B — Zephyr port (only if the footprint spike passes)
- **GPIOs:** `gpio.inc` (27 signals + 7 ALTERNATE) → a devicetree `.dts` overlay (`gpio-keys`/`named-gpios` + pinctrl).
- **Config:** `board.h` CONFIG → Kconfig + devicetree; `ec.tasklist` → the Zephyr cros-ec task shim / threads.
- **USB-PD (largest):** re-express the policy on **TCPMv2** (`common/usbc/`), and write a **Zephyr TCPC driver** for gale's bit-banged STM32F0 PHY (SPI1 + TIM16 + COMP) — there may be no existing STM32F0 cros-ec TCPC, so this is likely new.
- **raiden bridge:** re-implement `usb_spi` on Zephyr USB (or the modern `usb_spi` if it exists in Zephyr).
- **Board glue:** the `gale` command + AP power sequencing as Zephyr shell commands + hooks.
- Each step verified against the oracle; build with `zmake`/west.

## Plan A′ — last-legacy-ARM-tag forward-port (the pragmatic path)
- Rebase `board/gale` onto the pinned tag; apply the mechanical CONFIG renames; build with
  that tag's toolchain (likely a newer arm-none-eabi than 2016q3 — modernizes the toolchain).
- Re-run the oracle diff + the hardware test. Lower risk; same architecture; fits the chip.

## Honest bottom line
The literal goal ("rebase onto latest `main`") isn't achievable — upstream removed the ARM
firmware stack. The achievable outcomes are **A′** (newest legacy-ARM code that still builds
gale — feasible now) and **B** (Zephyr — the genuine latest, *if* it fits 128 KB/16 KB, which
is the open question). The two spikes above resolve the choice cheaply; the equivalence oracle
makes whichever port we choose verifiable.
