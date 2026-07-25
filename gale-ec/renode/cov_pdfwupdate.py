"""PD-FW-UPDATE lever — drives hc_remote_flash (usb_pd_protocol.c:3198, EC_CMD_USB_PD_FW_UPDATE=0x110),
a BLOCKING dispatcher the campaign never sends: it pd_send_vdm()s a firmware-update VDM then busy-waits
`while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val)) task_wait_event(...)` (:3267/:3281)
and returns TIMEOUT / SUCCESS / ERROR by vdm_state (:3273/:3284). Direct invocation can't cover this
(the wait loop needs the live PD task advancing vdm_state); so we bring up a real sink contract (like
pddbg) THEN send the FW_UPDATE subcommands over i2c so the VDM is actually queued and the wait loop runs.
With no partner VDM completion, vdm_state stays > 0 -> the loop iterates and exits on TIMEOUT (:3284 true);
the reactive GoodCRC/response path gives some VDMs a chance to retire vdm_state for the success arm.
Subcmds REBOOT(0)/FLASH_ERASE(1)/FLASH_WRITE(2)/ERASE_SIG(3) + the size%4 / size==0 INVALID_PARAM arms +
a bad subcmd default. Genuine host-cmd execution. RO + RW. Accumulates tmp/pdfwupdate_edges.pkl.
Usage: uv run --python .venv python cov_pdfwupdate.py [rw]
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


def hexmsg(m):
    sm = pe.encode_message(*m)
    return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()


def le16(v):
    return [v & 0xFF, (v >> 8) & 0xFF]


def le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


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
    trace = os.path.join(TMP, "pdfwupdate.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def fire(t="0.15"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.15"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    # ec_params_usb_pd_fw_update {u16 dev_id, u8 cmd, u8 port, u32 size, <data>}
    def fwu(cmd, port=0, size=0, data=None, t="0.7"):
        data = data or []
        payload = le16(0x00AA) + [cmd & 0xFF, port & 0xFF] + le32(size) + list(data)
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(0x0110, 0, 3, len(payload), payload),
                'emulation RunFor "%s"' % t]

    # Bring up a sink contract so pd_send_vdm() actually queues (port connected). (pddbg pattern.)
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "0.4"']
    if RW:
        c += cc("sysjump rw", "0.4") + ['emulation RunFor "0.3"']
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['cpu CreateExecutionTracing "trfwu" @%s PC' % trace]

    # reach SNK_READY (early SRC_CAP -> Accept -> PS_RDY)
    for _ in range(3):
        c += deliver(pe.SRC_CAP, "0.1")
    c += deliver(pe.ACCEPT(1), "0.15") + deliver(pe.PS_RDY(2), "0.3")

    # --- FW_UPDATE subcommand battery (each enters hc_remote_flash + its wait loop) ---
    # Generous RunFor (>0.5s) so the 500ms VDM timeout fires -> :3284 TIMEOUT arm.
    c += fwu(0, size=0, t="0.7")               # REBOOT
    c += fwu(3, size=0, t="0.7")               # ERASE_SIG -> VDO_CMD_ERASE_SIG + common wait loop
    c += fwu(1, size=0, t="0.7")               # FLASH_ERASE + common wait loop
    c += fwu(2, size=8, data=[0] * 8, t="0.7")  # FLASH_WRITE (mult of 4) -> per-chunk loop (:3267)
    c += fwu(2, size=16, data=[0] * 16, t="0.8")  # FLASH_WRITE larger -> multiple chunks
    # validation arms
    c += fwu(2, size=0, data=[], t="0.1")      # FLASH_WRITE size==0 -> INVALID_PARAM (:3256)
    c += fwu(2, size=3, data=[0, 0, 0], t="0.1")  # size % 4 != 0 -> INVALID_PARAM
    c += fwu(9, size=0, t="0.1")               # bad subcmd -> default INVALID_PARAM
    c += fwu(1, port=9, size=0, t="0.1")       # bad port

    # A second contract cycle delivering a VDM response so a VDM can retire (success-ish arm)
    for _ in range(2):
        c += deliver((pe.header(15, 1, 4), [0xFF008041]), "0.1")   # a VDM ACK-ish frame
    c += fwu(3, size=0, t="0.7")               # ERASE_SIG again with VDM responses staged

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "pdfwupdate.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "pdfwupdate_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/pdfwupdate_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
