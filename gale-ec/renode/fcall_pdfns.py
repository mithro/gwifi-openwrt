#!/usr/bin/env python3
"""Direct-call the direct-callable PD helper functions with crafted args (the reliable pure-ish
lever): pd_custom_vdm(port, cnt, payload*, rpayload**) decodes a VDO (bits[4:0]=cmd) and tcpc_run(
port, evt) dispatches a PD-task event bitmask. Sweep VDO commands + event bits so their dispatch
arms flip. Accumulates tmp/pdfns_edges.pkl (unioned by combine_coverage.py)."""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
PAY = 0x20002000      # payload buffer (VDOs)
RPP = 0x20002100      # rpayload pointer storage
SCRATCH = 0x20002200

PD_CUSTOM_VDM = (0x08000720, 0x08010720)
TCPC_RUN = (0x0800a05c, 0x0801a05c)


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    for ln in open(trace):
        ln = ln.strip()
        if len(ln) < 4 or not ln.startswith("0x"):
            prev = None; continue
        try:
            pc = int(ln, 16)
        except ValueError:
            prev = None; continue
        ex.add(pc)
        if prev is not None:
            ed.add((prev, pc))
        prev = pc
    os.remove(trace)


def main():
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "pdfns_edges.pkl")
    ex, ed = set(), set()
    if os.path.exists(out):
        try:
            pe, pd = pickle.load(open(out, "rb")); ex |= set(pe); ed |= set(pd)
        except Exception:
            pass
    trace = os.path.join(TMP, "pdfns.txt")
    if os.path.exists(trace):
        os.remove(trace)
    s = [fcall.Session(binp, boot="1.5", trace=trace)]

    def reboot():
        s[0].close(); fold(trace, ex, ed); s[0] = fcall.Session(binp, boot="1.5", trace=trace)

    # pd_custom_vdm(port=0, cnt=1, payload*, rpayload**): VDO with each command 0..31 + struct/svid bits
    for fn in PD_CUSTOM_VDM:
        for cmd in range(0, 32):
            for hdr in (0xFF008000, 0xFF008040, 0x12340000, 0x00000000, 0xFF018000):
                vdo = (hdr & ~0x1f) | cmd
                try:
                    s[0].rsp.writemem(PAY, struct.pack("<2I", vdo, 0x12345678))
                    s[0].rsp.writemem(RPP, struct.pack("<I", SCRATCH))
                    s[0].rsp.call(fn, (0, 1, PAY, RPP), timeout_continue=1)
                except Exception:
                    reboot()
    # tcpc_run(port=0, evt): event bitmask (PD_EVENT_* bits) — sweep single + combined bits
    for fn in TCPC_RUN:
        for evt in (0, 1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80, 0x100, 0x200, 0x800,
                    0x1000, 0x2000, 0x80000000, 0xFFFFFFFF, 0x202, 0x880):
            try:
                s[0].rsp.call(fn, (0, evt, 0, 0), timeout_continue=1)
            except Exception:
                reboot()
    s[0].close(); fold(trace, ex, ed)
    pickle.dump((ex, ed), open(out, "wb"))
    print("saved -> tmp/pdfns_edges.pkl: %d edges, %d PCs" % (len(ed), len(ex)))


if __name__ == "__main__":
    main()
