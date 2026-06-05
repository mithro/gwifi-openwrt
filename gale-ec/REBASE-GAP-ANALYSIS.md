# Gale forward-port gap analysis: 2016 `firmware-gale-8281.B` → current legacy `main`

Read-only sizing spike. No source trees were modified.

- **Source (port FROM):** `/home/tim/local/gwifi/tmp/ec` @ `firmware-gale-8281.B`
  (HEAD `7c97ab0 "Clear OWNERS for factory/firmware branch"`), board
  `board/gale/` — STM32F072CB, Cortex‑M0, 128 KB flash / 16 KB RAM, 1 USB‑PD
  sink port (TCPMv1 + bit‑banged STM32F0 PHY), raiden `usb_spi` bridge to the
  AP's W25Q64, USART‑over‑USB consoles, AP power sequencing, 4 tasks.
- **Target (port TO):** `/home/tim/local/gwifi/tmp/ec-main` @ `main`
  (HEAD `37850ff`, dated **2026‑06‑04**; shallow `--depth 1` clone, so deep git
  history / deletion commits are not visible).
- **Toolchains available:** system `arm-none-eabi-gcc` 14.2; 2016q3 gcc 5.4 at
  `/home/tim/local/gwifi/tmp/gcc-arm-none-eabi-5_4-2016q3`.

---

## TL;DR — headline finding

**Current legacy `main` is NOT a viable forward-port target for gale.** The
legacy ARM/STM32 firmware-target capability has been *removed* from the tree.
Every load-bearing subsystem gale depends on — the `chip/stm32` port, the
`core/cortex-m0` core, *any* STM32F0 board, the legacy **TCPMv1** PD state
machine and its bit-banged PHY, the raiden **USB‑SPI bridge**, and the
**USART/USB stream** drivers — is gone from the legacy paths. What remains under
the non-Zephyr tree is essentially: the shared `include/` config+macro
framework, the native **`host`** test/emulator target, an `npcx` *header stub*,
and the **`hyperdebug`** board (which is a *Zephyr* board). Real STM32 + PD work
now lives entirely under `zephyr/`.

The CONFIG symbols mostly still *exist* in `include/config.h`, but for the
subsystems gale needs (`CONFIG_USB_PD_TCPMV1`, `CONFIG_USB_SPI`,
`CONFIG_STREAM_USART*`) the symbol is **vestigial** — documented and sometimes
still referenced by a Makefile branch, but the implementation `.c`/`.h` files
have been deleted. A symbol surviving in config.h does **not** mean it builds.

**Overall effort: MAJOR — effectively a re-port, not a rebase.** Legacy `main`
gives you almost nothing reusable beyond the build harness and `include/`
headers. See "Recommendation" for the two realistic paths.

---

## Area 1 — Framework + toolchain sanity → **MAJOR (blocker)**

**Does legacy main still build an STM32F0 board? No — there are none, and the
ARM core is gone.**

Evidence:
- `ls board/` on main returns exactly **two** entries: `host`, `hyperdebug`.
  `servo_micro`, `twinkie`, `zinger`, `gale`, etc. are all **gone**.
- `make BOARD=servo_micro -j8 build/servo_micro/ec.bin` →
  `Makefile:23: *** unable to locate BOARD servo_micro. Stop.` (the task's
  suggested reference board does not exist).
- `grep -rl 'CHIP_VARIANT:=stm32f0' board/*/build.mk` → **no matches** (no
  STM32F0 board to use as a reference at all).
- `ls core/` → only `core/host` (+ the generic `core/build.mk`). **There is no
  `core/cortex-m0` or `core/cortex-m`.** The Cortex‑M core gale needs is
  deleted.
- `ls chip/` → only `host` and `npcx`. **No `chip/stm32`.** And `chip/npcx`
  contains a *single header* (`rom_chip.h`) with **no `build.mk`** — it is a
  Zephyr-shared stub, not a buildable legacy chip port.
- The only buildable legacy board is `host` (`CHIP:=host`, `CORE:=host`), i.e.
  the native unit-test emulator — it targets x86_64, not ARM.
