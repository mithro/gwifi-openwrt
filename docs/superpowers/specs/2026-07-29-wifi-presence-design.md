# OpenWrt → Home Assistant WiFi Presence Design

Date: 2026-07-29
Status: approved (design). Implementation of Tasks 1–5 is **COMPLETE** on
branch `wifi-presence` (commits d302e60, 1b387bc+33d4b2f,
474c92e+bd5c854+26e6a10, c7644d9+b544859+725f456, 0f1548b+4ec0273) — code
written and locally tested only; **nothing has been deployed, no live puck
or OpenWISP server has been touched.** Task 7 (`gdoc2netcfg wifi
show-login`) is cross-repo and still pending. DEPLOYMENT remains gated on
the PR #18 MQTT credential rollout (see Deployment runbook below).
Branch: `wifi-presence` — based on `puck-sheet-live-sync` (for `tools/fleet/`)
**with `main` merged in** so `openwisp/build-templates.py` is the current
ansells-aps version. All template work patterns on (and runs) the merged
copy; the pre-merge `gwifi-puck` build-templates is dead code and must never
be run against wisp.

## Implementation deviations from this spec (Tasks 1–7, recorded 2026-07-29)

- **`ap_name`** uses `{{ name }}` — OpenWISP's built-in device-name
  variable — not `{{hostname}}` as written under Components below;
  `hostname` is not a default OpenWISP device variable.
- **Per-puck `mqtt` verification** in `deploy_presence.py` (Component 3) is a
  puck-side syslog-evidence check: it requires positive log evidence for
  presence-detector, and empty log output FAILS. It is not a broker-side
  "state message arrived" check. The on-broker verification happens once,
  fleet-wide, in runbook step 4.
- **`gdoc2netcfg wifi show-login` requires `--all`** for the fleet-wide dump
  (Task 7, commit 7b0511d). The plan said "no positional args → every WiFi
  host"; that made a bare or typo-truncated invocation print every host's
  plaintext password, and this is the only command in the tasmota/wifi/wisp
  family that prints raw secrets at all. Now: named hosts → those hosts;
  `--all` → every WiFi-sheet host; neither (or both) → usage error, exit 1,
  nothing printed. `set_device_vars.py` always passes explicit machine names,
  so the contract with it is unaffected.

## Goal

Surface "which wifi clients are associated to the fleet" into Home Assistant as
`device_tracker` entities, so HA Person presence (home/away) works from wifi
association in near real-time. Every client on every SSID (ansells,
ansells-iot, ansells-guest) is tracked automatically; no HA configuration
changes are required beyond one-time Person↔tracker assignment.

## Constraints (user-set)

