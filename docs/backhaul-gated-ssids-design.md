# Backhaul-gated SSID advertisement (distributed batman gateways) — Design Spec

- **Date:** 2026-06-08
- **Status:** Draft — pending spec review + user approval.
- **Scope:** "Project 2" of the ten64-Wi-Fi initiative. (Project 1 = folding ten64's own radios into an OpenWISP-managed passthrough guest — deferred, separate spec.)
- **Target devices:** the whole AP fleet — Google Wifi (gale) `ipq40xx/chromium`, and Open-Mesh OM2P `ath79/generic` (lc/v1/v2/v4).
- **Controller:** OpenWISP (pull mode) at `https://wisp.welland.mithis.com`.
- **Build env:** `/home/tim/local/gwifi/openwrt` (OpenWrt v25.12.4).
- **Builds on:** [`gale-autoprovision-mesh-design.md`](gale-autoprovision-mesh-design.md), [`om2p-autoprovision-mesh-design.md`](om2p-autoprovision-mesh-design.md).

## 1. Summary

Each AP node must **advertise its client SSIDs only while it actually has a working path to ten64** (the router/DHCP/internet gateway). Today nothing checks this: an isolated node (no wired uplink *and* no usable mesh path) keeps beaconing, so clients associate, complete SAE/PSK locally, then fail DHCP — a black-hole AP.

We add a small, node-local control loop that gates the client SSIDs on backhaul presence, using **batman-adv's own gateway mechanism as the distributed signal** ("Approach D"): every node that can reach ten64 over **its own wired uplink** announces itself as a batman **gateway server**; every node treats *"I am a wired gateway, **or** I can see a gateway over the mesh"* as "I have backhaul." No new daemon, no new mesh, no changes to ten64 or to the client data path — just existing primitives (`batctl`, `hostapd` ubus, `cron`/`hotplug`) wired together by one script.

This also **completes the dynamic `gw_mode` the gale/OM2P designs already called for** (their bootstraps ship `gw_mode='client'` static; §6 of the gale spec intended server-on-wired/client-on-mesh for DHCP-gateway discovery). One mechanism, two payoffs: correct backhaul gating **and** DHCP-gateway discovery for mesh-failover client traffic.

## 2. Goals

- **G1** A node never advertises client SSIDs when it has no working backhaul to ten64 (no false "service available").
- **G2** A node *does* advertise when it has backhaul over **either** path — its own wired uplink **or** the wireless mesh to a wired node (no false negatives; wired-only and mesh-only nodes both serve correctly).
- **G3** Reuse what the images already ship (batman/batctl, hostapd, cron, hotplug). No bespoke daemon, no new package, no second mesh.
- **G4** No changes to ten64, to the per-VLAN bridge / BLA client data path, or to the OpenWISP wireless templates' *content*.
- **G5** Board-agnostic: one identical script for gale and every OM2P variant (auto-discovers the wired uplink and the gateway; no per-board constants).
- **G6** Fail-safe: a node that cannot determine backhaul keeps SSIDs **off** (prevent black-hole), stays manageable, and self-heals when backhaul returns.

## 3. Non-goals

- Carrying client data over batman-on-wired ("batman-over-everything") — explicitly rejected; the existing `wan.V` + `bat0.V` bridge + BLA failover is untouched.
- Making ten64 a batman node or a gateway anchor — not required by Approach D.
- Project 1 (ten64 radio passthrough guest).
- Cutover/rollback/migration — **nothing is deployed yet**; this is steady-state image behavior only.
- Per-device config content (SSIDs, passphrases) — still owned by OpenWISP.

## 4. Context & assumptions

- Verified by the 2026-06-08 ten64 audit (see `gwifi-ten64-infrastructure` memory): ten64 is the L2/L3 gateway/DHCP for the fleet VLANs; it is **not** a batman node and does not need to be for this design.
- Existing node design (both images): 802.11s mesh → `bat0` (BLA on, DAT on); one bridge per VLAN `br-<name>` = `{<uplink>.V, bat0.V}`; `br-mgmt` (VLAN 5) runs DHCP client → node mgmt IP + default route via ten64. `batctl-default` already in the package set.
- 802.11s mesh is **wpa_supplicant-managed**; client APs are **hostapd**-managed and register `hostapd.<ifname>` ubus objects. (To be reconfirmed in the validation spike — see §12.)
- Nothing is deployed on hardware yet; gale image built+merged, OM2P built+uploaded, neither flashed to field units.

## 5. Requirements (decided with user)

- **R1** Project 2 (this) is designed/built before Project 1.
- **R2** Signal = batman gateway presence (`gw_mode`/`batctl gwl`), **not** an L3 ping and **not** batman-carries-data. Distributed: **all wired-uplink nodes are gateway servers**, not a single anchor.
- **R3** No daemon — reuse existing primitives; the only new artifact is one script + a cron line + a hotplug hook + minimal overlay wiring.
- **R4** No cutover handling (undeployed fleet); instead a fail-safe boot state.
- **R5** ten64 and the client data path are not touched.

## 6. Architecture (Approach D — distributed wired-uplink gateways)

Each node runs one periodic + event-triggered evaluation:

```
Inputs (per evaluation):
  wired_ok   = uplink carrier up  AND  ten64 reachable via the wired uplink (wired-isolated)
  gw_present = batctl gwl lists >= 1 reachable gateway   (gateways seen over the mesh)

Decision:
  if   wired_ok:    role = server   ; serve = ON      # I am a wired exit
  elif gw_present:  role = client   ; serve = ON      # a wired exit is reachable over the mesh
  else:             role = client   ; serve = OFF     # islanded -> gate

Actuate:
  role  -> batctl gw <role> [bandwidth class when server]
  serve -> for each client AP BSS: ubus call hostapd.<bss> {enable|disable}
```

Why this is the right shape:
- The **wired** half is a *local* fact (does *my* uplink reach ten64), turned into a batman gateway announcement.
- The **mesh** half is read from batman's **existing wireless `bat0`** — gateway announcements ride the mesh that's already there. No batman-over-wired, no second mesh BSS.
- The actual client failover data path is unchanged: a mesh-only node's traffic still rides `bat0.V` + BLA to a wired node; `gw_mode` merely *names* that wired node so batman can also steer DHCP there (the gale design's original intent).

