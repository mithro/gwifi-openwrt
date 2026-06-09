# tenvm-image — OpenWISP-managed aarch64 OpenWrt VM image for ten64

This directory produces an OpenWrt VM image for the `armsr/armv8` target that runs
as a KVM guest on the **ten64** (LS1088A arm64) host and will own ten64's two PCIe
Wi-Fi radios (QCN6024/QCN9074 ath11k + QCA9377 ath10k) once they are passed through.

It is a sibling of `gale-image` and `om2p-image`: same OpenWISP + batman-adv +
802.11s mesh feature set, the shared `fleet-files/` overlay (backhaul-gate + hotplug
hook), and the per-image overlay (openwisp/usteer/wireless). The WiFi-6 radio carries
the 802.11s + batman-adv mesh in addition to client APs — this image is a **full mesh
sibling of gale**.

## Scope

This directory covers the **image build only**. The host-side VFIO passthrough of the
two PCIe radios, the libvirt domain XML, the live cutover from ten64's native hostapd,
and the OpenWISP device template are deferred follow-on work and are not part of this
directory. The image builds, boots in a VM, and provisions against OpenWISP **without
any radio attached** — radios are identified at first boot by driver via
`/usr/sbin/gwifi-radio-setup`, which is a no-op until passthrough exists.

## Prerequisites

- OpenWrt build tree at `/home/tim/local/gwifi/openwrt` (v25.12.4) with feeds updated
  and installed:
  ```sh
  ./scripts/feeds update -a && ./scripts/feeds install -a
  ```
- `fleet-secrets.conf` — the fleet-wide secrets file. It lives **outside this repo**
  at `/home/tim/local/gwifi/fleet-secrets.conf`. Build and verify take it via the
  `FLEET_SECRETS=` environment variable.
- For the smoke-boot: `qemu-system-aarch64` (Debian: `qemu-system-arm`) and an
  aarch64 UEFI firmware (Debian: `qemu-efi-aarch64`). On ten64 (aarch64) it runs
  under KVM; on an x86 dev host it runs under TCG (slower).

## Build

Run from the repo root:

```sh
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf ./tenvm-image/build-tenvm-image.sh
```

The script renders secrets into a temporary `files/` tree in the build directory,
merges the shared `fleet-files/` overlay, seeds `.config` for the `armsr/armv8`
target, runs `make defconfig`, then builds with `make -j6`.

`RENDER_ONLY=1` renders the overlay (with secrets substituted) without running the
build — useful to inspect the rendered files. `JOBS=N` controls parallelism (default 6).

## Outputs

Built images land in:

    /home/tim/local/gwifi/openwrt/bin/targets/armsr/armv8/

The relevant artifacts are:

- `*-combined-efi.img` — bootable disk image (UEFI + GRUB + rootfs)
- `*-rootfs.tar.gz` — rootfs tarball used by the verifier
- `*.manifest` — installed package list

**Important:** built images contain baked-in secrets and must NOT be published.

## Verify

After a successful build, run:

```sh
FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf uv run python tenvm-image/verify-tenvm-image.py
```

This checks packages (including ath11k/ath10k drivers and firmware), the rendered
overlay with no leftover placeholders, and that a `combined-efi` artifact exists.

## Smoke-boot

```sh
uv run python tenvm-image/qemu-smoke-boot.py
```

Boots the `combined-efi.img` headlessly under `qemu-system-aarch64 -M virt`. PASS
when the serial console emits the `TENVM-BOOTSTRAP-COMPLETE` marker from
`99-tenvm-bootstrap`. SKIPs cleanly if `qemu-system-aarch64` or an aarch64 UEFI
firmware is not installed. `SMOKE_TIMEOUT=<seconds>` overrides the 360 s default.

## Secret handling

Committed overlay files contain only placeholders (`__OPENWISP_SHARED_SECRET__`,
`__MESH_SAE_KEY__`, `__MESH_ID__`, `__OPENWISP_URL__`), substituted at build time.
`fleet-secrets.conf` is never committed to this repository. Built `.img` artifacts
are never published.
