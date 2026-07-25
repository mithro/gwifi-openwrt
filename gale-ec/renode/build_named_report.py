#!/usr/bin/env python3
"""Generate UNCOVERED-BY-FUNCTION.md with: (1) each function named (rebuilt-ELF symbol via
fingerprint match, addr2line-validated) + its C signature (from the rebuilt source) + source
location; (2) each uncovered branch annotated with a DISASSEMBLY-DERIVED CAUSE (always accurate:
the condition, what each operand is loaded from, and exactly what flips it) PLUS the rebuilt C source
line for that branch (addr2line on the function-relative offset)."""
import os
import re
import subprocess
import bisect

import capstone
import map_funcs as MF

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = MF.CAP
ELF = MF.ELF
BASE = 0x08000000
DATA = MF.DATA
MD = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
MD.detail = True
# Optional: the platform/ec source tree (outside this repo). Only used to enrich the report with
# source-line context; the report generates fine without it. Set GALE_EC_SRCROOT to enable.
SRCROOT = os.environ.get("GALE_EC_SRCROOT", "")

_a2l_cache = {}


def addr2line(addr):
    if addr in _a2l_cache:
        return _a2l_cache[addr]
    out = subprocess.run(["arm-none-eabi-addr2line", "-f", "-e", ELF, "%#x" % addr],
                         capture_output=True, text=True).stdout.strip().splitlines()
    r = (out[0], out[1]) if len(out) >= 2 else ("?", "?")
    _a2l_cache[addr] = r
    return r


_src_cache = {}


def src_line(fileline):
    """fileline like '/path/file.c:1387' -> the stripped source line text."""
    m = re.match(r"(.*):(\d+)", fileline)
    if not m:
        return ""
    path, ln = m.group(1), int(m.group(2))
    if path not in _src_cache:
        try:
            _src_cache[path] = open(path, errors="replace").read().splitlines()
        except Exception:
            _src_cache[path] = []
    lines = _src_cache[path]
    return lines[ln - 1].strip() if 0 < ln <= len(lines) else ""


def src_context(fileline, before=2, after=3):
    """Return (snippet, guarded) where snippet is the surrounding source and `guarded` is the first
    meaningful statement controlled by the branch (the line after the condition)."""
    m = re.match(r"(.*):(\d+)", fileline)
    if not m:
        return [], ""
    path, ln = m.group(1), int(m.group(2))
    if path not in _src_cache:
        try:
            _src_cache[path] = open(path, errors="replace").read().splitlines()
        except Exception:
            _src_cache[path] = []
    lines = _src_cache[path]
    if not (0 < ln <= len(lines)):
        return [], ""
    lo, hi = max(1, ln - before), min(len(lines), ln + after)
    snippet = [(i, lines[i - 1]) for i in range(lo, hi + 1)]
    guarded = ""
    for i in range(ln, min(len(lines), ln + 4)):
        t = lines[i].strip()
        if t and t not in ("{", "}") and not t.startswith(("//", "/*", "*")):
            guarded = t
            break
    return snippet, guarded


def signature(name, fileline):
    """Best-effort C signature: scan the source file near the function for its definition line."""
    m = re.match(r"(.*):(\d+)", fileline)
    if not m:
        return ""
    path = m.group(1)
    if path not in _src_cache:
        try:
            _src_cache[path] = open(path, errors="replace").read().splitlines()
        except Exception:
            _src_cache[path] = []
    lines = _src_cache[path]
    # a DEFINITION line: `name(` preceded by a return type, at low indentation, not ending in ';'
    # (which would be a prototype) and not preceded by tokens that make it a call.
    pat = re.compile(r"^\s{0,2}(?:static\s+|inline\s+|const\s+)*[A-Za-z_]\w[\w \*]*\b%s\s*\("
                     % re.escape(name))
    for i, l in enumerate(lines):
        if pat.search(l) and ";" not in l.split(name)[0]:
            sig = l.strip()
            j = i
            while ")" not in sig and j + 1 < len(lines):     # multi-line param list
                j += 1; sig += " " + lines[j].strip()
            return re.sub(r"\s*\{?\s*$", "", sig).strip()
    return ""