`★ Approach D in one line ─────────────────────────`
Wired backhaul is detected locally and **announced over the wireless control plane**; batman already does gateway election, hostapd already drops a BSS — we only supply the policy that connects uplink-health → gateway-announcement → beaconing.
`──────────────────────────────────────────────────`

## 7. Component design

### 7.1 The decision script — `/usr/sbin/gwifi-backhaul-gate`

A single POSIX-sh script. Structure:
- **Pure decision function** `decide(wired_ok, gw_present, fail_count) -> (role, serve, new_fail_count)` — no side effects, unit-testable in isolation (§12).
- **Probe functions** that produce `wired_ok` / `gw_present`.
- **Actuator functions** that apply `role` / `serve` idempotently (no-op if already in the desired state, to avoid log spam and BSS churn).
- A `--once` mode (used by cron/hotplug) and a `--status` mode (prints derived state for debugging).

### 7.2 Wired-uplink + gateway auto-discovery (board-agnostic, per G5)

- **Uplink netdev:** the non-`bat0` member of `br-mgmt`. `bridge link show` (or `ls /sys/class/net/br-mgmt/brif/`) → the member matching `*.5` whose parent is a physical eth = `<uplink>.5`; its parent netdev = the wired uplink. Works for gale (`wan`) and every OM2P variant (`eth0`/`eth1`) with no constants.
- **Gateway (ten64):** the default-route nexthop on `br-mgmt` — `ip -4 route show default dev br-mgmt` (DHCP-provided = ten64). No hardcoded IP/MAC.

### 7.3 `wired_ok` — wired-isolated reachability

Two-stage, cheap-first:
1. **Carrier:** `cat /sys/class/net/<uplink>/carrier` == `1`. If down → `wired_ok=false` immediately.
2. **Reachability constrained to the wired path** (distinguish wired from the BLA mesh-failover path). Primary method: `arping -I <uplink>.5 -c1 -w1 <gw_ip>`. If the mgmt sub-iface is bridge-enslaved and `arping -I` cannot egress it directly, fallback: prime the neighbor (`ping -c1 -w1 <gw_ip>`), read `gw_mac` (`ip neigh`), then confirm the bridge learned it on the wired port — `bridge fdb show | grep -i "<gw_mac> .*dev <uplink>.5"`. The FDB fallback is **weaker** than the primary: with BLA active and ten64 reachable over both paths, the bridge can learn ten64's MAC on the wired port from mesh-origin traffic BLA bridged back in, yielding a *false* wired-exit — so `arping` is strongly preferred and FDB is a last resort. (Exact method finalized in the §12 spike; the *function* — "ten64 reachable specifically via my wired uplink" — is fixed.)

Rationale for wired-isolation: a node must announce gateway-server only if **its own** uplink is a real exit. If only the mesh reaches ten64, it must be a *client* (mesh-exit), not a server. Getting this wrong is not catastrophic (traffic still exits via BLA failover) but would make gateway election suboptimal; isolating wired keeps the signal honest.

