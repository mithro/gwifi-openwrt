# ten64 Wi-Fi VM — aarch64 OpenWrt VM image — Design Spec

> Status: approved (design), pending spec review. The build target of this spec is
> **only the VM image** (a sibling of `gale-image`/`om2p-image`). The host-side VFIO
> passthrough, libvirt domain, cutover, and OpenWISP device template are **deferred**
> to follow-on deliverables (see §3).

## 1. Summary

Produce an OpenWISP-managed OpenWrt **aarch64 VM image** that will run as a KVM guest
on **ten64** and own ten64's two PCIe Wi-Fi radios once they are passed through. The
image is built by the same overlay+secret-substitution pattern as `gale-image` and
`om2p-image`, reuses the DRY shared `fleet-files/` overlay (the
backhaul-gate + hotplug hook), and is a **full mesh sibling of gale**: the WiFi-6 radio carries the
802.11s + batman-adv mesh in addition to client APs, so the core node is both a wired
batman gateway and an RF mesh anchor.

This deliverable ends at: *image builds → boots in a VM → runs first-boot bootstrap →
openwisp-config attempts controller registration.* No radio is required to validate it.

## 2. Goals

- **G1** A new `tenvm-image/` sibling that builds a bootable aarch64 OpenWrt image for
  the `armsr/armv8` target, as a `combined-efi.img` directly bootable under QEMU/KVM.
- **G2** Same managed feature set as gale: `openwisp-config` + `openwisp-monitoring`,
  batman-adv mesh, 802.11s SAE (`wpad-mesh-mbedtls`), `usteer`, LuCI.
- **G3** Driver + firmware for **both** of ten64's PCIe radios baked in:
  `kmod-ath11k-pci` + `ath11k-firmware-qcn9074` (QCN6024/9074), and
  `kmod-ath10k` + `ath10k-firmware-qca9377` (QCA9377).
- **G4** Reuse the DRY `fleet-files/` overlay (`gwifi-backhaul-gate` + hotplug hook)
  verbatim — the VM joins the same fleet behaviour with zero overlay divergence. (The
  OpenWISP UCI is a *per-image* file, like gale/om2p — see R3/§7.5.)
- **G5** First-boot bootstrap establishes the same VLAN map, `bat0`, per-VLAN bridges
  and backhaul-gating cron as gale, adapted to a **virtio trunk NIC (`eth0`)** instead
  of the gale DSA `wan` port.
- **G6** Radios identified at first boot **by driver/capability**, not by hardcoded
  path (a VM gets guest-assigned PCI slots), and the bootstrap is a no-op when no radio
  is attached — so the image boots and provisions before passthrough exists.
- **G7** Validation: a `verify-tenvm-image.py` rootfs check (packages + overlay + cron),
  **plus** a headless QEMU smoke-boot that confirms the image reaches first-boot.

## 3. Non-goals (deferred to follow-on deliverables)

- VFIO bind of the two radio endpoints; host `vfio-pci` / driverctl wiring.
- The libvirt domain XML, guest VLAN/bridge attachment on ten64, no-FLR reset handling,
  Layerscape MSI/SMMU passthrough verification.
- Live cutover from ten64's native `hostapd@wlan-*` services, with rollback.
- The OpenWISP **device template** for this node (client SSIDs, VLAN/bridge config) —
  client SSIDs are pushed by OpenWISP and are **never baked into the image** (same as
  gale). No real SSIDs/keys/MACs appear in this repo.

## 4. Context & assumptions

- **Build tree:** OpenWrt at `/home/tim/local/gwifi/openwrt`, v25.12.4 (r32933), feeds
  updated/installed. `openwisp-config` (1.2.1) and `openwisp-monitoring` (0.3.1) come
  from the **packages** feed (`feeds/packages/admin/`), no custom feed needed.
