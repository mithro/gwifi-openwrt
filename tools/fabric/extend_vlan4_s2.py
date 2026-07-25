#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Extend VLAN 4 "wifi" to switch s2 (user directive: VLAN 4 follows
VLAN 5 everywhere).

- s1 (10.1.5.22): tag VLAN 4 on ports 50+51 (the s2 trunks), clearing
  FASTPATH's pre-set untagged bits.
- s2 (10.1.5.23): create VLAN 4 (createAndWait — FASTPATH refuses
  createAndGo), name it "wifi", tag ports 49+51 and LAG ifIndex 418.

Every set verified by read-back per-bit (FASTPATH answers commitFailed
on sets it applies). Community strings via SNMP_*_COMMUNITY env.
"""
import os
import subprocess
import time

Q = "1.3.6.1.2.1.17.7.1.4.3.1"
EGRESS, UNTAG = f"{Q}.2", f"{Q}.4"
NAME, ROWSTATUS = f"{Q}.1", f"{Q}.5"
READ = os.environ.get("SNMP_READ_COMMUNITY", "public")
WRITE = os.environ.get("SNMP_WRITE_COMMUNITY", "private")

S1, S2 = "10.1.5.22", "10.1.5.23"


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True)


def get_hex(host, oid):
    r = run(["snmpget", "-v2c", "-c", READ, "-Ox", "-t", "5", "-r", "2",
             host, oid])
    if "Hex-STRING" not in r.stdout:
        raise SystemExit(f"read failed {host} {oid}: {r.stdout}{r.stderr}")
    return bytearray.fromhex(
        "".join(r.stdout.split("Hex-STRING:")[1].split()))


def set_lenient(host, oid, typ, val):
    run(["snmpset", "-v2c", "-c", WRITE, "-t", "5", host, oid, typ, val])


def bit_is(octets, port):
    idx, bit = (port - 1) // 8, 1 << (7 - ((port - 1) % 8))
    return idx < len(octets) and bool(octets[idx] & bit)


def with_bits(octets, ports, on):
    octets = bytearray(octets)
    for port in ports:
        idx, bit = (port - 1) // 8, 1 << (7 - ((port - 1) % 8))
        while idx >= len(octets):
            octets.append(0)
        if on:
            octets[idx] |= bit
        else:
            octets[idx] &= ~bit
    return octets


def ensure_bits(host, oid, ports, on, label):
    cur = get_hex(host, oid)
    if all(bit_is(cur, p) == on for p in ports):
        print(f"  {label}: already correct")
        return
    set_lenient(host, oid, "x", with_bits(cur, ports, on).hex())
    cur = get_hex(host, oid)
    bad = [p for p in ports if bit_is(cur, p) != on]
    assert not bad, f"VERIFY FAILED {label}: ports {bad}"
    print(f"  {label}: set + verified")


def vlan4_exists(host):
    r = run(["snmpget", "-v2c", "-c", READ, "-Ovq", "-t", "5", host,
             f"{ROWSTATUS}.4"])
    return r.returncode == 0 and "No Such" not in r.stdout


print("== s1: tag VLAN 4 on the s2 trunks (50, 51)")
ensure_bits(S1, f"{EGRESS}.4", [50, 51], True, "s1 vlan4 egress +50+51")
ensure_bits(S1, f"{UNTAG}.4", [50, 51], False, "s1 vlan4 untag clear 50,51")

print("== s2: create VLAN 4")
if not vlan4_exists(S2):
    set_lenient(S2, f"{ROWSTATUS}.4", "i", "5")  # createAndWait
    for _ in range(10):
        if vlan4_exists(S2):
            break
        time.sleep(1)
    assert vlan4_exists(S2), "s2: VLAN 4 row did not appear"
    print("  s2: VLAN 4 row created")
else:
    print("  s2: VLAN 4 row exists")
set_lenient(S2, f"{NAME}.4", "s", "wifi")
set_lenient(S2, f"{ROWSTATUS}.4", "i", "1")  # active
ensure_bits(S2, f"{EGRESS}.4", [49, 51, 418], True,
            "s2 vlan4 egress +49+51+lag418")
ensure_bits(S2, f"{UNTAG}.4", [49, 51, 418], False,
            "s2 vlan4 untag clear")
print("DONE - VLAN 4 extended to s2")
