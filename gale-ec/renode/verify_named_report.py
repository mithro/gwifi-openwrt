#!/usr/bin/env python3
"""INDEPENDENT verifier for UNCOVERED-BY-FUNCTION.md — re-derives every claim from primary sources
and diffs it against the file. NOTHING here calls build_named_report; the only shared input is
rda.cond (the canonical denominator) and the lever pkls (the raw coverage).

Checks:
  A. cap_uncovered.txt is a faithful, complete partition of rda.cond given the SAME pkl union
     combine_coverage.py uses (the pkl list is parsed out of combine_coverage.py so inputs are
     provably identical). My own fresh set-algebra recomputes taken/nottaken/both/uncovered+state.
  B. The report renders cap_uncovered.txt exactly: same branch set (no missing/extra/dup), same
     per-branch state, correct total, correct per-function counts (uncovered/unreached/one-dir/RW),
     and correct function grouping (each branch's RO-equiv lands in [func_start, func_end)).
  C. The disassembly cause is accurate: for every branch the report names a conditional mnemonic,
     an INDEPENDENT capstone decode at the RO-equivalent address yields the same mnemonic, the addr
     is a real conditional branch, and its (target, fall-through) match rda.cond.
  D. RW-mirror claims: every RW branch (>=0x08010000) has its RO counterpart in rda.cond AND the
     captured bytes at the two addresses are identical (the "identical code" claim).
"""
import os
import re
import pickle
import bisect

import capstone
import rda
import map_funcs as MF

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = 0x08000000
DATA = open(CAP, "rb").read()
MD = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
MD.detail = True
CONDS ={"beq", "bne", "bcs", "bhs", "bcc", "blo", "bmi", "bpl", "bvs", "bvc",
         "bhi", "bls", "bge", "blt", "bgt", "ble"}

fails = []
notes = []


def check(cond_ok, msg):
    print(("  PASS " if cond_ok else "  FAIL ") + msg)
    if not cond_ok:
        fails.append(msg)


def decode_at(addr):
    off = addr - BASE
    if off < 0 or off + 2 > len(DATA):
        return None
    return next(MD.disasm(DATA[off:off + 4], addr, count=1), None)


# ----- reproduce combine_coverage's EXACT union (parse its load() list) -----
print("== union (parsed from combine_coverage.py) ==")
csrc = open(os.path.join(HERE, "combine_coverage.py")).read()
pkl_names = re.findall(r'load\("([^"]+)"\)', csrc)
executed, edges = set(), set()
missing = []
for n in pkl_names:
    p = os.path.join(HERE, "tmp", n)
    if not os.path.exists(p):
        missing.append(n)
        continue
    with open(p, "rb") as f:
        e, d = pickle.load(f)
    executed |= set(e)
    edges |= set(d)
print("  pkls referenced: %d   loaded: %d   missing-on-disk: %d"
      % (len(pkl_names), len(pkl_names) - len(missing), len(missing)))
if missing:
    notes.append("combine references %d pkls not on disk: %s" % (len(missing), missing))
# any *_edges.pkl on disk NOT referenced by combine (would be an un-unioned lever)?
on_disk = {f for f in os.listdir(os.path.join(HERE, "tmp")) if f.endswith("_edges.pkl")}
unref = sorted(on_disk - set(pkl_names))
if unref:
    notes.append("%d *_edges.pkl on disk NOT unioned by combine: %s" % (len(unref), unref))

# ----- canonical denominator + my own fresh state algebra -----
seeds = executed | rda.ptr_targets(CAP)
_insns, cond, _calls = rda.analyze(CAP, extra_seeds=seeds)
taken = {a for a in cond if (a, cond[a][1]) in edges}
nottaken = {a for a in cond if (a, cond[a][0]) in edges}
both = {a for a in cond if a in taken and a in nottaken}
uncov_truth = {}
for a in cond:
    if a in both:
        continue
    if a not in executed:
        uncov_truth[a] = "unreached"
    elif a in taken:
        uncov_truth[a] = "taken-only"
    elif a in nottaken:
        uncov_truth[a] = "nottaken-only"
    else:
        uncov_truth[a] = "reached-neither"

