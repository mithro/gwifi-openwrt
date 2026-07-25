"""Targeted coverage of pure utility functions (strtoi / parse_bool / strzcpy / uint64divmod and
their neighbours) by calling candidate captured addresses with crafted inputs. The captured is a
different-era build so exact symbol mapping is unreliable; instead we drive a small set of
signature-matched CANDIDATE addresses with both input shapes:
  - string-parse shape: r0=ptr-to-string, r1=scratch(endptr/dest), r2=base   (strtoi/parse_bool/str*)
  - numeric shape:      r0=lo, r1=hi, r2=divisor/arg                          (uint64divmod/math)
Pure functions, so hitting the right address covers it fully; wrong candidates are harmless no-ops.
Accumulates tmp/pure_edges.pkl (unioned by combine_coverage.py). Serial + mem-capped.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

STRP = 0x20002600          # input string
SCR = 0x20002400          # endptr / dest scratch

# signature-matched candidate addresses (RO) for the whole util/string/math cluster + RW mirrors.
CAND = [0x0800b368, 0x08007468, 0x080062b4,       # strtoi / strncasecmp candidates
        0x0800a7b4, 0x0800a88a, 0x080071b4,       # parse_bool / memset candidates
        0x0800b36c, 0x080070fc, 0x08006fb4,       # uint64divmod candidates
        0x0800b4d0, 0x0800b4c0, 0x0800b4b0,       # strlen / strzcpy / memcmp candidates
        0x0800706c, 0x0800a646, 0x0800a666,       # isspace / tolower candidates
        0x08001fec, 0x0800b284, 0x0800a842,       # memcpy candidates
        0x08006528, 0x08004fe4,                   # memset candidates
        0x0800b72a, 0x0800b6f4, 0x0800b610,       # memmove candidates
        0x080059b8]                               # vfnprintf (sanity, already pure)
CAND = sorted(set(CAND + [a + 0x10000 for a in CAND]))

STRINGS = ["0", "123", "-7", "+8", "0x1f", "0xFFFFFFFF", "0XABC", "  42", "", "abc",
           "99999999999", "0b101", "0777", "2147483648", "-2147483648", "on", "off",
           "enable", "disable", "yes", "no", "1", "true", "y", "n", "0x", "  -0x10  "]
NUMS = [(0, 0, 1, 0), (100, 0, 10, 0), (0xFFFFFFFF, 0xFFFFFFFF, 16, 0), (1000, 0, 3, 0),
        (0, 1, 2, 0), (12345, 0, 7, 0), (0, 0, 0, 0), (0xFFFFFFFF, 0, 10, 0), (7, 0, 100, 0)]


def fold(trace, executed, edges):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if len(ln) < 4 or not ln.startswith("0x"):
                prev = None; continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None; continue
            executed.add(pc)
            if prev is not None:
                edges.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "pure_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior pure_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)
    trace = os.path.join(TMP, "pure.txt")
    if os.path.exists(trace):
        os.remove(trace)

    cands = [a for a in CAND if (0x08000000 <= a < 0x0800b744) or (0x08010000 <= a < 0x0801b744)]
    s = [fcall.Session(binp, boot="1.5", trace=trace)]
    n = [0]
    TO = 0.5                                   # pure fns return in microseconds; short timeout
    CRASH_CAP = 4                              # abandon a candidate after N consecutive faults

    def reboot():
        s[0].close(); fold(trace, executed, edges)
        s[0] = fcall.Session(binp, boot="1.5", trace=trace); n[0] = 0

    def checkpoint():
        with open(out, "wb") as f:
            pickle.dump((executed, edges), f)

    for fn in cands:
        crashes = 0
        for sv in STRINGS:                    # string-parse / 2-string shape
            if crashes >= CRASH_CAP:
                break
            try:
                s[0].rsp.writemem(STRP, sv.encode() + b"\x00")
                s[0].rsp.writemem(SCR, (sv if (len(sv) & 1) else "on").encode() + b"\x00" * 9)
                s[0].rsp.call(fn, (STRP, SCR, 16, 0), timeout_continue=TO)
                s[0].rsp.call(fn, (STRP, SCR, 10, 0), timeout_continue=TO)
                s[0].rsp.call(fn, (STRP, SCR, 4, 0), timeout_continue=TO)
                n[0] += 3; crashes = 0
            except Exception:
                crashes += 1; reboot()
        for nv in NUMS:                       # numeric shape
            if crashes >= CRASH_CAP:
                break
            try:
                s[0].rsp.call(fn, nv, timeout_continue=TO); n[0] += 1; crashes = 0
            except Exception:
                crashes += 1; reboot()
        if n[0] >= 80:
            reboot()
        checkpoint()                          # per-candidate checkpoint so a kill never loses work
        print("  swept 0x%08x" % fn)
    s[0].close(); fold(trace, executed, edges)
    checkpoint()
    print("saved %d edges, %d PCs -> tmp/pure_edges.pkl" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
