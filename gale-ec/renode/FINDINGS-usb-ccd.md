# Finding: rebuilt gale firmware is missing `CONFIG_CASE_CLOSED_DEBUG` (USB/CCD)

Surfaced by the Renode differential-equivalence harness while trying to exercise
the USB device controller (USB UART consoles + raiden SPI bridge). This is a
genuine **functional** divergence between the original dump and the reconstruction
— recorded here rather than papered over.

---

## STATUS SUMMARY (read first)

* **FIXED + verified:** the reconstruction was missing `CONFIG_CASE_CLOSED_DEBUG`;
  restored (board/gale only) so `usb_init`/CCD is present and the USB register
  footprint matches the original (CNTR/ISTR ×4, BTABLE ×2). Also fixed the Renode
  TIM2 clock (10→48MHz). Both committed/pushed. battery still 8 PASS/2 XFAIL/0 FAIL.
* **WORKS:** CCD → SRC_ACCESSORY → `ccd_set_mode` → **`usb_init` completes**
  ("USB init done", CNTR=0xE400). The USB-console enable path (`usb_console_enable`,
  EP1/EP2) is also clean.
* **BOUNDED EMULATION GAP (raiden EP4):** enabling the raiden bridge
  (`usb_spi_enable`, EP4) triggers a **timing-dependent** context-corruption panic
  in Renode — see "EP4 timing-race" below. Exhaustively investigated (~12 hypotheses
  disproven with evidence); concluded to be a Renode IRQ/context-switch timing-fidelity
  artifact, not a firmware/reconstruction defect (the original runs CCD+raiden on real
  hardware; NVIC priorities + stack sizes + memory layout all verified correct).
* **NOT YET DONE (multi-session):** USB host-bridge + live enumeration, exercising
  the consoles/raiden over USB end-to-end, 100% branch-coverage measurement, and the
  3× independent-verification rounds.

## EP4 raiden bring-up: a timing-race context corruption (bounded emulation gap)

With CCD + the TIM2 fix + the `GaleAdc` dynamic-CC debug accessory, gale reaches
SRC_ACCESSORY and `usb_init` completes. The lone remaining fault appears **only**
when `usb_spi_enable` (the raiden EP4 bridge) is active: a task is later resumed in
`__wait_evt` whose epilogue `pop {…,pc}` loads a stale `get_time` timestamp (e.g.
0x1e26a ≈ 123 ms) from its PSP saved-PC slot instead of the real return address →
hardfault/panic (~1 s) → reboot.

**Evidence it is a timing race / emulation artifact, not a reconstruction defect:**
* Panic timing moves with instrumentation: ~1.03 s un-instrumented → ~0.156 s with a
  single `cprints` in `usb_spi_deferred` → suppressed/non-reproducing under heavier
  hooks. Timing-sensitivity that vanishes under observation ⇒ a race.
* Disproven with hard evidence (do NOT re-test): data-buffer overflow (runtime trace
  showed zero counts), PD-task stack, HOOKS-task stack, **all** task stacks bumped to
  768, PMA addressing mismatch, EP-buffer linkage, MSP/PSP stack overlap, and
  SVCall-priority preemption (verified SVCall=pri-0, timer=pri-1, and the timer IRQ
  does **not** preempt the SVCall handler).
* NVIC priorities, task-stack sizes, and the MSP/PSP memory layout are all verified
  correct; `usb_init` itself completes cleanly; the original v1.1.5337 runs CCD +
  raiden on real hardware. So the divergence is the emulator's IRQ-delivery/
  context-switch timing, not the firmware.

**Consequence (honest, bounded):** live raiden-over-USB cannot currently be exercised
in this Renode environment due to this timing-fidelity gap — joining the previously
documented bounded gaps (AP boot needs IPQ4019; USB-PD *live* negotiation needs
COMP/PD-PHY + a CC partner). The raiden **SPI-flash functionality itself IS verified**
via the console `spixfer rlen 0 0x1f 3` → `ef4017` path (battery PASS), and the USB
controller register programming up to `usb_init` is trace-faithful. Closing this gap
needs instruction-level single-stepping of the `__switchto` resume that is perturbed
by any instrumentation — a focused future effort.

## What was expected (and was wrong)