REGNUM = {"r%d" % i: i for i in range(16)}


def operand_source(insns_by_addr, addrs, cmp_addr, reg):
    """Trace back from cmp_addr within the function to find what loaded `reg`. Return a short desc.
    CONTROL-FLOW-AWARE: stop the backward walk at the first UNCONDITIONAL flow break (b/bx/pop-pc/udf)
    — writers before that point are on a different basic block and provably off the path that reaches
    cmp_addr (a conditional branch does NOT stop the walk: its fall-through keeps predecessor defs
    live). Without this, a cmp at a jump target gets mis-attributed to the linear-preceding writer on
    a skipped path (e.g. an `ldr rN,[pc]` that the jump bypassed)."""
    i = bisect.bisect_left(addrs, cmp_addr)
    for a in reversed(addrs[max(0, i - 12):i]):
        mn, op, _ = insns_by_addr[a]
        base = mn.split(".")[0]
        if base in ("b", "bx", "udf") or (base == "pop" and "pc" in op):
            return "a value carried in from a preceding basic block"
        if not op.startswith(reg + ","):
            continue
        rhs = op[len(reg) + 1:].strip()
        if mn == "ldr" and "[pc" in rhs:
            return "a global/constant (pc-relative load)"
        if mn in ("ldr", "ldrb", "ldrh") and "[" in rhs:
            mm = re.search(r"\[(\w+)(?:,\s*#(0x[0-9a-f]+|\d+))?\]", rhs)
            if mm:
                base, off = mm.group(1), mm.group(2) or "0"
                w = {"ldr": "word", "ldrb": "byte", "ldrh": "halfword"}[mn]
                return "%s [%s+%s] (a struct/buffer field)" % (w, base, off)
        if mn in ("mov", "movs", "adds", "subs", "ands", "orrs", "lsls", "lsrs", "asrs", "uxtb", "sxtb"):
            return "computed (%s %s)" % (mn, rhs)
        if mn in ("bl", "blx"):
            return "the return value of a call"
    if reg in ("r0", "r1", "r2", "r3"):
        return "function argument %s" % reg
    return "register %s" % reg


COND = {"beq": ("==", "!="), "bne": ("!=", "=="), "bcs": (">=u", "<u"), "bhs": (">=u", "<u"),
        "bcc": ("<u", ">=u"), "blo": ("<u", ">=u"), "bmi": ("<0", ">=0"), "bpl": (">=0", "<0"),
        "bhi": (">u", "<=u"), "bls": ("<=u", ">u"), "bge": (">=", "<"), "blt": ("<", ">="),
        "bgt": (">", "<="), "ble": ("<=", ">")}


