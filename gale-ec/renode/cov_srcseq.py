"""SOURCE-SEQUENCE lever — drive gale-as-SOURCE through the full power-up state machine
(SRC_DISCOVERY -> NEGOCIATE -> ACCEPTED -> POWERED -> TRANSITION -> READY) and exercise messages in
each SRC state, plus source-side swaps/soft/hard from SRC_READY. The sink side is heavily covered;
the source intermediate states (SRC_ACCEPTED/POWERED/TRANSITION) and their sub-branches are the gap.
Reactive partner ACKs gale's TX; we deliver the sink-side Requests/control to advance each step.
Genuine. RO+RW.  Usage: uv run --python .venv python cov_srcseq.py [rw]
"""
import os, pickle, subprocess, sys
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
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "srcseq.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def fire_react(t="0.2"):
        f = []
        for _ in range(5):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]

    def stage_react(m, t="0.25"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire_react(t)

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc PartnerSink true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['cpu CreateExecutionTracing "trss" @%s PC' % trace]

    # force source role, let gale TX Source_Caps (SRC_DISCOVERY)
    c += cc("pd dualrole source") + ['emulation RunFor "1.2"']
    mid = 2
    for cyc in range(4):
        # sink Request advances SRC_DISCOVERY -> NEGOCIATE -> (gale ACCEPT) -> ACCEPTED -> POWERED ->
        # TRANSITION -> (gale PS_RDY) -> SRC_READY. Reactive GoodCRCs gale's Accept/PS_RDY.
        c += stage_react(pe.REQUEST(mid, 1, 150), "0.4"); mid += 1
        # from SRC_READY: partner Get_Source_Cap/Get_Sink_Cap/swaps/control + a new Request (re-neg)
        for ct in (7, 8, 9, 10, 11, 2, 5, 12, 13):
            c += stage_react(pe.ctrl(ct, mid & 7), "0.12"); mid += 1
        c += stage_react(pe.REQUEST(mid, 1, 100), "0.3"); mid += 1     # re-negotiate from READY
        # gale-initiated from SRC_READY
        for act in ("pd 0 swap data", "pd 0 swap power", "pd 0 vdm vers", "pd 0 soft"):
            c += cc(act) + fire_react("0.2")
        # hard reset -> SRC_HARD_RESET / recover -> re-discovery
        c += cc("pd 0 hard") + ['emulation RunFor "0.5"']
    # disconnect/reconnect the sink partner (SRC_DISCONNECTED + PREVIOUS_PD_CONN)
    for _ in range(2):
        c += ['sysbus.adc PartnerSink false', 'emulation RunFor "0.4"']
        c += ['sysbus.adc PartnerSink true', 'emulation RunFor "0.3"']
        c += stage_react(pe.REQUEST(mid, 1, 150), "0.4"); mid += 1

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "srcseq.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "srcseq_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/srcseq_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
