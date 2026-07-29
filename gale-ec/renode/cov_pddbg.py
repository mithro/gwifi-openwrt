"""PD-DEBUG-TRAFFIC lever — flips the whole family of `if (debug_level >= N) CPRINTF(...)` branches
scattered through usb_pd_protocol.c and usb_pd_tcpc.c. These live INSIDE the message RX/decode/handle
paths (pd_analyze_rx, handle_request, pd_task RX processing, pd_transmit), so they only execute when a
message arrives. The campaign sets debug high (`pd dump 3`) ONLY in console-only scenarios and delivers
messages ONLY in debug-off scenarios -> every debug-gated branch is false-only. This lever combines BOTH
conditions: set the protocol debug_level (`pd dump 3`) AND the tcpc debug_level (`tcpc dump 3`) high, THEN
run a rich source+sink contract with a battery of delivered messages (SRC_CAP/Accept/PS_RDY/ctrl/data/VDM
+ bad-CRC + cable SOP') so the debug prints in both modules run. Genuine execution. RO + RW.
Accumulates tmp/pddbg_edges.pkl. Usage: uv run --python .venv python cov_pddbg.py [rw]
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
    trace = os.path.join(TMP, "pddbg.txt")
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

    def deliver_raw(hexstr, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexstr] + fire(t)

    # Boot sink-attached (ForcePartnerSrc) so the RX/decode paths run on delivered messages.
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "0.4"']
    if RW:
        c += cc("sysjump rw", "0.4") + ['emulation RunFor "0.3"']
    # Raise BOTH debug levels to 3 BEFORE tracing, so every `if (debug_level >= N)` in the
    # message paths is in the high state when traffic flows.
    c += cc("pd dump 3", "0.1") + cc("tcpc dump 3", "0.1")
    c += cc("pd 0 dump 3", "0.1")          # per-port form too (in case it routes differently)

    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['cpu CreateExecutionTracing "trpdb" @%s PC' % trace]

    mid = 1
    # reach SNK_READY (early SRC_CAP) so in-contract message handling runs with debug high
    for _ in range(3):
        c += deliver(pe.SRC_CAP, "0.1")
    c += deliver(pe.ACCEPT(mid), "0.15") + deliver(pe.PS_RDY(mid + 1), "0.3"); mid += 2

    # battery of partner messages (each triggers debug prints in handle_request / pd_analyze_rx)
    for ct in (8, 7, 9, 10, 11, 12, 5, 2, 4, 13, 6, 3, 1, 14, 15):
        c += deliver(pe.ctrl(ct, mid & 7), "0.08"); mid += 1
    # data messages: Source_Caps, Request, Sink_Caps, VDMs (discover identity / svid / modes)
    c += deliver((pe.header(1, 3, mid & 7), [0x22019096, 0x0002D12C, 0x0003C12C]), "0.1"); mid += 1
    c += deliver(pe.REQUEST(mid & 7, 1, 250), "0.1"); mid += 1
    c += deliver((pe.header(4, 1, mid & 7), [0x2601912C]), "0.1"); mid += 1
    for vm in [(pe.header(15, 1, mid & 7), [0xFF008001]),
               (pe.header(15, 4, mid & 7), [0xFF008042, 1, 2, 3]),
               (pe.header(16, 1, mid & 7), [0xFF018001])]:
        c += deliver(vm, "0.1"); mid += 1

    # bad-CRC frame: stage a payload but corrupt the trailing CRC bytes so pcrc != ccrc (pd_analyze_rx
    # CRC-mismatch arm + the debug_level CRC print). Hand-corrupt the last hex byte of a valid msg.
    good = hexmsg(pe.ctrl(1, mid & 7)); mid += 1
    bad = good[:-2] + ("%02x" % ((int(good[-2:], 16) ^ 0xA5) & 0xFF))
    c += deliver_raw(bad, "0.1")

    # debug_level == 1 phase: the compound `(debug_level==1 && PD_HEADER_TYPE != PD_CTRL_PING)`
    # (usb_pd_protocol.c:1025) short-circuits at level>=2, so the PING-type sub-check is never
    # evaluated above. Set level EXACTLY 1, then deliver a PING (ctrl 5) AND non-PING messages so
    # both the `== 1` comparison and the `!= PD_CTRL_PING` comparison are exercised both ways.
    c += cc("pd dump 1", "0.1") + cc("tcpc dump 1", "0.1")
    c += deliver(pe.ctrl(5, mid & 7), "0.1"); mid += 1       # PING (type==PD_CTRL_PING)
    c += deliver(pe.ctrl(3, mid & 7), "0.1"); mid += 1       # ACCEPT (non-PING)
    c += deliver(pe.ctrl(6, mid & 7), "0.1"); mid += 1       # PS_RDY (non-PING)
    c += deliver(pe.SRC_CAP, "0.1")                          # data msg (non-PING) at level 1

    # console PD prints that themselves gate on debug_level (state/flags dumps with debug high)
    c += cc("pd 0 state") + cc("pd 0 flags") + cc("tcpc 0 dump") + cc("tcpc 0 state")
    c += cc("pd 0 soft", "0.2") + fire("0.2")
    c += cc("pd 0 hard", "0.3")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pddbg.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pddbg_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pddbg_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
