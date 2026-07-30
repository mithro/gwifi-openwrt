#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Build a dev-key TFTP-first Gale SPI image from a faithful live dump.

Usage:
    uv run build_gale_fleet_image.py <live.bin> <out.bin>

Transforms a live SPI dump into a dev-key-signed, TFTP-first image with BOTH
firmware slots carrying the identical payload (see galeflash.imagebuild). The
build self-gates: it exits non-zero if vboot verify or the per-region
diff-gate fails, so it can NEVER emit a bad image.

On success prints the sha256 of the output and a per-region diff vs the input.
"""
import hashlib
import sys
from pathlib import Path

# Allow running directly from the tools/fleet directory.
sys.path.insert(0, str(Path(__file__).parent))

from galeflash import fmapdiff, imagebuild


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <live.bin> <out.bin>")
    live = Path(sys.argv[1])
    out = Path(sys.argv[2])
    if not live.exists():
        sys.exit(f"FATAL: live input not found: {live}")

    # build() raises on any verify/gate failure -> non-zero exit, no bad image.
    imagebuild.build(live, out)

    print("=== BUILD COMPLETE ===")
    print(f"  output : {out}  ({out.stat().st_size} B)")
    print(f"  sha256 : {_sha256(out)}")
    print()
    print("Per-region diff vs live input:")
    fmapdiff.print_diff(live.read_bytes(), out.read_bytes())


if __name__ == "__main__":
    main()
