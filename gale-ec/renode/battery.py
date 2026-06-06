#!/usr/bin/env python3
"""gale EC equivalence test battery + trace-diff harness.

Runs the command-driven HARDWARE-TEST-PLAN tests on BOTH the original device dump
and the rebuilt ec.bin in Renode, captures each command's console output, applies
an explicit/documented immaterial-delta normalization, and reports per-test
PASS (byte-identical after normalization) / FAIL (with the diff).

Each command is delimited in the transcript by sending a unique invalid marker
command ("MKnn") before it; the EC's "Command 'MKnn' not found" reply is an
unambiguous section boundary.

Immaterial deltas that ARE normalized (and why):
  * version/build banner — the two images are different builds (gale_v1.1.5337 vs
    gale_v0.0.1); documented expected delta.
  * RW image hash — the RW binaries differ, so their SHA differs; documented.
  * async log timestamps "[D.DDDDDD ...]" and uptime/Time(s) columns — wall-clock
    /scheduling dependent, inherently non-deterministic across builds.
Anything else that differs is reported as FAIL — including genuine config deltas
(e.g. CONFIG_TASK_PROFILING, flash pstate), which must be fixed in the
reconstruction, not normalized away.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
UART = re.compile(r"usart1: \[host:[^\]]*\]\s?(.*)$")

# Safe, read-only, command-driven tests from ../HARDWARE-TEST-PLAN.md.
# (Power-sequencing / raiden / USB-PD need USB-FS + W25Q64 + PD-PHY models and
# are added once those land.)
COMMANDS = [
    "version", "sysinfo", "taskinfo", "gpioget", "flashinfo",
    "chan", "panicinfo", "adc", "gettime",
]


def run_image(binpath, name, boot="0.2", settle="0.04"):
    cmds = [
        '$h=@%s' % HERE,
        '$bin=@%s' % os.path.abspath(binpath),
        '$name="%s"' % name,
        'include @%s' % BASE,
        'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
        'emulation RunFor "%s"' % boot,
    ]
    for k, c in enumerate(COMMANDS):
        for ch in ("MK%02d\r" % k):
            cmds.append('sysbus.usart1 WriteChar %d' % ord(ch))
        cmds.append('emulation RunFor "0.01"')
        for ch in (c + "\r"):
            cmds.append('sysbus.usart1 WriteChar %d' % ord(ch))
        cmds.append('emulation RunFor "%s"' % settle)
    cmds.append('quit')

    proc = subprocess.run(
        ["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, timeout=900,
    )
    out = ANSI.sub("", proc.stdout)
    lines = []
    for line in out.splitlines():
        m = UART.search(line)
        if m is not None:
            lines.append(m.group(1).rstrip())
    crash = any(re.search(r"Unhandled exception|is not defined|core dumped", l)
                for l in out.splitlines())
    return lines, crash


def split_sections(lines):
    """Return {command: [output lines]} using the MKnn markers as boundaries."""
    sections = {}
    idx = []  # (k, line_index_of_marker_reply)
    marker = re.compile(r"Command '?MK(\d\d)'? not found", re.I)
    for i, l in enumerate(lines):
        m = marker.search(l)
        if m is not None:
            idx.append((int(m.group(1)), i))
    for n, (k, start) in enumerate(idx):
        end = idx[n + 1][1] if n + 1 < len(idx) else len(lines)
        body = lines[start + 1:end]
        # strip the echoed command line itself (first line equal to the command)
        cmd = COMMANDS[k]
        body = [b for b in body if b.strip().lstrip("> ").strip() != cmd]
        sections[cmd] = body
    return sections


def normalize(lines):
    out = []
    for l in lines:
        s = l
        # async log timestamp prefix: "[0.000046 ...]" -> "[T ...]"
        s = re.sub(r"\[\d+\.\d+ ", "[T ", s)
        # version / build banner
        s = re.sub(r"gale_v\S+", "gale_vX", s)
        s = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+", "DATE HOST", s)
        # RW image hash
        s = re.sub(r"hash (start|done)[ 0-9a-fx]+", r"hash \1 NORM", s)
        # bare uptime / Time(s) decimal columns
        s = re.sub(r"\b\d+\.\d{6}\b", "TIME", s)
        # drop trailing whitespace; skip pure async prompt noise
        s = s.rstrip()
        if s in (">", ""):
            continue
        out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True, help="original device dump")
    ap.add_argument("--rebuilt", required=True, help="rebuilt ec.bin")
    ap.add_argument("--outdir", default=os.path.join(HERE, "transcripts"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    print("Running battery on ORIGINAL ...", file=sys.stderr)
    o_lines, o_crash = run_image(args.orig, "orig")
    print("Running battery on REBUILT ...", file=sys.stderr)
    r_lines, r_crash = run_image(args.rebuilt, "rebuilt")

    o_sec = split_sections(o_lines)
    r_sec = split_sections(r_lines)

    n_pass = n_fail = 0
    report = []
    for c in COMMANDS:
        o = normalize(o_sec.get(c, []))
        r = normalize(r_sec.get(c, []))
        if not o and not r:
            verdict = "MISSING"
        elif o == r:
            verdict = "PASS"
            n_pass += 1
        else:
            verdict = "FAIL"
            n_fail += 1
        report.append((c, verdict, o, r))

    with open(os.path.join(args.outdir, "report.txt"), "w") as f:
        for c, v, o, r in report:
            line = "[%s] %s" % (v, c)
            print(line)
            f.write(line + "\n")
            if v == "FAIL":
                import difflib
                for d in difflib.unified_diff(o, r, "orig/" + c, "rebuilt/" + c, lineterm=""):
                    print("    " + d)
                    f.write("    " + d + "\n")
    print("\n%d PASS, %d FAIL (crash: orig=%s rebuilt=%s)"
          % (n_pass, n_fail, o_crash, r_crash))
    sys.exit(1 if (n_fail or o_crash or r_crash) else 0)


if __name__ == "__main__":
    main()
