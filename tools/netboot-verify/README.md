<!-- SPDX-License-Identifier: Apache-2.0 -->
# gale netboot / boot verification tooling

Rig-side helpers (run on `rpi3b-gwifi`, which is cabled to a puck's WAN via
`eth-gwan` and drives the puck's EC over libusb with `flash_puck_usb.py`) for
verifying that a freshly-flashed gale boots its dev-key netboot firmware
end-to-end. Companion to [`docs/gale-openwrt-netboot-install.md`](../../docs/gale-openwrt-netboot-install.md).

Paths are hard-coded for that rig (`~/gale-netboot/` staging dir, the pre-flash
dump under `~/local/gwifi/fleet-flash/backups/`). Adjust before reuse elsewhere.

## Files

- **`dnsmasq-gale.conf`** — provisioning-only DHCP+TFTP on `eth-gwan`. Uses
  `bind-dynamic` (NOT `bind-interfaces`, which logs "no address" and won't answer
  the freshly-added WAN IP). Serves the raw FIT as `netboot.itb`.
- **`netboot_verify.sh`** — brings up the server, boots the AP via `verify-boot`
  (which un-parks the parked EC — plain `gale power on` is a no-op after a cold
  boot), watches for the DHCP lease + TFTP of the FIT, then waits for OpenWrt's
  `udhcpc` lease (hostname `OpenWrt`) and SSHs in. PROVEN: DHCP → `sent
  netboot.itb` → `DHCPACK ... OpenWrt` → live shell. Note SSH to the puck's WAN
  is REJECTed by OpenWrt's firewall; reach dropbear on the LAN (`192.168.1.1`).
- **`reboot_retry_verify.sh`** — EC-driven: boots the AP via `verify-boot` with
  NO server (blank eMMC) and watches the WAN for periodic DHCP bursts. NOTE: the
  SuzyQ/EC rig can't demonstrate the loop — `cold_reboot()` (SoC self-reset)
  doesn't re-trigger the EC's external power-on, so the AP wedges after one cycle.
  Kept for diagnostics; for the real validation use `reboot_loop_validate.sh`.
- **`reboot_loop_validate.sh`** — the actual reboot-retry **validator**. Sniffs
  the WAN, counts DHCP-discover bursts, prints a live status line every 30s, and
  gives a PASS/FAIL verdict (≥3 evenly-spaced bursts = self-healing loop). Run it
  with the gale on **normal USB-C PD power** (not the SuzyQ), eMMC blank, no
  netboot server. Optional 4th arg = a Tasmota plug host/IP: if given it
  power-cycles the gale (off 5s, on) for a clean fresh boot before sniffing
  (`... eth-gwan 240 44:07:0b 10.1.91.18`). Full procedure:
  [`docs/reboot-retry-validation.md`](../../docs/reboot-retry-validation.md).
- **`plug_power_probe.py`** — pre-flight for the above. Power-cycles the gale via
  its Tasmota plug and watches **real-power draw** as an AP-boot signal (no
  EC/console needed): ~2W = EC+PHY only (**AP OFF/parked**); ≥4W = AP booting.
  Use it to confirm the AP actually boots on PD before spending a full validator
  window. NOTE (2026-07-08): a PD-only gale left parked by prior CCD/SuzyQ work
  stays at ~2W even after a 60s AC drain — un-parking needs an EC reboot over
  CCD, which the single USB-C port can't do while a plain PD adapter is attached.
  A PD-capable servo (CCD+PD together) is the way to validate the loop.
- **`restore_rw_nvram.py`** — restore RW_NVRAM (`0x6f0000`, in the RW area) from
  the clean pre-flash dump to clear a persistent `RW_NO_KERNEL (0x5b)` vboot
  recovery loop (self-inflicted by repeated no-server verify-boots on stock
  firmware). Uses `flash_puck_usb.py`'s tested `flash_region`. Run with
  `/usr/bin/python3` (system pyusb). Obsoleted for the fleet by the vboot
  reboot-retry patch, but handy for stock-firmware pucks.
- **`ap_console_probe.py <cmd>`** — run a shell command on the puck's AP serial
  console (`if1`, the EC's AP stream) — e.g. a running netbooted OpenWrt, which
  auto-logs-in root. Used to confirm dropbear + the WAN firewall directly.

## Hard-won gotchas (see memory: gale-verify-boot-wedged-bench)

- `verify-boot` **0 bytes = the AP never booted** (bench wedge), NEVER "no
  console". The E87 console works fine. PoE cold-boot the whole bench and retry.
- The console IS bidirectional over `if1` (interactive root shell confirmed).
