# SPDX-License-Identifier: Apache-2.0
"""Boot-capture classification for a freshly flashed gale puck.

Pure functions only — the serial capture itself lives in
``tools/fleet/verify_boot.py`` (needs pyserial + the live EC).

Marker choices (from real captures on puck 2712HW0072Z):
  - A GOOD (normal-mode, dev-keyed) boot prints ``Starting depthcharge on
    gale...`` and then netboot activity (``Sending DHCP discover``/TFTP).
  - Every boot — good or bad — prints ``vb2_check_recovery() Recovery reason
    from previous boot`` and a GPIO table row containing ``recovery``, so a
    bare "recovery" substring must NOT be a failure marker.
  - A failed verification / recovery entry prints one of the BAD_MARKERS.
"""

DEV_SIGNED_MARKER = "This is developer signed firmware"

GOOD_MARKERS = (
    "Starting depthcharge",   # our payload's banner — RW handoff succeeded
    "Sending DHCP discover",  # netboot running inside depthcharge
    "TFTP",
)

BAD_MARKERS = (
    "VB2:vb2_fail",           # verstage gave up on the RW slots
    "Need recovery",
    "Recovery requested",
    "Entering recovery mode",
)


def matched_markers(text: str) -> tuple[list[str], list[str]]:
    """Return (good, bad) marker lists found in *text*."""
    good = [m for m in GOOD_MARKERS if m in text]
    bad = [m for m in BAD_MARKERS if m in text]
    return good, bad


def decisive(text: str) -> bool:
    """True once *text* contains any marker that settles the verdict."""
    good, bad = matched_markers(text)
    return bool(good or bad)


def slot(text: str) -> str | None:
    """Which RW slot verstage verified ('A'/'B'), or None if not yet seen."""
    last = None
    for name in ("A", "B"):
        idx = text.rfind(f"FW_MAIN_{name} found")
        if idx >= 0 and (last is None or idx > last[1]):
            last = (name, idx)
    return last[0] if last else None


def classify(text: str) -> dict:
    """Classify a boot capture.

    Returns a dict with:
      verdict:    "GOOD" | "BAD" | "UNDECIDED"  (any BAD marker wins — a
                  recovery boot can still print a depthcharge banner)
      good, bad:  the matched marker lists
      dev_signed: verstage reported developer-signed firmware
      slot:       RW slot that was verified ("A"/"B"/None)
    """
    good, bad = matched_markers(text)
    if bad:
        verdict = "BAD"
    elif good:
        verdict = "GOOD"
    else:
        verdict = "UNDECIDED"
    return {
        "verdict": verdict,
        "good": good,
        "bad": bad,
        "dev_signed": DEV_SIGNED_MARKER in text,
        "slot": slot(text),
    }
