# SPDX-License-Identifier: Apache-2.0
"""Verified constants for the gale fleet flash toolkit (see docs/gale-fleet-firmware-flash-plan.md)."""
import os
import shutil
from pathlib import Path

UMBRELLA = Path("/home/tim/local/gwifi")

# The hardware tool flash_puck_usb.py imports pyusb, which lives in the SYSTEM
# python3's dist-packages (apt python3-usb) — NOT in the uv/pytest venv.  When
# the orchestrator runs under `uv run`, a bare "python3" subprocess resolves to
# the venv interpreter and ImportErrors on `usb`.  Shell the hardware tools with
# this explicit system interpreter so they work regardless of the parent env.
SYSTEM_PYTHON = "/usr/bin/python3"

# sync_sheet.py has its own inline `# /// script` deps (google-auth, requests),
# so it must be launched via `uv run` — but under a parent `uv run` the `uv`
# binary is not on the subprocess PATH (it lives in ~/.local/bin).  Resolve an
# absolute path so the spawn works regardless of PATH.
UV = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")

DC       = UMBRELLA / "depthcharge-ipq4019"
FUTILITY = DC / "vboot_reference/build/futility/futility"
CBFSTOOL = DC / "coreboot/util/cbfstool/cbfstool"
DEVKEYS  = DC / "vboot_reference/tests/devkeys"
PAYLOAD_ELF = DC / "depthcharge/build/depthcharge.elf"   # TFTP-first standard payload

# FMAP regions (offset, size) — confirmed via fmap_dump.py on a real dump
FMAP = {
    "GBB":          (0x301000, 0x0DEF00),
    "RO_FRID":      (0x3DFF00, 0x000100),
    "RO_VPD":       (0x3E0000, 0x020000),
    "VBLOCK_A":     (0x400000, 0x002000),
    "FW_MAIN_A":    (0x402000, 0x14DF00),
    "RW_SECTION_A": (0x400000, 0x160000),
    "VBLOCK_B":     (0x580000, 0x002000),
    "FW_MAIN_B":    (0x582000, 0x14DF00),
    "RW_SECTION_B": (0x580000, 0x160000),
    "RW_VPD":       (0x6E0000, 0x008000),
}
GBB_ROFRID_SPAN = (0x301000, 0x0DF000)   # GBB + RO_FRID, stops exactly at RO_VPD

# Depthcharge payload provenance.  The TFTP-first payload (PAYLOAD_ELF) is one
# fixed fleet-wide artifact; DEPTHCHARGE_GIT is the source rev that built it
# (git describe of depthcharge-ipq4019/depthcharge).  Update this when the
# payload is rebuilt — firmware.depthcharge_version() pairs it with the ELF's
# sha256 so the sheet value is both human-readable and verifiable.
DEPTHCHARGE_GIT = "c02e0cd"

# Off-site firmware backup archive (per-puck captures + flashed images).
BIG_STORAGE_HOST = "big-storage.welland.mithis.com"
BIG_STORAGE_DIR  = "/backups/machines/gwifi"

# RW_SECTION_A/B are COMPOSITES enclosing their VBLOCK_*+FW_MAIN_* leaves; the
# offline diff-gate compares LEAVES only (composites would double-report them).
COMPOSITE_REGIONS = {"RW_SECTION_A", "RW_SECTION_B"}
LEAF_FMAP = {k: v for k, v in FMAP.items() if k not in COMPOSITE_REGIONS}
# regions the build is permitted to change (the gate asserts: changed <= this).
# RO_FRID is allowed-but-unchanged-by-build (the flash step rewrites it identical).
ALLOWED_CHANGED = {"GBB", "RO_FRID", "FW_MAIN_A", "VBLOCK_A", "FW_MAIN_B", "VBLOCK_B"}
