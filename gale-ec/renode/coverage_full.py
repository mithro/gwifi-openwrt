#!/usr/bin/env python3
"""CUMULATIVE branch-coverage campaign for the gale EC firmware under Renode.

Branch coverage is the UNION over many test scenarios: a conditional branch counts as
fully covered when its taken direction is seen in SOME scenario and its not-taken
direction in SOME (possibly different) scenario. A single boot only walks one path
through each defensive branch; driving both directions needs varied inputs AND
deliberate fault injection (the `crash` command, flash/SPI error injection, etc.).

This harness runs a battery of scenarios on BOTH images (RO and, via `sysjump rw`, RW),
captures a PC execution trace per scenario, and unions:
  * executed instructions  (instruction coverage)
  * per-branch taken / not-taken directions  (branch coverage, both-directions)
across all scenarios, then reports cumulative coverage per image.

It also writes the per-image set of branches still uncovered (addr + containing symbol)
to cov_uncovered_{RO,RW}.txt for the exclusion-justification analysis (classify.py).

Usage: uv run python coverage_full.py [--boot 1.5]
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
TC = "/home/tim/local/gwifi/ec-rebuild/gcc-arm-none-eabi-5_4-2016q3/bin"
OBJDUMP = os.path.join(TC, "arm-none-eabi-objdump")
RW_ELF = "/home/tim/local/gwifi/ec-rebuild/ec/build/gale/RW/ec.RW.elf"
RO_ELF = "/home/tim/local/gwifi/ec-rebuild/ec/build/gale/RO/ec.RO.elf"
REBUILT = os.path.join(HERE, "ec-rebuilt.bin")
TMP = os.path.join(HERE, "tmp")

COND = re.compile(r'\b(b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)|cbz|cbnz)(\.[nw])?\b')

# Read-only console commands safe to run in either image.
RO_CMDS = ["version", "sysinfo", "gettime", "taskinfo", "timerinfo", "gpioget", "adc",
           "panicinfo", "chan", "flashinfo", "shmem", "history", "hcdebug", "hostevent",
           "pd 0 state", "pd 0 srccaps", "pd dump", "tcpc", "typec", "syslock",
           "gpioget LID_OPEN", "md 0x20000000", "waitms 1"]
# Deliberate fault / state-changing commands (drive defensive + handler branches).
CRASH_CMDS = ["crash unaligned", "crash divzero", "crash udf", "crash assert", "crash watchdog"]


def scenarios(boot):
    """List of (name, monitor-prelude-cmds, console-cmds). All run on ec-rebuilt.bin."""
    s = []
    s.append(("ro_readonly", [], RO_CMDS))
    s.append(("rw_readonly", [], ["sysjump rw"] + RO_CMDS))
    # debug accessory: brings up SRC_ACCESSORY -> ccd_set_mode -> usb_init -> usb_spi
    s.append(("ccd_usb", ['sysbus.adc CcPullAddress 0x20001107'],
              ["spixfer rlen 0 0x1f 3", "spixfer 500 0x9f", "pd 0 state", "typec"]))
    s.append(("ccd_usb_rw", ['sysbus.adc CcPullAddress 0x20001107'],
              ["sysjump rw", "spixfer rlen 0 0x1f 3", "pd 0 state"]))
    # SPI flash exercise (raiden target) — multiple lengths/offsets
    s.append(("spi", [], ["spixfer rlen 0 0x9f 3", "spixfer rlen 0 0x03000000 8",
                          "spixfer 2000 0x9f", "flashinfo"]))
    # write-protect / lock state machine
    s.append(("wp", [], ["flashwp", "flashwp enable", "flashwp now", "syslock", "flashinfo"]))
    # PD subcommands across ports/roles
    s.append(("pd", [], ["pd 0 dualrole", "pd 0 dualrole sink", "pd 0 dualrole source",
                         "pd 0 dualrole toggle-off", "pd 0 dualrole freeze", "pd 0 state",
                         "pd 0 tx", "pd dump 4", "tcpc", "typec"]))
    # deliberate crashes -> fault/panic/assert/hardfault handlers (RO)
    for c in CRASH_CMDS:
        s.append(("crash_ro_%s" % c.split()[1], [], [c]))
    # deliberate crashes in RW
    for c in CRASH_CMDS:
        s.append(("crash_rw_%s" % c.split()[1], [], ["sysjump rw", c]))
    # reboot/hibernate handler paths
    s.append(("reboot", [], ["reboot hard", "version"]))
    s.append(("hibernate", [], ["hibernate 1", "version"]))
    s.append(("gale", [], ["gale", "gale power on ap", "gale power off ap"]))
    return [(n, m, cc, boot) for (n, m, cc) in s]


def disasm_branches(elf):
    out = subprocess.run([OBJDUMP, "-d", elf], stdout=subprocess.PIPE,
                         universal_newlines=True).stdout
    insns, cond, sym = {}, {}, {}
    cur = "?"
    for ln in out.splitlines():
        fm = re.match(r'^[0-9a-f]+\s+<([^>]+)>:', ln)
        if fm:
            cur = fm.group(1); continue
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f ]+?)\s+(\S.*)$', ln)
        if not m:
            continue
        addr = int(m.group(1), 16)
        nb = len(m.group(2).replace(" ", "")) // 2
        insns[addr] = nb
        sym[addr] = cur
        cm = COND.search(m.group(3))
        if cm:
            tm = re.search(r'([0-9a-f]+)\s+<', m.group(3))
            if tm:
                cond[addr] = (addr + nb, int(tm.group(1), 16))
    return set(insns), cond, sym


def run_scenario(name, mon, cmds, boot):
    trace = os.path.join(TMP, "cov_%s.txt" % name)
    c = ['$h=@%s' % HERE, '$bin=@%s' % REBUILT, '$name="cov"', 'include @%s' % BASE] + mon
    c += ['cpu CreateExecutionTracing "tr_%s" @%s PC' % (name, trace),
          'emulation RunFor "%s"' % boot]
    for cmd in cmds:
        c += ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (cmd + "\r")]
        c.append('emulation RunFor "0.08"')
    c += ['cpu DisableExecutionTracing', 'quit']
    subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(c)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)
    return trace


def fold_trace(path, cond, executed, taken, nottaken):
    """Stream a trace file; update executed set + per-branch taken/nottaken sets."""
    prev = None
    if not os.path.exists(path):
        return
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None; continue
            pc = int(ln, 16)
            executed.add(pc)
            if prev is not None and prev in cond:
                fall, tgt = cond[prev]
                if pc == tgt:
                    taken.add(prev)
                elif pc == fall:
                    nottaken.add(prev)
            prev = pc
    os.remove(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", default="1.5")
    args = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)

    scns = scenarios(args.boot)
    print("Running %d scenarios (each a separate traced renode run)..." % len(scns))
    traces = []
    for name, mon, cmds, boot in scns:
        print("  scenario: %-18s (%d cmds)" % (name, len(cmds)))
        traces.append((name, run_scenario(name, mon, cmds, boot)))

    executed, taken, nottaken = set(), set(), set()
    for name, elf in []:  # placeholder
        pass
    # We need cond maps per image, but executed/taken/nottaken are address sets shared
    # across images (RO 0x0800xxxx vs RW 0x0801xxxx don't overlap), so fold once with the
    # union of both cond maps.
    ro_insn, ro_cond, ro_sym = disasm_branches(RO_ELF)
    rw_insn, rw_cond, rw_sym = disasm_branches(RW_ELF)
    allcond = dict(ro_cond); allcond.update(rw_cond)
    for name, path in traces:
        fold_trace(path, allcond, executed, taken, nottaken)

    for label, all_insn, cond, sym, elf in [("RO", ro_insn, ro_cond, ro_sym, RO_ELF),
                                             ("RW", rw_insn, rw_cond, rw_sym, RW_ELF)]:
        ex = executed & all_insn
        icov = 100.0 * len(ex) / max(len(all_insn), 1)
        reached = [a for a in cond if a in executed]
        both = [a for a in cond if a in taken and a in nottaken]
        only = [a for a in reached if a not in (set(taken) & set(nottaken))]
        bcov_tot = 100.0 * len(both) / max(len(cond), 1)
        bcov_reached = 100.0 * len(both) / max(len(reached), 1)
        print("\n=== %s image (cumulative over %d scenarios) ===" % (label, len(scns)))
        print("  instructions:  %d/%d = %.1f%%" % (len(ex), len(all_insn), icov))
        print("  cond branches: %d total, %d reached, %d both-dirs covered" %
              (len(cond), len(reached), len(both)))
        print("  branch coverage: %.1f%% of total, %.1f%% of reached" % (bcov_tot, bcov_reached))
        # dump uncovered (not both-dirs) branches with containing symbol for classify.py
        uncov = sorted(a for a in cond if a not in both)
        outp = os.path.join(HERE, "cov_uncovered_%s.txt" % label)
        with open(outp, "w") as f:
            for a in uncov:
                state = ("reached-one-dir" if a in executed else "unreached")
                f.write("0x%08x %-30s %s\n" % (a, sym.get(a, "?"), state))
        print("  wrote %d uncovered branches -> %s" % (len(uncov), os.path.basename(outp)))


if __name__ == "__main__":
    main()
