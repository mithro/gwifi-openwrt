# SPDX-License-Identifier: Apache-2.0
"""Tests for galeflash.bootverify — boot-capture classification.

The GOOD sample lines are lifted from the real capture of puck 2712HW0072Z
booting the flags-7 dev-key image in normal mode (2026-07-02).
"""
from galeflash import bootverify

# Trimmed, real, normal-mode dev-key boot (slot B).
GOOD_BOOT = """\
coreboot-60d1b1c Mon Jan  9 00:04:49 UTC 2017 verstage starting...
FMAP: area GBB found @ 301000 (913152 bytes)
VB2:vb2_check_recovery() Recovery reason from previous boot: 0x0 / 0x5b
VB2:vb2_report_dev_firmware() This is developer signed firmware
FMAP: area VBLOCK_B found @ 580000 (8192 bytes)
VB2:vb2_verify_fw_preamble() Verifying preamble.
FMAP: area FW_MAIN_B found @ 582000 (1367808 bytes)
        recovery | 0x00000039 |      low |       low
Jumping to boot code at 88104041(8724c000)
Starting depthcharge on gale...
MAC: 24:05:88:36:e2:f4
Sending DHCP discover...
"""

# Synthetic recovery entry: same always-printed preamble lines, then failure.
BAD_BOOT = """\
coreboot-60d1b1c Mon Jan  9 00:04:49 UTC 2017 verstage starting...
VB2:vb2_check_recovery() Recovery reason from previous boot: 0x0 / 0x5b
FMAP: area VBLOCK_A found @ 400000 (8192 bytes)
VB2:vb2_verify_keyblock() Checking key block signature...
FMAP: area FW_MAIN_A found @ 402000 (1367808 bytes)
VB2:vb2_fail() Need recovery, reason=0x17
"""

EARLY_BOOT = """\
coreboot-60d1b1c Mon Jan  9 00:04:49 UTC 2017 bootblock start
SF: Detected W25Q64 with sector size 0x1000, total 0x800000
VB2:vb2_check_recovery() Recovery reason from previous boot: 0x0 / 0x5b
"""


def test_good_boot_classified_good():
    r = bootverify.classify(GOOD_BOOT)
    assert r["verdict"] == "GOOD"
    assert r["dev_signed"] is True
    assert r["slot"] == "B"
    assert "Starting depthcharge" in r["good"]


def test_bad_boot_classified_bad():
    r = bootverify.classify(BAD_BOOT)
    assert r["verdict"] == "BAD"
    assert r["slot"] == "A"
    assert "VB2:vb2_fail" in r["bad"]


def test_bad_wins_over_good():
    """A recovery boot that still reaches a payload banner must stay BAD."""
    r = bootverify.classify(BAD_BOOT + "Starting depthcharge on gale...\n")
    assert r["verdict"] == "BAD"


def test_early_boot_is_undecided_not_bad():
    """The always-printed 'Recovery reason from previous boot' line and the
    GPIO table row containing 'recovery' must NOT trip the BAD markers."""
    r = bootverify.classify(EARLY_BOOT)
    assert r["verdict"] == "UNDECIDED"
    assert r["bad"] == []


def test_decisive_matches_classify():
    assert bootverify.decisive(GOOD_BOOT)
    assert bootverify.decisive(BAD_BOOT)
    assert not bootverify.decisive(EARLY_BOOT)


def test_slot_none_before_fw_main():
    assert bootverify.slot(EARLY_BOOT) is None