print("\n== A. cap_uncovered.txt vs independent re-derivation ==")
# 3328 after correcting TEXT_RANGES end 0x0800b744 -> 0x0800ba18 (the captured .text truly ends at
# command_typec's `pop` at 0x0800ba18; the old bound = rebuilt-ELF .text size wrongly cut 13 funcs).
check(len(cond) == 3328, "denominator |rda.cond| == 3328 (got %d)" % len(cond))
check(both.isdisjoint(set(uncov_truth)), "both-dirs and uncovered are disjoint")
check(set(both) | set(uncov_truth) == set(cond),
      "both-dirs + uncovered exactly partition cond")
check(len(both) + len(uncov_truth) == len(cond),
      "|both| + |uncov| == |cond|  (%d + %d == %d)" % (len(both), len(uncov_truth), len(cond)))

capfile = {}
for l in open(os.path.join(HERE, "cap_uncovered.txt")):
    if not l.startswith("0x"):
        continue
    a, st = l.split()
    capfile[int(a, 16)] = st
check(set(capfile) == set(uncov_truth),
      "cap_uncovered.txt branch set == re-derived uncovered set (file=%d truth=%d)"
      % (len(capfile), len(uncov_truth)))
missing_in_file = set(uncov_truth) - set(capfile)
extra_in_file = set(capfile) - set(uncov_truth)
if missing_in_file:
    fails.append("uncovered branches absent from file: %s" % [hex(x) for x in list(missing_in_file)[:8]])
if extra_in_file:
    fails.append("file lists branches that are actually covered: %s" % [hex(x) for x in list(extra_in_file)[:8]])
state_mismatch = [(hex(a), capfile[a], uncov_truth[a]) for a in set(capfile) & set(uncov_truth)
                  if capfile[a] != uncov_truth[a]]
check(not state_mismatch, "every per-branch state in file matches re-derivation (%d mismatches)"
      % len(state_mismatch))
for m in state_mismatch[:8]:
    print("      state mismatch %s: file=%s truth=%s" % m)

# ----- parse the report -----
print("\n== B. report renders cap_uncovered.txt exactly ==")
rpt = open(os.path.join(HERE, "UNCOVERED-BY-FUNCTION.md")).read().splitlines()
mtot = re.search(r"\*\*(\d+) uncovered branches across (\d+) functions\.\*\*", "\n".join(rpt))
rpt_total = int(mtot.group(1)) if mtot else -1
rpt_nfunc = int(mtot.group(2)) if mtot else -1

hdr_re = re.compile(r"^## (0x[0-9a-fA-F]+)\s+`(.+?)`\s+\(conf:(\w+)\)\s*$")
cnt_re = re.compile(r"\| rebuilt @ (0x[0-9a-fA-F]+) \| (\d+) uncovered \((\d+) unreached, (\d+) one-dir; (\d+) in RW mirror\)")
bul_re = re.compile(r"^- \*\*(0x[0-9a-fA-F]+)\*\*(\s+\(RW mirror\))?\s+\[([a-z?-]+)\]\s+—\s+(.*)$")

functions = []          # list of dict(fs,name,conf,rebuilt,decl_uncov,decl_unreach,decl_onedir,decl_rw,branches[])
cur = None
last_hdr_fs = None
for i, line in enumerate(rpt):
    mh = hdr_re.match(line)
    if mh:
        if cur:
            functions.append(cur)
        cur = dict(fs=int(mh.group(1), 16), name=mh.group(2), conf=mh.group(3),
                   rebuilt=None, decl=None, branches=[])
        continue
    mc = cnt_re.search(line)
    if mc and cur is not None:
        cur["rebuilt"] = int(mc.group(1), 16)
        cur["decl"] = (int(mc.group(2)), int(mc.group(3)), int(mc.group(4)), int(mc.group(5)))
        continue
    mb = bul_re.match(line)
    if mb and cur is not None:
        cur["branches"].append(dict(addr=int(mb.group(1), 16), rw=bool(mb.group(2)),
                                    state=mb.group(3), cause=mb.group(4)))
if cur:
    functions.append(cur)

rpt_branches = {}
dups = []
for f in functions:
    for b in f["branches"]:
        if b["addr"] in rpt_branches:
            dups.append(hex(b["addr"]))
        rpt_branches[b["addr"]] = (f, b)
n_bul = sum(len(f["branches"]) for f in functions)

