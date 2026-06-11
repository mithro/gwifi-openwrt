"""PANIC-DATA-PRINT direct-invocation lever — the panic register-dump branches (panic.c print_reg :13
`regnum < 10`, :19 `(regnum & 3) == 3`, the FRAME_VALID / exc_return / sp-align arms in
panic_data_print 0x0800abe4) are reachable but need a VALID saved panic_data, which the emulated
`crash` doesn't reliably produce. Here we craft a valid `struct panic_data` (magic + FRAME_VALID +
populated regs[12]/frame[8]) in RAM — exactly the state a real panic produces — and DIRECT-CALL
panic_data_print(ptr) (the EC-unit-test approach), so the dump runs over all 16 registers. Genuine
execution. RO + RW. Accumulates tmp/panicinject_edges.pkl.
Usage: uv run --python .venv python cov_panicinject.py
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
TMP = os.path.join(HERE, "tmp")
PD = 0x20002400                      # scratch RAM for the crafted panic_data struct
PANIC_DATA_PRINT_RO = 0x0800abe4
PANIC_DATA_MAGIC = 0x21636e50


def craft(flags, regs, frame, exc_return):
    # struct panic_data: arch(1) version(1) flags(1) reserved(1) | cm.regs[12] | cm.frame[8] | size | magic
    r = list(regs) + [0] * (12 - len(regs))
    r[11] = exc_return                # cm.regs[11] = exc_return (handler/thread stack discriminator)
    f = list(frame) + [0] * (8 - len(frame))
    b = bytes([1, 2, flags & 0xFF, 0])
    b += struct.pack("<12I", *r)
    b += struct.pack("<8I", *f)
    size = len(b) + 8
    b += struct.pack("<II", size, PANIC_DATA_MAGIC)
    return b


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None; continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None; continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "panicinject.txt")
    if os.path.exists(trace):
        os.remove(trace)
    ex, ed = set(), set()

    # varied register/frame values so print_reg dumps non-trivial data; multiple flag/exc_return combos
    cases = [
        (1, list(range(0x10, 0x10 + 12)), [0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x55, 0x12345678], 0xFFFFFFFD),
        (1, [0xDEAD0000 + i for i in range(12)], [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88], 0xFFFFFFF9),
        (1, [0] * 12, [0] * 8, 0xFFFFFFF1),                              # handler-stack exc_return (==1)
        (0, [0xFF] * 12, [0xFF] * 8, 0xFFFFFFFD),                        # FRAME not valid -> the other arm
        (1, [0x80000000 + i for i in range(12)], [0x7FFFFFFF] * 8, 0x00000009),  # ==9 discriminator
    ]
    # panic_data_print calls panic_puts (UART) and does not return to the spin trap -> the call TIMES
    # OUT (expected); the trace still captures its execution (register dump etc.) up to the wait. Use a
    # FRESH session per case and fold the trace right after each call (do NOT reuse the hung session).
    for bank, fn in (("RO", PANIC_DATA_PRINT_RO), ("RW", PANIC_DATA_PRINT_RO + 0x10000)):
        for flags, regs, frame, exc in cases:
            s = fcall.Session(CAPTURED, boot="1.5", trace=trace)
            try:
                s.rsp.writemem(PD, craft(flags, regs, frame, exc))
                try:
                    s.rsp.call(fn, (PD, 0, 0, 0), timeout_continue=2)
                except Exception:
                    pass                      # timeout expected (panic path does not return)
            finally:
                s.close()
            fold(trace, ex, ed)

    outp = os.path.join(TMP, "panicinject_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/panicinject_edges.pkl: %d edges, %d PCs" % (len(ed), len(ex)))


if __name__ == "__main__":
    main()
