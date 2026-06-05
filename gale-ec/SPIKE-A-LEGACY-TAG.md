# SPIKE A — Newest legacy `platform/ec` base that still builds `BOARD=gale`

**Result: SUCCESS.** `make BOARD=gale` produces `build/gale/ec.bin` (full 128 KiB
image) on the pinned base, with the system `arm-none-eabi-gcc` 14.2 toolchain and
`CONFIG_LTO`. All board/gale edits are confined to `ec-legacy/board/gale/*`; the
original 2016 tree (`/home/tim/local/gwifi/tmp/ec`) was not modified.

Working tree: `/home/tim/local/gwifi/tmp/ec-legacy` (full clone, 288 MB .git),
local branch **`spike-a-gale-base`** checked out at the pinned base.

---

## (a) Pinned base + deletion commits

### Pinned base (newest commit that still has all four ARM-stack components)

| field | value |
|---|---|
| **commit** | **`81ba8f9866c88192050e78b01d41e339184e33fb`** |
| author date | **2026-01-29** (committer date 2026-01-31) |
| subject | `Omit ec-private tests` |
| author | Jeremy Bettis \<jbettis@google.com\> |
| nearest release branch | **`firmware-R146-16581.2.B-main`** (ChromeOS milestone **R146**, platform **16581**) — the base is on the R146/R147/R148 mainline branches but NOT on R144/R145; it sits ~46 commits below the R146 branch tip, i.e. essentially at the R146 branch point. |
| nearest tag | only `v2.0.0` (`git describe` = `v2.0.0-30364-g81ba8f9866`) — no useful semver tag exists this recent; the release **branch** R146 is the meaningful anchor. |

This base is on `origin/main`'s first-parent history and is **~9.4 years newer than
the 2016 `firmware-gale-8281.B` base** the reconstructed board currently sits on.

### The four deletions (why the base is where it is)

The board needs `chip/stm32`, `core/cortex-m0`, `common/usb_pd_protocol.c`
(TCPMv1), and `usb_spi.c`. Note: there is **no `common/usb_spi.c`** in this repo —
the STM32 USB-SPI driver is **`chip/stm32/usb_spi.c`**.

| path | deletion commit | adate | subject |
|---|---|---|---|
| `common/usb_pd_protocol.c` | **`e25818b58e`** | **2026-01-22** | Remove unused c/cc files |
| `chip/stm32/usb_spi.c` | **`e25818b58e`** | **2026-01-22** | Remove unused c/cc files |
| `chip/stm32/` (whole dir) | `c6d2d1a6ea` | 2026-02-03 | Delete other unused files |
| `core/cortex-m0/` (whole dir) | `c6d2d1a6ea` | 2026-02-03 | Delete other unused files |

The **earliest** deletion is `e25818b58e` (2026-01-22, "Remove unused c/cc files"),
which removed both `common/usb_pd_protocol.c` and `chip/stm32/usb_spi.c`. Its graph
**parent is the pinned base `81ba8f9866`** (confirmed: `git rev-parse e25818b58e^`
→ `81ba8f9866…`). The dir-level removals of `chip/stm32` and `core/cortex-m0`
happened slightly later in `c6d2d1a6ea` (2026-02-03). All four are present and
whole at the base (chip/stm32 = 166 files, core/cortex-m0 = 28 files), and
`board/servo_micro` + `board/servo_v4` (STM32F072, `CHIP_VARIANT:=stm32f07x`,
same as gale) are present for reference/validation.

> Date nuance: the deletion's *author* date (2026-01-22) predates the *parent's*
> author date (2026-01-29) because of upstream rebasing; the **commit-graph parent
> edge** is what defines "still has all four", and it is verified above.

---

## (b) Toolchain

- **2016q3 GCC 5.4.1** (`/home/tim/local/gwifi/tmp/gcc-arm-none-eabi-5_4-2016q3`):
  **FAILS.** The modern build unconditionally passes `-Wimplicit-fallthrough`
  (a GCC ≥7 flag): `arm-none-eabi-gcc: error: unrecognized command line option
  '-Wimplicit-fallthrough'`. The 2016 compiler is too old for this tree.
