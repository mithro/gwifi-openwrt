#!/usr/bin/env python3
"""Map each uncovered REBUILT branch to its exact source line via the ELF's debug-line info.

The rebuilt ELF is built with -g, so addr2line resolves every branch address to function +
file:line. That lets us justify uncovered branches at the SOURCE level instead of guessing from
symbol names: read the actual line (a `case PD_STATE_SRC_*` body gale never enters as a sink-only
AP, an `ASSERT`, an `if (port >= COUNT)` defensive guard, ...) and classify precisely.

Reads cov_uncovered_{RO,RW}.txt (addr, symbol, state). For a function name filter (argv), prints
the uncovered branches grouped by source line with the line text, so the residual is auditable.

Usage: uv run --python .venv python classify_src.py [func_substring]
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TC = "/home/tim/local/gwifi/ec-rebuild/gcc-arm-none-eabi-5_4-2016q3/bin"
A2L = os.path.join(TC, "arm-none-eabi-addr2line")
RO_ELF = "/home/tim/local/gwifi/ec-rebuild/ec/build/gale/RO/ec.RO.elf"
RW_ELF = "/home/tim/local/gwifi/ec-rebuild/ec/build/gale/RW/ec.RW.elf"
SRC = "/home/tim/local/gwifi/ec-rebuild/ec"


def load_uncovered(img):
    path = os.path.join(HERE, "cov_uncovered_%s.txt" % img)
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) >= 3:
                out.append((p[0], p[1], p[2]))
    return out


def addr2line_batch(elf, addrs):
    """Resolve many addresses at once; returns list of (func, file, line) parallel to addrs."""
    if not addrs:
        return []
    r = subprocess.run([A2L, "-f", "-e", elf] + addrs, stdout=subprocess.PIPE,
                       universal_newlines=True).stdout.splitlines()
    res = []
    for i in range(0, len(r) - 1, 2):
        func = r[i].strip()
        fl = r[i + 1].strip()
        file, _, line = fl.rpartition(":")
        res.append((func, file, line))
    return res


_src_cache = {}


def src_line(file, line):
    if not file or not line.isdigit():
        return ""
    if file not in _src_cache:
        try:
            with open(file) as f:
                _src_cache[file] = f.read().splitlines()
        except OSError:
            _src_cache[file] = []
    lines = _src_cache[file]
    n = int(line)
    return lines[n - 1].strip() if 1 <= n <= len(lines) else ""


import re

# Source-line classification of an uncovered branch. Distinguishes branches that are GENUINELY
# unreachable on gale-as-built (so excludable with justification) from ones we simply have not
# driven yet (the work-list). Keyed on the actual source text + function name.
# ABSENT_HARDWARE only — peripherals gale physically lacks. PD source/swap states are NOT here
# (they are driveable; see categorize()).
_BOARD_DEAD = re.compile(
    r'charge_manager|\bbattery\b|charger|keyboard|\bkb_|motion|\bals\b|tablet|backlight|'
    r'lid_|power_button', re.I)
_DEFENSIVE = re.compile(
    r'\bASSERT|\bpanic|should not|cannot happen|BUG\(|__builtin_unreachable|'
    r'default:|EC_ERROR_(UNKNOWN|INVAL|UNIMPLEMENTED)|/\* unreachable', re.I)


_CASE = re.compile(r'^\s*case\s+(PD_STATE_\w+)\s*:')
# CORRECTION (2026-06-07): PD source-role / power-swap states are NOT board-dead. gale's board
# policy prefers SINK, but the state machine reaches the SOURCE states fine with `pd dualrole
# source` + a sink partner (GaleAdc.PartnerSink) — VERIFIED: captured sources to SRC_DISCOVERY.
# (The rebuilt currently crashes there = divergence #2, see gale-src-path-divergence.md, but that
# is a bug to FIX, not a reason to excuse the branch.) So PD states are DRIVEABLE, not excluded.
# The only genuinely board-dead code is for hardware gale physically lacks (keyboard/battery/...).


def enclosing_case(file, line):
    """Nearest preceding `case PD_STATE_X:` label for a line inside pd_task's big switch."""
    if file not in _src_cache:
        src_line(file, line)
    lines = _src_cache.get(file, [])
    n = int(line) if line.isdigit() else 0
    for i in range(min(n, len(lines)) - 1, max(0, n - 400), -1):
        m = _CASE.match(lines[i])
        if m:
            return m.group(1)
    return ""


