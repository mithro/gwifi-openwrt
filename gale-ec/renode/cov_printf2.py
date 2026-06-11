#!/usr/bin/env python3
"""VFNPRINTF-2 lever — closes the remaining vfnprintf (printf.c) branches by direct-calling the
format core with PER-FORMAT crafted arguments + the right addchar callback. The existing fcall_printf
battery shares ONE argword block across all formats and lacks the EC `%h` hex-dump (its `%hx`/`%hd`
hit the no-precision error path, not the success loop). Targeted missing branches (RO 0x080059b8):
  printf.c:153/164 `%h` hex dump   -> "%.Nh" with a real byte buffer (loop body) + ESTUB (overflow r0!=0)
  printf.c:182/185/197 'T' (0x54)  -> "%T"/"%lT" EC timestamp (get_time, PF_64BIT)
  printf.c:191 PF_64BIT va_arg u64 -> "%ld"/"%lx"/"%lX"/"%lu"/"%lb" with a true 64-bit value
  printf.c:203 'X'(0x58)/'b'(0x62) -> "%X","%b" + the v=-v PF_NEGATIVE sign path ("%d" of negatives)
  printf.c:266/280/288/296 pad     -> width>precision "%8.3d", space-pad "%8d", left-justify "%-8d"
vfnprintf(int (*addchar)(void*,int), void *ctx, const char *fmt, va_list args). Genuine execution of the
real formatter on injected args. RO + RW. Accumulates tmp/printf2_edges.pkl.
Usage: uv run --python .venv python cov_printf2.py
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

STUB = 0x20002800      # movs r0,#0; bx lr  -> always EC_SUCCESS
FMT = 0x20002000
ARGS = 0x20002400
HEXBUF = 0x20002600    # byte buffer for %h
ESTUB = 0x20002820     # counter addchar: succeeds ECNT times then errors
ECNT = 0x20002810
ESTUB_CODE = bytes([0x02, 0x68, 0x00, 0x2a, 0x03, 0xd0, 0x01, 0x3a,
                    0x02, 0x60, 0x00, 0x20, 0x70, 0x47, 0x01, 0x20, 0x70, 0x47])
HEXBYTES = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02, 0x7F, 0x80,
                  0x00, 0xFF, 0xA5, 0x5A, 0x10, 0x20, 0x30, 0x40])


def w32(*vals):
    return struct.pack("<%dI" % len(vals), *[v & 0xFFFFFFFF for v in vals])


# (format, argwords, use_estub, ecnt) — each a separate call with its own args.
CASES = [
    # %h hex dump WITH precision: success loop (printf.c:164) + the 'h' branch (printf.c:153)
    ("%.4h", w32(HEXBUF), False, 0), ("%.8h", w32(HEXBUF), False, 0),
    ("%.16h", w32(HEXBUF), False, 0), ("%.1h", w32(HEXBUF), False, 0),
    ("x=%.6h end", w32(HEXBUF), False, 0),
    ("%h", w32(HEXBUF), False, 0),                       # no precision -> hex-dump error arm
    # %h hex dump OVERFLOW: addchar returns error mid-dump (printf.c:164 r0!=0)
    ("%.8h", w32(HEXBUF), True, 1), ("%.8h", w32(HEXBUF), True, 3),
    ("%.16h", w32(HEXBUF), True, 5),
    # 'T' timestamp (0x54): plain and after 'l'
    ("%T", w32(0), False, 0), ("%lT", w32(0), False, 0), ("t=%T|", w32(0), False, 0),
    # 64-bit PF_64BIT va_arg path (printf.c:191): true 64-bit values
    ("%ld", w32(0x89ABCDEF, 0x01234567), False, 0), ("%lx", w32(0x89ABCDEF, 0x01234567), False, 0),
    ("%lX", w32(0xFFFFFFFF, 0x7FFFFFFF), False, 0), ("%lu", w32(0x00000000, 0x80000000), False, 0),
    ("%lb", w32(0x0000000F, 0), False, 0), ("%lld", w32(0xFFFFFFFF, 0xFFFFFFFF), False, 0),
    ("%ld", w32(0x00000000, 0x80000000), False, 0),     # INT64_MIN edge (v == 1<<63, skip v=-v)
    # signed negative -> PF_NEGATIVE (printf.c:266) + v=-v (printf.c:203)
    ("%d", w32(0xFFFFFFFF), False, 0), ("%d", w32(0x80000000), False, 0),
    ("%d", w32(0xFFFFFF9C), False, 0), ("%6d", w32(0xFFFFFFFB), False, 0),
    # base conversions
    ("%X", w32(0xDEADBEEF), False, 0), ("%b", w32(0xA5), False, 0),
    ("%b", w32(0), False, 0), ("%x", w32(0xABCDEF), False, 0),
    ("%u", w32(42), False, 0), ("%p", w32(0x08001234), False, 0),
    # width / precision / justify (printf.c:280/288/296)
    ("%8.3d", w32(5), False, 0), ("%8d", w32(5), False, 0), ("%-8d", w32(5), False, 0),
    ("%08d", w32(5), False, 0), ("%-8.3d", w32(5), False, 0), ("%12.4x", w32(0xAB), False, 0),
    ("%-12.4x", w32(0xAB), False, 0), ("%.5d", w32(7), False, 0), ("%2.8d", w32(123456), False, 0),
    # --- fresh-residual targeted (printf.c:197 switch-default error_str / :266 PF_NEGATIVE / :288 space-pad
    #     / :292 precision loop / :296 trailing space) ---
    ("%lz", w32(0, 0), False, 0), ("%lj", w32(1, 0), False, 0), ("%lq", w32(2, 0), False, 0),  # 64-bit bad conv -> error_str
    ("% 8d", w32(7), False, 0), ("%8u", w32(7), False, 0), ("% 8x", w32(0x2a), False, 0),       # space pad, no PADZERO
    ("%-8u", w32(9), False, 0), ("%-10x", w32(0xAB), False, 0), ("%-6d", w32(0xFFFFFFFB), False, 0),  # left-justify trailing space
    ("%.2s", w32(0x20002600), False, 0), ("%.1s", w32(0x20002600), False, 0),                    # string precision underflow
    ("%lT", w32(0, 0), False, 0), ("ts:%T.", w32(0, 0), False, 0),                               # 'T' switch case (:197)
    ("%d", w32(0x80000000), False, 0), ("%6d", w32(0x80000001), False, 0),                       # PF_NEGATIVE INT_MIN edges
    # reach the 64-bit-dispatch default 'T'-check block 0x08005b80 via %l<low-char != d/X/b/T>
    # (its beq-taken, c=='T', is provably dead: a post-'l' T is caught earlier at 0x08005b5c):
    ("%lc", w32(0x41, 0), False, 0), ("%la", w32(1, 0), False, 0), ("%l]", w32(2, 0), False, 0),
    ("%lr", w32(3, 0), False, 0), ("%lo", w32(0o755, 0), False, 0),
    # string precision: string LONGER than precision -> the --precision underflow exit (printf.c:292)
    ("%.2s", w32(0x20002600), False, 0), ("%.0s", w32(0x20002600), False, 0),
    ("%.3p", w32(0x08001234), False, 0), ("%5.2u", w32(987654), False, 0),
    # negative with width+zero-pad (sign + PADZERO interplay), and space-pad large
    ("%08d", w32(0xFFFFFFFB), False, 0), ("%-8d", w32(0xFFFFFF00), False, 0),
    ("% d", w32(5), False, 0), ("%+d", w32(5), False, 0),
]


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
    out = os.path.join(TMP, "printf2_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass

    trace = os.path.join(TMP, "printf2.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def fresh():
        s = fcall.Session(binp, boot="1.5", trace=trace)
        s.rsp.writemem(STUB, bytes([0x00, 0x20, 0x70, 0x47]))
        s.rsp.writemem(ESTUB, ESTUB_CODE)
        s.rsp.writemem(HEXBUF, HEXBYTES)
        return s

    for bank, vfn in (("RO", 0x080059b8), ("RW", 0x080159b8)):
        s = fresh()
        try:
            for fmt, argbytes, use_estub, ecnt in CASES:
                try:
                    s.rsp.writemem(FMT, fmt.encode() + b"\x00")
                    s.rsp.writemem(HEXBUF, HEXBYTES)
                    s.rsp.writemem(ARGS, argbytes + b"\x00" * 8)
                    if use_estub:
                        s.rsp.writemem(ECNT, struct.pack("<I", ecnt))
                        s.rsp.call(vfn, (ESTUB | 1, ECNT, FMT, ARGS), timeout_continue=3)
                    else:
                        s.rsp.call(vfn, (STUB | 1, 0, FMT, ARGS), timeout_continue=3)
                except Exception:
                    s.close()
                    fold(trace, executed, edges)
                    s = fresh()
        finally:
            s.close()
            fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/printf2_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
