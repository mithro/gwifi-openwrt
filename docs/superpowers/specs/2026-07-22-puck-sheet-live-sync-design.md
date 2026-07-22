# Puck sheet live-data sync — design

Date: 2026-07-22
Branch: `puck-sheet-live-sync` (off `fleet-firmware-flash`)
Status: approved in conversation (design review 2026-07-22)

## Goal

Populate the "Google WiFi Pucks" sheet (spreadsheet
`1fFm2irzmnLb7RQNmAi4DmAm2_c61wrd5A2j3ZzdqIWE`, gid `210946497`) with
live per-puck data, in one `sync_sheet.py` pass:

1. **Upstream switch + port** from LLDP (`lldpcli` on the puck's `lan`
   interface) into the existing free-text `Upstream` column (D),
   formatted `<switch-shortname> port <port-id>`
   (e.g. `sw-netgear-gsm7252ps-s1 port 1/0/46`).
2. **Wireless AP/mesh MACs** (7 BSSIDs per puck) into per-interface
   columns named after the actual gale interfaces.
3. **Column renames**: the stale `eth0`/`eth1`/`wlan0`/`wlan1` headers
   become the actual interface names (see below).
4. **Name column**: fill the empty `Name` column (B) with the puck's
   hostname (`puckNN`).

## Validated facts (2026-07-22 live probes)

- Sheet header is **28 columns** (A..AB). `sync_sheet.py`'s hardcoded
  `A1:Z1000` range **already truncates** columns AA (`Image Archive`)
  and AB (`Image SHA256`) — must be fixed here.
- Column L `eth0` holds VPD `ethernet_mac0` = the **wan** interface MAC;
  column M `eth1` holds `ethernet_mac1` = the **lan** interface MAC
  (verified on puck12 = 2831HW00WGD: wan=…A2:21=mac0, lan=…A2:22=mac1).
- The CPU-side `eth0` netdev MAC is **randomized every boot** (observed
  `22:cd…`, `72:a5…`, `06:ee…` across pucks) — no sheet column for it.
- Every live puck has exactly 7 wireless interfaces:
  `wl-main-2g4`, `wl-main-5g`, `wl-guest-2g4`, `wl-guest-5g`,
  `wl-iot-2g4`, `mesh-2g4`, `mesh-5g`. There is **no `wl-iot-5g`**.
- `/sys/firmware/vpd/ro/serial_number` is readable on live pucks —
  authoritative serial straight from the device.
- Fleet registry: `wisp.welland.mithis.com:/etc/dnsmasq.d/gwifi-generated/pucks.conf`
  (root-readable via sudo) maps `puckNN` → (wan MAC, lan MAC, 10.1.4.1NN).
  Registered: puck04–puck12. Live today: puck06, 07, 11, 12.
- LLDP caveat: pucks behind unmanaged switches (puck07 today) see peer
  devices (`rpi-sdr-kraken`, another OpenWrt box), not a switch. Only a
  neighbor with `port.local` + a real `SysName` counts as an upstream.
- Existing manual `Upstream` value: row 7 (`2712HW0072Z`)
  = `sw-netgear-gs110emx3 port 7`.

## Architecture

Chosen approach: **live-collector → inventory JSON → sync_sheet**
(single sheet-write path; reuses conflict guards, grid-grow, and the
`test_sheetmap.py` suite).

```
wisp pucks.conf ──┐
                  ├─> collect_puck_live.py ─> inventory/<serial>.json ─> sync_sheet.py ─> sheet
puckNN (ssh) ─────┘        (new)                  (merged fields)          (extended)
```

### Component 1: `tools/fleet/collect_puck_live.py` (new)

- Enumerate fleet from the wisp registry
  (`ssh wisp sudo cat …/pucks.conf`), or `--puck NN` overrides.
- Per reachable puck (ssh as root, IP from registry):
  - serial: `/sys/firmware/vpd/ro/serial_number`
  - hostname: `uname -n`
  - lan/wan MACs: `ip -j link` (parsed as JSON)
  - wifi BSSIDs: `iw dev` (parse Interface/addr pairs)
  - upstream: `lldpcli -f keyvalue show neighbors ports lan`
- **Identity gate**: the device serial must match the registry MACs
  (wan/lan from `ip -j link` vs `pucks.conf` entry) — mismatch aborts
  (same spirit as the flash serial-hint gate).
- **Fail loud**: a reachable puck that yields incomplete data (missing
  VPD, missing wifi interface, unparseable lldp) is an error, not a
  skip. Unreachable pucks are reported per-puck and skipped (offline is
  a normal fleet state; silent gaps are not).
- LLDP upstream recorded only when a managed switch is identified
  (`port.local` present AND chassis SysName non-generic). Peers seen on
  dumb switches are printed for the operator but not recorded.
