# gale AP SPI-flash toolkit (libusb / EC `usb_spi` bridge)

Read, write, and verify the Google Wifi "gale" (IPQ4019) **8 MiB Winbond
W25Q64** AP boot flash through the on-board **EC** (STM32F072CB) over a SuzyQ /
SuzyQable USB-C debug cable. The EC enumerates as USB `18d1:500f` and exposes
the chromiumos-EC `usb_spi` **V1** bridge on interface 3.

Everything is **one self-contained tool, `flash_puck_usb.py`** (pyusb only — no
pyserial, no flashrom). It is the verified path: it parks the AP itself, idles
out the rail-bounce event windows (see `EC-USB-SPI-BUG.md`), and
read-back-verifies every write. It replaced an earlier zoo of scripts
(`raiden*.py`, `chunk_read.py`, `gflash.py`, `gserial*.py`, `ec_park.py`,
`ec_console.py`, `greset.py`, `greattach.py`, `flash_diff.py`) — all removed.

> **NEVER use flashrom on gale** (distro or flashrom-cros). It failed both ways
> on this hardware: `-E/-w` trips on the `SRP1` status-register lock and its
> erase silently no-ops; its raiden read path returned silent `0x00` bursts
> with exit 0 (corrupt backups that looked successful). Always this tool.

## Commands

```
# EC console (no kernel tty needed) — park, inspect, uptime
python3 flash_puck_usb.py ec "gale power off"
python3 flash_puck_usb.py ec sysinfo gettime "gale power"

# Read / back up (parked + settled session, double-read confirmed)
python3 flash_puck_usb.py read gale-backup.bin                    # full 8 MiB
python3 flash_puck_usb.py read vpd.bin --offset 0x3e0000 --length 0x4000

# Flash a built image (RO-last; dry-run without --commit)
python3 flash_puck_usb.py flash out.bin                           # dry-run plan
python3 flash_puck_usb.py flash out.bin --commit --allow-ro --verify-boot

# Boot verification alone (EC reboot -> capture AP log -> GOOD/BAD/UNDECIDED)
python3 flash_puck_usb.py verify-boot --boot-log boot.log

# Research: characterize the small-frame rail-bounce wedge window
python3 flash_puck_usb.py budgetprobe
```

Exit codes: `flash`/`read`/`ec` 0 = ok, non-zero = fail-loud. `verify-boot`
0 = GOOD, 2 = BAD, 3 = UNDECIDED.

## Why it is reliable

- **Rail-bounce settle** — every session idles 5 s after ENABLE so the Z
  (bus-to-zeros) and H (EC task-starvation) one-shot events pass with the bus
  quiet, then re-checks RDID as a canary. Fully root-caused and measured in
  `EC-USB-SPI-BUG.md`. A wedge, if one ever slips through, is **fatal** — no
  silent retry.
- **RO-last write order** — `RW_SECTION_A` → `RW_SECTION_B` → `GBB`, so an
  interrupted flash never leaves a valid RO pointing at a half-written RW. The
  bottom 4 MiB (RO/bootblock) is gated behind `--allow-ro`.
- **Verify everything** — every written piece is read back and compared to
  source; reads are double-read confirmed.

Verified end-to-end on hardware (2026-07-07, pilot 2712HW0072Z): full flash +
verify + AP boot **GOOD in 4 m 01 s**, ~365 k transactions, zero anomalies.

## Hardware facts worth knowing

- **The SPI bus is shared with the AP**, so the AP must be parked (`gale power
  off`) before any bridge op — the tool does this in every session.
- **Status register is SRP1-locked** (power-cycle lock); the array itself is
  NOT write-protected (`BP=CMP=WPS=0`), so the tool drives the bridge directly
  rather than going through a WP-unlock step.
- **EC console sets are silent no-ops while `system_is_locked()`.** `gale
  power/dev/rec <v>` only act when unlocked; the only true ack of a set is an
  `OK` line. `WP_L` is pulled up by the AP's 3.3 V rail, so a **parked AP means
  a locked EC** and `gale power on` from a parked state is always refused. The
  way to power a parked puck on is an EC `reboot` (which `verify-boot` does):
  it clears `ENTERING_DEV/REC` and the PD renegotiation auto-powers the AP
  ~1 s later. The EC USB device re-enumerates on `reboot`.

## Fleet automation

`fleet/` wraps this tool for per-puck production: serial-guarded flash
(`flash_gale_fleet.py`), the full backup→build→flash→verify→sheet pipeline
(`flash_one_puck.py`), and the 'Google WiFi Pucks' sheet sync
(`sync_sheet.py`). See `fleet/README.md` and `FLASH-RUNBOOK.md`.

## Other helpers

- **`fmap_dump.py`** — print an image's FMAP region table (offline).
- **`validate_sysupgrade.py`** — device-side OpenWrt sysupgrade check over SSH.
- **`fix_ath10k_retries.py`** — device-side ath10k-ct retry-limit fix.

## Requirements

Python 3 with **`pyusb`** (libusb). Run on the host the SuzyQ cable is attached
to (the EC must enumerate as `18d1:500f`). No flashrom — see the directive above.
