#!/usr/bin/env python3
"""Recursive-descent disassembler for the gale EC raw flash images (ARMv6-M / Cortex-M0 Thumb).

WHY THIS EXISTS
---------------
The captured device firmware is a raw flash dump with no ELF, so there is no .text/.rodata
boundary to tell code from data. A FLAT linear disassembly (objdump -b binary) decodes the
literal pools and rodata tables as if they were instructions, inventing thousands of phantom
"conditional branches" that never execute. That makes an honest 100%-branch-coverage denominator
impossible: you can never cover branches that aren't real.

Recursive descent solves this: it follows only control flow that is actually reachable, so every
instruction it emits is provably code. STM32F072 is Cortex-M0 = ARMv6-M, which has NO IT blocks,
NO CBZ/CBNZ, and NO 32-bit conditional branches — every conditional branch is the 16-bit
B<cond> (T1) encoding. That keeps the flow analysis exact:
  * fall-through:           any non-flow instruction -> next address
  * B<cond> label (T1):     two successors (target, fall-through)  <-- THE branches we count
  * B label (T2, uncond):   one successor (target), no fall-through
  * BL imm:                 call; record target as a new function root, continue at fall-through
  * BX / BLX reg, POP{..pc},
    MOV pc,..  / udf / b .:  flow terminator (function/block end)

ROOTS (where descent starts)
----------------------------
  1. The Cortex-M0 vector table at the image base (SP at +0, then reset/NMI/HardFault/.../IRQ
     handlers). Every odd (Thumb-bit) in-range word is a handler entry.
  2. Extra seeds passed in by the caller — in practice the UNION of all PCs seen in the Renode
     execution traces. Trace PCs are definitely-code, so seeding with them lets descent discover
     the not-yet-executed branches that hang off executed basic blocks (the coverage gaps).

This is deliberately conservative: it follows ONLY direct flow, never speculatively treats a
rodata word as code. Whole functions that are reached only through a function-pointer table
(DECLARE_HOST_COMMAND / DECLARE_CONSOLE_COMMAND / DECLARE_HOOK / the task table) and never
executed will NOT be discovered here — that is what ptr_targets() is for (a separate completeness
pass that flags pointer-table targets the suite never entered, i.e. dead-code candidates).
"""
import capstone

# Two images packed into one 128 KiB dump: RO at 0x08000000, RW at 0x08010000.
RO_BASE = 0x08000000
RW_BASE = 0x08010000
# .text end measured FROM THE CAPTURED IMAGE, not the rebuilt ELF. The captured code is larger than
# the (not-yet-size-identical) rebuilt .text: the last function command_typec ends at 0x0800ba18
# (a `pop {r4-r7,pc}` + nop), after which lie its literal pool and a small u16 table up to the
# __cmds console-command table at 0x0800ba54. The old bound 0x0800b744 (= rebuilt .text size) wrongly
# excluded 13 real functions — tcpm_get_cc/tcpm_get_message/tcpc_alert, mutex_unlock, usb_mux_set/get,
# __gnu_thumb1_case_uhi and command_typec — from disassembly AND from the branch denominator, because
# _in_text() gates the recursive descent (a `bl mutex_unlock` past the bound was refused). Empirically
# verified: extending to 0x0800ba18 adds exactly 56 reachable conditional branches (28 per image) and
# removes none; extending further to 0x0800ba54 adds nothing (the gap is literal-pool/table data).
TEXT_RANGES = [(0x08000000, 0x0800ba18), (0x08010000, 0x0801ba18)]


def _in_text(a):
    return any(lo <= a < hi for lo, hi in TEXT_RANGES)


def _md():
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB + capstone.CS_MODE_MCLASS)
    md.detail = True
    return md


# ARMv6-M conditional-branch mnemonics (16-bit B<cond>, T1). No cbz/cbnz on Cortex-M0.
_CONDS = {"beq", "bne", "bcs", "bhs", "bcc", "blo", "bmi", "bpl", "bvs", "bvc",
          "bhi", "bls", "bge", "blt", "bgt", "ble"}
# Flow terminators: end a straight-line run (no fall-through successor).
_TERMS = {"bx", "pop", "udf", "b"}  # 'b'/'pop' handled specially below