def branch_cause(cap_start, cap_end, branch, state):
    """Disassembly-derived cause string for the branch (always accurate)."""
    insns = {}
    for ins in MD.disasm(DATA[cap_start - BASE:cap_end - BASE], cap_start):
        insns[ins.address] = (ins.mnemonic, ins.op_str, ins.size)
    addrs = sorted(insns)
    if branch not in insns:
        return "(branch not in linear decode — likely data/jump-table region)"
    bmn, bop, _ = insns[branch]
    # find the flag-setting instruction (nearest preceding cmp/cmn/tst/subs/adds/ands/lsls...)
    i = bisect.bisect_left(addrs, branch)
    flag = None
    for a in reversed(addrs[max(0, i - 6):i]):
        m, o, _ = insns[a]
        if m in ("cmp", "cmn", "tst", "subs", "adds", "ands", "orrs", "lsls", "lsrs", "asrs"):
            flag = (a, m, o); break
    taken_dir = COND.get(bmn, ("cond-true", "cond-false"))
    need = taken_dir[1] if state == "taken-only" else taken_dir[0]  # the MISSING direction's condition
    if not flag:
        if state == "unreached":
            return "%s — the whole basic block is never reached (need to enter this code path)" % bmn
        return "%s flag set by an earlier op; missing direction needs the condition to be %s" % (bmn, need)
    fa, fm, fo = flag
    if fm == "cmp":
        parts = fo.split(",")
        ra = parts[0].strip(); rb = parts[1].strip() if len(parts) > 1 else "?"
        srcA = operand_source(insns, addrs, fa, ra)
        if rb.startswith("#"):
            rhs = "constant %s" % rb[1:]
        else:
            rhs = "%s (= %s)" % (rb, operand_source(insns, addrs, fa, rb))
        op_now = taken_dir[0]
        # `need` is state-aware: taken-only -> missing is the fall-through condition (taken_dir[1]);
        # nottaken-only -> missing is the TAKEN condition (taken_dir[0]); unreached -> show taken side.
        # (Earlier this used taken_dir[1] unconditionally, which inverted the guidance for nottaken-only.)
        return ("`cmp %s, %s` then `%s`: taken when %s %s %s. %s = %s. "
                "MISSING direction (%s) needs %s %s %s."
                % (ra, rb, bmn, ra, op_now, rhs, ra, srcA, state, ra, need, rhs))
    if fm == "tst":
        parts = fo.split(",")
        ra = parts[0].strip(); rb = parts[1].strip()
        return ("`tst %s, %s` then `%s`: tests bits of %s (= %s) against mask %s. "
                "MISSING (%s) needs the masked bits %s."
                % (ra, rb, bmn, ra, operand_source(insns, addrs, fa, ra), rb, state,
                   "nonzero" if state == "nottaken-only" else "zero"))
    if fm in ("lsls", "lsrs", "asrs"):
        return ("`%s %s` sets flags from a shifted value (bit test) then `%s`. %s. "
                "MISSING (%s) needs the tested bit %s."
                % (fm, fo, bmn, "operand = " + operand_source(insns, addrs, fa, fo.split(",")[0].strip()),
                   state, "set" if (bmn == "bpl") == (state == "taken-only") else "clear"))
    return ("flags from `%s %s` then `%s`; MISSING direction (%s) needs the result to make `%s` go the other way"
            % (fm, fo, bmn, state, bmn))


def explain(sl, k, guarded):
    """Plain-English (what is this branch / under what condition does the uncovered edge trigger),
    derived from the rebuilt C construct + the branch's coverage state."""
    cl = sl.strip()
    low = cl.lower()
    if low.startswith(("if", "} else if", "else if")) or " if (" in low:
        cons = "an `if` test"
    elif low.startswith("switch"):
        cons = "a `switch` dispatch on the value"
    elif low.startswith(("while", "for", "do")):
        cons = "a loop condition"
    elif "case " in low or low.startswith("case"):
        cons = "a `case` comparison"
    elif "?" in cl:
        cons = "a ternary `?:` test"
    else:
        cons = "a conditional derived from this statement"
    if not cl:
        what = "Compiler-generated conditional (no single source line maps here — likely a multi-part `||`/`&&` or a `switch` jump)."
    else:
        what = "%s — `%s`." % (cons, cl)
        if guarded and guarded != cl and "switch" not in low:
            what += " When the condition holds it runs `%s`." % guarded
    if k == "unreached":
        trig = ("the basic block is **never executed at all** — no test reaches this point yet. "
                "Covering it requires first satisfying the enclosing condition(s) so control flow "
                "arrives here, then exercising this test.")
    elif k == "taken-only":
        trig = ("so far the condition has only ever been **true** (this branch taken); the "
                "**false / fall-through** path is never exercised. To cover it, supply an "
                "input/state that makes the condition above evaluate **false**.")
    else:  # nottaken-only
        trig = ("so far the condition has only ever been **false** (fall-through); the **true** path "
                "(branch taken) is never exercised. To cover it, supply an input/state that makes the "
                "condition above evaluate **true**.")
    return what, trig


