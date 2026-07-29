"""USB-INTERRUPT-EVENT lever — exercises usb_interrupt (usb.c:242-263, conf:high ~14 br): the RESET arm
(:257 status&(1<<10) -> the ep-reset loop :242), and the CTR arm (:260 status&(1<<15)) with DIR (:263
status&0x10 = RX vs TX) across endpoints. GaleUsb exposes SignalReset() and SignalTransfer(ep,rx,setup)
which raise the modeled USB IRQ -> the real usb_interrupt() services them. Drive a RESET + transfers on
several endpoints, both directions, repeatedly. Genuine execution. RO + RW.
Usage: uv run --python .venv python cov_usbevt.py [rw]
"""
import os, pickle, subprocess, sys
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
    trace = os.path.join(TMP, "usbevt.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def run(t="0.03"):
        return ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']                          # usb_init runs -> interrupts enabled
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "true" @%s PC' % trace]

    # USB RESET -> usb_interrupt RESET arm + the per-endpoint reset loop (:242/:257)
    for _ in range(3):
        c += ['sysbus.usb SignalReset'] + run("0.05")
    # CTR transfers across endpoints, both directions (RX/TX) + SETUP -> :260 CTR + :263 DIR + :262 ep<COUNT
    for ep in (0, 1, 2, 3):
        c += ['sysbus.usb SignalTransfer %d true true' % ep] + run()    # RX SETUP
        c += ['sysbus.usb SignalTransfer %d true false' % ep] + run()   # RX (OUT)
        c += ['sysbus.usb SignalTransfer %d false false' % ep] + run()  # TX (IN)
    # out-of-range endpoint -> the ep >= USB_EP_COUNT path (:262 false)
    c += ['sysbus.usb SignalTransfer 7 true false'] + run()
    c += ['sysbus.usb SignalTransfer 15 false false'] + run()
    # reset again then more transfers (re-enumeration sequence)
    c += ['sysbus.usb SignalReset'] + run("0.05")
    for ep in (0, 1):
        c += ['sysbus.usb SignalTransfer %d true true' % ep] + run()
        c += ['sysbus.usb SignalTransfer %d false false' % ep] + run()

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "usbevt.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "usbevt_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/usbevt_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
