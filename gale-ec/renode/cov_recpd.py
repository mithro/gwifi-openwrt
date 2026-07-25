"""REC + PD-CONSOLE lever — two console-command veins the campaign under-swept:
 (1) command_rec (board.c:394, the `rec` cmd): argc>1 false (`rec`), parse_bool true/false
     (`rec on`/`rec off`/`rec bogus`), and the gpio_get_level ternary "OFF"/"ON" (GPIO_ENTERING_REC
     driven to both levels by rec on=OUT_LOW and rec off=INPUT).
 (2) command_pd (usb_pd_protocol.c:2882-3069) subcommands: `dualrole` SET each drp_state
     (on/off/sink/source) then read-back (no-arg) to hit every `case PD_DRP_*` print arm; plus
     `bist`, `charger`, `dev <v>`, the VDM sends `ping`/`curr`/`vers`, `state`, and the param-error
     arms (`dev` missing, `ping x` PARAM4, `pd 0 xyz` PARAM_COUNT).
Genuine console execution. RO + RW. Accumulates tmp/recpd_edges.pkl.
Usage: uv run --python .venv python cov_recpd.py [rw]
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
    trace = os.path.join(TMP, "recpd.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.08"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trrp" @%s PC' % trace]

    # --- `gale` console command + its rec subcommand: every arm ---
    # command_rec is a SUBCOMMAND of `gale` (gale_subcommands[]), invoked `gale rec ...`.
    c += cc("gale")               # argc<2 -> dump: calls every subcommand handler with argc=1
    c += cc("gale rec")           # rec argc==1 -> argc>1 false, print-only
    c += cc("gale rec on")        # parse_bool true, v=1 -> GPIO_OUT_LOW (level ON), "OK"
    c += cc("gale rec")           # read-back: gpio_get_level -> "ON"
    c += cc("gale rec off")       # parse_bool true, v=0 -> GPIO_INPUT (level OFF)
    c += cc("gale rec")           # read-back: gpio_get_level -> "OFF"
    c += cc("gale rec bogus")     # parse_bool false -> skip OK, print-only
    c += cc("gale rec 1")         # parse_bool true (numeric)
    c += cc("gale rec 0")         # parse_bool true (numeric)
    # other gale subcommands with args (exercise their parse arms too)
    c += cc("gale cc")
    c += cc("gale vbus")
    c += cc("gale polarity")
    c += cc("gale power")
    c += cc("gale dev")
    c += cc("gale bogus")         # unknown subcommand

    # --- pd dualrole: SET each drp_state, then no-arg read-back hits each case ---
    for sub in ("on", "off", "sink", "source"):
        c += cc("pd 0 dualrole %s" % sub)
        c += cc("pd 0 dualrole")          # no-arg -> switch(drp_state) print arm
    # --- pd subcommands ---
    c += cc("pd 0 state")
    c += cc("pd 0 bist", "0.15")
    c += cc("pd 0 charger", "0.2")
    c += cc("pd 0 dev 5000", "0.15")
    c += cc("pd 0 dev 20000", "0.15")
    # VDM sends (need a port that accepts; just exercise the dispatch arms)
    c += cc("pd 0 ping", "0.12")
    c += cc("pd 0 curr", "0.12")
    c += cc("pd 0 vers", "0.12")
    c += cc("pd 0 ping 1", "0.12")        # ping with enable arg
    # param-error arms
    c += cc("pd 0 dev")                   # missing voltage
    c += cc("pd 0 ping x")                # PARAM4 (*e != 0)
    c += cc("pd 0 xyz")                   # PARAM_COUNT (unknown subcmd)
    c += cc("pd 9 state")                 # bad port
    c += cc("pd")                         # no subcmd

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "recpd.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "recpd_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/recpd_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
