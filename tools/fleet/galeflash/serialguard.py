# SPDX-License-Identifier: Apache-2.0
"""Serial-number guard: verify the live device matches the expected serial.

Pure logic is unit-tested.  Hardware I/O is in read_live_serial() (no-cover).
"""
import subprocess
import time
from pathlib import Path

from galeflash import vpd
from galeflash.const import FMAP

# Paths to the shared hardware toolkit.  This file is tools/fleet/galeflash/
# serialguard.py, so parents are: [0]=galeflash [1]=fleet [2]=tools.
TOOLS = Path(__file__).resolve().parents[2]   # .../tools
TMP   = Path(__file__).resolve().parents[1] / "tmp"  # tools/fleet/tmp/

# Read just the first 16 KiB of RO_VPD — more than enough for the compact VPD
# entry list (typically < 1 KiB).
_RO_VPD_OFF  = FMAP["RO_VPD"][0]  # 0x3E0000
_READ_LEN    = 0x4000              # 16 KiB partial read


def ok(live_serial: str, expected_serial: str) -> bool:
    """Return True iff live_serial matches expected_serial (exact, stripped).

    Pure function — no I/O — so it can be unit-tested without hardware.
    """
    return live_serial.strip() == expected_serial.strip()


# Identity fields read live for matching against the fleet sheet.  An explicit
# allowlist — sensitive VPD keys (stable_device_secret_*, setup_psk) never leave.
_IDENTITY_FIELDS = ("serial_number", "ethernet_mac0", "ethernet_mac1")


def read_live_identity() -> dict:  # pragma: no cover
    """Read the curated identity (serial + eth MACs) from the live RO_VPD.

    Uses flash_puck_usb.py `read` — the verified libusb tool (parks the AP
    itself, settles out the rail-bounce event windows, double-read confirmed).

    Returns:
        dict with keys from ``_IDENTITY_FIELDS`` (values may be None if absent).

    Raises:
        subprocess.CalledProcessError: if the read fails (incl. AP-park failure
        or a double-read mismatch inside the tool).
    """
    TMP.mkdir(exist_ok=True)
    out_path = TMP / "ro_vpd_partial.bin"

    def run(cmd, label):
        print(f"\n===== {label} =====", flush=True)
        print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
        t0 = time.time()
        subprocess.check_call(cmd)
        print(f"  ok ({time.time() - t0:.1f}s)")

    # Use system "python3" (NOT sys.executable) for the external tool: under
    # `uv run` sys.executable is the galeflash venv (pytest-only) which lacks
    # the pyusb that flash_puck_usb.py imports.
    run(
        [
            "python3",
            str(TOOLS / "flash_puck_usb.py"),
            "read",
            str(out_path),
            "--offset", hex(_RO_VPD_OFF),
            "--length", hex(_READ_LEN),
        ],
        f"read RO_VPD partial (0x{_RO_VPD_OFF:x}:0x{_READ_LEN:x})",
    )

    # Clean up the scratch read-back file regardless of decode outcome.
    try:
        kv = vpd.decode(out_path.read_bytes())
        return {field: kv.get(field) for field in _IDENTITY_FIELDS}
    finally:
        out_path.unlink(missing_ok=True)


def read_live_serial() -> str:  # pragma: no cover
    """Read the serial_number from the live device's RO_VPD.

    Raises:
        KeyError: if 'serial_number' is absent from the VPD (blank/erased device).
        subprocess.CalledProcessError: if the read fails.
    """
    serial = read_live_identity()["serial_number"]
    if serial is None:
        raise KeyError("serial_number")
    return serial
