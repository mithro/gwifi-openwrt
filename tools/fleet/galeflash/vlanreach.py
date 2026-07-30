# SPDX-License-Identifier: Apache-2.0
"""Pure logic for the per-VLAN reachability checker.

Builds the on-puck probe script and parses its RESULT lines.  All ssh I/O
lives in check_vlan_reach.py.  Fail loud: malformed probe output raises.
"""

from typing import NamedTuple


class VlanProbe(NamedTuple):
    """One VLAN leg to verify from a puck towards the ten64."""
    vid:    int
    gw:     str     # ten64 gateway address on this VLAN
    prefix: int     # subnet prefix length (for the temp address)
    mode:   str     # "mgmt" | "dhcp" | "static"


# The five VLANs every puck's br0 carries (verified live on puck03,
# 2026-07-26) and the matching ten64 bridge gateways:
#   4 mgmt/br-wifi (puck's own DHCP address lives here)
#  10 int/br-int   (DHCP pool 10.1.10.0/21)
#  20 roam/br-roam (DHCP pool 10.1.20.0/24; 'ansells' SSID)
#  90 iot/br-iot   (DHCP pool 10.1.90.0/23; 'ansells-iot' SSID)
#  99 guest/br-guest (NO DHCP by design; 'ansells-guest' SSID)
# int/roam/iot pools span their whole subnet, so a static temp address
# could collide with a live lease — DHCP is the only conflict-safe probe
# there.  Guest has no leases at all, so a static temp address is safe;
# its probe is ARP resolution of the gateway: the ten64 offers NO L3
# service on guest (dnsmasq has no 10.1.99.1 listener or DHCP range, and
# the firewall drops everything else from 10.1.99.0/24 — "Drop guest net
# to ten64"), so a resolved neighbour entry is the strongest reachability
# proof possible on that VLAN.
VLAN_PROBES: tuple[VlanProbe, ...] = (
    VlanProbe(4,  "10.1.4.1",  24, "mgmt"),
    VlanProbe(10, "10.1.10.1", 21, "dhcp"),
    VlanProbe(20, "10.1.20.1", 24, "dhcp"),
    VlanProbe(90, "10.1.90.1", 23, "dhcp"),
    VlanProbe(99, "10.1.99.1", 24, "arp"),
)

_SCRIPT_PRELUDE = """\
set -u

dhcp_probe() {
  vid="$1"; gw="$2"; pfx="$3"
  echo "== vlan$vid =="
  out="$(udhcpc -i "br0.$vid" -n -q -t 3 -T 3 -s /bin/true 2>&1)"
  echo "$out"
  lease="$(printf '%s\\n' "$out" | sed -n 's/.*lease of \\([0-9.]*\\) obtained.*/\\1/p' | head -n1)"
  if [ -z "$lease" ]; then
    echo "RESULT $vid FAIL no-dhcp-lease"
    return 0
  fi
  ip addr add "$lease/$pfx" dev "br0.$vid"
  if ping -c 2 -W 3 -I "br0.$vid" "$gw"; then
    echo "RESULT $vid OK dhcp+icmp lease=$lease"
  else
    echo "RESULT $vid FAIL icmp-after-dhcp lease=$lease"
  fi
  ip addr del "$lease/$pfx" dev "br0.$vid"
}

arp_probe() {
  vid="$1"; gw="$2"; pfx="$3"; tmpip="$4"
  echo "== vlan$vid =="
  ip addr add "$tmpip/$pfx" dev "br0.$vid"
  ip neigh flush dev "br0.$vid"
  # ICMP is dropped by the ten64's guest policy — the pings only exist to
  # force ARP resolution; the verdict is the neighbour entry.
  ping -c 2 -W 3 -I "br0.$vid" "$gw" || true
  neigh="$(ip neigh show to "$gw" dev "br0.$vid")"
  echo "neigh: $neigh"
  case "$neigh" in
    *lladdr*) echo "RESULT $vid OK arp src=$tmpip" ;;
    *)        echo "RESULT $vid FAIL no-arp src=$tmpip" ;;
  esac
  ip addr del "$tmpip/$pfx" dev "br0.$vid"
}

mgmt_probe() {
  vid="$1"; gw="$2"
  echo "== vlan$vid =="
  if ping -c 2 -W 3 -I "br0.$vid" "$gw"; then
    echo "RESULT $vid OK icmp"
  else
    echo "RESULT $vid FAIL icmp"
  fi
}
"""


def build_remote_script(puck_num: int) -> str:
    """Return the sh script a puck runs to probe every VLAN leg.

    ``puck_num`` uniquifies the guest temp address (10.1.99.200+NN) so
    concurrent runs against different pucks can never collide.
    """
    if not 1 <= puck_num <= 50:
        raise ValueError(f"implausible puck number: {puck_num}")
    lines = [_SCRIPT_PRELUDE]
    for p in VLAN_PROBES:
        if p.mode == "mgmt":
            lines.append(f"mgmt_probe {p.vid} {p.gw}")
        elif p.mode == "dhcp":
            lines.append(f"dhcp_probe {p.vid} {p.gw} {p.prefix}")
        elif p.mode == "arp":
            tmpip = f"10.1.{p.vid}.{200 + puck_num}"
            lines.append(f"arp_probe {p.vid} {p.gw} {p.prefix} {tmpip}")
        else:
            raise ValueError(f"unknown probe mode: {p.mode!r}")
    return "\n".join(lines) + "\n"


def parse_results(output: str) -> dict[int, tuple[bool, str]]:
    """Parse RESULT lines into {vid: (ok, detail)}.

    Raises if a VLAN reports twice or a RESULT line is malformed; callers
    check the returned dict covers every probed VLAN.
    """
    results: dict[int, tuple[bool, str]] = {}
    for line in output.splitlines():
        if not line.startswith("RESULT "):
            continue
        parts = line.split(None, 3)
        if len(parts) < 3 or parts[2] not in ("OK", "FAIL"):
            raise ValueError(f"malformed RESULT line: {line!r}")
        vid = int(parts[1])
        if vid in results:
            raise ValueError(f"duplicate RESULT for vlan {vid}: {line!r}")
        detail = parts[3] if len(parts) == 4 else ""
        results[vid] = (parts[2] == "OK", detail)
    return results
