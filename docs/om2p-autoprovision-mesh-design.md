# Open-Mesh OM2P auto-provisioning mesh-AP fleet image — Design Spec

- **Date:** 2026-06-07
- **Status:** Draft (pending spec-reviewer + user approval)
- **Target devices:** Open-Mesh **OM2P** family — OpenWrt **25.12.x**, target `ath79/generic`, devices `openmesh_om2p-{lc,v1,v2,v4}`
- **Controller:** OpenWISP (pull mode) at `https://wisp.welland.mithis.com`
- **Build env:** `/home/tim/local/gwifi/openwrt` (OpenWrt v25.12.x; currently builds `ipq40xx` — this adds the `ath79` target alongside it)
- **Companion spec:** `docs/gale-autoprovision-mesh-design.md` (this is its OM2P sibling; the two images join the **same** fleet mesh)

## 1. Summary

Build a small set of **generic** OpenWrt images (one per OM2P hardware revision) for the welland Open-Mesh/CloudTrax nodes that **auto-provision** from the existing OpenWISP controller and **survive loss of their wired uplink** by falling back to the fleet Wi-Fi mesh — the OM2P equivalent of the verified `gale-image/`. As with gale, the image bakes in only bootstrap connectivity, the OpenWISP agent, baked mesh credentials, and the capability set (VLANs, L2 client bridging, mesh). Per-device runtime config is **pulled from OpenWISP** after the node registers. Scope also includes a **single-radio OpenWISP config template** so the OM2P nodes onboard cleanly into the fleet that the dual-radio pucks already use.

The OM2P hardware is radically smaller than gale (single 2.4 GHz radio, **~7 MB** total firmware, ≥32 MB RAM) and has **two** Ethernet ports whose WAN/LAN→GMAC mapping differs by revision, so the design departs from gale in three specific places: a single shared radio; a **per-model uplink-port trunk** with the second port as a wired-client access port; and a **bootstrap-generated** wireless config (no static per-SoC `path`).

## 2. Goals

- **G1** One generic image **per OM2P revision** (`lc/v1/v2/v4`); per-device identity/config comes from OpenWISP (matched by MAC). The four images differ only by hardware profile, not by baked policy.
- **G2** On first boot, with no prior config, an OM2P reaches `https://wisp.welland.mithis.com` and pulls its config.
- **G3** Uplink prefers the wired uplink-port 802.1q trunk (the WAN/PoE jack — see C4); falls back to the **2.4 GHz** fleet mesh automatically, with no switchover daemon (batman-adv BLA), exactly as gale does.
- **G4** Full-service fallback: while on the mesh, management + all carried client VLANs keep working via a wired-uplink node acting as the batman-adv gateway.
- **G5** The fleet's OM2P nodes (4× OM2P-LC, 2× OM2P) onboard and are managed centrally via a **single-radio OpenWISP template** consistent with the dual-radio `gwifi-puck` template.

## 3. Non-goals

- Per-device config *content* (SSIDs, passphrases, steering tuning) — owned by OpenWISP templates.
- L3 routing/NAT on the node — OM2P are **L2 APs**; ten64 routes and serves DHCP.
- Changes to the OpenWISP server install or ten64 (assumed in place and correct).
- The OM2P-HS / OM5P / A40/A60 variants — **not in this fleet**; only the four mapped OM2P profiles are built.
- Bench-flashing real hardware (ap51-flash) and the live `sysupgrade` upgrade path — deployment work, tracked as follow-ups (see §13, §16).

## 4. Context & assumptions (from prior project work)

- OpenWISP is deployed/verified at `wisp.welland.mithis.com` (10.1.5.2, VLAN 5), trusted Let's Encrypt cert, org `default` with registration + shared secret.
- **The OM2P controller side already exists**: `openwisp/provision-openmesh.py` pre-creates the **6** Open-Mesh nodes as devices in org `default` (4× OM2P-LC + 2× OM2P, keyed by label MAC, `config=none`), reading the node list from the **gdoc2netcfg** inventory on ten64 (`/opt/gdoc2netcfg/.cache/network.csv`). `openwisp/playbook.yml` registers the OM2P image-type keys in `OPENWISP_CUSTOM_OPENWRT_IMAGES`, and `openwisp/validate-firmware-images.py` asserts the `model → image-type` map. What is missing is the **firmware build** and the **OM2P template** — this spec.
- welland VLANs: **mgmt/net = 5** (10.1.5.0/24, gw .1), **int = 10**, **roam = 20**, **iot = 90**, **guest = 99**. ten64 is router + DHCP for all.
- **Mesh interop is already defined**: the live `gwifi-puck` template (`openwisp/build-templates.py`) runs 802.11s `mesh_id="gwifi-mesh"` on **both** radios — `mp0` (2.4 GHz) and `mp1` (5 GHz) — over batman `bat0`. A single-radio OM2P joins through the **2.4 GHz leg**, so it must reuse the same `mesh_id` and the fleet `mesh_key`.

