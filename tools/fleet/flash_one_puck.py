#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Single-puck flash orchestrator for Gale fleet firmware.

Wires together the pipeline for one puck:
  backup → archive capture off-site → extract → build → flash →
  archive image off-site → read firmware ids → verify-boot (EC reboot +
  AP capture) → sheet sync ('Google WiFi Pucks')

All hardware I/O goes through flash_puck_usb.py — the verified libusb tool
(parked + settled sessions, double-read backups, byte-verified writes,
fail-fast wedge canaries).  The pre-flash capture and the flashed image are
both copied to big-storage (const.BIG_STORAGE_*), and the sheet records their
sha256s plus the firmware flashed: RO/RW coreboot ids, the depthcharge payload
id, and the live EC firmware id.

Usage:
    uv run flash_one_puck.py --serial-hint <S> --date <YYYY-MM-DD>
                              [--out-dir DIR] [--rekeyed-ok]
                              [--dry-run] [--skip-verify] [--no-sheet]

The serial-hint must match the live puck's serial number exactly: the run
refuses right after the identity read if the attached puck is not the hinted
one (before anything is archived or flashed), and the flash step's
serial-guard additionally re-reads the puck against the built image.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — flash_one_puck.py lives in tools/fleet/
# ---------------------------------------------------------------------------
FLEET = Path(__file__).resolve().parent   # tools/fleet/
TOOLS = FLEET.parent                      # tools/
sys.path.insert(0, str(FLEET))

from galeflash import const, firmware, imagebuild, inventory, orchestrator  # noqa: E402

DEFAULT_OUT_DIR = Path("/home/tim/local/gwifi/fleet-flash")

# Exit-criteria block printed after a successful flash (§7 of the plan doc).
_EXIT_CRITERIA = """\
=== BOOT EXIT CRITERIA (§7) — checked by flash_puck_usb.py verify-boot ===
  1. Verstage verifies a RW slot ("This is developer signed firmware").
  2. Depthcharge starts ("Starting depthcharge on gale...").
  3a. WITH DHCP/TFTP up  : puck netboots — TFTP kernel fetch visible on console.
  3b. WITHOUT DHCP/TFTP  : DHCP discover retries, then eMMC fallback.
  NOTE: slots are signed with the flags-7 firmware.keyblock, so the image
        boots in NORMAL mode — no per-unit developer-mode step is needed.
"""


# ---------------------------------------------------------------------------
# Hardware subprocess helpers — marked no-cover; touch real hardware
# ---------------------------------------------------------------------------

def _run_hw(cmd: list, label: str) -> None:  # pragma: no cover
    """Print a banner, run *cmd*, raise CalledProcessError on failure."""
    print(f"\n===== {label} =====", flush=True)
    print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.check_call(cmd)


def _backup_spi(backup: Path) -> None:  # pragma: no cover
    """Step 1: read full 8 MiB SPI flash from the live puck.

    flash_puck_usb.py `read` parks the AP itself, settles out the rail-bounce
    event windows, and double-reads (second pass must match byte-for-byte).
    """
    _run_hw(
        [const.SYSTEM_PYTHON, str(TOOLS / "flash_puck_usb.py"), "read", str(backup)],
        "backup SPI",
    )


def _unprotect_spi() -> None:  # pragma: no cover
    """Clear the SPI software write-protection before flashing.

    Stock units ship with block-protect latched — SR1=0xb8
    (SRP0|TB|BP2|BP1), seen on every stock puck measured so far.  Left set,
    ``write_region`` refuses and the flash step downshifts its chunk size to
    no purpose (the refusal precedes any erase, so nothing is written — the
    run simply fails after wasting a full backup+build cycle).

    ``unprotect`` is idempotent: on a puck with no protection set it reports
    "nothing to do" and exits 0, so this runs unconditionally rather than
    trying to predict which units need it.
    """
    _run_hw(
        [const.SYSTEM_PYTHON, str(TOOLS / "flash_puck_usb.py"),
         "unprotect", "--commit"],
        "unprotect SPI (clear block-protect)",
    )


