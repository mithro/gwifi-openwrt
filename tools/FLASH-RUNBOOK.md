# Gale puck netboot flash — operator runbook

A fast (<5 min on a healthy rig), reliable, libusb-only process to flash dev-signed
netboot firmware onto Google Wifi (gale, IPQ4019) pucks over the EC usb_spi bridge.

`flash_puck_usb.py` is self-contained (pyusb only — no pyserial/serial). The build
stage reuses the proven `galeflash` pipeline (host x86_64 futility/cbfstool).

---

## 0. HARD PREREQUISITE (electrical, measured)

**The puck MUST have a real 5 V / ≥2.5 A USB-C PD power source.**

A SuzyQ debug cable on a Pi USB-A port sags to ~4.28 V / ~1.5 A under load
(measured via the EC's own `gale` readout: `cc 924mV(1500mA)`, `vbus 4281mv`).
At that voltage the EC will **not** boot the AP (verify-boot gets 0 bytes — confirmed
by both the libusb tool and the proven pyserial tool) **and** the under-powered AP
intermittently wakes and contends the SPI bus mid-write (`RDID=000000`), collapsing
the per-session transaction budget from ~135000 (healthy) to ~1000 (starved) and
forcing the slow adaptive-downshift path (~50 min for a full image instead of ~2–3 min).

Both symptoms share this one cause. Fix the power first. Everything below assumes it.

If a puck is wedged from a prior interrupted run: power-cycle it (a USB reset /
EC `reboot` does NOT restore the degraded transaction budget — only a real
power-cycle does).

---

## 1. Build the per-puck image (host, offline — no hardware)

Preserves the puck's own RO (VPD/HWID); rewrites only GBB rootkey + FW_MAIN_A/B +
VBLOCK_A/B; re-signs at keyblock **flags 7** (`!DEV DEV !REC`, boots in normal mode).

```
python3 tools/fleet/build_gale_fleet_image.py <this-puck-dump.bin> out.bin
```

Validated 2026-07-06: a fresh build from a stock dump passes `futility verify`
(`Flags: 7 !DEV DEV !REC`, `Body verification succeeded` both slots) and the
diff-gate (only GBB/VBLOCK/FW_MAIN changed; RO_VPD/RW_VPD/RO_FRID untouched).

To get `<this-puck-dump.bin>`: read the puck first (step 2 read, below) — the build
starts from the puck's own live dump so its identity is preserved.

---

## 2. Flash (libusb) — RO-last, adaptive, fail-loud

Dry-run first (no writes — prints the RO-last plan):
```
python3 tools/flash_puck_usb.py flash out.bin
```
Expected plan: `RW_SECTION_A` (0x400000) → `RW_SECTION_B` (0x580000) → `GBB`
(0x301000..0x3e0000, needs `--allow-ro`). RO-last so an interrupted flash never
leaves a valid RO pointing at a half-written RW.

Commit + boot-verify:
```
python3 tools/flash_puck_usb.py flash out.bin --commit --allow-ro --verify-boot
```
- Sector-erase only (0x20, proven low-current; block-erase browns out a weak rail).
- Large 1.5 MiB sessions on a healthy rig (few sessions, fast); **adaptive downshift**
  (binary split to a 4 KiB floor) rides through any transient contention, re-verifying
  each piece. Fails LOUD only when a 4 KiB piece cannot be written+verified.
- Every piece is read-back-verified against the source. No silent retries.

Validated on hardware 2026-07-06: a real 128 KB destructive `--commit` write+verify+
restore completed **byte-identical** (even on the degraded rig, via downshift).

`--verify-boot`: EC reboot → re-enumerate (reliable) → capture the AP boot log →
classify GOOD/BAD/UNDECIDED (exit 0/2/3). Needs the AP to boot ⇒ needs step 0's power.

---

## 3. Recovery / diagnostics

| Symptom | Tool / meaning |
|---|---|
| `/dev/ttyUSB0/1` gone after a libusb run | `python3 tools/greattach.py` (reattach console kernel driver) |
| Need a clean USB re-enumerate (no EC reset) | `python3 tools/greset.py` |
| Measure the current per-session write budget | `python3 tools/flash_puck_usb.py budgetprobe` (large = healthy) |
| `RDID=000000 ... AP woke and is contending` | under-powered AP — see step 0 |
| `WREN did not latch WEL` | session budget hit — the downshift handles it; if persistent, power-cycle |

---

## 4. What is proven vs. gated

| Stage | Status |
|---|---|
| Build → futility-verified flags-7 image | ✅ demonstrated offline |
| Flash write (erase+program+verify) | ✅ byte-identical on hardware |
| RO-last plan on the built image | ✅ demonstrated offline |
| EC reboot + re-enumerate | ✅ reliable 3/3 on hardware |
| `<5 min` full-image timing | ⏸ needs a healthy (properly powered) rig |
| AP boot verification | ⏸ needs step 0's 5 V/≥2.5 A source |

The two gated rows are the same electrical prerequisite (step 0), not code.
