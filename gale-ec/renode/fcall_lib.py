#!/usr/bin/env python3
"""LIBRARY-FUNCTION direct-call lever — pure, input-determined functions whose branches the firmware's
own callers never exercise (callers only pass base-10 positive numbers / non-overlapping aligned copies).
Entry points CONFIRMED by direct disassembly of the captured binary (the conf:approx report labels are
unreliable; e.g. its "uint64divmod" @0x0800ad2c is actually a struct/ADC reader, so it is NOT targeted):
  strtoi  @ RO 0x0800a6fe / RW 0x0801a6fe  (const char *nptr, char **endptr, int base)
  memmove @ RO 0x0800a8cc / RW 0x0801a8cc  (void *dest, const void *src, size_t len)
Missing strtoi arms: leading whitespace skip (util.c:110), uppercase-hex 'A'-'F' (util.c:128),
lowercase-hex 'a'-'f' (util.c:130). Missing memmove arms: non-overlapping forward with dest>=src+len
(util.c:258), same-alignment word copy (util.c:274/279), overlapping BACKWARD word loop + byte tail
(util.c:294/300). We direct-call them with crafted strings/buffers in RAM — genuine execution, the real
helper parses/copies the injected data. Accumulates tmp/lib_edges.pkl (unioned by combine_coverage.py).
Usage: uv run --python .venv python fcall_lib.py
"""
import os
import pickle

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

STRTOI = [0x0800a6fe, 0x0801a6fe]
MEMMOVE = [0x0800a8cc, 0x0801a8cc]

# Scratch RAM well clear of the boot stack-scribble (0x20002000..40) and below the live stack.
STRBUF = 0x20002800     # strtoi input string
ENDPTR = 0x20002880     # strtoi endptr storage (char **)
SRC = 0x20002900        # memmove source buffer
DST = 0x20002980        # memmove dest buffer (non-overlapping)

# (string, base) pairs: leading whitespace, upper/lower hex, high base, sign, overflow, auto-base.
STRTOI_CASES = [
    ("  42", 10), ("\t 7", 10), ("1A", 16), ("ff", 16), ("0xC0DE", 16), ("DEAD", 16),
    ("z", 36), ("Zy", 36), ("-5", 10), ("+9", 10), ("123", 0), ("0x1f", 0), ("0777", 0),
    ("99999999999999", 10), ("  -0X2a", 16), ("g", 16), ("", 10), ("  ", 10),
    # exact stragglers from the digit classifier (disasm 0x0800a77e..a79c):
    (":", 10), ("9:", 10), (";", 10),        # char in ':'..'@' (>= '0'+10, <= '@') -> ble taken @a780
    ("G", 16), ("9G", 16), ("[", 16), ("`", 16),  # char in 'G'..'`' (>= 'A'+base-10, <= '`') -> ble taken @a790
]
# strtoi calls with endptr == NULL (r1=0) so the loop's `if (endptr)` store is skipped (beq taken @a7a0).
STRTOI_NULL_ENDPTR = [("42", 10), ("1a", 16), ("7", 10)]


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
    out = os.path.join(TMP, "lib_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior lib_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)

    trace = os.path.join(TMP, "lib.txt")
    if os.path.exists(trace):
        os.remove(trace)

    s = fcall.Session(binp, boot="1.5", trace=trace)

    def reboot():
        nonlocal s
        s.close()
        fold(trace, executed, edges)
        s = fcall.Session(binp, boot="1.5", trace=trace)

    try:
        for base_fn_strtoi, base_fn_memmove in ((STRTOI[0], MEMMOVE[0]), (STRTOI[1], MEMMOVE[1])):
            # ---- strtoi: write the string + a zeroed endptr slot, call(nptr, &endptr, base)
            for sstr, base in STRTOI_CASES:
                try:
                    s.rsp.writemem(STRBUF, sstr.encode() + b"\x00")
                    s.rsp.writemem(ENDPTR, b"\x00\x00\x00\x00")
                    s.rsp.call(base_fn_strtoi, (STRBUF, ENDPTR, base, 0), timeout_continue=2)
                except Exception:
                    reboot()
            # strtoi with endptr == NULL: valid digit reaches the loop store-skip (beq taken @a7a0)
            for sstr, base in STRTOI_NULL_ENDPTR:
                try:
                    s.rsp.writemem(STRBUF, sstr.encode() + b"\x00")
                    s.rsp.call(base_fn_strtoi, (STRBUF, 0, base, 0), timeout_continue=2)
                except Exception:
                    reboot()
            # ---- memmove cases
            payload = bytes(range(1, 65))
            mm_cases = [
                # (dest, src, len) — non-overlapping forward, dest ABOVE src+len, same alignment
                (DST, SRC, 32),
                # same alignment, larger word-aligned copy (forward word loop)
                (DST, SRC, 60),
                # overlapping BACKWARD: src<dest<src+len, word-aligned, multi-word + byte tail
                (SRC + 4, SRC, 40), (SRC + 8, SRC, 50), (SRC + 4, SRC, 37),
                # overlapping BACKWARD, same NON-zero alignment (dest&3==src&3!=0): leaves trailing
                # bytes below the word boundary -> the trailing byte loop runs (a916 fall) + leading
                # byte loop (a8f8). src/dest both ==1 (mod 4); dest>src; dest<src+len.
                (SRC + 5, SRC + 1, 40), (SRC + 9, SRC + 1, 40), (SRC + 6, SRC + 2, 32),
                (SRC + 7, SRC + 3, 28),
                # overlapping FORWARD (dest<src): copies via memcpy path
                (SRC, SRC + 4, 40),
                # misaligned dest vs src (dest&3 != src&3) -> byte path
                (DST + 1, SRC, 33), (DST + 2, SRC, 17),
                # tiny / zero length edges
                (DST, SRC, 1), (DST, SRC, 0), (DST, SRC, 3),
            ]
            for dest, src, ln in mm_cases:
                try:
                    s.rsp.writemem(SRC, payload)
                    s.rsp.call(base_fn_memmove, (dest, src, ln, 0), timeout_continue=2)
                except Exception:
                    reboot()
            reboot()   # fresh session between RO and RW images
    finally:
        s.close()
        fold(trace, executed, edges)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/lib_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
