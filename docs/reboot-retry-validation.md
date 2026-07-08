<!-- SPDX-License-Identifier: Apache-2.0 -->
# Validating the netboot reboot-retry loop (gale)

The dev-key netboot firmware is meant to **self-heal**: try TFTP netboot first,
fall back to the eMMC OS, and if **both** fail, **reboot and retry** — never
stranding a headless puck on a recovery screen. That behavior is the vboot patch
`patches/vboot_reference-netboot-reboot-retry.patch` in the
[`depthcharge-ipq4019`](https://github.com/mithro/depthcharge-ipq4019) firmware
tree. This is the one procedure that confirms the *loop* actually runs on
hardware.

## Why not on the SuzyQ rig

`cold_reboot()` de-asserts the AP's `PS_HOLD`, telling the PMIC to re-boot the
SoC. That needs **autonomous power sequencing**. The USB-A SuzyQ bench powers the
AP only when the EC is *told* (`gale power on`) and does no USB-C PD negotiation,
so after the `PS_HOLD` drop the AP just stays down — and the reset bounces the
shared USB-SPI rail, wedging the bench (an EC-reboot un-park can't recover it; it
needs a full PoE cold-boot). This limits the **pre-existing** `cold_reboot` path
too, so the SuzyQ rig cannot demonstrate reboot-looping with *any* firmware. The
whole blocker is autonomous power — give the gale that and it works.

## Setup

1. **Flash** the reboot-retry firmware via the SuzyQ (the normal fleet flow), and
   leave the **eMMC blank / with no bootable OS**. Both netboot *and* eMMC must
   fail for the reboot-retry path to trigger.
2. **Unplug the SuzyQ** from the gale's USB-C and plug in the **stock USB-C PD
   adapter**. The gale now boots on normal power (the EC auto-boots the AP;
   `cold_reboot` reboots cleanly).
3. Leave the gale's **WAN RJ45 cabled to the rig's `eth-gwan`** (that's a
   separate cable from the USB-C, so it stays put).
4. Ensure there is **no netboot/DHCP server** on that WAN segment (stop dnsmasq;
   remove the `192.168.50.1` provisioning IP) — netboot must fail every cycle.

## Run

On the rig (or any host with the gale's WAN cabled):

```sh
sudo tools/netboot-verify/reboot_loop_validate.sh eth-gwan 300
```

It passively sniffs the WAN for 300 s and counts the puck's DHCP-discover
**bursts**. It never touches the EC or power.

## Pass / fail

| Result | Meaning |
|--------|---------|
| **PASS** — ≥3 evenly-spaced bursts (~20–45 s apart) | `netboot → eMMC → reboot → netboot` self-heals ✓ |
| **FAIL** — one burst then silence | Booted once, did not reboot: pre-fix behavior, or not on PD power (still on SuzyQ) |
| **FAIL** — no frames at all | Puck never DHCP'd: not booting, WAN not cabled/carrier-down, or not PD-powered |

## Two more checks worth doing in the same session

- **eMMC fallback (the common deployed case):** netboot-install OpenWrt to eMMC
  (see [`gale-openwrt-netboot-install.md`](gale-openwrt-netboot-install.md)), then
  with no server confirm it does `netboot-fail → boot eMMC OpenWrt` — one boot
  into the installed OS, no loop.
- **Manual recovery still works:** hold the recovery button **>16 s** at power-on
  and confirm it waits for USB recovery media (the untouched `REC_SWITCH_ON`
  path) instead of reboot-looping.

## Seeing the console messages (optional)

To watch the actual `netboot: trying TFTP… → no kernel → rebooting to retry
netboot → [reboot]` cycle text, use a **PD-capable servo** (servo v4, or a
Type-C CCD/SuzyQ that passes PD) instead of the USB-A SuzyQ — it provides
autonomous power **and** the AP console + flashing at once.
