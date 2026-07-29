#!/usr/bin/env python3
"""PD-SWAP lever — targets the pd_task DR/PR-swap SEND-FAILURE arms that a healthy swap never hits:
  usb_pd_protocol.c:1885 PD_STATE_DR_SWAP -> res=send_control(PD_CTRL_DR_SWAP); if (res<0)
    set_state(res==-1 ? PD_STATE_SOFT_RESET : READY) -> the res==-1 (no-GoodCRC) SOFT_RESET arm,
  :1907 PD_STATE_SRC_SWAP_INIT -> res=send_control(PD_CTRL_PR_SWAP); same res==-1 arm.
Mechanism: reach a contract (SNK_READY / SRC_READY), then `pd 0 swap data|power` with SuppressGoodCrc
true so gale's swap message gets no GoodCRC -> send_control returns -1 -> the soft-reset recovery arm.
Also: partner-initiated swaps answered with REJECT / WAIT, and the gale-as-source PR_SWAP path.
Genuine execution with the reactive partner. RO + RW. Accumulates tmp/pdswap_edges.pkl.
Usage: uv run --python .venv python cov_pdswap.py [rw]
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
    trace = os.path.join(TMP, "pdswap.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def fire_react(t="0.15"):
        f = []
        for _ in range(4):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['cpu CreateExecutionTracing "trsw" @%s PC' % trace]

    # reach SNK_READY (ordered SRC_CAP -> ACCEPT -> PS_RDY), then SETTLE so task_state == SNK_READY
    # before any swap (pd_request_data_swap only enters DR_SWAP from a stable SNK_READY, usb_pd:804).
    c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(1)) + deliver(pe.PS_RDY(2), "0.4")
    c += ['emulation RunFor "0.6"'] + cc("pd 0 state", "0.1")

    # PHASE 1 (swap SEND succeeds): gale-initiated DR/PR swaps with reactive ACCEPT -> success arms.
    # settle back to READY between swaps so each is issued from SNK_READY/SRC_READY.
    for act in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap data"):
        c += cc(act) + fire_react("0.2") + fire_react("0.2") + ['emulation RunFor "0.4"']

    # PHASE 2 (swap SEND FAILS, res==-1): SuppressGoodCrc -> gale's DR_SWAP/PR_SWAP gets no GoodCRC ->
    # send_control returns -1 -> set_state(SOFT_RESET) (usb_pd_protocol.c:1894 / :1917).
    c += ['emulation RunFor "0.4"', 'sysbus.dma1 SuppressGoodCrc true']
    for act in ("pd 0 swap data", "pd 0 swap power"):
        c += cc(act) + ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"', 'emulation RunFor "0.4"']
        c += ['emulation RunFor "0.3"']    # let the soft-reset recovery settle back toward READY
    c += ['sysbus.dma1 SuppressGoodCrc false', 'sysbus.dma1 ReactiveEnabled true']
    # recover after the soft-resets
    c += cc("pd 0 soft") + fire_react("0.3")
    for mid in (4, 5):
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid)) + deliver(pe.PS_RDY(mid + 1), "0.25")

    # PHASE 3: partner-initiated swaps answered REJECT (4) / WAIT (12) instead of ACCEPT -> the
    # reject/wait handling arms in the swap responder.
    for mid, ct in ((6, 9), (7, 10), (8, 9), (9, 10)):  # DR_SWAP(9) / PR_SWAP(10) requests to gale
        c += deliver(pe.ctrl(ct, mid), "0.15")
    # deliver explicit REJECT and WAIT controls in-contract
    c += deliver(pe.ctrl(4, 2), "0.12") + deliver(pe.ctrl(12, 3), "0.12")

    # PHASE 4 (source role): PartnerSink + force source, reach SRC_READY, then PR swap init fails.
    c += ['sysbus.adc ForceSourceCc false', 'sysbus.adc PartnerSink true']
    c += cc("pd dualrole source") + ['emulation RunFor "1.0"']
    for mid2 in (3, 4):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(mid2))] + fire_react("0.3")
    for act in ("pd 0 swap data", "pd 0 swap power"):
        c += cc(act) + fire_react("0.2")
    c += ['sysbus.dma1 SuppressGoodCrc true']
    for act in ("pd 0 swap power", "pd 0 swap data"):
        c += cc(act) + ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"', 'emulation RunFor "0.4"']
    c += ['sysbus.dma1 SuppressGoodCrc false']

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pdswap.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdswap_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pdswap_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
