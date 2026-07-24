# Fleet image base + tenwrt VM parity — Design Spec

> Status: approved (design) 2026-07-24, pending spec review. Supersedes
> `docs/ten64-vm-image-design.md` for the **content** of the ten64 VM image (that
> spec's mesh-era feature set is preserved in git history and via the detached
> `gwifi-mesh-aps` template, matching the fleet-wide 2026-07-22 simple-profile
> restructure). Host-side VFIO/libvirt work remains out of scope, as before.

## 1. Summary

Two deliverables, one branch (`tenwrt-vm-parity`):

1. **A shared image base** — new `fleet-image/` directory holding the common
   OpenWrt config fragment, the common overlay (openwisp agent config + shared
   first-boot bootstrap functions), common build-script steps, and common
   verifier checks. `gale-image/` (pucks), `tenwrt-image/` (ten64 KVM guest)
   and `om2p-image/` (OpenMesh OM2P) become thin specializations of it.
2. **tenwrt VM image parity** with the deployed simple-profile fleet:
   - fix the missing MediaTek MT7915 PCIe firmware (and the other silently
     missing mt76 firmware packages),
   - add VM guest tools (`acpid` + `qemu-ga`) so the hypervisor can signal a
     graceful shutdown,
   - replace the mesh-era baked config with the pucks' minimal
     wisp-connectivity bootstrap; everything else is delivered by OpenWISP
     (wisp.welland.mithis.com) after registration,
   - the small wisp-side updates needed for wisp to manage the VM.

## 2. Context — verified current state (2026-07-24)

### 2.1 Branch topology

`tenwrt-image/` existed only on `openwisp-controller` (mesh-era design);
the deployed puck reality lives on `wisp-netboot-install` (+ tools on
`puck-sheet-live-sync`). Branch `tenwrt-vm-parity` was created off `main` and
both lines merged (commit `980703c`); the four conflicts were resolved to the
deployed `wisp-netboot-install` side. Baseline after merge: 54 gwifi-netboot
pytest + `tests/tenwrt/test-radio-setup.sh` + backhaul decide tests all pass.

### 2.2 Deployed puck reality (the parity target)

- The gale image bakes **only wisp-connectivity**
  (`gale-image/files/etc/uci-defaults/99-gale-bootstrap`): vlan-aware `br0`
  (STP off) over the uplink trunk jack, mgmt **VLAN 4 untagged/pvid**, DHCP
  from wisp (10.1.4.2), openwisp agent config
  (`management_interface 'br0.4'`, `mac_interface 'wan'`), dnsmasq DHCP off +
  `mithis.com` rebind whitelist, mgmt in the trusted firewall zone.
- OpenWISP delivers the rest via templates (verified live on wisp):
  - `SSH Keys` (default: auto-attaches on registration),
  - `gwifi-base` (files): lldpd + usteer configs, crontab, and the
    `post-reload-hook` that **creates the roam=20 / iot=90 / guest=99
    bridge-vlans + interfaces**, keyed on trunk detection
    (`eth-black`, falling back to `lan`), plus remote syslog to 10.1.4.2,
  - `gwifi-aps` (radios + six APs on VLANs 20/90/99).
- Per-device config objects on wisp are **empty** — templates carry everything.

### 2.3 tenwrt image as merged (mesh-era, to be replaced)

Baked batman-adv + 802.11s mesh seed + backhaul-gate cron, VLAN map
`mgmt=5 int=10 roam=20 iot=90 guest=99` on the virtio trunk `eth0`, baked
wireless/usteer, mesh secrets. Full in-tree PCIe Wi-Fi driver matrix — but the
config comment "firmware bundled with each kmod" is **wrong** for mt76:
`kmod-mt7915e` ships only the driver; the blobs
(`mt7915_wa/wm/rom_patch.bin`) are in the separate `kmod-mt7915-firmware`
package (verified in `package/kernel/mt76/Makefile`, OpenWrt v25.12.4), with
`kmod-mt7916-firmware` for the MT7916 variant sharing the same driver. The
same split applies to mt7615/mt7921/mt7922/mt7925/mt7996. No guest tools.

