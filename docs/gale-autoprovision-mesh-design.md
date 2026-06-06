# Gale auto-provisioning mesh-AP fleet image — Design Spec

- **Date:** 2026-06-05
- **Status:** Approved (spec-reviewer + user); all open questions resolved — ready for implementation planning. Committed to `gwifi-openwrt` (branch `gale-autoprovision-mesh`, unpushed).
- **Target device:** Google Wifi (gale) — OpenWrt **25.12.4**, target `ipq40xx/chromium`, device `google_wifi`
- **Controller:** OpenWISP (pull mode) at `https://wisp.welland.mithis.com`
- **Build env:** `/home/tim/local/gwifi/openwrt` (OpenWrt v25.12.4, already builds factory/sysupgrade)

## 1. Summary

Build a single **generic** OpenWrt image for the welland gale puck fleet that **auto-provisions** from the existing OpenWISP controller and **survives loss of its wired uplink** by falling back to a Wi-Fi mesh backhaul. The image bakes in only bootstrap connectivity, the OpenWISP agent, baked mesh credentials, and all capabilities (VLANs, L2 client bridging, mesh, steering). Per-device runtime config (SSIDs, passphrases, steering parameters, VLAN refinements) is **pulled from OpenWISP** after the puck registers.

## 2. Goals

- **G1** One generic image for all welland gale pucks; per-device identity/config comes from OpenWISP (matched by MAC).
- **G2** On first boot, with no prior config, a puck reaches `https://wisp.welland.mithis.com` and pulls its config.
- **G3** Uplink path prefers the wired `wan` port (802.1q trunk); falls back to the Wi-Fi mesh **automatically**, with no active switchover daemon.
- **G4** Full-service fallback: while on the mesh, **both** management and **all client VLAN traffic** continue working, via a wired-uplink puck acting as the batman-adv gateway.
- **G5** Image contains everything needed for VLANs, client bridging, mesh, and steering, so OpenWISP can enable features without a reflash.

## 3. Non-goals

- Per-device config *content* (SSIDs, passphrases, steering tuning) — owned by OpenWISP templates.
- L3 routing/NAT of client traffic on the puck — pucks are **L2 APs**; ten64 routes and serves DHCP.
- Changes to the OpenWISP server or ten64 (assumed in place and correct).
- Depthcharge/ChromeOS-kernel firmware-upgrade orchestration (tracked separately).

## 4. Context & assumptions (from prior project work)

- OpenWISP is deployed/verified at `wisp.welland.mithis.com` (10.1.5.2, VLAN 5), trusted Let's Encrypt cert, org `default` with registration enabled + shared secret. 11 pucks pre-created and matched by label MAC.
- welland VLANs: **mgmt/net = 5** (10.1.5.0/24, gw .1), **int = 10**, **roam = 20**, **iot = 90**, **guest = 99**. ten64 is the router and DHCP server for all.
- gale hardware: 2 ethernet ports `wan` + `lan` (wan carries the label MAC), 2× ath10k radios (2.4 GHz + 5 GHz), eMMC (ample image room).

## 5. Requirements (decided with user)

- **R1** Full-service mesh fallback: mgmt + all client VLANs over the mesh.
- **R2** `wan` = 802.1q trunk; mgmt VLAN 5 **tagged**; client VLANs 10/20/90/99 tagged.
- **R3** Failover mechanism = **passive L2 mesh extension with batman-adv Bridge Loop Avoidance** (no failover daemon).
- **R4** Provisioning = OpenWISP `openwisp-config` **pull mode** (outbound HTTPS).
- **R5** Generic fleet image; secrets (org shared secret, mesh SAE key) externalized from committed files; built images contain them → **`.bin`s are sensitive, not published**.

## 6. Architecture

