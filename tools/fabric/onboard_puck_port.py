#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Onboard a gale puck's switch port onto the wifi VLAN (4).

Steps (each verified by read-back — FASTPATH answers commitFailed on
sets it APPLIES, so success is judged only by re-reading):
  1. refuse to touch trunk/uplink ports (tagged member of >2 VLANs,
     ignoring the puck client VLANs this tool itself adds)
  2. VLAN 4: egress + untagged member
  3. PVID 4
  4. client VLANs 10/20/90/99 tagged (SSID bridges ride lan.<vid>)
  5. drop the port from VLAN 1 (egress + untagged)
  6. ifAlias = eth0.<puck> (site convention, e.g. eth0.puck11)

Usage: onboard_puck_port.py --port 11 --puck puck11 [--switch 10.1.5.22]
Community strings via SNMP_READ_COMMUNITY / SNMP_WRITE_COMMUNITY.
"""
import argparse
import os
import subprocess

Q = "1.3.6.1.2.1.17.7.1.4.3.1"
EGRESS, UNTAG = f"{Q}.2", f"{Q}.4"
PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1"
IFALIAS = "1.3.6.1.2.1.31.1.1.1.18"
PHYS_OCTETS = 7  # compare only physical ports; FASTPATH appends LAG bits
WIFI_VLAN = 4
CLIENT_VLANS = (10, 20, 90, 99)  # int/roam/iot/guest — tagged to the puck
TRUNK_TAGGED_LIMIT = 2  # >2 tagged VLANs (beyond client set) = trunk, refuse


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True)


class Switch:
    def __init__(self, host, read, write):
        self.host, self.read, self.write = host, read, write

    def get_hex(self, oid):
        r = run(["snmpget", "-v2c", "-c", self.read, "-Ox", "-t", "5",
                 self.host, oid])
        if r.returncode != 0 or "Hex-STRING" not in r.stdout:
            raise SystemExit(f"read failed: {oid}\n{r.stdout}{r.stderr}")
        return "".join(r.stdout.split("Hex-STRING:")[1].split()).lower()

    def get(self, oid):
        r = run(["snmpget", "-v2c", "-c", self.read, "-Ovq", "-t", "5",
                 self.host, oid])
        return r.stdout.strip().strip('"')

    def set_lenient(self, oid, typ, val):
        # FASTPATH may answer commitFailed while applying: ignore rc,
        # caller must verify by read-back.
        run(["snmpset", "-v2c", "-c", self.write, "-t", "5",
             self.host, oid, typ, val])

    def walk_hex(self, oid):
        r = run(["snmpwalk", "-v2c", "-c", self.read, "-Ox", "-On", "-t",
                 "5", self.host, oid])
        out, key, buf = {}, None, []
        for line in r.stdout.splitlines():
            if line.startswith("."):
                if key is not None:
                    out[key] = "".join(buf)
                left, _, val = line.partition(" = ")
                key = left.split(".")[-1]
                buf = (["".join(val.split("Hex-STRING:")[-1].split()).lower()]
                       if "Hex-STRING" in val else [])
            elif key is not None:
                buf.append("".join(line.split()).lower())
        if key is not None:
            out[key] = "".join(buf)
        return out


def ports_in(hexstr):
    ports = set()
    for i, o in enumerate(bytes.fromhex(hexstr)[:PHYS_OCTETS]):
        for b in range(8):
            if o & (1 << (7 - b)):
                ports.add(i * 8 + b + 1)
    return ports


def with_bit(hexstr, port, on):
    octets = bytearray.fromhex(hexstr)
    bit = 1 << (7 - ((port - 1) % 8))
    if on:
        octets[(port - 1) // 8] |= bit
    else:
        octets[(port - 1) // 8] &= ~bit
    return octets.hex()


def tagged_vlans(sw, port):
    egress, untag = sw.walk_hex(EGRESS), sw.walk_hex(UNTAG)
    return sorted(int(v) for v, ehex in egress.items()
                  if port in ports_in(ehex) - ports_in(untag.get(v, "")))


def ensure_hex(sw, oid, want, label):
    cur = sw.get_hex(oid)
    if cur[: PHYS_OCTETS * 2] == want[: PHYS_OCTETS * 2]:
        print(f"  {label}: already correct")
        return
    sw.set_lenient(oid, "x", want)
    cur = sw.get_hex(oid)
    assert cur[: PHYS_OCTETS * 2] == want[: PHYS_OCTETS * 2], \
        f"VERIFY FAILED {label}: {cur[:PHYS_OCTETS*2]} != {want[:PHYS_OCTETS*2]}"
    print(f"  {label}: set + verified")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--puck", required=True, help="e.g. puck11")
    ap.add_argument("--switch", default="10.1.5.22")
    ap.add_argument("--alias-only", action="store_true",
                    help="only set the ifAlias, skip VLAN changes")
    args = ap.parse_args()

    sw = Switch(args.switch,
                os.environ.get("SNMP_READ_COMMUNITY", "public"),
                os.environ.get("SNMP_WRITE_COMMUNITY", "private"))

    tags = [v for v in tagged_vlans(sw, args.port) if v not in CLIENT_VLANS]
    if len(tags) > TRUNK_TAGGED_LIMIT and not args.alias_only:
        raise SystemExit(
            f"REFUSING: port {args.port} looks like a trunk/uplink "
            f"(tagged VLANs {tags}). Pucks belong on access ports.")

    if not args.alias_only:
        ensure_hex(sw, f"{EGRESS}.{WIFI_VLAN}",
                   with_bit(sw.get_hex(f"{EGRESS}.{WIFI_VLAN}"),
                            args.port, True),
                   f"vlan{WIFI_VLAN}-egress+p{args.port}")
        ensure_hex(sw, f"{UNTAG}.{WIFI_VLAN}",
                   with_bit(sw.get_hex(f"{UNTAG}.{WIFI_VLAN}"),
                            args.port, True),
                   f"vlan{WIFI_VLAN}-untag+p{args.port}")
        if sw.get(f"{PVID}.{args.port}") != str(WIFI_VLAN):
            sw.set_lenient(f"{PVID}.{args.port}", "u", str(WIFI_VLAN))
        assert sw.get(f"{PVID}.{args.port}") == str(WIFI_VLAN), \
            "PVID verify failed"
        print(f"  pvid.{args.port} = {WIFI_VLAN}")
        for vid in CLIENT_VLANS:
            ensure_hex(sw, f"{EGRESS}.{vid}",
                       with_bit(sw.get_hex(f"{EGRESS}.{vid}"),
                                args.port, True),
                       f"vlan{vid}-tagged+p{args.port}")
        ensure_hex(sw, f"{EGRESS}.1",
                   with_bit(sw.get_hex(f"{EGRESS}.1"), args.port, False),
                   f"vlan1-egress-p{args.port}")
        ensure_hex(sw, f"{UNTAG}.1",
                   with_bit(sw.get_hex(f"{UNTAG}.1"), args.port, False),
                   f"vlan1-untag-p{args.port}")

    alias = f"eth0.{args.puck}"
    if sw.get(f"{IFALIAS}.{args.port}") != alias:
        sw.set_lenient(f"{IFALIAS}.{args.port}", "s", alias)
    got = sw.get(f"{IFALIAS}.{args.port}")
    assert got == alias, f"ifAlias verify failed: {got!r} != {alias!r}"
    print(f"  ifAlias.{args.port} = {alias!r}")
    print(f"DONE - port {args.port} ready for {args.puck}")


if __name__ == "__main__":
    main()
