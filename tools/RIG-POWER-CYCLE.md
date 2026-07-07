# Power-cycling the rpi3b-gwifi rig (PoE switch, via SNMP)

The gale flash rig `rpi3b-gwifi.iot.welland.mithis.com` (10.1.90.216, VLAN 90
"iot") is **PoE-powered** from the Netgear "s1" switch. When the rig is
wedged/offline (e.g. its USB NICs died — everything on an rpi3b hangs off one
USB controller), cut and restore its PoE port to cold-boot it.

**Control and probing is done over SNMP** (not the switch's legacy-crypto SSH
CLI). **No credentials in this file**: reads work with the standard read
community; the **write community** (needed for the actual power cycle) comes
from the usual secrets store / Tim — never write it into files.

## The switch

| what | value |
|---|---|
| name | `sw-netgear-gsm7252ps-s1.net.welland.mithis.com` |
| IP | `10.1.5.22` (VLAN 5 "net"; reachable from desktop and ten64) |
| model | Netgear ProSafe **GSM7252PS** (48×GbE PoE, SNMP v2c) |
| siblings | s2 = 10.1.5.23, s3 = 10.1.5.24 — **do not confuse** |

## ⚠️ ALWAYS validate the port first

**The hardware sometimes moves / changes ports. Never cycle a port from
memory or from this document alone — validate that ALL of the following
agree on the SAME ifIndex immediately before cycling:**

```sh
SW=10.1.5.22
# 1. Port descriptions (ifAlias): find "eth0.rpi3b-gwifi" -> ifIndex N
snmpwalk -v2c -c <read> $SW 1.3.6.1.2.1.31.1.1.1.18 | grep -i rpi3b

# 2. LLDP remote SysName (index = timeMark.localPort.idx). When the rig is
#    HEALTHY its lldpd announces "rpi3b-gwifi" on local port N; when the rig
#    is dead (the usual reason you are here) the entry is ABSENT -- check no
#    OTHER SysName sits on port N:
snmpwalk -v2c -c <read> $SW 1.0.8802.1.1.2.1.4.1.1.9

# 3. VLAN: PVID of port N must be 90 (iot):
snmpget -v2c -c <read> $SW 1.3.6.1.2.1.17.7.1.4.5.1.1.N

# 4. PoE state: admin-enabled and DELIVERING power (rig draws PoE even with
#    a dead network):  pethPsePortAdminEnable / pethPsePortDetectionStatus
snmpget -v2c -c <read> $SW 1.3.6.1.2.1.105.1.1.1.3.1.N   # 1 = enabled
snmpget -v2c -c <read> $SW 1.3.6.1.2.1.105.1.1.1.6.1.N   # 3 = deliveringPower

# 5. Link state (sanity): rig-NIC-dead shows ifOperStatus = 2 (down):
snmpget -v2c -c <read> $SW 1.3.6.1.2.1.2.2.1.8.N
```

Cross-checks: description + VLAN 90 + PoE draw must all point at the same
ifIndex; if LLDP shows a **different** SysName on that port — **STOP**. If
anything disagrees, walk the cable or ask before cycling.

### Worked example (validated 2026-07-07 — REVALIDATE, DO NOT TRUST BLINDLY)

ifIndex **4** (= physical port 1/0/4): `ifAlias.4 = "eth0.rpi3b-gwifi"`,
`dot1qPvid.4 = 90`, `pethPsePortAdminEnable.1.4 = 1`,
`pethPsePortDetectionStatus.1.4 = 3` (delivering), `ifOperStatus.4 = 2`
(down, rig NICs dead), no LLDP entry on port 4 while every healthy neighbor
had one.

## Cycle the port (write community required)

POWER-ETHERNET-MIB `pethPsePortAdminEnable` (.1.3.6.1.2.1.105.1.1.1.3.1.N):
`2` = off, `1` = on.

```sh
snmpset -v2c -c <write> $SW 1.3.6.1.2.1.105.1.1.1.3.1.N i 2   # PoE OFF
sleep 8
snmpset -v2c -c <write> $SW 1.3.6.1.2.1.105.1.1.1.3.1.N i 1   # PoE ON
# verify power is being delivered again:
snmpget -v2c -c <read>  $SW 1.3.6.1.2.1.105.1.1.1.6.1.N       # want 3
```

## Side effects & after the cycle

- Cutting the rig's power also cold-boots **everything on its USB**: the
  gale puck under test (EC cold boot — clears saved `panicinfo`!), hub,
  USB NICs.
- Boot takes ~45–90 s. Verify:
  ```sh
  ping -c3 rpi3b-gwifi.iot.welland.mithis.com
  ssh rpi3b-gwifi.iot.welland.mithis.com 'lsusb -d 18d1:500f; ls /dev/ttyUSB*'
  ssh rpi3b-gwifi.iot.welland.mithis.com \
      'cd local/gwifi/gwifi-openwrt/tools && python3 flash_puck_usb.py ec sysinfo'
  ```
- If ttyUSB nodes are missing but the gale enumerates:
  `echo 0 > /sys/bus/usb/devices/1-1.2/authorized; sleep 2; echo 1 > ...`
  (device-scoped driver re-probe).

## Why not the rig's own hub-port power toggle?

`/sys/bus/usb/devices/1-1:1.0/1-1-port2/disable` on the rig cold-boots the
gale EC, but the SMSC2514 hub has **ganged** port power: it bounces the rig's
own USB NICs too, and on 2026-07-07 the third use took the rig's networking
down entirely (hence this document). Prefer waiting out the EC's self-heal;
use the PoE cycle for the whole rig; do not use the ganged hub toggle.

## Discovery trail (for re-derivation if names change)

ten64 router (10.1.90.1) `lldpcli show neighbors` → switch inventory lives in
`net.welland.mithis.com` / 10.1.5.0/24 (PTR sweep via internal DNS
@10.98.5.1). VLAN ids match the third octet of their subnets (iot=90, net=5).
The switch also has a legacy-crypto SSH CLI (FASTPATH) — not used; SNMP is
the supported control path.