check(rpt_total == len(capfile), "header total (%d) == cap_uncovered count (%d)" % (rpt_total, len(capfile)))
check(rpt_nfunc == len(functions), "header function-count (%d) == parsed headers (%d)" % (rpt_nfunc, len(functions)))
check(n_bul == len(capfile), "rendered bullets (%d) == cap_uncovered count (%d)" % (n_bul, len(capfile)))
check(not dups, "no duplicate branch entries in report (%d dups)" % len(dups))
check(set(rpt_branches) == set(capfile),
      "report branch set == cap_uncovered set (report=%d file=%d)" % (len(rpt_branches), len(capfile)))
b_state_mismatch = [(hex(a), rpt_branches[a][1]["state"], capfile[a])
                    for a in set(rpt_branches) & set(capfile)
                    if rpt_branches[a][1]["state"] != capfile[a]]
check(not b_state_mismatch, "every report state matches cap_uncovered (%d mismatches)" % len(b_state_mismatch))
for m in b_state_mismatch[:8]:
    print("      report-state mismatch %s: report=%s file=%s" % m)

# per-function declared counts vs actual bullets
cnt_bad = []
for f in functions:
    if f["decl"] is None:
        cnt_bad.append((hex(f["fs"]), "no count line"))
        continue
    du, dur, dod, drw = f["decl"]
    au = len(f["branches"])
    aur = sum(1 for b in f["branches"] if b["state"] == "unreached")
    aod = sum(1 for b in f["branches"] if b["state"] in ("taken-only", "nottaken-only"))
    arw = sum(1 for b in f["branches"] if b["addr"] >= 0x08010000)
    if (du, dur, dod, drw) != (au, aur, aod, arw):
        cnt_bad.append((hex(f["fs"]), "decl=%s actual=%s" % ((du, dur, dod, drw), (au, aur, aod, arw))))
check(not cnt_bad, "per-function declared counts match actual bullets (%d bad)" % len(cnt_bad))
for m in cnt_bad[:8]:
    print("      count mismatch %s: %s" % m)

# grouping: each branch's RO-equiv must fall in its function's [fs, cap_end)
mapping, cap_end = MF.build_map()
cap_starts = sorted(mapping)
group_bad = []
for f in functions:
    for b in f["branches"]:
        ro = b["addr"] - 0x10000 if b["addr"] >= 0x08010000 else b["addr"]
        # which function SHOULD this belong to (same bisect as build_named_report)?
        idx = bisect.bisect_right(cap_starts, ro) - 1
        want_fs = cap_starts[idx] if idx >= 0 else None
        if want_fs != f["fs"]:
            group_bad.append((hex(b["addr"]), "under 0x%x but maps to %s" %
                              (f["fs"], hex(want_fs) if want_fs else None)))
        elif f["fs"] in cap_end and not (f["fs"] <= ro < cap_end[f["fs"]]):
            group_bad.append((hex(b["addr"]), "ro 0x%x outside [0x%x,0x%x)" % (ro, f["fs"], cap_end[f["fs"]])))
check(not group_bad, "every branch grouped under the correct function (%d bad)" % len(group_bad))
for m in group_bad[:8]:
    print("      grouping %s: %s" % m)

# ----- C. disassembly cause accuracy (independent capstone decode) -----
print("\n== C. disassembly cause vs independent capstone decode ==")
mn_mismatch = []
not_branch = []
edge_mismatch = []
nolinear = []
for a, (f, b) in rpt_branches.items():
    ro = a - 0x10000 if a >= 0x08010000 else a
    m = re.search(r"\b(beq|bne|bcs|bhs|bcc|blo|bmi|bpl|bvs|bvc|bhi|bls|bge|blt|bgt|ble)\b", b["cause"])
    claimed = m.group(1) if m else None
    ins = decode_at(ro)
    if ins is None:
        not_branch.append((hex(a), "undecodable@ro"))
        continue
    actual = ins.mnemonic.split(".")[0]
    if claimed is None:
        nolinear.append(hex(a))            # report fell back (no mnemonic in prose)
    elif actual != claimed:
        mn_mismatch.append((hex(a), "report=%s decode=%s" % (claimed, actual)))
    # the addr must be a real conditional branch in rda.cond with matching successors
    if ro not in cond:
        not_branch.append((hex(a), "ro not in rda.cond"))
    elif actual not in CONDS:
        not_branch.append((hex(a), "decode '%s' not a conditional branch" % actual))
    else:
        tgt = None
        for op in ins.operands:
            if op.type == capstone.arm.ARM_OP_IMM:
                tgt = op.imm & 0xFFFFFFFF
        ft = ro + ins.size
        if (ft, tgt) != cond[ro]:
            edge_mismatch.append((hex(a), "decode(ft=0x%x,tgt=%s) vs cond%s" %
                                  (ft, hex(tgt) if tgt else None, cond[ro])))
