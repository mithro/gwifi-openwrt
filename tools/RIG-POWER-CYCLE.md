# Power-cycling the rpi3b-gwifi rig (PoE switch method)

The gale flash rig `rpi3b-gwifi.iot.welland.mithis.com` (10.1.90.216, VLAN 90
"iot") is **PoE-powered** from the Netgear "s1" switch. When the rig is
wedged/offline (e.g. its USB NICs died — everything on an rpi3b hangs off one
USB controller), cut and restore its PoE port to cold-boot it.

**No passwords in this file.** The switch admin password is required at the
SSH prompt — get it from the usual secrets store / Tim.

## The switch

| what | value |
|---|---|
| name | `sw-netgear-gsm7252ps-s1.net.welland.mithis.com` |
| IP | `10.1.5.22` (VLAN 5 "net"; reachable from desktop and ten64) |
| model | Netgear ProSafe **GSM7252PS** (48×GbE PoE, FASTPATH CLI) |
| siblings | s2 = 10.1.5.23, s3 = 10.1.5.24 — **do not confuse** |
| user | `admin` |

The switch only speaks legacy SSH crypto; connect with:

```sh
ssh -o KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1 \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o Ciphers=+aes128-cbc,3des-cbc \
    admin@sw-netgear-gsm7252ps-s1.net.welland.mithis.com
```

## ⚠️ ALWAYS validate the port first

**The hardware sometimes moves / changes ports. Never cycle a port from
memory or from this document alone — validate ALL of the following agree
on the SAME port number immediately before cycling:**

```
enable                            # privileged mode (FASTPATH CLI)
show port description all         # description should name rpi3b / gwifi
show lldp remote-device all       # SysName "rpi3b-gwifi" -- ONLY visible when
                                  # the rig's networking is alive; absent when
                                  # it is down (the usual reason you're here)
show vlan 90                      # port must be a member of VLAN 90 (iot)
show poe                          # then: show poe port ... (use `show poe ?`)
                                  # the port should show power DELIVERED
                                  # (a few W: rpi3b + its USB hub) -- a live
                                  # PoE draw even when the network is dead
show mac-addr-table               # rpi3b eth0 MAC learned on that port
                                  # (absent if its NIC is down)
```

Cross-checks:
- Description, VLAN 90 membership, and PoE draw must all point at the same
  port. If LLDP shows a **different** SysName on that port — **STOP**.
- If anything disagrees, walk the cable or ask before cycling.

## Cycle the port

In the FASTPATH CLI (exact PoE keyword set varies by firmware — use `?`):

```
enable
configure
interface 0/NN          # the VALIDATED port
poe reset               # if supported: one-shot PoE cycle -- preferred
# -- otherwise --
no poe                  # (or `no poe admin`) cut PoE power
# wait >= 5 seconds
poe                     # (or `poe admin`) restore PoE power
exit
exit
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
      'cd local/gwifi/gwifi-openwrt/tools && python3 ec_console.py sysinfo'
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
