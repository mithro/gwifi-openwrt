#!/usr/bin/env python3
"""PHY-LEVEL RX-DECODE fault lever — targets pd_analyze_rx (0x08009eb0, ~27 uncovered) per
UNCOVERED-BY-FUNCTION.md: the SOP'/SOP'' framing arms (val==PD_SOP_PRIME), HARD_RESET/CABLE_RESET
ordered-set arms, the CRC-mismatch arm (pcrc != ccrc), and the bad-EOP arm (eop != PD_EOP). These
need malformed WIRE-FORMAT messages, crafted with pd_encode's PHY primitives (TxBits/BMC/K-codes),
delivered to a receiving gale so the real decoder takes the error/variant branch. Genuine execution.
RO + RW. Accumulates tmp/rxdecode2_edges.pkl.
Usage: uv run --python .venv python cov_rxdecode2.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C
import pd_encode as pe

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")

# USB-PD 5-bit K-codes (usb_pd_tcpc.c): the ordered-set + EOP symbols
SYNC1, SYNC2, SYNC3, RST1, RST2, EOP = 0x18, 0x11, 0x06, 0x07, 0x19, 0x0D
SOP        = [SYNC1, SYNC1, SYNC1, SYNC2]
SOP_PRIME  = [SYNC1, SYNC1, SYNC3, SYNC3]
SOP_DPRIME = [SYNC1, SYNC3, SYNC1, SYNC3]
HARD_RESET = [RST1, RST1, RST1, RST2]
CABLE_RESET = [RST1, SYNC1, RST1, SYNC3]


def craft(header, objs, sop=SOP, crc_xor=0, eop=EOP, drop_crc=False):
    """Replicate pd_encode.build_tx with a custom SOP ordered set / corrupted CRC / corrupted EOP."""
    tx = pe.TxBits()
    tx.preamble()
    for s in sop:
        tx.sym(pe.BMC(s))
    tx.encode_short(header)
    for o in objs:
        tx.encode_word(o)
    if not drop_crc:
        tx.encode_word(pe.crc32_pd(header, objs) ^ crc_xor)
    tx.sym(pe.BMC(eop))
    tx.last_edge()
    return pe.levels_to_samples(tx.level_bits())


def hx(samples):
    return (samples + bytes([(samples[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()


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
    trace = os.path.join(TMP, "rxdecode2.txt")
    if os.path.exists(trace):
        os.remove(trace)

    hdr = pe.header(1, 1, 0)                              # a simple SOP message header (Source_Cap-ish)
    objs = [0x22019096]
    variants = [
        ("sop_prime",  craft(hdr, objs, sop=SOP_PRIME)),
        ("sop_dprime", craft(hdr, objs, sop=SOP_DPRIME)),
        ("hard_reset", craft(hdr, [], sop=HARD_RESET, drop_crc=True)),
        ("cable_reset", craft(hdr, [], sop=CABLE_RESET, drop_crc=True)),
        ("bad_crc",    craft(hdr, objs, crc_xor=0xFFFFFFFF)),
        ("bad_crc2",   craft(hdr, objs, crc_xor=0x00000001)),
        ("bad_eop",    craft(hdr, objs, eop=SYNC1)),
        ("bad_eop2",   craft(hdr, objs, eop=RST1)),
        ("ctrl_sopp",  craft(pe.header(6, 0, 1), [], sop=SOP_PRIME)),   # PS_RDY on SOP'
        ("multiobj_badcrc", craft(pe.header(1, 3, 0), [0x22019096, 0x2D, 0x3C], crc_xor=0x10)),
        # multi-object messages so the decode loop iterates (bit>0) + reaches the CRC check fully
        ("multiobj_ok7", craft(pe.header(1, 7, 0), [0x22019096, 0x2D, 0x3C, 0x44, 0x55, 0x66, 0x77])),
        ("multiobj_badcrc7", craft(pe.header(1, 7, 0), [0x22019096, 0x2D, 0x3C, 0x44, 0x55, 0x66, 0x77], crc_xor=0x80)),
        ("twoobj_badcrc", craft(pe.header(1, 2, 0), [0x22019096, 0x0002D12C], crc_xor=0x1)),
        ("ctrl_badcrc", craft(pe.header(6, 0, 1), [], crc_xor=0xDEAD)),     # 0-object ctrl + bad CRC
        ("trunc_header", craft(pe.header(1, 1, 0), [0x22019096], drop_crc=True, eop=SYNC2)),  # no CRC + odd EOP
    ]

    def fire(t="0.05"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += ['sysbus.usart1 WriteChar %d' % x for x in b"sysjump rw\r"] + ['emulation RunFor "0.5"']
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hx(pe.encode_message(*pe.ctrl(1, i))))]
    # enable PD RX debug (pd[port].debug_level>0) so the SOP''/CRC CPRINTF arms (usb_pd_tcpc.c:639/682)
    # run, and reach a contract so the decode loop processes full multi-object messages.
    c += ['sysbus.usart1 WriteChar %d' % x for x in b"pd 0 dump 3\r"] + ['emulation RunFor "0.05"']
    c += ['sysbus.usart1 WriteChar %d' % x for x in b"pd 0 dump\r"] + ['emulation RunFor "0.05"']
    c += ['cpu CreateExecutionTracing "trrx" @%s PC' % trace]
    # deliver each malformed waveform several times (DISCOVERY retries -> repeated RX-arm windows)
    for name, samp in variants:
        for _ in range(4):
            c += ['sysbus.dma1 StageResponse "%s"' % hx(samp)] + fire("0.05")
    # interleave a valid SRC_CAP so gale stays in a receiving state between malformed deliveries
    for name, samp in variants:
        c += ['sysbus.dma1 StageResponse "%s"' % hx(pe.encode_message(*pe.SRC_CAP))] + fire("0.05")
        c += ['sysbus.dma1 StageResponse "%s"' % hx(samp)] + fire("0.05")
    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "rxdecode2.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "rxdecode2_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/rxdecode2_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
