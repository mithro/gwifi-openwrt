#!/usr/bin/env python3
"""HOST-COMMAND-MATRIX lever — driven by UNCOVERED-BY-FUNCTION.md host_command_* branches that the
existing hostcmd scenarios miss: EC_CMD_REBOOT(0xd1) dispatch, the repeat-detection arm (same command
twice quickly -> args->command==hc_prev_cmd), GET_CMD_VERSIONS version 1 (the v1 struct path) with a
found AND not-found command code, and commands that return a non-zero result. Genuine host-command
execution via the real I2C protocol-v3 framing. RO + RW. Accumulates tmp/hcargs_edges.pkl.
Usage: uv run --python .venv python cov_hcargs.py [rw]
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
    trace = os.path.join(TMP, "hcargs.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.04"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, ver, sver, dlen, data, bad=False, t="0.05"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, ver, sver, dlen, data, bad),
                'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trhc" @%s PC' % trace]

    # repeat-detection arm: same command twice with NO gap (hc_prev_cmd match within HCDEBUG_MAX_REPEAT_DELAY)
    for _ in range(3):
        c += hc(0x0001, 0, 3, 4, [0x44, 0x33, 0x22, 0x11], t="0.005")   # HELLO x3 back-to-back
    # enable hcdebug so the repeat/print arms run, then repeat again
    c += cc("hcdebug on")
    for _ in range(2):
        c += hc(0x0001, 0, 3, 4, [0x44, 0x33, 0x22, 0x11], t="0.005")
    c += cc("hcdebug normal")
    # EC_CMD_REBOOT (0xd1) dispatch arm
    c += hc(0x00d1, 0, 3, 0, [])
    # GET_CMD_VERSIONS version 1 (v1 struct = u16 cmd): found (0x01) AND not-found (0xff00)
    c += hc(0x0008, 1, 3, 2, [0x01, 0x00])
    c += hc(0x0008, 1, 3, 2, [0x00, 0xff])
    c += hc(0x0008, 0, 3, 1, [0x01])                          # version 0 path (u8 cmd)
    c += hc(0x0008, 0, 3, 1, [0xff])                          # version 0 not-found
    # commands that produce a non-zero result (error) -> args->result != 0 arm
    c += hc(0x0103, 0, 3, 1, [9])                             # USB_PD_POWER_INFO bad port -> error
    c += hc(0x0101, 0, 3, 4, [9, 0, 0, 0])                    # USB_PD_CONTROL bad port -> error
    c += hc(0x0011, 0, 3, 8, [0]*8)                           # FLASH_READ zero -> ok/edge
    c += hc(0x0012, 0, 3, 4, [0, 0, 0, 0])                    # FLASH_WRITE truncated -> error
    # a spread of valid command codes to drive the lookup loop both ways (found early/late/miss)
    for cmd in (0x02, 0x03, 0x04, 0x06, 0x0b, 0x0d, 0x67, 0x97, 0x98, 0x7f, 0xb0, 0x00aa):
        c += hc(cmd, 0, 3, 0, [], t="0.03")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "hcargs.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "hcargs_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/hcargs_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