- **Use existing packages; write no new daemons.** On-device software is the
  upstream `presence-detector` from
  [rmoesbergen/openwrt-ha-device-tracker](https://github.com/rmoesbergen/openwrt-ha-device-tracker)
  (v3.x), vendored at a pinned commit. Our code is limited to templates,
  deploy/verify tooling, and configuration.
- **Each puck publishes its own details** — per-AP publishing, no central
  collector.
- **Real-time + reconcile** — ubus hostapd assoc/disassoc events, plus a
  periodic full sync to self-heal missed events.
- Deployment is **gated** on the PR #18 (gdoc2netcfg) rollout step ③: per-device
  MQTT credentials (`wifi-<host>` users) registered with the broker and
  verified.

## Verified preconditions (checked live 2026-07-29)

| Precondition | Result |
|---|---|
| Broker reachability from mgmt VLAN 4 | `ha.welland.mithis.com:1883` OPEN over IPv4 (10.1.90.2, via ten64 mgmt→iot routing) and IPv6. Broker is dual-stack — the old "v6-only" note is stale. |
| Puck IPv6 | Pucks have **no global IPv6** (no RA/DHCPv6 on VLAN 4) → they will connect over IPv4. Python's connect falls back from AAAA to A automatically. |
| Package feed | `python3` 3.13.9 and `python3-paho-mqtt` 1.6.1 available in the 25.12.4 apk feed; `apk update` works from pucks (mgmt has internet). |
| paho API compatibility | presence-detector supports both paho 1.x and 2.x APIs (runtime `CallbackAPIVersion` detection). |
| Disk | ~79 MB free overlay per puck; python3+paho is well within budget. |
| Event source | Fleet wpad has ubus support (usteer depends on it); the 6 AP BSSes appear as `hostapd.wl-*` ubus objects. |

## Architecture

```
registered fleet pucks (OpenWrt)             ha.welland.mithis.com
┌─────────────────────────────┐              ┌──────────────────┐
│ hostapd.wl-* ──ubus events──▶│              │ mosquitto :1883  │
│ presence-detector (procd)   │──MQTT/IPv4──▶│  user wifi-puckNN│
│  settings.json (OpenWISP-   │              └────────┬─────────┘
│   templated, per-dev creds) │                       │ MQTT discovery
└─────────────────────────────┘              ┌────────▼─────────┐
                                             │ Home Assistant   │
                                             │ device_tracker.  │
                                             │  puckNN_<mac>    │
                                             │ Person = OR of   │
                                             │  assigned trackers│
                                             └──────────────────┘
```

- presence-detector subscribes to every `hostapd.*` ubus object
  (auto-detected), reacting to assoc/disassoc in ~seconds, with
  `fallback_sync_interval=60` re-syncing the full station list once a minute.
- Discovery topic `homeassistant/device_tracker/<slug>/config`, state topic
  `homeassistant/device_tracker/<slug>/state`, where
  `slug = <ap_name>_<mac-with-underscores>`.

## Entity model: per-puck trackers (roaming race)

usteer actively steers clients between pucks, and the old AP's disassoc can
arrive after the new AP's assoc. A shared per-MAC topic would let the stale
`not_home` overwrite the fresh `home` until the next sync. Instead each puck
sets `ap_name=<puckNN>`, giving one entity per (puck, MAC):
`device_tracker.puck06_aa_bb_cc_dd_ee_ff`. Roaming then flips two different
entities and an HA Person (which ORs its router-type trackers) never
false-aways. Cost: ~6× entities (accepted) and a one-time manual Person
assignment per tracked human device.

## Components

1. **`ansells-presence` OpenWISP template** (in `openwisp/build-templates.py`,
   same pattern as the ansells-aps templates), attached per device via
   `Config.templates` exactly as the existing templates are (no OpenWISP
   Group objects). Attach set = every registered fleet-puck device (so
   future pucks 01/02 pick it up on registration); the deploy/verify tools
   operate on the *live* pucks from wisp's `pucks.conf` registry. Delivers:
   - `/opt/presence-detector/presence-detector.py` — vendored upstream script,
     pinned commit recorded in the template source.
   - `/etc/presence-detector/settings.json` — rendered per device:
     `mqtt_host=ha.welland.mithis.com`, `mqtt_port=1883`,
     `mqtt_username={{mqtt_username}}`, `mqtt_password={{mqtt_password}}`,
     `ap_name={{hostname}}`, `fallback_sync_interval=60`,
     `mqtt_retain_state=true` (default), interfaces auto-detect, no filters
     (all SSIDs).
   - procd init script (upstream's, adjusted paths), enabled.
   Credentials live only in per-device OpenWISP configuration variables —
   never in the git-tracked template.
2. **Device-vars tool** — sets each OpenWISP device's
   `mqtt_username`/`mqtt_password` config variables. Credential source:
   gdoc2netcfg's docs state the device side "must be configured out-of-band
   with the same derived MqttUser/MqttPassword (re-derivable from the same
   mqtt_secret)" — so a small new `gdoc2netcfg wifi show-login <host>`
   subcommand (gdoc2netcfg repo; follows the `password --quiet` root-only
   precedent, reusing `wifi_credentials.build_logins`) emits one host's
   login. The device-vars script in this repo (`tools/fleet/`) runs it over
   ssh on ten64 and pushes the values into OpenWISP via the established
   ow-shell pattern on wisp. Secrets transit ssh pipes only — never disk,
   git, or logs.
3. **`tools/fleet/deploy_presence.py`** — per puck (registry from wisp
   `pucks.conf`, as `check_vlan_reach.py` does): `apk add python3
   python3-paho-mqtt`, verify the service starts, then verify a state message
   from that puck actually appears on the broker. Fail-loud per puck; summary
   matrix; non-zero exit on any failure.

## Deployment runbook (ordered, gated)

1. **GATE**: PR #18 rollout ③ complete — `[wifi]`/`[wisp]` `mqtt_secret` set,
   `wifi register-broker` run, logins verified.
2. Device-vars tool → OpenWISP per-device variables set.
3. `build-templates.py` run (mutates wisp; it is idempotent/retry-safe per the
   tenwrt-parity work). Known gotcha: an OpenWISP per-BSS apply can leave a
   BSS beaconless — follow each puck's apply with a full `wifi` reload check
   ([[gwifi-openwisp-apply-breaks-beacon]]).
4. `deploy_presence.py` across the live fleet.
5. End-to-end verify: `mosquitto_sub` on
   `homeassistant/device_tracker/+/config` + state topics shows every live
   puck; flip a known client (associate/disassociate) and watch home/not_home.
6. Manual (user): assign phone trackers to Persons in the HA UI.

## Error handling

- presence-detector reconnects automatically (1–60 s backoff); retained state
  + 60 s full sync make broker/HA restarts self-healing.
- Deploy tooling: fail-loud, never skip a puck silently, never print secrets.
- BSSID/interface churn: interfaces are auto-detected at service start; a
  `wifi` reload restarts hostapd objects — procd keeps the service up and the
  sync interval re-registers clients.
- **Known accepted risk — dead-AP stale `home`**: if a puck dies uncleanly
  (power loss), its retained per-puck `home` states stay frozen (MQTT
  device_tracker has no expire_after) and a Person ORing that tracker stays
  home. Accepted for now (rare, human-noticed; the existing gdoc2netcfg
  reachability entities show the puck itself down). If it bites, the fix is
  an HA automation keying off the puck's connectivity entity — not new
  on-device code.
- **`POST_RELOAD_HOOK` churn**: it now enables+restarts presence-detector on
  EVERY future config apply once `python3` exists on a puck — the same
  accepted churn class as the existing lldpd/usteer/cron lines, but worth
  naming: an unrelated template edit will bounce presence-detector
  fleet-wide.
- **`mode 0600` on `/etc/presence-detector/settings.json` is defense-in-depth
  only, not a security boundary**: pucks have no non-root local users, and
  puck dropbear still accepts blank-password root login (already flagged
  out-of-scope below), so anyone who can reach dropbear reads the file
  regardless of its mode.
- **netjsonconfig literal-placeholder gotcha**: `evaluate_vars` leaves a
  LITERAL `{{ mqtt_username }}` in the rendered file when the variable is
  absent from `Config.context` — it does not raise, and does not blank it.
  `build-templates.py` therefore prints a `WARNING: presence attached but
  mqtt context vars MISSING on: [...]` naming any device attached without
  those context vars. Ordering (`set_device_vars.py` runs BEFORE the config
  applies) is load-bearing.

## Testing

- Template rendering: unit tests alongside the existing build-templates
  patterns (settings.json shape, variable substitution, no secrets in
  template).
- Deploy tool: unit tests for pure logic (reuse `galeflash` registry parsing;
  parse apk/service/broker-verify outputs).
- End-to-end: the runbook's step 5 on the live fleet.

## Out of scope (flagged follow-ups)

- Baking python3+paho+presence-detector into the gale fleet image (reflash
  persistence) — image workstream.
- tenwrt + OpenMesh spare APs (template attach is trivial later).
- HA dashboards; wifi-device remote syslog (will reuse this template pattern).
- Locking down puck dropbear blank-password root ssh (pre-existing flag).
