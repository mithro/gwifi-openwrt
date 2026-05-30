# Backing up the Google Wifi (gale) SPI flash over a SuzyQ cable

How the `gale-spi-stock-2026-05-28.bin` dump was made: a full read of the 8 MiB
SPI-NOR boot firmware (coreboot + depthcharge + GBB/VPD) to a local file, over the
SuzyQ/CCD cable — **no USB stick, no opening the case, no touching the eMMC.**

> ⚠️ **Shared-device caution.** The SuzyQ raiden bridge, the AP power state, and the
> EC/AP consoles are *single-owner, global* resources. If anyone/anything else is using
> this puck (e.g. depthcharge driver development), powering the AP off or running
> flashrom will collide with their work — and theirs will collide with yours.
> Coordinate before running any step below.

---

## Prerequisites

- gale powered up, with a **SuzyQ cable in its USB-C port**.
- Linux host; your user in the **`dialout`** group (so `/dev/ttyUSB*` is usable without
  sudo). `sudo` is still needed for `flashrom` (raw USB).
- `flashrom` built with the **`raiden_debug_spi`** programmer (check: `flashrom -p raiden_debug_spi:target=ap` should at least *find* the device).
- `uv` available, for the pyserial EC-console helper (Appendix A). Any serial terminal
  works too (see the manual alternative in step 3).

## 0. Confirm the cable enumerated

```bash
lsusb                 # expect: 18d1:500f Google Inc. Gale debug
ls -l /dev/ttyUSB*    # expect: ttyUSB0 and ttyUSB1
```

The "Gale debug" device exposes three vendor-class interfaces (verify with
`sudo lsusb -v -d 18d1:500f`):

| Interface | class/sub/proto | iInterface | Node | Role |
|---|---|---|---|---|
| 0 | `ff/50/01` | `EC_PD` | `/dev/ttyUSB0` | EC console (also does USB-C PD) |
| 1 | `ff/50/01` | `AP`    | `/dev/ttyUSB1` | AP console (coreboot/depthcharge/kernel) |
| 3 | `ff/51/01` | —       | (none)         | **raiden_debug_spi** SPI bridge |

There is **no Cr50/H1 GSC** on gale; the EC (an STM32F072) provides both consoles and
the SPI bridge.

## 1. The one thing that makes this work: power the AP off

gale's EC is a *dumb* SPI passthrough — it muxes its SPI master onto the AP's boot-flash
bus but, unlike a Cr50, it does **not** hold the AP in reset for you. So:

- If the **AP is running**, it contends on the shared bus and flashrom reports
  **`No EEPROM/flash device found`**.
- You must power the AP off yourself first (EC console: `gale power off`).
- **flashrom re-powers the AP when it exits**, so the power-off and the read must be a
  **single atomic command** — otherwise a separate flashrom run (e.g. a probe) leaves
  the AP live again and the next read fails.
- Use the **generic enable** (no `target=`). `target=AP` (`ENABLE_AP`) STALLs on this EC
  with `LIBUSB_ERROR_PIPE` / `Raiden: Failed to enable SPI bridge`.

## 2. Read the flash (atomic: power off → read)

```bash
uv run --with pyserial python ec_console.py /dev/ttyUSB0 "gale power off" \
  && sudo flashrom -p raiden_debug_spi -r gale-spi-backup.bin
```

Expected: flashrom finds `Unknown flash chip "SFDP-capable chip" (8192 kB, SPI)` — the
"Unknown" is normal (the bridge doesn't surface a DB-matched JEDEC ID; SFDP gives the
correct geometry and read/write/erase all work), then `Reading flash... done.`

Manual alternative (no helper script): open `/dev/ttyUSB0` in a serial terminal
(`picocom -b 115200 /dev/ttyUSB0`), type `gale power off`, leave it, then in another
shell run the `sudo flashrom ... -r` line. A single-shot send also works:
`printf 'gale power off\n' > /dev/ttyUSB0` (less robust — no confirmation).

## 3. Restore the AP

```bash
uv run --with pyserial python ec_console.py /dev/ttyUSB0 "gale power on" "gpioget"
```

In the `gpioget` output, `VDD_1P1_CPU_EN = 1` confirms the CPU core rail is back and the
AP is running. (flashrom usually re-powers the AP on exit anyway; this is belt-and-braces.)

## 4. Verify the dump (do not skip — slow bridges can flake)

Read a **second** time to a different file and byte-compare; a stable bridge gives
identical dumps:

```bash
uv run --with pyserial python ec_console.py /dev/ttyUSB0 "gale power off" \
  && sudo flashrom -p raiden_debug_spi -r gale-spi-backup2.bin
sha256sum gale-spi-backup.bin gale-spi-backup2.bin   # the two hashes MUST match
```

Then prove it's a real firmware image by parsing its FMAP (Appendix B):

```bash
uv run python verify_spi.py gale-spi-backup.bin
```

Expect `8388608` bytes and an FMAP at `0x300000` whose regions match the coreboot map
(`WP_RO@0x0/0x400000`, `GBB@0x301000`, `RO_FRID@0x3dff00`, `RW_SECTION_A@0x400000`,
`RW_SECTION_B@0x580000`, `RW_LEGACY@0x700000`, 24 areas total).

## What was observed on this unit (2026-05-28)

