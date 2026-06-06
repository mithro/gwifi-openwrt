<!-- SPDX-License-Identifier: Apache-2.0 -->
# Netboot-install OpenWrt on gale (Google Wifi) over TFTP

Install OpenWrt on a `gale` puck **entirely over the network**: TFTP-netboot a
RAM-only OpenWrt, then from that running system write the firmware to the eMMC.
No case-opening, no eMMC clip.

This is the detailed version of steps 2–3 of the repo
[README](../README.md#approach). The bootloader/firmware side (flashing the
depthcharge netboot payload, the SuzyQ/CCD cable) lives in the
[`depthcharge-ipq4019`](../depthcharge-ipq4019) submodule; this doc covers the
**OpenWrt** side.

```
  ┌────────────┐   eth (WAN port)    ┌──────────────────────┐
  │ your Linux  │◄───────────────────►│ gale (depthcharge     │
  │ host        │  DHCP+TFTP+HTTP     │ netboot firmware)     │
  │ 192.168.50.1│                     │  + SuzyQ → serial     │
  └────────────┘                     └──────────────────────┘
        1. serve .itb over TFTP  ──► gale TFTP-boots it into RAM
        2. serve factory.bin over HTTP ──► gale fetches + dd's to eMMC
        3. stop serving ──► gale reboots, falls back to eMMC = installed
```

---

## 0. Prerequisites

- **gale runs a depthcharge build with TFTP netboot** — the IPQ4019-driver
  `netboot` payload (boots straight into netboot) **or** the `dev` payload
  (normal boot + `Ctrl+N`). Build/flash per
  [`depthcharge-ipq4019/docs/build.md`](../depthcharge-ipq4019/docs/build.md).
  Stock Google depthcharge will **not** do this.
- **Serial console** to gale via SuzyQ/CCD (`ttyMSM0`, **115200 8N1**). This is
  the reliable way to drive the RAM system (gale is headless). The netbooted
  kernel's console is already `console=ttyMSM0,115200n8` (hard-coded in
  `netboot.c`).
- **A wired link** from your host to a gale ethernet port. Use the **WAN port**
  (the one with the **printed MAC label** — `02_network` derives `wan` from the
  label MAC), so the default OpenWrt `wan` DHCP client brings it up on your
  host's subnet after boot.
- **The two build artifacts** (from `openwrt/bin/targets/ipq40xx/chromium/`):
  - `…-google_wifi-initramfs-fit-zImage.itb` — the **raw** netboot FIT
    (produced by the patch in [`../openwrt-patches/`](../openwrt-patches);
    *not* the `.itb.vboot`).
  - `…-google_wifi-squashfs-factory.bin` — the full eMMC image (first install).
- Host tools: `dnsmasq`, and any static HTTP server. Run the privileged steps
  with `sudo`.

> **Sanity check the FIT before you start** — it must be a raw FIT, not the
> vboot-wrapped one:
> ```sh
> xxd -l4 openwrt-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb   # d00dfeed
> ```
> If you only have the `.itb.vboot`, you didn't apply the
> [netboot-FIT patch](../openwrt-patches); see that README.

---

## 1. Server setup (DHCP + TFTP + HTTP)

Pick the host NIC cabled to gale (here `eth1`) and give it a static address:

```sh
sudo ip addr flush dev eth1
sudo ip addr add 192.168.50.1/24 dev eth1
sudo ip link set eth1 up
```

Stage the files and start a static HTTP server (for the eMMC image):

```sh
mkdir -p /srv/tftp
cp openwrt-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb /srv/tftp/
cp openwrt-ipq40xx-chromium-google_wifi-squashfs-factory.bin     /srv/tftp/

# serve /srv/tftp over HTTP on :8000 (any static server works)
( cd /srv/tftp && python3 -m http.server 8000 ) &
```

Write a minimal dnsmasq config (`/etc/dnsmasq-gale.conf`):

```ini
interface=eth1
bind-interfaces
# no DNS, this is a provisioning-only instance
port=0
dhcp-range=192.168.50.50,192.168.50.150,12h
# becomes the DHCP "bootfile" + next-server that depthcharge netboot reads
dhcp-boot=openwrt-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb
enable-tftp
tftp-root=/srv/tftp
log-dhcp
```

Validate and run it in the foreground (so you can watch the transfer):

```sh
dnsmasq --test -C /etc/dnsmasq-gale.conf      # "syntax check OK"
sudo dnsmasq -d -C /etc/dnsmasq-gale.conf
```

Leave this terminal up — you'll see the `DHCPDISCOVER`/`DHCPOFFER` and the
TFTP `sent …/openwrt-…itb` line when gale boots.

---

## 2. Netboot OpenWrt into RAM

Open the serial console in a second terminal, then power-cycle gale:

```sh
# e.g. picocom; the SuzyQ enumerates a CCD/AP TTY — pick the AP console
picocom -b 115200 /dev/ttyUSB0
```

- `netboot` payload: it starts netboot automatically.
- `dev` payload: press **`Ctrl+N`** at the depthcharge prompt.

On the serial console you should see depthcharge do its thing:

```
MAC: xx:xx:xx:xx:xx:xx
My ip is 192.168.50.50
Bootfile supplied by DHCP server: openwrt-…-initramfs-fit-zImage.itb
The bootfile was 8080404 bytes long.
...
```

…then the **OpenWrt** kernel banner and, after a few seconds, a root shell
prompt on the serial console. You are now running OpenWrt **in RAM** — nothing
on the eMMC has changed yet.

> If it instead prints `Bad FIT header magic value 0x4348524f`, you served the
> `.itb.vboot` (CHROMEOS keyblock) instead of the raw `.itb`. Swap the file.

