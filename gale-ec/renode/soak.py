#!/usr/bin/env python3
"""Soak / stability equivalence test (HARDWARE-TEST-PLAN "Stability").

Runs each image for an extended virtual-time soak, then checks the EC is still alive
and clean: `panicinfo` reports no panic and `version` still responds. Verifies both the
original dump and the rebuilt ec.bin survive the soak with identical (panic-free)
status — i.e. neither crashes/hangs over extended operation.
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
UART = re.compile(r"usart1: \[host:[^\]]*\]\s?(.*)$")


def soak(binpath, name, seconds):
    e = [
        '$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(binpath), '$name="%s"' % name,
        'include @%s' % BASE,
        'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
        'emulation RunFor "0.3"',               # boot
        'emulation RunFor "%s"' % seconds,       # soak
    ]
    for c in ("panicinfo", "version"):
        for ch in (c + "\r"):
            e.append('sysbus.usart1 WriteChar %d' % ord(ch))
        e.append('emulation RunFor "0.08"')
    e += ['cpu IsHalted', 'quit']
    p = subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(e)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, timeout=900)
    out = ANSI.sub("", p.stdout)
    lines = [m.group(1).rstrip() for m in (UART.search(l) for l in out.splitlines()) if m]
    text = "\n".join(lines)
    alive = "Chip:" in text and "stm32f07x" in text       # version responded post-soak
    # panic-free: the EC prints "No saved panic data" (or similar) when clean
    panic_clean = bool(re.search(r"[Nn]o (saved )?panic", text))
    crash = bool(re.search(r"Unhandled exception|is not defined|core dumped", out))
    halted = any(l.strip() == "True" for l in out.splitlines()[-6:])
    return alive, panic_clean, crash, halted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True)
    ap.add_argument("--rebuilt", required=True)
    ap.add_argument("--seconds", default="2.0", help="virtual soak seconds")
    args = ap.parse_args()

    print("=== SOAK / STABILITY (%s s virtual) ===" % args.seconds)
    res = {}
    for label, b in (("orig", args.orig), ("rebuilt", args.rebuilt)):
        alive, clean, crash, halted = soak(b, label, args.seconds)
        res[label] = (alive, clean, crash, halted)
        print("%-8s alive=%s panic_clean=%s crash=%s halted=%s"
              % (label, alive, clean, crash, halted))
    ok = all(alive and clean and not crash and not halted
             for (alive, clean, crash, halted) in res.values())
    same = res["orig"][:3] == res["rebuilt"][:3]
    print("\n%s soak: both stable (alive, panic-free, no crash/halt) and identical: %s"
          % ("[PASS]" if (ok and same) else "[FAIL]", ok and same))
    raise SystemExit(0 if (ok and same) else 1)


if __name__ == "__main__":
    main()
