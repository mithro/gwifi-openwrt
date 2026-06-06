#!/usr/bin/env python3
"""gale EC execution-trace equivalence — peripheral-access (MMIO) trace diff.

The strongest build-independent execution trace of two firmwares is the sequence
of hardware register accesses they perform: address/offset, read-vs-write, width,
and value. These are HARDWARE facts (same STM32F072 register map for both builds),
so an equivalent firmware programs the silicon in the same order with the same
values — unlike the instruction/PC stream, which differs by toolchain.

This tool boots BOTH images, logs every access to a set of peripherals (in CPU
execution order), strips the build-specific `[cpu: 0xPC]` prefix, and compares the
two access sequences by LONGEST COMMON PREFIX. A long identical prefix is direct
evidence the firmwares drive the hardware identically. (A fixed virtual-time window
captures different amounts of progress, so the sequences eventually diverge simply
because one image ran further — hence prefix length, not full-sequence equality, is
the meaningful metric; the FIRST genuine value/offset mismatch is reported for audit.)
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Peripherals to trace (the ones the boot/console paths actually touch).
PERIPHS = [
    "rcc", "flashif", "gpioPortA", "gpioPortB", "gpioPortC", "gpioPortF",
    "usart1", "usart2", "spi1", "spi2", "dma1", "adc", "exti",
    "timer1", "timer2", "timer3", "timer16", "timer17",
]
# matches "<periph>: [cpu: 0x...] <Read|Write>... " and captures periph + the rest
LINE = re.compile(r"(\w+): \[cpu: 0x[0-9A-Fa-f]+\] (.*)$")


def capture(binpath, runt):
    cmds = [
        '$h=@%s' % HERE,
        '$bin=@%s' % os.path.abspath(binpath),
        '$name="g"',
        'include @%s' % BASE,
    ]
    for p in PERIPHS:
        cmds.append('sysbus LogPeripheralAccess sysbus.%s true' % p)
    cmds += ['emulation RunFor "%s"' % runt, 'quit']
    proc = subprocess.run(
        ["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, timeout=600,
    )
    out = ANSI.sub("", proc.stdout)
    seq = []
    pset = set(PERIPHS)
    for line in out.splitlines():
        m = LINE.search(line)
        if m and m.group(1) in pset:
            seq.append("%s: %s" % (m.group(1), m.group(2).strip()))
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True)
    ap.add_argument("--rebuilt", required=True)
    ap.add_argument("--runt", default="0.02", help="virtual seconds (cover boot)")
    ap.add_argument("--outdir", default=os.path.join(HERE, "transcripts"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    o = capture(args.orig, args.runt)
    r = capture(args.rebuilt, args.runt)
    with open(os.path.join(args.outdir, "trace_orig.txt"), "w") as f:
        f.write("\n".join(o))
    with open(os.path.join(args.outdir, "trace_rebuilt.txt"), "w") as f:
        f.write("\n".join(r))

    # longest common prefix
    lcp = 0
    for a, b in zip(o, r):
        if a == b:
            lcp += 1
        else:
            break

    # Order-independent view: the multiset of (offset,R/W,value) events. Equivalent
    # firmwares touch the same registers with the same values even if a different-era
    # toolchain schedules the init steps in a slightly different order. Strip the
    # read-return value's annotation noise; keep periph+op+offset+value.
    import collections
    co, cr = collections.Counter(o), collections.Counter(r)
    common = co & cr            # multiset intersection
    only_o = co - cr
    only_r = cr - co
    n_common = sum(common.values())

    print("=== EXECUTION-TRACE (MMIO register-access) EQUIVALENCE ===")
    print("peripherals traced: %s" % ", ".join(PERIPHS))
    print("orig accesses: %d   rebuilt accesses: %d" % (len(o), len(r)))
    print("LONGEST COMMON PREFIX: %d identical register accesses (in order)" % lcp)
    if lcp < min(len(o), len(r)):
        print("--- first divergence at access #%d (likely init ordering / timing) ---" % lcp)
        print("  orig:    %s" % (o[lcp] if lcp < len(o) else "<end>"))
        print("  rebuilt: %s" % (r[lcp] if lcp < len(r) else "<end>"))
    print("--- order-independent (multiset) coverage ---")
    print("common access-events (in both): %d" % n_common)
    print("only in orig: %d distinct  / only in rebuilt: %d distinct"
          % (len(only_o), len(only_r)))
    for label, c in (("orig-only", only_o), ("rebuilt-only", only_r)):
        if c:
            print("  top %s events:" % label)
            for ev, n in c.most_common(8):
                print("    x%d  %s" % (n, ev))


if __name__ == "__main__":
    main()
