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
export RIG_SNMP_WRITE_COMMUNITY=…      # from the secrets store / Tim; NEVER in a file
tools/rig_power_cycle.py --dry-run     # validate switch + port, change nothing
tools/rig_power_cycle.py               # clean shutdown -> PoE off/on -> wait for ssh
tools/rig_power_cycle.py --force       # hard-cycle even if the rig can't be shut down
```

- Pre-flights the VPN/switch, **validates the PoE port** (ports move — never
  trust a remembered ifIndex), cleanly shuts the Pi down, cycles PoE, then
  **polls** for it to come back (tolerating the ssh-refused boot window).
- `--force` is needed only if the rig can't be reached to run `shutdown`.
- Communities come from `RIG_SNMP_{READ,WRITE}_COMMUNITY` (read defaults to
  `public`) — **never** store the write community in a file.
- It does **not** check USB / the gale EC — verify that separately with
  `tools/flash_puck_usb.py ec sysinfo`.
- Full detail + the underlying SNMP: `tools/RIG-POWER-CYCLE.md`.

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
