# SPIKE B — Can the cros-ec **Zephyr** EC host "gale" on its real silicon?

Feasibility analysis. No build was run (a full Zephyr `west`/`zmake` env is
heavy: `west`, `zmake`, the Zephyr SDK / `arm-none-eabi` toolchain and the
`hal_stm32`/`cmsis` modules are not installed here — only `cmake`+`ninja` and the
2016 ARM GCC for legacy ECOS builds are present). Findings are grounded in the
current platform/ec HEAD tree + measured legacy artifacts. Where a number could
not be measured locally it is cited from the in-tree documentation or upstream
Zephyr SoC facts and flagged as such.

## TL;DR — VERDICT

> ## **DOES NOT FIT** (as-is) — and a port is **MAJOR**, effectively a
> from-scratch Zephyr chip+stack bring-up, not a board add.
>
> gale = STM32F072CB: **Cortex-M0 (ARMv6-M), 128 KB flash (64 RO + 64 RW), 16 KB RAM**.
>
> Three independent hard findings, any one of which is disqualifying for a
> drop-in port:
> 1. **No Cortex-M0 / STM32F0 target exists** in cros-ec Zephyr. The entire
>    STM32 shim is gated to `SOC_SERIES_STM32F4X`/`STM32G4X`/`STM32H743` (Cortex-M4/M7).
>    The smallest STM32 Zephyr target is **bloonchipper = STM32F412 (Cortex-M4F,
>    1 MB flash, 256 KB RAM)** — ~8× the flash, ~16× the RAM of gale.
> 2. **No bit-banged STM32F0 PD PHY / TCPMv1 anywhere in Zephyr.** Every Zephyr
>    USB-C port is an *external* TCPC/PDC chip referenced from devicetree. gale's
>    "the MCU **is** the TCPC" model (TCPMv1 + `TCPM_STUB` + COMP/DAC/EXTI/SPI1/TIM
>    bit-bang) has **zero** counterpart. TCPMv1 itself does not exist in `zephyr/`.
> 3. **Footprint:** the smallest-RAM EC silicon cros-ec Zephyr is *documented* to
>    support is **60 KiB RAM / 1 MiB flash** (ITE IT81202/IT81302); smallest flash
>    is **512 KiB**. gale has **16 KiB / 128 KiB** with a **64 KiB per-image**
>    budget. No measured Zephyr image fits 64 KiB/16 KiB; the evidence points
>    strongly to "won't fit," and what's *measurable* is the absence of any target
>    even close to this size.
>
> The one part that is genuinely fine: gale's app shape is tiny and ordinary —
> **4 tasks** (HOOKS, HOSTCMD, CONSOLE, PD_C0), **27 GPIOs**, 1 sink PD port.
> The blocker is never the application; it is the **silicon class + the PD-PHY +
> the bridge**, none of which the Zephyr EC provides for this chip.

---

## Evidence trees & versions

- **Port TO (target):** `/home/tim/local/gwifi/tmp/ec-main` @ `main`, HEAD
  `37850ff4dfdad2a8062702be5a3591d195f4c9c1`, dated **2026-06-04** (shallow
  `--depth 1`; deep history / deletion commits not visible). Contains the Zephyr
  EC under `zephyr/`.
- **Port FROM (gale source):** `/home/tim/local/gwifi/tmp/ec` @ gale factory
  branch, `board/gale/` (STM32F072CB). Confirmed 27 GPIOs, 4 tasks.
- **Legacy stack reference:** `/home/tim/local/gwifi/tmp/ec-legacy` still carries
  `chip/stm32/usb_pd_phy.c` (685 LOC) and `chip/stm32/usb_spi.c` (998 LOC) — the
  two drivers a Zephyr port would have to recreate.
- **Shipping gale image:** `gale-ec-gale_v1.1.5337-...bin` = **131072 B = 128 KB**
  (= 64 KB RO + 64 KB RW), confirming the hard flash split.

This spike is the natural sequel to `regale/REBASE-GAP-ANALYSIS.md`, which already
established that the **legacy (non-Zephyr) `main`** tree deleted all STM32/
Cortex-M0/TCPMv1/usb_spi support ("effectively a re-port"). SPIKE B answers: *is
the Zephyr EC a viable home instead?* Answer: not without major new work.

