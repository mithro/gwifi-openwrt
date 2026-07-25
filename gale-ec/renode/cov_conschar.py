"""CONSOLE-CHAR lever — drives console_handle_char (console.c) input arms the campaign's console
levers missed because they sent printable commands + at most arrow keys, never the VT100
`~`-terminated sequences or the full control-char set. Targets:
 - :439 `if (c == '~')` in the ESC_BRACKET_1 state -> send ESC [ 1 ~ (Home) and ESC [ 3 ~ (Del).
 - :497 `if (input_pos == input_len)` (KEY_DEL) -> Delete at end-of-line AND mid-line (cursor moved).
 - :494 `switch (c)` variety -> the full control-char set (Ctrl-A/E/B/F/K/U/W/L/D, \b, 0x7f, tab).
 - :111/:112 word-split: `argv[*argc]=c` (c != '#') and the MAX-args bound (a command with >9 words
   and one with few) + a '#' comment line.
 - :255 `Command returned error %d` -> run commands that return nonzero error codes.
Genuine console input via usart. RO + RW. Accumulates tmp/conschar_edges.pkl.
Usage: uv run --python .venv python cov_conschar.py [rw]
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
    trace = os.path.join(TMP, "conschar.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def bytes_in(bs, t="0.04"):
        """Feed raw byte values into the console one at a time."""
        return ['sysbus.usart1 WriteChar %d' % (b & 0xFF) for b in bs] + ['emulation RunFor "%s"' % t]

    def text(s, t="0.04"):
        return bytes_in([ord(ch) for ch in s], t)

    def line(s, t="0.08"):
        return bytes_in([ord(ch) for ch in s] + [0x0D], t)   # type + Enter

    ESC = 0x1B
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += line("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trcc" @%s PC' % trace]

    # --- VT100 `~`-terminated sequences (the :439 c=='~' arm) ---
    # Type some text so there's an input buffer + cursor to act on.
    c += text("hello world")
    c += bytes_in([ESC, ord('['), ord('1'), ord('~')])     # Home  -> ESC_BRACKET_1, c=='~' (:439)
    c += bytes_in([ESC, ord('['), ord('3'), ord('~')])     # Delete at... (cursor now at home) -> KEY_DEL mid-line (:497 nottaken)
    c += bytes_in([ESC, ord('O'), ord('F')])               # End (ESC O F) -> KEY_END, cursor to end
    c += bytes_in([ESC, ord('['), ord('3'), ord('~')])     # Delete at end-of-line (:497 taken, break)
    c += bytes_in([ESC, ord('['), ord('4'), ord('~')])     # End variant (ESC[4~)
    c += bytes_in([ESC, ord('['), ord('5'), ord('~')])     # PgUp (ESC[5~) -> unknown ~ seq
    c += bytes_in([ESC, ord('['), ord('6'), ord('~')])     # PgDn (ESC[6~)
    c += bytes_in([ESC, ord('['), ord('2'), ord('~')])     # Insert (ESC[2~)
    # arrows (ESC [ A/B/C/D) + ESC O variants
    for k in "ABCD":
        c += bytes_in([ESC, ord('['), ord(k)])
    c += bytes_in([ESC, ord('O'), ord('H')])               # ESC O H (Home alt)
    c += bytes_in([ESC, ord('['), ord('Z')])               # back-tab
    c += bytes_in([ESC, ord('X')])                         # bad escape (-> ESC_BAD)
    c += text("\r", "0.06")                               # finish line

    # --- full control-char set through the switch(c) (:494) ---
    c += text("abcdef")
    for ctrl in (0x01, 0x05, 0x02, 0x06, 0x0B, 0x15, 0x17, 0x0C, 0x04, 0x09):  # A E B F K U W L D, tab
        c += bytes_in([ctrl])
    c += bytes_in([0x08])        # backspace
    c += bytes_in([0x7F])        # DEL char
    c += bytes_in([0x03])        # Ctrl-C
    c += text("\r", "0.06")

    # --- word-split arms (:111 '#'/c, :112 MAX args) ---
    c += line("a b c d e f g h i j k l m n o p")            # >9 words -> arg-count bound (:112)
    c += line("# this is a comment line")                   # '#' comment (:111 c=='#')
    c += line("x#y notacomment")                            # '#' mid-token
    c += line("one two three")                              # few words

    # --- command-returns-error arms (:255 'Command returned error %d') ---
    c += line("gpioset BADPIN 1")          # invalid arg -> error code
    c += line("gpioget NONEXIST")          # invalid -> error
    c += line("hash badsub")               # bad subcommand
    c += line("i2cxfer")                    # missing args -> PARAM_COUNT
    c += line("waitms notanumber")          # bad numeric -> PARAM
    c += line("rw 0 99 abc")                # bad args
    c += line("md")                         # missing args
    c += line("nonexistentcommand")         # unknown command

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "conschar.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "conschar_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/conschar_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
