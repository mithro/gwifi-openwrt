"""SMALL conf:high clusters without model changes:
 - usart_rx_interrupt_handler:32 `if (!queue_add_unit(...))` -> RX queue FULL: blast a char burst faster
   than the console drains it, so queue_add_unit fails (the dropped-byte arm).
 - flash_is_erased:270 `if (*ptr != CONFIG_FLASH_ERASED_VALUE32)` -> BOTH arms: erase a region that has
   DATA (loop finds non-0xFF early -> not-erased) AND a region already all-0xFF (loop completes -> erased),
   via FLASH_WRITE+FLASH_ERASE vs FLASH_ERASE+FLASH_ERASE host commands.
Genuine execution. RO + RW.  Usage: uv run --python .venv python cov_smallisr.py [rw]
"""
import os, pickle, subprocess, sys
import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


def _le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
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
    trace = os.path.join(TMP, "smallisr.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.25"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data), 'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trsi" @%s PC' % trace]

    # (1) USART RX queue overflow: blast many chars with NO RunFor between (console can't drain) -> the
    # queue_add_unit-fails (dropped-byte) arm in usart_rx_interrupt_handler.
    burst = []
    for _ in range(400):
        burst += ['sysbus.usart1 WriteChar %d' % ord('A')]
    c += burst + ['emulation RunFor "0.1"']
    for _ in range(300):
        c += ['sysbus.usart1 WriteChar %d' % ord('x')]
    c += ['emulation RunFor "0.1"'] + cc("")    # newline to flush

    # (2) flash_is_erased both arms:
    #   has-DATA region -> not-erased arm: write data then erase
    c += hc(0x12, _le32(0x18000) + _le32(8) + [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])  # FLASH_WRITE
    c += hc(0x13, _le32(0x18000) + _le32(0x800))                                                  # FLASH_ERASE -> is_erased(false)
    #   already-erased region -> erased arm: erase the now-erased region again
    c += hc(0x13, _le32(0x18000) + _le32(0x800))                                                  # FLASH_ERASE -> is_erased(true, loop completes)
    c += cc("flasherase 0x18000 0x800") + cc("flashwrite 0x18000 4") + cc("flasherase 0x18000 0x800")
    c += cc("flashinfo")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "smallisr.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "smallisr_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/smallisr_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