# Role-swap states: gale's force-sink board policy (pd_check_power_swap / pd_check_data_swap
# return false) means it neither initiates nor accepts PR/DR/VCONN swaps — VERIFIED in emulation:
# `pd 0 swap power/data` produce no swap TX. So the SNK_SWAP_*/SRC_SWAP_*/VCONN_SWAP/DR_SWAP states
# are unreachable on THIS board in BOTH firmwares (matching dead code, not a divergence). The
# SOURCE-CONTRACT states (SRC_STARTUP..SRC_READY) are NOT here — gale does source via `pd dualrole
# source` + a sink partner, so those stay driveable.
_SWAP_DEAD = re.compile(r'PD_STATE_(SNK|SRC)_SWAP|PD_STATE_VCONN_SWAP|PD_STATE_DR_SWAP')


def categorize(func, file, line, text):
    # ABSENT_HARDWARE: only code for peripherals gale physically lacks is genuinely unreachable.
    if _BOARD_DEAD.search(text):
        return "ABSENT_HARDWARE"
    # DEFENSIVE asserts/panics: the failing side usually needs fault injection — driveable in
    # principle (bad params, hardware-error injection), so flagged but NOT auto-excused.
    if _DEFENSIVE.search(text):
        return "DEFENSIVE"
    case = enclosing_case(file, line)
    if case and _SWAP_DEAD.search(case):
        return "SWAP_POLICY_DEAD"   # force-sink board refuses role swaps -> unreachable both images
    return "DRIVEABLE"


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else None
    agg = filt == "--agg"
    if agg:
        filt = None
    for img, elf in (("RO", RO_ELF), ("RW", RW_ELF)):
        uncov = load_uncovered(img)
        addrs = [a for a, s, st in uncov]
        resolved = addr2line_batch(elf, addrs)
        rows = []
        for (a, sym, state), (func, file, line) in zip(uncov, resolved):
            if filt and filt not in func and filt not in sym:
                continue
            rows.append((func, file, line, state, a))
        if not rows:
            continue
        # group by (func, full_file, line)
        groups = {}
        for func, file, line, state, a in rows:
            key = (func, file, line)
            groups.setdefault(key, []).append(state)
        if agg:
            cats = {"DRIVEABLE": 0, "ABSENT_HARDWARE": 0, "DEFENSIVE": 0, "SWAP_POLICY_DEAD": 0}
            cat_funcs = {"DRIVEABLE": {}, "ABSENT_HARDWARE": {}, "DEFENSIVE": {}, "SWAP_POLICY_DEAD": {}}
            for (func, file, line), states in groups.items():
                txt = src_line(file, line)
                c = categorize(func, file, line, txt)
                cats[c] += len(states)
                cat_funcs[c][func] = cat_funcs[c].get(func, 0) + len(states)
            tot = sum(cats.values())
            print("\n=== %s: %d uncovered branches by category ===" % (img, tot))
            for c in ("DRIVEABLE", "ABSENT_HARDWARE", "DEFENSIVE", "SWAP_POLICY_DEAD"):
                print("  %-12s %4d   top: %s" % (
                    c, cats[c], ", ".join("%s(%d)" % (f, n) for f, n in
                                          sorted(cat_funcs[c].items(), key=lambda k: -k[1])[:6])))
            continue
        print("\n=== %s: %d uncovered branches%s ===" %
              (img, len(rows), (" in *%s*" % filt) if filt else ""))
        for (func, file, line), states in sorted(
                groups.items(), key=lambda k: (k[0][0], int(k[0][2]) if k[0][2].isdigit() else 0)):
            txt = src_line(file, line)
            nun = sum(1 for s in states if s == "unreached")
            print("  %-24s %s:%-5s [%dx %s] %s" %
                  (func[:24], os.path.basename(file), line, len(states),
                   "unreached" if nun == len(states) else "1dir", txt[:78]))


if __name__ == "__main__":
    main()
