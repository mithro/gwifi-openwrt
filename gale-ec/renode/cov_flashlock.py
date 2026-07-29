#!/usr/bin/env python3
"""FLASH-LOCKED / PROTECT lever — targets system_run_image_copy (system.c:544 `if (system_is_locked())`
true arm) + flash_set_protect (flash.c:491 EC_FLASH_PROTECT_ALL_AT_BOOT mask / :513 flash_protect_at_boot
(FLASH_WP_ALL)). The campaign always boots UNLOCKED, so the system_is_locked()==true paths (sysjump /
reboot / reset rejection) never run. Here we set GaleFlash WrpValue to a RO-protected pattern BEFORE
boot so flash_get_protect() reports RO_NOW and system_is_locked() returns true, then drive sysjump /
reboot / flash-protect; plus FLASH_PROTECT host commands carrying the ALL_AT_BOOT / ALL_NOW / RO_NOW
masks. Genuine execution. RO + RW. Accumulates tmp/flashlock_edges.pkl.
Usage: uv run --python .venv python cov_flashlock.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


def _le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "flashlock.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.06"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data), 'emulation RunFor "%s"' % t]

    # WrpValue patterns: 0 = ALL sectors protected (RO+RW); 0xFFFF0000 / 0x0000FFFF = RO-region protected
    # (the low groups cover RO 0x08000000..0x10000); these make flash_get_protect() report RO_NOW.
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']                            # boot NORMALLY first (WrpValue default = unprotected)
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trfl" @%s PC' % trace]
    # NOW make flash RO-protected and re-init so flash_get_protect()/system_is_locked() see it locked.
    # WrpValue with low groups cleared = RO region (0x08000000..) write-protected; reboot re-reads it.
    c += ['sysbus.flashif WrpValue 0xFFFF0000'] + cc("flashinfo") + cc("reboot ro", "0.6") + cc("flashinfo")
    # system_is_locked()==true arms: sysjump / reboot / reset are rejected when locked
    for cmd in ("sysjump rw", "sysjump ro", "sysjump a", "reboot ro", "reboot rw", "reboot",
                "sysinfo", "flashinfo", "flashwp", "flashwp now", "flashwp enable"):
        c += cc(cmd)
    # FLASH_PROTECT (0x15) mask+flags matrix: RO_AT_BOOT(0x1) RO_NOW(0x2) ALL_NOW(0x4) ALL_AT_BOOT(0x20)
    for mask, flags in [(0x01, 0x01), (0x02, 0x02), (0x04, 0x04), (0x20, 0x20), (0x20, 0x00),
                        (0x24, 0x24), (0x27, 0x27), (0x00, 0x00), (0xFFFFFFFF, 0x20)]:
        c += hc(0x15, _le32(mask) + _le32(flags))
    # sweep WrpValue live across partial-protection patterns + re-read protect via flashinfo
    for wrp in (0x00000000, 0x0000FFFF, 0xFFFF0000, 0xFFFFFFFE, 0x0000FFFE, 0xAAAAAAAA):
        c += ['sysbus.flashif WrpValue 0x%08X' % wrp] + cc("flashinfo") + hc(0x15, _le32(0) + _le32(0))
    # FLASH_PROTECT get after each, + a flash erase/write attempt while protected (WRPRTERR path)
    c += ['sysbus.flashif InjectWriteProtErr true'] + hc(0x13, _le32(0x18000) + _le32(0x800))   # erase -> WP err
    c += hc(0x12, _le32(0x18000) + _le32(4) + _le32(0xDEADBEEF))                                  # write while protected
    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "flashlock.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "flashlock_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/flashlock_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