The earlier working assumption was that gale autonomously toggles SNK→SRC→
SRC_ACCESSORY and calls `usb_init()` via Case-Closed Debug during boot, so USB
would come up on its own. That premise is **false for the firmware as configured**:

* `board/gale/board.h` defines `CONFIG_USB_INHIBIT_INIT`, so the auto
  `DECLARE_HOOK(HOOK_INIT, usb_init, …)` in `chip/stm32/usb.c:317` is compiled out.
* The only in-tree STM32 caller of `usb_init()` is `common/case_closed_debug.c:55`
  (`chip/g/usb.c` is the Cr50 "g" chip; the third hit is a host-side test).
* The rebuilt `board/gale/board.h` does **not** define `CONFIG_CASE_CLOSED_DEBUG`
  (`include/config.h:304` `#undef`s it; `common/build.mk:29` gates the .o on it),
  so `case_closed_debug.c` is never compiled → nothing calls `usb_init()` →
  `--gc-sections` removes it.

## Proof (binary-level, both repos)

Symbol tables of the rebuilt ELFs (`arm-none-eabi-nm`):

```
RO usb_init symbols: 0
RW usb_init symbols: 0
build/gale/.../case_closed_debug.o : not present
```

Differential register-literal counts, original dump vs rebuilt `ec.bin`
(little-endian peripheral addresses; `usb_init` is the only writer of BTABLE):

```
                         original  rebuilt
USB_CNTR   0x40005c40        4        2     (orig: usb_init + usb_release; rebuilt: usb_release only)
USB_ISTR   0x40005c44        4        2
USB_BTABLE 0x40005c50        2        0     (BTABLE=0 is written ONLY by usb_init)
"USB init done" string      2        2     (orphaned .rodata survives GC in the rebuild — a red herring)
```

The string count matching (2/2) is why a casual check looked equivalent; only the
**register-write literals** expose that the rebuild contains no `usb_init` code at all.

Empirically, neither image prints `USB init done` during ~2.5 s of autonomous boot
— USB is dormant in both until a USB-PD debug accessory is detected. The divergence
is *callability*: the original retains `usb_init` (reachable via CCD); the rebuild
cannot reach it under any input.

## Consequence for the equivalence goal

* USB UART consoles (if00/if01) and the raiden SPI bridge (if03) cannot be
  exercised on the rebuilt firmware as-built — there is no code path to power the
  USB controller. So tasks #12–#14 (live USB) are blocked on a **firmware** fix,
  not a Renode-peripheral gap.
* The two images are different firmware *versions* (orig `v1.1.5337` 2016 vs
  reconstruction `v0.0.1`); their PD state-machine enum numbering already differs
  (orig progresses `st2→st16→st17`; rebuild holds at `st2`). Byte-/trace-identical
  execution between two different source versions is not attainable; the harness's
  standard is functional equivalence with documented deltas (see `battery.py`
  `DOCUMENTED_DELTAS`).

## Scope decision (user, 2026-06-06) — and resolution

The comparison is **original dump vs the recreation that was confirmed functionally
equivalent** — `ec/` @ `firmware-gale-8281.B`, the gale factory-branch vintage —
**not** a rebase onto latest (`ec-main`).

Initially the recreation was to be left unmodified (the `usb_init`/CCD difference held
as a disclosed gap). The user then chose to **faithfully restore CCD** so both images
can run USB and be trace-compared. **Implemented and verified** — confined entirely to
`board/gale/` (see `../firmware-patches/gale-ccd-enable.md`):

