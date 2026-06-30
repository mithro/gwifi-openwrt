#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Extract device identity from a Gale SPI dump and write it to an inventory JSON.

Usage:
    uv run extract_identity.py <dump> [--out DIR]

The identity JSON is written to <DIR>/<serial_number>.json (pretty-printed).
Default DIR: /home/tim/local/gwifi/fleet-flash/inventory
"""
import argparse
import json
import sys
from pathlib import Path

# Allow running directly from the tools/fleet directory
sys.path.insert(0, str(Path(__file__).parent))

from galeflash import identity

DEFAULT_INVENTORY = Path("/home/tim/local/gwifi/fleet-flash/inventory")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract curated device identity from a Gale SPI dump."
    )
    parser.add_argument("dump", type=Path, help="Path to the 8 MiB SPI dump binary.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_INVENTORY,
        metavar="DIR",
        help=f"Output directory for JSON (default: {DEFAULT_INVENTORY})",
    )
    args = parser.parse_args()

    idv = identity.from_dump(args.dump)

    serial = idv.get("serial_number")
    if not serial:
        print("ERROR: serial_number missing from identity dict", file=sys.stderr)
        sys.exit(1)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / f"{serial}.json"
    out_file.write_text(json.dumps(idv, indent=2) + "\n")

    print(json.dumps(idv, indent=2))
    print(f"\nWritten: {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
