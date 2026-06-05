# gale AP SPI-flash toolkit (over the EC raiden bridge)

Host-side tools to read, back up, and write the Google WiFi ("gale", IPQ4019)
**8 MiB Winbond W25Q64FV** boot flash through the on-board **EC** (STMicroelectronics
STM32F072CB) using a **SuzyQ / SuzyQable** USB-C debug cable. The EC exposes
flashrom's `raiden_debug_spi` bridge (USB `18d1:500f`, interface subclass `0x51`).

These tools speak the chromiumos-EC `usb_spi` **V1** protocol directly, because
**stock `flashrom -E/-w` does not work on this unit** (see *Why not flashrom*).

## Hardware setup
- SuzyQable into the gale USB-C debug port; the EC enumerates as `18d1:500f`.
- The SPI bus is shared with the AP, so the AP must be parked before any operation:
  `python3 ec_console.py "gale power off"` (this also grants the EC the SPI bus).

## Quirks this toolkit works around (all measured on real hardware)
1. **~87 KiB per-session cliff.** The bridge silently returns/accepts only ~87 KiB
   (`0x015db8`) per *enable-session*; past it, reads return `0x00` and writes silently
   no-op — **with no error reported**. The only thing that resets a session is a
   *fresh process* (re-`REQ_ENABLE`, re-park, and `DISABLE`+`ENABLE` within one libusb
   claim all fail). So every tool works in `<84 KiB` pieces, one fresh process per
   piece. A single full-chip read therefore looks "bricked" (all zeros) — it isn't.
2. **~212-byte blind spot at flash address 0** (`0x0–0xd4`). A region read based at
   `0x0` returns `0x00` over the bootblock ELF header (the real bytes are present on
   the chip). Patch those `0xd4` bytes from a known-good bootblock for a faithful image.
3. **Status register is locked** (`SRP1=1`, power-cycle lock). The array is NOT
   write-protected (`BP=CMP=WPS=0`), but stock flashrom's WP-unlock step trips on the
   SR lock and its erase then silently no-ops — which is why these tools drive the
   bridge directly instead.

## Tools
- **`raiden_write_region.py`** — region-aware erase+program+verify writer (the main
  write tool). Resolves an FMAP region name or `0xOFF:0xLEN`, splits into ≤16 KiB
  chunks, and per chunk spawns a fresh worker process (erase → program, then a
  separate read-back), aborting on the first verify mismatch. Dry-run unless
  `--commit`; refuses the bottom 4 MiB (RO/bootblock) without `--allow-ro`; requires
  4 KiB alignment. (16 KiB is the safe per-session write ceiling — a transaction
  guard refuses bigger `--chunk`.)
- **`chunk_read.py`** — chunked reader / backup. `all <out.bin>` reads and stitches
  the full 8 MiB, re-parking per chunk. Remember to patch the `0x0` blind spot.
- **`raiden_sr.py`** — read `RDID` + status registers `SR1/SR2/SR3` (self-validated
  by `RDID == ef4017`). Surfaces the `BP/CMP/WPS/SRP` write-protect bits flashrom
  doesn't decode.
- **`ec_console.py`** — minimal EC USB-console client (`gale power off`, `version`,
  `gpioget`, …). Note: EC-reported gpio values can be stale; don't trust them as proof.

## Usage
```sh
# 1) park the AP / grant the EC the bus (before any bridge op)
python3 ec_console.py "gale power off"

# 2) full backup (read + stitch; re-parks per chunk)
python3 chunk_read.py all gale-backup.bin

# 3) inspect chip id + write-protect state
python3 raiden_sr.py

# 4) preview a write (dry-run — touches nothing)
python3 raiden_write_region.py <src.bin> RW_SECTION_A

# 5) write a region for real (erase + program + per-chunk verify)
python3 raiden_write_region.py <src.bin> RW_SECTION_A --commit

# explicit span, e.g. restore RW_LEGACY from a backup:
python3 raiden_write_region.py gale-backup.bin 0x700000:0x100000 --commit
```

## Why not flashrom
`flashrom -p raiden_debug_spi … -E/-w` fails on this unit: it logs *"Failed to unlock
flash status reg with wp support"* (the `SRP1` lock) and its erase silently no-ops (it
also verifies at the `0x0` blind spot → a false `ERASE_FAILED`). `flashrom -r` works
only if each read stays `< 84 KiB`. For a clean full reflash that bypasses the EC
entirely, a **CH341A + SOIC-8 clip** on the W25Q64 is the most robust option (its own
Vcc + bus master — no cliff, no blind spot, but you must hold the AP off).

## Configuration (environment variables)
- `GALE_FLASHROM` — path to a `raiden_debug_spi`-capable flashrom (used by `chunk_read.py`).
- `GALE_CHIP` — flashrom chip name (default `W25Q64BV/W25Q64CV/W25Q64FV`).
- `GALE_STOCK` — reference image for `chunk_read.py`'s vs-reference comparison.
- `GALE_WORK` — scratch dir for temporary chunk/layout files (default: this directory).

The defaults point at the original test rig; override them for your setup.

## Requirements
- Python 3 with **`pyserial`** and **`pyusb`** (libusb). Run on the host the SuzyQ
  cable is attached to (the EC must enumerate as `18d1:500f`).
- `chunk_read.py` additionally needs a `raiden_debug_spi`-capable flashrom build
  (e.g. the chromiumos flashrom fork).

## Safety
- `raiden_write_region.py` is **dry-run by default**; pass `--commit` to write.
- RO / bootblock writes are gated behind `--allow-ro` (bricking risk — prefer CH341A).
- **Back up first** (`chunk_read.py all`); the writer verifies every chunk after writing.
