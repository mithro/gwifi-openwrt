#!/usr/bin/env python3
"""ADC-VALUE-SWEEP lever — drive the emulated non-CC ADC channels (VBUS / CURRENT sense) across their
full 12-bit range via GaleAdc.ForceRaw, so value-THRESHOLD branches that are currently one-direction
(e.g. over-voltage / over-current / charge-present comparisons that never trip because the channel
reads a constant) flip both ways. Genuine execution: the real firmware's periodic ADC-polling tasks +
the `adc` console command read the forced value and take the real branch. Peripheral-state enrichment,
the "build proper emulation" direction. RO + RW. Accumulates tmp/adcsweep_edges.pkl.
Usage: uv run --python .venv python cov_adcsweep.py [rw]
"""
import os
import pickle
import subprocess
import sys

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
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "adcsweep.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "0.05"']

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw") + ['emulation RunFor "0.5"']
    c += ['cpu CreateExecutionTracing "tra" @%s PC' % trace]
    # console commands that read/print ADC + charge/battery/power state (consume the forced value)
    adc_cmds = ["adc", "charger", "battery", "powerinfo", "chgstate", "temps", "ec_int",
                "pwr", "chg", "power", "chargestate"]
    # sweep VBUS/CURRENT raw across the 12-bit range incl. boundary values; run periodic tasks each time
    for raw in (0, 1, 0x040, 0x100, 0x320, 0x400, 0x640, 0x800, 0x960, 0xC00, 0xE00, 0xFFE, 0xFFF):
        c += ['sysbus.adc ForceRaw %d' % raw, 'emulation RunFor "0.25"']   # periodic ADC pollers see it
        for cmd in adc_cmds:
            c += cc(cmd)
    c += ['sysbus.adc ForceRaw -1', 'cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "adcsweep.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "adcsweep_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/adcsweep_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