check(not mn_mismatch, "every named branch mnemonic matches independent decode (%d mismatches)" % len(mn_mismatch))
for m in mn_mismatch[:10]:
    print("      mnemonic mismatch %s: %s" % m)
check(not not_branch, "every entry is a genuine conditional branch in rda.cond (%d bad)" % len(not_branch))
for m in not_branch[:10]:
    print("      not-a-branch %s: %s" % m)
check(not edge_mismatch, "decoded (target,fall-through) match rda.cond (%d mismatches)" % len(edge_mismatch))
for m in edge_mismatch[:10]:
    print("      edge mismatch %s: %s" % m)
print("      (%d entries used the 'not in linear decode' fallback — no prose mnemonic; verified as real branches above)" % len(nolinear))

# ----- D. RW-mirror identical-code claim -----
print("\n== D. RW-mirror claims ==")
rw_no_ro = []
rw_bytes_differ = []
n_rw = 0
for a in rpt_branches:
    if a < 0x08010000:
        continue
    n_rw += 1
    ro = a - 0x10000
    if ro not in cond:
        rw_no_ro.append(hex(a))
    ins = decode_at(a)
    sz = ins.size if ins else 2
    if DATA[a - BASE:a - BASE + sz] != DATA[ro - BASE:ro - BASE + sz]:
        rw_bytes_differ.append(hex(a))
check(not rw_no_ro, "every RW branch has its RO counterpart in rda.cond (%d without)" % len(rw_no_ro))
check(not rw_bytes_differ, "RW branch bytes byte-identical to RO counterpart (%d differ)" % len(rw_bytes_differ))
print("      RW-mirror branch entries checked: %d" % n_rw)

# ----- E. operand-provenance: is the attributed writer in the SAME basic block as the cmp? -----
print("\n== E. operand-provenance is control-flow-sound (writer in same basic block) ==")
FLAG_OPS = ("cmp", "cmn", "tst", "subs", "adds", "ands", "orrs", "lsls", "lsrs", "asrs")
WR_OPS = ("ldr", "ldrb", "ldrh", "mov", "movs", "adds", "subs", "ands", "orrs",
          "lsls", "lsrs", "asrs", "uxtb", "sxtb", "bl", "blx")
_fn_cache = {}


def func_disasm(fs, fe):
    if fs in _fn_cache:
        return _fn_cache[fs]
    d = {}
    for ins in MD.disasm(DATA[fs - BASE:fe - BASE], fs):
        d[ins.address] = ins
    _fn_cache[fs] = (d, sorted(d))
    return _fn_cache[fs]


def intervening_uncond(d, addrs, w, fa):
    """True iff an UNCONDITIONAL flow break sits strictly between writer w and cmp fa — which
    severs the straight-line from w to fa, proving w is on no path that reaches fa."""
    for a in addrs:
        if a <= w or a >= fa:
            continue
        mn = d[a].mnemonic.split(".")[0]
        if mn in ("b", "bx", "udf") or (mn == "pop" and "pc" in d[a].op_str):
            return True
    return False


def unbounded_writer(d, addrs, fa, reg):
    """Reproduce build_named_report.operand_source's linear 12-insn back-scan; return writer addr."""
    i = bisect.bisect_left(addrs, fa)
    for a in reversed(addrs[max(0, i - 12):i]):
        op = d[a].op_str
        mn = d[a].mnemonic.split(".")[0]
        if op.startswith(reg + ",") and mn in WR_OPS:
            return a
    return None


