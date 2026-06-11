#!/usr/bin/env python3
"""Map captured-firmware functions to their rebuilt-ELF counterparts (which carry DWARF symbols +
source lines), so the uncovered-branch report can be named + source-annotated.

Strategy: the captured raw dump and the rebuilt ec.RO.elf are the same source at slightly different
addresses (shift +0xbc..+0x34c, growing). For each captured function (rda entry) we fingerprint its
disassembly (cmp/sub immediates multiset + bl-call count + instruction count) and match it to the
rebuilt function (from nm ranges) with the closest fingerprint within an anchor-interpolated address
window. Anchors = console-command handlers present in both (symbolize <-> nm by name). Result:
cap_func_start -> (reb_func_start, name). A branch's source line = addr2line(reb_start + (branch -
cap_start)) since internal layout matches for a faithful reconstruction.
"""
import os
import struct
import subprocess

import capstone
import rda
import symbolize

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
# Vendored rebuilt firmware reference (self-contained in-repo; see data/README). The build that
# produces it lives outside this repo (platform/ec + toolchain), but the analysis only needs this
# committed snapshot. Override with GALE_REBUILT_RO_ELF if you rebuilt and want a fresh ELF.
ELF = os.environ.get("GALE_REBUILT_RO_ELF", os.path.join(HERE, "data", "rebuilt-RO.elf"))
BASE = 0x08000000
DATA = open(CAP, "rb").read()
RDATA = open(ELF, "rb").read()
MD = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)


def _reb_text():
    """rebuilt .text bytes mapped at their vaddr (for fingerprinting rebuilt funcs)."""
    # read the ELF program/section: use objdump to get .text file offset + vaddr
    out = subprocess.run(["arm-none-eabi-objdump", "-h", ELF], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        p = ln.split()
        if len(p) >= 6 and p[1] == ".text":
            size = int(p[2], 16); vma = int(p[3], 16); off = int(p[5], 16)
            return vma, RDATA[off:off + size]
    return None, b""


REB_VMA, REB_TEXT = _reb_text()


def _disasm_window(blob, vma, start, end):
    out = []
    off = start - vma
    if off < 0:
        return out
    for ins in MD.disasm(blob[off:off + (end - start)], start):
        out.append(ins)
    return out


def _rd32(blob, vma, a):
    o = a - vma
    return (blob[o] | (blob[o + 1] << 8) | (blob[o + 2] << 16) | (blob[o + 3] << 24)) \
        if 0 <= o + 4 <= len(blob) else None


def fingerprint(blob, vma, start, end):
    imms = []
    consts = []          # scalar constants loaded via ldr [pc] — IDENTICAL across cap/reb (no shift)
    nbl = 0
    n = 0
    for ins in _disasm_window(blob, vma, start, min(end, start + 0x600)):
        n += 1
        if ins.mnemonic in ("cmp", "cmn", "subs", "adds", "movs") and "#" in ins.op_str:
            try:
                imms.append(int(ins.op_str.split("#")[1], 0) & 0xFFFFFFFF)
            except Exception:
                pass
        if ins.mnemonic == "ldr" and "[pc" in ins.op_str:
            try:
                imm = int(ins.op_str.split("#")[1].rstrip("]"), 0)
                v = _rd32(blob, vma, ((ins.address + 4) & ~3) + imm)
                # keep only NON-pointer scalars (constants don't shift; addresses do)
                if v is not None and not (0x08000000 <= v < 0x08020000) and not (0x20000000 <= v < 0x20020000):
                    consts.append(v)
            except Exception:
                pass
        if ins.mnemonic in ("bl",):
            nbl += 1
    return (n, nbl, tuple(sorted(imms)), tuple(sorted(consts)))


def _imm_dist(a, b):
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    return sum((ca - cb).values()) + sum((cb - ca).values())


def fp_dist(fa, fb):
    # constants are the strongest discriminator (identical across cap/reb for the same function)
    return (abs(fa[0] - fb[0]) + 2 * abs(fa[1] - fb[1]) + _imm_dist(fa[2], fb[2])
            + 4 * _imm_dist(fa[3], fb[3]))


def build_map():
    # rebuilt funcs: nm -> sorted (addr,name), ranges
    reb = []
    for ln in subprocess.run(["arm-none-eabi-nm", "-n", ELF], capture_output=True, text=True).stdout.splitlines():
        p = ln.split()
        if len(p) == 3 and p[1] in "tT" and REB_VMA <= int(p[0], 16) < REB_VMA + len(REB_TEXT):
            reb.append((int(p[0], 16), p[2]))
    reb.sort()
    reb_starts = [a for a, _ in reb]
    reb_end = {reb[i][0]: (reb[i + 1][0] if i + 1 < len(reb) else REB_VMA + len(REB_TEXT))
               for i in range(len(reb))}
    reb_name = dict(reb)
    reb_fp = {a: fingerprint(REB_TEXT, REB_VMA, a, reb_end[a]) for a, _ in reb}

    # captured funcs
    ins, cond, calls = rda.analyze(CAP, extra_seeds=rda.ptr_targets(CAP))
    cap = sorted(f for f in (set(calls) | rda.ptr_targets(CAP)) if f < 0x08010000)
    cap_end = {cap[i]: (cap[i + 1] if i + 1 < len(cap) else 0x08010000) for i in range(len(cap))}

    # anchors from console names
    cap_names = symbolize.symbol_map(CAP)
    reb_n2a = {n: a for a, n in reb}
    anchors = sorted((ca, reb_n2a[nm]) for ca, nm in cap_names.items()
                     if ca < 0x08010000 and nm in reb_n2a)

    def interp_shift(ca):
        if not anchors:
            return 0x180
        if ca <= anchors[0][0]:
            return anchors[0][1] - anchors[0][0]
        if ca >= anchors[-1][0]:
            return anchors[-1][1] - anchors[-1][0]
        for i in range(len(anchors) - 1):
            c0, r0 = anchors[i]; c1, r1 = anchors[i + 1]
            if c0 <= ca <= c1:
                s0, s1 = r0 - c0, r1 - c1
                return int(s0 + (s1 - s0) * (ca - c0) / max(1, c1 - c0))
        return anchors[-1][1] - anchors[-1][0]

    mapping = {}   # cap_start -> (reb_start, name, confidence)
    for cs in cap:
        fp = fingerprint(DATA, BASE, cs, cap_end[cs])
        est = cs + interp_shift(cs)
        # candidate rebuilt funcs within +-0x500 of est
        best = None
        for ra, nm in reb:
            if abs(ra - est) > 0x500:
                continue
            d = fp_dist(fp, reb_fp[ra]) + abs(ra - est) // 0x80
            if best is None or d < best[0]:
                best = (d, ra, nm)
        if best:
            conf = "exact" if best[0] == 0 else ("high" if best[0] <= 3 else "approx")
            mapping[cs] = (best[1], best[2], conf)
    return mapping, cap_end


if __name__ == "__main__":
    m, _ = build_map()
    # sanity: print the console-anchor functions' mapping + a few others
    import symbolize as S
    capn = S.symbol_map(CAP)
    ok = 0; tot = 0
    for cs, (ra, nm, conf) in sorted(m.items()):
        if cs in capn:
            tot += 1
            match = (nm == capn[cs])
            ok += match
            print("  %#010x -> %#010x %-22s conf=%-6s anchor=%-18s %s"
                  % (cs, ra, nm, conf, capn[cs], "OK" if match else "MISMATCH"))
    print("anchor self-match: %d/%d" % (ok, tot))
    print("total mapped: %d" % len(m))
