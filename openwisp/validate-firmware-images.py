#!/usr/bin/env python3
"""Validate the OPENWISP_CUSTOM_OPENWRT_IMAGES staged in playbook.yml.

Run:  uv run --with pyyaml python openwisp/validate-firmware-images.py

Reproduces openwisp_firmware_upgrader/hardware.py (1.2.1) exactly:

    if app_settings.CUSTOM_OPENWRT_IMAGES:
        OPENWRT_FIRMWARE_IMAGE_MAP = OrderedDict(app_settings.CUSTOM_OPENWRT_IMAGES)
    ...
    OPENWRT_FIRMWARE_IMAGE_MAP.update(OrderedDict(<stock map>))
    for key, info in FIRMWARE_IMAGE_MAP.items():
        for board in info["boards"]:
            REVERSE_FIRMWARE_IMAGE_MAP[board] = key

OpenWISP matches a device to a firmware image by testing `device.model`
against each image's `boards` tuple, so this asserts that the model strings
our hardware reports (`ubus call system board` -> .model) resolve to the
intended sysupgrade image-type keys. It also cross-checks every key against a
real artifact / device profile in the sibling OpenWrt tree, so a typo in an
image name fails loudly here instead of silently never matching on the box.

Exits non-zero on any mismatch.
"""
from collections import OrderedDict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PLAYBOOK = HERE / "playbook.yml"
OPENWRT = HERE.parent / "openwrt"  # the OpenWrt 25.12.2 build tree

# What each device reports as `.model` -> the sysupgrade image-type key we expect.
EXPECT = {
    "Google WiFi (Gale)": "ipq40xx-chromium-google_wifi-squashfs-sysupgrade.bin",
    "Google Wifi": "ipq40xx-chromium-google_wifi-squashfs-sysupgrade.bin",
    "OpenMesh OM2P-LC": "ath79-generic-openmesh_om2p-lc-squashfs-sysupgrade.bin",
    "OpenMesh OM2P v1": "ath79-generic-openmesh_om2p-v1-squashfs-sysupgrade.bin",
    "OpenMesh OM2P v2": "ath79-generic-openmesh_om2p-v2-squashfs-sysupgrade.bin",
    "OpenMesh OM2P v4": "ath79-generic-openmesh_om2p-v4-squashfs-sysupgrade.bin",
}


def load_custom_images():
    """Exec the verbatim Python the role renders into settings.py."""
    play = next(iter(yaml.safe_load_all(PLAYBOOK.read_text())))[0]
    instr = play["vars"]["openwisp2_extra_django_settings_instructions"]
    assert isinstance(instr, list), "instructions must be a YAML list"
    block = "\n".join(instr)
    compile(block, "<settings_instructions>", "exec")  # SyntaxError if malformed
    ns: dict = {}
    exec(block, ns)  # noqa: S102 - validating our own staged code
    return ns["OPENWISP_CUSTOM_OPENWRT_IMAGES"]


def build_reverse_map(custom):
    """Mirror hardware.py: OrderedDict(custom), then derive REVERSE map."""
    fw_map = OrderedDict(custom)  # raises if entries aren't 2-tuples
    reverse: dict = {}
    for key, info in fw_map.items():
        assert set(info) >= {"label", "boards"}, f"{key}: missing label/boards"
        assert isinstance(info["boards"], (tuple, list)), f"{key}: boards not a seq"
        for board in info["boards"]:
            assert board not in reverse, f"duplicate board {board!r}"
            reverse[board] = key
    return fw_map, reverse


def cross_check_artifacts(reverse):
    """Every image-type key must correspond to something real in the tree."""
    if not OPENWRT.exists():
        print(f"[skip] OpenWrt tree not present at {OPENWRT}; artifact check skipped")
        return
    gale = "ipq40xx-chromium-google_wifi-squashfs-sysupgrade.bin"
    art = OPENWRT / "bin/targets/ipq40xx/chromium" / ("openwrt-" + gale)
    assert art.exists(), f"gale artifact missing: {art}"
    print(f"[OK] gale artifact present: {art.name}")

    mk = (OPENWRT / "target/linux/ath79/image/generic.mk").read_text()
    for prof in ("openmesh_om2p-lc", "openmesh_om2p-v1",
                 "openmesh_om2p-v2", "openmesh_om2p-v4"):
        assert f"define Device/{prof}\n" in mk, f"missing Device/{prof} in generic.mk"
        key = f"ath79-generic-{prof}-squashfs-sysupgrade.bin"
        assert key in reverse.values(), f"image key not mapped: {key}"
    print("[OK] OM2P device profiles exist in ath79/generic.mk; keys match")


def main():
    custom = load_custom_images()
    fw_map, reverse = build_reverse_map(custom)
    print(f"=== {len(fw_map)} custom image types, {len(reverse)} board aliases ===")
    for board, key in sorted(reverse.items()):
        print(f"  {board!r:32} -> {key}")

    for board, want in EXPECT.items():
        got = reverse.get(board)
        assert got == want, f"board {board!r}: got {got!r}, want {want!r}"
    print("\n[OK] all expected board->image mappings present and correct")

    cross_check_artifacts(reverse)
    print("\nVALIDATION PASSED")


if __name__ == "__main__":
    main()
