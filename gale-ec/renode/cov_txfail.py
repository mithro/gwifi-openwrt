#!/usr/bin/env python3
"""TX-FAILURE (GoodCRC-timeout) lever — covers the pd_send error-return branches (the ~157 `cmp r0,#0`
after a `bl` class; top callees pd_send_control 0x08007794 (8 br) + 0x0800a6ba (6 br)). These are
one-direction because every existing PD scenario auto-delivers GoodCRC, so pd_send ALWAYS succeeds; the
error path needs a GoodCRC TIMEOUT (the partner never ACKs gale's TX) — a REAL protocol fault, not
register-forcing.

Sequence: reach SNK_READY normally (GoodCRC delivered during negotiation), THEN switch the partner to
SILENT (ReactiveEnabled false + ClearResponses + ClearTx) and trigger gale-initiated control sends
(swaps / soft-reset / hard-reset / get_*) with NO RX windows fired -> gale's send_validate_message
exhausts its retries and pd_send returns error -> the send-failure branches execute. Genuine execution.
RO + RW. Accumulates tmp/txfail_edges.pkl, unioned by combine_coverage.py.
Usage: uv run --python .venv python cov_txfail.py [rw]
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


def hexmsg(m):
    sm = pe.encode_message(*m)
    return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()


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
    trace = os.path.join(TMP, "txfail.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "0.05"']

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw") + ['emulation RunFor "0.5"']
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    c += ['cpu CreateExecutionTracing "trt" @%s PC' % trace]
    # (A) negotiate to SNK_READY (GoodCRC delivered normally)
    for mid in (1, 2, 3):
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid)) + deliver(pe.PS_RDY(mid + 1), "0.3")

    # (B) GO SILENT: partner stops ACKing. gale's subsequent control sends time out -> pd_send error.
    def silent_action(scmd):
        # SuppressGoodCrc makes the model deliver NO ACK for gale's TX even when it arms RX, so
        # send_validate_message's GoodCRC wait times out across all retries -> pd_send error return.
        return cc(scmd) + ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"',
                           'emulation RunFor "0.6"']     # RX-arm windows + time for PD_RETRY_COUNT timeouts

    c += ['sysbus.dma1 ReactiveEnabled false', 'sysbus.dma1 SuppressGoodCrc true']
    for action in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn", "pd 0 soft",
                   "pd 0 vdm version", "pd 0 vdm 1", "pd 0 swap data", "pd 0 hard"):
        c += silent_action(action)
    # (C) deliver a request that makes gale TX a reply while GoodCRC still suppressed (reply times out)
    for ct in (8, 7, 9, 10, 11, 13):          # GET_SNK_CAP/GET_SRC_CAP/DR/PR/VCONN/SOFT requests -> gale replies, no ACK
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.ctrl(ct, ct & 7))]
        c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.000005"',
              'sysbus.exti FireComp 21', 'emulation RunFor "0.000005"', 'emulation RunFor "0.5"']
    c += ['sysbus.dma1 SuppressGoodCrc false']

    c += ['sysbus ReadByte 0x20001156', 'cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "txfail.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    out = subprocess.run(C._renode_cmd("include @%s" % rescf),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=600).stdout

    ex, ed = set(), set()
    outp = os.path.join(TMP, "txfail_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/txfail_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