---

## Q1 — Does cros-ec Zephyr support Cortex-M0 / STM32F0 at all?

**No.** STM32 *is* supported in Zephyr cros-ec, but only the Cortex-M4/M7 families.

What exists:
- `zephyr/shim/chip/stm32/` — `clock.c` (a no-op mock), `debug.c`,
  `include/flash_chip.h`. The arch-specific code is gated:
  - `shim/chip/stm32/debug.c:10` → `#if defined(CONFIG_SOC_SERIES_STM32F4X) || defined(CONFIG_SOC_SERIES_STM32G4X)` … `#elif CONFIG_SOC_STM32H743XX`
  - `drivers/cros_flash/cros_flash_stm32_backend.c:87` → `#ifdef CONFIG_SOC_SERIES_STM32F4X`
  - `drivers/cros_flash/Kconfig:135` → `depends on CROS_FLASH_BACKEND_STM32 && SOC_SERIES_STM32F4X`
  - `test/hwtest/src/rollback.c:26` → `#if defined(CONFIG_SOC_STM32F412CX)`
  → i.e. the STM32 flash backend, cros-system, and debug paths are **F4-only**.
    None compile for STM32F0. STM32F0's flash controller, RCC, and option-byte
    layout are different from F4 and would need new backend code.
- **The only STM32 program is `zephyr/program/fpmcu/bloonchipper/`** (the
  fingerprint MCU). `soc.dtsi` includes `<cros/st/stm32.dtsi>`; the board is
  `google_dragonclaw` (STM32F412), pulled from **upstream Zephyr** via
  `variant_modules=["hal_stm32", "cmsis_6"]` (see `program/fpmcu/BUILD.py:35,37`).
  STM32F412 = **Cortex-M4F, 256 KB RAM, 1 MB flash**. RO≈128 KB (`0x20000`),
  RW≈640 KB (`0xa0000`) per `bloonchipper.dts`.

The **EC-defined** Zephyr boards (`zephyr/boards/google/`) are exactly:
`it8xxx2, mec172x, npcx7, npcx9, realtek` — **no STM32 at all**. STM32 boards live
upstream. So enabling gale's STM32F072 means: (a) upstream Zephyr must define an
`st,stm32f072xb` SoC + a board for it — it does upstream in general (e.g.
`nucleo_f072rb`), but **no such board is wired into cros-ec**, and (b) the cros-ec
STM32 shim/flash/system drivers above would all need F0 variants written.

Cortex-M0 awareness in the EC tree is **incidental, not enablement**:
- `zephyr/CMakeLists.txt:336` → `if (NOT DEFINED CONFIG_CPU_CORTEX_M0)` only
  toggles a curve25519 asm variant.
- `zephyr/test/hwtest/src/panic.c:58` → `if (IS_ENABLED(CONFIG_CPU_CORTEX_M0))` in a
  test.
- These are leftover/defensive guards (ARMv6-M lacks some ARMv7-M instructions);
  **no board, SoC, program, or shim selects an M0 part.**

### Smallest existing STM32 cros-ec Zephyr target
| Target | Core | Flash | RAM | Notes |
|---|---|---|---|---|
| **bloonchipper** (STM32F412) | Cortex-M4F | 1 MB | 256 KB | the *only* STM32 Zephyr program; an FPMCU, **no USB-C/PD** |
| gale (STM32F072CB) — desired | **Cortex-M0** | **128 KB** | **16 KB** | nothing comparable exists |

### Smallest *any-chip* cros-ec Zephyr target (from `docs/zephyr/project_config.md:204-211`)
| zephyr_board | RAM | Flash |
|---|---|---|
| Microchip MEC1727 | 416 KiB | 512 KiB |
| Nuvoton NPCX7m7FC | 384 KiB | 512 KiB |
| Nuvoton NPCX9m3F | 320 KiB | 512 KiB |
| Nuvoton NPCX9m7F | 384 KiB | 1 MiB |
| **ITE IT81202 / IT81302** | **60 KiB** | 1 MiB |

→ **Smallest sanctioned RAM = 60 KiB; smallest flash = 512 KiB.** gale's 16 KiB /
128 KiB is ~**4× under RAM and 4× under flash** vs the smallest documented target,
and its 64 KiB per-image budget is **8×** smaller than the smallest chip's flash.

