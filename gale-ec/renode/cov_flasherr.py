#!/usr/bin/env python3
"""FLASH-OPTION-BYTE-ERROR lever — drives the write_optb / erase_optb wait_busy/unlock FAILURE arms
(chip/stm32/flash-f.c:110/114/122/183/188) that only run when an OPTION-BYTE program fails. These
execute in the protect-AT-BOOT path (FLASH_PROTECT with RO_AT_BOOT/ALL_AT_BOOT -> flash_protect_at_boot
-> write_optbytes -> erase_optb + write_optb). flashprog injects errors during normal write/erase but
NOT during option-byte programming, so these stayed nottaken-only (the success path only). Here we set
GaleFlash StuckBusy / InjectProgErr / InjectWriteProtErr and THEN issue a protect-at-boot change so the
option-byte wait_busy times out / OPTPG faults. Also WP-asserted (PB11 low) so protect-at-boot is honoured.
Genuine execution. RO + RW. Accumulates tmp/flasherr_edges.pkl.
Usage: uv run --python .venv python cov_flasherr.py [rw]
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


def le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "flasherr.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.08"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.2"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data),
                'emulation RunFor "%s"' % t]

    RO_AT_BOOT, ALL_AT_BOOT = 0x01, 0x40

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    # assert WP so protect-at-boot is honoured (GPIO_WP_L = PB11 low)
    c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"']
    c += ['cpu CreateExecutionTracing "trfe" @%s PC' % trace]

    def protect_at_boot(mask):
        return hc(0x0015, le32(mask) + le32(mask))

    # (1) StuckBusy during option-byte program: erase_optb/write_optb wait_busy() times out (flash-f.c:110/122)
    c += ['sysbus.flashif StuckBusy true']
    c += protect_at_boot(RO_AT_BOOT) + cc("flashinfo")
    c += protect_at_boot(ALL_AT_BOOT) + cc("flashinfo")
    c += cc("flashwp atboot") + cc("flashwp now")           # console protect-at-boot paths
    c += ['sysbus.flashif StuckBusy false', 'emulation RunFor "0.2"']

    # (2) InjectProgErr -> PGERR on the OPTPG program (flash-f.c:188 path)
    c += ['sysbus.flashif InjectProgErr true'] + protect_at_boot(RO_AT_BOOT) + cc("flashinfo")
    c += ['sysbus.flashif InjectProgErr true'] + protect_at_boot(ALL_AT_BOOT) + cc("flashinfo")

    # (3) InjectWriteProtErr -> WRPRTERR on the option-byte erase/program
    c += ['sysbus.flashif InjectWriteProtErr true'] + protect_at_boot(RO_AT_BOOT) + cc("flashinfo")
    c += ['sysbus.flashif InjectWriteProtErr true'] + protect_at_boot(ALL_AT_BOOT) + cc("flashinfo")

    # (4) clear-protect-at-boot requests (mask set, flags 0) with errors -> the un-protect option-byte path
    c += ['sysbus.flashif InjectProgErr true'] + hc(0x0015, le32(RO_AT_BOOT) + le32(0)) + cc("flashinfo")
    c += ['sysbus.flashif StuckBusy true'] + hc(0x0015, le32(ALL_AT_BOOT) + le32(0)) + cc("flashinfo")
    c += ['sysbus.flashif StuckBusy false']

    # (5) repeated injections (each self-clearing error fails the NEXT op) to walk successive arms
    for _ in range(3):
        c += ['sysbus.flashif InjectProgErr true'] + protect_at_boot(RO_AT_BOOT)
        c += ['sysbus.flashif InjectWriteProtErr true'] + protect_at_boot(ALL_AT_BOOT)
    c += cc("flashinfo")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "flasherr.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "flasherr_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/flasherr_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
