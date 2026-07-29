"""FLASH-PROTECT-GATE-OPEN lever — flips the flash_set_protect / flash_command_write arms the existing
flashwp/flashprot levers miss because of ORDERING. flash_set_protect (flash.c:503) has a gate
`if ((~flash_get_protect()) & (GPIO_ASSERTED | RO_AT_BOOT)) return;` -> the deeper arms (:513
flash_protect_at_boot(FLASH_WP_ALL) for an ALL_AT_BOOT *set*; the :491 inner `if (flash_get_protect() &
RO_AT_BOOT) range = FLASH_WP_RO` for an ALL_AT_BOOT *clear*) only run when BOTH GPIO_ASSERTED **and**
RO_AT_BOOT are already set. cov_flashwp asserts WP but sends the ALL_AT_BOOT requests while WrpValue is
still default (no RO_AT_BOOT yet) -> gate returns early -> :513 never reached. This lever establishes
WrpValue=RO-protected (0xFFFF0000) + WP asserted FIRST (so flash_get_protect() = GPIO_ASSERTED|RO_AT_BOOT),
THEN sends the ALL_AT_BOOT set/clear + RO_NOW/ALL_NOW requests with the gate OPEN. Also an UNPROTECTED
FLASH_WRITE up front for the :815 `& ALL_NOW` false side. Plus flashinfo at each stage for the :553/:561
flag-decompose prints. Genuine host-cmd/console execution. RO + RW. Accumulates tmp/flashprot2_edges.pkl.
Usage: uv run --python .venv python cov_flashprot2.py [rw]
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

RO_AT_BOOT, RO_NOW, ALL_NOW, ALL_AT_BOOT = 0x01, 0x02, 0x04, 0x40


def le32(v):
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
    trace = os.path.join(TMP, "flashprot2.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.15"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data),
                'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trfp2" @%s PC' % trace]

    # --- Phase 0: UNPROTECTED writes/erase up front (ALL_NOW clear -> flash_command_write :815 false) ---
    # EC_CMD_FLASH_WRITE (0x12) params {u32 offset, u32 size} + data. offset relative to region start.
    for off, sz in ((0x20000, 4), (0x21000, 8), (0x00000, 4)):
        c += hc(0x12, le32(off) + le32(sz) + [0] * sz)
    c += hc(0x13, le32(0x20000) + le32(0x1000))     # FLASH_ERASE unprotected
    c += cc("flashinfo")

    # --- Phase 1: establish GPIO_ASSERTED | RO_AT_BOOT so the flash_set_protect gate (:503) is OPEN ---
    # Assert WP_L (PB11, active-low) LOW + WrpValue RO-protected pattern (0xFFFF0000 = RO sectors locked
    # -> flash_get_protect() reports RO_AT_BOOT). reboot ro so the firmware re-reads protection at init.
    c += ['sysbus.flashif WrpValue 0xFFFF0000', 'gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"']
    c += cc("reboot ro", "0.7")
    c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"']      # re-assert after reboot
    if RW:
        c += cc("sysjump rw", "0.4")
        c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"']
    c += cc("flashinfo")        # decompose-print loop with RO_AT_BOOT set (:553 ro_at_boot true)

    # --- Phase 2: FLASH_PROTECT requests with the gate OPEN ---
    # ALL_AT_BOOT *set* (:513 flash_protect_at_boot(FLASH_WP_ALL)) and *clear* (:491 inner RO_AT_BOOT range).
    for m, fl in ((ALL_AT_BOOT, ALL_AT_BOOT),       # :513 set-all-at-boot (gate open)
                  (ALL_AT_BOOT, 0),                  # :491 clear-all-at-boot, RO_AT_BOOT set -> range=WP_RO
                  (RO_NOW, RO_NOW),                  # ro_now (gate open)
                  (RO_AT_BOOT, 0),                   # clear ro_at_boot request
                  (ALL_NOW, ALL_NOW),                # all_now -> now ALL_NOW set
                  (RO_AT_BOOT | ALL_AT_BOOT, RO_AT_BOOT | ALL_AT_BOOT),
                  (0xFFFFFFFF, 0xFFFFFFFF), (0xFFFFFFFF, 0)):
        c += hc(0x0015, le32(m) + le32(fl))
        c += cc("flashinfo")    # each read-back walks the flag-decompose prints (:553/:561 all/ro/stuck)

    # --- Phase 3: now ALL_NOW is set -> a write is DENIED at :815 (true side, the complement) ---
    c += hc(0x12, le32(0x20000) + le32(4) + [0, 0, 0, 0])
    c += hc(0x13, le32(0x20000) + le32(0x1000))     # erase denied too
    c += cc("flashinfo") + cc("flashwp") + cc("flashwp now")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "flashprot2.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "flashprot2_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/flashprot2_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