- **Radios:** 5 GHz = client AP **+** 802.11s mesh backhaul (shared); 2.4 GHz = client AP.
- **Mesh:** 802.11s (baked mesh-id + WPA3-SAE key) → **batman-adv `bat0`**. Two batman-adv features, doing **different** jobs:
  - **Bridge Loop Avoidance (BLA)** — loop-free bridging when multiple pucks bridge the mesh into the same wired VLANs (this is the failover-safety mechanism of R3).
  - **`gw_mode`** (server on wired-uplink pucks / client on mesh-only pucks) — DHCP gateway *discovery* so clients on a mesh-only puck pull DHCP from ten64 over the best path. (Operates on raw `bat0`; see Risk #3 for the per-VLAN caveat + fallback.)
- **VLANs:** 802.1q tagged throughout — 5, 10, 20, 90, 99.
- **One bridge per VLAN**, spanning the wired trunk + the mesh (+ the matching Wi-Fi AP at steady state):
  - `br-mgmt` = `wan.5` + `bat0.5` → puck's own management IP (DHCP from ten64) + OpenWISP traffic
  - `br-int`  = `wan.10` + `bat0.10` (+ `ap-int`)
  - `br-roam` = `wan.20` + `bat0.20` (+ `ap-roam`)
  - `br-iot`  = `wan.90` + `bat0.90` (+ `ap-iot`)
  - `br-guest`= `wan.99` + `bat0.99` (+ `ap-guest`)
- **Baked vs runtime (important):** the `files/` overlay creates each bridge with **only its `wan.V` + `bat0.V` members — no `ap-*`**. The Wi-Fi APs shown in parentheses are the **post-OpenWISP steady state**: OpenWISP's `wifi-iface` config carries `option network 'br-<name>'`, so netifd **auto-attaches** each AP to its bridge when the SSID is brought up. No client SSIDs exist at first boot.

## 7. Component design

### 7.1 Mesh backhaul
802.11s mesh point on the 5 GHz radio; `mesh_id` and SAE (WPA3) key baked into the image so every puck forms the same mesh on first boot with no controller involvement. `wpad-mesh-mbedtls` provides the SAE-capable supplicant/AP (replaces `wpad-basic-mbedtls`). batman-adv runs over the 802.11s interface producing `bat0`; BLA on.

### 7.2 VLAN bridges
DSA presents `wan`/`lan` as switch ports; `wan` configured as a tagged trunk (VLANs 5/10/20/90/99). For each VLAN *V*: a tagged uplink sub-interface (`wan.V`), a batman VLAN (`bat0.V`), and an L2 bridge `br-<name>`. The overlay bakes each bridge with members `{wan.V, bat0.V}` only (no AP member — see §6 "Baked vs runtime"); `br-mgmt` (V=5) additionally runs a DHCP client for the puck's management IP and never carries a client AP.

### 7.3 Provisioning agent
`/etc/config/openwisp`: `url=https://wisp.welland.mithis.com`, `shared_secret=__OPENWISP_SHARED_SECRET__` (placeholder), `verify_ssl=1`, default poll interval, management interface = `br-mgmt`. `openwisp-monitoring` agent installed for telemetry.

### 7.4 First-boot bootstrap
`/etc/uci-defaults/99-gale-bootstrap` establishes the pre-OpenWISP working state: `wan` trunk + VLAN 5, the per-VLAN bridges (baked with `wan.V`+`bat0.V` members only, per §6), 802.11s + batman-adv + BLA with baked creds, DHCP client on `br-mgmt`, and **no client SSIDs/APs** (added later by OpenWISP, which auto-attach to their bridges via `network=br-<name>`). uci-defaults scripts run once on first boot then are removed (standard OpenWrt convention); must be idempotent.

### 7.5 Steering
`usteer` installed; runtime config delivered via an OpenWISP template (not hard-baked beyond safe defaults).

## 8. Data flows

- **8.1 First boot, wired present:** power → mesh forms → `wan.5` DHCP → mgmt IP → `openwisp-config` → register (MAC match) → pull config → apply SSIDs/VLANs/steering.
- **8.2 First boot / runtime, wired absent:** power → mesh forms → `bat0.5` DHCP via a gateway puck over the mesh → mgmt IP → `openwisp-config` reaches `wisp` over the mesh → same registration/pull. Client VLANs bridge over `bat0.X` to the gateway puck.
- **8.3 Wired→mesh transition at runtime:** `wan` carrier drops → `wan.X` leaves each bridge → only `bat0.X` remains → traffic reroutes over the mesh via BLA; the outbound `openwisp-config` poll continues. Reverse on link-up (wired re-preferred, 1 hop).

## 9. Package set ("everything needed")

- Provisioning: `openwisp-config`, `openwisp-monitoring`
- Mesh: `kmod-batman-adv`, `batctl`, **`wpad-mesh-mbedtls`** (replaces `wpad-basic-mbedtls`; required for 802.11s SAE)
- Steering: `usteer`
- VLAN/bridge: 802.1q is in-kernel (`CONFIG_VLAN_8021Q=y`) + DSA/bridge-vlan tooling (base; no `kmod-8021q` package exists)
- Services: base `dnsmasq`, `firewall4`
- Management/diag: `luci`, `ip-full`, `tcpdump-mini`, `ethtool`
- Wi-Fi: `ath10k-ct` + `ath10k-firmware-qca4019-ct` (already default for the device)

## 10. Build mechanics

Reuse the `openwrt/` v25.12.4 build env. The custom image is defined by three artifacts in the **`gwifi-openwrt`** repo, kept **separate from the stock config** (so the plain v25.12.4 image stays reproducible):

1. A **config fragment** adding the extra `CONFIG_PACKAGE_*` lines (and swapping wpad).
2. A **`files/` overlay** template: `/etc/config/openwisp`, `/etc/uci-defaults/99-gale-bootstrap`, mesh config, and batman/bridge/network config — with **placeholders** for the two credentials (`__OPENWISP_SHARED_SECRET__`, `__MESH_SAE_KEY__`).
3. A **build script** that reads the untracked creds file, substitutes the placeholders into a temporary overlay, and runs `make`.

`make` produces `openwrt-…-google_wifi-squashfs-{factory,sysupgrade}.bin` with the overlay baked in.

**Secrets handling:** committed overlay files contain only placeholders. Real values live in an **untracked, gitignored** `gale-secrets.conf` (a committed `gale-secrets.conf.example` documents the keys). The *built image* still contains the substituted secrets, so the `.bin` artifacts remain unpublishable — already covered by the repo's `*.bin` gitignore. The spec, overlay templates, and build script are safe to commit; only the creds file and the built images are not.

## 11. Error handling / resilience

| Failure | Behavior |
|---|---|
| `wan` link down | bridges fall back to `bat0.X`; traffic rides mesh to a gateway puck |
| `wisp` unreachable | `openwisp-config` keeps the last-applied config running locally |
| Mesh partition | isolated puck keeps running last config; reconverges on heal |
| L2 loop (multi-gateway) | batman-adv BLA suppresses it |
| Cold fleet (no wired anywhere) | mesh-only pucks cannot reach `wisp` until ≥1 puck has wired uplink (expected) |

## 12. Testing

Bench-validate on **one** puck before the fleet:
1. Build → boot wired → confirm mgmt IP on VLAN 5 + OpenWISP auto-registration.
2. Push a test config from OpenWISP → confirm SSIDs/VLANs apply.
3. **Unplug `wan`** → confirm the puck rejoins via the mesh through a second puck and stays manageable, and a client on a client-VLAN SSID still passes traffic.
4. Re-plug `wan` → confirm wired path resumes (preferred).

## 13. Risks / to validate during implementation

1. **ath10k concurrent AP + 802.11s on one 5 GHz radio** (multi-vif) — generally works on ath10k but must be tested; fallback = dedicate 5 GHz to mesh, clients on 2.4 GHz only. (This fallback would change §6/§14 radio plan and the AP/bridge band assignments — carry it into the plan as a decision branch.)
2. ath10k 802.11s stability on IPQ4019 + OpenWISP per-client monitoring over mesh (prior research flagged OpenWISP issue #21) — verify on 25.12.
3. **batman-adv `gw_mode` + BLA over VLAN-tagged `bat0`** with several simultaneous wired gateways: `gw_mode` operates on raw `bat0` while DHCP here runs on tagged `bat0.V` sub-interfaces. Fallback if `gw_mode` won't cooperate with per-VLAN tagging: rely on plain DHCP broadcast/relay over the bridged mesh (BLA still provides loop-free bridging) instead of batman `gw_mode`.
4. First-boot cold-fleet bootstrap requires ≥1 wired-uplink puck to seed mesh-only pucks.

## 14. Decided sub-choices

- Radio plan: **5 GHz shared (AP + mesh) + 2.4 GHz AP** (fallback per Risk #1: dedicate 5 GHz to mesh).
- Steering daemon: **usteer**.
- LuCI: **included** (local debugging).
- Mesh identity: `mesh_id` defaults to a fixed fleet value (overridable); the **SAE key is generated at build time** and recorded in the untracked creds file.
- Version control: committed to the **`gwifi-openwrt`** repo on a feature branch; credentials externalized to an untracked, gitignored `gale-secrets.conf` (placeholders in committed files); built `.bin`s stay gitignored (they contain baked secrets).
- Out-of-band recovery: **none** — rely on wired + mesh reachability; a puck isolated from both is recovered via physical access / the serial + EC console (existing project tooling). No permanent baked recovery SSID.

## 15. Open questions

None — all design decisions are resolved (see §14).
