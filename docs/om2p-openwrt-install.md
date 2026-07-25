# Installing OpenWrt on the Open-Mesh OM2P (first flash via ap51-flash)

The OM2P nodes ship Open-Mesh / CloudTrax stock firmware. Getting OpenWrt onto
them the first time uses **`ap51-flash`** — a host tool that pushes an image to
the device's bootloader over a direct Ethernet link during the boot window. After
that first flash, OpenWISP manages upgrades over SSH (`sysupgrade`).

> On-hardware flashing is bench work; this note is the procedure, not something
> the build performs. See the build in [`../om2p-image/`](../om2p-image/) and the
> design in [`om2p-autoprovision-mesh-design.md`](om2p-autoprovision-mesh-design.md).
> It parallels the gale path in [`gale-openwrt-netboot-install.md`](gale-openwrt-netboot-install.md).

## The artifact

There is **no separate factory image** for these devices. The
`openmesh-image`-wrapped **sysupgrade** is the flashable artifact:

```
openwrt-…-openmesh_om2p-<rev>-squashfs-sysupgrade.bin
```

Pick the file matching the unit's revision (`lc`, `v1`, `v2`, or `v4`). If unsure,
the OM2P-LC is the 4-of-6 majority; the bare "OM2P" units report their exact
revision once booted into OpenWrt.

## Procedure (outline)

1. Install `ap51-flash` on a host with a wired NIC
   (`https://github.com/openwrt/ap51-flash`, or the Open-Mesh build).
2. Connect the host NIC **directly** to the OM2P's PoE/uplink port (use a PoE
   injector to power the unit). No other DHCP server on that link.
3. Start the flasher pointed at the NIC and the chosen image, then **power on**
   the OM2P — ap51-flash detects the bootloader and pushes the image:
   ```sh
   sudo ap51-flash <iface> openwrt-…-openmesh_om2p-<rev>-squashfs-sysupgrade.bin
   ```
4. Wait for it to report success and the unit to reboot. Do **not** interrupt
   power during the write.

## First boot / onboarding

On first boot the baked overlay:

- selects the uplink port by board name (eth1 on lc/v2, eth0 on v1/v4), builds
  the 802.1q trunk + batman mesh + per-VLAN bridges, and puts the second port on
  the roam VLAN (20);
- brings up `radio0` + the 802.11s mesh (`gwifi-mesh`);
- requests DHCP on the management VLAN (5) and runs `openwisp-config`, which
  registers the device with `https://wisp.welland.mithis.com` (matched by MAC).

Confirm the device appears in OpenWISP, then assign/push the `gwifi-om2p` template
(see `../openwisp/build-templates.py`). For the two bare "OpenMesh OM2P" devices,
set their `uplink_port`/`client_port` context once they report their exact
revision.

## Upgrades (after first flash)

Managed via the OpenWISP firmware-upgrader (`sysupgrade` over SSH) once the
matching firmware image is registered (see `../openwisp/upload-firmware.py`).
Validate the `sysupgrade` path on one unit before relying on it fleet-wide.