## 5. Hardware constraints (the crux — verified against the OpenWrt tree)

| Profile | SoC | Radio | Wi-Fi `path` | Ports | **Uplink (WAN/PoE) port** |
|---|---|---|---|---|---|
| `openmesh_om2p-lc` | ar9330 | 2.4 GHz (on-SoC wmac) | `platform/ahb/18100000.wmac` | eth0 + eth1 | **`eth1`** |
| `openmesh_om2p-v1` | ar7240 | 2.4 GHz (**PCI** radio) | PCIe path (no on-SoC wmac) | eth0 + eth1 | **`eth0`** |
| `openmesh_om2p-v2` | ar9330 | 2.4 GHz (on-SoC wmac) | `platform/ahb/18100000.wmac` | eth0 + eth1 | **`eth1`** |
| `openmesh_om2p-v4` | qca9533 | 2.4 GHz (on-SoC wmac) | (qca9533 wmac addr) | eth0 + eth1 | **`eth0`** |

> **Two real Ethernet ports per device** (verified in the DTS: `&eth0` + `&eth1` both `status="okay"` with their own ART MACs; both a `wan_blue` and a `lan_blue` LED). The **WAN/PoE uplink maps to a different GMAC by revision** — `eth1` on lc/v2 (`label-mac-device=&eth1`; default `02_network` `lan_wan "eth0" "eth1"`), `eth0` on v1/v4 (`label-mac-device=&eth0`; `lan_wan "eth1" "eth0"`). The design selects the uplink port **per model** (C4): trunk on the uplink port, the other port as a wired-client access port (§8.2).