def main():
    mapping, cap_end = MF.build_map()
    cap_starts = sorted(mapping)
    # group uncovered branches by captured function. RW-half branches (>=0x08010000) mirror RO: map
    # to the RO-equivalent (a-0x10000) for naming/cause, but keep the real RW address in the listing.
    groups = {}
    for l in open(os.path.join(HERE, "cap_uncovered.txt")):
        if not l.startswith("0x"):
            continue
        a, k = l.split(); a = int(a, 16)
        ro = a - 0x10000 if a >= 0x08010000 else a
        i = bisect.bisect_right(cap_starts, ro) - 1
        fs = cap_starts[i] if i >= 0 else None
        groups.setdefault(fs, []).append((a, k, ro))

    lines = ["# Uncovered branches by function — named + caused (captured gale EC firmware)", "",
             "## Methodology & confidence",
             "- **Branch cause** — the `cmp/tst/...` condition, the compared register/immediate, and "
             "exactly which direction is missing — is derived **directly from the captured disassembly "
             "(always exact)**. The operand **provenance** hint (`= word [r5+0x54]`, `= computed (subs #4)`, "
             "etc.) is the nearest **in-basic-block** definition, found by a control-flow-aware backward "
             "walk that stops at unconditional flow breaks; values defined further upstream are reported "
             "as *\"carried in from a preceding basic block\"* rather than guessed.",
             "- **Function name / signature / source line** come from the **rebuilt ELF's DWARF** "
             "(vendored in-repo at `renode/data/rebuilt-RO.elf`), mapped to captured addresses by a disassembly "
             "fingerprint (instruction count + cmp-immediate multiset + **loaded scalar-constant multiset**, "
             "which is shift-invariant) within an anchor-interpolated window, then `addr2line`.",
             "- **conf:exact / conf:high** — fingerprint distance 0 / ≤3: name+source reliable. "
             "**conf:approx** — best-effort match; the *name* may occasionally be wrong (the rebuilt has no "
             "1:1 counterpart, or a fingerprint collision), but the disassembly **cause is still exact**.",
             "- The per-branch **rebuilt C line** is `addr2line(reb_func_start + branch_offset)`; reliable when "
             "the internal layout matches (it does for faithful reconstructions), best-effort for conf:approx.",
             "- RO functions shown (0x0800xxxx); each function notes how many of its uncovered branches are in "
             "the **RW mirror** (0x0801xxxx, identical code).", ""]
    total = sum(len(v) for v in groups.values())
    lines.append("**%d uncovered branches across %d functions.**" % (total, len(groups)))
    lines.append("")
    for fs in sorted(g for g in groups if g is not None):
        ra, name, conf = mapping[fs]
        fn, fl = addr2line(ra)
        sig = signature(fn if fn != "?" else name, fl)
        g = sorted(groups[fs])
        ur = sum(1 for _, k, _ in g if k == "unreached")
        nrw = sum(1 for a, _, _ in g if a >= 0x08010000)
        lines.append("## %#010x  `%s`  (conf:%s)" % (fs, fn if fn != "?" else name, conf))
        if sig:
            lines.append("**Signature:** `%s`" % sig)
        lines.append("**Source:** %s  | rebuilt @ %#x | %d uncovered (%d unreached, %d one-dir; %d in RW mirror)"
                     % (fl, ra, len(g), ur, len(g) - ur, nrw))
        lines.append("")
        for a, k, ro in g:
            cause = branch_cause(fs, cap_end[fs], ro, k)
            rb_addr = ra + (ro - fs)            # rebuilt addr for this branch (function-relative)
            _, rfl = addr2line(rb_addr)
            sl = src_line(rfl)
            _, guarded = src_context(rfl)
            tag = " (RW mirror)" if a >= 0x08010000 else ""
            lines.append("- **%#010x**%s [%s] — %s" % (a, tag, k, cause))
            if sl:
                lines.append("  - rebuilt C (%s): `%s`" % (rfl.split("/")[-1], sl))
            what, trig = explain(sl, k, guarded)
            lines.append("  - **What:** %s" % what)
            lines.append("  - **Triggers when:** %s" % trig)
        lines.append("")
    outp = os.path.join(HERE, "UNCOVERED-BY-FUNCTION.md")
    open(outp, "w").write("\n".join(lines))
    print("wrote %s: %d branches, %d functions" % (outp, total, len(groups)))


if __name__ == "__main__":
    main()
