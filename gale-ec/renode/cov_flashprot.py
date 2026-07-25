#!/usr/bin/env python3
"""FLASH-PROTECT-MATRIX + PD-ARG lever. Two bundled clusters:
 (1) flash_set_protect / flash_get_protect mask arms (flash.c:481-528, 410-448): driven by the
     EC_CMD_FLASH_PROTECT (0x15) host command swept across each single-bit MASK subset
     {RO_AT_BOOT=0x01, RO_NOW=0x02, ALL_NOW=0x04, ALL_AT_BOOT=0x40} x flags {0, =mask}, so every
     `if ((mask & BIT) && ...)` guard runs both nonzero and zero. Plus WrpValue partial-protect
     patterns (some groups clear) + reboot + flashinfo/flashwp console for the per-bank
     INCONSISTENT (:436) and RO_NOW/ALL_NOW reconciliation arms.
 (2) command_pd console arg residual (usb_pd_protocol.c:2882-3069): broad `pd ...` variations
     (bad number args -> strtoi leftover, bad port, bad subcmd, dualrole/dump/enable/trysrc/dev arms).
Genuine console + host-command execution. RO + RW. Accumulates tmp/flashprot_edges.pkl.
Usage: uv run --python .venv python cov_flashprot.py [rw]
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


def le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "flashprot.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.15"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data),
                'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trfp" @%s PC' % trace]

    # ---- (1a) FLASH_PROTECT mask matrix. EC_CMD_FLASH_PROTECT=0x15, params {u32 mask, u32 flags}.
    RO_AT_BOOT, RO_NOW, ALL_NOW, ALL_AT_BOOT = 0x01, 0x02, 0x04, 0x40
    masks = [0x00, RO_AT_BOOT, RO_NOW, ALL_NOW, ALL_AT_BOOT,
             RO_AT_BOOT | ALL_AT_BOOT, RO_NOW | ALL_NOW, RO_AT_BOOT | RO_NOW,
             ALL_AT_BOOT | ALL_NOW, 0xFFFFFFFF]
    for m in masks:
        for fl in (0x00000000, m):                     # clear-request and set-request for each mask
            c += hc(0x0015, le32(m) + le32(fl))
        c += cc("flashinfo")                           # flash_get_protect read-back arms each time

    # ---- (1b) WrpValue partial-protect patterns -> per-bank INCONSISTENT (:436) + RO/ALL_NOW arms.
    for wrp in ("0xFFFFFFFE", "0x0000FFFF", "0xFFFF0000", "0xFFFFFFFC", "0x00000000"):
        c += ['sysbus.flashif WrpValue %s' % wrp]
        c += cc("reboot ro", "0.7")
        if RW:
            c += cc("sysjump rw", "0.4")
        c += cc("flashinfo") + cc("flashwp") + cc("flashwp now") + cc("flashwp noboot")
        c += hc(0x0015, le32(0xFFFFFFFF) + le32(RO_NOW))   # RO_NOW request against this WRP state
    c += ['sysbus.flashif WrpValue 0xFFFFFFFF', 'emulation RunFor "0.2"']

    # ---- (2) command_pd console arg residual: bad number args (strtoi leftover != 0), bad port/subcmd,
    # dualrole/dump/enable/trysrc/dev arms with valid + invalid args.
    pdargs = [
        "pd", "pd dualrole", "pd dualrole on", "pd dualrole off", "pd dualrole sink",
        "pd dualrole source", "pd dualrole bogus", "pd dump", "pd dump 0", "pd dump 1",
        "pd dump 2", "pd dump 3", "pd dump xx", "pd dump 2q", "pd enable", "pd enable 0",
        "pd enable 1", "pd enable q", "pd trysrc", "pd trysrc 0", "pd trysrc 1", "pd trysrc z",
        "pd 9 state", "pd x state", "pd 0", "pd 0 zzz", "pd 0 state", "pd 0 dev", "pd 0 dev 20",
        "pd 0 dev xx", "pd 0 info", "pd 0 tx", "pd 0 charger", "pd 0 soft", "pd 0 hard",
        "pd 0 bist_rx", "pd 0 bist_tx", "pd 0 vdm", "pd 0 vdm vers", "pd 0 vdm ping 1", "pd 0 vdm curr",
    ]
    for s in pdargs:
        c += cc(s, "0.1")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "flashprot.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "flashprot_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/flashprot_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
