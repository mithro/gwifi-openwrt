#!/usr/bin/env python3
"""CC-partner PD message injector — drives a live USB-PD negotiation against gale in Renode.

gale is attached as a SINK (GaleAdc PartnerSource presents a source on CC1) and sits in
SNK_DISCOVERY with RX enabled. We then act as the Source's PD-PHY + comparator:
  1. write the BMC/4b5b/CRC-encoded RX capture samples (pd_encode) into pd_phy[0].raw_samples;
  2. tell GaleDma how many sample bytes are staged (TimRxSampleCount) so the TIM1-capture RX
     DMA reports them via dma_bytes_done() without overwriting the buffer;
  3. fire the COMP comparator three times within 20us (GaleExti.FireComp 21) so the real
     pd_rx_handler runs -> pd_rx_start (arms RX) -> pd_rx_event (wakes pd_task);
  4. pd_task -> tcpc_run -> pd_analyze_rx decodes our message from raw_samples and dispatches it.

A full contract additionally needs the partner to answer gale's Request with Accept then
PS_RDY (and the EC auto-sends GoodCRC for received msgs). We inject those after each gale TX
settle window.

Addresses: pd_phy.raw_samples=0x20000638, tcpc pd[0].cc_pull=0x20001107.
Usage: uv run python pd_inject.py [--bin ec-rebuilt.bin] [--boot 2.0] [--dump]
"""
import argparse
import os
import re
import subprocess

import pd_encode

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
RAW = 0x20000638          # pd_phy[0].raw_samples (nm pd_phy)
CCPULL = 0x20001107       # pd[0].cc_pull (tcpc layer); CC1 -> COMP1 -> EXTI line 21
RXHEAD = 0x20001114       # pd[0].rx_head[0] = pd_analyze_rx() return (header, or <0 on fail)
EXTI_COMP_LINE = 21


def stage(msg):
    """Write a message's samples to raw_samples, pad a little, set TimRxSampleCount, and
    fire 3 COMP edges within 20us to wake pd_task through the real RX path."""
    s = pd_encode.encode_message(*msg)
    pad = bytes([(s[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])  # trailing 0-bit edges
    buf = s + pad
    c = ['sysbus WriteByte 0x%X 0x%02X' % (RAW + i, b) for i, b in enumerate(buf)]
    c += ['sysbus.dma1 TimRxSampleCount %d' % len(buf)]
    # 3 comparator edges, ~5us apart (< PD_RX_TRANSITION_WINDOW=20us) -> pd_rx_start
    for _ in range(3):
        c += ['sysbus.exti FireComp %d' % EXTI_COMP_LINE, 'emulation RunFor "0.000005"']
    c += ['emulation RunFor "0.05"']     # let pd_task decode + react (and TX GoodCRC/Request)
    return c


def console(cmd):
    return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (cmd + "\r")] + ['emulation RunFor "0.05"']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=os.path.join(HERE, "ec-rebuilt.bin"))
    ap.add_argument("--boot", default="2.0")
    ap.add_argument("--dump", action="store_true", help="enable firmware PD debug (pd dump 3)")
    args = ap.parse_args()

    cmds = ['$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(args.bin), '$name="pdinj"',
            'include @%s' % BASE,
            'sysbus.adc CcPullAddress 0x%X' % CCPULL, 'sysbus.adc PartnerSource true',
            'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
            'emulation RunFor "%s"' % args.boot]
    if args.dump:
        cmds += console("pd dump 3")
    cmds += console("pd 0 state")                  # SNK_DISCOVERY
    cmds += stage(pd_encode.SRC_CAP)               # inject Source_Capabilities
    cmds += ['sysbus ReadDoubleWord 0x%X' % RXHEAD]  # pd_analyze_rx() return == 0x1161?
    cmds += console("pd 0 state")                  # -> SNK_REQUESTED / sent Request?
    cmds += stage(pd_encode.ACCEPT(1))             # inject Accept
    cmds += console("pd 0 state")                  # -> SNK_TRANSITION?
    cmds += stage(pd_encode.PS_RDY(2))             # inject PS_RDY
    cmds += console("pd 0 state")                  # -> SNK_READY (explicit contract)?
    cmds += ['quit']
    out = subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=400).stdout
    rxh = re.findall(r'^(0x[0-9A-Fa-f]{8})\s*$', out, re.M)
    if rxh:
        v = int(rxh[0], 16)
        print("pd_analyze_rx -> 0x%04X  (%s Source_Caps header 0x1161 decoded LIVE over the CC-partner PD-PHY)"
              % (v & 0xFFFF, "==" if (v & 0xFFFF) == 0x1161 else "!="))
    for ln in out.splitlines():
        if re.search(r'(State:|C0 st\d|Request|Accept|PS_RDY|SrcCap|contract|Rdy|recv)', ln, re.I):
            print(ln[-110:])


if __name__ == "__main__":
    main()