- Tree-wide, `CHIP_FAMILY:=stm32f0` / `stm32f07x` appear **only** in
  `.git-blame-ignore-revs` (historical hashes) and `util/stm32mon.cc` (a
  host-side serial flashing tool, not firmware). STM32 firmware support survives
  *only* under `zephyr/shim/chip/stm32` (pure CMake/Zephyr:
  `zephyr_library_sources(clock.c)` …) — not usable from the legacy Makefile
  path.

Toolchain note: the question of "gcc 14 vs gcc 5.4 / which CFLAGS" is **moot** —
there is no ARM core build to feed a toolchain to. `CFLAGS_CPU` is supplied
per-core from `core/$(CORE)/build.mk`, and only `core/host` exists, so there is
no `-mcpu=cortex-m0 -mthumb` path on legacy main at all. (`Makefile.rules` still
prints a stale `make BOARD=reef CROSS_COMPILE_arm=…` help line, but `reef` is
gone too.) For completeness I tried `make BOARD=host`; it requires the
ChromiumOS SDK chroot (`x86_64-pc-linux-gnu-clang`, `libec.pc` pkg-config) and
does not build on a bare host — but `host` is not our target regardless.

**Smoking gun for "it used to be here":** `common/build.mk:86` still reads
`ifneq ($(CORE),cortex-m0)`. The build system *remembers* cortex-m0 as a
concept (to exclude certain common files for it), but the
`core/cortex-m0` directory that guard was written for has been deleted. Vestige,
not capability.

---

## Area 2 — Chip / core support → **MAJOR (blocker)**

**`chip/stm32` + `core/cortex-m0` + the `stm32f07x` variant do NOT exist on
main.** This is the same finding as Area 1, stated against the specific paths:

| gale needs | on legacy main |
|---|---|
| `chip/stm32/` (registers, clock, gpio, adc, spi, i2c, dma, usart, flash, hwtimer…) | **REMOVED** — dir absent |
| `core/cortex-m0/` (startup, task switch, `asm_offsets`, vectors) | **REMOVED** — only `core/host` remains |
| `CHIP_VARIANT:=stm32f07x` | **REMOVED** — no `chip/stm32/variant_*` |
| `chip/stm32/adc_chip.h` (`STM32_AIN`) | **REMOVED** — `adc_chip.h` exists only under `chip/host` |
| STM32 register defs (`STM32_RCC_*`, `STM32_GPIO_*`, `STM32_COMP_*`, `STM32_TIM_*`, `STM32_SYSCFG_*`, `STM32_DMAC_*`) used pervasively by `board.c` + `usb_pd_config.h` | **REMOVED** with `chip/stm32/registers.h` |

All of these now exist only inside `zephyr/` (the STM32 HAL is provided by
Zephyr's own drivers + `zephyr/shim/chip/stm32`). There is no legacy STM32 chip
layer to forward-port onto.

---

## Area 3 — `board.h` CONFIG drift → **MODERATE (in isolation) / overshadowed**

Classification of every `CONFIG_*` (and the USB iface/EP/string constructs)
gale's `board.h` uses, checked against `include/config.h` and the surviving
`board/host`. **Caveat:** "STILL EXISTS" below means *the symbol is present in
config.h*; for three of them the **implementation is gone** (flagged).

**RENAMED** (the ~2021 inclusive-language de-mastering sweep):
- `CONFIG_SPI_MASTER` → **`CONFIG_SPI_CONTROLLER`** (`config.h:4254`; old name: 0
  hits tree-wide). gale's `board.h` and `CONFIG_SPI_FLASH_PORT` usage must
  switch.
- `CONFIG_I2C_SLAVE` → **`CONFIG_I2C_PERIPHERAL`** (`config.h:2911`; old name: 0
  hits). gale's `I2C_PORT_SLAVE` / `CONFIG_I2C_SLAVE` block must switch. (`I2C_PORT_*`
  board defines are board-local, so only the CONFIG token changes.)
