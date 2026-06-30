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

# Read just the first 16 KiB of RO_VPD — well under the ~87 KiB per-raiden-session
# cliff, and more than enough for the compact VPD entry list (typically < 1 KiB).
_RO_VPD_OFF  = FMAP["RO_VPD"][0]  # 0x3E0000
_READ_LEN    = 0x4000              # 16 KiB partial read


def ok(live_serial: str, expected_serial: str) -> bool:
    """Return True iff live_serial matches expected_serial (exact, stripped).

    Pure function — no I/O — so it can be unit-tested without hardware.
    """
    return live_serial.strip() == expected_serial.strip()


def read_live_serial() -> str:  # pragma: no cover
    """Read the serial_number from the live device's RO_VPD over the raiden bridge.

    Steps:
      1. Park the AP ('gale power off') so the EC owns the SPI bus.
      2. Spawn raiden_write_region.py _rd to read a 16 KiB slice of RO_VPD
         (offset 0x3E0000, length 0x4000) into a scratch file under tools/fleet/tmp/.
         One fresh subprocess per read resets the per-session raiden cliff (~87 KiB).
      3. Decode the blob with vpd.decode() and return the 'serial_number' value.

    Raises:
        KeyError: if 'serial_number' is absent from the VPD (blank/erased device).
        subprocess.CalledProcessError: if the EC park or raiden read fails.
    """
    TMP.mkdir(exist_ok=True)
    out_path = TMP / "ro_vpd_partial.bin"

    def run(cmd, label):
        print(f"\n===== {label} =====", flush=True)
        print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
        t0 = time.time()
        subprocess.check_call(cmd)
        print(f"  ok ({time.time() - t0:.1f}s)")

    # Use system "python3" (NOT sys.executable) for the external tools: under
    # `uv run` sys.executable is the galeflash venv (pytest-only) which lacks
    # the pyserial/pyusb that ec_console.py and raiden_write_region.py import.
    # Matches ec_console / flash_gale_fleet.py / tmp/flash_devkey_bringup.py.

    # Park the AP — grants EC control of the SPI bus.
    run(["python3", str(TOOLS / "ec_console.py"), "gale power off"],
        "park AP for VPD read")

    # Partial read via raiden_write_region.py's "_rd" INTERNAL worker subcommand
    # ("not for direct use" per that tool's docstring).  We use it anyway because
    # it is the only standalone bridge reader that runs in a FRESH subprocess,
    # which resets the ~87 KiB per-raiden-session cliff for this 16 KiB read.
    # If raiden_write_region.py is refactored, update this call site.
    run(
        [
            "python3",
            str(TOOLS / "raiden_write_region.py"),
            "_rd",
            hex(_RO_VPD_OFF),
            hex(_READ_LEN),
            str(out_path),
        ],
        f"read RO_VPD partial (0x{_RO_VPD_OFF:x}:0x{_READ_LEN:x})",
    )

    # Clean up the scratch read-back file regardless of decode outcome.
    try:
        blob = out_path.read_bytes()
        kv = vpd.decode(blob)
        return kv["serial_number"]
    finally:
        out_path.unlink(missing_ok=True)
