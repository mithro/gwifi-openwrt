"""PD-BIST + UNHANDLED-VDM lever — two pd_task message paths the campaign never delivers:
 (1) :757 PD_DATA_BIST handling -> `if ((payload[0] >> 28) == 5) pd_transmit(TCPC_TX_BIST_MODE_2)`:
     reached only when a BIST data message (type 3) with payload 0x5xxxxxxx arrives WHILE in SNK_READY
     (sink) or SRC_READY (source). The campaign delivers many message types but not a mode-2 BIST in
     the ready state.
 (2) :498 `if (debug_level >= 1) CPRINTF("Unhandled VDM VID %04x CMD %04x")`: reached when a VDM
     (type 15) is neither handled by pd_svdm (unknown SVID) nor pd_custom_vdm (rlen<=0). Needs an
     UNHANDLED VDM + debug_level high.
Drives both from a live sink contract (SNK_READY) AND a source contract (SRC_READY) with debug high.
Genuine live PD execution. RO + RW. Accumulates tmp/pdbist_edges.pkl.
Usage: uv run --python .venv python cov_pdbist.py [rw]
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


# A BIST data message (PD_DATA_BIST=type 3) with mode field (bits 31:28)==5 -> BIST Carrier Mode 2.
def BIST(mid, prole=1, drole=1):
    return (pe.header(3, 1, mid, prole=prole, drole=drole), [0x50000000])


# An UNHANDLED structured VDM. gale has CONFIG_USB_PD_ALT_MODE but NOT _DFP, so pd_svdm NAKs unknown
# INIT commands (rsize=1 -> handled) but returns 0 for a RESPONSE type: a VDM with cmd_type=CMDT_RSP_NAK
# (2<<6=0x80) hits the final `else { CPRINTF("ERR:CMDT"); rsize=0; }` -> rlen<=0 -> "Unhandled VDM" print.
# (Avoid CMDT_RSP_BUSY=3: handle_vdm_request intercepts it when vdm_state==BUSY.)
def UNHANDLED_SVDM(mid, svid=0x1234, cmd=0x05, cmdt=2):
    vdo = (svid << 16) | (1 << 15) | ((cmdt & 0x3) << 6) | (cmd & 0x1F)   # SVDM bit + CMDT field
    return (pe.header(15, 1, mid), [vdo])


# A custom (non-SVDM) VDM that pd_custom_vdm returns 0 for (SVDM bit clear, unknown VID).
def UNHANDLED_CUSTOM_VDM(mid, vid=0x4321):
    vdo = (vid << 16) | 0x00AB                            # SVDM bit (15) CLEAR -> pd_custom_vdm
    return (pe.header(15, 1, mid), [vdo])


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "pdbist.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    def contract_setup():
        s = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
        for i in range(8):
            s += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        for i in range(8):
            s += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
        return s

    # ---------- SINK side: gale=sink (ForcePartnerSrc) -> SNK_READY, debug high ----------
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "0.4"']
    if RW:
        c += cc("sysjump rw", "0.4") + ['emulation RunFor "0.3"']
    c += cc("pd dump 3", "0.1") + cc("tcpc dump 3", "0.1")
    c += contract_setup()
    c += ['cpu CreateExecutionTracing "trbist" @%s PC' % trace]

    mid = 1
    for _ in range(3):
        c += deliver(pe.SRC_CAP, "0.1")
    c += deliver(pe.ACCEPT(mid), "0.15") + deliver(pe.PS_RDY(mid + 1), "0.3"); mid += 2
    # now in SNK_READY: BIST + unhandled VDMs (partner is source -> prole=1)
    c += deliver(BIST(mid & 7, prole=1, drole=1), "0.3"); mid += 1
    # BIST drops to disconnected -> re-attach for the VDM tests
    c += ['sysbus.adc ForcePartnerSrc false', 'emulation RunFor "0.3"',
          'sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "0.4"']
    for _ in range(3):
        c += deliver(pe.SRC_CAP, "0.1")
    c += deliver(pe.ACCEPT(mid), "0.15") + deliver(pe.PS_RDY(mid + 1), "0.3"); mid += 2
    for ct in (2, 1, 2, 3):       # CMDT: NAK, ACK, NAK, BUSY (all -> rsize=0 -> unhandled, non-DFP)
        c += deliver(UNHANDLED_SVDM(mid & 7, svid=0x1234, cmd=0x05, cmdt=ct), "0.15"); mid += 1
    c += deliver(UNHANDLED_SVDM(mid & 7, svid=0xABCD, cmd=0x0A, cmdt=2), "0.15"); mid += 1
    c += deliver(UNHANDLED_CUSTOM_VDM(mid & 7, vid=0x4321), "0.15"); mid += 1
    c += deliver(UNHANDLED_CUSTOM_VDM(mid & 7, vid=0x18d1), "0.15"); mid += 1   # google VID, bad cmd
    # a multi-VDO unhandled VDM
    c += deliver((pe.header(15, 3, mid & 7), [(0x5678 << 16) | (1 << 15) | 0x07, 0xDEADBEEF, 0xCAFEBABE]), "0.15"); mid += 1
    # INVALID DATA-message type (>= 16) with cnt>=1: the msg-type dispatch computes r0=(type-1); `cmp r0,#0xe;
    # bls` uses the data jump table for type 1..15, else default. type>=16 -> the bls-not-taken arm
    # (0x0800817a missing dir: type-1 > 0xe). cnt>=1 so r5!=0 (data, not control).
    for ty in (16, 20, 31):
        c += deliver((pe.header(ty, 1, mid & 7), [0xDEADBEEF]), "0.12"); mid += 1
    # --- more malformed-header dispatch arms (proven vein) ---
    # invalid CONTROL types (cnt==0, type > the control jump-table max) -> control-dispatch default
    for ty in (14, 15, 20, 31):
        c += deliver((pe.header(ty, 0, mid & 7), []), "0.1"); mid += 1
    # EXTENDED-message bit (bit 15) set on the header -> the extended-message path (bpl-not-taken arm)
    for ty in (1, 2, 4):
        hdr, dat = pe.header(ty, 1, mid & 7), [0xAABBCCDD]
        c += deliver((hdr | (1 << 15), dat), "0.1"); mid += 1
    # cnt/type mismatch: a CONTROL type carried with cnt>=1 (data path) and a DATA type with cnt==0
    c += deliver((pe.header(6, 2, mid & 7), [0x11111111, 0x22222222]), "0.1"); mid += 1   # PS_RDY w/ data
    c += deliver((pe.header(2, 0, mid & 7), []), "0.1"); mid += 1                          # REQUEST w/ no data
    c += deliver((pe.header(0, 1, mid & 7), [0xDEADC0DE]), "0.1"); mid += 1                # reserved type 0, cnt=1
    # SPEC-REVISION field (header bits 6-7) variants: the campaign only sends rev=1. rev=3 is reserved
    # (0x08008338 `(header>>6)&3 == 3` missing dir) + rev=0/2 exercise the rev-dependent arms.
    for rv in (0, 2, 3):
        c += deliver((pe.header(1, 1, mid & 7, rev=rv), [pe.PDO_5V_1A5]), "0.1"); mid += 1   # Source_Cap, rev variant
        c += deliver((pe.header(6, 0, mid & 7, rev=rv), []), "0.1"); mid += 1                 # PS_RDY ctrl, rev variant
        c += deliver((pe.header(3, 0, mid & 7, rev=rv), []), "0.1"); mid += 1                 # Accept ctrl, rev variant

    # ---------- SOURCE side: gale=source (PartnerSink) -> SRC_READY, then BIST ----------
    c += ['sysbus.adc ForcePartnerSrc false', 'sysbus.adc ForceRaw 0', 'emulation RunFor "0.4"']
    c += ['sysbus.adc PartnerSink true', 'emulation RunFor "0.3"']
    c += cc("pd 0 dualrole source", "0.2") + ['emulation RunFor "1.0"']
    for _ in range(2):
        c += deliver(pe.REQUEST(mid & 7, 1, 150), "0.3"); mid += 1
    c += deliver((pe.header(4, 1, mid & 7, prole=0, drole=0), [0x2601912C]), "0.3"); mid += 1   # sink cap -> SRC_READY settle
    c += ['emulation RunFor "0.4"']
    # A VALID Request delivered IN SRC_READY (task_state != SRC_DISCOVERY): the PD_DATA_REQUEST handler
    # validates (pd_check_requested_voltage >= 0) then `if (task_state == SRC_DISCOVERY)`; in SRC_READY
    # this takes the ELSE/fall-through (0x08008404 task_state!=0x14 missing dir).
    for _ in range(2):
        c += deliver(pe.REQUEST(mid & 7, 1, 150), "0.25"); mid += 1
    c += ['emulation RunFor "0.3"']
    # BIST in SRC_READY (partner is sink -> prole=0)
    c += deliver(BIST(mid & 7, prole=0, drole=0), "0.3"); mid += 1
    # unhandled VDM in source ready
    c += deliver(UNHANDLED_SVDM(mid & 7, svid=0x2468, cmd=0x09), "0.15"); mid += 1
    c += cc("pd 0 state")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pdbist.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdbist_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pdbist_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