- `CONFIG_USB_PD_PORT_COUNT` → **`CONFIG_USB_PD_PORT_MAX_COUNT`**
  (`config.h:5002`; old name: **0** hits in config.h and 0 in any non-Zephyr
  `.c`/`.h`). Hard rename; gale uses the dead name.

**REMOVED:**
- `CONFIG_STM_HWTIMER32` — **0** hits (was a `chip/stm32` config; died with
  `chip/stm32`). gale sets it for its 32-bit hwtimer.

**STILL EXISTS as a symbol (✓) — but implementation DELETED (✗ build):**
- `CONFIG_USB_SPI` — symbol at `config.h:5817`, **but** `common/usb_spi.c` /
  `include/usb_spi.h` / `USB_SPI_CONFIG` are gone (see Area 5). Vestigial.
- `CONFIG_STREAM_USART` (`:4575`), `CONFIG_STREAM_USART2`, `CONFIG_STREAM_USB`
  (`:4589`) — symbols present, **but** `usb-stream.h`, `usart-stm32f0.h`,
  `usart_tx_dma.h`, `usart_rx_dma.h`, the `USB_STREAM_CONFIG` macro and all
  `usart*.c`/`usb-stream.c` implementations are **gone** (non-Zephyr). Vestigial.

**STILL EXISTS (symbol present; generic/common, likely fine):**
`CONFIG_UART_CONSOLE` (4615), `CONFIG_ADC`, `CONFIG_ADC_WATCHDOG`,
`CONFIG_BOARD_PRE_INIT`, `CONFIG_HW_CRC`, `CONFIG_WATCHDOG_HELP`,
`CONFIG_LID_SWITCH`, `CONFIG_USB`, `CONFIG_USB_PID`, `CONFIG_USB_CONSOLE`,
`CONFIG_USB_INHIBIT_INIT`, `CONFIG_SPI_FLASH_PORT`, `CONFIG_I2C`,
`CONFIG_CMD_SPI_XFER`, `CONFIG_FLASH_PSTATE_BANK`, `CONFIG_FW_PSTATE_SIZE`,
`CONFIG_SYSTEM_UNLOCKED`, `CONFIG_USBC_SS_MUX` (7 hits, healthy).
(All PD CONFIGs are covered in Area 4.)

**USB iface/EP/`usb_strings` constructs:** the descriptor/string machinery
survives — `include/usb_descriptor.h` still defines `USB_STRING_DESC` and
`usb_string_desc`. gale's `enum usb_strings`, `USB_IFACE_*`/`USB_EP_*` `#define`
blocks, and the `usb_strings[]` table are board-local idioms that still match
the framework. **BUT** `USB_STREAM_CONFIG` (used for the AP-console USB serial
interface) and `USB_SPI_CONFIG` (the SPI USB interface) are gone, so two of
gale's four USB interfaces lose their backing macros.

**Sizing:** the pure rename/removed churn (4 tokens) is genuinely *moderate and
mechanical*. But it is overshadowed — fixing the CONFIG names is pointless while
the chip/core/PD/SPI/stream implementations those CONFIGs switch on do not
exist.

---

## Area 4 — USB‑PD stack → **MAJOR (the defining blocker)**

**Legacy `main` is effectively TCPMv2-only in practice; gale's entire TCPMv1 +
bit-banged STM32F0 PHY model has no implementation to land on.**

What's still there (encouraging at first glance):
- `CONFIG_USB_PD_TCPMV1` **is still defined** in `config.h:4706` (documented as
  "legacy power delivery state machine", vs `CONFIG_USB_PD_TCPMV2` "current", and
  the mutual-exclusion guard at `config.h:6219` still enforces exactly one of
  TCPMV1 / TCPMV2 / CONTROLLER).
- All of gale's other PD CONFIGs still exist as symbols:
  `CONFIG_USB_PD_ALT_MODE` (4775), `CONFIG_USB_PD_DUAL_ROLE` (4891),
  `CONFIG_USB_PD_INTERNAL_COMP` (4973), `CONFIG_USB_PD_TCPC` (5017),
  `CONFIG_USB_PD_TCPM_STUB` (5129), `CONFIG_USB_PD_CUSTOM_VDM`.