- **System `arm-none-eabi-gcc` 14.2.1** (`/usr/bin/arm-none-eabi-`): **BUILDS
  CLEANLY** — both the `servo_micro` base validation and `BOARD=gale` succeed.
  **This is the toolchain to use.**

Build command (firmware target):
```
make -C ec-legacy BOARD=gale CROSS_COMPILE=/usr/bin/arm-none-eabi- -j8 build/gale/ec.bin
```
No `COMMON_WARN` override was needed (unlike the 2016 tree under GCC 14). The
`libec`/`coreboot-sdk-ec-dependencies.eclass` pkg-config noise is harmless
(ChromeOS-SDK probes outside the chroot).

---

## (c) Does `make BOARD=gale` build? YES — the port diff

`build/gale/ec.bin` = 131072 bytes (128 KiB). RW text 61988 B and RO text 62368 B,
both under the 64 KiB half-limit. Zero undefined symbols after link.

All changes are inside `board/gale/`. **CONFIG renames were required** — this base
already uses the NEW names (verified in `include/config.h`: `CONFIG_SPI_CONTROLLER`,
`CONFIG_I2C_PERIPHERAL`, `CONFIG_USB_PD_PORT_MAX_COUNT` present; the old
`SPI_MASTER`/`I2C_SLAVE`/`USB_PD_PORT_COUNT`/`STM_HWTIMER32` all gone).

### `board/gale/board.h`
- `CONFIG_SPI_MASTER` → `CONFIG_SPI_CONTROLLER`
- `CONFIG_I2C_SLAVE` → `CONFIG_I2C_PERIPHERAL`
- `CONFIG_USB_PD_PORT_COUNT 1` → `CONFIG_USB_PD_PORT_MAX_COUNT 1`
- removed `CONFIG_STM_HWTIMER32` (removed upstream; 32-bit hwtimer now unconditional on stm32)
- **added `CONFIG_USB_PD_TCPMV1`** — config.h now `#error`s unless a TCPM version is
  chosen; gale's built-in-TCPC + `TCPM_STUB` is the TCPMv1 stack (same combo as servo_v4)
- **added `CONFIG_USB_PD_CUSTOM_PDO`** — default PDO tables moved to
  `common/usb_pd_pdo.c` (guarded by `!CUSTOM_PDO`); gale supplies its own, so this
  avoids a multiple-definition link error
- **added `USB_STR_SPI_NAME`** to the `usb_strings` enum — the refactored
  `chip/stm32/usb_spi.c` references a board-provided SPI iInterface string index
- removed gale's `#define PD_DEFAULT_STATE PD_STATE_SNK_DISCONNECTED` — it is now a
  function-like macro `PD_DEFAULT_STATE(port)` in `usb_pd.h`; with
  `CONFIG_USB_PD_DUAL_ROLE` (gale has it) the header default already resolves to
  sink-disconnected, matching original intent
- **added `CONFIG_LTO`** — see (e); needed to fit the 64 KiB RW half under GCC 14

### `board/gale/board.c`
- include `"tcpm.h"` → `"tcpm/tcpm.h"` (header moved under `driver/` on the include path)
- USART_CONFIG(): added the new `FLAGS` arg (`…, 115200, 0, …`) — macro grew a 5th field
- `usleep(25)` → `crec_usleep(25)` (×2; `usleep` removed to avoid POSIX clash)
- USB-SPI bridge rework (matches `board/servo_micro`):
  - `spi_devices[]` entry gained 4th field `USB_SPI_ENABLED`
  - `usb_spi_board_enable/disable(struct usb_spi_config const *)` → `(void)`
  - `spi_enable(CONFIG_SPI_FLASH_PORT, …)` → `spi_enable(SPI_FLASH_DEVICE, …)` (takes a `spi_device_t*`)
  - removed `USB_SPI_CONFIG(usb_spi, …)` instance macro (deleted upstream)
  - added `usb_spi_enable(1)` in `board_init()` to start the bridge endpoint
