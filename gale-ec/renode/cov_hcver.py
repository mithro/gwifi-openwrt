"""HOST-COMMAND-VERSION sweep — the campaign exercised v0 of many EC commands but never v1+, leaving
version-gated paths dark (GPIO_GET v1 alone gave +12). This drives v1 of the gale-compiled multi-version
commands, the highest-value being EC_CMD_USB_PD_CONTROL (0x101) whose v1 response (r_v1) has a flag-check
per PD_FLAGS_* (VCONN_ON / PARTNER_DR_POWER / PARTNER_DR_DATA / PARTNER_USB_COMM / PARTNER_EXTPOWER /
PREVIOUS_PD_CONN) + role/connected/state-name. Those branches need the flags BOTH clear and set, so we
run v1 at boot (flags clear) AND in a SNK_READY contract (via ForcePartnerSrc + early SRC_CAP, flags set).
Also FLASH_INFO(0x10), GET_PROTOCOL_INFO(0x0b), GET_FEATURES(0x0d), GET_CMD_VERSIONS(0x08) v1.
Genuine host-command execution. RO + RW. Usage: uv run --python .venv python cov_hcver.py [rw]
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
    trace = os.path.join(TMP, "hcver.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, ver, data, t="0.12"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, ver, 3, len(data), data),
                'emulation RunFor "%s"' % t]

    def fire(t="0.15"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def deliver(m, t="0.15"):
        return ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire(t)

    PDC = 0x101   # EC_CMD_USB_PD_CONTROL: params {port, role, mux, swap}

    # Boot WITH a sink contract so the PD_FLAGS_* are SET (covers the flag-set arms of the v1 response).
    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForcePartnerSrc true', 'sysbus.adc ForceRaw 3103', 'emulation RunFor "0.4"']
    if RW:
        c += cc("sysjump rw", "0.4") + ['emulation RunFor "0.3"']
    c += ['cpu CreateExecutionTracing "trhv" @%s PC' % trace]

    # PD_CONTROL v0 + v1 BEFORE the contract (flags mostly clear)
    for ver in (0, 1):
        for role, mux, swap in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 2), (0, 0, 3)]:
            c += hc(PDC, ver, [0, role, mux, swap])
    # bad port / bad role / bad mux (validation arms)
    c += hc(PDC, 1, [9, 0, 0, 0]) + hc(PDC, 1, [0, 99, 0, 0]) + hc(PDC, 1, [0, 0, 99, 0])

    # reach SNK_READY (flags PD_FLAGS_* set) then PD_CONTROL v1 -> the flag-SET response arms
    c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    for _ in range(3):
        c += deliver(pe.SRC_CAP, "0.1")
    c += deliver(pe.ACCEPT(1), "0.15") + deliver(pe.PS_RDY(2), "0.3")
    for ver in (0, 1):
        for role in (0, 1, 2, 3):
            c += hc(PDC, ver, [0, role, 0, 0])
    # a data/power swap to set more flags, then PD_CONTROL v1 again
    c += cc("pd 0 swap data") + fire("0.2") + hc(PDC, 1, [0, 0, 0, 0])
    c += cc("pd 0 swap power") + fire("0.2") + hc(PDC, 1, [0, 0, 0, 0])

    # other multi-version commands (v0 + v1)
    for cmd in (0x10, 0x0b, 0x0d):           # FLASH_INFO, GET_PROTOCOL_INFO, GET_FEATURES
        c += hc(cmd, 0, []) + hc(cmd, 1, [])
    # GET_CMD_VERSIONS v1 (u16 cmd) for a few commands
    for q in ([0x01, 0x00], [0x93, 0x00], [0x01, 0x01], [0xff, 0x00]):
        c += hc(0x08, 1, q)

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "hcver.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "hcver_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/hcver_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
