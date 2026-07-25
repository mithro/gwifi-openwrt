#!/usr/bin/env python3
"""Targeted coverage of three reached-one-direction (flippable) clusters that direct invocation with
SEMANTICALLY-crafted scalar inputs can flip (the proven pure/near-pure technique):

  0x08003c00 (RO)/0x08013c00 (RW) — ANSI/console char dispatcher: switches on r0 = an input char/key
     (cmp #0xd CR, #0x44 'D', #0x46 'F', #0x7e '~', #0xc ...). Sweep r0 over the full byte range +
     the escape-sequence keys so every key-case dispatch arm executes.
  0x08009eb0 (RO)/0x08019eb0 (RW) — error-code handler: tests r0 == -2 / -6 (adds r3,r4,#N;bne) and
     r0 sign (cmp #0;blt/ble/bge). Call with r0 over the EC error-code range + sign edges, r1=buffer.
  0x0800971c (RO)/0x0801971c (RW) — argc/argv console handler: early arg-validation arms flip with
     crafted argc + argv string-pointer arrays.

Genuine execution; accumulates tmp/misc_edges.pkl (unioned by combine_coverage.py). Serial + capped.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

BUF = 0x20002000        # scratch buffer (r1 for the error-code handler)
ARGV = 0x20002400       # argv pointer array
STRS = 0x20002500       # argv string storage
M = 0xFFFFFFFF


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
    out = os.path.join(TMP, "misc_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior misc_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)

    trace = os.path.join(TMP, "misc.txt")
    if os.path.exists(trace):
        os.remove(trace)

    s = [fcall.Session(binp, boot="1.5", trace=trace)]

    def reboot():
        s[0].close(); fold(trace, executed, edges)
        s[0] = fcall.Session(binp, boot="1.5", trace=trace)

    def call(fn, args):
        try:
            s[0].rsp.call(fn, args, timeout_continue=1)
        except Exception:
            reboot()

    # 0x8003c00 = console_handle_char, a STATEFUL VT100 line editor: ESC(0x1b) sets escape-buffer
    # [state+0x50]; subsequent chars walk the escape sub-parser ([ / O / digits / final D,F,~,A..H).
    # So the escape-key cases only flip when fed the SEQUENCE in order on ONE session (no reboot).
    ESC, LB, OO = 0x1b, 0x5b, 0x4f          # ESC, '[', 'O'
    seqs = []
    for final in (0x41, 0x42, 0x43, 0x44, 0x46, 0x48, 0x50, 0x7e):   # A B C D F H P ~
        seqs.append([ESC, LB, final])
        seqs.append([ESC, OO, final])
    for d in (0x31, 0x32, 0x33, 0x34, 0x35, 0x36):                   # ESC [ <digit> ~
        seqs.append([ESC, LB, d, 0x7e])
    seqs.append([ESC, LB, 0x31, 0x3b, 0x35, 0x44])                   # ctrl-left (modifier form)
    seqs.append([ESC, LB, 0x33, 0x7e])                               # delete
    # plain editing chars (each its own 1-char "sequence"): CR LF tab BS DEL printable ctrl-keys
    for ch in (0x0d, 0x0a, 0x09, 0x08, 0x7f, ord('a'), ord('Z'), ord('0'), ord(' '),
               0x01, 0x02, 0x04, 0x05, 0x06, 0x0b, 0x0c, 0x0e, 0x10, 0x17, 0x1b, 0x03, 0x00):
        seqs.append([ch])
    # error-code handler: EC error codes (negatives), sign edges, the 0xd special, INT_MIN
    ecodes = [(-n) & M for n in range(0, 16)] + [0, 1, 2, 0xd, 0x7FFFFFFF, 0x80000000, 5, 50]

    for cd in (0x08003c00, 0x08013c00):
        for seq in seqs:
            for ch in seq:                  # feed the sequence IN ORDER, state persists in RAM global
                call(cd, (ch, 0, 0, 0))
    for eh in (0x08009eb0, 0x08019eb0):
        for ec in ecodes:
            s[0].rsp.writemem(BUF, b"\x00" * 64)
            call(eh, (ec, BUF, 32, 0))
    # argc/argv handler: argv = [STRS+0, STRS+16, STRS+32], strings vary
    s[0].rsp.writemem(STRS, b"on\x00" + b"\x00" * 13 + b"1\x00" + b"\x00" * 14 + b"foo\x00")
    s[0].rsp.writemem(ARGV, struct.pack("<4I", STRS, STRS + 16, STRS + 32, 0))
    for ah in (0x0800971c, 0x0801971c):
        for argc in (0, 1, 2, 3):
            call(ah, (argc, ARGV, 0, 0))

    s[0].close(); fold(trace, executed, edges)
    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/misc_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
