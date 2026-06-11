#!/usr/bin/env python3
"""Deterministic coverage of handle_ctrl_request's swap/reset completion arms via msgbat's PROVEN
fire() delivery (ExpectContractMsg+FireComp x3 reaches handle_ctrl_request — that's the source of the
existing one-dir coverage) COMBINED with a CPU hook (hook_pdstate.py) that forces pd[0].task_state to a
genuinely-reachable target EXACTLY at the handler's read, so the delivered ctrl msg branches in-state.
CORRECTED enum (captured/rebuilt have NO CONFIG_USBC_VCONN_SWAP): SOFT_RESET=32, no VCONN states.
Legitimacy = the accepted stinj injection class (reachable state + real delivered msg + real handler);
the hook only fixes timing. Accumulates tmp/pdhook_edges.pkl (unioned by combine_coverage.py)."""
import os
import pickle
import subprocess
import sys

import pd_encode as pe
import coverage_captured as CC

RW = "rw" in sys.argv                 # run the lever in the RW image (sysjump rw); hook PCs +0x10000
OFF = 0x10000 if RW else 0
BASE_READ_PCS = [0x08007fbc, 0x08008454, 0x0800848c, 0x080084ac, 0x080084d0, 0x080084e4, 0x08008512, 0x0800855c]

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")
TGT = 0x20002F00

PS_RDY, REJECT, WAIT, ACCEPT, SOFT = 6, 4, 12, 3, 13
# (ctrl-type, [target task_state values whose handle_ctrl_request arm it completes]) — CORRECTED enum
PAIRS = [
    (ACCEPT, [32, 27, 28, 10, 7]),     # SOFT_RESET(=32, NO VCONN)/DR_SWAP/SRC_SWAP_INIT/SNK_SWAP_INIT/SNK_REQUESTED
    (REJECT, [27, 28, 10, 7]),         # DR_SWAP/SRC_SWAP_INIT/SNK_SWAP_INIT/SNK_REQUESTED
    (WAIT,   [27, 28, 10, 7]),
    (PS_RDY, [12, 31, 6, 13]),         # SNK_SWAP_SRC_DISABLE/SRC_SWAP_STANDBY/SNK_DISCOVERY/SNK_SWAP_STANDBY
]


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


