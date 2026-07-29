#!/usr/bin/env python3
"""Per-console-command coverage report (CAPTURED firmware).

1. Locate the __cmds console-command table inside the captured binary by structural scan
   (struct console_command {name, handler, argdesc, shorthelp}, 16B stride).
2. Map each handler (a captured function start) to its rebuilt-ELF name + captured extent via
   map_funcs.build_map() (the same captured<->rebuilt mapping the UNCOVERED-BY-FUNCTION report uses).
3. Classify every conditional branch in each handler's extent using the EXACT combined coverage
   snapshot (tmp/_combined.pkl) that combine_coverage.py wrote (so totals match the 2222/3272 head).

NOTE: extent = [handler_start, next_captured_func_start) — i.e. the handler's own body. Helper
functions it calls (e.g. shared parsers) are separate captured functions and are reported under
their own name elsewhere, not folded into the command here.

Run combine_coverage.py first. Usage: uv run --python .venv python cmdtable.py
"""
import os
import pickle
import string
import struct

import map_funcs

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = 0x08000000
PRINT = set(string.printable[:-6].encode())

with open(CAPTURED, "rb") as f:
    BIN = f.read()
END = BASE + len(BIN)


def rd32(off):
    return struct.unpack_from("<I", BIN, off)[0]


def is_ptr(v):
    return BASE <= v < END


def ascii_at(addr, maxlen=24):
    o = addr - BASE
    if not (0 <= o < len(BIN)):
        return None
    s = bytearray()
    while o < len(BIN) and BIN[o] != 0 and len(s) < maxlen:
        if BIN[o] not in PRINT:
            return None
        s.append(BIN[o])
        o += 1
    if o >= len(BIN) or BIN[o] != 0 or len(s) == 0:
        return None
    return s.decode("latin1")


def find_cmds():
    """Return (base, count) of the longest valid 16B-stride __cmds run."""
    def valid(o):
        np = rd32(o); h = rd32(o + 4); ad = rd32(o + 8); sh = rd32(o + 12)
        nm = ascii_at(np) if is_ptr(np) else None
        ok_name = nm and all(33 <= ord(c) < 127 for c in nm)
        return (ok_name and (h & 1) and BASE <= (h & ~1) < END
                and (ad == 0 or is_ptr(ad)) and (sh == 0 or is_ptr(sh)))
    best = None
    o = 0
    while o + 16 <= len(BIN):
        if valid(o):
            n = 0
            while o + (n + 1) * 16 <= len(BIN) and valid(o + n * 16):
                n += 1
            if best is None or n > best[1]:
                best = (BASE + o, n)
            o += 16 * max(n, 1)
        else:
            o += 4
    return best


def main():
    with open(os.path.join(HERE, "tmp", "_combined.pkl"), "rb") as f:
        cond, executed, edges = pickle.load(f)
    mapping, cap_end = map_funcs.build_map()
    # Robust function-start list: captured func starts (from mapping) PLUS every cmd handler,
    # so a handler that rda never seeded (only referenced from __cmds) still gets a bounded extent.
    starts_known = set(cap_end.keys())

    def classify(a):
        tk = (a, cond[a][1]) in edges
        nt = (a, cond[a][0]) in edges
        if tk and nt:
            return "both"
        if a not in executed:
            return "unreached"
        return "taken-only" if tk else ("nottaken-only" if nt else "reached-neither")

    cond_addrs = sorted(cond.keys())

    base, count = find_cmds()
    print("=== __cmds @ 0x%08x, %d commands (captured binary) ===\n" % (base, count))

    cmds = []
    for i in range(count):
        ent = (base - BASE) + i * 16     # file offset of this table entry
        cmds.append((ascii_at(rd32(ent)), rd32(ent + 4) & ~1))

    # global sorted boundaries = known captured func starts + all handlers
    all_starts = sorted(starts_known | {h for _, h in cmds})

    def extent(h):
        end = cap_end.get(h)
        if end is not None:
            return end
        idx = all_starts.index(h)
        return all_starts[idx + 1] if idx + 1 < len(all_starts) else 0x08010000

    print("  %-12s %-26s %4s %4s %4s %4s %5s" % ("command", "handler (rebuilt name)", "br", "both", "1dir", "unr", "%"))
    print("  " + "-" * 72)
    tot_br = tot_both = 0
    incomplete = []
    for name, handler in sorted(cmds, key=lambda x: x[0].lower()):
        reb = mapping.get(handler)
        end = extent(handler)
        rebname = reb[1] if reb else ("command_%s?" % name)
        conf = reb[2] if reb else "unseed"
        br = [a for a in cond_addrs if handler <= a < end]
        states = [classify(a) for a in br]
        both = states.count("both")
        onedir = states.count("taken-only") + states.count("nottaken-only")
        unr = states.count("unreached") + states.count("reached-neither")
        nbr = len(br)
        pct = (100.0 * both / nbr) if nbr else 100.0
        tot_br += nbr; tot_both += both
        flag = "" if (nbr == 0 or both == nbr) else "  <<"
        print("  %-12s %-20s:%-5s %4d %4d %4d %4d %4.0f%s"
              % (name, rebname[:20], conf[:5], nbr, both, onedir, unr, pct, flag))
        if nbr and both != nbr:
            incomplete.append((name, rebname, handler, end, list(zip(br, states))))
    print("  " + "-" * 72)
    print("  %-12s %-26s %4d %4d   (%.1f%% both-dirs across handler bodies)\n"
          % ("TOTAL", "", tot_br, tot_both, 100.0 * tot_both / tot_br if tot_br else 0))

    print("=== Incomplete handlers — uncovered branch detail ===")
    for name, rebname, hs, he, bs in incomplete:
        miss = [(a, s) for a, s in bs if s != "both"]
        print("\n  %-10s %-22s [0x%08x..0x%08x]  %d/%d missing"
              % (name, rebname, hs, he, len(miss), len(bs)))
        for a, s in miss:
            print("    0x%08x  %s" % (a, s))


if __name__ == "__main__":
    main()
