# SPDX-License-Identifier: Apache-2.0
"""Combined dev-key TFTP-first SPI image builder for Gale pucks.

Generalizes two proven prototypes (tmp/build_devkey_bringup.py and
tmp/build_depthcharge_image_v2.py) into a single, per-puck-generic
``build()`` that transforms a faithful live SPI dump into a dev-key-signed,
TFTP-first image with BOTH firmware slots carrying the identical payload.

Build order (confirmed empirically against a stock G4 dump in Task 4):
  1. copy live -> out.
  2. GBB rootkey -> dev (``futility gbb_utility --set -k root_key.vbpubk``).
  3. ``cbfstool remove fallback/payload`` from FW_MAIN_A. Stock's LAST CBFS
     entry IS ``fallback/payload`` (not an empty sentinel); the remove leaves
     a trailing empty entry.
  4. ``cbfs.extend_fw_main_a`` — grow that empty entry to fill the FMAP region
     so the larger TFTP-first payload fits.
  5. ``cbfstool add-payload fallback/payload`` (the TFTP-first depthcharge.elf).
  6. Mirror FW_MAIN_A body -> FW_MAIN_B (equal-size region copy; both slots now
     carry the identical payload). Only the FW_MAIN_B body is touched.
  7. Sign BOTH slots (per-slot ``vbutil_firmware`` + vblock splice, dev
     keyblock; bodies are identical so one keyblock signs both).
  8. ``futility verify``.
  9. Diff-gate: changed regions <= ALLOWED_CHANGED and VPD untouched.

``build()`` raises if verify or the diff-gate fails — it must NEVER emit an
image that does not verify or that touched per-device VPD.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from galeflash import cbfs, const, fmapdiff

# In-tree scratch dir (NO /tmp). Temp FV / vblock files live here, cleaned up.
TMPDIR = Path(__file__).resolve().parent.parent / "tmp"


def _run(*cmd) -> subprocess.CompletedProcess:
    """Run a subprocess, raising RuntimeError with captured output on failure."""
    proc = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed (rc={proc.returncode}): {' '.join(map(str, cmd))}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc


def sign_slot(out: Path, slot: str) -> None:
    """Sign one firmware slot in-place: per-slot ``vbutil_firmware`` + splice.

    Ports the v2 prototype's signing method, parameterized by *slot* ("A"/"B").
    The slot's full ``FW_MAIN_{slot}`` region is the firmware volume, so the new
    preamble's ``body_size`` == the FMAP region size (matching coreboot's
    runtime CBFS bound). The dev keyblock is used; ``--flags 0`` drops
    USE_RO_NORMAL so the body hash is actually checked at verify/runtime.
    """
    vb_off, vb_size = const.FMAP[f"VBLOCK_{slot}"]
    fw_off, fw_size = const.FMAP[f"FW_MAIN_{slot}"]

    TMPDIR.mkdir(parents=True, exist_ok=True)
    fv: Path | None = None
    nvb: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=TMPDIR, prefix=f"_fv_{slot}_", suffix=".bin", delete=False
        ) as f:
            fv = Path(f.name)
        with tempfile.NamedTemporaryFile(
            dir=TMPDIR, prefix=f"_vblock_{slot}_", suffix=".bin", delete=False
        ) as f:
            nvb = Path(f.name)

        # Firmware volume = the slot's full FW_MAIN region (records body_size).
        buf = out.read_bytes()
        fv.write_bytes(buf[fw_off:fw_off + fw_size])

        _run(
            const.FUTILITY, "vbutil_firmware",
            "--vblock", nvb,
            "--keyblock", const.DEVKEYS / "dev_firmware.keyblock",
            "--signprivate", const.DEVKEYS / "dev_firmware_data_key.vbprivk",
            "--version", "1",
            "--fv", fv,
            "--kernelkey", const.DEVKEYS / "kernel_subkey.vbpubk",
            "--flags", "0",
        )

        # Splice the produced vblock into the image, zero-pad to region size.
        new_vb = nvb.read_bytes()
        if len(new_vb) > vb_size:
            raise RuntimeError(
                f"new VBLOCK_{slot} ({len(new_vb)} B) > region size ({vb_size} B)"
            )
        mut = bytearray(out.read_bytes())
        mut[vb_off:vb_off + vb_size] = new_vb + b"\x00" * (vb_size - len(new_vb))
        out.write_bytes(bytes(mut))
    finally:
        for p in (fv, nvb):
            if p is not None:
                p.unlink(missing_ok=True)


def build(live: Path, out: Path) -> None:
    """Build a dev-key TFTP-first image from *live* into *out* (see module doc).

    Raises RuntimeError if the image fails ``futility verify`` or if the
    diff-gate (changed regions must be a subset of ALLOWED_CHANGED, with VPD
    untouched) fails — the build never emits a bad image.
    """
    live = Path(live)
    out = Path(out)

    # 1. start from a faithful copy of the live dump
    shutil.copy2(live, out)

    # 2. GBB rootkey -> dev public rootkey (so the dev keyblock chains)
    _run(const.FUTILITY, "gbb_utility", "--set",
         "-k", const.DEVKEYS / "root_key.vbpubk", out)

    # 3. remove stock fallback/payload (leaves a trailing CBFS empty entry)
    _run(const.CBFSTOOL, out, "remove", "-r", "FW_MAIN_A", "-n", "fallback/payload")

    # 4. grow that empty entry to fill the FW_MAIN_A FMAP region
    cbfs.extend_fw_main_a(out)

    # 5. add the TFTP-first payload
    _run(const.CBFSTOOL, out, "add-payload", "-r", "FW_MAIN_A",
         "-n", "fallback/payload", "-f", const.PAYLOAD_ELF, "-c", "lzma")

    # 6. mirror FW_MAIN_A body -> FW_MAIN_B (equal-size region copy; only the
    #    FW_MAIN_B body, leaving RW_FWID_B / RW_SHARED untouched)
    a_off, a_size = const.FMAP["FW_MAIN_A"]
    b_off, b_size = const.FMAP["FW_MAIN_B"]
    if a_size != b_size:
        raise RuntimeError(
            f"FW_MAIN_A size ({a_size}) != FW_MAIN_B size ({b_size})")
    mut = bytearray(out.read_bytes())
    mut[b_off:b_off + b_size] = mut[a_off:a_off + a_size]
    out.write_bytes(bytes(mut))

    # 7. sign BOTH slots (dev keyblock; bodies identical)
    sign_slot(out, "A")
    sign_slot(out, "B")

    # 8. offline vboot verify — must pass
    _run(const.FUTILITY, "verify", out)

    # 9. diff-gate — never emit an image that touched disallowed regions or VPD
    changed = fmapdiff.changed_regions(live.read_bytes(), out.read_bytes())
    if not changed <= const.ALLOWED_CHANGED:
        raise RuntimeError(
            f"diff-gate failed: changed regions {sorted(changed)} not a subset "
            f"of ALLOWED_CHANGED {sorted(const.ALLOWED_CHANGED)}; offending: "
            f"{sorted(changed - const.ALLOWED_CHANGED)}")
    if "RO_VPD" in changed or "RW_VPD" in changed:
        raise RuntimeError(f"diff-gate failed: VPD changed ({sorted(changed)})")
