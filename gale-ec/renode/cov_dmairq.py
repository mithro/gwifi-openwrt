"""DMA-TC-INTERRUPT lever — exercises dma_event_interrupt_channel_1/2_3 (conf:exact/high, ~16 br), the
DMA transfer-complete ISR path that was MISSING from the emulation (GaleDma was polling-only). The
firmware enables the TC interrupt on the PD SPI-TX DMA channel (usb_pd_phy.c:344 dma_enable_tc_interrupt_
callback). With GaleDma.DmaTcIrqEnabled set, each gale PD TX -> SPI-TX DMA completion asserts the NVIC
DMA IRQ -> the ISR runs (-> _dma_wake_callback). Drive lots of gale PD TX (contract + swaps + VDM +
requests) so the ISR fires repeatedly. Genuine execution of newly-modeled HW. RO + RW.
Usage: uv run --python .venv python cov_dmairq.py [rw]
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
    trace = os.path.join(TMP, "dmairq.txt")
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
    c += ['sysbus.dma1 DmaTcIrqEnabled true']            # <-- model the DMA TC-interrupt path
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['cpu CreateExecutionTracing "trdq" @%s PC' % trace]

    # contract (gale TXs Request/GoodCRC -> SPI-TX DMA completes -> TC IRQ); then lots of gale TX
    for mid in (1, 2, 3):
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid)) + deliver(pe.PS_RDY(mid + 1), "0.25")
    for act in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn", "pd 0 vdm vers",
                "pd 0 vdm ping 1", "pd 0 soft", "pd 0 state", "pd 0 hard"):
        c += cc(act) + fire_react("0.2")
    # partner-initiated msgs -> gale replies (more TX) -> more TC IRQs
    mid = 5
    for ct in (8, 7, 9, 10, 11, 12, 13, 2, 5):
        c += deliver(pe.ctrl(ct, mid & 7), "0.12"); mid += 1
    # re-contract cycles (each TX completes via TC IRQ)
    for cyc in range(2):
        c += cc("pd 0 hard") + ['emulation RunFor "0.4"']
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid & 7)) + deliver(pe.PS_RDY((mid + 1) & 7), "0.25"); mid += 2

    c += ['sysbus.dma1 DmaTcIrqEnabled false', 'cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "dmairq.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "dmairq_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/dmairq_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
