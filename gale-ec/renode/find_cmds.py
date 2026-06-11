#!/usr/bin/env python3
"""Locate the __cmds console-command table INSIDE the captured binary by structural scan.
Each struct console_command is {name_ptr, handler_ptr, argdesc_ptr, shorthelp_ptr} (16B if
CONFIG_CONSOLE_CMDHELP) or {name_ptr, handler_ptr} (8B). Identify the longest contiguous run of
records where name_ptr -> printable ASCII (a plausible command token) and handler_ptr is an odd
(thumb) address in the text region. Report stride, base, count, and the decoded command list.
"""
import os
import string
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = 0x08000000

with open(CAPTURED, "rb") as f:
    BIN = f.read()
END = BASE + len(BIN)
PRINT = set(string.printable[:-6].encode())  # no whitespace controls except space


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


def looks_name(addr):
    s = ascii_at(addr)
    return s if (s and all(33 <= ord(c) < 127 for c in s)) else None


def is_handler(v):
    return (v & 1) == 1 and BASE <= (v & ~1) < END


def score_run(start_off, stride):
    """count contiguous valid records starting at start_off for given stride (8 or 16)."""
    cnt = 0
    cmds = []
    o = start_off
    while o + stride <= len(BIN):
        name_p = rd32(o)
        handler = rd32(o + 4)
        nm = looks_name(name_p) if is_ptr(name_p) else None
        if nm is None or not is_handler(handler):
            break
        if stride == 16:
            ad = rd32(o + 8)
            sh = rd32(o + 12)
            if not ((ad == 0 or is_ptr(ad)) and (sh == 0 or is_ptr(sh))):
                break
        cmds.append((nm, handler & ~1))
        cnt += 1
        o += stride
    return cnt, cmds


def main():
    best = None
    for stride in (16, 8):
        o = 0
        while o + stride <= len(BIN):
            name_p = rd32(o)
            if is_ptr(name_p) and looks_name(name_p) and is_handler(rd32(o + 4)):
                cnt, cmds = score_run(o, stride)
                if cnt >= 8 and (best is None or cnt > best[0]):
                    best = (cnt, stride, BASE + o, cmds)
                o += stride * max(cnt, 1)
            else:
                o += 4
    if not best:
        print("no plausible __cmds table found")
        return
    cnt, stride, base, cmds = best
    print("FOUND __cmds: base=0x%08x stride=%d count=%d (end=0x%08x)\n"
          % (base, stride, cnt, base + cnt * stride))
    for nm, h in sorted(cmds, key=lambda x: x[0].lower()):
        print("  %-14s handler=0x%08x" % (nm, h))


if __name__ == "__main__":
    main()
