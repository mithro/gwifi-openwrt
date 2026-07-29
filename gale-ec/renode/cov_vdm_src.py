#!/usr/bin/env python3
"""SOURCE-ROLE + VDM-SEND lever — targets the pd_task VDM *send* state machine (vdm_state 1/2/3 at the
pd_task top-switch on offset 72; clusters 0x8008016/24/28/32 + 0x80080a6/a8/ae), which runs ONLY when
gale is the DFP/source initiating VDM discovery (sink/UFP merely responds via handle_vdm_request).

Sequence: boot as source (PartnerSink), drive a source contract (gale sends SRC_CAP -> we deliver a
partner REQUEST -> gale ACCEPT/PS_RDY -> SRC_READY), then as DFP initiate VDM Discover-Identity/SVIDs/
Modes (console `pd 0 vdm ...`); the reactive partner (ReactToTx) auto-delivers the staged VDM ACKs from
slots 9..12 so gale's DFP VDM state machine walks its states on REAL data. Genuine execution, no forced
state. RO + RW. Accumulates tmp/vdmsrc_edges.pkl, unioned by combine_coverage.py.
Usage: uv run --python .venv python cov_vdm_src.py [rw]
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
    trace = os.path.join(TMP, "vdmsrc.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def fire_react(t="0.15"):                            # no ExpectContractMsg: let the reactive replies flow
        f = []
        for _ in range(4):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "0.05"']

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc PartnerSink true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw") + ['emulation RunFor "0.5"']
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg((pe.header(4, 1, 0), [0x2601912C]))]
    # VDM ACK replies the reactive partner sends back when gale (DFP) queries (slots 9..12 in walk order)
    vdm_acks = [
        (pe.header(15, 4, 0), [0xFF008042, 0x12345678, 0xABCD, 0]),    # Disc Identity ACK (4 VDO)
        (pe.header(15, 5, 0), [0xFF018043, 0x00010002, 0, 0, 0]),      # Disc SVIDs ACK
        (pe.header(15, 5, 0), [0xFF1C8044, 0x00010002, 0, 0, 0]),      # Disc Modes ACK
        (pe.header(15, 1, 0), [0xFF1C8045]),                           # Enter Mode ACK
    ]
    for k, ack in enumerate(vdm_acks):
        c += ['sysbus.dma1 SetReply %d "%s"' % (9 + k, hexmsg(ack))]
    c += ['cpu CreateExecutionTracing "trv" @%s PC' % trace]

    # FORCE SOURCE/DFP role then let gale TX Source_Caps (SRC_DISCOVERY). `pd dualrole source` is the
    # missing key — PartnerSink alone keeps gale dual-role-toggling rather than committed source.
    c += cc("pd dualrole source") + ['emulation RunFor "1.2"']
    # SOURCE CONTRACT: stage the partner Request but fire WITHOUT ExpectContractMsg, so the model's
    # delivery priority gives gale's own Source_Cap TX its GoodCRC FIRST (pendingGoodCrc), THEN the
    # Request from pdQueue. (ExpectContractMsg forces the Request ahead of the GoodCRC -> gale's
    # Source_Cap is never acked -> it loops in SRC_DISCOVERY=20, never reaching SRC_READY where pd_vdm
    # returns VDOs.) Request uses DEFAULT 1500mA (within gale's 1.5A cap; 5000mA over-cap -> reject).
    # diag (tmp/diag_src.py) showed: in SRC_DISCOVERY gale retransmits Source_Cap, so pendingGoodCrc
    # keeps STARVING the pdQueue Request (handle_request fired 0). Force the Request through with
    # ExpectContractMsg (nextIsContract outranks pendingGoodCrc), THEN run plain windows so the
    # reactive GoodCRCs for gale's resulting Accept + PS_RDY flow -> SRC_NEGOCIATE -> SRC_READY.
    for mid in (2, 3, 4):
        c += deliver(pe.REQUEST(mid), "0.1")             # ExpectContractMsg: Request beats GoodCRC spam
        c += fire_react("0.15") + fire_react("0.15")     # GoodCRC gale's Accept then PS_RDY
    c += cc("pd 0 state")

    # DFP VDM DISCOVERY from SRC_READY: console-initiate each VDM query; reactive partner ACKs (slots 9..12)
    for action in ("pd 0 vdm 1", "pd 0 vdm 2", "pd 0 vdm 3",
                   "pd 0 vdm version", "pd 0 vdm identity", "pd 0 vdm svid", "pd 0 vdm mode"):
        c += cc(action) + fire_react("0.2") + fire_react("0.2")
    # also deliver inbound VDM REQUESTS to exercise handle_vdm_request (UFP responder) in source role
    for vm in [(pe.header(15, 1, 4), [0xFF008001]), (pe.header(15, 1, 5), [0xFF008002]),
               (pe.header(15, 1, 6), [0xFF008003])]:
        c += deliver(vm, "0.15")
    # re-initiate after a soft reset to re-walk the VDM machine
    c += cc("pd 0 soft") + fire_react("0.2")
    for action in ("pd 0 vdm 1", "pd 0 vdm 2", "pd 0 vdm 3"):
        c += cc(action) + fire_react("0.2") + fire_react("0.2")

    c += ['sysbus ReadByte 0x20001156', 'sysbus ReadByte 0x20001198',   # task_state, vdm_state
          'cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "vdmsrc.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    out = subprocess.run(C._renode_cmd("include @%s" % rescf),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=600).stdout

    ex, ed = set(), set()
    outp = os.path.join(TMP, "vdmsrc_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    tail = [ln.strip() for ln in out.splitlines()[-12:] if ln.strip().startswith("0x")]
    print("final task_state/vdm_state bytes:", tail[-2:] if len(tail) >= 2 else tail)
    print("saved -> tmp/vdmsrc_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