- **C1 — Flash budget:** `Device/openmesh_common_256k` sets `IMAGE_SIZE := 7168k`. Kernel + rootfs must fit in ~7 MB; OpenWrt **fails the build loudly** on overflow.
- **C2 — Single radio:** one 2.4 GHz PHY. The client AP(s) and the 802.11s mesh **share** it (no dedicated backhaul band, unlike gale's 5 GHz).
- **C3 — RAM:** ≥32 MB (om2p-v1/ar7240 = 32 MB; ar9330/qca9533 typically 64 MB). 32 MB is the floor that `openwisp-monitoring`/collectd must tolerate.
- **C4 — Uplink vs client port (per model):** both `eth0` and `eth1` are real external RJ45s. The WAN/PoE **uplink** is `eth1` on lc/v2 and `eth0` on v1/v4 (from `02_network`'s per-model `lan_wan` assignment, corroborated by `label-mac-device`). The bootstrap selects ports from the board name (`/tmp/sysinfo/board_name`): `openmesh,om2p-lc`/`-v2` → uplink `eth1`, client `eth0`; `openmesh,om2p-v1`/`-v4` → uplink `eth0`, client `eth1`. The **uplink** carries the 802.1q trunk; the **client** port is a wired access port (§8.2). Binding is to the raw eth netdev, never a DSA `wan`/`lan` role (those roles are inconsistent across the family).
- **C5 — Per-SoC `path`:** the radio `path` differs fundamentally across models (ar9330 AHB wmac vs ar7240 **PCI** radio vs qca9533) → a single static `/etc/config/wireless` with a hard-coded `path` cannot serve all four in one build. Wireless is configured **by radio name** in the bootstrap instead (§8.4).
- **C6 — Image format:** the recipe emits only `IMAGE/sysupgrade.bin` wrapped by `openmesh-image` (CloudTrax/ap51 format) + `append-metadata`. There is **no separate factory image**; first install is via **ap51-flash** using this artifact (§13).

## 6. Requirements (decided with user)

- **R1** Networking = **gale parity**: 802.1q trunk (VLANs 5/10/20/90/99) on the **uplink** port + mesh failover; full-service fallback (mgmt + client VLANs over the mesh). The **second (client) port is a wired access port on the roam VLAN (20)** — mirroring the gale puck template, which bridges the puck `lan` into `br-roam`.
- **R2** Failover mechanism = passive L2 mesh extension with batman-adv **Bridge Loop Avoidance** (no failover daemon).
- **R3** Provisioning = OpenWISP `openwisp-config` **pull mode** (outbound HTTPS); **`openwisp-monitoring` included** (telemetry parity with the pucks), accepting the C1/C3 fit risk to be validated empirically (§10).
- **R4** Scope = **firmware images + OpenWISP template**: build the 4 OM2P sysupgrade artifacts **and** add a single-radio OM2P config template attached to the 6 pre-provisioned devices.
- **R5** Secrets: a **single shared `fleet-secrets.conf`** sourced by **both** the gale and OM2P build scripts (the mesh key/shared secret/mesh-id/controller-URL are all fleet-wide; one file removes the drift footgun). Committed files use placeholders; built `.bin`s are sensitive (already gitignored).
- **R6** Code organization = **parallel sibling** `om2p-image/` mirroring `gale-image/` (not a shared multi-target builder — YAGNI for two device families; keeps the verified gale pipeline intact).

## 7. Architecture

- **Radio:** single 2.4 GHz `radio0` = client AP(s) **+** 802.11s mesh backhaul (shared, per C2).
- **Mesh:** 802.11s (baked `mesh_id=gwifi-mesh` + WPA3-SAE fleet key) → **batman-adv `bat0`** with **BLA** (loop-free bridging when multiple nodes bridge the mesh into the same wired VLANs) and `gw_mode=client` (DHCP gateway discovery over the mesh). Joins the pucks' 2.4 GHz mesh leg (`mp0`).
- **VLANs:** 802.1q tagged on the **uplink** port (`UP`, per-model: `eth1` on lc/v2, `eth0` on v1/v4) — 5, 10, 20, 90, 99. `CLIENT` = the other port.
- **One bridge per VLAN**, spanning the wired trunk + the mesh (+ the matching Wi-Fi AP at steady state):
  - `br-mgmt` = `UP.5` + `bat0.5` → node's own management IP (DHCP from ten64) + OpenWISP traffic
  - `br-int`  = `UP.10` + `bat0.10`
  - `br-roam` = `UP.20` + `bat0.20` + **`CLIENT`** (untagged wired-client port) (+ `ap-roam`)
  - `br-iot`  = `UP.90` + `bat0.90` (+ `ap-iot`)
  - `br-guest`= `UP.99` + `bat0.99`
- **Baked vs runtime:** the `files/` overlay creates each bridge with **only its `UP.V` + `bat0.V` members (plus `CLIENT` on `br-roam`) — no `ap-*`**. Client APs are the **post-OpenWISP** steady state: the pulled `wifi-iface` config carries `option network 'br-<name>'`, so netifd auto-attaches each AP to its bridge when the SSID comes up. No client SSIDs exist at first boot.
- **All five VLAN bridges are baked as pure L2 plumbing.** The OpenWISP template (§12) only attaches client APs to a **subset** (5/20/90) — exactly as on gale, where `br-int`(10)/`br-guest`(99) carry no AP. A VLAN without an AP is still bridged across wired+mesh for transit; it is not "missing".

## 8. Component design

### 8.1 Mesh backhaul
802.11s mesh point on `radio0` (2.4 GHz); `mesh_id` + SAE key baked so every node forms the same fleet mesh on first boot with no controller involvement. `wpad-mesh-mbedtls` provides the SAE-capable supplicant/AP (replaces `wpad-basic-mbedtls`). batman-adv runs over the 802.11s iface producing `bat0`; BLA on; `gw_mode=client`.

### 8.2 VLAN bridges (uplink trunk + wired-client port)
The bootstrap first picks `UP`/`CLIENT` from the board name (C4). For each VLAN *V*: a tagged sub-interface on the uplink (`UP.V`, an `8021q` device), a batman VLAN (`bat0.V`), and an L2 bridge `br-<name>` with members `{UP.V, bat0.V}`. `br-mgmt` (V=5) additionally runs a DHCP client for the node's management IP and never carries a client AP. The **`CLIENT` port is added untagged to `br-roam` (VLAN 20)** as a wired-access port — the same placement the gale puck template uses for its `lan`. **Deliberate divergence from gale:** gale bakes only `{wan.V, bat0.V}` and adds its wired-client port via the OpenWISP template *only*; the OM2P overlay bakes `CLIENT`∈`br-roam` **and** sets it in the template, so a wired client works even pre-onboard. The bridge *structure* is identical across profiles; only the concrete `UP`/`CLIENT` netdev names differ per model (resolved at runtime), so one overlay serves all four.

### 8.3 Provisioning agent
`/etc/config/openwisp`: `url=https://wisp.welland.mithis.com`, `shared_secret=__OPENWISP_SHARED_SECRET__` (placeholder), `verify_ssl=1`, `interval=120`, `management_interface=br-mgmt` — identical stanza to gale. `openwisp-monitoring` agent installed for telemetry (subject to §10 fit).

### 8.4 First-boot bootstrap (`/etc/uci-defaults/99-om2p-bootstrap`)
Establishes the pre-OpenWISP working state, **idempotent** (fixed UCI section names), runs once then is removed. Key steps (where the per-model and single-radio handling live):
1. **Port selection + network:** read `/tmp/sysinfo/board_name` → set `UP`/`CLIENT` (C4: lc/v2 → `eth1`/`eth0`; v1/v4 → `eth0`/`eth1`). Then batman `bat0` + `mesh_hardif`, the VLAN loop building `UP.V`/`bat0.V`/`br-<name>` (mgmt=DHCP, rest=none), and `CLIENT` untagged into `br-roam` (§8.2). Uses the raw eth netdevs, not DSA `wan`/`lan` roles. (`/tmp/sysinfo/board_name` is written by board-detect before uci-defaults run, so this selection is safe.)
2. **Wireless by name (C5):** rather than ship a static `/etc/config/wireless` with a per-SoC `path`, the bootstrap ensures the wireless config exists (running `wifi config` if board-detection has not yet generated it), then sets `radio0` params (`band=2g`, `channel`, `htmode=HT20`, `disabled=0`) and adds the `mesh0` `wifi-iface` referencing `device 'radio0'` with the baked mesh creds + `network 'mesh_hardif'`. The single-radio name `radio0` is stable across all four SoCs; the per-SoC `path` is supplied by detection. **Boot-ordering of uci-defaults vs wireless generation is a validation item** (§15.1).

### 8.5 Steering
`usteer` installed (small); runtime config delivered via the OpenWISP template, not hard-baked beyond safe defaults. First on the trim ladder if §10 overflows.

## 9. Data flows

- **9.1 First boot, wired present:** power → mesh forms on 2.4 GHz → `UP.5` DHCP → mgmt IP → `openwisp-config` registers (MAC match) → pulls config → applies SSIDs/VLANs.
- **9.2 First boot / runtime, wired absent:** power → mesh forms → `bat0.5` DHCP via a gateway node over the mesh → mgmt IP → `openwisp-config` reaches `wisp` over the mesh → same registration/pull. Client VLANs (incl. the wired-client port on `br-roam`) bridge over `bat0.X`.
- **9.3 Wired→mesh transition:** uplink (`UP`) carrier drops → `UP.X` leaves each bridge → only `bat0.X` remains → traffic reroutes over the mesh via BLA; the outbound poll continues. A device on the wired-client port keeps working via `br-roam`'s `bat0.20`. Reverse on link-up (wired re-preferred, 1 hop).

## 10. Package set & fit budget

```
# om2p.config
CONFIG_PACKAGE_openwisp-config=y
CONFIG_PACKAGE_openwisp-monitoring=y
CONFIG_PACKAGE_kmod-batman-adv=y
CONFIG_PACKAGE_batctl-default=y
# CONFIG_PACKAGE_wpad-basic-mbedtls is not set
CONFIG_PACKAGE_wpad-mesh-mbedtls=y
CONFIG_PACKAGE_usteer=y
```
- Deliberately **no** `luci`, `tcpdump-mini`, `ethtool`, `ip-full` — the budget can't take them. 802.1q is in-kernel; ath9k + `uboot-envtools` are device defaults.
- **Fit risk (C1/C3):** `openwisp-monitoring` pulls collectd + plugins; the rootfs must stay under 7168k and run in 32 MB. This is validated **empirically** by the build (it errors on overflow) and a bench RAM check.
- **Trim ladder if it overflows (in order):** (1) drop `usteer`; (2) `batctl-default` → `batctl-tiny`; (3) prune optional `collectd-mod-*` plugins to the monitoring essentials; (4) **last resort** — report that monitoring + gale-parity networking cannot co-reside in 7 MB and ask the user to choose (drop monitoring, or accept a reduced feature set). Measured fit (image size, free flash, idle RAM) is reported before the task is declared done; any trim taken is logged (no silent truncation).

## 11. Build mechanics & secrets

Reuse the `openwrt/` build env; **add** the `ath79/generic` target (first build compiles a second toolchain, mips_24kc, ~30–60 min one-time — the `ipq40xx` artifacts are unaffected). The custom image is defined by artifacts in `gwifi-openwrt`, kept separate from stock config:

```
om2p-image/
  build-om2p-image.sh        # source fleet-secrets.conf; render overlay; seed .config (4 profiles); make
  verify-om2p-image.py       # unsquashfs /etc (non-root safe); assert overlay + substituted secret VALUES (without ever printing them — redact, per the build-templates.py precedent) + packages; report image size vs 7168k
  om2p.config                # the fragment above
  README.md
  files/etc/
    config/openwisp          # controller stanza (placeholders)
    uci-defaults/99-om2p-bootstrap
fleet-secrets.conf.example   # repo root; placeholders + MESH_ID=gwifi-mesh, OPENWISP_URL=https://wisp.welland.mithis.com
```

- **`.config` seeding:** `CONFIG_TARGET_ath79=y` + `CONFIG_TARGET_ath79_generic=y` + the four `CONFIG_TARGET_DEVICE_ath79_generic_DEVICE_openmesh_om2p-{lc,v1,v2,v4}=y`, then `om2p.config`, then `make defconfig`. One `make` run emits all four images.
- **Outputs:** `bin/targets/ath79/generic/openwrt-…-openmesh_om2p-{lc,v1,v2,v4}-squashfs-sysupgrade.bin` — matching the keys already in `playbook.yml` (validated by `validate-firmware-images.py`).

**Secrets (R5) — one shared file:**
- New **`fleet-secrets.conf`** at the repo root (untracked, `0600`): `OPENWISP_SHARED_SECRET`, `MESH_SAE_KEY`, `MESH_ID`, `OPENWISP_URL`.
- **Both** `build-om2p-image.sh` and `build-gale-image.sh` source it (default path + `FLEET_SECRETS=` env override); each escapes sed replacement metacharacters as the gale script already does. `openwisp/build-templates.py` reads the same file (default `../fleet-secrets.conf` relative to `openwisp/`, with the same `FLEET_SECRETS=` override for test isolation).
- Committed **`fleet-secrets.conf.example`** documents the keys + the two stable defaults.
- **`.gitignore`:** add `fleet-secrets.conf` (keep the existing `gale-secrets.conf` line so any leftover stays ignored).
- **Migration:** one-time — copy the real values from the primary checkout's `gale-image/gale-secrets.conf` into `fleet-secrets.conf`, then retire the old file. `build-gale-image.sh`'s only change is its secrets-source path (same values, same rendering), so the gale build+verify is **re-run after the change** to confirm no regression.
- **Mesh key single-sourced (critical — see §12 & §15.7):** `MESH_SAE_KEY` in `fleet-secrets.conf` is the **one** fleet mesh key. `build-templates.py` is changed to **read** `mesh_key` from `fleet-secrets.conf` instead of generating a fresh one per run, so the baked images (gale + OM2P) and the OpenWISP templates (puck + OM2P) always agree. On migration, seed `fleet-secrets.conf`'s `MESH_SAE_KEY` with the **currently deployed** value (from `gale-secrets.conf`, which already equals the pucks' live key) so the existing fleet keeps working.

## 12. OpenWISP template (`gwifi-om2p`, single-radio)

Extend `openwisp/build-templates.py` to also build + attach a single-radio template, **reusing** the same secrets as the puck template: client passphrases (`ansells_key`, `iot_key`) still read from ten64 hostapd at runtime, and the **`mesh_key` now read from `fleet-secrets.conf`** (`MESH_SAE_KEY`) rather than generated — so the OM2P template, the puck template, and both baked images share one mesh key (§11, §15.7). No new secret handling is introduced. The template is the **2.4 GHz subset** of the `gwifi-puck` netjson (principled: the pucks already run `ansells` + `ansells-iot` + mesh on radio0; `ansells-guest` is 5 GHz-only, so OM2P simply does not carry guest):

- **radios:** `radio0` only (802.11n, ch 6, HT20, AU).
- **per-device port variables:** the template uses `{{ uplink_port }}` / `{{ client_port }}` so one template serves all revisions; each device's OpenWISP context sets them by model (lc/v2 → `eth1`/`eth0`; v1/v4 → `eth0`/`eth1`). (Verify netjsonconfig substitutes `{{ }}` inside `device`/`ifname` fields — §15.8; fallback = two template variants.)
- **interfaces:** `8021q` parents on **`{{ uplink_port }}`** (vids 5/20/90) + `bat0` (vids 5/20/90); bridges `br-mgmt` (dhcp), `br-roam` (members incl. **`{{ client_port }}`** = the wired-access port), `br-iot`; `wl-ans-2` (ansells/wpa3 → br-roam), `wl-iot` (ansells-iot/wpa2 → br-iot), `mp0` (802.11s/sae mesh_id gwifi-mesh → mesh0).
- **network:** `bat0` (batadv, BLA, DAT) + `mesh0` (batadv_hardif → bat0).
- **attach:** to the **6** pre-provisioned OM2P devices in org `default`, setting each device's `uplink_port`/`client_port` context by model. The 4 OM2P-LC are known now (`eth1`/`eth0`); the **2 bare “OpenMesh OM2P” devices report their exact revision only on first onboard**, so their port variables are set then (pre-onboard they run the baked config, which derives ports from the board name — correct regardless; §15.9). The template is **not** `default=True` (that flag belongs to `gwifi-puck`); it is attached explicitly to the OM2P devices, so pucks keep the dual-radio template and OM2P get the single-radio one.

> netjson must not reference `radio1`/`mp1`/`br-guest`/`wl-ans-5`/`wl-guest` (no second radio on OM2P).

## 13. First-flash / install path (note, not built here)

OM2P units currently run Open-Mesh/CloudTrax stock firmware. First install to OpenWrt is via **`ap51-flash`** (host tool) pushing the produced `openmesh-image`-wrapped artifact to the device's bootloader over a direct Ethernet link — there is no factory image (C6). A short install note (analogous to `docs/gale-openwrt-netboot-install.md`) will be added, but **on-hardware flashing is bench work**, out of scope for the build. After first flash, OpenWISP-driven upgrades use the default `sysupgrade`-over-SSH upgrader (still to be validated live — §16).

## 14. Error handling / resilience

| Failure | Behavior |
|---|---|
| uplink (`UP`) link down | bridges fall back to `bat0.X`; traffic rides mesh to a gateway node; the wired-client port stays served via `br-roam` |
| `wisp` unreachable | `openwisp-config` keeps the last-applied config running locally |
| Mesh partition | isolated node keeps running last config; reconverges on heal |
| L2 loop (multi-gateway) | batman-adv BLA suppresses it |
| Cold fleet (no wired anywhere) | mesh-only nodes can't reach `wisp` until ≥1 node (puck or OM2P) has wired uplink (expected) |
| Image overflow at build | build fails loudly → apply trim ladder (§10) |

## 15. Risks / to validate during implementation

1. **uci-defaults vs wireless-generation ordering** (§8.4): confirm `99-om2p-bootstrap` can create/modify `radio0` on first boot (run `wifi config` if `/etc/config/wireless` is absent at that point). Fallback: a tiny `/etc/init.d` one-shot ordered after wifi detection.
2. **Fit (C1) + RAM (C3):** `openwisp-monitoring` on 7 MB / 32 MB — empirical; trim ladder ready (§10). The 32 MB om2p-v1 is the worst case.
3. **Concurrent client AP + 802.11s on one 2.4 GHz ath9k radio** (multi-vif): generally supported on ath9k, but verify; the baked image only runs mesh at first boot, so this only bites once OpenWISP adds client SSIDs.
4. **batman-adv `gw_mode` + BLA over VLAN-tagged `bat0`** with multiple wired gateways (same caveat as gale Risk #3): `gw_mode` is on raw `bat0` while DHCP runs on tagged `bat0.V`. Fallback: plain DHCP over the bridged mesh (BLA still loop-safe).
5. **ath79 target addition** to a tree configured for ipq40xx: confirm `make defconfig` + build produces ath79 images without disturbing the ipq40xx outputs (separate `bin/targets/` trees, so expected clean).
6. **Cold-fleet bootstrap** requires ≥1 wired-uplink node to seed mesh-only nodes.
7. **Mesh-key regeneration footgun (must fix in the `build-templates.py` extension):** today `build-templates.py` calls `secrets.token_urlsafe(18)` every run and overwrites the puck template's `mesh_key` + `.wifi-secrets`. Re-running it as-is to add the OM2P template would **silently invalidate the deployed pucks and the baked gale image**. The extension must instead **read** `mesh_key` from `fleet-secrets.conf` (§11) and never regenerate. Verify a re-run is idempotent and leaves the puck template's key unchanged. The edited script should also **stop writing `.wifi-secrets`** (or write it only as a read-back of the fleet key) so that file can't drift back into being a second source of truth — `fleet-secrets.conf` is the sole source.
8. **netjsonconfig variable substitution in `device`/`ifname` fields (§12):** the OM2P template relies on `{{ uplink_port }}`/`{{ client_port }}` resolving **inside interface device names**, not just key values. Verify the OpenWISP/netjsonconfig context pass substitutes there. Fallback: ship **two** template variants (lc/v2 = `eth1`/`eth0`; v1/v4 = `eth0`/`eth1`) attached by model, instead of variables.
9. **Bare-OM2P port variables (§12):** the 2 unspecified “OpenMesh OM2P” devices need `uplink_port`/`client_port` set after they onboard and report v1/v2/v4. Until then they run the **baked** config, which derives ports from the board name (correct on the device), so there is no wrong-port window on-device — only the *managed* template apply waits for the vars.
10. **Pushed netjson must not drop baked transit bridges:** the template manages VLANs 5/20/90 only, but the overlay bakes all five. Confirm at bring-up that applying the OpenWISP config leaves `br-int`(10)/`br-guest`(99) intact for transit (same open behavior as gale — netjsonconfig renders the whole `/etc/config/network`, so verify these bridges survive or are re-declared).

## 16. Decided sub-choices

- Radio plan: **single 2.4 GHz `radio0`** shared (AP + mesh) — forced by hardware (C2).
- Ports: **two real RJ45s**; trunk on the **uplink** port (per-model from the board name: `eth1` on lc/v2, `eth0` on v1/v4), **second port = wired-client access on roam / VLAN 20** (matching the gale puck `lan`∈`br-roam`). Bind to raw eth netdevs, not DSA roles.
- Wireless config: **bootstrap-generated by radio name** (C5), not a static per-SoC file.
- Packages: minimal managed + monitoring (§10) with a defined trim ladder.
- Code org: **parallel sibling `om2p-image/`** (R6).
- Secrets: **single shared `fleet-secrets.conf`** (R5).
- Template: **`gwifi-om2p`** single-radio variant, 2.4 GHz SSID subset (ansells + ansells-iot, no guest), with **`{{ uplink_port }}`/`{{ client_port }}` per-device variables** for the per-model port mapping (§12), attached to the 6 OM2P devices; built by extending `build-templates.py`, which is also changed to **read the fleet `mesh_key` from `fleet-secrets.conf`** (not regenerate) so images + templates stay coherent (§15.7).
- Revisions built: all four mapped profiles (`lc/v1/v2/v4`).
- Version control: feature branch in the `gwifi-openwrt` worktree (`openwisp-controller`); per DEVELOPMENT.md, advance `main` via PR. Built `.bin`s stay gitignored (baked secrets).

## 17. Follow-ups (out of scope, tracked)

- `docs/om2p-openwrt-install.md` — the ap51-flash first-install runbook (§13).
- Validate the live `sysupgrade`-over-SSH upgrade path on a flashed OM2P; set the OpenWISP **Build `os`** field post-onboard for auto-matching.
- Bench-validate one OM2P end-to-end (flash → wired onboard → push SSID → unplug uplink → mesh failover → replug).

## 18. Open questions

None — all design decisions are resolved (see §16). Implementation-time validations are tracked in §15.
