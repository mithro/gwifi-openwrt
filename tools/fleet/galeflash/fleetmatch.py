# SPDX-License-Identifier: Apache-2.0
"""Match a live puck's identity against the 'Google WiFi Pucks' fleet sheet.

Pure logic (no hardware, no network): given the live identity read from the
puck's VPD and the sheet's header + rows, find which fleet row it is and report
its flash status.  Lets the operator identify a connected puck without reading
a label — the sheet is the source of truth.
"""
from galeflash.sheetmap import FIELD_TO_HEADER, format_mac


def _col(header: list[str], name: str) -> int:
    """Return the 0-based index of *name* in *header* (case-insensitive), or -1."""
    lower = [h.strip().lower() for h in header]
    try:
        return lower.index(name.lower())
    except ValueError:
        return -1


def _cell(row: list[str], idx: int) -> str:
    return row[idx].strip() if 0 <= idx < len(row) else ""


def _mac_cols(header: list[str]) -> tuple[int, int]:
    """Return the (wan, lan) MAC column indices, tolerating the legacy names.

    ``sheetmap.RENAME_HEADERS`` renamed ``eth0``->``wan`` and ``eth1``->``lan``,
    and the live sheet has carried the new names since 2026-07-25.  Looking the
    columns up under the old names returned -1 for both, which ``_cell()``
    renders as ``""`` — indistinguishable from a genuinely blank cell, so the
    cross-check degraded to ``mac_ok=None`` ("sheet has no MACs") instead of
    catching a mismatch.  Prefer the current names, fall back to the legacy
    ones so an un-renamed sheet still gets checked.
    """
    for wan, lan in ((FIELD_TO_HEADER["ethernet_mac0"],
                      FIELD_TO_HEADER["ethernet_mac1"]),
                     ("eth0", "eth1")):
        wan_col, lan_col = _col(header, wan), _col(header, lan)
        if wan_col >= 0 and lan_col >= 0:
            return wan_col, lan_col
    return -1, -1


def find_claimable_row(
    serial: str, name: str, header: list[str], rows: list[list[str]]
) -> dict:
    """Decide whether the row called *name* may be seeded with *serial*.

    The fleet sheet is pre-populated with placeholder rows that carry a Name
    (``puck16``…) but no Serial.  Everything downstream — ``match_puck`` here
    and ``sheetmap.compute_updates`` — keys off the **Serial** column, so a
    placeholder is invisible to the pipeline until its Serial is seeded: a
    freshly flashed puck's whole record lands in ``unmatched`` and is dropped
    without a single cell being written.  Seeding that one cell is what links
    a physical unit to the fleet name the operator chose for it.

    Because Serial is an *identity* column, this is deliberately a gate and
    not a write-through:

      * an occupied cell is never overwritten — a differing serial means the
        row already belongs to another puck, not that this one moved;
      * a serial already listed on a different row is refused — claiming it
        again would list one physical puck twice, and duplicate serials would
        make ``compute_updates``' serial→row map non-deterministic;
      * a duplicated or absent Name is refused rather than guessed at.

    Re-claiming a row that already carries this exact serial is not an error:
    it reports ``already`` so the caller can no-op and stay idempotent.

    Args:
        serial: the live puck's VPD serial number.
        name:   the fleet name to claim (matched case- and whitespace-
                insensitively against the Name column).
        header: the sheet's header row.
        rows:   the sheet's data rows (header excluded).

    Returns a dict:
        claimable:  True iff a write is needed AND safe.
        already:    True iff the row already carries this serial (no write).
        row_number: 1-based spreadsheet row of the named row, or None.
        serial_col: 0-based index of the Serial column, or None.
        reason:     human-readable explanation when not claimable.

    Raises:
        ValueError: if the header lacks a Name or Serial column.
    """
    name_col = _col(header, "name")
    serial_col = _col(header, "serial")
    if name_col < 0:
        raise ValueError("Header row has no 'Name' column — cannot claim a row.")
    if serial_col < 0:
        raise ValueError("Header row has no 'Serial' column — cannot claim a row.")

    serial = serial.strip()
    wanted = name.strip().lower()

    result = {
        "claimable": False,
        "already": False,
        "row_number": None,
        "serial_col": serial_col,
        "reason": "",
    }

    matches = [i for i, row in enumerate(rows)
               if _cell(row, name_col).lower() == wanted]

    if not matches:
        result["reason"] = f"no row named {name!r} in the sheet"
        return result
    if len(matches) > 1:
        sheet_rows = ", ".join(f"row {i + 2}" for i in matches)
        result["reason"] = (
            f"ambiguous: {len(matches)} rows are named {name!r} ({sheet_rows})")
        return result

    row_idx = matches[0]
    result["row_number"] = row_idx + 2          # +1 header, +1 for 1-based

    # A serial may appear exactly once in the sheet.  Check this BEFORE the
    # target cell so "already claimed elsewhere" is reported as such rather
    # than as an empty-cell claim that would duplicate the identity.
    for i, row in enumerate(rows):
        if i != row_idx and _cell(row, serial_col) == serial:
            other = _cell(row, name_col) or "(unnamed)"
            result["reason"] = (
                f"serial {serial!r} is already listed on row {i + 2} "
                f"({other}) — claiming it for {name!r} would list one "
                f"physical puck twice")
            return result

    current = _cell(rows[row_idx], serial_col)
    if current == serial:
        result["already"] = True
        result["reason"] = (
            f"row {result['row_number']} ({name}) already carries "
            f"{serial!r} — nothing to do")
        return result
    if current:
        result["reason"] = (
            f"row {result['row_number']} ({name}) already holds serial "
            f"{current!r}, not {serial!r} — that row is a different puck; "
            f"identity cells are never overwritten")
        return result

    result["claimable"] = True
    return result


