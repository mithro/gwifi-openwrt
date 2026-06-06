#!/usr/bin/env python3
"""Boot a gale image in Renode, capture USART1 console output, optionally inject
console commands, and print a clean transcript.

The USART1 LoggingUartAnalyzer emits lines of the form
  HH:MM:SS.ssss [INFO] usart1: [host: ...|virt: ...] <console text>
This extracts <console text> in order, giving the firmware's console transcript —
the observable compared between the original and rebuilt images.
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
# match "usart1: [host: ...|virt: ...] TEXT"  (single prefix bracket pair)
UART = re.compile(r"usart1: \[host:[^\]]*\]\s?(.*)$")


def char_cmds(s):
    """Renode monitor commands to type string s into USART1 (as RX input)."""
    return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in s]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--name", default="gale")
    ap.add_argument("--boot", default="0.1", help="virtual seconds to boot before commands")
    ap.add_argument("--settle", default="0.03", help="virtual seconds to run after each command")
    ap.add_argument("--cmd", action="append", default=[],
                    help="console command to send after boot (repeatable)")
    ap.add_argument("--mon", action="append", default=[],
                    help="Renode monitor command to run before boot (repeatable)")
    ap.add_argument("--logfile", default=os.path.join(HERE, "console.log"))
    args = ap.parse_args()

    cmds = [
        '$h=@%s' % HERE,
        '$bin=@%s' % os.path.abspath(args.bin),
        '$name="%s"' % args.name,
        'include @%s' % BASE,
    ]
    cmds += list(args.mon)   # e.g. inject ADC CC values for a USB-debug-accessory scenario
    cmds += [
        'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
        'emulation RunFor "%s"' % args.boot,
    ]
    for c in args.cmd:
        cmds += char_cmds(c + "\r")
        cmds.append('emulation RunFor "%s"' % args.settle)
    cmds.append('quit')

    proc = subprocess.run(
        ["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, timeout=600,
    )
    out = ANSI.sub("", proc.stdout)
    with open(args.logfile, "w") as f:
        f.write(out)

    transcript = []
    for line in out.splitlines():
        m = UART.search(line)
        if m is not None:
            transcript.append(m.group(1).rstrip())

    crash = [l for l in out.splitlines()
             if re.search(r"Unhandled exception|is not defined|Aborted|core dumped", l)]

    print("=== CONSOLE TRANSCRIPT: %s ===" % args.name)
    for t in transcript:
        print(t)
    if crash:
        print("--- CRASH/EXCEPTION (%d) ---" % len(crash))
        for l in crash[:10]:
            print("  " + l.strip())


if __name__ == "__main__":
    main()
