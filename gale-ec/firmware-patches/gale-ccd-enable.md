# Firmware reconstruction patch: restore Case-Closed-Debug (USB) to board/gale

Applies to the confirmed-equivalent recreation `ec/` @ `firmware-gale-8281.B`
(the gale factory-branch vintage). `board/gale/` is the reconstruction working copy
(untracked in `ec/`), so this records the edits as a reproducible patch.

**Why:** the original dump retains `usb_init` (the USB device controller power-on:
USB_CNTR/ISTR written 4×, USB_BTABLE 2×) but the CCD-less recreation garbage-collected
it (2/2/0), because `case_closed_debug.c` — the only STM32 caller of `usb_init` — was
not compiled. See `../renode/FINDINGS-usb-ccd.md`.

**Verification after applying (build `make BOARD=gale build/gale/ec.bin`):**
- `usb_init` + `ccd_set_mode` present in both RO/RW symbol tables (were absent).
- USB register-write literal counts now **match the original**: CNTR 4=4, ISTR 4=4,
  BTABLE 2=2.
- Still boots clean in Renode; `battery.py` still **8 PASS / 2 XFAIL / 0 FAIL**.
- PD state machine now advances `st2 → st15` (SRC states compiled in), like the
  original (`st2 → st16 → st17`), instead of being stuck at `st2`.

All changes are confined to `board/gale/`; `common/` is untouched and gale's validated
input-current/AP-power behavior is unchanged (no `CONFIG_CHARGE_MANAGER`).

---

## 1. board/gale/board.h — enable CCD (after `#define CONFIG_USB_INHIBIT_INIT`)

```c
/*
 * Case Closed Debugging — the original gale firmware compiles
 * common/case_closed_debug.c (proven: the original dump retains usb_init —
 * USB_CNTR/ISTR x4, USB_BTABLE x2 — which the CCD-less reconstruction GC'd). CCD
 * powers the USB device controller (EC/AP consoles + the raiden SPI bridge, which
 * IS case_closed_debug.c's ccd_usb_spi) on Type-C debug-accessory detection.
 *
 * gale is sink-only with no battery and no charger IC (its 4-task list has no
 * charger task), so CONFIG_CHARGE_MANAGER is NOT enabled — that would change the
 * validated input-current/AP-power flow and pull in a charge subsystem absent from
 * this design. The two charge_manager-era calls the CCD SRC_ACCESSORY path makes
 * (typec_set_input_current_limit, charge_manager_update_dualrole) are satisfied by
 * sink-only board stubs in usb_pd_policy.c, keeping all CCD changes confined to
 * board/gale and leaving common/ and gale's validated behavior untouched.
 */
#define CONFIG_CASE_CLOSED_DEBUG
```

## 2. board/gale/board.c — remove the duplicate raiden USB-SPI config

`case_closed_debug.c` declares `USB_SPI_CONFIG(ccd_usb_spi, USB_IFACE_SPI, USB_EP_SPI)`
and `ccd_set_mode()` enables it, so the board-level duplicate must be removed (else
`multiple definition of ep_4_tx / iface_3_request / usb_desc_iface3_*`). Replace

```c
USB_SPI_CONFIG(usb_spi, USB_IFACE_SPI, USB_EP_SPI);
```

with a comment noting iface3/ep4 is now owned by `ccd_usb_spi`. (`usb_spi_board_enable`
/`usb_spi_board_disable` are callbacks taking `config` as a parameter — they do not
reference the removed `usb_spi` symbol, so they are unaffected.)

## 3. board/gale/usb_pd_policy.c — sink-only CCD glue

Add `#include "charge_manager.h"` and, after `pd_set_input_current_limit`:

```c
void typec_set_input_current_limit(int port, uint32_t max_ma,
				   uint32_t supply_voltage)
{
	pd_set_input_current_limit(port, max_ma, supply_voltage);
}

void charge_manager_update_dualrole(int port, enum dualrole_capabilities cap)
{
	/* No charge manager on gale; nothing to update. */
}
```