def match_puck(live_identity: dict, header: list[str], rows: list[list[str]]) -> dict:
    """Match a live puck to a fleet-sheet row by serial.

    Args:
        live_identity: dict with ``serial_number`` and optionally
            ``ethernet_mac0`` / ``ethernet_mac1`` (bare-hex VPD values).
        header: the sheet's header row.
        rows:   the sheet's data rows (header excluded).

    Returns a dict:
        matched:      True if the serial was found in the sheet.
        serial:       the live serial.
        row_number:   1-based spreadsheet row of the match (header is row 1), or None.
        flash_status: the matched row's Flash Status cell ("" if blank/absent).
        mac_ok:       True/False if the sheet has MACs to compare, else None.
        mac_columns_known: False when the header has no MAC columns at all, so
            callers can tell an unreadable schema from merely blank cells.
        notes:        human-readable warnings (e.g. MAC mismatch).
    """
    serial = (live_identity.get("serial_number") or "").strip()
    serial_col = _col(header, "serial")
    eth0_col, eth1_col = _mac_cols(header)
    status_col = _col(header, "flash status")

    result = {
        "matched": False,
        "serial": serial,
        "row_number": None,
        "flash_status": "",
        # False when the sheet has no Flash Status column at all.  _cell()
        # returns "" for the resulting -1 index, which is indistinguishable
        # from a genuinely blank cell -- i.e. from "not yet flashed".  Callers
        # must not read a blank status as permission to flash unless this is
        # True.  (identify_puck.py fetched only A1:Z1000 while the schema
        # reached AH, so this was silently the case for every puck.)
        "flash_status_known": status_col >= 0,
        "mac_ok": None,
        # False when the sheet has neither the current wan/lan MAC columns nor
        # the legacy eth0/eth1 ones.  Without this, an unreadable schema is
        # reported as mac_ok=None -- the same value as "the sheet's cells are
        # blank" -- so a dead cross-check looks like a benign one.
        "mac_columns_known": eth0_col >= 0 and eth1_col >= 0,
        "notes": [],
    }
    if status_col < 0:
        result["notes"].append(
            "sheet header has no 'Flash Status' column — flash state is "
            "UNKNOWN, not blank (is the fetched column range wide enough?)")
    if not result["mac_columns_known"]:
        result["notes"].append(
            "sheet header has no 'wan'/'lan' (or legacy 'eth0'/'eth1') MAC "
            "columns — the MAC cross-check is UNAVAILABLE, not merely blank")

    match_idx = None
    for i, row in enumerate(rows):
        if serial and _cell(row, serial_col) == serial:
            match_idx = i
            break

    if match_idx is None:
        result["notes"].append(
            f"serial {serial!r} is not listed in the sheet")
        return result

    row = rows[match_idx]
    result["matched"] = True
    result["row_number"] = match_idx + 2          # +1 header, +1 for 1-based
    result["flash_status"] = _cell(row, status_col)

    # Cross-check MACs when both live values and sheet cells are present.
    live_macs = [format_mac(live_identity.get("ethernet_mac0") or ""),
                 format_mac(live_identity.get("ethernet_mac1") or "")]
    sheet_macs = [_cell(row, eth0_col), _cell(row, eth1_col)]
    if all(live_macs) and all(sheet_macs):
        if [m.lower() for m in live_macs] == [m.lower() for m in sheet_macs]:
            result["mac_ok"] = True
        else:
            result["mac_ok"] = False
            result["notes"].append(
                f"MAC mismatch: live {live_macs} vs sheet {sheet_macs}")

    return result
