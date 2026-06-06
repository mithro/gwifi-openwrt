# OpenWrt tree patches for gale

Patches applied on top of a **stock OpenWrt source tree** to build
`gale`-specific firmware. Keeping them here as patches (rather than committing a
whole OpenWrt fork) lets them rebase cleanly onto new OpenWrt releases — the same
approach the [`depthcharge-ipq4019`](../depthcharge-ipq4019) submodule uses for
its coreboot/vboot build fixes.

> Note: the auto-provision image (see [`docs/`](../docs)) customises OpenWrt
> purely via a rootfs overlay + `.config` and needs **no** source patch. These
> patches are only for changes that must happen *inside* the OpenWrt build
> itself (e.g. the image recipe).

## Patches

### `0001-ipq40xx-chromium-google_wifi-emit-raw-netboot-fit.patch`

Makes the `ipq40xx/chromium` image recipe also emit the **unwrapped kernel FIT**
for the `google_wifi` (gale) device, so the initramfs image can be
**TFTP-netbooted** by depthcharge.

**Why:** depthcharge's netboot path (`netboot.c` → `boot()` → `fit_load()`) feeds
the downloaded file in directly and requires a **raw FIT** (FDT magic
`0xd00dfeed`). The stock build only emits the cros-vboot-wrapped
`…-fit-zImage.itb.vboot`, which leads with the `CHROMEOS` vboot keyblock and is
rejected (`Bad FIT header magic value 0x4348524f`). The eMMC boot path unwraps
the keyblock itself; the TFTP path does not. See the
[`depthcharge-ipq4019`](../depthcharge-ipq4019) submodule for the netboot side.

The patch adds a `Build/emit-raw-fit` step to the **initramfs** kernel pipeline
only (the squashfs / `factory.bin` kernel path is untouched). It copies `$@` out
as `…-initramfs-fit-zImage.itb` while `$@` still holds the raw FIT — i.e. just
before `cros-vboot` overwrites it in place.

**Tested against:** OpenWrt v25.12.4 (`r32933-4ccb782af7`).

**Result:** after `make`, alongside the usual outputs in
`bin/targets/ipq40xx/chromium/` you also get
`openwrt-…-google_wifi-initramfs-fit-zImage.itb` (~7.7 MB, magic `d00dfeed`).
`factory.bin`, `sysupgrade.bin`, and the `.itb.vboot` are byte-for-byte
unchanged (verified).

## Applying

From the OpenWrt build tree root (`openwrt/`):

```sh
git -C openwrt apply gwifi-openwrt/openwrt-patches/0001-ipq40xx-chromium-google_wifi-emit-raw-netboot-fit.patch
# or, without git:
cd openwrt && patch -p1 < .../openwrt-patches/0001-ipq40xx-chromium-google_wifi-emit-raw-netboot-fit.patch
```

Then build normally — the raw FIT is produced by the initramfs image step.

## Netboot usage

The emitted `.itb` is already a raw FIT; serve it directly over TFTP, e.g.:

```sh
dnsmasq --enable-tftp --tftp-root=/srv/tftp \
        --dhcp-boot=openwrt-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb
```

Verify it's a valid FIT before serving:

```sh
xxd -l4 openwrt-ipq40xx-chromium-google_wifi-initramfs-fit-zImage.itb   # -> d00dfeed
```
