# SPDX-License-Identifier: Apache-2.0
"""Match a live puck's identity against the 'Google WiFi Pucks' fleet sheet.

Pure logic (no hardware, no network): given the live identity read from the
puck's VPD and the sheet's header + rows, find which fleet row it is and report
its flash status.  Lets the operator identify a connected puck without reading
a label — the sheet is the source of truth.
"""
from galeflash.sheetmap import format_mac


def _col(header: list[str], name: str) -> int:
    """Return the 0-based index of *name* in *header* (case-insensitive), or -1."""
    lower = [h.strip().lower() for h in header]
    try:
        return lower.index(name.lower())
    except ValueError:
        return -1


def _cell(row: list[str], idx: int) -> str:
    return row[idx].strip() if 0 <= idx < len(row) else ""


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
        notes:        human-readable warnings (e.g. MAC mismatch).
    """
    serial = (live_identity.get("serial_number") or "").strip()
    serial_col = _col(header, "serial")
    eth0_col, eth1_col = _col(header, "eth0"), _col(header, "eth1")
    status_col = _col(header, "flash status")

    result = {
        "matched": False,
        "serial": serial,
        "row_number": None,
        "flash_status": "",
        "mac_ok": None,
        "notes": [],
    }

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
