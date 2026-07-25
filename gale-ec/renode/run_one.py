#!/usr/bin/env python3
"""Run one gale image in Renode headless; report where it went + unmodeled accesses.

Boots an image on the gale machine (base.resc), runs a bounded slice of virtual
time, and reports (a) final PC / executed-instruction count / halt state and
(b) every distinct "non existing peripheral" (unmodeled) address the firmware
touched, aggregated with counts. Those addresses are the trace-driven worklist.
"""
import argparse
import collections
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--name", default="gale")
    ap.add_argument("--sym", default="", help="optional ELF for symbol resolution")
    ap.add_argument("--runt", default="0.2", help="virtual seconds to run")
    ap.add_argument("--logfile", default=os.path.join(HERE, "run.log"))
    args = ap.parse_args()

    cmds = [
        '$h=@%s' % HERE,
        '$bin=@%s' % os.path.abspath(args.bin),
        '$name="%s"' % args.name,
        'include @%s' % BASE,
    ]
    if args.sym:
        cmds.append('sysbus LoadSymbolsFrom @%s' % os.path.abspath(args.sym))
    cmds += [
        'emulation RunFor "%s"' % args.runt,
        'cpu PC',
        'cpu ExecutedInstructions',
        'cpu IsHalted',
        'quit',
    ]
    proc = subprocess.run(
        ["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, timeout=600,
    )
    out = ANSI.sub("", proc.stdout)
    with open(args.logfile, "w") as f:
        f.write(out)

    lines = [l.rstrip() for l in out.splitlines()]
    pc = instr = halt = "?"
    for l in lines:
        s = l.strip()
        if re.fullmatch(r"0x[0-9A-Fa-f]{1,9}", s):
            pc = s
        elif re.fullmatch(r"0x[0-9A-Fa-f]{10,16}", s):
            instr = str(int(s, 16))
        elif s in ("True", "False"):
            halt = s

    # Aggregate accesses to non-existing (unmodeled) peripherals.
    rx = re.compile(
        r"(Read|Write)\w*\s+(?:from|to)\s+non existing peripheral at (0x[0-9A-Fa-f]+)")
    hits = collections.Counter()
    kinds = collections.defaultdict(set)
    for line in lines:
        m = rx.search(line)
        if m:
            addr = int(m.group(2), 16)
            hits[addr] += 1
            kinds[addr].add(m.group(1))

    errs = [l for l in lines
            if re.search(r"error|exception|could not|failed|cannot", l, re.I)
            and "non existing" not in l]

    print("=== RENODE RUN: %s ===" % args.name)
    print("POSTRUN_PC:    %s" % pc)
    print("POSTRUN_INSTR: %s" % instr)
    print("POSTRUN_HALT:  %s" % halt)
    print("--- unmodeled peripheral addresses: %d ---" % len(hits))
    for addr in sorted(hits):
        print("  0x%08X  %-10s  x%d  %s"
              % (addr, "/".join(sorted(kinds[addr])), hits[addr], periph_guess(addr)))
    if errs:
        print("--- error/diagnostic lines (%d) ---" % len(errs))
        for l in errs[:30]:
            print("  " + l.strip())


RANGES = [
    (0x40000000, 0x40000400, "TIM2"), (0x40000400, 0x40000800, "TIM3"),
    (0x40001000, 0x40001400, "TIM6"), (0x40001400, 0x40001800, "TIM7"),
    (0x40002000, 0x40002400, "TIM14"), (0x40002800, 0x40002C00, "RTC"),
    (0x40002C00, 0x40003000, "WWDG"), (0x40003000, 0x40003400, "IWDG"),
    (0x40003800, 0x40003C00, "SPI2"), (0x40004400, 0x40004800, "USART2"),
    (0x40004800, 0x40004C00, "USART3"), (0x40005400, 0x40005800, "I2C1"),
    (0x40005800, 0x40005C00, "I2C2"), (0x40005C00, 0x40006000, "USB"),
    (0x40006000, 0x40006400, "USB_FS"), (0x40006400, 0x40006800, "bxCAN"),
    (0x40006C00, 0x40007000, "CRS"), (0x40007000, 0x40007400, "PWR"),
    (0x40010000, 0x40010400, "SYSCFG/COMP"), (0x40010400, 0x40010800, "EXTI"),
    (0x40011400, 0x40011800, "USART6"), (0x40012400, 0x40012800, "ADC"),
    (0x40012C00, 0x40013000, "TIM1"), (0x40013000, 0x40013400, "SPI1"),
    (0x40013800, 0x40013C00, "USART1"), (0x40014000, 0x40014400, "TIM15"),
    (0x40014400, 0x40014800, "TIM16"), (0x40014800, 0x40014C00, "TIM17"),
    (0x40015800, 0x40015C00, "DBGMCU"), (0x40020000, 0x40020400, "DMA"),
    (0x40021000, 0x40021400, "RCC"), (0x40022000, 0x40022400, "FLASH_IF"),
    (0x40023000, 0x40023400, "CRC"), (0x48000000, 0x48001800, "GPIO"),
]


def periph_guess(addr):
    for lo, hi, name in RANGES:
        if lo <= addr < hi:
            return "%s+0x%X" % (name, addr - lo)
    return "?"


if __name__ == "__main__":
    main()