---

## Q2 — Footprint reality: does TCPMv2 + USB device + Zephyr kernel fit 64 KiB / 16 KiB?

**No measured-fit evidence exists, and all available evidence points to "no."**

- **No size budgets in docs.** A full scan of `docs/zephyr/` for flash/RAM budget
  language returned essentially nothing (only one `zephyr_tokenized_logging.md`
  mention that tokenized logging *reduces* image size — itself a signal that
  Zephyr log strings are a footprint concern). There is **no documented minimum
  footprint** to cite, and **no board overlay** in this tree sets
  `CONFIG_FLASH_SIZE`/`CONFIG_SRAM_SIZE` to anything near 16 KiB — those values
  come from the upstream SoC `.dtsi` for the (much larger) supported chips.
- **No measurable Cortex-M map file here.** `ec-main/build/` contains only a
  `host` (posix) build, not a flashable ARM image, so no `.map` to extract real
  section sizes from. (Producing one needs the full Zephyr build env, which is out
  of scope for this spike.)
- **Indirect but strong RAM evidence:** the smallest RAM target cros-ec Zephyr is
  *documented* to run on is **60 KiB** (ITE). Zephyr's kernel + threads + the
  cros-ec shim layer were sized against ≥60 KiB parts. gale has **16 KiB** total —
  less than a *quarter*. Stack sizes alone illustrate the pressure: the FPMCU USB
  device thread is `CONFIG_USBD_THREAD_STACK_SIZE=2048`
  (`program/fpmcu/et171/prj.conf`); gale's whole legacy RAM budget is 16 KiB and
  its four legacy task stacks total ~2.25 KiB (HOOKS 640, HOSTCMD 488, CONSOLE 488,
  PD_C0 640 — from the live `taskinfo`). Zephyr's per-thread/IPC/heap overhead is
  materially higher than legacy ECOS.
- **Per-image flash:** gale's images are **64 KiB each**. Zephyr's own RW on its
  smallest STM32 (bloonchipper) is sized at **640 KiB**, and even its *RO* is
  128 KiB. TCPMv2 (the `zephyr` USB-C PRL/PE/TC state machines) + the USB device
  stack (`usbd`/`udc`) + the Zephyr kernel + shell console is a well-known
  multi-tens-of-KiB stack on its own; fitting RO **and** RW each into 64 KiB on top
  of the Zephyr base is not credible on the evidence.

> **Footprint verdict: DOES NOT FIT.** RAM is the harder wall (16 KiB vs a 60 KiB
> documented floor). Flash (64 KiB/image) is also very likely over budget once the
> Zephyr kernel + TCPMv2 + USB device are included. Exact numbers are *uncertain*
> (no local build), but every measurable anchor is 4–10× on the wrong side.

---

## Q3 — Is there a Zephyr TCPC driver for a bit-banged STM32F0 PHY?

**No. None. All Zephyr TCPCs/PDCs are external chips.**

- `zephyr/drivers/usbc/` contains only **PDC** drivers for external controllers:
  `pdc_rts54xx*`, `pdc_tps6699x*`, `tps6699x_*`, `intel_altmode`, `ucsi_v3` — all
  I2C/SPI silicon.