def _write_hook():
    """Generate the pydev hook script with PCs offset for RO/RW. pd[0] RAM (TS/VDM) is image-independent."""
    pcs = [pc + OFF for pc in BASE_READ_PCS]
    src = (
        "from Antmicro.Renode.Core import EmulationManager\n"
        "mc = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]\n"
        "cpu = mc[\"sysbus.cpu\"]\n"
        "TGT=0x20002F00; VTGT=0x20002F01; TS=0x20001156; VDM=0x20001198\n"
        "def _f(c,pc):\n"
        "    t=mc.SystemBus.ReadByte(TGT)\n"
        "    if t!=0xFF: mc.SystemBus.WriteByte(TS,t)\n"
        "    v=mc.SystemBus.ReadByte(VTGT)\n"
        "    if v!=0x7F: mc.SystemBus.WriteByte(VDM,v)\n"
        "for _pc in %r:\n"
        "    cpu.AddHook(_pc, _f)\n" % (pcs,))
    p = os.path.join(TMP, "hook_pdstate_gen.py")
    with open(p, "w") as f:
        f.write(src)
    return p


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "pdhook.txt")
    if os.path.exists(trace):
        os.remove(trace)
    hookf = _write_hook()

    def fire(t="0.05"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "0.05"']

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAP, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true']
    if RW:
        c += ['emulation RunFor "1.5"']                          # boot RO first so the console is ready
        c += cc("sysjump rw") + ['emulation RunFor "0.3"']       # jump to the RW image, then hook RW PCs
    c += ['sysbus WriteByte 0x%X 0xFF' % TGT,                     # task_state hook inert during contract
          'sysbus WriteByte 0x20002F01 0x7F',                     # vdm_state hook inert
          'include @%s' % hookf,
          'sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
          'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for m in (pe.SRC_CAP, pe.ACCEPT(1), pe.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    c += fire("0.2") + fire("0.2")
    c += ['cpu CreateExecutionTracing "trh" @%s PC' % trace]
    # now: for each (ctrl-type, target state) set the hook target, deliver via msgbat's fire()
    mid = 3
    for ctype, states in PAIRS:
        for st in states:
            c += ['sysbus WriteByte 0x%X %d' % (TGT, st)]
            # re-sync the reactive partner (drop stale TX-reaction state) + deliver, twice per target so a
            # desynced first attempt is retried while the hook still forces the target state.
            for rep in range(4):
                c += ['sysbus.dma1 ClearTx',
                      'sysbus.dma1 StageResponse "%s"' % hexmsg(pe.ctrl(ctype, mid))]
                c += fire("0.03")
                mid = (mid + 1) & 7 or 1
    # DATA messages -> handle_data_request arms, delivered with task_state forced to SNK_READY(9) so the
    # in-contract data handling runs (Source_Cap re-negotiate, Request, Sink_Cap, BIST, VDM, etc.).
    pdos = [0x22019096, 0x0002D12C, 0x0003C12C]
    data_msgs = [(pe.header(1, 3, 3), pdos), pe.REQUEST(4, 2, 300), (pe.header(4, 1, 5), [0x2701912C]),
                 (pe.header(3, 1, 6), [0]), (pe.header(5, 1, 7), [0]), (pe.header(6, 1, 1), [1]),
                 (pe.header(15, 1, 2), [0xFF008001]), (pe.header(15, 3, 3), [0xFF008001, 0x12345678, 0])]
    for st in (9, 7, 8):                         # SNK_READY / SNK_REQUESTED / SNK_TRANSITION
        for m in data_msgs:
            c += ['sysbus WriteByte 0x%X %d' % (TGT, st)]
            for rep in range(2):
                c += ['sysbus.dma1 ClearTx', 'sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
                c += fire("0.03")
    # MAIN dispatch switch: force task_state through the full enum (0..36, corrected: no VCONN) so every
    # state-case in the pd_task giant switch executes; deliver a control + data msg in each so message-
    # dependent sub-branches run too. The hook (now also at 0x08007fbc) holds the forced state at the read.
    pdos3 = [0x22019096, 0x0002D12C, 0x0003C12C]
    for st in range(0, 37):
        c += ['sysbus WriteByte 0x%X %d' % (TGT, st)]
        # full per-state message battery: control types 1..13 + key data msgs + role-swap headers, so the
        # message-dependent sub-branches inside each state-case run on real delivered data (hook holds st).
        msgs = [pe.ctrl(ct, mid) for ct in range(1, 14)]
        msgs += [(pe.header(1, 3, mid), pdos3), pe.REQUEST(mid, 2, 300), (pe.header(4, 1, mid), [0x2701912C]),
                 (pe.header(3, 1, mid), [0]), (pe.header(15, 1, mid), [0xFF008001]),
                 (pe.header(9, 0, mid, 0, 1), []), (pe.header(10, 0, mid, 1, 0), [])]
        for m in msgs:
            c += ['sysbus.dma1 ClearTx', 'sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
            c += fire("0.015")
        mid = (mid + 1) & 7 or 1
    # VDM cluster: force vdm_state through its values (READY=1/BUSY=2/WAIT_RSP_BUSY=3/ERR_TMOUT=-1=0xFF/
    # ERR_BUSY=-3=0xFD/DONE=0) while task_state held in a connected state (SNK_READY=9) and a VDM is
    # delivered, so pd_vdm_send_state_machine + handle_vdm_request cases run. Reactive partner ACKs gale's
    # own VDM TX via SetReply slots 9-12.
    c += ['sysbus WriteByte 0x%X 9' % TGT]                        # hold SNK_READY for the VDM phase
    for slot, ack in ((9, (pe.header(15, 1, 0), [0xFF008041])), (10, (pe.header(15, 4, 0), [0xFF008042, 0, 0, 0])),
                      (11, (pe.header(15, 5, 0), [0xFF008043, 0, 0, 0, 0])), (12, (pe.header(15, 1, 0), [0xFF008044]))):
        c += ['sysbus.dma1 SetReply %d "%s"' % (slot, hexmsg(ack))]
    vdms = [(pe.header(15, 1, 3), [0xFF008001]),                  # Disc Identity REQ
            (pe.header(15, 4, 3), [0xFF008042, 0x12345678, 0xABCD, 0]),  # Disc Identity ACK (4 VDO)
            (pe.header(15, 5, 3), [0xFF018043, 1, 2, 3, 4]),      # Disc SVID/Modes ACK
            (pe.header(15, 1, 3), [0xFF018000]),                  # unstructured VDM
            (pe.header(15, 1, 3), [0x12340040])]                  # other-SVID VDM
    for vstate in (1, 2, 3, 0xFF, 0xFD, 0):
        c += ['sysbus WriteByte 0x20002F01 %d' % vstate]
        for m in vdms:
            for rep in range(2):
                c += ['sysbus.dma1 ClearTx', 'sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
                c += fire("0.02")
    c += ['sysbus WriteByte 0x20002F01 0x7F']                     # vdm_state hook inert again
    c += ['sysbus WriteByte 0x%X 0xFF' % TGT, 'cpu DisableExecutionTracing', 'quit']
    # The script far exceeds the 128KB single -e argument limit, so write it to a .resc file and include
    # it (the -e stays tiny). renode runs the file's commands in order, arbitrary size.
    rescf = os.path.join(TMP, "pdhook_script.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    out = subprocess.run(CC._renode_cmd("include @%s" % rescf),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=600).stdout
    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdhook_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb")); ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("joined-cmd len:", len("; ".join(c)))
    print("saved -> tmp/pdhook_edges.pkl: %d edges, %d PCs" % (len(ed), len(ex)))


if __name__ == "__main__":
    main()
