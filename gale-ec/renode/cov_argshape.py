#!/usr/bin/env python3
"""ARGUMENT-SHAPE console lever — drives the captured firmware's console commands with the EXACT
argv forms each handler parses, to cover the per-command dark arms identified in UNCOVERED-BY-FUNCTION
(adc/help/md/reboot/spixfer/sysjump/pd/typec). Sources read from the rebuilt tree to get keywords:
  * adc <name>      : channel names are CC1/CC2/VBUS/CUR (board.c adc_channels[]); bad name -> PARAM1.
  * md .b/.h/.s ADDR: size suffix is a SEPARATE first arg ".b" (argv[1][0]=='.' && len==2), NOT "md.b";
                      bad suffix ".x" -> PARAM1; count arg drives the num loop.
  * typec [debug|PORT [none|usb|dp|dock]] : port must be < CONFIG_USB_PD_PORT_COUNT (=1) -> `typec 1`
                      and `typec x` hit the reject arm; `typec 0 <mux>` walks the mux_name[] loop.
  * spixfer rlen|w DEV OFF VAL : needs EXACTLY 5 args (argc!=5 -> PARAM_COUNT); VAL>32 -> PARAM4 bound.
  * pd <sub> ...    : dualrole/dump/enable/trysrc + per-port tx/bist/charger/dev/hard/info/soft/swap/ping.
  * RESET-SAFE keyword walks: `reboot cancel`+`reboot bad` and `sysjump disable`+`sysjump bad` walk the
    strcasecmp chains WITHOUT resetting/jumping; the genuinely-resetting `reboot hard` is fed LAST.
Genuine console execution of the captured firmware (RO + RW). Accumulates tmp/argshape_edges.pkl.
Usage: uv run --python .venv python cov_argshape.py [rw]
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

# Non-resetting commands first; the one genuinely-resetting command (`reboot hard`) goes LAST so its
# pre-reset keyword/flag branches are traced without truncating the rest of the run.
CMDS = [
    # --- adc: find_adc_channel_by_name match (valid) + miss (PARAM1) ---
    "adc", "adc CC1", "adc CC2", "adc VBUS", "adc CUR", "adc NOPE",
    # --- md: '.'-suffix size selector (separate arg) + count loop ---
    "md .b 0x20000000", "md .h 0x20000000", "md .s 0x20000000", "md .x 0x20000000",
    "md .b 0x20000000 8", "md 0x20000000 5", "md .h 0x20000000 4",
    # --- help: shorthelp arm + prefix listing ---
    "help reboot", "help pd", "help typec", "help adc", "help spixfer", "help s", "help re", "help zzz",
    # --- spixfer: argc!=5 + per-arg strtoi PARAM + rlen length bound ---
    "spixfer", "spixfer rlen 0 0 4", "spixfer w 0 0 0x55", "spixfer rlen 0 0 99",
    "spixfer x 0 0 0", "spixfer rlen z 0 0", "spixfer rlen 0 z 0", "spixfer rlen 0 0 z",
    # --- sysjump: keyword chain WITHOUT jumping (disable + bad-addr) ---
    "sysjump disable", "sysjump zzz",
    # --- reboot: keyword chain WITHOUT resetting (cancel returns early; bad -> PARAM1) ---
    "reboot cancel", "reboot nope",
    # --- pd: subcommand + per-port action keyword arms ---
    "pd", "pd dualrole", "pd dualrole on", "pd dualrole off", "pd dualrole sink",
    "pd dualrole source", "pd dualrole bad", "pd dump", "pd dump 2", "pd dump bad",
    "pd enable", "pd enable 0", "pd enable 1", "pd trysrc", "pd trysrc on", "pd trysrc off",
    "pd 0", "pd 0 state", "pd 0 tx", "pd 0 bist_rx", "pd 0 bist_tx", "pd 0 charger",
    "pd 0 dev", "pd 0 dev 9000", "pd 0 hard", "pd 0 info", "pd 0 soft",
    "pd 0 swap", "pd 0 swap power", "pd 0 swap data", "pd 0 swap vconn",
    "pd 0 ping", "pd 0 ping on", "pd 5", "pd 0 bogus",
    # --- typec: port reject + mux_name[] loop ---
    "typec", "typec debug", "typec 0", "typec 1", "typec x",
    "typec 0 none", "typec 0 usb", "typec 0 dp", "typec 0 dock", "typec 0 bad",
    # set each mux state then PRINT (argc<3) so usb_mux_get returns different dp_str/usb_str combos,
    # covering the print-path ternary arms (dp_str?/usb_str?/both) at 0x0800b9ae/b9b8/b9be.
    "typec 0 none", "typec 0", "typec 0 usb", "typec 0", "typec 0 dp", "typec 0",
    "typec 0 dock", "typec 0",
]
# Resetting commands LAST (each truncates whatever follows it):
RESET_LAST = ["reboot hard"]


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
    trace = os.path.join(TMP, "argshape.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.15"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trcs" @%s PC' % trace]
    for cmd in CMDS:
        # pd/spixfer do more work (state machine / SPI) -> give them a little longer
        c += cc(cmd, "0.25" if cmd.startswith(("pd ", "spixfer")) else "0.15")
    for cmd in RESET_LAST:
        c += cc(cmd, "0.4")
    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "argshape.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "argshape_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/argshape_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