- `i2c_ports[]` switched to designated initializers (`.name/.port/.kbps/.scl/.sda`) — struct layout changed
- USB-mux API overhaul:
  - callbacks `(int port_addr, …)` → `(const struct usb_mux *me, …)`; `set()` gained `bool *ack_required` (set to `false`)
  - mux flags `MUX_POLARITY_INVERTED`/`MUX_USB_ENABLED` → `USB_PD_MUX_POLARITY_INVERTED`/`USB_PD_MUX_USB_ENABLED`
  - `struct usb_mux usb_muxes[]` (`.port_addr`) → `const struct usb_mux_chain usb_muxes[]` wrapping a `static const struct usb_mux board_ss_mux` (`.mux = &…`)
- removed gale's local `pd_send_host_event()` — now a `static inline` no-op in
  `usb_pd.h` when `CONFIG_USB_PD_TCPM_STUB` is set
- console: all 7 command handlers + the dispatch table fn-ptr + the dispatch cast
  `(int argc, char **argv)` → `(int argc, const char **argv)` (console routine
  signature added `const`)
- `DECLARE_CONSOLE_COMMAND(gale, …, NULL)` → dropped the trailing flags arg (macro is now 4-arg)
- `ap_usb.state->rx_disabled = 1;` → no-op (the `usb_stream_state` struct dropped
  `rx_disabled`; struct now only has `flags`/`TX_FLUSH`). **Behavioral gap, see (e).**

### `board/gale/usb_pd_policy.c`
- 4 PD callbacks re-typed to match `__override_proto` decls and marked `__override`:
  `pd_check_data_swap`/`pd_execute_data_swap` `int data_role` → `enum pd_data_role`;
  `pd_check_pr_role` `int pr_role` → `enum pd_power_role`; `pd_check_dr_role`
  `int dr_role` → `enum pd_data_role`
- `SYSTEM_IMAGE_UNKNOWN` → `EC_IMAGE_UNKNOWN`
- `pd_set_dual_role(state)` → `pd_set_dual_role(port, state)` (gained leading port arg)
- moved the PDO tables out (now in new `usb_pd_pdo.c`)

### `board/gale/build.mk`
- `board-$(CONFIG_USB_POWER_DELIVERY)+=usb_pd_policy.o` **`usb_pd_pdo.o`**

### NEW `board/gale/usb_pd_pdo.c`
- gale's sink-only PDO tables (`pd_src_pdo[]={}`, `pd_snk_pdo[]` = 5V/3A dual-role).
  Required because under `CONFIG_USB_PD_CUSTOM_PDO` the host `genvif` tool links the
  board's PDOs from `board/<board>/usb_pd_pdo.c` (see `util/build.mk`), exactly as
  `board/servo_v4/usb_pd_pdo.c` does. Includes only `usb_pd.h` (not the fixed-size
  `usb_pd_pdo.h`, which declares `pd_src_pdo[1]`/`pd_snk_pdo[3]`).

### NEW `board/gale/vif_override.xml`
- 3-line comment stub (copied from servo_v4) so the default `all` target's VIF step
  finds it. Not needed for `ec.bin`.

`board/gale/gpio.inc`, `ec.tasklist`, `usb_pd_config.h` needed **no changes**.

---

## (d) Effort sizing for a full forward-port: **MODERATE**

Not trivial (it was not a pure rename pass — required real API rewrites for the USB
mux, USB-SPI bridge, PD policy callbacks, and a file split), but well short of major
(no algorithmic/behavioral redesign; every change has a clear in-tree precedent in
`servo_micro`/`servo_v4`, both same-chip STM32F072 boards). One spike session took it
from "current main deleted the ARM stack" to a clean-linking `ec.bin` with structural
parity to the oracle. ~10 mechanical API-drift fixes + 1 file split + LTO.

### Top risks for the full port
1. **`rx_disabled` removal (behavioral, highest-value).** The USB-stream RX gate was
   deleted upstream. The original used it to make the AP console **read-only when
   write-protect is enabled** (a security property). The port currently no-ops the
   locked branch — `TODO(full-port)` to reinstate an RX-inhibit at the USART/queue
   layer. Does not affect the build; does change locked-device behavior.
