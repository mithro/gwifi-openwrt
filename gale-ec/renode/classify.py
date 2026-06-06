#!/usr/bin/env python3
"""Classify the branches left uncovered by coverage_full.py into auditable categories,
so the irreducible remainder of a 100%-branch-coverage goal is JUSTIFIED per-branch
(not silently dropped). Reads cov_uncovered_{RO,RW}.txt (addr, symbol, reached-state).

Each uncovered branch is binned by its containing function symbol into one of:
  UNREACHABLE_FAULT   panic / exception / hard-fault / assert handlers — taking both
                      directions needs a fault that resets the CPU; the not-taken side
                      is the normal path, so both-in-one-image is structurally excluded.
  AP_DEPENDENT        host-command / LPC / AP-stream / keyboard / charger paths that
                      need the IPQ4019 AP (absent in EC-only emulation).
  HW_CANT_FAIL        EC_ERROR_* returns for modeled hardware that never errors
                      (flash never BSY, SPI slave always responds, I2C ack).
  WATCHDOG_TIMEOUT    watchdog-trip / timeout-expiry guards that never fire deterministically.
  COVERABLE_GAP       reached in some scenario but only one direction seen, and NOT in any
                      excluded category — i.e. a real branch we have not yet driven both
                      ways. These are NOT excusable; they are the work-list to drive down.
  UNREACHED_OTHER     never reached by any scenario and not in an excluded category.

Prints per-category counts and writes the COVERABLE_GAP + UNREACHED_OTHER work-lists so
they can be attacked with more scenarios. The honest 100%-coverage claim is:
  covered / (total - justified_exclusions) == 100%  AND  COVERABLE_GAP == 0.

Usage: uv run python classify.py
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

FAULT = re.compile(r'(panic|exception|hard_?fault|fault_|_fault|assert|software_panic|'
                   r'reboot|watchdog|wdt|hook_critical|cpu_reset|system_reset|jump_to_image|'
                   r'exception_panic|report_panic|hibernate)', re.I)
AP_DEP = re.compile(r'(host_command|hostcmd|host_event|hostevent|lpc|^hc_|_hc_|keyboard|'
                    r'kb_|charge|battery|charger|pmu|motion|als|tablet|backlight|pwm|'
                    r'lid|power_button|chipset|ap_|x86|espi)', re.I)
HW_FAIL = re.compile(r'(flash_|spi_|i2c_|adc_|dma_|_read_|_write_|_xfer|_transfer|crc)', re.I)
WDT = re.compile(r'(watchdog|wdt|timeout|deadline|timer_|hwtimer)', re.I)


def classify(sym, state):
    if FAULT.search(sym):
        return "UNREACHABLE_FAULT"
    if AP_DEP.search(sym):
        return "AP_DEPENDENT"
    if WDT.search(sym):
        return "WATCHDOG_TIMEOUT"
    if HW_FAIL.search(sym):
        return "HW_CANT_FAIL"
    return "COVERABLE_GAP" if state == "reached-one-dir" else "UNREACHED_OTHER"


def main():
    for img in ("RO", "RW"):
        path = os.path.join(HERE, "cov_uncovered_%s.txt" % img)
        if not os.path.exists(path):
            print("%s: %s missing — run coverage_full.py first" % (img, os.path.basename(path)))
            continue
        cats = {}
        gap, other = [], []
        with open(path) as f:
            for ln in f:
                p = ln.split()
                if len(p) < 3:
                    continue
                addr, sym, state = p[0], p[1], p[2]
                c = classify(sym, state)
                cats.setdefault(c, []).append((addr, sym))
                if c == "COVERABLE_GAP":
                    gap.append((addr, sym))
                elif c == "UNREACHED_OTHER":
                    other.append((addr, sym))
        total_uncov = sum(len(v) for v in cats.values())
        print("\n=== %s: %d uncovered branches ===" % (img, total_uncov))
        for c in sorted(cats, key=lambda k: -len(cats[k])):
            print("  %-20s %4d" % (c, len(cats[c])))
        for nm, lst in (("gap", gap), ("other", other)):
            outp = os.path.join(HERE, "tmp", "worklist_%s_%s.txt" % (img, nm))
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            with open(outp, "w") as f:
                for a, s in lst:
                    f.write("%s %s\n" % (a, s))


if __name__ == "__main__":
    main()
