"""GPIO-GET-V1 lever — drives EC_CMD_GPIO_GET (0x93) VERSION 1 to cover gpio_command_get's v1 arms
(gpio_commands.c): :215 version!=0 (v1), :228 switch(subcmd) cases 0(BY_NAME)/1(COUNT)/2(GET_INFO),
:220 name-not-found (i==GPIO_COUNT) for a bogus name, :242 get_info.index >= GPIO_COUNT (out of range).
The campaign only exercised v0; the v1 subcmd dispatch was unreached. Genuine host-command execution.
RO + RW. Usage: uv run --python .venv python cov_gpioget.py [rw]
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


def name32(s):
    b = s.encode()[:31]
    return list(b) + [0] * (32 - len(b))


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "gpioget.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, ver, data, t="0.15"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, ver, 3, len(data), data),
                'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trgg" @%s PC' % trace]

    G = 0x93
    # v0 (covered baseline): get by name
    c += hc(G, 0, name32("WP_L"))
    # v1 subcmd=0 GET_BY_NAME: valid name (found) + bogus name (i == GPIO_COUNT, :220)
    c += hc(G, 1, [0] + name32("WP_L"))
    c += hc(G, 1, [0] + name32("EC_INT_L"))
    c += hc(G, 1, [0] + name32("NONEXISTENT_PIN_XYZ"))
    c += hc(G, 1, [0] + name32(""))
    # v1 subcmd=1 GET_COUNT
    c += hc(G, 1, [1])
    c += hc(G, 1, [1, 0, 0, 0])
    # v1 subcmd=2 GET_INFO: valid index + out-of-range index (>= GPIO_COUNT=0x1d, :242)
    c += hc(G, 1, [2, 0])
    c += hc(G, 1, [2, 5])
    c += hc(G, 1, [2, 28])
    c += hc(G, 1, [2, 99])
    c += hc(G, 1, [2, 0xFF])
    # v1 bad subcmd (default case)
    c += hc(G, 1, [3])
    c += hc(G, 1, [9, 0])

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "gpioget.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "gpioget_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/gpioget_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