---

## 3. Install to eMMC (first install)

From the gale serial shell.

**3a. Pull the image over the network.** The port you cabled comes up as `wan`
(DHCP client) and will have grabbed an address from your dnsmasq:

```sh
ip -4 addr show wan          # expect 192.168.50.x; gateway/host is .1
# if it's empty, bring the cabled port up by hand:
#   ip link            # find the port with NO-CARRIER cleared (link up)
#   udhcpc -i eth0     # or eth1 — whichever shows carrier
uclient-fetch -O /tmp/factory.bin \
  http://192.168.50.1:8000/openwrt-ipq40xx-chromium-google_wifi-squashfs-factory.bin
```

**3b. Identify the eMMC — do NOT skip this.** `factory.bin` is a whole-disk GPT
image and gets written to the **block device**, erasing it:

```sh
cat /proc/partitions          # the ~3.7 GB disk with no "p" suffix = eMMC
ls -l /dev/mmcblk*            # expect /dev/mmcblk0 (eMMC); mmcblk1* if an SD-like dev exists
```

Confirm `/dev/mmcblk0` is the internal eMMC (largest fixed device) before the
next step.

**3c. Write it.**

```sh
dd if=/tmp/factory.bin of=/dev/mmcblk0 bs=4M conv=fsync
sync
partx -u /dev/mmcblk0 2>/dev/null || true
cat /proc/partitions          # now shows mmcblk0p1 (kernel) + mmcblk0p2 (rootfs)
```

`factory.bin` lays down the ChromeOS GPT: **p1 = `kernel`** (the cros_kernel
partition depthcharge boots from) and **p2 = `rootfs`** (squashfs). The
read-write `overlay` (rootfs_data) is created automatically on first boot in the
remaining space.

---

## 4. Boot the installed system

The netboot firmware tries **TFTP first**, every boot. To make it fall back to
the freshly-installed eMMC kernel, remove the TFTP path:

```sh
# on the host: stop the provisioning server (Ctrl-C the `dnsmasq -d`), or:
sudo pkill -f dnsmasq-gale.conf
# (or simply unplug the ethernet cable from gale)
```

Then reboot gale (`reboot` on the serial console). depthcharge will wait out the
netboot link/DHCP timeout (~15–45 s — see `netboot.c`
`NETBOOT_LINK_TIMEOUT_MS`/`NETBOOT_DHCP_MAX_TRIES`), print
`=== Falling back to eMMC kernel partition ===`, and boot your installed OpenWrt
from `mmcblk0p1`.

Reconnect the cable afterwards; the installed system uses `wan` as a normal
uplink.

---

## 5. Updating later (sysupgrade)

Once OpenWrt is on eMMC you don't need the factory image again — use the
**sysupgrade** image, which preserves config (`platform.sh` runs
`emmc_do_upgrade` + `emmc_copy_config` for `google,wifi`):

```sh
# on the running gale (over SSH on the LAN side, or serial):
scp …-google_wifi-squashfs-sysupgrade.bin root@<gale>:/tmp/
ssh root@<gale> 'sysupgrade -v /tmp/…-sysupgrade.bin'   # add -n to wipe config
```

You can also run `sysupgrade` from a netbooted RAM session (handy if the eMMC
install is broken): repeat §2, then `uclient-fetch` the **sysupgrade** image and
`sysupgrade -n /tmp/…-sysupgrade.bin`.

---

## Troubleshooting

| Symptom (serial console) | Cause / fix |
|---|---|
| `netboot: no link; … fall back to eMMC` | Cable/port: try the other ethernet port; check host NIC is `up` with carrier. |
| `Dhcp failed, retrying` | dnsmasq not serving on that NIC — check `interface=`, that no other DHCP server is on the wire, and `log-dhcp` output. |
| `Tftp failed` | `.itb` not in `tftp-root`, or name ≠ `dhcp-boot=`. Confirm `dnsmasq -d` logs the TFTP request. |
| `Bad FIT header magic value 0x4348524f` | Served the `.itb.vboot`; serve the raw `.itb` (magic `d00dfeed`). |
| `Bad FIT header magic value 0x00000000` | Served `factory.bin` (a disk image) as the bootfile — that's not netbootable; it's for §3 only. |
| OpenWrt boots but `uclient-fetch` can't reach host | The cabled port came up as `lan` (static 192.168.1.1), not `wan`. `udhcpc -i <cabled-port>` to get a host-subnet address (see §3a). |
| After install it keeps netbooting | TFTP is still reachable (firmware tries it first). Stop dnsmasq / unplug before rebooting (§4). |

---

## How it works (why two stages, not one)

depthcharge's TFTP path loads the bootfile straight into RAM and hands it to
`fit_load()`, which requires a **raw FIT** (`netboot.c` → `boot()` →
`fit.c:fit_load`, magic `0xd00dfeed`). It is a **kernel loader**, not an
installer — it has no way to write a disk image to storage. So:

1. **Netboot** loads a *kernel* (the initramfs FIT, kernel+rootfs embedded,
   `console=ttyMSM0`, no `root=` needed) — a complete OpenWrt in RAM.
2. **That OpenWrt** is what writes `factory.bin` (a GPT *disk image*) to the
   eMMC block device — the only component that can.

This is exactly why `factory.bin` cannot be "netbooted" directly, and why the
build must emit the unwrapped FIT (see [`../openwrt-patches/`](../openwrt-patches)).
The eMMC boot path *can* consume the wrapped `.itb.vboot` because it strips the
`CHROMEOS` keyblock itself (`emmc_fallback.c`); the TFTP path does not.