- All of gale's policy-hook **prototypes** survive in `include/usb_pd.h`:
  `pd_power_supply_reset` (1844), `pd_set_input_current_limit` (1887),
  `pd_check_power_swap` (1941), `pd_check_data_swap` (1961),
  `pd_custom_vdm` (2042), `svdm_rsp` (445), `pd_src_pdo[]` (2791),
  `pd_snk_pdo[]` (2795).

Why it is nonetheless a MAJOR blocker:
1. **The TCPMv1 core implementation is DELETED.** `common/usb_pd_protocol.c`
   (the legacy state machine gale's policy hooks plug into) **does not exist
   anywhere in the tree** (`find` → nothing). Neither does a generic
   `common/usb_pd_policy.c`. Yet `common/build.mk:175-177` still says
   `ifneq ($(CONFIG_USB_PD_TCPMV1),) … += usb_pd_protocol.o usb_pd_policy.o
   usb_pd_pdo.o`. So enabling TCPMv1 points the Makefile at **object files whose
   sources were removed** — it cannot link. TCPMv1 is a config symbol with no
   body.
2. **No board enables TCPMv1.** `grep -rln 'define CONFIG_USB_PD_TCPMV1'` over
   the whole tree returns **only `include/config.h`** (the `#undef` default).
   Zero boards, zero tests exercise the v1 path → it is unmaintained/bit-rotted
   even where stubs survive.
3. **`common/usbc/` is now the TCPMv2 world:** `usb_pe_drp_sm.c` (policy
   engine), `usb_prl_sm.c` (protocol layer), `usb_tc_drp_acc_trysrc_sm.c`
   (Type‑C SM), `usb_pd_dpm.c`, `usb_pd_timer.c`, etc. This is a completely
   different architecture (PE/PRL/TC layered state machines) from gale's
   monolithic TCPMv1 `pd_task` + policy callbacks.
4. **The bit-banged STM32F0 PHY has nowhere to live.** gale's
   `usb_pd_config.h` is pure `chip/stm32` register banging: SPI1 TX (`SPI_REGS`,
   `STM32_RCC_PB2_SPI1`), `TIM16_CH1`, `TIM1` input capture, `COMP1/COMP2`
   (`STM32_COMP_CSR`, `CMP*INSEL_VREF12`), `STM32_EXTI_FTSR`, DMA channels,
   `gpio_set_alternate_function`, `STM32_GPIO_MODER/OSPEEDR`. Every one of those
   symbols came from `chip/stm32` (Area 2) → **gone**. The only legacy PHY left
   is `chip/host/usb_pd_phy.c` (an *emulated* PHY for unit tests), which is not a
   real silicon driver.
5. **Hook signature drift** (typed enums + weak-override switch). Compare gale
   (old) vs `board/host/usb_pd_policy.c` (current TCPMv2 reference):
   - `pd_check_data_swap(int, int data_role)` →
     `__override int pd_check_data_swap(int, enum pd_data_role data_role)`
   - `pd_check_pr_role(int, int pr_role, int)` →
     `__override void pd_check_pr_role(int, enum pd_power_role pr_role, int)`
   - `pd_check_dr_role(int, int dr_role, int)` →
     `__override void pd_check_dr_role(int, enum pd_data_role dr_role, int)`
   - hooks are now `__override`/`__overridable`/`test_mockable` weak symbols
     rather than plain definitions. gale's plain definitions would need
     re-annotation and signature updates.
   - Also: `pd_src_pdo[]`/`pd_snk_pdo[]` now live in `usb_pd_pdo.c` +
     `include/usb_pd_pdo.h` (gale declares them inline in `usb_pd_policy.c`);
     `tcpm.h` moved to `include/driver/tcpm/tcpm.h` (gale's `tcpm_get_cc()` call
     in `board.c`'s `board_no_charger` needs the new path); the
     `TYPEC_CC_VOLT_SNK_*` enum names used by gale's `board.c`/`print_cc_current`
     must be re-checked against the current enum.

**Sizing:** porting gale's PD onto legacy main means either (a) **resurrecting
deleted code** — restore `common/usb_pd_protocol.c` + a `chip/stm32` PD PHY from
an old branch and keep them alive against today's `usb_pd.h`; or (b)
**rewriting** gale's policy + PHY against TCPMv2 (`usb_pe`/`usb_prl`/`usb_tc` +
a TCPMv2-style PHY/TCPC driver). Both are **MAJOR rewrites**, and (b) is
arguably a Zephyr-class effort. This is *the* item that sinks the legacy-main
target.

---

## Area 5 — raiden `usb_spi` bridge → **MAJOR (removed)**

**The USB‑SPI bridge common code is gone from legacy main.**

Evidence:
- `common/usb_spi.c` — **does not exist** (`find` → nothing, non-Zephyr).
- `include/usb_spi.h` — **does not exist**.
- `USB_SPI_CONFIG`, `struct usb_spi_config`, `usb_spi_board_enable`,
  `usb_spi_board_disable` — **0** references across `include/`, `common/`,
  `chip/` (non-Zephyr). gale's `board.c` defines `usb_spi_board_enable/disable`
  and instantiates `USB_SPI_CONFIG(usb_spi, USB_IFACE_SPI, USB_EP_SPI)` against
  an API that no longer exists.
- `CONFIG_USB_SPI` survives as a *symbol* (`config.h:5817`) and
  `CONFIG_USB_SPI_IGNORE_HOST_SIDE_ENABLE` (5825) — but, like TCPMv1, these are
  vestigial: no implementation, and `usb_spi*` does **not** appear under
  `zephyr/` either, so it wasn't migrated — it was removed.

What *does* survive: the underlying SPI-controller/flash master infrastructure —
`include/spi.h` still defines `struct spi_device_t spi_devices[]` and
`SPI_FLASH_DEVICE (&spi_devices[0])`. So gale's `spi_devices[]` table and the
raw SPI master path are fine; it is specifically the **USB↔SPI bridge endpoint**
(the thing that makes the AP's W25Q64 reachable from the host over USB) that has
no code on main.

**Sizing: MAJOR** — the entire bridge (common driver + the `chip/stm32`
`usb_spi` glue) would have to be restored from the old tree (and then kept
working against the current USB stack), since there is no modern equivalent in
the legacy paths.

---

## Area 6 — `gpio.inc` / `ec.tasklist` / RWSIG-version → **TRIVIAL–MODERATE (the one bright spot)**

The board-description DSLs and version machinery are the *only* gale-facing
surfaces that survive intact on legacy main.

- **`gpio.inc` macros:** `include/gpio.wrap` still defines `GPIO(name,pin,flags)`
  (:55), `ALTERNATE(pinmask,function,module,flags)` (:84), `UNIMPLEMENTED(name)`
  (:104), plus `GPIO_INT`, `PIN`, `PIN_MASK`, and RO/RW variants
  (`ALTERNATE_RO/RW`, `UNIMPLEMENTED_RO/RW`). `include/gpio_signal.h` and
  `include/gpio_list.h` are present. The surviving `board/host/gpio.inc` uses the
  exact same `GPIO_INT(...)`/`GPIO(...)`/`PIN(port,n)` syntax gale uses →
  **gale's `gpio.inc` is essentially drop-in** (modulo the obvious caveat that
  the `MODULE_USB_PD` / `MODULE_SPI_FLASH` / `MODULE_USART` alternate-function
  targets it references are only meaningful if the corresponding chip drivers
  exist — which, per Areas 2/4/5, they don't). *Minor watch-item:*
  `include/gpio.h` carries two `GPIO_INT_F_*` flag-value blocks (legacy vs
  shim); verify flag encodings if reused.
- **`ec.tasklist` macros:** `include/task_filter.h` still defines `TASK_ALWAYS`,
  `TASK_NOTEST`, `LARGER_TASK_STACK_SIZE`, `TASK_STACK_SIZE`. gale's 4-task list
  (HOOKS/HOSTCMD/CONSOLE/PD_C0) uses exactly these tokens → **syntactically
  drop-in** (though PD_C0 is moot without a PD stack, and stack sizes would need
  re-tuning for whatever core it eventually targets).
- **RWSIG / version:** `util/getversion.sh` still exists; `CONFIG_RWSIG`,
  `CONFIG_RWSIG_TYPE_RWSIG`, `CONFIG_RWSIG_TYPE_USBPD1` survive
  (`config.h:4090/4110/4111`). gale does **not** use RWSIG (it uses
  `CONFIG_FW_PSTATE_SIZE 0` + PSTATE embedded in RO), so this surface is
  low-risk regardless.

**Sizing: TRIVIAL** for the macro syntax itself; **MODERATE** only because the
modules these files point at are missing.

---

## Synthesis

### (a) Overall effort estimate — **MAJOR (re-port, not a rebase)**

This is not a "forward-port the board onto a newer framework" exercise, because
the framework gale targets (legacy ARM/STM32 EC with TCPMv1) **no longer exists
on `main`**. Of gale's six surfaces:

| Area | Size | One-line reason |
|---|---|---|
| 1 Framework + toolchain | **MAJOR** | No STM32F0 board, no ARM build path at all |
| 2 chip/stm32 + core/cortex-m0 | **MAJOR** | Both directories deleted |
| 3 board.h CONFIG drift | MODERATE* | 4 renames/removals; *but moot w/o impls |
| 4 USB‑PD (TCPMv1 + STM32F0 PHY) | **MAJOR** | v1 core + PHY deleted; tree is TCPMv2 |
| 5 raiden usb_spi bridge | **MAJOR** | Bridge common code + API deleted |
| 6 gpio.inc / tasklist / version | TRIVIAL | DSLs intact (only bright spot) |

Four of six are MAJOR and three are hard *blockers* (1, 2, 4/5 share the same
root cause: the legacy ARM stack was excised). Mechanical CONFIG renames (Area
3) and the GPIO/task DSLs (Area 6) are the only cheap parts, and they are
worthless without the missing chip/core/PD/SPI layers underneath.

### (b) Top 3 risks / blockers

1. **No legacy ARM target exists on `main`.** `chip/stm32` and
   `core/cortex-m0` are deleted; there are zero STM32F0 boards and no
   `-mcpu=cortex-m0` build path. Without restoring an entire chip+core port,
   nothing for gale can compile. *(Hard blocker.)*
2. **TCPMv1 is a config symbol with no body.** `common/usb_pd_protocol.c` is
   deleted, `common/build.mk` still references the missing object, no board
   enables v1, and the bit-banged STM32F0 PHY's register layer is gone. gale's
   PD stack — its core differentiator — cannot land without either resurrecting
   dead code or a TCPMv2 rewrite. *(Hard blocker.)*
3. **The USB‑SPI bridge (W25Q64 access) is removed**, and the USART/USB stream
   drivers (gale's two USB serial/SPI interfaces) are removed. These are gale
   *features*, not incidentals; both require restoring deleted subsystems.
   Plus the silent-trap risk: several CONFIG symbols (`CONFIG_USB_SPI`,
   `CONFIG_STREAM_*`, `CONFIG_USB_PD_TCPMV1`) **still exist in `config.h`**, so a
   naïve port "looks" supported and only fails at link time when the missing
   `.o` files surface. Do not trust symbol presence as capability.

### (c) Is legacy-main a viable target for gale? — **No.**

- Framework: ✗ no ARM/STM32F0 build path.
- STM32F0 chip + Cortex‑M0 core: ✗ both deleted.
- PD stack: ✗ TCPMv1 implementation deleted, PHY register layer deleted, tree is
  TCPMv2-only in practice.
- raiden usb_spi + USART streams: ✗ deleted.
- Only the board-description DSLs (gpio.inc/ec.tasklist), the USB
  descriptor/string helpers, and the generic `include/config.h` token set carry
  over — i.e. the scaffolding, none of the substance.

Current legacy `main` has been reduced to the `host` unit-test target + Zephyr
glue (`hyperdebug`, the `npcx` header stub, `zephyr/`). It is a maintenance
shell for the Zephyr transition, **not** a home for a new STM32F0 ARM board.

### (d) Recommended port ORDER

Because legacy `main` is non-viable as-is, the realistic options are:

- **Option A — Stay on a real legacy snapshot (recommended, lowest risk).**
  Keep gale on `firmware-gale-8281.B` (or rebase only onto the *last* legacy EC
  tag that still shipped `chip/stm32` + `core/cortex-m0` + TCPMv1 — identifiable
  via the deep history this shallow clone hides). Cherry-pick only targeted
  fixes. This preserves everything gale needs with near-zero porting cost.

- **Option B — Go to Zephyr (the actual modern target).** If "current" is the
  real requirement, port gale to the **Zephyr EC** under `zephyr/` (using
  `zephyr/shim/chip/stm32` + Zephyr STM32F0 HAL, TCPMv2 PD, devicetree GPIO).
  This is a ground-up board bring-up, not a forward-port of the 2016 C, but it
  targets the tree that is actually maintained.

- **Option C — Resurrect-on-legacy-main (NOT recommended).** Restore the deleted
  `chip/stm32`, `core/cortex-m0`, `common/usb_pd_protocol.c`, the STM32F0 PD
  PHY, and `common/usb_spi.c` from an old branch onto today's `main`, then fix
  the API drift. This is a fork of half the historical EC and an ongoing
  maintenance burden; only sensible if you must be on `main` *and* cannot use
  Zephyr.

If forced down Option C, sequence to surface blockers earliest:
1. **Core/chip first:** restore `core/cortex-m0` + `chip/stm32` (+ `stm32f07x`
   variant, `registers.h`, clock/gpio/dma) and get an empty STM32F0 board to
   link with system `arm-none-eabi-gcc` 14.2 (or the 2016q3 gcc 5.4 to match the
   restored code's vintage). No point doing anything else until ARM links.
2. **board.h CONFIG renames** (Area 3: `SPI_MASTER→SPI_CONTROLLER`,
   `I2C_SLAVE→I2C_PERIPHERAL`, `USB_PD_PORT_COUNT→…_MAX_COUNT`, drop
   `STM_HWTIMER32` or restore it) + **gpio.inc / ec.tasklist** (Area 6, basically
   drop-in) — get a minimal gale booting (HOOKS/CONSOLE) with GPIO + UART.
3. **USB device + descriptors + USB console** (`usb_descriptor.h` survives), then
   restore **USART/USB streams** (`usb-stream.h`, `usart-stm32f0.*`) for the AP
   console, then the **raiden usb_spi bridge** (Area 5) for W25Q64 access.
4. **USB‑PD last and biggest** (Area 4): restore `usb_pd_protocol.c` + the
   STM32F0 PD PHY (`usb_pd_config.h` register banging) and re-point
   `tcpm.h`→`driver/tcpm/tcpm.h`, fix the typed-enum/`__override` hook
   signatures, move PDO tables to `usb_pd_pdo.*`. Validate sink/DRP behaviour and
   the `gale` console command path.

(Under Option A this ordering is unnecessary — gale already builds on its native
tree. Under Option B the ordering is a standard Zephyr board bring-up, not this
list.)

---

### Determinability notes
- The shallow `--depth 1` clone hides the exact commits/tags where
  `chip/stm32`, `core/cortex-m0`, `usb_pd_protocol.c`, and `usb_spi.c` were
  removed. A full clone (or `git log -- <path>` on an unshallowed tree) would
  pin the "last good legacy tag" for Option A — recommended as the immediate
  next step if Option A is pursued.
- `board/host` does not build on this bare machine (needs the CrOS SDK chroot
  toolchain + `libec` pkg-config), so the legacy *host* framework was confirmed
  present but not executed end-to-end. This does not affect any gale conclusion,
  since `host` targets x86_64, not STM32F0.