def _flash_image(image_path: Path, serial: str) -> None:  # pragma: no cover
    """Step 4: flash the built image; flash_gale_fleet.py's serial-guard runs here."""
    _run_hw(
        [
            const.SYSTEM_PYTHON, str(FLEET / "flash_gale_fleet.py"),
            str(image_path),
            serial,
        ],
        "flash",
    )


def _verify_boot(log_path: Path) -> None:  # pragma: no cover
    """Step 5: EC-reboot the puck and verify the captured boot.

    `gale power on` cannot un-park the AP (the EC is locked while parked —
    WP_L follows the AP's 3.3V rail), so flash_puck_usb.py `verify-boot`
    reboots the EC: that clears dev/rec and the PD renegotiation auto-powers
    the AP into a clean normal-mode cold boot, which is captured, classified,
    and written to *log_path*.  Raises CalledProcessError on a BAD (exit 2)
    or UNDECIDED (exit 3) verdict.
    """
    _run_hw(
        [const.SYSTEM_PYTHON, str(TOOLS / "flash_puck_usb.py"), "verify-boot",
         "--boot-log", str(log_path)],
        "verify-boot",
    )


def _read_ec_version() -> str:  # pragma: no cover
    """Read the STM32 EC firmware id live over libusb (`ec version` -> RO line)."""
    out = subprocess.check_output(
        [const.SYSTEM_PYTHON, str(TOOLS / "flash_puck_usb.py"), "ec", "version"],
        text=True,
    )
    return firmware.parse_ec_version(out)


def _archive_to_bigstorage(local: Path) -> str:  # pragma: no cover
    """Copy a firmware file off-site to big-storage; return its archive path.

    rsync to ``BIG_STORAGE_HOST:BIG_STORAGE_DIR`` (the rig trusts big-storage's
    host key in ~/.ssh/known_hosts).  Fails loud — an un-archived capture is a
    lost irreplaceable backup, so the run must stop, not proceed silently.
    """
    remote = f"{const.BIG_STORAGE_HOST}:{const.BIG_STORAGE_DIR}/"
    _run_hw(["rsync", "-a", str(local), remote], f"archive {local.name} -> big-storage")
    return f"{const.BIG_STORAGE_HOST}:{const.BIG_STORAGE_DIR}/{local.name}"


def _sync_sheet(inventory_dir: Path) -> None:  # pragma: no cover
    """Step 6: push the inventory (identity + flash bookkeeping) to the
    'Google WiFi Pucks' sheet.  Raises CalledProcessError on failure — the
    operator must know the sheet was NOT updated.

    --update-flash: a pipeline sync always carries a fresh flash, so the
    flash-audit columns (firmware ids, date/status, backup/image paths+shas)
    legitimately replace the previous flash's values.  Identity columns stay
    conflict-guarded inside sync_sheet."""
    _run_hw(
        [const.UV, "run", str(FLEET / "sync_sheet.py"), "--write",
         "--update-flash", "--inventory", str(inventory_dir)],
        "sync sheet",
    )


# ---------------------------------------------------------------------------
# Pure helpers (testable, no hardware)
# ---------------------------------------------------------------------------

def _ensure_dirs(out_dir: Path) -> tuple[Path, Path]:
    """Create and return (backups_dir, inventory_dir) under *out_dir*."""
    backups_dir = out_dir / "backups"
    inventory_dir = out_dir / "inventory"
    backups_dir.mkdir(parents=True, exist_ok=True)
    inventory_dir.mkdir(parents=True, exist_ok=True)
    return backups_dir, inventory_dir


