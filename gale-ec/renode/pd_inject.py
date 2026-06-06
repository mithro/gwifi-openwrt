#!/usr/bin/env python3
"""CC-partner PD message injector — drives a live USB-PD negotiation against gale in Renode.

Prereq: gale is attached as a SINK (GaleAdc PartnerSource=true presents a source on CC1),
so pd_task sits in SNK_DISCOVERY with rx_enabled. We then act as the Source's PD-PHY:
  1. write the BMC/4b5b/CRC-encoded RX capture samples (pd_encode) into pd_phy[0].raw_samples;
  2. arm the RX path the firmware checks — RX DMA ch2 EN with CNDTR=0 (dma_bytes_done=full),
     and TIM1 CR1.EN=1 (pd_rx_started() true);
  3. let pd_task's next loop run tcpc_run -> pd_analyze_rx, which decodes our message and
     dispatches it (handle_request).
No IRQ is required: tcpc_run polls pd_rx_started() every pd_task iteration.

Addresses (rebuilt + original share these — pd_phy is at the same .bss addr in RO/RW):
  pd_phy.raw_samples = 0x20000638 ; TIM1 CR1 = 0x40012C00 ; DMA ch2 CCR=0x4002001C CNDTR=0x40020020

Usage: uv run python pd_inject.py [--bin ec-rebuilt.bin] [--boot 2.0]
"""
import argparse
import os
import re
import subprocess

import pd_encode

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
RAW = 0x20000638          # pd_phy[0].raw_samples (nm pd_phy)
TIM1_CR1 = 0x40012C00
DMA2_CCR = 0x4002001C
DMA2_CNDTR = 0x40020020
CCPULL = 0x20001107       # pd[0].cc_pull (tcpc layer)


def write_samples(samples):
    """Monitor commands to write the sample bytes into raw_samples (byte writes)."""
    return ['sysbus WriteByte 0x%X 0x%02X' % (RAW + i, b) for i, b in enumerate(samples)]


def arm_rx():
    """Arm the RX path so pd_rx_started() is true and dma_bytes_done() reports full."""
    return ['sysbus WriteDoubleWord 0x%X 0' % DMA2_CNDTR,      # CNDTR=0 -> no transfer on EN
            'sysbus WriteDoubleWord 0x%X 1' % DMA2_CCR,        # CCR.EN=1 (dma_bytes_done sees EN)
            'sysbus WriteDoubleWord 0x%X 1' % TIM1_CR1]        # TIM1 CR1.EN=1 (pd_rx_started)


def inject(msg, settle="0.12"):
    """Write a message's samples + arm RX + let pd_task decode it."""
    h, objs = msg
    s = pd_encode.encode_message(h, objs)
    return write_samples(s) + arm_rx() + ['emulation RunFor "%s"' % settle]


def console(cmd):
    c = ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (cmd + "\r")]
    return c + ['emulation RunFor "0.05"']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=os.path.join(HERE, "ec-rebuilt.bin"))
    ap.add_argument("--boot", default="2.0")
    args = ap.parse_args()

    cmds = ['$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(args.bin), '$name="pdinj"',
            'include @%s' % BASE,
            'sysbus.adc CcPullAddress 0x%X' % CCPULL, 'sysbus.adc PartnerSource true',
            'showAnalyzer sysbus.usart1 Antmicro.Renode.Analyzers.LoggingUartAnalyzer',
            'emulation RunFor "%s"' % args.boot]
    cmds += console("pd 0 state")                              # should show SNK_DISCOVERY
    cmds += inject(pd_encode.SRC_CAP)                          # inject Source_Capabilities
    cmds += console("pd 0 state")                              # did it advance / send Request?
    cmds += inject(pd_encode.ACCEPT(1))                        # inject Accept
    cmds += console("pd 0 state")
    cmds += inject(pd_encode.PS_RDY(2))                        # inject PS_RDY -> SNK_READY?
    cmds += console("pd 0 state")
    cmds += ['quit']
    out = subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(cmds)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=400).stdout
    # print just the PD state lines + any PD console chatter
    for ln in out.splitlines():
        if re.search(r'(State:|SNK_|SRC_|C0 st\d|Request|Accept|PS_RDY|contract|RX|CRC|EVT)', ln):
            print(ln)


if __name__ == "__main__":
    main()
