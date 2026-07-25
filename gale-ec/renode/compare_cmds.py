#!/usr/bin/env python3
"""Compare the console-command set + per-command branch structure between the CAPTURED firmware and
the REBUILT firmware ("new firmware"). Both are analyzed with the SAME recursive-descent disassembler
(rda) so branch counts are apples-to-apples (real conditional branches only, no literal-pool noise).

CAPTURED: structural __cmds scan @0x0800ba54 (27 cmds), extents = next captured func start.
REBUILT:  __cmds from the ELF (symbols + flat image), 30 cmds, extents = nm symbol sizes.
Reports: commands only-in-one, and for shared commands the (captured vs rebuilt) branch count.
"""
import os
import string
import struct
import subprocess

import rda

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
# Vendored rebuilt firmware reference (in-repo, committed). Override via GALE_REBUILT_RO_ELF.
ELF = os.environ.get("GALE_REBUILT_RO_ELF", os.path.join(HERE, "data", "rebuilt-RO.elf"))
REB_BIN = os.path.join(HERE, "tmp", "rebuilt_RO.bin")
BASE = 0x08000000
PRINT = set(string.printable[:-6].encode())

CAP_CMDS = 0x0800ba54          # captured __cmds (structural scan)
CAP_N = 27


def reb_cmds_bounds():
    """Read __cmds / __cmds_end from the rebuilt ELF (re-derived each run; the table moves when
    the build changes)."""
    lo = hi = None
    for ln in subprocess.check_output(["arm-none-eabi-nm", ELF]).decode().splitlines():
        p = ln.split()
        if len(p) == 3 and p[2] == "__cmds":
            lo = int(p[0], 16)
        elif len(p) == 3 and p[2] == "__cmds_end":
            hi = int(p[0], 16)
    return lo, hi


def ascii_at(img, addr, maxlen=24):
    o = addr - BASE
    if not (0 <= o < len(img)):
        return None
    s = bytearray()
    while o < len(img) and img[o] != 0 and len(s) < maxlen:
        if img[o] not in PRINT:
            return None
        s.append(img[o]); o += 1
    return s.decode("latin1") if (o < len(img) and img[o] == 0 and s) else None


def rd32(img, addr):
    o = addr - BASE
    return struct.unpack_from("<I", img, o)[0]


def cap_commands(img):
    out = {}
    for i in range(CAP_N):
        ent = CAP_CMDS + i * 16
        out[ascii_at(img, rd32(img, ent))] = rd32(img, ent + 4) & ~1
    return out


def reb_commands(img):
    lo, hi = reb_cmds_bounds()
    out = {}
    for ent in range(lo, hi, 16):
        out[ascii_at(img, rd32(img, ent))] = rd32(img, ent + 4) & ~1
    return out


def reb_sizes():
    sz = {}
    for ln in subprocess.check_output(["arm-none-eabi-nm", "-S", "--numeric-sort", ELF]).decode().splitlines():
        p = ln.split()
        if len(p) == 4 and p[2] in ("t", "T", "w", "W"):
            sz[int(p[0], 16) & ~1] = (int(p[1], 16), p[3])
    return sz


def analyze(binpath, ranges):
    rda.TEXT_RANGES = ranges
    _, cond, calls = rda.analyze(binpath, extra_seeds=rda.ptr_targets(binpath))
    return cond, calls


def main():
    with open(CAP, "rb") as f:
        capimg = f.read()
    with open(REB_BIN, "rb") as f:
        rebimg = f.read()

    capcmds = cap_commands(capimg)
    rebcmds = reb_commands(rebimg)

    cond_cap, _ = analyze(CAP, [(0x08000000, 0x0800ba18), (0x08010000, 0x0801ba18)])
    reb_lo, _ = reb_cmds_bounds()
    cond_reb, _ = analyze(REB_BIN, [(0x08000000, reb_lo)])   # rebuilt code ends before __cmds rodata
    cap_addrs = sorted(cond_cap)
    reb_addrs = sorted(cond_reb)
    sizes = reb_sizes()

    # captured extents = next captured func start (from rda calls + ptr_targets)
    cap_starts = sorted(set(rda.ptr_targets(CAP)) | set(analyze(CAP, [(0x08000000, 0x0800ba18), (0x08010000, 0x0801ba18)])[1]))
    cap_starts = [a for a in cap_starts if a < 0x08010000]

    def cap_extent(h):
        nxt = [s for s in cap_starts if s > h]
        return min(nxt) if nxt else 0x0800ba18

    def cap_brs(h):
        e = cap_extent(h)
        return [a for a in cap_addrs if h <= a < e]

    def reb_brs(h):
        sz = sizes.get(h, (0, "?"))[0]
        return [a for a in reb_addrs if h <= a < h + sz]

    allnames = sorted(set(capcmds) | set(rebcmds))
    only_cap = [n for n in allnames if n in capcmds and n not in rebcmds]
    only_reb = [n for n in allnames if n in rebcmds and n not in capcmds]
    shared = [n for n in allnames if n in capcmds and n in rebcmds]

    print("captured commands: %d   rebuilt commands: %d   shared: %d\n"
          % (len(capcmds), len(rebcmds), len(shared)))
    print("ONLY in CAPTURED (%d): %s" % (len(only_cap), ", ".join(only_cap) or "-"))
    print("ONLY in REBUILT  (%d): %s\n" % (len(only_reb), ", ".join(only_reb) or "-"))

    print("  %-12s %-22s %6s   %-22s %6s  %s" % ("command", "captured handler", "br", "rebuilt fn", "br", "match"))
    print("  " + "-" * 86)
    mism = []
    for n in shared:
        ch, rh = capcmds[n], rebcmds[n]
        cb, rb = len(cap_brs(ch)), len(reb_brs(rh))
        rname = sizes.get(rh, (0, "?"))[1]
        flag = "OK" if cb == rb else "DIFF (%+d)" % (rb - cb)
        if cb != rb:
            mism.append((n, cb, rb))
        print("  %-12s 0x%08x            %6d   %-22s %6d  %s" % (n, ch, cb, rname[:22], rb, flag))
    print("  " + "-" * 86)
    print("\nbranch-count mismatches: %d" % len(mism))
    for n, cb, rb in mism:
        print("   %-12s captured=%d rebuilt=%d" % (n, cb, rb))


if __name__ == "__main__":
    main()