- **ten64 radios (verified live, read-only probe 2026-06-09):**
  - `0001:03:00.0` — Qualcomm **QCN6024/9024/9074** `[17cb:1104]`, driver `ath11k_pci`,
    WiFi-6 (HE), currently 5 GHz (ch36/80). The phy advertises `HE Iftypes: mesh point`.
    Firmware on ten64: `/lib/firmware/ath11k/QCN9074/hw1.0/{amss,board-2,m3}.bin` →
    OpenWrt package `ath11k-firmware-qcn9074`.
  - `0001:04:00.0` — Qualcomm Atheros **QCA9377** `[168c:0042]`, driver `ath10k_pci`,
    currently 2.4 GHz (ch6). Firmware `/lib/firmware/ath10k/QCA9377/hw1.0/` → OpenWrt
    package `ath10k-firmware-qca9377` (mainline; this tree has **no** `-ct` variant,
    which also avoids the ath10k-CT reset history seen on the gale's IPQ4019).
  - Both radios are in ten64 IOMMU group 1 (relevant only to the deferred passthrough).
- **VM platform:** ten64 is aarch64 (LS1088A), so the guest is aarch64; `armsr/armv8`
  is OpenWrt's generic UEFI aarch64 target intended for servers/VMs.
- The fleet VLAN map is fixed fleet-wide: `mgmt=5 int=10 roam=20 iot=90 guest=99`;
  `mgmt` (VID 5) is the DHCP/management VLAN whose gateway is ten64.

## 5. Requirements (decided with user)

- **R1 (mesh role):** *Full sibling of gale.* The ath11k 5 GHz radio carries 802.11s +
  batman (`mesh0` on the mesh hardif) **and** 5 GHz client APs; the ath10k 2.4 GHz radio
  carries 2.4 GHz client APs. The VM runs `batctl gw server` (it has a wired uplink to
  ten64) and anchors the RF mesh. The fleet overlay stays 100% uniform.
- **R2 (validation depth):** verify script **and** headless QEMU smoke-boot.
- **R3 (DRY):** `gwifi-backhaul-gate` + the hotplug hook are the shared `fleet-files/`
  source, merged at build time — not copied/forked into `tenvm-image/`. The OpenWISP UCI
  (`etc/config/openwisp`) is per-image: each of gale/om2p ships its own, and so does
  tenvm (the controller stanza is identical apart from build-time secret substitution).
- **R4 (no secrets / no sensitive data):** placeholders only in committed overlay; real
  secrets substituted at build from `fleet-secrets.conf`; no SSIDs/MACs in the repo.

## 6. Architecture

### 6.1 Target & artifact
- Target tuple: `CONFIG_TARGET_armsr=y`, `CONFIG_TARGET_armsr_armv8=y`.
- Filesystem: `CONFIG_TARGET_ROOTFS_EXT4FS=y`; `CONFIG_TARGET_ROOTFS_PARTSIZE=256`
  (MiB) for headroom (openwisp-monitoring, logs). Image: **`combined-efi.img`** (GPT:
  EFI system partition with grub + kernel, plus the rootfs partition).
- Boot path: libvirt/QEMU `virt` machine + UEFI (AAVMF/edk2) → grub → OpenWrt kernel.
  Serial console on `ttyAMA0` (and `ttyS0` fallback) for headless operation.

### 6.2 Boot/provisioning flow (radio-independent)
1. UEFI → grub → kernel → procd userspace.
2. `uci-defaults/99-tenvm-bootstrap` runs once: builds `bat0` + the VLAN trunk on
   `eth0` + per-VLAN bridges, installs the backhaul-gating cron, then runs the
   radio-identification step (no-op if no phy present).
3. `openwisp-config` starts and registers with the controller over `br-mgmt`.
4. The backhaul-gate evaluates: with a working wired uplink it sets `gw server` and
   serves APs (whatever OpenWISP has pushed).

`★ The image is decoupled from the radios:` steps 1–3 work with zero radios attached,
which is exactly what the QEMU smoke-boot exercises. Radio bring-up (step 4's APs) is
completed only once the deferred passthrough work attaches the real hardware.

## 7. Component design

### 7.1 Package fragment — `tenvm-image/tenvm.config`
Mirrors `gale.config` plus the two radio stacks and the VM target/rootfs lines:
```
CONFIG_TARGET_ROOTFS_EXT4FS=y
CONFIG_TARGET_ROOTFS_PARTSIZE=256
CONFIG_PACKAGE_openwisp-config=y
CONFIG_PACKAGE_openwisp-monitoring=y
CONFIG_PACKAGE_kmod-batman-adv=y
CONFIG_PACKAGE_batctl-default=y
# CONFIG_PACKAGE_wpad-basic-mbedtls is not set
CONFIG_PACKAGE_wpad-mesh-mbedtls=y
CONFIG_PACKAGE_usteer=y
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_ip-full=y
CONFIG_PACKAGE_tcpdump-mini=y
CONFIG_PACKAGE_ethtool=y
# radios passed through from the host (VFIO) — drivers + firmware:
CONFIG_PACKAGE_kmod-ath11k-pci=y
CONFIG_PACKAGE_ath11k-firmware-qcn9074=y
CONFIG_PACKAGE_kmod-ath10k=y
CONFIG_PACKAGE_ath10k-firmware-qca9377=y
```
The target lines themselves (`CONFIG_TARGET_armsr*`) are prepended by the build script
(mirroring how `build-gale-image.sh` prepends the ipq40xx target lines).

### 7.2 Build script — `tenvm-image/build-tenvm-image.sh`
Structurally identical to `build-gale-image.sh`:
1. Render `tenvm-image/files` + the shared `fleet-files/.` into `$OWRT/files`,
   substituting the four secrets (`__OPENWISP_*__`, `__MESH_*__`) with the same
   metacharacter-escaping `esc()`.
2. `chmod 0755` the bootstrap, the gate, and the hotplug hook.
3. Seed `.config` with the armsr/armv8 target lines + `tenvm.config`, `make defconfig`,
   `make -j"${JOBS:-6}"`.
4. Output dir: `$OWRT/bin/targets/armsr/armv8/`. `RENDER_ONLY=1` short-circuits as in gale.

### 7.3 First-boot bootstrap — `tenvm-image/files/etc/uci-defaults/99-tenvm-bootstrap`
Same logic as `99-gale-bootstrap` with two adaptations:
- **Trunk port:** a single variable `UPLINK=eth0` replaces gale's `wan`. The per-VLAN
  tagged sub-ifaces become `eth0.<vid>`; bridges still pair `eth0.<vid>` + `bat0.<vid>`;
  `mgmt` is DHCP, the rest `proto none`. `bat0`/`mesh_hardif` config is identical.
- **Backhaul cron + crond enable:** identical idempotent block (the gate/hook come from
  `fleet-files/`).
- **Radio identification (new, VM-specific):** after `wifi config` (auto-detect), assign
  roles by **driver**, not path: resolve each generated `radioN`'s phy via its `path`,
  read `/sys/class/ieee80211/<phy>/device/driver`; the `ath11k_pci` radio gets the mesh
  hardif `mesh0` (802.11s SAE, `mesh_fwding 0`) + 5 GHz band defaults, the `ath10k_pci`
  radio gets 2.4 GHz band defaults. **No-op when no radio/phy is present** (image-first /
  pre-passthrough). Client SSIDs are *not* created here — OpenWISP owns them.

### 7.4 Wireless seed — `tenvm-image/files/etc/config/wireless`
Unlike gale (fixed SoC `path`), the VM ships a **minimal** `wireless` defining only the
`mesh0` wifi-iface template (mesh_id/key placeholders, `network 'mesh_hardif'`,
`mesh_fwding '0'`); the `wifi-device radioN` stanzas and the mesh0 `device` binding are
completed at first boot by §7.3 once phys exist. (Rationale: guest PCI paths are
unknown until the libvirt XML pins them; capability/driver matching is path-independent.)

### 7.5 OpenWISP config & secrets
tenvm ships its **own** `files/etc/config/openwisp` (per-image, like gale/om2p) — the
controller stanza with `management_interface 'br-mgmt'` and `__OPENWISP_*__` placeholders
substituted at build time. It is **not** in `fleet-files/` (which holds only the gate +
hook). tenvm also ships its own `files/etc/config/usteer`, mirroring gale.

## 8. VM/network integration model (image-side only)

The VM presents a **single virtio trunk NIC (`eth0`)** carrying all fleet VLANs, mirroring
gale's single trunked uplink. On the host (deferred), that NIC attaches to ten64's
existing VLAN-trunk bridge. This keeps the backhaul-gate unchanged: its uplink member is
`eth0.5` on `br-mgmt`, and `wired_reaches_gw` confirms ten64 via the FDB on that port.
(Per-VLAN access NICs were considered and rejected: more guest config, breaks the gale
mirror, and complicates the shared bootstrap.)

## 9. Validation & testing

- **Unit/structure:** `verify-tenvm-image.py` (sibling of `verify-gale-image.py`):
  unsquashfs/ext4-extract the rootfs from the built image and assert (a) required
  packages present (`openwisp-config`, `openwisp-monitoring`, batman, `wpad-mesh-mbedtls`,
  `kmod-ath11k-pci`, `ath11k-firmware-qcn9074`, `kmod-ath10k`, `ath10k-firmware-qca9377`),
  (b) overlay files present + executable (bootstrap, gate, hotplug hook), (c) the
  bootstrap contains the backhaul cron line, (d) the openwisp controller stanza present.
- **QEMU smoke-boot:** boot `combined-efi.img` headless on `qemu-system-aarch64 -M virt`
  with UEFI firmware and a user-mode NIC; assert via serial console that the kernel boots
  to userspace, `99-tenvm-bootstrap` ran (bat0 + `eth0.5`/`br-mgmt` devices exist), and
  `openwisp-config` is running/attempting registration. Successful controller
  registration is **not** required (controller may be unreachable from the test host);
  the bar is "reaches and completes first-boot." Runs on ten64 (KVM, fast) or locally
  (TCG, slow); the script auto-selects KVM when available.

## 10. Open questions / risks

- **OQ1 (radio role mapping, live):** §7.3's driver-based mapping is fully validated only
  once real radios are passed through (deferred). Image-first it is exercised as a no-op.
  Mitigation: keep the mapping a small, separately-testable shell function.
- **OQ2 (QCN9074 6 GHz):** ten64's QCN6024 currently advertises only 5 GHz (Band 2). If a
  later board-2.bin/regdb enables 6 GHz, the 5 GHz role still holds; no image change needed.
- **OQ3 (QEMU UEFI firmware path):** AAVMF/edk2 firmware location differs across hosts
  (`/usr/share/AAVMF/AAVMF_CODE.fd`, `/usr/share/qemu-efi-aarch64/QEMU_EFI.fd`). The
  smoke-boot script probes known paths and skips with a clear message if none found.
- **OQ4 (ext4 vs squashfs overlay):** ext4-combined chosen for a simple writable VM disk;
  if image size/whole-disk-reset semantics later matter, squashfs+overlay is a drop-in
  `.config` change.

## 11. File inventory (delta)

```
tenvm-image/
  build-tenvm-image.sh                 # new (sibling of build-gale-image.sh)
  tenvm.config                         # new (target/rootfs + packages + radio stacks)
  files/
    etc/config/openwisp                # new (controller stanza, per-image like gale/om2p)
    etc/config/usteer                  # new (steering config, mirrors gale)
    etc/config/wireless                # new (minimal mesh0 template)
    etc/uci-defaults/99-tenvm-bootstrap# new (eth0 trunk + bat0 + cron + radio-id)
  verify-tenvm-image.py                # new (rootfs asserts)
  qemu-smoke-boot.sh                   # new (headless boot test, KVM/TCG auto)
  README.md                            # new (build + smoke-boot instructions)
docs/
  ten64-vm-image-design.md             # this file
  ten64-vm-image-plan.md               # implementation plan (next)
# REUSED from fleet-files/ (no change): usr/sbin/gwifi-backhaul-gate,
#   etc/hotplug.d/net/30-gwifi-backhaul
```
