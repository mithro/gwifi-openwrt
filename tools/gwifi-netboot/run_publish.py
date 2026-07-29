#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Publish a factory image into a staging images/ dir (CLI wrapper).

Usage: uv run run_publish.py <factory.bin> <images_dir>
"""
import sys
from pathlib import Path

from gwifi_netboot.publish import publish

manifest = publish(Path(sys.argv[1]), Path(sys.argv[2]))
for k, v in manifest.items():
    print(f"{k}: {v}")
