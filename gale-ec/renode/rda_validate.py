#!/usr/bin/env python3
"""Validate rda.py against the rebuilt ELF ground truth.

The rebuilt firmware HAS a real ELF (proper .text/.symtab), so objdump on it gives the exact
set of conditional-branch addresses. Running rda on the rebuilt RAW binary and comparing tells
us rda's accuracy: false positives (rda calls a branch that the ELF says is data) and false
negatives (real ELF branches rda missed). Only once rda matches the ELF can we trust its
denominator on the CAPTURED dump, which has no ELF to check against.
"""
import os
import re
import subprocess

import rda

HERE = os.path.dirname(os.path.abspath(__file__))
OBJDUMP = "arm-none-eabi-objdump"   # system cross-binutils on PATH
# Vendored rebuilt firmware refs (in-repo, committed); override via GALE_REBUILT_R{O,W}_ELF.
RW_ELF = os.environ.get("GALE_REBUILT_RW_ELF", os.path.join(HERE, "data", "rebuilt-RW.elf"))
RO_ELF = os.environ.get("GALE_REBUILT_RO_ELF", os.path.join(HERE, "data", "rebuilt-RO.elf"))
REBUILT = "ec-rebuilt.bin"
COND = re.compile(r'\b(b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)|cbz|cbnz)(\.[nw])?\b')


def elf_branches(elf):
    """Ground-truth conditional-branch addresses from the ELF (objdump -d only walks .text)."""
    out = subprocess.run([OBJDUMP, "-d", elf], stdout=subprocess.PIPE,
                         universal_newlines=True).stdout
    br = set()
    insns = set()
    for ln in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f ]+?)\s+(\S.*)$', ln)
        if not m:
            continue
        addr = int(m.group(1), 16)
        insns.add(addr)
        if COND.search(m.group(3)):
            br.add(addr)
    return insns, br


def main():
    ro_insn, ro_br = elf_branches(RO_ELF)
    rw_insn, rw_br = elf_branches(RW_ELF)
    elf_br = ro_br | rw_br
    elf_insn = ro_insn | rw_insn
    print("ELF ground truth: %d cond branches (RO %d + RW %d), %d insns" %
          (len(elf_br), len(ro_br), len(rw_br), len(elf_insn)))

    # rda seeded by vector table + ALL pointer-table targets (closest to "all reachable code"
    # without an execution trace).
    seeds = rda.ptr_targets(REBUILT)
    insns, cond, calls = rda.analyze(REBUILT, extra_seeds=seeds)
    rda_br = set(cond)
    print("rda (vectors + ptr-table seeds): %d cond branches, %d insns" % (len(rda_br), len(insns)))

    fp = rda_br - elf_br          # rda says branch, ELF disagrees -> false positive (data?)
    fn = elf_br - rda_br          # ELF branch rda missed -> false negative (unreachable code?)
    print("  false positives (rda extra):   %d" % len(fp))
    print("  false negatives (rda missing): %d" % len(fn))
    print("  matched: %d / %d ELF branches = %.1f%%" %
          (len(rda_br & elf_br), len(elf_br), 100.0 * len(rda_br & elf_br) / len(elf_br)))
    # Sample the discrepancies for inspection.
    if fp:
        print("  sample FP:", [hex(a) for a in sorted(fp)[:15]])
    if fn:
        print("  sample FN:", [hex(a) for a in sorted(fn)[:15]])


if __name__ == "__main__":
    main()