def _word(img, base, addr):
    o = addr - base
    if o < 0 or o + 4 > len(img):
        return None
    return img[o] | (img[o + 1] << 8) | (img[o + 2] << 16) | (img[o + 3] << 24)


# libgcc Thumb-1 switch-dispatch helpers (toolchain-identical, so the captured dump contains the
# byte-for-byte same bodies as the rebuilt ELF). After `bl <helper>` an inline jump table follows:
#   target_i = table_base + 2 * table[i]      (table_base = bl_addr + 4)
# uqi = unsigned-byte entries, uhi = unsigned-halfword entries. Locating these and parsing their
# tables is what lets recursive descent follow C switch() statements (the dominant blind spot).
_UQI_SIG = bytes.fromhex("8c46714649084900095c49008e4461467047")  # __gnu_thumb1_case_uqi body
_UHI_SIG = bytes.fromhex("03b47146490840004900095a49008e4403bc7047")  # __gnu_thumb1_case_uhi body


def _find_case_helpers(data):
    """Locate __gnu_thumb1_case_uqi/_uhi in the dump by byte signature.
    Returns {addr: entry_size_bytes}."""
    helpers = {}
    for sig, esz in ((_UQI_SIG, 1), (_UHI_SIG, 2)):
        start = 0
        while True:
            j = data.find(sig, start)
            if j < 0:
                break
            helpers[RO_BASE + j] = esz
            start = j + 2
    return helpers


def _parse_case_table(data, bl_addr, entry_size):
    """Parse the inline jump table that follows a `bl __gnu_thumb1_case_*`. The table starts at
    bl_addr+4; each entry is an (un)signed offset; target = table_base + 2*entry. The table length
    is not encoded, so we use the standard bound: the table ends at the smallest in-range target
    (the first case body sits immediately after the table). Returns (sorted target list, table_end)."""
    table_base = bl_addr + 4
    targets = []
    table_end = None
    pos = table_base
    for _ in range(1024):                      # safety bound; real tables are tiny
        if table_end is not None and pos >= table_end:
            break
        off = pos - RO_BASE
        if off < 0 or off + entry_size > len(data):
            break
        val = data[off] if entry_size == 1 else (data[off] | (data[off + 1] << 8))
        tgt = table_base + 2 * val
        if tgt > table_base and _in_text(tgt):
            if table_end is None or tgt < table_end:
                table_end = tgt
        targets.append(tgt)
        pos += entry_size
    if table_end is None:
        return [], table_base
    good = sorted(set(t for t in targets if t >= table_end and _in_text(t)))
    return good, table_end


