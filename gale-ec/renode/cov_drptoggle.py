"""DRP-TOGGLE lever — drives the pd_task DUAL-ROLE toggling arms that a static-role attach never reaches.
This firmware (no separate AUTO_TOGGLE state) toggles in place: in PD_STATE_SRC_DISCONNECTED
(usb_pd_protocol.c:1558 `drp_state != PD_DRP_FORCE_SOURCE && get_time().val >= next_role_swap` -> swap to
sink, :1563 next_role_swap += PD_T_DRP_SNK) and PD_STATE_SNK_DISCONNECTED (:2025 `drp_state ==
PD_DRP_TOGGLE_ON && get_time().val >= next_role_swap` -> :2030 back to SRC_DISCONNECTED). The toggle is
driven by WALL-CLOCK, not I/O: enabling DRP (`pd 0 dualrole on`) + advancing emulated time with CC OPEN
(no partner) flips the `>=` both ways and cycles the two disconnected states repeatedly. Also FORCE_SINK
(:1258), FORCE_SOURCE (:1275), TOGGLE_OFF, and partner-attach-mid-toggle role resolution (PartnerSink ->
gale resolves SOURCE; ForcePartnerSrc -> gale resolves SINK). pd_task sleeps between toggles so the trace
stays bounded. Genuine execution. RO + RW. Accumulates tmp/drptoggle_edges.pkl.
Usage: uv run --python .venv python cov_drptoggle.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


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
    trace = os.path.join(TMP, "drptoggle.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.08"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    # Boot with CC OPEN (no partner) so gale sits in SRC_DISCONNECTED ready to toggle.
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trdt" @%s PC' % trace]

    # (1) Enable DRP toggling, no partner -> SRC_DISCONNECTED <-> SNK_DISCONNECTED cycling on the clock.
    c += cc("pd 0 dualrole on")
    for _ in range(6):                       # several role-swap periods (PD_T_DRP_* are tens of ms)
        c += ['emulation RunFor "0.6"']
    # (2) FORCE_SINK then FORCE_SOURCE then OFF (each a distinct drp_state arm at :1258/:1275/:1260)
    c += cc("pd 0 dualrole sink") + ['emulation RunFor "0.8"']
    c += cc("pd 0 dualrole source") + ['emulation RunFor "0.8"']
    c += cc("pd 0 dualrole off") + ['emulation RunFor "0.8"']
    # (3) back to toggle, then attach a SINK partner mid-toggle -> gale resolves to SOURCE
    c += cc("pd 0 dualrole on") + ['emulation RunFor "0.6"']
    c += ['sysbus.adc PartnerSink true', 'emulation RunFor "1.0"']
    c += ['sysbus.adc PartnerSink false', 'emulation RunFor "0.8"']   # detach -> back to toggle
    # (4) attach a SOURCE partner mid-toggle -> gale resolves to SINK (DRP sink-attach / try-src path)
    c += ['sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "1.0"']
    c += ['sysbus.adc ForcePartnerSrc false', 'sysbus.adc ForceRaw 0', 'emulation RunFor "0.8"']
    # (5) a final toggle stretch to catch any remaining timing arm
    for _ in range(4):
        c += ['emulation RunFor "0.6"']

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "drptoggle.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "drptoggle_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/drptoggle_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
