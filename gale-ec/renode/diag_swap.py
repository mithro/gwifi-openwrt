#!/usr/bin/env python3
"""Diagnostic: pinpoint WHERE a gale-initiated DR_Swap stalls. Boot, establish a SNK contract, read
pd[0].task_state at each step (0x20001156), issue `pd 0 swap data`, blanket-fire COMP, re-read state.
Prints the task_state sequence so we can see whether gale reaches SNK_READY(9) then DR_SWAP(27) then
returns. Captured-firmware only. One renode, memory-capped."""
import os
import re
import subprocess

import pd_encode as pe
import coverage_captured as CC

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TS = 0x20001156   # pd[0].task_state


def hexmsg(m):
    sm = pe.encode_message(*m)
    return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()


def cc(scmd):
    return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]


def blanket(reps, gap="0.0015"):
    f = []
    for _ in range(reps):
        f += ['sysbus.exti FireComp 21', 'emulation RunFor "%s"' % gap]
    return f


def main():
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true',
         'sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    # boot with the partner ACTIVE: stage the contract messages and blanket COMP THROUGHOUT boot so
    # gale catches Source_Cap while in SNK_DISCOVERY (instead of exhausting hard resets unanswered).
    c += ['emulation RunFor "0.4"']                          # let pd_init run
    c += ['sysbus ReadByte 0x%X' % TS]                       # [0] early boot state
    for rep in range(12):
        for m in (pe.SRC_CAP, pe.ACCEPT(1), pe.PS_RDY(2)):
            c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
        c += ['sysbus.dma1 ExpectContractMsg']
        c += blanket(10) + ['emulation RunFor "0.03"']
    c += ['sysbus ReadByte 0x%X' % TS]                       # [1] state after contract attempt
    c += cc("pd 0 state") + ['emulation RunFor "0.05"']      # dump state to console too
    c += cc("pd 0 swap data") + ['emulation RunFor "0.003"']
    c += ['sysbus ReadByte 0x%X' % TS]                       # [2] state right after swap cmd
    for _ in range(20):
        c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.0015"', 'sysbus ReadByte 0x%X' % TS]  # [3..22] during blanket
    c += cc("pd 0 state") + ['emulation RunFor "0.05"']
    c += ['quit']
    out = subprocess.run(CC._renode_cmd("; ".join(c)),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=400).stdout
    vals = [int(x, 16) for x in re.findall(r'^(0x[0-9A-Fa-f]+)\s*$', out, re.M)]
    names = {0: "DISABLED", 1: "SUSPENDED", 2: "SNK_DISCONNECTED", 3: "DEBOUNCE", 4: "SNK_ACCESSORY",
             5: "SNK_HARD_RST_REC", 6: "SNK_DISCOVERY", 7: "SNK_REQUESTED", 8: "SNK_TRANSITION",
             9: "SNK_READY", 27: "DR_SWAP", 35: "SOFT_RESET"}
    print("task_state sequence (post-boot, post-contract, post-swap-cmd, then 20x during blanket):")
    print("  [0] boot      =", vals[0] if len(vals) > 0 else "?",
          names.get(vals[0], "") if len(vals) > 0 else "")
    print("  [1] contract  =", vals[1] if len(vals) > 1 else "?",
          names.get(vals[1], "") if len(vals) > 1 else "")
    print("  [2] post-swap =", vals[2] if len(vals) > 2 else "?",
          names.get(vals[2], "") if len(vals) > 2 else "")
    seq = vals[3:23]
    print("  [3..] blanket =", " ".join("%d" % v for v in seq))
    # console state-dump lines
    for ln in out.splitlines():
        if "St:" in ln or "state" in ln.lower() and "0x" not in ln:
            print("  console:", ln.strip()[:100])


if __name__ == "__main__":
    main()
