# SPDX-License-Identifier: Apache-2.0
"""Flash bookkeeping: compute the four audit fields written to inventory/<serial>.json.

These fields are the ones that ``galeflash.sheetmap.FIELD_TO_HEADER`` maps to
the fleet spreadsheet's audit columns.  ``bookkeeping()`` is a pure helper —
no hardware, no I/O except reading the already-built image for its SHA-256.
"""
import hashlib
from pathlib import Path


def bookkeeping(
    image_path: Path,
    backup_path: Path,
    date: str,
    status: str,
) -> dict:
    """Return a flash bookkeeping dict for one puck.

    Args:
        image_path:  Path to the built fleet image (.bin).  Its bytes are
                     SHA-256-hashed so the sheet audit column can verify
                     integrity later.
        backup_path: Path to the pre-flash SPI backup file.
        date:        Flash date string (``YYYY-MM-DD``).
        status:      Flash status label (e.g. ``"flashed"``).

    Returns:
        Dict with exactly four keys — ``backup_path``, ``image_sha256``,
        ``flash_date``, ``flash_status`` — which are a strict subset of
        ``galeflash.sheetmap.FIELD_TO_HEADER``.
    """
    sha256 = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    return {
        "backup_path": str(backup_path),
        "image_sha256": sha256,
        "flash_date": date,
        "flash_status": status,
    }
