"""REQUEST/SOURCE_CAP handling lever — handle_data_request arms (usb_pd_protocol.c:705 SOURCE_CAP
state-membership, :728 REQUEST as source w/ pd_check_requested_voltage valid vs invalid, :750 BIST).
As SOURCE: deliver a VALID request RDO (-> pd_check passes -> ACCEPT -> SRC_ACCEPTED) AND an INVALID
over-cap RDO (-> pd_check fails -> reject arm). As SINK: deliver Source_Cap in DISCOVERY/READY/
TRANSITION (the state-set check) + BIST Carrier-Mode-2 (payload>>28==5). Genuine. RO+RW.
Usage: uv run --python .venv python cov_reqcap.py [rw]
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
    trace = os.path.join(TMP, "reqcap.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def fire_react(t="0.2"):
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
    c += ['cpu CreateExecutionTracing "trrq" @%s PC' % trace]

    # SINK: deliver Source_Cap in DISCOVERY (initial), then reach READY and deliver Source_Cap again
    # (re-negotiate from READY), and a multi-PDO Source_Cap (the state-membership + PDO-select arms).
    c += deliver(pe.SRC_CAP)                                                   # DISCOVERY
    c += deliver(pe.ACCEPT(1)) + deliver(pe.PS_RDY(2), "0.3")                  # -> SNK_READY
    c += deliver((pe.header(1, 3, 3), [0x22019096, 0x0002D12C, 0x0003C12C]))   # Source_Cap from READY (multi-PDO)
    c += deliver(pe.SRC_CAP, "0.15")                                          # Source_Cap again (re-neg)
    c += deliver((pe.header(3, 1, 4), [0x50000000]), "0.12")                  # BIST Carrier Mode 2 (>>28==5)

    # SOURCE: become source, then deliver VALID + INVALID (over-cap) request RDOs
    c += ['sysbus.adc PartnerSink true'] + cc("pd dualrole source") + ['emulation RunFor "1.0"']
    # valid request (within gale's 5V/1.5A cap): op_current modest
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(2, 1, 150))] + fire_react("0.3")
    # invalid/over-cap request: huge op_current/max -> pd_check_requested_voltage fails (reject arm)
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(3, 1, 900))] + fire_react("0.3")
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(4, 2, 1023))] + fire_react("0.3")  # bad pos+max
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(5, 1, 1))] + fire_react("0.3")     # tiny valid
    # partner Get_Source_Cap / Get_Sink_Cap to gale-as-source
    for ct in (7, 8):
        c += deliver(pe.ctrl(ct, ct & 7), "0.15")
    # BIST as source
    c += deliver((pe.header(3, 1, 6), [0x50000000]), "0.12")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "reqcap.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "reqcap_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/reqcap_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