### 7.4 `gw_present` — mesh gateway visibility

`batctl gwl` parsed for ≥1 gateway entry. A node in `gw client` builds/sees the gateway list from server announcements over `bat0`. (Confirm in §12 that `gwl` is populated in client mode and empties when no server is reachable.)

### 7.5 `gw_mode` actuation

Runtime via `batctl gw server <bw>` / `batctl gw client` (not uci, to avoid churn and fighting OpenWISP). Re-asserted every evaluation, so it survives reloads. Server bandwidth: a nominal symmetric class (e.g. `100mbit/100mbit`); value documented as a tunable. Base uci `gw_mode` stays `client` (safe default if the script hasn't run yet).

### 7.6 SSID gating actuation

- **Target set:** all client AP BSSes = the `hostapd.*` ubus objects (`ubus list | grep '^hostapd\.'`). The 802.11s mesh is supplicant-managed and therefore **not** in this set; as a hard safety guard the script also explicitly refuses to touch any iface whose mode is `mesh`.
- **Enable/disable:** `ubus call hostapd.<bss> disable` / `enable` (runtime only — does **not** edit uci, so it never fights OpenWISP's pushed config and never churns the radio).
- **Empty target set = no-op:** if an evaluation runs before OpenWISP has pushed/started any client BSS, `hostapd.*` is legitimately empty; the actuator treats this as a successful no-op (nothing to gate), never an error.
- **Management is unaffected:** mgmt/OpenWISP live on `br-mgmt` (wired/mesh), not on a client BSS — so a gated node stays reachable, keeps polling OpenWISP, and keeps the mesh up to detect recovery.

### 7.7 Scheduling & triggers

- **Periodic:** a `cron` line (busybox crond) runs `gwifi-backhaul-gate --once` every minute (re-asserts state; recovers within ≤1 cycle, including after an OpenWISP `wifi reload` transiently re-enabled a BSS).
- **Event (fast reaction):** `/etc/hotplug.d/net/30-gwifi-backhaul` runs `--once` on carrier change of the discovered uplink, so wired-loss gating is near-immediate rather than waiting for the next minute.

### 7.8 Hysteresis & fail-safe

- **Debounce down, fast up:** flip `serve=OFF` only after **K** consecutive "no backhaul" evaluations (default K=3 ≈ 3 min with 1-min cron, plus instant hotplug for carrier loss); flip `serve=ON` on the first positive evaluation. Counter persisted in `/tmp`.
- **Boot state = fail-closed:** the script's initial `serve` state is **OFF**; client BSSes are enabled only after the first evaluation confirms backhaul, preventing a boot-time black hole. (A fresh unit has *no* client SSIDs anyway — they arrive later from OpenWISP — so the guarantee is the script defaulting to OFF and gating each BSS as/after it appears, **not** pre-disabling anything in the overlay.) The script is part of the image and asserted present by the verifier (§12), so "script missing" is caught at build time.

## 8. Interaction with the existing design

| Existing element | Change |
|---|---|
| 802.11s mesh, `bat0`, BLA, DAT | none |
| per-VLAN bridges `{<uplink>.V, bat0.V}` | none |
| client data failover (wired↔mesh via BLA) | none |
| `gw_mode` (was static `client`) | now driven dynamically by the script (server when wired-exit) |
| client AP BSSes | runtime enable/disable via hostapd ubus, gated on backhaul |
| ten64 | none |
| OpenWISP wireless template content | none (script is baked in the image, not pushed) |

## 9. Overlay placement & OpenWISP

Identical files added to **both** overlays (`gale-image/files/`, `om2p-image/files/`):
- `usr/sbin/gwifi-backhaul-gate` (the script).
- `etc/hotplug.d/net/30-gwifi-backhaul` (carrier trigger).
- cron line installed idempotently by the existing `uci-defaults` bootstrap (`99-gale-bootstrap` / `99-om2p-bootstrap`), which also ensures `cron` is enabled. (Fail-closed boot comes from the script's default `serve=OFF` per §7.8, not from pre-disabling SSIDs — a fresh unit has none.)
- Optional `etc/config/gwifi-backhaul` for tunables (poll interval, K, gw bandwidth) — else constants at the top of the script.

OpenWISP: **no template change required.** Gating is runtime-only via ubus and does not modify the pushed wireless config; the per-minute re-assert tolerates OpenWISP config reloads (a reload may re-enable a BSS for up to ~1 cycle before it's re-gated — accepted, and noted as known behavior).

## 10. Error handling / resilience

| Situation | Behavior |
|---|---|
| Wired up, reaches ten64 | `gw server`; SSIDs on |
| Wired down, mesh reaches a gateway | `gw client`; SSIDs on; client traffic via `bat0.V`+BLA; DHCP steered to a gateway node |
| Wired carrier up but switch isolated from ten64 | not a server; SSIDs follow `gw_present` (correct) |
| Fully islanded (no wired exit, no mesh gateway) | SSIDs **off** after K cycles; mgmt + mesh stay up; self-heals |
| OpenWISP pushes a `wifi reload` | re-gated within ≤1 cron cycle |
| Script/cron fails to run | fail-closed (SSIDs stay off) — safe; verifier asserts presence at build |
| Flapping uplink | hysteresis (K-down / instant-up) damps SSID flap |

## 11. Validation & testing (no hardware yet)

1. **Unit tests of `decide()`** — exhaustive truth table (`wired_ok` × `gw_present` × `fail_count`) + hysteresis transitions, run on the dev box with a plain sh test harness (or `shunit2`). Pure function, no root.
2. **Namespace integration harness** — on the Linux dev box, build a mini-fleet with `ip netns` + `veth` + batman-adv (mainline kernel): node-A (veth "wired" to a "ten64" netns + a veth "mesh" to node-B), node-B (mesh only). Assert: A→server & SSIDs on; cut A's wired → A demotes to client and (if B has no other exit) both gate off; restore → recover. Validates `gw`/`gwl` semantics and the actuators without gale/OM2P hardware. **Caveat:** a flat `veth` mesh is a single L2 segment (every node hears every node), so it does *not* exercise multi-hop gateway propagation; add a 3-node **line** topology (A—B—C, only A wired, B relaying) to approximate, and treat true multi-hop RF propagation as bench-only (§11.4, Q7).
3. **Image verifier** — extend `verify-gale-image.py` / `verify-om2p-image.py` to assert the script + hotplug hook + cron line are present and `batctl-default`/`cron` are in the manifest.
4. **Bench (later, when hardware is available)** — real gale + OM2P: pull/cut the uplink, partition the mesh, confirm beaconing tracks backhaul and DHCP still works on the mesh-failover path. (Folds into the existing gale Task-9 / OM2P bench.)

## 12. Open questions / risks (to close in spike before/while planning)

- **Q1** Exact `wired_ok` isolation primitive: `arping -I <uplink>.5` vs the FDB-port-after-priming-ping method (does `arping -I` egress a bridge-enslaved sub-iface on this build?).
- **Q2** Confirm `batctl gwl` populates in `gw client` and empties when no server is reachable (signal validity).
- **Q3** Confirm the 802.11s mesh is *not* a `hostapd.*` object (so enumerating `hostapd.*` can't accidentally gate the mesh); keep the explicit mesh-mode guard regardless.
- **Q4** `ubus hostapd.<bss> disable/enable` behavior on 25.12.4 (clean BSS down/up, beacons actually stop, re-enable restores cleanly).
- **Q5** Hysteresis K and cron interval tuning (default K=3 @ 1 min).
- **Q6** gw server bandwidth class value and whether multiple equal servers cause any churn in selection (cosmetic).
- **Q7** Gateway-announcement propagation across a multi-hop 802.11s mesh with `mesh_fwding=0`: batman OGMs carrying gateway TQ are batman's own broadcasts over the hardif and *should* be independent of 802.11s-layer forwarding, but the whole signal hinges on `gwl` populating on a mesh-only node ≥2 hops from any wired node. Validate with the 3-node line harness (§11.2) and confirm on the bench (§11.4).

## 13. File inventory (delta)

```
gale-image/files/usr/sbin/gwifi-backhaul-gate                 (new, shared)
gale-image/files/etc/hotplug.d/net/30-gwifi-backhaul         (new, shared)
gale-image/files/etc/uci-defaults/99-gale-bootstrap          (edit: install cron line, fail-closed init)
om2p-image/files/usr/sbin/gwifi-backhaul-gate                 (new, identical copy)
om2p-image/files/etc/hotplug.d/net/30-gwifi-backhaul         (new, identical copy)
om2p-image/files/etc/uci-defaults/99-om2p-bootstrap          (edit: install cron line, fail-closed init)
verify-gale-image.py / verify-om2p-image.py                   (edit: assert presence)
docs/backhaul-gated-ssids-plan.md                             (next: implementation plan)
```

(The two new files are byte-identical across the images; the plan will keep them DRY via a single source copied into both overlays at build time, mirroring how `fleet-secrets.conf` is shared.)
