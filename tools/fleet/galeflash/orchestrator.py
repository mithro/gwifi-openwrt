# SPDX-License-Identifier: Apache-2.0
"""Pure planning logic for single-puck flash orchestration.

``plan()`` is deterministic / side-effect-free: it reads one identity dump,
computes filename paths (no build I/O, no hardware calls), and returns a
``FlashPlan``.  All hardware and build steps are delegated to the imperative
entrypoint (``flash_one_puck.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from galeflash import identity

# The documented full procedure, in order.  "verify" is the operator boot-check
# (watching the serial console for the §7 exit criteria) and so comes AFTER
# "poweron"; the offline futility-verify is internal to imagebuild.build().
#
# "unprotect" clears the SPI software write-protection.  Every stock unit
# measured so far ships with block-protect latched (SR1=0xb8 =
# SRP0|TB|BP2|BP1 — 2125HW00PL3 2026-07-12, then 3719HW0037B/0037U/004FU on
# 2026-08-01), which makes write_region refuse and every erase a no-op; the
# flash step then walks its chunk size down to no purpose.  It sits AFTER
# "backup" on purpose: it is the first step that writes anything to the
# device (the status register), so the irreplaceable capture must exist
# first.  It is a no-op on an already-unprotected puck.
STEPS: list[str] = ["backup", "extract", "build", "unprotect", "flash",
                    "poweron", "verify", "sheet"]


@dataclass(frozen=True)
class FlashPlan:
    """Immutable description of what the flash operator should do for one puck.

    Frozen so the ``refuse`` interlock cannot be mutated after the gate
    decision has been made.

    Attributes:
        expected_serial: Serial number read from the backup dump.  The
            hardware flasher's serial-guard will re-read the live puck and
            abort if it does not match — ensuring we flash the same puck we
            backed up.
        is_stock: True if the puck's GBB root key is still the Google
            production key.  A non-stock unit has already been re-keyed to
            the Chromium OS dev key.
        image_path: Where the built fleet image will be written.  Placed
            alongside the backup in the same directory.
        identity: The curated identity dict read from the backup dump (exactly
            what ``identity.from_dump`` returns).  Carried on the plan so
            callers never re-read the dump — one futility invocation per puck.
        steps: The full six-step procedure (always the same list; included
            for operator display / dry-run output).
        refuse: True when the plan must not proceed.  The operator must
            acknowledge the situation and re-invoke with ``--rekeyed-ok``.
        refuse_reason: Human-readable explanation when ``refuse`` is True;
            empty string otherwise.
    """

    expected_serial: str
    is_stock: bool
    image_path: Path
    identity: dict
    steps: list[str] = field(default_factory=lambda: list(STEPS))
    refuse: bool = False
    refuse_reason: str = ""


def plan(backup: Path, *, rekeyed_ok: bool = False, date: str) -> FlashPlan:
    """Build a :class:`FlashPlan` from an existing pre-flash SPI dump.

    Args:
        backup:     Path to the pre-flash SPI dump.  Expected filename form:
                    ``gale-<serial>-<date>-pre-flash.bin``.
        rekeyed_ok: Set to ``True`` to allow flashing a unit whose GBB root
                    key has already been replaced with the Chromium OS dev
                    key.  Without this flag a non-stock puck causes
                    ``FlashPlan.refuse`` to be set.
        date:       Date string to embed in the output image filename
                    (``YYYY-MM-DD``).  Passed in explicitly so ``plan()``
                    stays pure and deterministic (no ``datetime.now()`` call).

    Returns:
        A :class:`FlashPlan` with all fields populated.  The caller **must**
        inspect ``plan.refuse`` before proceeding — a refused plan must not
        be flashed.
    """
    backup = Path(backup)
    idv = identity.from_dump(backup)

    serial: str = idv["serial_number"]
    is_stock: bool = idv["is_stock"]

    image_path = backup.parent / f"gale-{serial}-{date}-fleet.bin"

    refuse = not is_stock and not rekeyed_ok
    refuse_reason = (
        f"Puck {serial!r} is already dev-keyed (is_stock=False). "
        "Re-keying a non-stock unit is unexpected; the fleet pilot must use "
        "a FRESH STOCK puck. Pass --rekeyed-ok to override."
        if refuse
        else ""
    )

    return FlashPlan(
        expected_serial=serial,
        is_stock=is_stock,
        image_path=image_path,
        identity=idv,
        steps=list(STEPS),
        refuse=refuse,
        refuse_reason=refuse_reason,
    )
