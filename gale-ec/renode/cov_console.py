#!/usr/bin/env python3
"""CONSOLE-EDITOR lever — replicate the EC's own test/console_edit.c stimulus (author-designed) against
the captured firmware. The campaign's other console scenarios only send "command\\r", so the line
editor's ANSI-escape / cursor / history / kill / insert-delete state machine (console_has_input ->
handle_console_char) is never exercised both-ways. This sends the exact key sequences the unit test
uses: arrows (ESC[A-D), delete (ESC[3~), home (ESC[1~), end (ESC O F), ctrl-keys, backspace, and the
full history navigation (up/up-up/down/edit/stash/list) + output-channel (chan save/0/restore).
Genuine execution of the real console editor. RO + RW. Accumulates tmp/console_edges.pkl.
Usage: uv run --python .venv python cov_console.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")

# editor key byte-sequences (from test/console_edit.c)
UP, DOWN, RIGHT, LEFT = b"\x1b[A", b"\x1b[B", b"\x1b[C", b"\x1b[D"
DEL, HOME, END = b"\x1b[3~", b"\x1b[1~", b"\x1bOF"
CTRL = lambda c: bytes([ord(c) - ord('@')])           # ctrl-K = 0x0B, ctrl-A = 0x01, ctrl-E = 0x05


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "console.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def send(b):                                       # raw bytes -> usart1, then let the editor run
        return ['sysbus.usart1 WriteChar %d' % x for x in b] + ['emulation RunFor "0.03"']

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += ['sysbus.usart1 WriteChar %d' % x for x in b"sysjump rw\r"] + ['emulation RunFor "0.5"']
    c += ['cpu CreateExecutionTracing "trcon" @%s PC' % trace]

    seqs = [
        b"test123\r",                                  # baseline
        UP, LEFT * 3, RIGHT * 2, HOME, END,            # cursor movement + arrows
        b"testx\b1\r",                                 # backspace edit
        b"tet1" + LEFT * 2 + b"s\r",                   # insert char mid-line
        b"testt1" + LEFT + b"\b\r",                    # delete-via-backspace mid-line
        b"txet1" + LEFT * 4 + RIGHT + b"s\r",          # move + insert
        b"est" + LEFT * 3 + b"t" + END + b"1\r",       # home/insert/end
        b"test123" + HOME + DEL + END + b"\r",         # delete key + home + end
        b"killme" + HOME + CTRL('K') + b"\r",          # ctrl-K kill-to-end
        b"abc" + LEFT * 2 + CTRL('K') + b"\r",         # ctrl-K mid-line
        # history: build a stack, then navigate
        b"hist1\r", b"hist2\r", b"hist3\r", b"hist4\r", b"hist5\r",
        UP, UP, UP, DOWN, DOWN, b"\r",                 # up/up-up/down navigation
        UP + b"\bX\r",                                 # history edit
        UP + UP + DOWN + b"\r",                        # up-up-down
        b"partial" + UP + b"\r",                       # history stash (type then recall)
        b"history\r",                                  # history list
        # output channel commands (chan save/set/restore)
        b"chan save\r", b"chan 0\r", b"chan 0xffffffff\r", b"chan restore\r", b"chan\r",
        # control chars / edge cases
        CTRL('A') + b"start" + CTRL('E') + b"\r",      # ctrl-A home, ctrl-E end (if supported)
        b"\x1b[Z\r",                                   # unknown escape (back-tab) -> default arm
        b"\x1b\x1b\r",                                 # bare ESC then ESC
        b"\t\r", b"he\t\r",                            # tab (completion if any)
    ]
    for s in seqs:
        c += send(s)
    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "console.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "console_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/console_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