def analyze(binpath, extra_seeds=None):
    """Recursive-descent disassemble the dump. Returns:
        insns  : set of instruction start addresses (provably-code bytes)
        cond   : {branch_addr: (fall_through_addr, target_addr)} for every reachable B<cond>
        calls  : set of BL/function-pointer targets discovered as roots
    """
    data = open(binpath, "rb").read()
    md = _md()
    case_helpers = _find_case_helpers(data)   # {helper_addr: entry_size}

    cond = {}
    insns = set()
    calls = set()
    seen_blocks = set()      # block start addresses already walked
    work = []

    def add_root(a):
        a &= ~1                       # drop Thumb bit
        if _in_text(a) and a not in seen_blocks:
            work.append(a)

    # Root set 1: vector tables (skip word0 = initial SP).
    for base in (RO_BASE, RW_BASE):
        for off in range(4, 0xC0, 4):           # 48 vectors covers Cortex-M0 sys + STM32F0 IRQs
            v = _word(data, RO_BASE, base + off)  # whole dump is mapped from RO_BASE
            if v and (v & 1) and _in_text(v & ~1):
                add_root(v)
        calls.add(base)  # mark base so callers know the image is present

    # Root set 2: caller-supplied seeds (execution-trace PCs).
    for s in (extra_seeds or ()):
        add_root(s)

    while work:
        pc = work.pop()
        if pc in seen_blocks:
            continue
        # Walk straight-line from pc until a terminator or an already-seen instruction.
        cur = pc
        prev_was_bl = False     # last decoded insn was a `bl` (a literal pool may follow it)
        while True:
            if cur in seen_blocks:
                break
            base = RO_BASE
            off = cur - base
            if off < 0 or off + 4 > len(data):
                break
            # Decode one instruction (give capstone up to 4 bytes).
            chunk = data[off:off + 4]
            ins = next(md.disasm(chunk, cur, count=1), None)
            if ins is None:
                break                       # undecodable -> treat as data, stop this run
            insns.add(cur)
            seen_blocks.add(cur)
            mn = ins.mnemonic.split(".")[0]
            size = ins.size
            nxt = cur + size

            if mn in _CONDS:
                # Literal-pool guard: a `bl` to a no-return path (panic/reset) is followed by a
                # literal pool, whose pointer words can decode as a phantom conditional branch.
                # Only when we land here straight after a `bl`, at a 4-byte-aligned word that is a
                # flash/RAM pointer (0x08../0x20..), is it data — stop the run. (Validated against
                # the ELF: removes both false positives, adds zero false negatives.)
                if prev_was_bl and cur % 4 == 0:
                    w = _word(data, RO_BASE, cur)
                    if w is not None and (w >> 24) in (0x08, 0x20):
                        seen_blocks.discard(cur)
                        insns.discard(cur)
                        break
                tgt = _branch_target(ins)
                if tgt is not None:
                    cond[cur] = (nxt, tgt)
                    add_root(tgt)
                # conditional: fall through continues this run
                prev_was_bl = False
                cur = nxt
                continue
            if mn == "b":                   # unconditional T2 branch: terminator, follow target
                tgt = _branch_target(ins)
                if tgt is not None:
                    add_root(tgt)
                break
            if mn in ("bl",):               # call: record root, continue after it
                tgt = _branch_target(ins)
                if tgt is not None:
                    t = tgt & ~1
                    if t in case_helpers:    # switch dispatch: parse inline table, it follows here
                        bodies, _tend = _parse_case_table(data, cur, case_helpers[t])
                        for b in bodies:
                            add_root(b)
                        break                # bl-to-case-helper never falls through to the table
                    calls.add(t)
                    add_root(tgt)
                prev_was_bl = True
                cur = nxt
                continue
            if mn in ("bx",):               # return / indirect: terminator
                break
            if mn == "blx":                 # indirect call: continue after it
                prev_was_bl = False
                cur = nxt
                continue
            if mn == "pop":                 # pop {..., pc} returns; pop without pc falls through
                if "pc" in ins.op_str:
                    break
                prev_was_bl = False
                cur = nxt
                continue
            if mn == "udf":                 # permanently undefined -> block end
                break
            # mov pc, rX / ldr pc, ... -> indirect jump terminator
            if ins.op_str.startswith("pc,") and mn in ("mov", "ldr", "add"):
                break
            prev_was_bl = False
            cur = nxt

    return insns, cond, calls


def _branch_target(ins):
    """Return the absolute branch/call target for a PC-relative Thumb branch, else None."""
    for op in ins.operands:
        if op.type == capstone.arm.ARM_OP_IMM:
            return op.imm & 0xFFFFFFFF
    return None


def ptr_targets(binpath):
    """Completeness pass: every word-aligned value in the dump that is an odd (Thumb) pointer
    into a .text range — the function-pointer tables (DECLARE_HOST_COMMAND / CONSOLE / HOOK /
    task list) plus literal-pool function pointers. Targets here that the recursive descent
    (seeded by the trace) never reached are dead-code candidates to drive or justify."""
    data = open(binpath, "rb").read()
    out = set()
    for off in range(0, len(data) - 3, 2):       # 2-byte aligned is enough for table scan
        v = data[off] | (data[off + 1] << 8) | (data[off + 2] << 16) | (data[off + 3] << 24)
        if (v & 1) and _in_text(v & ~1):
            out.add(v & ~1)
    return out


if __name__ == "__main__":
    import sys
    b = sys.argv[1] if len(sys.argv) > 1 else \
        "../../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"
    insns, cond, calls = analyze(b)
    print("recursive descent from vector table only (no trace seeds):")
    print("  code instructions: %d" % len(insns))
    print("  conditional branches: %d" % len(cond))
    print("  call/root targets: %d" % len(calls))
    print("  pointer-table targets: %d" % len(ptr_targets(b)))