### 2.4 Host side (read-only facts; ten64 is NOT touched by this work)

ten64's `tenwrt` libvirt domain: single virtio trunk NIC on `br-raw` (floods
all tagged frames), one PCI hostdev — the MT7915A/D `14c3:7915` (DBDC 2.4+5
GHz), `<acpi/>` present, no virtio-serial channel. The feed `acpid` package's
default config maps the ACPI power button to `/sbin/poweroff`, so
`virsh shutdown` works with the existing XML once `acpid` is in the image;
`qemu-ga` additionally needs a `<channel>` (staged locally only, §4.7).

## 3. Decisions (locked with Tim, 2026-07-24)

- **D1** Base the work on a merge of both lines in a new branch + worktree
  (`.worktrees/tenwrt-vm-parity`); never the base worktree, never ten64.
- **D2** VM mgmt = **VLAN 4 tagged** on the virtio trunk (`eth0:t` in br0) —
  same subnet/registry/monitoring parity as the pucks.
- **D3** Guest tools = `acpid` + `qemu-ga`; the domain-XML channel edit is
  staged in `ten64-host/` locally and never deployed by this work.
- **D4** **Simple profile, no mesh baked** — exact puck parity. Mesh returns
  fleet-wide via OpenWISP when/if the fleet flips back.
- **D5** Shared `fleet-image/` base specialized into gale and tenwrt (this
  spec's core; requested by Tim).
- **D6** (revised 2026-07-24) `om2p-image` **also builds from the base**:
  it adopts `build-lib.sh` + the `base.config` layering, but its overlay
  *content* stays mesh-era as-is (own bootstrap + `fleet-files/`) and is
  protected by the same render byte-diff gate as gale. Converting om2p to the
  simple profile (and onto `bootstrap.sh`) is a follow-up — its 7168k slot is
  the constraint, not the build machinery.
- **D7** tenwrt builds use a **separate armsr OpenWrt build tree** (fresh
  v25.12.4 checkout, `OWRT=` override) so concurrent gale builds in the shared
  tree are never disturbed.

## 4. Design

### 4.1 Layout

```
fleet-image/
  base.config       # shared managed feature set: openwisp-config,
                    # openwisp-monitoring, kmod-batman-adv + batctl-default
                    # (mesh-capable, unconfigured), wpad-mesh-mbedtls, usteer,
                    # luci, ip-full, tcpdump-mini, ethtool
  files/            # shared overlay, merged FIRST at build time:
    etc/config/openwisp        # URL/secret placeholders, interval, verify_ssl,
                               # management_interface 'br0.4'
    lib/gwifi/bootstrap.sh     # shared first-boot functions (§4.2)
  build-lib.sh      # sourced by image build scripts: secrets render (esc/sed),
                    # overlay merge (fleet-image/files/ then <image>/files/),
                    # config concat + defconfig, forced rootfs rebuild,
                    # out/ artifacts + image-id stamp & sidecar
  verify_lib.py     # shared verifier checks: no unrendered placeholders,
                    # package manifest asserts, overlay-presence asserts

gale-image/         # specialization: ipq40xx/google_wifi target fragment,
                    # gale extras (cros_ec, netconsole, topology, lldpd),
                    # 99-gale-bootstrap → thin driver over bootstrap.sh
tenwrt-image/       # specialization: armsr/armv8 target fragment, PCIe Wi-Fi
                    # driver+firmware matrix, acpid + qemu-ga,
                    # 99-tenwrt-bootstrap → thin driver over bootstrap.sh,
                    # slimmed gwifi-radio-setup (§4.5)
om2p-image/         # specialization: ath79 target fragment + 7168k-fit
                    # disables; overlay content unchanged for now (mesh-era
                    # bootstrap + fleet-files; D6)
```

The pre-existing `fleet-files/` overlay (mesh-era backhaul gate + hotplug
hook) is **not** folded into `fleet-image/files/`: the tenwrt build **stops
consuming it** (backhaul gating is mesh-era; §4.5 drops the wiring).
`build-lib.sh` therefore takes the overlay list per image rather than
hardcoding it: gale and tenwrt merge `fleet-image/files/` + their own
`files/`; om2p merges only its own `files/` + `fleet-files/` (its current
order), skipping the base overlay so its rendered tree stays byte-identical
through the refactor (D6, §4.8.1). `fleet-files/` stays alive solely for
om2p until its simple-profile conversion.

### 4.2 Shared bootstrap functions, thin per-image drivers

`fleet-image/files/lib/gwifi/bootstrap.sh` provides parameterized functions
for the wisp-connectivity shape both images share: vlan-aware `br0` (STP off),
mgmt bridge-vlan + `mgmt` interface (`br0.4`, DHCP), delete default
lan/wan/wan6, dnsmasq DHCP off + `mithis.com` rebind whitelist, mgmt into the
trusted firewall zone. Idempotent fixed UCI section names, and the
retry-next-boot pattern (exit non-zero when preconditions are missing) carries
over from 99-gale-bootstrap.

Per-image drivers supply only what differs:

| parameter | gale (pucks) | tenwrt (VM) |
|---|---|---|
| bridge | edit board-generated `br-lan` → `br0` | create `br0` from scratch (a QEMU guest matches no armsr board case, so no board network exists) |
| trunk port | `eth-black` (case marking; netdev per DTS) | `eth0` (virtio) |
| mgmt VLAN 4 | untagged + pvid (`:u*`) | tagged (`:t`) |
| bridge MAC | pinned to label MAC (eth-blue section) | inherit `eth0` (virtio MAC fixed by domain XML — stable) |
| `mac_interface` | `wan` | `eth0` |
| hostname | puck naming (installer-set) | `tenwrt` (set in bootstrap) |

The shared `etc/config/openwisp` ships with `mac_interface` unset; each
image's bootstrap driver applies its value with a `uci set` (no per-image
full-file override of the shared overlay). Similarly, `build-lib.sh` takes a
**per-image required-secrets set**: gale keeps
`MESH_SAE_KEY`/`MESH_ID`/`TOPOLOGY_RECEIVE_URL` (its extras still render
them); tenwrt requires only `OPENWISP_URL` + `OPENWISP_SHARED_SECRET`.

