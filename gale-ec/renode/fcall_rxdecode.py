#!/usr/bin/env python3
"""Direct-call pd_analyze_rx (the PHY RX decoder, RO 0x08009eb0 / RW 0x08019eb0) with crafted BMC
sample streams pre-loaded into pd_phy[0].raw_samples (captured @0x20000790) — bypassing the partner/
COMP timing entirely. Each variant exercises a decode arm: valid msg, bad CRC (pcrc!=ccrc), truncated
(eop!=PD_EOP / bit<0), SOP'/SOP'' (val==PD_SOP_PRIME...), HARD-RESET/CABLE-RESET ordered sets
(PD_RX_ERR_HARD_RESET/CABLE_RESET), multi-object data. Accumulates tmp/rxdec_edges.pkl."""
import os
import pickle

import fcall
import pd_encode as pe

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
RAW = 0x20000790          # captured pd_phy[0].raw_samples
PAYLOAD = 0x20002400      # where pd_analyze_rx writes decoded objects
ANALYZE = (0x08009eb0, 0x08019eb0)
SYNC1, SYNC2, SYNC3, RST1, RST2, EOP = 0x18, 0x11, 0x06, 0x07, 0x19, 0x0D


def samples(sop_syms, header=None, objs=(), crc=None, eop=True):
    tx = pe.TxBits()
    tx.preamble()
    for sym in sop_syms:
        tx.sym(pe.BMC(sym))
    if header is not None:
        tx.encode_short(header)
        for o in objs:
            tx.encode_word(o)
        tx.encode_word(pe.crc32_pd(header, objs) if crc is None else crc)
    if eop:
        tx.sym(pe.BMC(EOP))
    tx.last_edge()
    return pe.levels_to_samples(tx.level_bits())


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
    out = os.path.join(TMP, "rxdec_edges.pkl")
    ex, ed = set(), set()
    if os.path.exists(out):
        try:
            pe2, pd2 = pickle.load(open(out, "rb")); ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    trace = os.path.join(TMP, "rxdec.txt")
    if os.path.exists(trace):
        os.remove(trace)
    SOP = [SYNC1, SYNC1, SYNC1, SYNC2]
    hdr = pe.header(1, 0, 0)
    variants = [
        samples(SOP, hdr),                                  # valid control msg
        samples(SOP, pe.header(2, 1, 0), objs=[0x12345678]),    # valid 1-object data
        samples(SOP, pe.header(2, 7, 0), objs=[0] * 7),     # 7 objects
        samples(SOP, hdr, crc=0xDEADBEEF),                  # bad CRC
        samples(SOP, hdr, eop=False),                       # no EOP
        samples([SYNC1, SYNC1, SYNC3, SYNC3], hdr),         # SOP'
        samples([SYNC1, RST2, RST2, SYNC3], hdr),           # SOP''
        samples([RST1, RST1, RST1, RST2]),                  # HARD RESET
        samples([RST1, SYNC1, RST1, SYNC3]),                # CABLE RESET
        bytes([0, 0, 0, 0]),                                # no preamble -> err
        bytes(range(0, 60)),                                # garbage
    ]
    s = [fcall.Session(binp, boot="1.5", trace=trace)]

    def reboot():
        s[0].close(); fold(trace, ex, ed); s[0] = fcall.Session(binp, boot="1.5", trace=trace)

    for fn in ANALYZE:
        for sm in variants:
            try:
                buf = sm[:0x80].ljust(0x80, b"\x00")
                s[0].rsp.writemem(RAW, buf)
                s[0].rsp.call(fn, (0, PAYLOAD, 0, 0), timeout_continue=1)
            except Exception:
                reboot()
    s[0].close(); fold(trace, ex, ed)
    pickle.dump((ex, ed), open(out, "wb"))
    print("saved -> tmp/rxdec_edges.pkl: %d edges, %d PCs" % (len(ed), len(ex)))


if __name__ == "__main__":
    main()