- The **TCPMv2** chip drivers (shared at `driver/tcpm/`) are *all* external:
  `anx7406/anx7447`, `ccgxxf`, `fusb302`, `nct38xx`, `ps8xxx` (ps8751/805/815/745),
  `raa489000`, `rt1715`, `rt1718s`, `tusb422`, plus the integrated **ITE-EC** TCPCs
  (`it83xx`, `it8xxx2` — those are ITE's *own* EC silicon, not STM32). Enumerated
  Kconfig options (`zephyr/Kconfig.tcpm`): `TCPCI, CCGXXF, ITE_ON_CHIP,
  DRIVER_IT83XX, DRIVER_IT8XXX2, ANX7406, ANX7447, FUSB302, NCT38XX, PS8XXX,
  PS8745/751/805/815, RAA489000, RT1715, RT1718S, TUSB422` — **no STM32 / bit-bang
  option.**
- The Zephyr USB-C model (`docs/zephyr/zephyr_tcpc.md`, `zephyr_pd.md`) is
  devicetree-centric: every port is `named-usbc-port { tcpc = <&external_chip>; }`
  on an I2C bus. There is **no notion of "the SoC is the PHY."** ("Board Specific
  Code: None required.")
- gale is the opposite architecture. From `ec/board/gale/board.h`:
  `CONFIG_USB_PD_TCPC` + `CONFIG_USB_PD_TCPM_STUB` + `CONFIG_USB_PD_INTERNAL_COMP`
  — i.e. **gale itself is the TCPC**, using **TCPMv1** with a *local* PHY. The
  legacy PHY (`ec-legacy/chip/stm32/usb_pd_phy.c`, 685 LOC) bit-bangs raw
  STM32F0 peripherals: **SPI1** (TX), **TIM** (timing), **DMA1**, and **COMP1/COMP2
  comparators + DAC (850 mV threshold) + EXTI** for RX (`STM32_COMP_CSR`,
  `STM32_EXTI_PR/IMR`, `STM32_DAC_*`, `DECLARE_IRQ(STM32_IRQ_COMP,…)`). None of
  these have Zephyr cros-ec driver abstractions; the only "bitbang" in the whole
  Zephyr tree is **HDMI-CEC** (`shim/src/cec_bitbang.c`), not USB-PD.
- And **TCPMv1 does not exist in `zephyr/` at all** — grep for
  `TCPMV1`/`TCPM_STUB` returns zero. Zephyr offers only **TCPMv2** (pre-2024) and
  **PDC** (2024+) per `docs/zephyr/zephyr_new_board_checklist.md:79-82`.

→ A Zephyr gale needs **a brand-new STM32F0 PD-PHY TCPC** (or a from-scratch
"internal/SoC TCPC" shim feeding TCPMv2), wiring Zephyr's COMP/DAC/EXTI/SPI/TIM
drivers (or raw register access) into the TCPMv2 PRL/PE. **This is the single
largest work item and a genuine research-grade driver, not a config change.**

---

## Q4 — Does a `usb_spi` (raiden) bridge exist in Zephyr cros-ec?

**No.** Grep of the entire `zephyr/` tree for `usb_spi` / `raiden` returns
**nothing**. The raiden `usb_spi` bridge (gale's path to flash the AP's W25Q64 over
USB) is legacy-only: `ec-legacy/chip/stm32/usb_spi.c` (**998 LOC**, STM32-DMA/SPI-
master specific) + the shared `common/usb_spi.c` protocol layer. gale enables it
via `CONFIG_USB_SPI` + `CONFIG_SPI_MASTER` + `CONFIG_USB_SPI` (`board.h:57-60`).

Zephyr *does* have a USB-device subsystem and Google-vendor USB endpoints
(`zephyr/subsys/usb_dc/` and `zephyr/subsys/usbd_service/`:
`usb_google_update.c`, `usb_google_i2c.c`, HID kb/tp), built on
`CONFIG_USB_DEVICE_STACK` / `..._NEXT` and a Zephyr `udc` controller. But there is
**no `usb_spi` endpoint** among them, and the USB plumbing assumes a `udc` driver
for the SoC's USB IP — the FPMCU uses **STM32F4 USB-OTG**; STM32F0 has a *different*
(smaller FS-device) USB IP. So the bridge would be **new** (port the ~1 KLOC
host-side protocol onto Zephyr's usbd as a custom class/endpoint), and it depends
on getting Zephyr's `st,stm32-usb` FS device driver working on F0 first.

---

## Q5 — Port shape (what a Zephyr gale would actually require)

Closest existing reference = **`zephyr/program/fpmcu/bloonchipper`** (only STM32
program) for the SoC/flash/USB-device/shim patterns, but note it carries **no
USB-C/PD** — so there is **no single board to copy**; gale would stitch together
bloonchipper's STM32 plumbing + a USB-C program's TCPMv2 config + two new drivers.

Grounded in `ec/board/gale/{board.h, gpio.inc (27 sigs), ec.tasklist (4 tasks),
usb_pd_config.h, usb_pd_policy.c, board.c}`:

| Piece | Effort | Notes / evidence |
|---|---|---|
| **STM32F0 SoC + board into Zephyr** | **MAJOR (blocker)** | No `st,stm32f072` board wired into cros-ec; F0 RCC/flash/option-bytes differ from F4. New `zephyr/boards/` entry + upstream SoC reliance + F0 flash backend (today `SOC_SERIES_STM32F4X`-only). Must also fit ARMv6-M (no bit-banded SRAM etc.). |
| **Bit-bang STM32F0 PD-PHY TCPC driver** | **MAJOR (blocker)** | 685 LOC of COMP/DAC/EXTI/SPI1/TIM/DMA register bit-bang, re-expressed as a Zephyr TCPC feeding **TCPMv2** (gale's TCPMv1+STUB has no Zephyr port). No precedent; highest-risk item. |
| **raiden `usb_spi` bridge** | **MAJOR** | ~1 KLOC, new Zephyr usbd class/endpoint + SPI-master DMA; depends on F0 `udc`/USB-FS driver working first. |
| **USB device consoles + USART↔USB streams** | **MODERATE** | gale: 4 ifaces / 5 eps, `STREAM_USART/USART2/USB`. Zephyr has `usbd_service` + console, but no `usb_spi`/`STREAM_USART` equivalent; needs F0 USB-FS `udc`. |
| **Power sequencing / AP comms** | **MODERATE** | gale uses GPIO seq + I2C-slave-to-AP (`board.c`, `CONFIG_I2C_SLAVE`), not a heavy power task. Zephyr `ap_pwrseq`/`Kconfig.powerseq` exist but are x86/MTK-oriented; gale's tiny custom seq is simplest as small board C + shell cmds. `CONFIG_PLATFORM_EC_POE` stub exists (added 2025) and is gale-relevant (PoE AP) but is only a bool. |
| **Devicetree from gpio.inc (27 signals + alt-funcs)** | **MODERATE** | Mechanical: `named-gpios` + STM32 `pinctrl` for SPI1/USART1/USART2/ADC(CC1/CC2/VBUS/Isense)/TIM. Straightforward *given* the SoC exists. |
| **Kconfig from board.h** | **TRIVIAL–MODERATE** | Map `CONFIG_USB_PD_*`, `CONFIG_ADC`, `CONFIG_HW_CRC`, PD power constants to `PLATFORM_EC_*` Kconfig + `project.conf`. Easy once the stack below it exists. |
| **App/tasks** | **TRIVIAL** | 4 tasks (HOOKS/HOSTCMD/CONSOLE/PD_C0) map to Zephyr's shimmed tasks; ordinary. |

---

## Top 3 risks / blockers

1. **Footprint (16 KiB RAM / 64 KiB-per-image).** The wall. RAM is 4× under the
   smallest *documented* cros-ec Zephyr target (60 KiB) and far under what
   TCPMv2 + a Zephyr USB-device stack + kernel + shell realistically use. Flash
   per-image (64 KiB) is also very likely over budget. **Unmeasured locally** (no
   build env), but every anchor is 4–10× adverse. If RAM doesn't fit, nothing else
   matters.
2. **The bit-bang STM32F0 PD-PHY + TCPMv1→TCPMv2 gap.** Zephyr has *no* internal/
   bit-bang TCPC and *no* TCPMv1; gale *is* its TCPC via COMP/DAC/EXTI/SPI/TIM.
   This is net-new, research-grade driver work with hard real-time RX decoding on a
   48 MHz M0 — the highest-effort, highest-uncertainty item.
3. **No STM32F0 / Cortex-M0 enablement in cros-ec at all** (shim/flash/system are
   F4-gated; no F0 board; ARMv6-M vs the ARMv7-M everything was built/tested on),
   **plus** the `usb_spi` bridge being entirely absent and dependent on an unproven
   F0 USB-FS `udc`. Two more from-scratch subsystems before gale boots.

### Bottom line
A Zephyr gale is **not a board port** — it is **bringing a new low-end SoC class
(Cortex-M0/STM32F0/16 KiB) into cros-ec Zephyr and writing its two hardest drivers
(internal PD-PHY TCPC, usb_spi) from scratch**, against a footprint that the
evidence says **does not fit**. **VERDICT: DOES NOT FIT** for gale's
128 KiB/16 KiB STM32F072. (The footprint conclusion is evidence-strong but
*unmeasured* here; a definitive number needs a real Zephyr build, which the
available anchors make very unlikely to change the verdict.)
