"""PD-SOURCE-ROLE lever — drives the source-side pd_task states the campaign's _src_contract_post
reaches only one-directionally: PD_STATE_SRC_GET_SINK_CAP(26), SRC_DISCOVERY(20), VCONN_SWAP_SEND(32),
SNK_SWAP_STANDBY(13). gale as SOURCE (GaleAdc.PartnerSink + `pd dualrole source`) reaches SRC_READY, which
AUTO-enters SRC_GET_SINK_CAP (send_control GET_SINK_CAP) while `!(flags & PD_FLAGS_SNK_CAP_RECVD)`. The
campaign never delivers a Sink_Capabilities message back, so:
 - the `flags & PD_FLAGS_SNK_CAP_RECVD` TRUE arm (don't re-send) is dark -> we deliver SINK_CAP (data msg
   type 4) so the flag sets;
 - the snk_cap_count > PD_SNK_CAP_RETRIES + `debug_level>=1` "ERR SNK_CAP" arm is dark -> a phase with
   debug high and NO sink-cap response so the retry counter exhausts;
 - VCONN_SWAP_SEND via `pd 0 swap vconn` from SRC_READY (pd_request_vconn_swap :796);
 - SNK_SWAP_STANDBY via a PR swap.
Genuine live PD execution. RO + RW. Accumulates tmp/pdsrc_edges.pkl.
Usage: uv run --python .venv python cov_pdsrc.py [rw]
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


# Sink_Capabilities = data msg type 4 + a fixed sink PDO (5V 3A). Sets PD_FLAGS_SNK_CAP_RECVD in gale.
def SINK_CAP(mid):
    return (pe.header(4, 1, mid, prole=0, drole=0), [0x2601912C])


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "pdsrc.txt")
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

    # Boot as SOURCE: PartnerSink (CC1 in source Rd band) so gale source-attaches.
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc PartnerSink true', 'emulation RunFor "0.4"']
    if RW:
        c += cc("sysjump rw", "0.4") + ['emulation RunFor "0.3"']
    # debug high (source-path debug prints + the ERR SNK_CAP retry arm)
    c += cc("pd dump 3", "0.1") + cc("tcpc dump 3", "0.1")
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['cpu CreateExecutionTracing "trsrc" @%s PC' % trace]

    # Enter source role -> SRC_STARTUP -> SRC_DISCOVERY (TX Source_Caps)
    c += cc("pd 0 dualrole source", "0.2")
    c += ['emulation RunFor "1.2"']
    mid = 2
    # Deliver sink Request -> SRC_NEGOCIATE -> SRC_ACCEPTED -> SRC_TRANSITION -> SRC_READY
    for _ in range(2):
        c += deliver(pe.REQUEST(mid, 1, 150), "0.3"); mid += 1
    # SRC_READY auto-sends GET_SINK_CAP -> SRC_GET_SINK_CAP. Deliver SINK_CAP -> PD_FLAGS_SNK_CAP_RECVD set
    # (the "don't re-send" arm + SRC_GET_SINK_CAP exit-with-cap).
    c += deliver(SINK_CAP(mid), "0.3"); mid += 1
    c += ['emulation RunFor "0.4"']      # settle in SRC_READY with cap received

    # --- swaps from SRC_READY ---
    c += cc("pd 0 swap vconn") + fire("0.2") + deliver(pe.ACCEPT(mid), "0.2") + deliver(pe.PS_RDY(mid + 1), "0.2"); mid += 2
    c += cc("pd 0 swap power") + fire("0.2") + deliver(pe.ACCEPT(mid), "0.2") + deliver(pe.PS_RDY(mid + 1), "0.3"); mid += 2
    c += cc("pd 0 swap data") + fire("0.2") + deliver(pe.ACCEPT(mid), "0.2"); mid += 1
    # partner-initiated swaps/requests in source ready (handle_ctrl in source role)
    for t in (7, 8, 9, 10, 11, 5, 2, 12, 4, 13):   # GET_SRC_CAP GET_SNK_CAP DR_SWAP PR_SWAP VCONN_SWAP PING GOTO_MIN WAIT REJECT SOFT
        c += deliver(pe.ctrl(t, mid & 7), "0.1"); mid += 1
    c += deliver(SINK_CAP(mid & 7), "0.12"); mid += 1     # another sink cap (already-recvd path)

    # --- Phase 2: retry-exhaust SRC_GET_SINK_CAP (no SINK_CAP response, debug high -> ERR SNK_CAP) ---
    # Re-attach as a fresh source so flags clear, then DON'T answer the GET_SINK_CAP -> snk_cap_count
    # climbs past PD_SNK_CAP_RETRIES (each SRC_READY re-entry retries).
    c += ['sysbus.adc PartnerSink false', 'emulation RunFor "0.4"',
          'sysbus.adc PartnerSink true', 'emulation RunFor "0.4"']
    c += cc("pd 0 dualrole source", "0.2") + ['emulation RunFor "0.6"']
    for _ in range(2):
        c += deliver(pe.REQUEST(mid, 1, 150), "0.3"); mid += 1
    # let it sit in SRC_READY<->SRC_GET_SINK_CAP retrying with NO sink-cap answer (retries exhaust)
    for _ in range(6):
        c += ['emulation RunFor "0.4"']
    c += cc("pd 0 state")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pdsrc.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdsrc_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pdsrc_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
