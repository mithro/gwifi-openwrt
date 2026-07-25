# Reconstruction divergence: missing `PD_STATE_SNK_ACCESSORY` (sink-side CCD trigger)

**Status:** FIXED 2026-06-08 (ec/ branch `gale-divergence-fixes`, commit 5120003). The rebuilt now
reaches `SNK_ACCESSORY` and brings USB up under a debug accessory (USB_CNTR=0xE400), matching the
captured; normal boot is unchanged (both reach SRC_ACCESSORY identically). See "Fix" below.
Originally CONFIRMED 2026-06-07 by the Renode equivalence harness.
**Severity:** functional — the reconstruction cannot enable Case-Closed Debug (CCD) / USB on
the real (sink-only) board; the captured device firmware can.

## What was found

Driving both firmwares with an identical Type-C **debug-accessory** stimulus
(`sysbus.adc ForceAccessory true` — both CC lines held in the Rd voltage band) and reading the
firmware's own `pd 0 state`:

| firmware | `pd 0 state` after ForceAccessory | USB_CNTR (0x40005C40) |
|----------|-----------------------------------|------------------------|
| **captured** (device dump 602a4614) | `Role: SNK-UFP State: SNK_ACCESSORY` | `0xE400` (USB up, IRQs enabled) |
| **rebuilt** (ec/ @ firmware-gale-8281.B, sha 6946bdf5) | `Role: SNK-UFP State: SNK_DISCOVERY` | `0x0003` (reset default — usb_init never ran) |

(`0x0003` = FRES|PDWN, the STM32 USB_CNTR power-on reset value, i.e. `usb_init` did not configure
the controller. `0xE400` = CTRM|PMAOVRM|ERRM|RESETM enabled = `usb_init` ran and USB is active.)

## Root cause

The two firmwares' PD state-name tables (extracted with `strings`) are **identical except for one
state**:

```
captured has:   SNK_ACCESSORY
rebuilt lacks:  SNK_ACCESSORY   (all 36 other states match exactly)
```

The captured device firmware implements `PD_STATE_SNK_ACCESSORY` — **sink-side** debug/audio
accessory detection. gale is a sink-only access point (board policy `board_no_charger` forces the
SINK role; it has no battery to source from), so it never enters the SOURCE side of the PD state
machine. The standard upstream CCD trigger is `PD_STATE_SRC_ACCESSORY` (usb_pd_protocol.c:1644-1664),
reachable only while **sourcing** — which gale never does. The captured firmware therefore carries
an extra **SNK_ACCESSORY** state so a sinking port can still detect the SuzyQ debug cable and call
`ccd_set_mode(ENABLED) -> usb_init`. The reconstruction (ec/ @ firmware-gale-8281.B) does not have
this state, so on the real board its CCD/USB is effectively dead code: `usb_init` is linked (because
CONFIG_CASE_CLOSED_DEBUG is compiled) but nothing reachable ever calls it.

`PD_STATE_SNK_ACCESSORY` is present in **none** of the local EC source trees
(ec / ec-gale / ec-legacy / ec-main) — the captured device was built from a gale-specific EC vintage
that added it.

## Why earlier "equivalence" missed it

Prior MMIO trace-diff rounds exercised console / battery / PD-contract / raiden paths but never the
sink-accessory path, so the missing state never affected an observable. The dedicated ForceAccessory
scenario is what surfaced it.

## Reproduce

```
cd gale-ec/renode
uv run --python .venv python capture_console.py --bin ../../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin \
    --mon 'sysbus.adc ForceAccessory true' --boot 2.0 --settle 0.3 --cmd "pd 0 state"   # -> SNK_ACCESSORY
uv run --python .venv python capture_console.py --bin ec-rebuilt.bin \
    --mon 'sysbus.adc ForceAccessory true' --boot 2.0 --settle 0.3 --cmd "pd 0 state"   # -> SNK_DISCOVERY
# state-name table diff:
strings <bin> | grep -E '^SNK_' | sort -u
```

## Exact enum position (reverse-engineered from the captured pd_state_names[])

The captured `pd_state_names[]` table is at **0x0800d638** (37 entries). `SNK_ACCESSORY` is at
**index 4**, inserted between `SNK_DISCONNECTED_DEBOUNCE` (3) and `SNK_HARD_RESET_RECOVER` (5);
every other state matches the upstream order exactly (so all states after index 3 are shifted +1
vs the reconstruction's 36-state enum — this is also why captured `pd 0 state` prints higher
`stN` numbers than the rebuilt). Full captured order: DISABLED, SUSPENDED, SNK_DISCONNECTED,
SNK_DISCONNECTED_DEBOUNCE, **SNK_ACCESSORY**, SNK_HARD_RESET_RECOVER, SNK_DISCOVERY, SNK_REQUESTED,
SNK_TRANSITION, SNK_READY, SNK_SWAP_INIT, SNK_SWAP_SNK_DISABLE, SNK_SWAP_SRC_DISABLE,
SNK_SWAP_STANDBY, SNK_SWAP_COMPLETE, SRC_DISCONNECTED, SRC_DISCONNECTED_DEBOUNCE, SRC_ACCESSORY,
SRC_HARD_RESET_RECOVER, SRC_STARTUP, SRC_DISCOVERY, SRC_NEGOCIATE, SRC_ACCEPTED, SRC_POWERED,
SRC_TRANSITION, SRC_READY, SRC_GET_SNK_CAP, DR_SWAP, SRC_SWAP_INIT, SRC_SWAP_SNK_DISABLE,
SRC_SWAP_SRC_DISABLE, SRC_SWAP_STANDBY, SOFT_RESET, HARD_RESET_SEND, HARD_RESET_EXECUTE,
BIST_RX, BIST_TX.

Behaviour (from the observable): on entry SNK_ACCESSORY calls `ccd_set_mode(ENABLED)` (USB
comes up, CNTR=0xE400), and the port is reached from `SNK_DISCONNECTED_DEBOUNCE` when both CC
lines read the Rd band (debug accessory) while sinking. The exact handler body still needs to be
read from the captured pd_task's case-4 disassembly to guarantee byte/behaviour-identical
equivalence (not just "reaches the state").

## Fix (reconstruction work required)

Restore `PD_STATE_SNK_ACCESSORY` to the gale reconstruction's `common/usb_pd_protocol.c` (and the
state-name table), matching the captured behaviour: a sinking DRP that sees both CC in the Rd band
(debug accessory) transitions to SNK_ACCESSORY and invokes `ccd_set_mode`. The exact handler must be
reverse-engineered from the captured dump's disassembly of the SNK_ACCESSORY case (or recovered from
the gale-vintage EC source if it can be located). This is a genuine reconstruction gap, not a
harness limitation: until SNK_ACCESSORY is restored, the rebuilt firmware is NOT functionally
equivalent to the captured device on the CCD/USB path, and the USB cluster (usb_init / ep0_rx /
usb_spi_deferred / usb_console) stays unreachable in the rebuilt.