- Chip: SFDP-capable, **8192 kB** (= Winbond **W25Q64FV**).
- Two independent reads identical: `sha256 735b1c5adc3399d8257915d28b3df0313c3e2f64ab8385297c5b1a7eb10012d9`.
- Firmware IDs: RO `Google_Gale.8281.38.0`, RW_A `Google_Gale.8281.47.0`, RW_B `Google_Gale.8281.40.0`.
- GBB v1.2, flags `0x0` (stock), HWID `GALE C2I-A2A-A3C-A4I-E87`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No EEPROM/flash device found` | AP is powered on (bus contention), or a previous flashrom run re-powered it | Ensure `gale power off` immediately precedes the read, in one `&&` command |
| `LIBUSB_ERROR_PIPE` / `Failed to enable SPI bridge` | used `target=AP` | drop `target=` — use the generic enable |
| `Unknown flash chip "SFDP-capable chip"` | bridge doesn't expose a DB JEDEC ID | normal; read/verify/erase/write still work |
| consoles silent | EC consoles only echo on input | send a newline / a command first |

## Restoring (writing) — note

The same path writes: `... "gale power off" && sudo flashrom -p raiden_debug_spi -w <image>`.
Caveats before ever writing: (1) when the AP is off, `WP_L=0` so the **WP_RO** half is
hardware write-protected — you can only write the **RW** sections that way; (2) writing
RW from an *older* image is an anti-rollback downgrade that vboot may refuse at boot;
(3) never write the shellball's raw `bios.bin` whole — it has a blank GBB/VPD and would
wipe this unit's HWID/MAC. Write `-i RW_SECTION_A -i RW_SECTION_B` with a layout, and
keep this backup as the undo image.

---

## Appendix A — `ec_console.py`

```python
#!/usr/bin/env python3
"""Talk to the gale EC console (ChromeOS EC) over USB serial.

Usage: ec_console.py [PORT] [CMD ...]
PORT defaults to /dev/ttyUSB0 (the EC_PD console on gale).
Sends each CMD followed by newline, then prints whatever the EC replies.
"""
import sys
import time

import serial  # pyserial


def read_reply(ser, settle=3.0, idle=0.6):
    data = bytearray()
    deadline = time.time() + settle
    last = time.time()
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            data += chunk
            last = time.time()
        elif time.time() - last > idle:
            break
    return bytes(data)


def main():
    argv = sys.argv[1:]
    port = "/dev/ttyUSB0"
    if argv and not argv[0].startswith("-") and "/" in argv[0]:
        port = argv.pop(0)
    cmds = argv if argv else ["", "help", "version"]

    ser = serial.Serial(port, 115200, timeout=0.3)
    time.sleep(0.2)
    ser.reset_input_buffer()
    for c in cmds:
        ser.write((c + "\n").encode())
        ser.flush()
        reply = read_reply(ser)
        sys.stdout.write(f"\n===== sent {c!r} =====\n")
        sys.stdout.write(reply.decode("utf-8", errors="replace"))
        sys.stdout.flush()
    ser.close()


if __name__ == "__main__":
    main()
```

## Appendix B — `verify_spi.py`

```python
#!/usr/bin/env python3
"""Sanity-check a gale SPI dump: size, blank-ratio, signatures, validated FMAP parse."""
import re
import struct
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "gale-spi-backup.bin"
with open(path, "rb") as f:
    data = f.read()

print(f"file : {path}")
print(f"size : {len(data)} bytes ({len(data) / 1024 / 1024:.2f} MiB)  "
      f"expected 8388608 -> {'OK' if len(data) == 8 * 1024 * 1024 else 'MISMATCH'}")
ff, zz = data.count(0xFF), data.count(0x00)
print(f"blank: 0xFF {100 * ff / len(data):.1f}%, 0x00 {100 * zz / len(data):.1f}%")

print("\nsignatures:")
for sig in (b"$GBB", b"LARCHIVE", b"Google_Gale", b"CHROMEOS", b"coreboot"):
    idx = data.find(sig)
    print(f"  {sig.decode('latin1'):14} {hex(idx) if idx >= 0 else 'NOT FOUND'}")


def parse_fmap(buf):
    for m in re.finditer(b"__FMAP__", buf):
        fi = m.start()
        if fi + 56 > len(buf):
            continue
        ver_major, ver_minor = buf[fi + 8], buf[fi + 9]
        nareas = struct.unpack_from("<H", buf, fi + 54)[0]
        name = buf[fi + 22:fi + 54].split(b"\0")[0]
        if ver_major != 1 or ver_minor > 1 or not (0 < nareas < 256):
            continue
        if not name or not all(0x20 <= b <= 0x7e for b in name):
            continue
        base = struct.unpack_from("<Q", buf, fi + 10)[0]
        size = struct.unpack_from("<I", buf, fi + 18)[0]
        areas, off = [], fi + 56
        for _ in range(nareas):
            a_off, a_size = struct.unpack_from("<II", buf, off)
            a_name = buf[off + 8:off + 40].split(b"\0")[0].decode("ascii", "replace")
            areas.append((a_name, a_off, a_size))
            off += 42
        return fi, ver_major, ver_minor, base, size, name.decode(), areas
    return None


res = parse_fmap(data)
print("\nFMAP:")
if res:
    fi, vmaj, vmin, base, size, name, areas = res
    print(f"  valid FMAP @ {hex(fi)}: v{vmaj}.{vmin} base={hex(base)} "
          f"size={hex(size)} name='{name}' areas={len(areas)}")
    for a_name, a_off, a_size in areas:
        print(f"  {a_name:24} {hex(a_off):>10} {hex(a_size):>10}")
else:
    print("  no valid FMAP found -- dump may be invalid")
```
