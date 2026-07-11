<!-- SPDX-License-Identifier: Apache-2.0 -->
# gale-installer — netboot eMMC auto-installer image

The RAM-only OpenWrt image that armed pucks TFTP-boot from wisp. It
fetches the current manifest from `http://<wisp>:8080/manifest`, compares
the installed `/etc/gwifi-image-id` marker (idempotent — a stale-armed
puck reports `already-current` and reboots), sha256-verifies and `dd`s the
factory image to eMMC, verifies the marker on the new rootfs, phones home
(auto-disarm), and reboots. Every failure path reports if it can and
**stays up** (serial shell + retry on next power cycle; no reboot loops).

Design: `../docs/wisp-netboot-install-design.md` §5.5. Ops:
`../docs/wisp-netboot-runbook.md`.

```sh
./build-installer.sh        # → out/gale-installer-<buildid>.itb (+ symlink)
# stage it:
uv run ../tools/gwifi-netboot/deploy.py --artifacts <dir with tftp/ + images/>
```

Notes:
- Minimal config (stock device packages, no mesh/openwisp, **no secrets**);
  the raw-FIT initramfs comes from the tree's netboot patch
  (`../openwrt-patches/`).
- The server address comes from the `tftpserverip=` kernel cmdline arg the
  depthcharge netboot payload appends — nothing is baked in.
- The manifest is guaranteed flat by `gwifi_netboot/publish.py` (busybox
  `sed` parses it; no jq in the image).
