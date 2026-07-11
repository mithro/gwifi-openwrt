#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create VLAN 4 "wifi" on the welland switch fabric for the gale pucks.

Run on ten64. Idempotent and VERIFY-BY-READBACK: Netgear FASTPATH agents
sometimes apply a Q-BRIDGE set and still answer `commitFailed`, so set
errors are warnings — only a read-back mismatch fails.

Topology (validated 2026-07-12 via LLDP/FDB; m4300 port-1 alias
"trunk.sw-cisco-shed" is STALE — that switch is gone, port 1 is ten64):

  ten64 eth9 -- m4300-24x(10.1.5.13) port1 ; port2 -- s1(10.1.5.22) port49
  puck12 on s1 port 46 (PoE)

Target state:
  m4300: VLAN 4 "wifi", tagged 1+2, no untagged        (131-octet bitmaps)
  s1:    VLAN 4 "wifi", tagged 49, untagged 46,        (75-octet bitmaps)
         PVID(46)=4, port 46 out of VLAN 1 (best-effort)

Env: SNMP_WRITE_COMMUNITY (default 'private'), SNMP_READ_COMMUNITY
(default 'public').
"""

import os
import subprocess
import sys

READ = os.environ.get("SNMP_READ_COMMUNITY", "public")
WRITE = os.environ.get("SNMP_WRITE_COMMUNITY", "private")

Q = "1.3.6.1.2.1.17.7.1.4.3.1"    # dot1qVlanStaticTable columns
NAME, EGRESS, UNTAG, ROWSTATUS = f"{Q}.1", f"{Q}.2", f"{Q}.4", f"{Q}.5"
PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1"


def snmpget(host, oid, hex_out=False):
    fmt = "-Ox" if hex_out else "-Ovq"
    r = subprocess.run(
        ["snmpget", "-v2c", "-c", READ, fmt, "-t", "5", "-r", "1", host, oid],
        capture_output=True, text=True)
    out = r.stdout.strip()
    if r.returncode != 0 or "No Such" in out:
        return None
    return out


def get_hex(host, oid):
    raw = snmpget(host, oid, hex_out=True)
    if raw is None:
        return None
    return "".join(raw.split("Hex-STRING:")[1].split()).lower()


def snmpset_lenient(host, oid, typ, val):
    """Set; FASTPATH may apply-and-still-error, so only warn on failure."""
    r = subprocess.run(
        ["snmpset", "-v2c", "-c", WRITE, "-t", "5", "-r", "1",
         host, oid, typ, val],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  (set on {oid.rsplit('.', 2)[-2:]} reported an error — "
              f"verifying by read-back)")


# Physical ports live in the first octets of the port bitmaps; both
# switches auto-add internal LAG/CPU ports (high bits, e.g. octet 96 on the
# m4300) to every VLAN — compare only the physical range and never fight
# the agent over the rest.
PHYS_OCTETS = 7  # ports 1-56 (m4300-24x: 24 ports; s1: 52 ports)


def _phys(hexstr):
    return hexstr[: PHYS_OCTETS * 2]


def ensure(host, oid, typ, want, *, hex_col=False, label=""):
    """Idempotent set: skip when current == want, else set + verify.

    Hex (bitmap) columns compare only the physical-port octets.
    """
    cur = get_hex(host, oid) if hex_col else snmpget(host, oid)
    norm = want.lower() if hex_col else want
    if cur is not None:
        matches = (_phys(cur) == _phys(norm)) if hex_col \
            else cur.strip('"') == norm.strip('"')
        if matches:
            print(f"  {label}: already correct")
            return
    snmpset_lenient(host, oid, typ, want)
    cur = get_hex(host, oid) if hex_col else snmpget(host, oid)
    ok = cur is not None and (
        (_phys(cur) == _phys(norm)) if hex_col
        else cur.strip('"') == norm.strip('"'))
    if not ok:
        raise SystemExit(
            f"VERIFY FAILED on {host} {label}: want {norm!r} got {cur!r}")
    print(f"  {label}: set + verified")


def bitmap(num_octets, ports):
    octets = bytearray(num_octets)
    for port in ports:
        octets[(port - 1) // 8] |= 1 << (7 - ((port - 1) % 8))
    return octets.hex()


def ensure_vlan4(host, tagged, untagged):
    n = len(bytes.fromhex(get_hex(host, f"{EGRESS}.1")))
    print(f"{host}: bitmap length {n} octets")
    if snmpget(host, f"{NAME}.4") is None:
        snmpset_lenient(host, f"{ROWSTATUS}.4", "i", "5")   # createAndWait
        if snmpget(host, f"{NAME}.4") is None and \
           snmpget(host, f"{ROWSTATUS}.4") is None:
            raise SystemExit(f"{host}: VLAN 4 row did not appear")
    ensure(host, f"{NAME}.4", "s", "wifi", label="name")
    ensure(host, f"{EGRESS}.4", "x", bitmap(n, tagged + untagged),
           hex_col=True, label="egress")
    ensure(host, f"{UNTAG}.4", "x", bitmap(n, untagged),
           hex_col=True, label="untagged")
    ensure(host, f"{ROWSTATUS}.4", "i", "1", label="rowstatus-active")
    print(f"{host}: VLAN 4 verified")


def main():
    ensure_vlan4("10.1.5.13", tagged=[1, 2], untagged=[])
    ensure_vlan4("10.1.5.22", tagged=[49], untagged=[46])
    ensure("10.1.5.22", f"{PVID}.46", "u", "4", label="s1 pvid.46")

    # Best-effort: drop port 46 from VLAN 1 membership.
    try:
        for col, label in ((EGRESS, "vlan1-egress"), (UNTAG, "vlan1-untag")):
            octets = bytearray.fromhex(get_hex("10.1.5.22", f"{col}.1"))
            octets[(46 - 1) // 8] &= ~(1 << (7 - ((46 - 1) % 8)))
            ensure("10.1.5.22", f"{col}.1", "x", octets.hex(),
                   hex_col=True, label=label)
    except SystemExit as e:
        print(f"s1: VLAN 1 cleanup refused (harmless, continuing): {e}")

    print("DONE — fabric VLAN 4 ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
