# Divergence #10: captured "USB up at no-force boot" vs rebuilt not — EMULATION ARTIFACT

**Status:** RESOLVED 2026-06-09 = **emulation (phantom-boot-accessory) artifact, NOT a real
firmware divergence.** Decisive evidence below. Found via equivalence console-diff + USB_CNTR read.

## DECISIVE TEST (2026-06-09): equivalent under a real accessory
| stimulus | captured USB_CNTR | rebuilt USB_CNTR |
|----------|-------------------|------------------|
| no-force boot | 0xE400 | 0x0003 |
| **ForceAccessory (real debug accessory)** | **0xE400** | **0xE400** |

Under a REAL forced debug accessory BOTH firmwares are IDENTICAL (USB up). The difference exists
ONLY at no-force boot. But the no-force boot reaches SRC_ACCESSORY only because GaleAdc presents a
PHANTOM debug accessory whenever gale sources (Rd-band on CC while cc_pull==RP) — a real sink-only
gale at boot with no accessory attached reads CC open and would NEVER enter SRC_ACCESSORY. So the
captured's no-force USB-up is itself an emulation effect, and the captured-vs-rebuilt difference is
just the two builds classifying that PHANTOM accessory's borderline CC differently (DEBUG_ACC vs
AUDIO_ACC) — the known-immaterial [200,250)mV CC-threshold band from EQUIVALENCE-REVIEW-1. With a
real, unambiguous Rd/Rd accessory both classify DEBUG_ACC and enable CCD identically.

CONCLUSION: not a reconstruction bug. The firmwares are equivalent on the USB/CCD-enable path under
any real accessory; the no-force-boot difference is an artifact of the emulator's phantom accessory.
(This is evidence-based, unlike a bare "artifact" claim: the ForceAccessory-equivalence is the proof.)

----- original (pre-resolution) analysis kept for audit -----
**Status:** CONFIRMED behavioral divergence, found 2026-06-09 via equivalence console-diff +
hardware-register read. Stable (not a timing effect). Likely the ROOT of open divergence #7
(EP4/usb_spi) — if USB never initializes at boot, the USB device/CCD/raiden path can't behave
equivalently.

## What was found
At NORMAL boot (no debug accessory, no partner), reading the STM32 USB controller register
`USB_CNTR` (0x40005C40):

| firmware | USB_CNTR @ boot (2.5s AND 6.0s) | meaning |
|----------|-------------------------------|---------|
| **captured** (device dump) | **0xE400** | CTRM|PMAOVRM|ERRM|RESETM set — `usb_init` ran, USB active |
| **rebuilt** (ec/ @ firmware-gale-8281.B) | **0x0003** | FRES|PDWN — power-on reset default, `usb_init` never ran |

Corroborated by the console boot log: the **captured prints `USB init done`** during boot; the
**rebuilt does not**. Confirmed stable at 6.0s boot (rebuilt still 0x0003) — NOT a timing/late-init
effect.

Both firmwares reach the **same PD state** at boot (`C0 st16` on the console), so the divergence is
specifically in **whether USB gets initialized**, not in the PD state reached.

## Significance
The captured device firmware brings its USB device controller up at boot (so the CCD console /
raiden usb_spi bridge are immediately live). The reconstruction does not — its USB only comes up via
the (now-fixed) SNK_ACCESSORY/CCD trigger under a debug accessory. So on a normally-booted board the
reconstruction's USB/CCD is effectively dead until an accessory is attached, whereas the captured's
is live from boot. This plausibly explains the EP4/usb_spi stall recorded as divergence #7
(FINDINGS-usb-ccd.md): downstream USB behavior diverges because the precondition (USB initialized)
differs.

## Reproduce
```
cd gale-ec/renode
# read USB_CNTR after boot (fcall GDB stub): captured 0xE400, rebuilt 0x0003
# or via console boot log: captured prints "USB init done", rebuilt does not
uv run --python .venv python capture_console.py --bin <fw> --boot 2.0 --cmd "version" | grep -i "USB init"
```

## ROOT CAUSE (confirmed 2026-06-09 — with an important correction)
Both firmwares define `CONFIG_USB_INHIBIT_INIT` (rebuilt: board.h:38; captured: inferred — see
timing below), so NEITHER runs `usb_init` at HOOK_INIT. Confirmed: the rebuilt's HOOK_INIT list is
`board_init, adc_init, gpio_init, i2c_init, panic_init, tcpc_pre_init` — `usb_init` absent.

TIMING TEST (captured USB_CNTR vs boot duration) — the decisive evidence:
```
boot=0.05s 0.2s 0.5s 1.0s -> 0x0003   (USB NOT up early)
boot=2.5s              -> 0xE400      (USB comes up LATE, ~1-2s in)
```
USB comes up LATE, not at HOOK_INIT (which would be 0xE400 by 0.05s). So the captured brings USB up
via the **CCD path** (PD reaches a CCD-enabling accessory state ~1-2s -> ccd_set_mode -> usb_init),
WITH the inhibit config. The rebuilt reaches the SAME PD state (`C0 st16`) but its CCD path does NOT
call usb_init (stays 0x0003 through 6s).

=> The divergence is NOT the config (both inhibit HOOK_INIT). It is that the captured's normal-boot
PD/CCD path ENABLES CCD (-> usb_init) while the reconstruction's does not. So **removing
CONFIG_USB_INHIBIT_INIT would be the WRONG fix** (it would init USB early at ~0.001s, not matching
the captured's ~2s CCD-path init).

## FIX (reconstruction) — corrected
Make the reconstruction's normal-boot PD/CCD path enable CCD (call ccd_set_mode -> usb_init) the way
the captured does. This is the same family as the SNK_ACCESSORY work: the earlier fix made the
rebuilt bring USB up UNDER a forced debug accessory (ForceAccessory -> 0xE400), but at NORMAL boot
(no accessory) the captured still enables CCD and the rebuilt does not. NEXT: determine which state
the captured enters at normal boot that calls ccd_set_mode (SRC_ACCESSORY? a board CCD-default?),
and why the reconstruction's equivalent path doesn't. Likely the root of divergence #7. Do NOT touch
CONFIG_USB_INHIBIT_INIT.
