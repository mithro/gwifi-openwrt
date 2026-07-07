# Gale puck netboot flash — operator runbook

A fast (**4 m 01 s**, verified) libusb-only process to flash dev-signed netboot
firmware onto Google Wifi (gale, IPQ4019) pucks over the EC `usb_spi` bridge.

`flash_puck_usb.py` is the single, verified tool (pyusb only — no pyserial). It
owns every hardware interaction: read, EC console, park, flash, boot-verify.
The build stage reuses the `galeflash` pipeline (host x86_64 futility/cbfstool).

---

## 0. The one thing to know: the rail-bounce settle

Every flash session parks the AP then re-raises the flash rail (SYS_PWR_EN +
VDD_3P3). That rail bounce plants two one-shot events on the shared SPI bus:

* **Z** — at rails-up +0.47 s the bus dies to zeros IF small SPI frames are in
  flight at that instant;
* **H** — at +1.9–3.3 s an EC task-starvation storm kills in-flight transactions.

Both pass harmlessly when the bus is **idle**. `flash_puck_usb.py` therefore
idles **5 s after every ENABLE** (`SETTLE_AFTER_ENABLE_S`) and re-checks RDID as
a canary before any real traffic. Fully root-caused and measured — see
`tools/EC-USB-SPI-BUG.md`. With the settle, a session runs 135 k+ transactions
clean; a wedge, if one ever slips through, is **fatal** (no silent retry).

No special power supply is required for flashing. (Booting the AP for
`verify-boot` still needs the puck's normal USB-C power.)

---

## 1. Build the per-puck image (host, offline — no hardware)

Preserves the puck's own RO (VPD/HWID); rewrites only GBB rootkey + FW_MAIN_A/B +
VBLOCK_A/B; re-signs at keyblock **flags 7** (`!DEV DEV !REC`, boots in normal mode).

```
python3 tools/fleet/build_gale_fleet_image.py <this-puck-dump.bin> out.bin
```

Get `<this-puck-dump.bin>` by reading the puck first (step 2 read) — the build
starts from the puck's own live dump so its identity is preserved.

---

## 2. Read, flash, verify (libusb — all one tool)

**Read / back up** (parked + settled session, double-read confirmed):
```
python3 tools/flash_puck_usb.py read gale-backup.bin           # full 8 MiB
python3 tools/flash_puck_usb.py read vpd.bin --offset 0x3e0000 --length 0x4000
```

**Flash** — dry-run first (no writes; prints the RO-last plan):
```
python3 tools/flash_puck_usb.py flash out.bin
```
Plan: `RW_SECTION_A` (0x400000) → `RW_SECTION_B` (0x580000) → `GBB`
(0x301000..0x3e0000, needs `--allow-ro`). RO-last so an interrupted flash never
leaves a valid RO pointing at a half-written RW.

Commit + boot-verify:
```
python3 tools/flash_puck_usb.py flash out.bin --commit --allow-ro --verify-boot
```
- One parked + settled session per region; erase (4 KiB sectors) → program →
  **byte-for-byte read-back verify**. No silent retries; a wedge canary aborts loud.
- `--verify-boot`: EC reboot → re-enumerate → capture the AP boot log →
  classify GOOD/BAD/UNDECIDED (exit 0/2/3). Add `--boot-log FILE` to save it.

Validated on hardware 2026-07-07 (pilot puck 2712HW0072Z): 3 regions
erased/programmed/verified + EC reboot + AP boot verdict **GOOD** in
**4 m 01 s**, ~365 k transactions, zero anomalies.

**EC console** (no kernel tty needed):
```
python3 tools/flash_puck_usb.py ec sysinfo gettime "gale power"
```

---

## 3. Recovery / diagnostics

| Symptom | Action |
|---|---|
| `/dev/ttyUSB0/1` gone after a libusb run | device-scoped re-probe: `echo 0 > /sys/bus/usb/devices/<dev>/authorized; sleep 2; echo 1 > …` (the tool doesn't need the ttys; this is only for other tooling) |
| EC seems wedged / unresponsive | `python3 tools/flash_puck_usb.py verify-boot` (EC reboot recovers it) |
| Rig itself is unreachable | PoE power-cycle — see `tools/RIG-POWER-CYCLE.md` |
| Characterize the small-frame wedge window | `python3 tools/flash_puck_usb.py budgetprobe` (research/diagnostic) |

---

## 4. Status

| Stage | Status |
|---|---|
| Build → futility-verified flags-7 image | ✅ offline |
| Read (double-read confirmed) | ✅ hardware |
| Flash write (erase+program+verify, RO-last) | ✅ byte-identical on hardware |
| EC reboot + re-enumerate | ✅ reliable on hardware |
| AP boot verification | ✅ GOOD on hardware |
| Full flash + verify + boot, timed | ✅ **4 m 01 s** end-to-end |
