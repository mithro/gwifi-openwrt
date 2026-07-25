#!/usr/bin/env python3
"""Power-sequencing equivalence test (HARDWARE-TEST-PLAN "Power sequencing").

The EC's `gale power on|off ap` drives the AP supply rails (VDD_3P3, VDD_3P3_2G,
VDD_1P35, VDD_1P1_CPU, VDD_1P8, SYS_PWR) via GPIO in a fixed sequence. This boots
each image, toggles AP power on then off, reads back the rail GPIO levels after each,
and verifies the rail vector is identical between the original dump and the rebuilt
ec.bin (a dedicated test rather than a console-section diff, to avoid the async-PD
noise that pollutes the generic battery for slow `gale` commands).
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
UART = re.compile(r"usart1: \[host:[^\]]*\]\s?(.*)$")
RAILS = ["VDD_3P3_EN", "VDD_3P3_2G_EN", "VDD_1P35_EN", "VDD_1P1_CPU_EN",
         "VDD_1P8_EN", "SYS_PWR_EN"]


def run(binpath, name, cmds, boot="0.3", settle="0.15"):
    e = [
        '$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(binpath), '$name="%s"' % name,
        'include @%s' % BASE,
        'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
        'emulation RunFor "%s"' % boot,
    ]
    for c in cmds:
        for ch in (c + "\r"):
            e.append('sysbus.usart1 WriteChar %d' % ord(ch))
        e.append('emulation RunFor "%s"' % settle)
    e.append('quit')
    p = subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(e)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, timeout=600)
    out = ANSI.sub("", p.stdout)
    return [m.group(1).rstrip() for m in (UART.search(l) for l in out.splitlines()) if m]


def rail_vector_after(lines, marker_index_from_end=0):
    """Return {rail: level} from the LAST gpioget block in the transcript."""
    vec = {}
    for l in lines:
        m = re.match(r"\s*([01])\*?\s+(\w+)\s*$", l)
        if m and m.group(2) in RAILS:
            vec[m.group(2)] = m.group(1)  # last occurrence wins (latest gpioget)
    return vec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True)
    ap.add_argument("--rebuilt", required=True)
    args = ap.parse_args()

    results = {}
    for label, b in (("orig", args.orig), ("rebuilt", args.rebuilt)):
        on = rail_vector_after(run(b, label, ["gale power on ap", "gpioget"]))
        off = rail_vector_after(run(b, label, ["gale power off ap", "gpioget"]))
        results[label] = (on, off)

    o_on, o_off = results["orig"]
    r_on, r_off = results["rebuilt"]
    print("=== POWER SEQUENCING (rail GPIO vector) ===")
    print("rails: %s" % ", ".join(RAILS))
    print("orig    on : %s" % [o_on.get(x, "?") for x in RAILS])
    print("rebuilt on : %s" % [r_on.get(x, "?") for x in RAILS])
    print("orig    off: %s" % [o_off.get(x, "?") for x in RAILS])
    print("rebuilt off: %s" % [r_off.get(x, "?") for x in RAILS])
    on_ok = o_on == r_on and all(o_on.get(x) == "1" for x in RAILS)
    off_ok = o_off == r_off and all(o_off.get(x) == "0" for x in RAILS)
    ok = on_ok and off_ok
    print("\npower-ON  rails identical & all high: %s" % on_ok)
    print("power-OFF rails identical & all low : %s" % off_ok)
    print("%s power sequencing is %sEQUIVALENT"
          % ("[PASS]" if ok else "[FAIL]", "" if ok else "NOT "))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
