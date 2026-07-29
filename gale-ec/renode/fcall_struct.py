"""Targeted coverage of struct-context parsers (e.g. 0x8007a60: handler(ctx) where ctx has a data
pointer at +8 and a length at +12; it reads byte[3], a 32-bit field at bytes[4..7], bounds-checks).
These stay UNREACHED because the generic fuzzer passes garbage r0 (not a valid ctx). We build a real
ctx struct in RAM pointing at a data buffer, and vary the data + length to walk the parser branches.

Also drives event-type handlers (0x8013c00: handler(event) switching on r0 in {10,13,27,...}) with
r0 swept 0..40.

Pure-ish w.r.t. the crafted inputs; accumulates tmp/struct_edges.pkl. crash-cap + checkpoint + 0.5s.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

CTX = 0x20002400          # the context struct
DATA = 0x20002600         # data buffer the ctx points at

# struct-context parsers (ctx at +8 = data ptr, +12 = len): 0x8007a60 + RW mirror
STRUCT_FNS = [0x08007a60, 0x08017a60]
# event-type handlers swept on r0: 0x8013c00 + RW mirror
EVENT_FNS = [0x08013c00, 0x08003c00, 0x08017a60 - 0, 0x08013c00 + 0x10000, 0x08003c00 + 0x10000]

# State gate inside 0x8007a60: a signed byte at GATE must be <= 0 to enter the body (it exits early
# otherwise). We pre-write it before each call. (Found by disassembly: ldrsb [global+72]; ble.)
GATE = 0x20001198

# data-buffer payloads: byte[2] must be <=3; bytes[4..7] = the VDM header (SVID in bits[31:16]).
# The function references SVID 0x18d1 (Google), so it's a VDM handler -> craft Google-SVID VDMs.
def payloads():
    # 0x8007a60 is a VDM handler: bytes[4..7] = VDM header (SVID bits[31:16], structured bit15,
    # command-type bits[7:6], command bits[4:0]). Sweep the full field space (with the gate satisfied)
    # so the in-body command/type dispatch branches flip both ways. byte[2] (<=3) = object count.
    out = []
    for svid in (0x18d1, 0xff00, 0x1234):
        for sbit in (1, 0):                  # structured / unstructured
            for ctype in (0, 1, 2, 3):       # REQ / ACK / NAK / BUSY
                for cmd in (0, 1, 2, 3, 4, 5, 6, 7, 15, 16):
                    f32 = (svid << 16) | (sbit << 15) | (ctype << 6) | cmd
                    buf = bytearray(64)
                    buf[2] = 2               # object count (<=3)
                    buf[3] = 0
                    struct.pack_into("<I", buf, 4, f32 & 0xFFFFFFFF)
                    struct.pack_into("<I", buf, 8, f32 & 0xFFFFFFFF)
                    out.append(bytes(buf))
    return out

LENGTHS = [16, 64]            # enough to pass the bounds check for the 2 VDOs; length isn't the
                              # dispatch variable for the VDM command/type branches.


def fold(trace, executed, edges):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if len(ln) < 4 or not ln.startswith("0x"):
                prev = None; continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None; continue
            executed.add(pc)
            if prev is not None:
                edges.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "struct_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("fresh (%s)" % e)
    trace = os.path.join(TMP, "struct.txt")
    if os.path.exists(trace):
        os.remove(trace)

    s = [fcall.Session(binp, boot="1.5", trace=trace)]
    def reboot():
        s[0].close(); fold(trace, executed, edges)
        s[0] = fcall.Session(binp, boot="1.5", trace=trace)
    def ckpt():
        with open(out, "wb") as f:
            pickle.dump((executed, edges), f)

    pays = payloads()
    for fn in STRUCT_FNS:
        if not ((0x08000000 <= fn < 0x0800b744) or (0x08010000 <= fn < 0x0801b744)):
            continue
        crashes = 0
        for pay in pays:
            for ln in LENGTHS:
                if crashes >= 4:
                    break
                try:
                    s[0].rsp.writemem(DATA, pay)
                    s[0].rsp.writemem(GATE, b"\x00")            # satisfy the state gate (<=0)
                    ctx = bytearray(32)
                    struct.pack_into("<I", ctx, 8, DATA)        # ctx+8 = data ptr
                    struct.pack_into("<H", ctx, 12, ln & 0xFFFF)  # ctx+12 = length
                    s[0].rsp.writemem(CTX, bytes(ctx))
                    s[0].rsp.call(fn, (CTX, 0, 0, 0), timeout_continue=0.5)
                    crashes = 0
                except Exception:
                    crashes += 1; reboot()
        ckpt(); print("  struct-swept 0x%08x" % fn)

    # 0x8013c00/0x8003c00 branch on r0 (event) AND a global flag at 0x20000cd8 ([r4,#76]); toggling
    # the flag both ways while sweeping the event flips the flag-dependent branches both directions.
    EVENT_FLAG = 0x20000cd8
    for fn in sorted(set(EVENT_FNS)):
        if not ((0x08000000 <= fn < 0x0800b744) or (0x08010000 <= fn < 0x0801b744)):
            continue
        crashes = 0
        for ev in range(0, 41):
            if crashes >= 4:
                break
            for flag in (0, 1):
                try:
                    s[0].rsp.writemem(EVENT_FLAG, bytes([flag, 0, 0, 0]))
                    s[0].rsp.call(fn, (ev, 0, 0, 0), timeout_continue=0.5)
                    crashes = 0
                except Exception:
                    crashes += 1; reboot()
        ckpt(); print("  event-swept 0x%08x" % fn)

    s[0].close(); fold(trace, executed, edges); ckpt()
    print("saved %d edges, %d PCs -> tmp/struct_edges.pkl" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
