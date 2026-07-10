# gwifi-openwrt — project notes for Claude

Firmware + tooling for flashing dev-key netboot firmware onto Google Wifi
"gale" (IPQ4019 AP, STM32F072 EC) fleet pucks and booting them over the network.

## The flash rig

`rpi3b-gwifi.iot.welland.mithis.com` (10.1.90.216, VLAN 90 "iot") — a Raspberry
Pi 3B, **PoE-powered** from the Netgear "s1" switch (`10.1.5.22`). The gale puck
under test hangs off the Pi's USB (EC USB-SPI bridge `18d1:500f`) plus two
USB-ethernet dongles (`eth-gwan` = puck WAN, `eth-glan` = puck LAN). Reach it
over ssh (cross-site ~250 ms; use `-4 -o ConnectTimeout=…`). It needs the
**welland VPN** up.

### Power-cycling the rig — use the script

When the rig or the puck EC wedges, cold-boot the whole rig by cycling its PoE
port. **Use `tools/rig_power_cycle.py`** (not ad-hoc SNMP):

```sh
tools/rig_power_cycle.py --dry-run     # validate switch + port, change nothing
tools/rig_power_cycle.py               # clean shutdown -> PoE off/on -> wait for ssh
tools/rig_power_cycle.py --force       # hard-cycle even if the rig can't be shut down
```

- Pre-flights the VPN/switch, **validates the PoE port** (ports move — never
  trust a remembered ifIndex), cleanly shuts the Pi down, cycles PoE, then
  **polls** for it to come back (tolerating the ssh-refused boot window).
- `--force` is needed only if the rig can't be reached to run `shutdown`.
- Communities default to the switch's standard values (read `public`, write
  `private`); override with `RIG_SNMP_{READ,WRITE}_COMMUNITY` if they change.
- It does **not** check USB / the gale EC — verify that separately with
  `tools/flash_puck_usb.py ec sysinfo`.
- Full detail + the underlying SNMP: `tools/RIG-POWER-CYCLE.md`.

## The second bench: rpi4-gwifi

`rpi4-gwifi.iot.welland.mithis.com` — Pi 4 with the dev gale puck, same layout
(EC bridge `18d1:500f`, `eth-gwan`/`eth-glan` dongles). Provisioned 2026-07-10
(tools tree, `~/gale-netboot`, dnsmasq installed with the system service
disabled, udev rule for the bridge). **On this bench the puck's netboot port
is cabled to `eth-glan`** — never assume dongle names match cabling; the
autonomous test watches both dongles and says which one the puck is on.

## gale EC power/lock gotchas (hardware-proven 2026-07-10)

- **WP_L is sensed from the SYS_PWR domain.** `gale power off` drops
  SYS_PWR_EN ⇒ WP_L=0 ⇒ `system_is_locked()` ⇒ every console `gale ...` set
  is refused (status prints, no `OK`) until an **EC cold reboot** restores
  the SYS_PWR_EN=high default. Never `gale power off` in scripts; reset a
  running AP with `flash_puck_usb.py ec reboot --deadline 2` (expect the USB
  pipe error, reopen in a new process).
- A freshly cold-booted puck is **parked + unlocked**; `gale power on` works
  from RO and is the exact console equivalent of the autonomous charger
  trigger (`pd_set_input_current_limit(5V, >2.5A)` → `set_ap_power(1)`,
  which has **no lock gate**). SuzyQ = SNK_ACCESSORY ⇒ parked by design; a
  5V/3A supply powers the AP autonomously.
- SYS_PWR_EN also powers the ethernet PHYs: **carrier proves nothing** about
  the AP being alive on a parked puck.
- Autonomous-boot verification: `tools/netboot-verify/autonomous_boot_test.py
  [WATCH_S] [WAN_IF] [DOWN_IF]` (run on the bench with /usr/bin/python3;
  `WAN_IF=none` proves the no-server eMMC-fallback path).
- **Do not touch the EC/AP consoles during the AP's first seconds of boot.**
  The only netboot "wedges" ever seen (RX-only, no DHCP TX, runs 3/4 on
  2026-07-10) happened when the harness claimed the AP console interface
  (clear_halt) and polled `gpioget` while the SBL was reading the EC-shared
  SPI flash — the same perturbation class as the gale SPI wedge. With the
  trigger-then-hands-off ordering: 16/16 consecutive autonomous
  netboot→OpenWrt boots, incl. 6/6 with ALL USB closed after the trigger
  (`hands_off_boot_test.py`) and dual-port cabling throughout. Attach
  consoles BEFORE the power-on trigger, or not at all.

## Final no-SuzyQ proof — ARMED (2026-07-10)

`tools/netboot-verify/final_pd_verify.py` is running on rpi4-gwifi
(log `~/gale-netboot/final_pd.log`), netboot server live on eth-glan,
Tasmota (10.1.91.18) AC on. **The one human step:** unplug the SuzyQ from
the puck's USB-C and plug in the stock Google Wifi adapter (adapter AC
side in the Tasmota plug). Everything after is automatic: it detects the
first autonomous adapter-powered boot, then runs 5 unattended AC
cold-plug cycles and prints the N/N verdict — the literal production
scenario (no debug cable, plain 5V/3A supply), judged from the wire.

## Key hardware tools (all on `tools/`)

- **`flash_puck_usb.py`** — the single, verified libusb tool for ALL gale
  hardware I/O over the EC USB-SPI bridge: `read`, `flash`, `ec <cmd>`,
  `verify-boot`. Runs under **`/usr/bin/python3`** (system pyusb), not `uv`.
  Never use `flashrom` on gale. Runbook: `tools/FLASH-RUNBOOK.md`.
- **`fleet/build_gale_fleet_image.py`** — builds a per-puck dev-key TFTP-first
  image from a live dump (self-gating; reproducible).
- **`netboot-verify/`** — netboot/boot verification helpers (rig-side).

## Conventions

- Python via `uv` (except `flash_puck_usb.py` and its helpers, which need system
  pyusb). Use Python, not bash, for anything with loops/conditionals.
- ssh: never `-H`, never `StrictHostKeyChecking=no` (use `accept-new`).
- Never redirect stderr to `/dev/null`; never write temp files to `/tmp`.
- The switch and rig are reliable: a reboot/cycle that misbehaves is a **script**
  bug (short timeout, missed poll, mis-parse), not flaky hardware.
