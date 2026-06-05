# gwifi-openwrt

Running **OpenWrt** on **Google Wifi** (1st-gen, board codename **`gale`**) pucks.

Google Wifi `gale` is a headless **Qualcomm IPQ4019** (IPQ40xx, quad-core ARMv7
Cortex-A7) router that ships ChromeOS-style verified-boot firmware (**coreboot +
depthcharge**) on an 8 MiB SPI-NOR, with the kernel/rootfs on eMMC. This repo
collects the tooling, documentation, and firmware work needed to boot and run
OpenWrt on it.

## What's here

- **[`depthcharge-ipq4019/`](https://github.com/mithro/depthcharge-ipq4019)**
  (submodule) — a new **IPQ4019 ESS EDMA ethernet driver for depthcharge** so
  `gale` can **TFTP-netboot** from its *onboard* ethernet ports (previously only
  a USB-ethernet dongle worked). Includes the full bring-up docs, the from-scratch
  build recipe, recovery procedures, and the `mithro/depthcharge` fork as a nested
  submodule.
- **[`gale-spi-flash-backup.md`](gale-spi-flash-backup.md)** — how to back up the
  `gale` SPI boot flash over a **SuzyQ/CCD cable** with `flashrom` (no case-opening,
  no eMMC access).
- **[`gale-ec/`](gale-ec/)** — the **reconstructed `board/gale` EC-firmware source**,
  reverse-engineered from this unit's EC dump (`gale-ec-*.bin`). `make BOARD=gale`
  rebuilds it, and an independent reviewer certified the result **functionally
  equivalent** to the dump. See [`gale-ec/FIDELITY.md`](gale-ec/FIDELITY.md).

## Approach

`gale` has no removable media and a locked-down boot flow, so the safe path is:

1. **Back up the stock SPI flash** first (see `gale-spi-flash-backup.md`) — keep it
   as your undo image.
2. **Netboot OpenWrt over TFTP** using a depthcharge build that includes the
   IPQ4019 driver (see the submodule's `docs/build.md` and
   `docs/post-recovery-recipe.md`).
3. Once validated, install OpenWrt to eMMC.

Full, verified step-by-step procedures live in the
[`depthcharge-ipq4019`](https://github.com/mithro/depthcharge-ipq4019) submodule's
`docs/`.

## Firmware images (not included)

Large binaries are intentionally **not** committed to this repository. Obtain them
as follows:

- **ChromeOS recovery image** (board `gale`) — published by Google; find the image
  for board **`gale`** via the Chromebook Recovery Utility or the ChromeOS recovery
  image catalog. Used to restore the device to stock.
- **OpenWrt firmware** — build OpenWrt for target **`ipq40xx`** / subtarget
  **`chromium`**, device **`google_wifi`** (produces
  `openwrt-<ver>-ipq40xx-chromium-google_wifi-squashfs-{factory,sysupgrade}.bin`),
  or download a build from the OpenWrt firmware selector. See the OpenWrt
  *Google Wifi* device page.

## Clone

```sh
git clone --recursive https://github.com/mithro/gwifi-openwrt.git
# or, after a plain clone:
git submodule update --init --recursive
```

## Layout

```
README.md                  this file
gale-spi-flash-backup.md   SuzyQ SPI-flash backup procedure
depthcharge-ipq4019/       submodule: IPQ4019 netboot driver + docs (+ depthcharge fork)
```

## License

Documentation and scripts in **this** repository are **Apache-2.0**
(© 2026 Tim 'mithro' Ansell). The `depthcharge-ipq4019` submodule and its nested
`depthcharge` fork are **GPL-2.0-or-later** (they derive from ChromeOS depthcharge
and U-Boot); see those repositories for details.

## Safety & privacy note

These procedures touch per-device identity (VPD: serial numbers, MAC addresses)
stored in SPI flash. The stock SPI dump of a real unit is **not** published here
because it contains that unit's unique identifiers — make and keep your own backup
privately.
