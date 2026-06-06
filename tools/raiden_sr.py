#!/usr/bin/env python3
"""Read-only raiden status-register reader for the gale AP flash (W25Q64FV).

Reads RDID + SR1/SR2/SR3 and decodes them -- in particular CMP (SR2 bit6) and WPS
(SR3 bit2), the write-protect bits flashrom does NOT decode and which can block
erase while SR1 shows "no protection". Issues ONLY read opcodes (0x9F/0x05/0x35/
0x15): no WREN, no WRSR, no erase, no program.

Uses the shared raiden transport (fail-loud); Raiden() validates RDID==ef4017 on
connect, so a wrong chip / disabled bridge aborts immediately.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find raiden.py beside us
from raiden import Raiden, OP_RDID, OP_RDSR1, OP_RDSR2, OP_RDSR3  # noqa: E402


def bits(v, names):
    return "  ".join(f"{n}={(v >> i) & 1}" for i, n in enumerate(names))


def main():
    with Raiden() as r:                       # parks + enables + validates RDID
        rdid = r.xfer([OP_RDID], 3)
        s1 = r.xfer([OP_RDSR1], 1)[0]
        s2 = r.xfer([OP_RDSR2], 1)[0]
        s3 = r.xfer([OP_RDSR3], 1)[0]

    print(f"RDID = {rdid.hex()}  (Winbond W25Q64FV; validated by transport)\n")
    print(f"SR1 = 0x{s1:02x}   " + bits(s1, ["BUSY", "WEL", "BP0", "BP1", "BP2", "TB", "SEC", "SRP0"]))
    print(f"SR2 = 0x{s2:02x}   " + bits(s2, ["SRL", "QE", "R2", "LB1", "LB2", "LB3", "CMP", "SUS"]))
    print(f"SR3 = 0x{s3:02x}   " + bits(s3, ["R0", "R1", "WPS", "R3", "R4", "DRV0", "DRV1", "HOLD/RST"]))

    cmp_set, wps_set = (s2 >> 6) & 1, (s3 >> 2) & 1
    print()
    if cmp_set:
        print("** CMP=1: with BP=0 the protected range is COMPLEMENTED -> WHOLE chip "
              "protected (blocks erase/program); flashrom does not decode this. **")
    if wps_set:
        print("** WPS=1: Individual Block/Sector Lock mode -> all sectors locked by "
              "default (blocks erase/program); flashrom cannot see this. **")
    if not cmp_set and not wps_set:
        print(">> Neither CMP nor WPS set: protection is NOT in SR2/SR3.")


if __name__ == "__main__":
    main()