- Output: merge into `inventory/<serial>.json` (create a minimal record
  `{serial_number, …}` for never-flashed pucks). New fields, all under
  existing top level:
  - `name` (e.g. `puck12`)
  - `upstream` (e.g. `sw-netgear-gsm7252ps-s1 port 1/0/46`)
  - `wifi_macs`: `{interface_name: colon-mac}` for the 7 interfaces
  Flash fields are never touched. Re-runs are idempotent.

### Component 2: `galeflash/sheetmap.py` (extend)

- `FIELD_TO_HEADER` additions (flattened wifi fields are produced by the
  record-prep layer in `sync_sheet.py` from `wifi_macs`):

  | inventory field       | sheet header  |
  |-----------------------|---------------|
  | `name`                | `Name`        |
  | `upstream`            | `Upstream`    |
  | `wifi_wl_main_2g4`    | `wl-main-2g4` |
  | `wifi_wl_main_5g`     | `wl-main-5g`  |
  | `wifi_wl_guest_2g4`   | `wl-guest-2g4`|
  | `wifi_wl_guest_5g`    | `wl-guest-5g` |
  | `wifi_wl_iot_2g4`     | `wl-iot-2g4`  |
  | `wifi_mesh_2g4`       | `mesh-2g4`    |
  | `wifi_mesh_5g`        | `mesh-5g`     |

- New `RENAME_HEADERS: dict[str, str]` = `{eth0→wan, eth1→lan,
  wlan0→wl-main-2g4, wlan1→wl-main-5g}` plus a pure helper
  `compute_header_renames(header) -> list[(col_idx, old, new)]` that
  matches case-insensitively and only renames a cell whose current value
  equals the old name (idempotent; a re-run after renaming is a no-op).
  Column *matching* for FIELD_TO_HEADER runs against the **post-rename**
  header, so `wl-main-2g4` lands in old `wlan0` (N) and `wl-main-5g` in
  old `wlan1` (O). Net new columns: 5 (guest ×2, iot ×1, mesh ×2) →
  AC..AG.
- New `LIVE_OVERWRITE_FIELDS = {upstream}` — recabling is legitimate
  change, enabled by a `--update-live` CLI flag (mirrors
  `--update-flash`). `name` and all MAC fields stay conflict-guarded.

### Component 3: `sync_sheet.py` (fix + extend)

- **Range fix**: read/write/read-back ranges computed from
  `len(get_extended_header(header))` (via `_col_letter`), replacing all
  three hardcoded `A1:Z1000` uses. Initial header read uses `A1:ZZ1000`.
- Apply header renames (from `compute_header_renames`) as guarded header
  cell writes in the same batch, before data writes; the in-memory
  header is renamed before `compute_updates` runs.
- Record-prep: flatten `wifi_macs` dict into `wifi_<iface>` fields
  (dashes → underscores), format all MACs via `format_mac`.
- `--update-live` flag: adds `LIVE_OVERWRITE_FIELDS` to
  `allow_overwrite`.

## Error handling

- Collector: per-puck hard failures (identity mismatch, incomplete
  data) abort the run with the puck named; unreachable pucks are
  loudly listed at the end. Nothing is fabricated (no placeholder
  values, per repo fail-loud rules).
- sync_sheet: existing conflict semantics unchanged — any differing
  non-empty cell outside the allow-set aborts before writing.
- Renames: a header cell that matches neither old nor new name is a
  conflict (printed, abort) — the sheet changed under us.

## Testing

- `test_sheetmap.py` additions (pure, no I/O): rename computation
  (fresh, already-renamed, unexpected-header), new-field column
  assignment landing in renamed columns, `LIVE_OVERWRITE_FIELDS`
  overwrite vs conflict, extended-header width for range computation.
- New `test_collect_puck_live.py`: parsers (`iw dev`, `lldpcli`
  keyvalue, `pucks.conf`, `ip -j link`) against fixtures captured from
  today's live probes; identity-gate and managed-switch classification
  logic.
- Live validation: collector run against the 4 live pucks → dry-run
  sync (plan reviewed) → `--write` → built-in read-back verification.

## Rollout

1. Implement + tests green (85 existing must stay green).
2. Collect from live fleet (puck06/07/11/12) over the welland VPN.
3. `sync_sheet.py` dry-run; review planned updates + renames.
4. `sync_sheet.py --write`; read-back verify.
5. Small discrete commits throughout; PR from `puck-sheet-live-sync`.

## Out of scope

- `wl-iot-5g` (doesn't exist), CPU `eth0` MAC (random per boot).
- Writing `Location`/`Controlled By`/other operator columns.
- The wisp→HA presence integration and the ansells-iot investigation
  (separate tasks).
