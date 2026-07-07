# galeflash — Gale Fleet Firmware Flash Toolkit

Per-puck production tooling for dev-key netboot firmware on a fleet of Gale
(IPQ4019) pucks. All hardware I/O goes through the verified `flash_puck_usb.py`
tool one directory up (parked + settled sessions, double-read backups,
byte-verified RO-last writes, fail-fast wedge canaries).

## Per puck

**1. Identify it against the fleet sheet** (no label reading — reads the live
VPD and looks it up in 'Google WiFi Pucks'):

```
uv run identify_puck.py
```

Reports which sheet row the connected puck is, whether it's already been
flashed, cross-checks its MACs, and prints the exact command to run. Exit 0 =
ready to flash, 2 = already flashed (needs `--rekeyed-ok`), 3 = not in sheet,
4 = MAC mismatch (investigate).

**2. Flash it:**

```
uv run flash_one_puck.py --serial-hint <SERIAL> --date $(date +%F)
```

Pipeline: backup (`flash_puck_usb.py read`) → **archive the capture off-site**
→ extract identity + inventory → build the flags-7 dev-key image →
**serial-guarded** RO-last flash (`flash_gale_fleet.py` → `flash_puck_usb.py
flash`) → **archive the flashed image off-site** → read firmware ids →
EC-reboot boot verification → **sheet sync** to 'Google WiFi Pucks'.

The pre-flash capture and the flashed image are both copied to
`big-storage.welland.mithis.com:/backups/machines/gwifi/` (const.BIG_STORAGE_*).
The sheet records, per puck: RO/RW coreboot firmware ids, the depthcharge
payload id (git rev + ELF sha), the live EC firmware id, both archive paths,
and both sha256 checksums.

Flags:
- `--rekeyed-ok` — re-flash a puck whose GBB is already dev-keyed.
- `--skip-verify` — flash only, leave the puck parked (no boot check).
- `--no-sheet` — skip the sheet update at the end.
- `--dry-run` — print the plan; touch no hardware.

The serial guard reads the live puck's RO_VPD and aborts before any write if it
does not match `--serial-hint`, so the wrong puck can never be flashed.

## Components

- `flash_one_puck.py` — the per-puck orchestrator (above).
- `flash_gale_fleet.py` — serial-guarded single-image flash (RO-last, via the tool).
- `build_gale_fleet_image.py` — build a flags-7 image from a puck's own dump.
- `extract_identity.py` — curate device identity from a dump into inventory JSON.
- `sync_sheet.py` — push inventory (identity + flash bookkeeping) to the sheet.
- `galeflash/` — package: `const.py` (FMAP, allowed-change sets), `vpd.py`,
  `identity.py`, `imagebuild.py`, `inventory.py`, `orchestrator.py`,
  `serialguard.py`, `sheetmap.py`, `fmapdiff.py`, `cbfs.py`.

## Tests

```
cd tools/fleet
uv run pytest -q
```

Pure logic is unit-tested (58 tests); hardware seams are monkeypatched. The
underlying `flash_puck_usb.py` has its own suite one directory up
(`uv run --with pyusb --with pytest python -m pytest flash_puck_usb_test.py`).
Binary fixtures under `UMBRELLA` (see `galeflash/const.py`) are optional; tests
that need them skip when absent.