2. **GCC 14 vs 2016q3 GCC 5.4 — no byte-for-byte parity possible.** Newer compiler +
   ~9 years of code drift. Confirm functional equivalence on hardware / against the
   oracle behaviorally, not by image diff. (Vector tables already match structurally:
   identical initial SP `0x2000_04c0`, correct RO/RW reset-vector bases.)
3. **RW size headroom is thin (~3.5 KiB, ~5%).** LTO is what makes it fit. Any added
   feature can re-overflow the 64 KiB RW half; watch `__flash_used` on every change.
4. **PD policy semantics under TCPMv1 on the newer protocol code.** Signatures match
   and it links, but the TCPMv1 state machine in `common/usb_pd_protocol.c` has
   evolved since 2016 — sink-only role/swap behavior should be validated live.
5. **ChromeOS-SDK build coupling.** The default `all` target needs `vpython3` (config
   allow-list check) and `libec`/eclasses that only exist in the cros chroot. The
   firmware target builds without them, but a "clean `make BOARD=gale`" with no errors
   requires either the chroot or trimming those host-side targets.

---

## (e) Blockers / honest caveats (it DOES build — these are non-blocking)

- **None block `build/gale/ec.bin`.** It builds and links cleanly (exit 0, 0 undefined
  symbols).
- The **full default `all` target** stops at the `notice` step with
  `env: 'vpython3': No such file or directory` — an environmental gap (ChromeOS
  vpython wrapper absent on this host), **not** a gale issue. The `genvif` host tool
  itself now compiles (the PDO link error is resolved).
- The **`rx_disabled` no-op** is the one intentional behavioral simplification (item 1
  above), clearly marked `TODO(full-port)` in `board.c`.

---

## Sanity vs oracle (task 6)

`xxd -l 16` of built `.flat` vs oracle dumps (`/home/tim/local/gwifi/tmp/work/`):

```
built RO.flat : c004 0020 1901 0008 111c 0008 111c 0008
oracle RO.bin : c004 0020 ed00 0008 3b01 0008 3b01 0008
built RW.flat : c004 0020 1901 0108 111c 0108 111c 0108
oracle RW.bin : c004 0020 ed00 0108 3b01 0108 3b01 0108
```
- **Initial SP word identical** (`0xC004 0020` LE = `0x2000_04C0`) for RO and RW — RAM
  layout / stack config match.
- Reset/NMI/HardFault vectors point into the correct image base (RO `0x0800_xxxx`,
  RW `0x0801_xxxx`) in both; only the exact handler offsets differ
  (`0x0119`/`0x1c11` built vs `0x00ed`/`0x013b` oracle), as expected for a newer
  toolchain + code. Structure matches; bytes do not (and were never expected to).

Board symbols present in `build/gale/RW/ec.RW.elf` (`arm-none-eabi-nm`):
`command_gale`, `board_no_charger`(+deferred), `set_ap_power_on/off`, `pd_snk_pdo`,
and the full `usb_spi_*` bridge (rx/tx/event/deferred/interface). The `pd_check_*` /
`pd_custom_vdm` callbacks are LTO-inlined into the PD task (hence no standalone
symbols) — their presence is proven by the successful link of `usb_pd_protocol.c`
against them with zero undefined references.

---

## Reproduce
```
cd /home/tim/local/gwifi/tmp/ec-legacy
git checkout spike-a-gale-base            # detached base 81ba8f9866 + board/gale port
make BOARD=gale CROSS_COMPILE=/usr/bin/arm-none-eabi- -j8 build/gale/ec.bin
# -> build/gale/ec.bin (131072 bytes), build/gale/RW/ec.RW.elf, build/gale/RO/ec.RO.elf
```
Base validation (proves the pinned tree itself is sound):
```
make BOARD=servo_micro CROSS_COMPILE=/usr/bin/arm-none-eabi- -j8 build/servo_micro/ec.bin
```
