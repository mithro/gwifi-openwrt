#!/usr/bin/env python3
"""DIRECT-CALL host-command lever for the residual host_command.c functions the transport can't reach:
  * host_command_received (0x080052d0): the `if (args->command == EC_CMD_REBOOT)` and `if (args->result)`
    arms — call with command=REBOOT (resets, no return) and with result!=0.
  * host_packet_respond (0x08004e80): the `response_size > response_max - sizeof(*r)` "too big" arm —
    prime pkt0 via a real host_packet_receive, then call respond with an oversized response_size.
  * host_command_process (0x080051c0): host_command_debug_request's repeat-suppress
    `command == hc_prev_cmd` arm (two back-to-back same-command calls) + find_host_command match/no-match.
Fresh session per scenario (a non-returning REBOOT call only times out itself). Both RO+RW banks.
Accumulates tmp/hccmd2_edges.pkl.  Usage: uv run --python .venv python cov_hccmd2.py
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
TMP = os.path.join(HERE, "tmp")

ARGS = 0x20002c00         # struct host_cmd_handler_args (28B)
PKT = 0x20002c40          # struct host_packet (28B), for priming pkt0
REQ = 0x20002c80          # request buffer
RESP = 0x20002d40         # response buffer
STUB = 0x20002e00         # bx lr
OFF = {"received": 0x52d0, "process": 0x51c0, "respond": 0x4e80, "receive": 0x5314}
EC_CMD_HELLO = 0x0001
EC_CMD_REBOOT = 0xD1


def hca(command, result, send_response=None, version=0, params=0, params_size=0,
        response=RESP, response_max=0x80, response_size=0):
    sr = (STUB | 1) if send_response is None else send_response
    # send_response@0 command@4 version@6 params@8 params_size@0xc response@0x10
    # response_max@0x14 response_size@0x16 result@0x18
    return struct.pack("<IHBxIH2xIHHI", sr & 0xFFFFFFFF, command, version, params,
                       params_size, response, response_max, response_size, result)


def hpkt(send_response, request, request_temp, request_max, request_size,
         response, response_max, response_size, driver_result):
    return struct.pack("<IIIHHIHHI", send_response & 0xFFFFFFFF, request, request_temp,
                       request_max, request_size, response, response_max, response_size, driver_result)


def valid_req():
    h = bytearray(struct.pack("<BBHBBH", 3, 0, EC_CMD_HELLO, 0, 0, 4)) + bytes([0xA0, 0xB1, 0xC2, 0xD3])
    h[1] = (-sum(h)) & 0xFF
    return bytes(h)


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
    out = os.path.join(TMP, "hccmd2_edges.pkl")
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
        except Exception:
            pass
    trace = os.path.join(TMP, "hccmd2.txt")

    def session(fn, tmo_note=""):
        if os.path.exists(trace):
            os.remove(trace)
        s = fcall.Session(CAPTURED, boot="1.5", trace=trace)
        try:
            s.rsp.writemem(STUB, b"\x70\x47")
            fn(s)
        except Exception as e:
            print("  session EXC %s %s" % (tmo_note, e))
        finally:
            s.close()
            fold(trace, executed, edges)

    for base in (0x08000000, 0x08010000):
        def call(s, name, addr_args, tmo=8):
            for a, d in addr_args:
                s.rsp.writemem(a, d)
            faddr = base + OFF[name.split(":")[0]]
            try:
                r = s.rsp.call(faddr, (ARGS if name != "respond_prime" else PKT,), timeout_continue=tmo)
                print("  %08x %-22s -> r0=0x%x" % (faddr, name, r & 0xFFFFFFFF))
            except Exception as e:
                print("  %08x %-22s -> (no-return) %s" % (faddr, name, type(e).__name__))

        # 1) host_command_received with result!=0  (the `if (args->result)` true arm)
        session(lambda s, b=base: call(s, "received:result", [(ARGS, hca(EC_CMD_HELLO, 5))]))
        # 1b) host_command_received with command==EC_CMD_GET_COMMS_STATUS(9), result=0
        #     -> the `else if (args->command == EC_CMD_GET_COMMS_STATUS)` arm (host_command.c:165)
        session(lambda s, b=base: call(s, "received:comms_status", [(ARGS, hca(0x0009, 0))]))
        # 2) host_command_received with command==EC_CMD_REBOOT (resets; no return)
        session(lambda s, b=base: call(s, "received:reboot", [(ARGS, hca(EC_CMD_REBOOT, 0))], tmo=4))
        # 3) host_command_process: find_host_command MATCH (HELLO) then a 2nd same call (repeat-suppress)
        def proc_repeat(s):
            s.rsp.writemem(ARGS, hca(EC_CMD_HELLO, 0))
            f = base + OFF["process"]
            for _ in range(2):
                try:
                    s.rsp.call(f, (ARGS,), timeout_continue=8)
                except Exception:
                    pass
            print("  %08x process:repeat            -> done" % f)
        session(proc_repeat)
        # 4) host_command_process: unknown command -> find_host_command no-match
        session(lambda s, b=base: call(s, "process:notfound", [(ARGS, hca(0xEEEE, 0))]))
        # 5) host_packet_respond too-big: prime pkt0 via receive, then respond with response_size>max-8
        def respond_toobig(s):
            s.rsp.writemem(REQ, valid_req())
            s.rsp.writemem(PKT, hpkt(STUB | 1, REQ, 0, 0x80, len(valid_req()), RESP, 0x80, 0, 0))
            try:
                s.rsp.call(base + OFF["receive"], (PKT,), timeout_continue=8)   # sets pkt0/args0
            except Exception:
                pass
            s.rsp.writemem(ARGS, hca(EC_CMD_HELLO, 0, response_size=200))
            try:
                r = s.rsp.call(base + OFF["respond"], (ARGS,), timeout_continue=8)
                print("  %08x respond:toobig           -> r0=0x%x" % (base + OFF["respond"], r & 0xFFFFFFFF))
            except Exception as e:
                print("  %08x respond:toobig           -> (no-return) %s" % (base + OFF["respond"], type(e).__name__))
        session(respond_toobig)

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/hccmd2_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
