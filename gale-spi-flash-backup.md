# Backing up the gale SPI boot flash (over SuzyQ / CCD)

`gale` keeps coreboot + depthcharge on an **8 MiB Winbond W25Q64FV** SPI-NOR. You can
read it **without opening the case** through the on-board **EC** (STM32F072CB), which
exposes flashrom's `raiden_debug_spi` bridge over a **SuzyQ / SuzyQable** USB-C debug
cable (the EC enumerates as USB `18d1:500f`).

> **Make this backup before touching the flash** — it is your undo image.

## TL;DR

```sh
cd tools/
python3 ec_console.py "gale power off"      # park the AP, grant the EC the SPI bus
python3 chunk_read.py all gale-backup.bin   # read + stitch the full 8 MiB
```

The full toolkit, requirements, and write/restore path are in
[`tools/README.md`](tools/README.md).

## Why not just `flashrom -r`

The EC bridge silently returns reliable data only for **< ~84 KiB per read session**
(the cliff is at `0x015db8` ≈ 87.4 KiB). Past it, it returns `0x00` **with no error**,
so a single full-chip `flashrom -r` looks like a *zeroed / bricked* chip when it is
not. `tools/chunk_read.py` works around this by reading in 64 KiB pieces — each in a
fresh session, re-parking the AP between pieces — and stitching them into one image.

One read caveat, handled/documented under `tools/`: flashrom (and the bridge)
re-power the AP **on** after each read, so the AP must be re-parked before the
next session.

## Requirements

- A SuzyQ / SuzyQable USB-C debug cable into the gale debug port.
- Python 3 with `pyserial` + `pyusb`, and a `raiden_debug_spi`-capable `flashrom`
  build (e.g. the chromiumos fork). Set `GALE_FLASHROM` to its path. See
  [`tools/README.md`](tools/README.md).

## Restoring / writing it back

To write a region back (or reflash), use
[`tools/raiden_write_region.py`](tools/raiden_write_region.py) — stock
`flashrom -E/-w` does **not** work on this unit (it trips on the flash's `SRP1`
status-register lock and its erase silently no-ops). Details and safety rails are in
[`tools/README.md`](tools/README.md).