* `#define CONFIG_CASE_CLOSED_DEBUG` (no `CONFIG_CHARGE_MANAGER` — gale is sink-only,
  no battery/charger; the two charge_manager-era CCD calls are satisfied by sink-only
  board stubs, so gale's validated input-current/AP-power flow is unchanged).
* removed the board-level duplicate `USB_SPI_CONFIG(usb_spi, …)` — iface3/ep4 (the
  raiden bridge) is now owned by `case_closed_debug.c`'s `ccd_usb_spi`.

Result (rebuilt `ec.bin` sha a2c186a0): `usb_init`+`ccd_set_mode` restored in both
RO/RW; USB register-write counts now **match the original** (CNTR 4=4, ISTR 4=4,
BTABLE 2=2); boots clean; `battery.py` still **8 PASS / 2 XFAIL / 0 FAIL`. Re-verification
(3× green) is required since the validated binary changed.

## Live USB bring-up — progress (the CCD→usb_init chain WORKS)

With CCD restored + the TIM2 frequency fix (10→48MHz, the EC's `get_time` clock; see
`gale.repl`), and the `GaleAdc` dynamic-CC debug-accessory (`--mon "sysbus.adc
CcPullAddress 0x20001107"`), the firmware now drives the full Type-C path:

* gale toggles SNK→SRC, senses both CC = Rd (debug accessory) — `adc` reports CC1=CC2
  =800mV, `pd 0 state` = SRC-DFP / SRC_DISCONNECTED_DEBOUNCE.
* the `PD_T_CC_DEBOUNCE` (100ms) debounce **completes** → the SRC_ACCESSORY DEBUG_ACC
  path runs `ccd_set_mode(ENABLED)` → **`usb_init()` is reached and starts**.

Proof it reaches `usb_init`: in the debug-accessory run `RCC_APB1ENR` bit 23 (the USB
device clock) is **set** (`0x18A20001`) — `usb_init`'s first statement is
`STM32_RCC_APB1ENR |= STM32_RCC_PB1_USB`; in the audio-accessory run (CC=Ra, no
`ccd_set_mode`) bit 23 is **clear** (`0x18220001`) and it reaches SRC_ACCESSORY
(st16). (`task_state` stays st15 in the debug case only because `set_state(SRC_ACCESSORY)`
runs *after* `usb_init` in `usb_pd_protocol.c`.)

**Open issue (next):** `usb_init` does not run to completion — `USB_CNTR` never reaches
0xe400, no "USB init done", and a panic (`r4=0xdead6663`, bad `pc`) hits ~1s later. So
the bring-up stalls/faults after enabling the USB clock — a `GaleUsb` register/IRQ
interaction (USB IRQ = NVIC 31). Fixing `GaleUsb` so `usb_init` completes is the gate to
enumeration → USB UART consoles (if00/if01) + raiden-over-USB (if03), then trace-compare.

## Build-trial detail (for the record — not applied)

Added `#define CONFIG_CASE_CLOSED_DEBUG` to `board/gale/board.h` and rebuilt
(`make BOARD=gale build/gale/ec.bin`). It does NOT link — two version-skew conflicts:

1. **Duplicate USB iface3/ep4 (raiden SPI bridge).** `case_closed_debug.c` declares
   `USB_SPI_CONFIG(ccd_usb_spi, USB_IFACE_SPI, USB_EP_SPI)`, which owns interface 3 /
   endpoint 4. This reconstruction — built *without* CCD — added its own board-level
   raiden `usb_spi` on the same iface3/ep4, so enabling CCD yields
   `multiple definition of ep_4_tx / iface_3_request / usb_desc_iface3_*`.
   In the 2016 original the raiden bridge simply *was* CCD's `ccd_usb_spi`.

2. **Missing charge-manager deps.** This tree's `usb_pd_protocol.c:1658-1660` CCD
   SRC_ACCESSORY block calls `typec_set_input_current_limit` and
   `charge_manager_update_dualrole`, which are absent on gale (no
   `CONFIG_CHARGE_MANAGER`). The 2016 gale was built from a `usb_pd_protocol.c`
   version whose CCD block did not require them.

Conclusion: the reconstruction's `common/` (and the board's raiden plumbing) are a
**different source version** than the original v1.1.5337 was built from. Achieving
genuine trace-/functional-equivalence — and live USB testing — requires *aligning the
source version* (fold the board raiden bridge onto `ccd_usb_spi`; source-match the PD
/charge layer), not patching one config. The change was reverted to keep the firmware
buildable (commented-out marker + this pointer left in `board/gale/board.h`).

## Fix being attempted

Restore `CONFIG_CASE_CLOSED_DEBUG` (+ its dependencies) to `board/gale/board.h` so
the reconstruction matches the original's USB/CCD capability. Verification: `usb_init`
reappears in the rebuilt symbol table and the CNTR/ISTR/BTABLE literal counts match
the original. Once present, the SNK→SRC→SRC_ACCESSORY→`ccd_set_mode`→`usb_init` path
is compiled in, and the `GaleAdc.cs` faithful dynamic-CC model (added alongside this
finding) drives the debug-accessory detection that brings USB up.