### 4.3 Config layering

`build-lib.sh` seeds `.config` as: target lines (per image) + `base.config` +
`<image>.config`, then `make defconfig` — the same seeding the scripts do
today, three-layered. Later fragments override earlier ones (kconfig takes
the last assignment), which is what lets `om2p.config` shrink to its target
fragment + the 7168k-fit disables: base packages it cannot afford (e.g.
`luci`) are turned off with explicit `# CONFIG_PACKAGE_x is not set` lines,
self-documenting the size trade.

### 4.4 tenwrt package changes

- **Firmware fix**: add `kmod-mt7915-firmware` + `kmod-mt7916-firmware` (the
  MT7915 fix), and the other split-firmware packages for kmods already listed:
  `kmod-mt7615-firmware`, `kmod-mt7921-firmware`, `kmod-mt7922-firmware`,
  `kmod-mt7925-firmware`, `kmod-mt7996-firmware` (+ variants as the Makefile
  requires). Correct the wrong "firmware bundled with each kmod" comment. The
  rtw88/rtw89/ath auto-pull claims are re-verified against the built manifest
  at implementation time, not trusted from comments.
- **Guest tools**: `acpid` (+ default power-button→poweroff config) and
  `qemu-ga` (+ whatever virtio-console/serial kmod armsr needs, verified at
  plan time — armsr builds many virtio drivers in-kernel).
- Mesh-era-only bits leave the tenwrt fragment where they were tenwrt-specific;
  the shared mesh-capable packages stay in `base.config` for gale parity
  (pucks ship them today with mesh unconfigured).

### 4.5 tenwrt overlay — simple parity

