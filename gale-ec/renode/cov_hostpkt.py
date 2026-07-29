#!/usr/bin/env python3
"""HOST-PACKET-RECEIVE lever — targets host_packet_receive (0x08005314, host_command.c) per
UNCOVERED-BY-FUNCTION.md: the REQUEST_TRUNCATED arm (:259 request_size <= 7 -> a RUNT I2C packet),
the request-copy loops (:278/:313 with real data_len), the struct_version!=3 / INVALID_HEADER arms
(:282/:289/:291), and the driver_result arm (:252 -> an I2C transaction error mid-receive via the
GaleI2c InjectNack/InjectBusErr knobs). Delivered as raw protocol-v3 I2C writes of varied length.
Genuine execution. RO + RW. Accumulates tmp/hostpkt_edges.pkl.
Usage: uv run --python .venv python cov_hostpkt.py [rw]
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
    trace = os.path.join(TMP, "hostpkt.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(scmd, t="0.4"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "%s"' % t]

    def raw(hexstr, t="0.15"):
        return ['sysbus.i2c1 HostCmd "%s"' % hexstr, 'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trhp" @%s PC' % trace]

    # 1) RUNT packets (protocol-3 "da" + < 8 header bytes) -> request_size <= 7 -> REQUEST_TRUNCATED (:259)
    for body in ("", "00", "0003", "00030102", "0003010204", "000301020405", "00030102040506"):
        c += raw("da" + body)
    # 2) struct_version variants (first header byte != 3) -> INVALID_HEADER (:282/:289/:291)
    #    da + [struct_version, checksum, cmd_lo, cmd_hi, ver, rsvd, dlen_lo, dlen_hi, data...]
    for sv in (0x00, 0x02, 0x03, 0x04, 0xFF):
        hdr = [sv, 0x00, 0x01, 0x00, 0x00, 0x00, 0x04, 0x00, 0x44, 0x33, 0x22, 0x11]
        hdr[1] = ((-sum(hdr) - 0xda) & 0xFF)            # checksum so a struct_version==3 one validates
        c += raw("da" + "".join("%02x" % b for b in hdr))
    # 3) VALID packets with real data_len (the request-copy loops :278/:313 iterate)
    c += raw(C._hc_packet(0x0001, 0, 3, 4, [0x44, 0x33, 0x22, 0x11]))   # HELLO 4 data bytes
    c += raw(C._hc_packet(0x0001, 0, 3, 8, [1, 2, 3, 4, 5, 6, 7, 8]))   # 8 data bytes
    c += raw(C._hc_packet(0x0012, 0, 3, 12, list(range(12))))            # FLASH_WRITE 12 bytes (copy loop)
    # 4) DATA-LEN MISMATCH: header data_len field > actual bytes sent -> request_size < hdr+data_len (:295)
    for dlen in (8, 16, 64):
        c += raw(C._hc_packet(0x0001, 0, 3, dlen, [0x44, 0x33]))         # claims dlen but sends 2 bytes
    # 5) I2C transaction ERROR mid-receive -> pkt->driver_result set (:252)
    c += ['sysbus.i2c1 InjectBusErr true'] + raw(C._hc_packet(0x0001, 0, 3, 4, [0x44, 0x33, 0x22, 0x11]))
    c += ['sysbus.i2c1 InjectBusErr false', 'sysbus.i2c1 InjectNack true']
    c += raw(C._hc_packet(0x0001, 0, 3, 4, [0x44, 0x33, 0x22, 0x11]))
    c += ['sysbus.i2c1 InjectNack false']
    c += raw(C._hc_packet(0x0001, 0, 3, 4, [0x44, 0x33, 0x22, 0x11]))    # clean again

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "hostpkt.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "hostpkt_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/hostpkt_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
