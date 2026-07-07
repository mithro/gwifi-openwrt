# SPDX-License-Identifier: Apache-2.0
"""Flash bookkeeping: the audit fields written to inventory/<serial>.json.

These keys are a strict subset of ``galeflash.sheetmap.FIELD_TO_HEADER``, so the
sheet-sync consumer has a column for each.  ``bookkeeping()`` computes the file
checksums itself and passes through the firmware/archive values captured by the
flow (live EC read, cbfs RW id, off-site archive paths).
"""
import hashlib
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bookkeeping(
    image_path: Path,
    backup_path: Path,
    date: str,
    status: str,
    *,
    ec_version: str,
    rw_fwid: str,
    depthcharge_version: str,
    capture_archive: str,
    image_archive: str,
) -> dict:
    """Return the flash bookkeeping dict for one puck.

    Args:
        image_path:   Local path to the built fleet image (hashed -> image_sha256).
        backup_path:  Local path to the pre-flash SPI capture (hashed -> backup_sha256).
        date:         Flash date string (``YYYY-MM-DD``).
        status:       Flash status label (e.g. ``"flashed+boot-verified"``).
        ec_version:   STM32 EC firmware id read live (``firmware.parse_ec_version``).
        rw_fwid:      coreboot RW firmware id in the flashed image (``firmware.rw_fwid``).
        depthcharge_version: netboot payload id (``firmware.depthcharge_version``).
        capture_archive: off-site (big-storage) path of the archived capture.
        image_archive:   off-site (big-storage) path of the archived flashed image.

    Returns:
        Dict whose keys are all present in ``sheetmap.FIELD_TO_HEADER``.
    """
    return {
        "flash_date":          date,
        "flash_status":        status,
        # firmware flashed to / running on the device
        "ec_version":          ec_version,
        "rw_fwid":             rw_fwid,
        "depthcharge_version": depthcharge_version,
        # off-site backup archive + checksums
        "backup_path":         capture_archive,   # 'Backup' column = archive location
        "backup_sha256":       _sha256(backup_path),
        "image_archive":       image_archive,
        "image_sha256":        _sha256(image_path),
    }
