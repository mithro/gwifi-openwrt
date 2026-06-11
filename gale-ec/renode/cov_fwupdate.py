#!/usr/bin/env python3
"""PD-FW-UPDATE lever — targets hc_remote_flash (0x08007a60, ~21 uncovered): the VDM-in-progress
timeout loop `while (pd[port].vdm_state > 0 && get_time().val < timeout.val) task_wait_event(...)`
(usb_pd_protocol.c:3266/3281) + the valid size path (`if (!p->size || p->size%4)` fall-through).
These need a USB_PD_FW_UPDATE host command (EC_CMD 0x110) issued while gale can send a VDM, so
pd_send_vdm sets vdm_state>0 and the wait loop runs. Covered BOTH ways: VDM completes (reactive ACK ->
vdm_state->0 -> early exit) vs VDM hangs (SuppressGoodCrc -> stays>0 -> loop iterates to timeout exit).
Genuine execution. RO + RW. Accumulates tmp/fwupdate_edges.pkl.
Usage: uv run --python .venv python cov_fwupdate.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C
import pd_encode as pe

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


def _le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def _fw(dev, cmd, port, size, data=None):
    return [dev & 0xFF, (dev >> 8) & 0xFF, cmd & 0xFF, port & 0xFF] + _le32(size) + list(data or [])


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
    trace = os.path.join(TMP, "fwupdate.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.04"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.2"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.2"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    def fw(dev, cmd, port, size, data=None, t="0.4"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(0x110, 0, 3, len(_fw(dev, cmd, port, size, data)),
                                                          _fw(dev, cmd, port, size, data)),
                'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    # VDM ACK replies (slots 9..12) so a sent FW-update VDM can COMPLETE in the normal phase
    for k, ack in enumerate([(pe.header(15, 4, 0), [0xFF008042, 0, 0, 0]),
                             (pe.header(15, 1, 0), [0xFF008041]),
                             (pe.header(15, 1, 0), [0xFF008041]),
                             (pe.header(15, 1, 0), [0xFF008041])]):
        c += ['sysbus.dma1 SetReply %d "%s"' % (9 + k, hexmsg(ack))]
    # reach SNK_READY so pd_send_vdm has an active contract
    for mid in (1, 2, 3):
        c += deliver(pe.SRC_CAP) + deliver(pe.ACCEPT(mid)) + deliver(pe.PS_RDY(mid + 1), "0.3")
    c += ['cpu CreateExecutionTracing "trfw" @%s PC' % trace]

    # PHASE 1 (VDM COMPLETES): valid FW-update commands; reactive partner ACKs the VDM -> vdm_state->0
    # -> the wait loop exits early (vdm_state==0 arm).
    for cmd, size, data in [(0, 0, []),                       # USB_PD_FW_REBOOT -> pd_send_vdm
                            (1, 0, []),                       # FLASH_ERASE
                            (3, 0, []),                       # ERASE_SIG
                            (2, 4, [0xDE, 0xAD, 0xBE, 0xEF]), # FLASH_WRITE valid size=4 (size%4==0 arm)
                            (2, 8, [1, 2, 3, 4, 5, 6, 7, 8])]:# FLASH_WRITE size=8
        c += fw(0, cmd, 0, size, data, "0.3")
        c += fire("0.1")                                      # let the VDM exchange + GoodCRC complete

    # PHASE 2 (VDM HANGS -> TIMEOUT): same commands but partner never ACKs -> vdm_state stays >0 ->
    # the `while (vdm_state>0 && time<timeout)` loop iterates and exits via the TIMEOUT arm.
    c += ['sysbus.dma1 SuppressGoodCrc true', 'sysbus.dma1 ReactiveEnabled false']
    for cmd, size, data in [(0, 0, []), (1, 0, []), (3, 0, []), (2, 4, [0xDE, 0xAD, 0xBE, 0xEF])]:
        c += fw(0, cmd, 0, size, data, "0.6")                 # long enough to hit the FW-update timeout
    c += ['sysbus.dma1 SuppressGoodCrc false']
    # invalid-arg arms too (size%4!=0, size=0, bad port) for completeness
    for bad in [_fw(0, 2, 0, 3, [1, 2, 3]), _fw(0, 2, 0, 0, []), _fw(0, 0, 9, 0, []),
                _fw(0, 7, 0, 0, [])]:
        c += ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(0x110, 0, 3, len(bad), bad), 'emulation RunFor "0.1"']

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "fwupdate.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "fwupdate_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/fwupdate_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
