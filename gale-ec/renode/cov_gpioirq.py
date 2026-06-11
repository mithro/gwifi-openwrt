"""GPIO-INTERRUPT lever — exercises gpio_interrupt (gpio.c:114 get_next_bit loop / :117 handler dispatch,
conf:high). gale enables GPIO interrupts (switch.c GPIO_WP/RECOVERY_L/WP_L, power_button.c
POWER_BUTTON_L) but the EXTI model only played the COMP lines. GaleExti now has FireGpio(line) which sets
EXTI_PR[line] + pulses the GPIO-EXTI NVIC line (0-1->5, 2-3->6, 4-15->7), so the firmware's
gpio_interrupt() reads PR and dispatches the registered handler. Fire each GPIO EXTI line (the configured
ones are processed; others are not in exti_events -> harmless), toggling the pin level first. Genuine
execution of newly-modeled HW. RO + RW.
Usage: uv run --python .venv python cov_gpioirq.py [rw]
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
    trace = os.path.join(TMP, "gpioirq.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']                          # switch_init/power_button enable GPIO ints
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trgi" @%s PC' % trace]

    # toggle the WP pin (PB11) + fire its EXTI line, then sweep all GPIO EXTI lines both edges
    seq = []
    seq += ['gpioPortB OnGPIO 11 false', 'sysbus.exti FireGpio 11', 'emulation RunFor "0.04"']
    seq += ['gpioPortB OnGPIO 11 true',  'sysbus.exti FireGpio 11', 'emulation RunFor "0.04"']
    for line in range(0, 16):
        seq += ['sysbus.exti FireGpio %d' % line, 'emulation RunFor "0.02"']
    # second pass after re-toggling pins (different handler-read levels)
    for pin in (0, 1, 2, 5, 6, 11, 13):
        seq += ['gpioPortA OnGPIO %d false' % pin, 'sysbus.exti FireGpio %d' % pin, 'emulation RunFor "0.02"']
        seq += ['gpioPortA OnGPIO %d true' % pin,  'sysbus.exti FireGpio %d' % pin, 'emulation RunFor "0.02"']
    c += seq

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "gpioirq.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "gpioirq_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/gpioirq_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
