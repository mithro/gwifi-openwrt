#!/usr/bin/env python3
"""DIRECT-CALL host_packet_receive lever (host_command.c:239). The real I2C/SPI transport (cov_hostpkt)
can't set pkt->request_temp (the gale driver never uses a temp buffer) nor force response_max<8, so the
copy-to-temp loops (:278/:313), the ASSERT(response_max>=8) fail (:273), and the struct_version!=3 arm
(:291) stay dark. Here we craft a `struct host_packet` in RAM and CALL host_packet_receive directly
(same legitimacy as cov_flashfault/cov_optbclean — genuine execution of the real captured firmware with
full control of the input), covering every arm deterministically. Unknown command id also drives the
host_command_process not-found loop (:366). Calls BOTH the RO (0x08005314) and RW (0x08015314) copies in
one boot. Accumulates tmp/hcpkt2_edges.pkl.  Usage: uv run --python .venv python cov_hcpkt2.py
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
TMP = os.path.join(HERE, "tmp")

# scratch RAM (below SPIN@0x20003000, above firmware BSS — same region cov_optbclean/cov_flashfault use)
PKT = 0x20002c00          # struct host_packet (28 bytes)
REQ = 0x20002c20          # request buffer
TEMP = 0x20002cb0         # request_temp buffer
RESP = 0x20002d40         # response buffer
STUB = 0x20002e00         # `bx lr` (0x4770): a no-op send_response callback
RECV_OFF = 0x5314         # host_packet_receive within each bank


def hp(send_response, request, request_temp, request_max, request_size,
       response, response_max, response_size, driver_result):
    # struct host_packet: send_response@0 request@4 request_temp@8 request_max@0xc request_size@0xe
    #                     response@0x10 response_max@0x14 response_size@0x16 driver_result@0x18
    return struct.pack("<IIIHHIHHI", send_response & 0xFFFFFFFF, request, request_temp,
                       request_max, request_size, response, response_max, response_size, driver_result)


def build_req(version, command, command_version, data, bad_csum=False):
    """ec_host_request header (8B) + data, with checksum so total byte-sum == 0 (unless bad_csum)."""
    dlen = len(data)
    h = bytearray(struct.pack("<BBHBBH", version, 0, command, command_version, 0, dlen))
    body = bytes(h) + bytes(data)
    cs = (-sum(body)) & 0xFF
    if bad_csum:
        cs = (cs + 1) & 0xFF
    h[1] = cs
    return bytes(h) + bytes(data)


VALID = build_req(3, 0x0001, 0, [0xA0, 0xB1, 0xC2, 0xD3])      # EC_CMD_HELLO + 4 data bytes, csum ok


def scenarios():
    """(label, {addr:bytes writes}, pkt_struct_bytes). All non-panic."""
    out = []
    out.append(("valid_notemp", {REQ: VALID},
                hp(STUB | 1, REQ, 0, 0x80, len(VALID), RESP, 0x80, 0, 0)))
    out.append(("valid_temp", {REQ: VALID},                       # request_temp!=NULL -> copy loops :278/:313
                hp(STUB | 1, REQ, TEMP, 0x80, len(VALID), RESP, 0x80, 0, 0)))
    out.append(("badversion", {REQ: build_req(2, 0x0001, 0, [1, 2, 3, 4])},   # struct_version!=3 -> :291
                hp(STUB | 1, REQ, TEMP, 0x80, 12, RESP, 0x80, 0, 0)))
    out.append(("badcsum", {REQ: build_req(3, 0x0001, 0, [1, 2, 3, 4], bad_csum=True)},  # :318 INVALID_CHECKSUM
                hp(STUB | 1, REQ, TEMP, 0x80, 12, RESP, 0x80, 0, 0)))
    out.append(("runt", {REQ: VALID},                             # request_size<8 -> :259 TRUNCATED
                hp(STUB | 1, REQ, 0, 0x80, 4, RESP, 0x80, 0, 0)))
    out.append(("toobig", {REQ: VALID},                           # request_size>request_max -> :265 TRUNCATED
                hp(STUB | 1, REQ, 0, 0x40, 0x60, RESP, 0x80, 0, 0)))
    # data_len=100 but request_size=8 -> :303 TRUNCATED params
    h = bytearray(struct.pack("<BBHBBH", 3, 0, 0x0001, 0, 0, 100)); h[1] = (-sum(h)) & 0xFF
    out.append(("truncparams", {REQ: bytes(h)},
                hp(STUB | 1, REQ, 0, 0x80, 8, RESP, 0x80, 0, 0)))
    out.append(("driver_err", {REQ: VALID},                       # pkt->driver_result!=0 -> :252
                hp(STUB | 1, REQ, 0, 0x80, len(VALID), RESP, 0x80, 0, 1)))
    out.append(("unknown_cmd", {REQ: build_req(3, 0xEEEE, 0, [])},  # host_command_process not-found :366
                hp(STUB | 1, REQ, 0, 0x80, 8, RESP, 0x80, 0, 0)))
    out.append(("valid_respond", {REQ: VALID},                    # send_response = real host_packet_respond
                hp(0x08004e80 | 1, REQ, 0, 0x80, len(VALID), RESP, 0x80, 0, 0)))
    return out


# ASSERT(response_max>=8) fail -> panic; isolate (the call won't return to the trap).
PANIC = ("assert_respmax", {REQ: VALID}, hp(STUB | 1, REQ, 0, 0x80, len(VALID), RESP, 4, 0, 0))


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
    executed, edges = set(), set()
    out = os.path.join(TMP, "hcpkt2_edges.pkl")
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass
    trace = os.path.join(TMP, "hcpkt2.txt")

    def one_call(base, label, mem, pkt, tmo):
        """Fresh session per call -> a non-returning call (RW dispatcher wedge / ASSERT panic) only
        times out ITS call; the trace up to the wedge is still folded, covering the path through
        host_packet_receive before the wedge."""
        if os.path.exists(trace):
            os.remove(trace)
        s = fcall.Session(CAPTURED, boot="1.5", trace=trace)
        try:
            s.rsp.writemem(STUB, b"\x70\x47")        # bx lr
            for a, d in mem.items():
                s.rsp.writemem(a, d)
            s.rsp.writemem(PKT, pkt)
            try:
                r = s.rsp.call(base + RECV_OFF, (PKT,), timeout_continue=tmo)
                print("  %08x %-14s -> r0=0x%x" % (base + RECV_OFF, label, r & 0xFFFFFFFF))
            except Exception as e:
                print("  %08x %-14s -> (no-return) %s" % (base + RECV_OFF, label, type(e).__name__))
        finally:
            s.close()
            fold(trace, executed, edges)

    # RO bank: one session is fine (all RO calls return cleanly). RW bank: fresh session PER call so
    # the dispatcher-wedge on the deep scenarios can't cascade across the whole bank.
    if os.path.exists(trace):
        os.remove(trace)
    s = fcall.Session(CAPTURED, boot="1.5", trace=trace)
    try:
        s.rsp.writemem(STUB, b"\x70\x47")
        for label, mem, pkt in scenarios():
            for a, d in mem.items():
                s.rsp.writemem(a, d)
            s.rsp.writemem(PKT, pkt)
            try:
                r = s.rsp.call(0x08000000 + RECV_OFF, (PKT,), timeout_continue=8)
                print("  %08x %-14s -> r0=0x%x" % (0x08000000 + RECV_OFF, label, r & 0xFFFFFFFF))
            except Exception as e:
                print("  %08x %-14s -> (no-return) %s" % (0x08000000 + RECV_OFF, label, type(e).__name__))
    finally:
        s.close()
        fold(trace, executed, edges)

    for label, mem, pkt in scenarios():
        one_call(0x08010000, label, mem, pkt, 8)

    # ASSERT(response_max>=8) fail -> panic; isolate per bank.
    for base in (0x08000000, 0x08010000):
        one_call(base, PANIC[0], PANIC[1], PANIC[2], 4)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/hcpkt2_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