CARRIED = "a value carried in from a preceding basic block"
severed = 0          # (branch,reg) where the linear-preceding writer is provably off-path
prov_checked = 0
violations = []      # severed cases the report STILL renders with a concrete (off-path) source
for a, (f, b) in rpt_branches.items():
    ro = a - 0x10000 if a >= 0x08010000 else a
    fs = f["fs"]
    if fs not in cap_end:
        continue
    d, addrs = func_disasm(fs, cap_end[fs])
    if ro not in d:
        continue
    # find flag-setter (nearest preceding FLAG_OP within 6 insns), as branch_cause does
    i = bisect.bisect_left(addrs, ro)
    flag = None
    for aa in reversed(addrs[max(0, i - 6):i]):
        if d[aa].mnemonic.split(".")[0] in FLAG_OPS:
            flag = aa
            break
    if flag is None or d[flag].mnemonic.split(".")[0] != "cmp":
        continue
    parts = d[flag].op_str.split(",")
    regs = [parts[0].strip()]
    if len(parts) > 1 and not parts[1].strip().startswith("#"):
        regs.append(parts[1].strip())
    for ri, reg in enumerate(regs):
        if reg not in ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7"):
            continue
        prov_checked += 1
        w = unbounded_writer(d, addrs, flag, reg)
        if w is not None and intervening_uncond(d, addrs, w, flag):
            severed += 1
            # the report must NOT print a concrete source for this off-path reg; it must say CARRIED.
            phrase_ra = "%s = %s" % (reg, CARRIED)
            phrase_rb = "%s (= %s)" % (reg, CARRIED)
            if phrase_ra not in b["cause"] and phrase_rb not in b["cause"]:
                violations.append((hex(a), "off-path %s still concrete: …%s…"
                                   % (reg, b["cause"][:90])))
check(not violations,
      "every off-path operand is rendered as 'carried in', not a concrete source "
      "(%d violations; %d severed sites detected / %d reg-attributions)"
      % (len(violations), severed, prov_checked))
for m in violations[:12]:
    print("      VIOLATION %s: %s" % m)
if not violations:
    print("      (%d off-path linear-writers detected — all correctly rendered as 'carried in')" % severed)

# ----- F. cmp missing-direction operator is consistent with coverage-state -----
print("\n== F. cmp 'MISSING needs' operator matches the state (not the already-seen side) ==")
OPRE = r"(>=u|<=u|>u|<u|>=|<=|==|!=|>|<)"
NEG = {"==": "!=", "!=": "==", ">=u": "<u", "<u": ">=u", ">u": "<=u", "<=u": ">u",
       ">=": "<", "<": ">=", ">": "<=", "<=": ">"}
bad_dir = []
dir_checked = 0
for a, (f, b) in rpt_branches.items():
    cause = b["cause"]
    m1 = re.search(r"taken when (r\d+) " + OPRE + " ", cause)
    m2 = re.search(r"needs (r\d+) " + OPRE + " ", cause)
    if not (m1 and m2 and m1.group(1) == m2.group(1)):
        continue
    dir_checked += 1
    op1, op2 = m1.group(2), m2.group(2)
    # taken-only: missing is the fall-through (negation of taken-when); else (nottaken-only/unreached):
    # missing is (described as) the taken-when condition itself.
    expect = NEG.get(op1) if b["state"] == "taken-only" else op1
    if op2 != expect:
        bad_dir.append((a, "[%s] taken-when '%s' but MISSING needs '%s' (expected '%s')"
                        % (b["state"], op1, op2, expect)))
check(not bad_dir, "every cmp 'MISSING needs' operator is state-consistent (%d of %d wrong)"
      % (len(bad_dir), dir_checked))
for m in bad_dir[:12]:
    print("      dir %s: %s" % m)

# ----- summary -----
print("\n== SUMMARY ==")
print("  denominator: %d   both-dirs: %d   uncovered: %d   (both+uncov=%d)"
      % (len(cond), len(both), len(uncov_truth), len(both) + len(uncov_truth)))
print("  report: %d branches across %d functions" % (rpt_total, rpt_nfunc))
for n in notes:
    print("  NOTE: " + n)
if fails:
    print("\n  RESULT: %d CHECK(S) FAILED" % len(fails))
    for fmsg in fails:
        print("   - " + fmsg)
else:
    print("\n  RESULT: ALL CHECKS PASSED")


if __name__ == "__main__":
    pass
