#!/usr/bin/env python3
"""CONTRACT lever — the keystone breakthrough (diag_rx.py proved RX reception works; the gap was that
no scenario delivered the ordered SRC_CAP->ACCEPT->PS_RDY negotiation, so gale never reached SNK_READY
and every in-contract pd_task branch stayed dark).

This driver: (1) boots as a sink (ForceSourceCc), (2) negotiates to SNK_READY by delivering exactly one
message per RX window in protocol order, then (3) from a REAL SNK_READY contract delivers the full
in-contract message battery (data Source_Cap re-negotiate / Request / Get_Sink_Cap / BIST / VDM
Disc-Identity-SVID-Modes / every control type incl. role-swaps) AND issues gale-initiated console swap
actions, each with the reactive partner (ReactiveEnabled) auto-completing the handshake. Genuine
execution of the real captured firmware through a live PD contract; no faked branches, no forced state.

RO + RW (sysjump rw). Accumulates tmp/contract_edges.pkl, unioned by combine_coverage.py.
Usage: uv run --python .venv python cov_contract.py [rw] [--bin <fw>]
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
    trace = os.path.join(TMP, "contract.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):                            # stage one msg, then open an RX window
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
    # reactive replies the partner sends to gale-initiated requests: ACCEPT (slots 0-7) + Sink_Cap (slot 8)
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg((pe.header(4, 1, 0), [0x2601912C]))]
    c += ['cpu CreateExecutionTracing "trc" @%s PC' % trace]

    # (2) NEGOTIATE TO SNK_READY — one msg per window, protocol order. Repeat to absorb msg_id/timing.
    for mid in (1, 2, 3):
        c += deliver(pe.SRC_CAP)
        c += deliver(pe.ACCEPT(mid))
        c += deliver(pe.PS_RDY(mid + 1), "0.3")

    # (3) IN-CONTRACT BATTERY from SNK_READY. Each delivered msg drives a handle_*_request arm in-state;
    # the reactive partner auto-GoodCRCs/Accepts gale's responses so multi-step exchanges complete.
    pdos = [0x22019096, 0x0002D12C, 0x0003C12C]
    mid = 5
    data_battery = [
        (pe.header(1, 3, mid), pdos),                   # Source_Cap re-negotiate (3 PDOs)
        pe.REQUEST(mid, 2, 300),                        # Request object
        (pe.header(4, 1, mid), [0x2601912C]),           # Sink_Cap
        (pe.header(3, 1, mid), [0]),                    # BIST
        (pe.header(15, 1, mid), [0xFF008001]),          # VDM Disc Identity REQ (structured)
        (pe.header(15, 4, mid), [0xFF008042, 0x12345678, 0xABCD, 0]),  # Disc Identity ACK (4 VDO)
        (pe.header(15, 5, mid), [0xFF018043, 1, 2, 3, 4]),             # Disc SVID/Modes ACK
        (pe.header(15, 1, mid), [0xFF018000]),          # unstructured VDM
    ]
    for m in data_battery:
        c += deliver(m, "0.12")
    # every control type from READY (incl. role-swap requests the partner initiates)
    for ct in range(1, 14):
        c += deliver(pe.ctrl(ct, mid & 7), "0.1")
        mid += 1
    # gale-INITIATED swaps/soft-reset/VDM from READY (console), reactive partner completes the handshake
    for action in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn",
                   "pd 0 vdm version", "pd 0 soft", "pd 0 dump 1", "pd 0 state"):
        c += cc(action) + fire("0.15") + fire("0.15")
    # re-negotiate + hard reset cycle to flip HARD_RESET_SEND/EXECUTE/RECOVER + re-entry to READY
    c += cc("pd 0 hard") + fire("0.2")
    for mid2 in (6, 7):
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid2)) + deliver(pe.PS_RDY(mid2 + 1), "0.3")

    c += ['sysbus ReadByte 0x20001156',                 # final task_state (expect 9 = SNK_READY)
          'cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "contract.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    out = subprocess.run(C._renode_cmd("include @%s" % rescf),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=600).stdout

    ex, ed = set(), set()
    outp = os.path.join(TMP, "contract_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    # surface the final state line from the renode console
    for ln in out.splitlines()[-12:]:
        if ln.strip().startswith("0x"):
            print("final task_state byte:", ln.strip())
    print("saved -> tmp/contract_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
