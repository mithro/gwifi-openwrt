#!/usr/bin/env python3
"""KEYSTONE DIAGNOSTIC: localize exactly where USB-PD RX reception breaks in SNK_DISCOVERY.

Counts three points along the RX chain while running the PROVEN contract setup (ForceSourceCc sink
attach + staged Source_Cap + ReactiveEnabled + FireComp), so the pattern of zero/nonzero counters
pinpoints the fault (rather than theorizing):
  C = pd_rx_process call site (0x0800a092) -> the RX-process path ran at all
  A = pd_analyze_rx entry  (0x08009eb0)    -> the DMA delivered sample bytes and decode was invoked
  B = handle_request split (0x08008172)    -> a decoded message was dispatched to the policy engine
Also samples pd[0].task_state (0x20001156)/last_state and raw_samples[0] (0x20000790) at the end.

Read-only on the firmware (hooks + counters in scratch RAM); no faked branches. Serial + mem-capped.
"""
import os
import subprocess

import coverage_captured as C
import pd_encode

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")

# scratch counters (in RAM, away from the boot stack / driver globals)
A, B, Cc, DBG = 0x20002F00, 0x20002F04, 0x20002F08, 0x20002F0C


def hexmsg(m):
    sm = pd_encode.encode_message(*m)
    return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()


def _hook_script():
    src = (
        "from Antmicro.Renode.Core import EmulationManager\n"
        "mc = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]\n"
        "cpu = mc[\"sysbus.cpu\"]\n"
        "sb = mc.SystemBus\n"
        "def mk(addr):\n"
        "    def f(c, pc):\n"
        "        sb.WriteDoubleWord(addr, sb.ReadDoubleWord(addr) + 1)\n"
        "    return f\n"
        "cpu.AddHook(0x08009eb0, mk(0x20002F00))\n"   # A pd_analyze_rx
        "cpu.AddHook(0x08008172, mk(0x20002F04))\n"   # B handle_request dispatch
        "cpu.AddHook(0x0800a092, mk(0x20002F08))\n"   # C pd_rx_process call site
        "cpu.AddHook(0x0800a170, mk(0x20002F08))\n")  # C (second pd_analyze_rx call site)
    p = os.path.join(TMP, "diag_rx_hook.py")
    with open(p, "w") as f:
        f.write(src)
    return p


def main():
    os.makedirs(TMP, exist_ok=True)
    hookf = _hook_script()
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true',
         'emulation RunFor "1.5"']                    # boot; gale enters sink DISCOVERY
    # zero the counters AFTER boot, install hooks, THEN drive the contract
    c += ['sysbus WriteDoubleWord 0x%X 0' % A, 'sysbus WriteDoubleWord 0x%X 0' % B,
          'sysbus WriteDoubleWord 0x%X 0' % Cc, 'sysbus WriteDoubleWord 0x%X 0' % DBG,
          'include @%s' % hookf,
          'sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]

    def fire(t):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def state():                                       # snapshot task_state to observe progression
        return ['sysbus ReadByte 0x20001156']

    # PROPER sink negotiation sequence: SRC_CAP -> (gale sends Request) -> ACCEPT -> PS_RDY -> SNK_READY.
    # ReactiveEnabled lets the C# partner auto-GoodCRC gale's TX; we deliver the policy replies in order.
    c += state()
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.SRC_CAP)] + fire("0.2") + state()
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.ACCEPT(1))] + fire("0.2") + state()
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.PS_RDY(2))] + fire("0.3") + state()
    # a couple more cycles in case msg_id / timing needs a retry
    for mid in (3, 4):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.SRC_CAP)] + fire("0.2") + state()
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.ACCEPT(mid))] + fire("0.2") + state()
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.PS_RDY(mid + 1))] + fire("0.3") + state()
    # report
    c += ['sysbus ReadDoubleWord 0x%X' % A, 'sysbus ReadDoubleWord 0x%X' % B,
          'sysbus ReadDoubleWord 0x%X' % Cc,
          'sysbus ReadByte 0x20001156', 'sysbus ReadByte 0x20001157',
          'sysbus ReadDoubleWord 0x20000790', 'quit']
    rescf = os.path.join(TMP, "diag_rx.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    out = subprocess.run(C._renode_cmd("include @%s" % rescf),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, timeout=300).stdout
    # the ReadDoubleWord/ReadByte results print as "0x..." lines near the end
    print(out[-2500:])


if __name__ == "__main__":
    main()