def _write_inventory(idv: dict, inventory_dir: Path) -> Path:
    """Write identity dict to <inventory_dir>/<serial>.json; return the path."""
    serial = idv["serial_number"]
    out_file = inventory_dir / f"{serial}.json"
    out_file.write_text(json.dumps(idv, indent=2) + "\n")
    print(f"Identity written: {out_file}", flush=True)
    return out_file


def _print_dry_run(
    serial_hint: str,
    date: str,
    backup: Path,
    rekeyed_ok: bool,
) -> None:
    """Print a dry-run plan summary; reads backup only if it already exists.

    When the backup is on disk we run the real ``plan()`` and report its
    actual fields (image_path, expected_serial, refuse).  When it is not, we
    synthesize the prospective filenames from the serial hint — there is no
    dump to read, so refuse cannot yet be determined.
    """
    print("=== DRY RUN (no hardware access, no build) ===")
    print(f"  backup          : {backup}")
    print(f"  steps           : {orchestrator.STEPS}")
    print(f"  rekeyed_ok      : {rekeyed_ok}")
    if backup.exists():
        p = orchestrator.plan(backup, rekeyed_ok=rekeyed_ok, date=date)
        print(f"  image           : {p.image_path}")
        print(f"  expected_serial : {p.expected_serial}")
        print(f"  refuse          : {p.refuse}")
        if p.refuse:
            print(f"  refuse_reason   : {p.refuse_reason}")
    else:
        image_path = backup.parent / f"gale-{serial_hint}-{date}-fleet.bin"
        print(f"  image           : {image_path}")
        print(f"  expected_serial : {serial_hint}")
        print("  refuse          : (unknown — backup not yet on disk)")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--serial-hint", required=True,
        help="Expected serial number of the puck to flash",
    )
    parser.add_argument(
        "--date", required=True,
        help="Date stamp for output filenames (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR,
        help=f"Output root directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--rekeyed-ok", action="store_true",
        help="Allow flashing a puck whose GBB root key is already dev-keyed",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print plan filenames and steps; do NOT touch hardware or build",
    )
    parser.add_argument(
        "--skip-verify", action="store_true",
        help="Skip the EC-reboot boot verification (leaves the puck parked)",
    )
    parser.add_argument(
        "--no-sheet", action="store_true",
        help="Skip the 'Google WiFi Pucks' sheet sync at the end",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> None:
    args = _parse_args(argv)

    backups_dir, inventory_dir = _ensure_dirs(args.out_dir)
    backup = backups_dir / f"gale-{args.serial_hint}-{args.date}-pre-flash.bin"

    # --dry-run: show plan without touching hardware or building.
    if args.dry_run:
        _print_dry_run(args.serial_hint, args.date, backup, args.rekeyed_ok)
        return

    # Step 1: backup (hardware)
    _backup_spi(backup)  # pragma: no cover

    # Step 2: extract identity + plan (one dump read; identity rides on the plan)
    p = orchestrator.plan(backup, rekeyed_ok=args.rekeyed_ok, date=args.date)

    # Serial-hint gate: the capture file was named from the hint before the
    # dump existed; the dump's own RO_VPD is ground truth.  A mismatch means
    # the WRONG PUCK is on the SuzyQ — refuse before anything is archived
    # under a wrong name or flashed.  (2026-07-11: WGD was flashed under
    # --serial-hint 2712HW0072Z because this check did not exist; the flash
    # step's serial-guard only proves image-serial == device-serial, which is
    # trivially true when both derive from the attached device.)
    live_serial = p.identity.get("serial_number", "")
    if live_serial != args.serial_hint:
        kept = backup.with_name(f"gale-{live_serial}-{args.date}-WRONG-PUCK.bin")
        backup.rename(kept)
        print(f"\nREFUSED: attached puck is {live_serial!r}, not --serial-hint "
              f"{args.serial_hint!r} — the wrong puck is on the SuzyQ.  Its "
              f"capture is kept at {kept}; nothing was archived or flashed.",
              file=sys.stderr)
        sys.exit(1)

    # Step 2.5: archive the irreplaceable pre-flash capture off-site before
    # any write to the puck (the identity gate above must run first so the
    # archive can never be filed under the wrong serial).
    capture_archive = _archive_to_bigstorage(backup)  # pragma: no cover

    _write_inventory(p.identity, inventory_dir)

    if p.refuse:
        print(f"\nREFUSED: {p.refuse_reason}", file=sys.stderr)
        sys.exit(1)

    # Step 3: build (offline — futility + cbfstool, no hardware)
    print("\n===== build =====", flush=True)
    imagebuild.build(backup, p.image_path)
    print(f"  image: {p.image_path}", flush=True)

    # Step 3.5: clear SPI block-protect (hardware).  After the refuse gate and
    # the capture archive — this is the first write to the device — and before
    # the flash it exists to enable.  A no-op on an unprotected puck.
    _unprotect_spi()  # pragma: no cover

    # Step 4: flash (hardware); serial-guard runs inside flash_gale_fleet.py
    _flash_image(p.image_path, p.expected_serial)  # pragma: no cover

    # Step 4.2: archive the exact flashed image + read the firmware ids that go
    # on the sheet (EC live; RW fwid from the image; depthcharge payload id).
    image_archive = _archive_to_bigstorage(p.image_path)  # pragma: no cover
    fw = dict(  # pragma: no cover
        ec_version=_read_ec_version(),
        rw_fwid=firmware.rw_fwid(p.image_path),
        depthcharge_version=firmware.depthcharge_version(),
        capture_archive=capture_archive,
        image_archive=image_archive,
    )

    # Step 4.5: bookkeeping — merge audit fields into inventory/<serial>.json now
    # that the flash has completed successfully.  Re-writes the file that was first
    # written in Step 2 (identity only) with identity + bookkeeping together.
    bk = inventory.bookkeeping(p.image_path, backup, args.date, "flashed", **fw)
    _write_inventory({**p.identity, **bk}, inventory_dir)

    # Step 5: verify — EC reboot + AP boot capture, classified automatically.
    # A non-GOOD verdict must not lose the bookkeeping/sheet steps: the flash
    # itself was already byte-verified, and mute-console benches (e.g. the
    # WGD/rpi3b combo) return UNDECIDED with 0 bytes even on good boots —
    # judge those from the wire (dnsmasq DHCP/TFTP lines).
    print(_EXIT_CRITERIA)
    verify_failed = False
    if args.skip_verify:
        print("verify-boot SKIPPED (--skip-verify); puck is parked.  To power "
              "it on, reboot the EC (NOT `gale power on` — refused while "
              "parked): python3 " + str(TOOLS / "flash_puck_usb.py")
              + " verify-boot")
    else:
        log_path = (args.out_dir / "logs"
                    / f"gale-{p.expected_serial}-{args.date}-boot.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _verify_boot(log_path)  # pragma: no cover
        except subprocess.CalledProcessError as e:
            verify_failed = True
            print(f"verify-boot did not return GOOD (exit {e.returncode}); "
                  "sheet status stays 'flashed'.  Judge from the wire and "
                  "re-run verify-boot when in doubt.", file=sys.stderr)
        else:
            bk = inventory.bookkeeping(
                p.image_path, backup, args.date, "flashed+boot-verified", **fw)
            _write_inventory({**p.identity, **bk}, inventory_dir)

    # Step 6: sheet — push identity + bookkeeping to 'Google WiFi Pucks'.
    if args.no_sheet:
        print("sheet sync SKIPPED (--no-sheet); run later with: "
              f"uv run {FLEET / 'sync_sheet.py'} --write")
    else:
        _sync_sheet(inventory_dir)  # pragma: no cover

    print(f"Done.  backup: {backup}")
    print(f"       image : {p.image_path}")
    if verify_failed:
        sys.exit(3)


if __name__ == "__main__":
    main()
