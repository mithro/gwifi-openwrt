# Finding: rebuilt gale firmware is missing `CONFIG_CASE_CLOSED_DEBUG` (USB/CCD)

Surfaced by the Renode differential-equivalence harness while trying to exercise
the USB device controller (USB UART consoles + raiden SPI bridge). This is a
genuine **functional** divergence between the original dump and the reconstruction
— recorded here rather than papered over.

---

## STATUS SUMMARY (read first — reconciled 2026-06-06, supersedes all conflicting notes below)

This file accreted contradictory claims over many sessions ("USB EQUIVALENCE PROVEN" vs a
later "NOT functionally equivalent"). The following is the single reconciled status, scoped
precisely to what the runnable evidence (`usb_host.py` on both binaries) actually shows.
Where older sections below disagree, **this section wins**; they are kept only as audit trail.

**What is EQUIVALENT (live, exercised end-to-end on BOTH images via `usb_host.py`):**
* **Device descriptor — byte-identical.** All 18 bytes match; idVendor 0x18d1 / idProduct
  0x500f on both. (Full 18-byte compare, not just the ID.)
* **Config descriptor — header + topology match.** bLength=9, bDescriptorType=2,
  wTotalLength=78, bNumInterfaces=4 on both (console if00 / AP if01 / unused / raiden if03).
  The **full** config body is NOT byte-compared and is NOT expected identical: the raiden
  endpoint-address byte differs (original EP3 vs rebuilt EP4 — see below).
* **USB UART console (EP1/if00) — byte-identical.** Both stream `"RST EP0 3220\r\n"`
  (14 bytes) on EP1.
* **raiden SPI bridge over USB (if03) — both return JEDEC `ef4017`.** USB_SPI_REQ_ENABLE
  then RDID (write 0x9F / read 3) over the raiden bulk endpoint returns status=SUCCESS +
  `ef4017` (W25Q64FV) on BOTH — a real SPI2 transaction transported over USB end-to-end,
  **not** a hardcoded value (the `GaleSpiFlash` JEDEC state machine was falsification-checked
  by the no-shortcuts agent). Reproducible (`window=late`/`window=early` per image).

**What DIVERGES (real source-version differences — documented, not papered over):**
1. **raiden endpoint number: original EP3 vs rebuilt EP4** (`USB_EP_SPI` = 3 vs 4). This is
   why the full config descriptor is not byte-identical.
2. **usb_spi readiness/stability timing.** The original's usb_spi isn't armed until ~1.2 s
   after SPI_ENABLE and is stable thereafter, so it answers RDID in the **late** window
   (after full enumeration). The rebuilt answers immediately but its usb_spi state
   **degrades after ~1 s**, so it answers only in the **early** window (RDID right after
   SPI_ENABLE). `usb_host.py` fires both windows and reports which one each image used —
   so the divergence is *visible in the tool output*, not hidden. Both still return `ef4017`.
3. **Autonomous USB bring-up.** The ORIGINAL reaches `usb_init` on its own PD path
   (st2→st16→st17→"USB init done", 0 panics over 5 s). The REBUILT does **not** bring up
   `usb_init` autonomously (st2→st15→st16 then stalls); it needs the debug-accessory CC
   forced (`--mon "sysbus.adc CcPullAddress 0x20001107"`). Root cause = PD/CCD source-version
   skew (the reconstruction's `usb_pd_protocol.c`/CCD plumbing is a newer vintage than the
   2016 original). This is the divergence the CORRECTION section below correctly identified;
   it stands.

**Bounded conclusion (honest):** the rebuilt's USB *function* — enumeration, USB UART
console, and the raiden SPI bridge — is **equivalent to the original** once the USB
controller is up, each within its own readiness window. The rebuilt is **NOT** equivalent
in **autonomous PD/CCD bring-up** (needs forced debug accessory) nor in raiden **endpoint
number** / **usb_spi stability timing**. These are real reconstruction/source-version deltas,
reserved (with AP boot and USB-PD live negotiation) as documented bounded gaps — not claimed
as identical.

* **FIXED + verified:** the reconstruction was missing `CONFIG_CASE_CLOSED_DEBUG`;
  restored (board/gale only) so `usb_init`/CCD is present and the USB register
  footprint matches the original (CNTR/ISTR ×4, BTABLE ×2). Also fixed the Renode
  TIM2 clock (10→48MHz). battery still 8 PASS/2 XFAIL/0 FAIL.

## ⚠️ CORRECTION (independent verification, later): the EP4 fault is a RECONSTRUCTION divergence, NOT an emulation artifact

> **SCOPE NOTE (2026-06-06):** this section's core finding — that the divergence is a real
> reconstruction defect, NOT an emulator artifact (the original runs the same path clean in
> this harness while the rebuilt stalls/panics) — **stands and is correct**. But its blanket
> conclusion "the rebuilt CANNOT exercise live USB / is NOT functionally equivalent on USB"
> is now **narrowed**: with the debug accessory forced and the raiden RDID fired in the
> rebuilt's early usb_spi window, the rebuilt DOES enumerate, stream its USB console, and
> return raiden `ef4017` (see the reconciled STATUS SUMMARY above). The genuine divergence is
> specifically **autonomous PD/CCD bring-up** + raiden **endpoint number** + **usb_spi
> stability timing** — not a wholesale inability to do live USB.

An independent adversarial verification agent + a direct test **retracted** the
"emulation timing-race artifact" conclusion below. Decisive test in the SAME Renode
harness, autonomous boot, no dynamic CC:
* **ORIGINAL dump (v1.1.5337):** st2 → st16 → st17 → **"USB init done"** — brings up
  the USB device controller (the CCD/usb_init path) **cleanly, 0 panics over 5 s**.
* **REBUILT (CCD-enabled reconstruction):** st2 → st15 → **st16, then STALLS** — never
  prints "USB init done", never reaches st17; and PANICS when the debug-accessory path
  is forced via dynamic CC.

A pure *emulator* timing-fidelity bug would corrupt **both** images on the same models.
It does not — the original runs the same path clean in this very harness. Therefore the
EP4/usb_spi fault is a **real functional divergence of the reconstruction**, almost
certainly the **source-version skew** already documented here (the reconstruction's
`common/usb_pd_protocol.c` is the 8281.B-tip ~2021 version whose SRC_ACCESSORY→CCD path
differs from the 2016 original's; this tree even required `CONFIG_CHARGE_MANAGER` +
folding raiden onto `ccd_usb_spi` to build CCD at all). The "timing-sensitivity" (panic
moves under instrumentation) is real but only means the *manifestation* is timing-
dependent — the underlying defect is in the rebuilt firmware's PD/CCD/USB-bring-up, not
in Renode. **The earlier "bounded emulation gap" framing for raiden-over-USB is WRONG
and retracted.** Correct status: the reconstruction is **NOT functionally equivalent**
to the original on USB bring-up; closing it requires source-version alignment of the
PD/CCD/raiden plumbing to the original's vintage (or obtaining the original's exact
source). The original firmware *can* be used to exercise live USB in this harness; the
rebuilt cannot until the divergence is fixed.

## (RETRACTED) EP4 raiden bring-up: a timing-race context corruption (bounded emulation gap)

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
