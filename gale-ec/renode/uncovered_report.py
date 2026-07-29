#!/usr/bin/env python3
"""Complete uncovered-branch report: every uncovered conditional branch grouped by its enclosing
function, annotated with the recovered function name (where known) and each branch's coverage state
(unreached / taken-only / nottaken-only) plus the disassembled branch instruction.

Output: UNCOVERED-BY-FUNCTION.md  (and a console summary).
"""
import os

import capstone
import rda
import symbolize

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
BASE = 0x08000000
DATA = open(os.path.abspath(CAPTURED), "rb").read()
MD = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)


def disasm_at(addr):
    off = addr - BASE
    if off < 0 or off + 4 > len(DATA):
        return "?"
    for ins in MD.disasm(DATA[off:off + 4], addr):
        return "%s %s" % (ins.mnemonic, ins.op_str)
    return "(data)"


def main():
    binp = os.path.abspath(CAPTURED)
    # function entries (vector roots + call targets + pointer-table targets) and name map
    insns, cond, calls = rda.analyze(binp, extra_seeds=rda.ptr_targets(binp))
    entries = sorted(set(calls) | rda.ptr_targets(binp) | {0x08000000})
    try:
        names = symbolize.symbol_map(binp)
    except Exception:
        names = {}

    import bisect

    def enclosing(addr):
        i = bisect.bisect_right(entries, addr) - 1
        return entries[i] if i >= 0 else None

    # read uncovered list
    uncovered = []
    for l in open(os.path.join(HERE, "cap_uncovered.txt")):
        if not l.startswith("0x"):
            continue
        a, k = l.split()
        uncovered.append((int(a, 16), k))

    groups = {}
    for a, k in uncovered:
        e = enclosing(a)
        groups.setdefault(e, []).append((a, k))

    # order functions by address
    funcs = sorted(groups, key=lambda x: (x is None, x if x is not None else 0))

    lines = []
    total = len(uncovered)
    lines.append("# Complete uncovered-branch report (captured gale EC firmware)")
    lines.append("")
    lines.append("Binary: `gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin` (raw flash dump, no symtab).")
    lines.append("Denominator: rda recursive-descent, 3272 conditional branches (16-bit B<cond>, ARMv6-M).")
    lines.append("")
    lines.append("**%d uncovered branches across %d functions.** "
                 "RO functions are 0x0800xxxx; their RW mirrors are at +0x10000 (0x0801xxxx)."
                 % (total, len(funcs)))
    lines.append("")
    lines.append("Branch state: `unreached` = the branch instruction itself never executed; "
                 "`taken-only` = only the taken edge seen (fall-through never taken); "
                 "`nottaken-only` = only the fall-through seen (branch never taken).")
    lines.append("")
    lines.append("| state | count |")
    lines.append("|---|---|")
    for st in ("unreached", "taken-only", "nottaken-only"):
        lines.append("| %s | %d |" % (st, sum(1 for _, k in uncovered if k == st)))
    lines.append("")

    for e in funcs:
        g = sorted(groups[e])
        nm = names.get(e, "") if e is not None else ""
        ec = ("0x%08x" % e) if e is not None else "(no enclosing entry)"
        ur = sum(1 for _, k in g if k == "unreached")
        od = len(g) - ur
        head = "## %s  %s" % (ec, nm) if nm else "## %s" % ec
        lines.append(head)
        lines.append("%d uncovered (%d unreached, %d one-direction)" % (len(g), ur, od))
        lines.append("")
        lines.append("| branch | state | instruction |")
        lines.append("|---|---|---|")
        for a, k in g:
            lines.append("| 0x%08x | %s | `%s` |" % (a, k, disasm_at(a)))
        lines.append("")

    outp = os.path.join(HERE, "UNCOVERED-BY-FUNCTION.md")
    with open(outp, "w") as f:
        f.write("\n".join(lines))
    print("wrote %s: %d uncovered branches across %d functions" % (outp, total, len(funcs)))
    # console summary: top 25 functions by uncovered count
    top = sorted(funcs, key=lambda e: -len(groups[e]))[:25]
    print("\nTop 25 functions by uncovered-branch count:")
    print("%-12s %-26s %5s %9s %7s" % ("entry", "name", "uncov", "unreached", "1-dir"))
    for e in top:
        g = groups[e]
        ur = sum(1 for _, k in g if k == "unreached")
        nm = (names.get(e, "") if e is not None else "?")[:26]
        ec = ("0x%08x" % e) if e is not None else "?"
        print("%-12s %-26s %5d %9d %7d" % (ec, nm, len(g), ur, len(g) - ur))


if __name__ == "__main__":
    main()