Dropped: baked wireless/mesh0 seed, baked usteer config, batman/backhaul
bootstrap wiring, mesh secrets (`MESH_ID`/`MESH_SAE_KEY` no longer render into
this image). Kept: first-boot console completion marker;
`gwifi-radio-setup` **slimmed to band normalization only** — ensure the MT7915
DBDC phys land as `radio0` = 2.4 GHz / `radio1` = 5 GHz (with detected phy
`path` preserved) so the unmodified `gwifi-aps` template binds correctly, and
remain a no-op with no radio attached. The existing
`tests/tenwrt/test-radio-setup.sh` is updated alongside.

### 4.6 wisp-side changes

- `gwifi-base` `post-reload-hook`: extend trunk detection
  `eth-black` → `lan` → **`eth0`** (final fallback; pucks match earlier names —
  on gale `eth0` is the DSA conduit, so ordering matters). Delivered via
  `openwisp/build-templates.py`, which becomes the in-repo source of truth for
  the hook it pushes.
- `openwisp/build-templates.py`: attach `gwifi-aps` + `gwifi-base` to the
  `tenwrt` device alongside the pucks. Registration itself is automatic via
  the shared secret; `SSH Keys` auto-attaches (default template).
  **Sequencing**: the attach loop skips devices that don't exist yet, so the
  `tenwrt` attach only takes effect on a `build-templates.py` run **after**
  the VM's first successful registration (documented as a deploy-runbook
  step, not automated here).
- lldpd stays puck-only for v1 (open item §5).

### 4.7 Host-side, staged only

`ten64-host/tenwrt.xml` (local, outside this repo) gains the qemu-ga
virtio-serial `<channel org.qemu.guest_agent.0>` edit — staged for Tim's next
manual `virsh define`; nothing on ten64 is read, written, or restarted by this
work.

### 4.8 Verification

1. **Gale + om2p no-regression gates (must pass before the branch is
   finished)**: for each, render the overlay with `RENDER_ONLY=1` from the
   pre-refactor tree and from the refactored base+specialization, and
   **byte-diff the rendered `files/` trees**; also diff the post-`defconfig`
   `.config`. Both must be identical (or every diff explained and approved).
   Notes: today's `build-gale-image.sh` has no `RENDER_ONLY` seam (tenwrt/om2p
   have one), so the gate starts with a trivial preliminary commit adding that
   seam to the pre-refactor script; om2p additionally keeps its existing
   verifier green, including the 7168k fit gate.
2. `verify-tenwrt-image.py` (on `verify_lib.py`): asserts
   `mediatek/mt7915_{wa,wm,rom_patch}.bin` present in the rootfs, `acpid` +
   `qemu-ga` installed, **no** mesh/wireless/usteer leftovers in the baked
   overlay (including that the mesh-era `fleet-files/` pieces —
   `gwifi-backhaul-gate` and the `30-gwifi-backhaul` hotplug hook — are
   absent), no unrendered placeholders, combined-efi artifact exists.
3. `qemu-smoke-boot.py`: keeps the first-boot completion marker assertion and
   gains a **graceful-shutdown assertion** — send QEMU `system_powerdown` and
   require a clean guest poweroff (exercises the exact `virsh shutdown` path
   with no ten64 involvement).
4. Existing suites stay green (gwifi-netboot pytest, radio-setup, backhaul).

## 5. Out of scope / open items

- Live deploy on ten64 (VFIO bind, `virsh start`, cutover) — Tim's manual gate.
- MT7915 DBDC phy order/count — only provable on real hardware;
  `gwifi-radio-setup` normalizes whatever appears.
- `gwifi-aps` stays 11n/11ac; 802.11ax uplift for MT7915 is a follow-up.
- VM LLDP visibility (announce on `eth0` without puck side-effects).
- Converting om2p to the simple profile + `bootstrap.sh` (and retiring
  `fleet-files/`) — its build machinery moves to the base now (D6), its
  content later.
- When to rebuild/republish the gale image from the refactored base — Tim's
  call; the published image is untouched until then.
