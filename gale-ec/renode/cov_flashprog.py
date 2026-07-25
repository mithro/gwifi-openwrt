#!/usr/bin/env python3
"""FLASH-PROGRAMMING lever — targets the flash-f.c driver clusters write_optb (0x08000f44),
flash_physical_erase (0x080010e0), flash_set_protect (0x0800451c) per UNCOVERED-BY-FUNCTION.md:
the busy-wait/timeout loops (`while (STM32_FLASH_SR & 1) && time < deadline`), the already-erased
shortcut (`flash_is_erased`), the program/write-protect error returns (PGERR / WRPRTERR), and the
option-byte programming path (write_optb via flash_protect_at_boot). Driven by FLASH_* host commands +
GaleFlash fault knobs (StuckBusy / InjectProgErr / InjectWriteProtErr / WrpValue). Genuine execution.
RO + RW. Accumulates tmp/flashprog_edges.pkl.
Usage: uv run --python .venv python cov_flashprog.py [rw]
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
RWOFF = 0x18000   # an RW-region flash offset safe to erase/write in the model


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
    trace = os.path.join(TMP, "flashprog.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.1"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data), 'emulation RunFor "%s"' % t]

    ERASE = lambda off, sz: hc(0x13, _le32(off) + _le32(sz), "0.3")
    WRITE = lambda off, data: hc(0x12, _le32(off) + _le32(len(data)) + list(data), "0.2")

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trfp" @%s PC' % trace]

    # 1) NORMAL erase then erase AGAIN -> flash_is_erased() shortcut (region already 0xFF)
    c += ERASE(RWOFF, 0x800)
    c += ERASE(RWOFF, 0x800)                                   # already erased -> shortcut arm
    c += cc("flashinfo")
    # 2) StuckBusy: SR&1 stays set -> the busy-wait loop iterates to the deadline -> TIMEOUT arm
    c += ['sysbus.flashif StuckBusy true']
    c += ERASE(RWOFF, 0x800, ) + WRITE(RWOFF, [0xDE, 0xAD, 0xBE, 0xEF])
    c += ['sysbus.flashif StuckBusy false']
    # 3) InjectProgErr -> PGERR on write; InjectWriteProtErr -> WRPRTERR on erase
    c += ['sysbus.flashif InjectProgErr true'] + WRITE(RWOFF, [1, 2, 3, 4])
    c += ['sysbus.flashif InjectWriteProtErr true'] + ERASE(RWOFF, 0x800)
    # 4) console flash ops too
    c += cc("flasherase 0x18000 0x800") + cc("flashwrite 0x18000 4") + cc("flashinfo")
    # 5) write_optb: FLASH_PROTECT changing AT-BOOT protection -> flash_protect_at_boot -> write_optb
    #    (toggle the protection state so the option bytes actually re-program)
    for mask, flags in [(0x01, 0x01), (0x01, 0x00), (0x20, 0x20), (0x20, 0x00), (0x04, 0x04), (0x02, 0x02)]:
        c += ['sysbus.flashif WrpValue 0xFFFF0000'] + hc(0x15, _le32(mask) + _le32(flags))
        c += ['sysbus.flashif WrpValue 0xFFFFFFFF'] + hc(0x15, _le32(mask) + _le32(flags))
    c += cc("flashwp now") + cc("flashwp enable") + cc("flashwp disable")
    # 6) erase/write at RO offset (protected) + bad/misaligned offsets -> bounds/error arms
    c += ERASE(0x0, 0x800) + WRITE(0x0, [0, 0, 0, 0]) + ERASE(0x1, 0x7FF) + WRITE(0x18001, [1, 2, 3])

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "flashprog.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "flashprog_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/flashprog_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
