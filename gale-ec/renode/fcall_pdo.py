#!/usr/bin/env python3
"""Targeted coverage of the PDO-selector at RO 0x080072f0 / RW 0x080172f0 (a pd_find_pdo_index /
pd_extract_pdo_power style routine from usb_pd_protocol.c). It iterates src_caps[cnt], decodes each
PDO (bits[31:30]=type, with type==1=battery; voltage/current fields scaled x50mV / x10mA), clamps to
max_request_mv (RAM global 0x20001f20 vs 5000mV), and selects the best-power PDO. The fixed cprintf/
contract paths never feed it battery/variable PDOs or an over-limit voltage, so ~10 branches/bank are
uncovered. We drive it directly with CRAFTED PDO arrays (genuine execution — the switch reads real
injected PDO words; never faked).

Signature (decoded):
  f(r0=cnt, r1=src_caps*, r2=max_ma, r3=*out_pwr, stack[0]=*out_mv, stack[1]=flag_byte)
    flag != 0 -> selection loop over cnt PDOs; flag == 0 -> use PDO[0] directly (0x8007380 path).

Accumulates tmp/pdo_edges.pkl (unioned by combine_coverage.py). Serial + memory-capped via fcall.
"""
import os
import pickle
import struct

import fcall

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")

PDO = 0x20002000           # src_caps array
OUT_PWR = 0x20002400       # *out_pwr (r3)
OUT_MV = 0x20002404        # *out_mv  (stack[0])
SP = 0x20003800            # scratch entry-SP (frame pushes below this; stack args at SP+0/SP+4)
MAXREQ_MV = 0x20001f20     # max_request_mv RAM global (clamp source, vs 5000)


def pdo_fixed(mv, ma):
    return ((mv // 50) & 0x3FF) << 10 | ((ma // 10) & 0x3FF)          # type=00 fixed


def pdo_battery(mv, mw):
    return 0x40000000 | ((mv // 50) & 0x3FF) << 10 | ((mw // 250) & 0x3FF)   # type=01 battery


def pdo_variable(mv, ma):
    return 0x80000000 | ((mv // 50) & 0x3FF) << 10 | ((ma // 10) & 0x3FF)    # type=10 variable


# Test vectors: (cnt, flag, [pdo words], max_ma, max_req_mv_global)
VECTORS = [
    # flag=1 selection loop, mixed PDO types + voltages so type/power/clamp branches all flip
    (4, 1, [pdo_fixed(5000, 3000), pdo_battery(9000, 18000),
            pdo_fixed(9000, 2000), pdo_variable(12000, 1500)], 3000, 5000),
    (4, 1, [pdo_fixed(5000, 3000), pdo_battery(9000, 18000),
            pdo_fixed(9000, 2000), pdo_variable(12000, 1500)], 3000, 6000),  # global>5000 -> clamp arm
    (3, 1, [pdo_fixed(20000, 5000), pdo_fixed(5000, 500),
            pdo_battery(15000, 45000)], 5000, 9000),                          # high voltage clamp
    (2, 1, [pdo_battery(5000, 2500), pdo_fixed(5000, 3000)], 3000, 5000),
    (1, 1, [pdo_fixed(5000, 3000)], 3000, 5000),
    (4, 1, [pdo_fixed(3300, 1000), pdo_fixed(5000, 3000),
            pdo_fixed(12000, 3000), pdo_fixed(20000, 5000)], 3000, 20000),
    # flag=0 direct-PDO[0] path (0x8007380): vary PDO[0] type to flip the type==1 branch there
    (1, 0, [pdo_fixed(5000, 3000)], 3000, 5000),
    (1, 0, [pdo_battery(9000, 18000)], 3000, 5000),
    (1, 0, [pdo_fixed(20000, 5000)], 5000, 9000),
    (1, 0, [pdo_variable(12000, 1500)], 1500, 5000),
    (1, 0, [pdo_fixed(5000, 3000)], 3000, 6000),                              # global>5000
    # --- second pass: flip the remaining power-comparison / clamp branches ---
    # decreasing-power array: best stays PDO[0]; later PDOs worse -> 0x8007368 ble taken / 0x8007370
    (4, 1, [pdo_fixed(20000, 5000), pdo_fixed(5000, 500),
            pdo_fixed(5000, 200), pdo_fixed(3300, 100)], 5000, 20000),
    # over-limit current field (>300 -> x10 >3000) -> 0x800735c nottaken clamp
    (2, 1, [pdo_fixed(5000, 9990), pdo_fixed(5000, 100)], 9990, 5000),
    (1, 1, [pdo_fixed(20000, 9990)], 9990, 20000),
    # all-battery loop: exercise battery arm + battery power clamp inside the loop
    (3, 1, [pdo_battery(20000, 100000), pdo_battery(9000, 50000),
            pdo_battery(5000, 2500)], 5000, 20000),
    # flag=0 battery PDO[0] with large power -> 0x80073a8 ble clamp arm
    (1, 0, [pdo_battery(20000, 100000)], 5000, 20000),
    (1, 0, [pdo_battery(20000, 200000)], 5000, 20000),
    # flag=0 fixed PDO[0] high current -> final 0x80073ca power clamp
    (1, 0, [pdo_fixed(20000, 9990)], 9990, 20000),
]


def main():
    binp = os.path.abspath(CAPTURED)
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, "pdo_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior pdo_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)

    trace = os.path.join(TMP, "pdo.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def fresh():
        return fcall.Session(binp, boot="1.5", trace=trace)

    for bank, fn in (("RO", 0x080072f0), ("RW", 0x080172f0)):
        s = fresh()
        try:
            for cnt, flag, words, max_ma, maxreq in VECTORS:
                try:
                    s.rsp.writemem(PDO, struct.pack("<%dI" % len(words), *words))
                    s.rsp.writemem(OUT_PWR, b"\x00\x00\x00\x00")
                    s.rsp.writemem(OUT_MV, b"\x00\x00\x00\x00")
                    s.rsp.writemem(MAXREQ_MV, struct.pack("<I", maxreq))
                    # stack args at entry-SP: [SP+0]=*out_mv, [SP+4]=flag byte
                    s.rsp.writemem(SP, struct.pack("<I", OUT_MV) + bytes([flag, 0, 0, 0]))
                    s.rsp.setreg(13, SP)                       # entry SP -> scratch
                    s.rsp.call(fn, (cnt, PDO, max_ma, OUT_PWR), timeout_continue=3)
                except Exception:
                    s.close(); s = fresh()
        finally:
            s.close()
        if os.path.exists(trace):
            prev = None
            with open(trace) as f:
                for ln in f:
                    ln = ln.strip()
                    if len(ln) < 4 or not ln.startswith("0x"):
                        prev = None; continue
                    try:
                        pc = int(ln, 16)
                    except ValueError:
                        prev = None; continue
                    executed.add(pc)
                    if prev is not None:
                        edges.add((prev, pc))
                    prev = pc
            os.remove(trace)
        print("  %s pdo-selector swept: %d edges, %d PCs so far" % (bank, len(edges), len(executed)))

    with open(out, "wb") as f:
        pickle.dump((executed, edges), f)
    print("saved -> tmp/pdo_edges.pkl")


if __name__ == "__main__":
    main()
