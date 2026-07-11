<!-- SPDX-License-Identifier: Apache-2.0 -->
# wisp netboot-install — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Power-cycling a fleet-firmware gale puck on VLAN 4 gets OpenWrt installed
to its eMMC automatically and boots from eMMC on every later cycle.

**Spec:** `docs/wisp-netboot-install-design.md` (approved). Decision numbers
(D1–D7) and section numbers (§5.1–§8) below refer to that document.

**Architecture:** New VLAN 4 `wifi` (10.1.4.0/24): ten64 routes it and serves
DNS (gdoc2netcfg-generated puck host-records) but deliberately serves **no
DHCP/boot** there (D7); the wisp VM migrates onto it (single NIC, static
10.1.4.2) and runs DHCP+TFTP (dnsmasq, `port=0`) + HTTP (nginx + a small API)
for the pucks; gdoc2netcfg pushes puck identity (`pucks.json` + DNS fragment);
a `gwifi-netboot` service owns armed-state, phone-home, and the generated
per-MAC dnsmasq config; an idempotent installer initramfs flashes the eMMC.

**Tech stack:** systemd-networkd + libvirt + netplan (infra), dnsmasq, nginx,
Python 3.11+/uv + pytest (services, both repos), OpenWrt 25.12 ipq40xx build
tree (installer image), POSIX sh (installer init script).

**Conventions (apply to every task):**
- All Python runs via `uv` (`uv run`, `uv run pytest`). Never bare `python`/`pip`.
- Commit after every green test cycle; small discrete commits.
- Never redirect stderr to /dev/null. Temp files under the repo-local `tmp/`.
- Remote ops: `ssh ten64.welland.mithis.com` / `ssh wisp.welland.mithis.com`
  (BatchMode key auth works for user `tim`; use `sudo` on the remote for root
  files — `/usr/sbin` is not in the non-root PATH).
- Anything >60 s: run in background with a log and report progress ~every 60 s.

**Phase dependency graph:** Phase 1 → Phase 2 → Phase 4 → Phase 7.
The **development/TDD** portions of Phase 3 (gdoc2netcfg), Phase 5 (gwifi-netboot
code, Tasks 5.1–5.5 + the code steps of 5.6) and Phase 6 (Tasks 6.1–6.3) are
independent of each other and of Phase 2 and may run in parallel. The
**deployment** tasks are not: Task 3.5 Step 3, Task 5.6's deploy steps, Task
5.7, and Task 6.4 all require Phases 2 **and** 4 complete (wisp at 10.1.4.2
with dnsmasq/nginx up) — deploying earlier crash-loops `serve` binding
10.1.4.2 on the live VM. Everything lands before Phase 7 (pilot).

**⚠ STOP-AND-CONFIRM points (live infra):** Task 2.3 (wisp VM shutdown/retarget)
and Task 7.1 (switch port change). Announce before executing; these affect a
running service and the physical network.

---

## Phase 1 — VLAN 4 network foundation (ten64 + sheet)

### Task 1.1: Add VLAN 4 to the VLAN-Allocations sheet

**Files:** none (Google Sheet edit + verification commands)

The `Welland - VLAN Allocations` tab (gid 208407908) drives gdoc2netcfg's VLAN
topology. The fleet service-account key (`~/.config/gale-fleet/sheets-sa.json`)
has write access to this spreadsheet (it is what `sync_sheet.py --write` uses).
**Note:** `tools/fleet/` (incl. `sync_sheet.py`) is NOT on this branch — it
lives on the unmerged `fleet-firmware-flash` branch; read it at
`/home/tim/local/gwifi/gwifi-openwrt/.worktrees/fleet-firmware-flash/tools/fleet/`.

- [x] **Step 1:** Write `tmp/add_vlan4_row.py` (PEP-723 script, deps
  `google-auth`,`requests`) that appends one row to the tab via the Sheets API
  `values:append` on range `'Welland - VLAN Allocations'!A:I`:
  `["4","wifi","10.X.4.X","255.255.255.0","/24","","","","WiFi AP management (see gwifi-openwrt docs/wisp-netboot-install-design.md)"]`
  Model auth on `tools/fleet/sync_sheet.py` (scope
  `https://www.googleapis.com/auth/spreadsheets`). Print the updated range.
  **Placement caveat:** `values:append` appends after the last non-empty row —
  the tab has section headings ("Untrusted VLANs" etc.), so appending at the
  bottom is acceptable but verify gdoc2netcfg's `vlan_parser` doesn't require
  numeric ordering (read `src/gdoc2netcfg/sources/vlan_parser.py` first; if it
  does, insert the row after VLAN 1 instead using `batchUpdate`).
- [x] **Step 2:** Run it: `cd tmp && uv run add_vlan4_row.py`. Expected: HTTP
  200, updated range printed.
- [x] **Step 3:** Verify the published CSV shows the row (publish lag can be a
  few minutes; retry):
  `curl -sL 'https://docs.google.com/spreadsheets/d/e/2PACX-1vR5j6yiZCEv5YNoeVNLM4MMsxzBVjG4OtViBz7tXXF1LydHd8bCOOVWt7MvfVEPZtK0TeWgyxF3i9Tj/pub?gid=208407908&single=true&output=csv' | grep '^4,wifi'`
- [x] **Step 4:** On ten64, confirm gdoc2netcfg still validates with the new
  VLAN: `ssh ten64.welland.mithis.com 'cd /opt/gdoc2netcfg && uv run gdoc2netcfg fetch && uv run gdoc2netcfg validate'`
  Expected: exit 0, no new constraint errors. (VLAN 4 has no hosts yet — that
  must be fine; if the validator objects to a hostless VLAN, note it and fix in
  Phase 3's repo work.)
- [x] **Step 5:** Delete `tmp/add_vlan4_row.py`; commit nothing (no repo change).

### Task 1.2: ten64 networkd units for vlan-wifi + br-wifi

**Files (on ten64, root):**
- Create: `/etc/systemd/network/vlan-wifi.netdev`, `vlan-wifi.network`,
  `br-wifi.netdev`, `br-wifi.network`
- Modify: `/etc/systemd/network/br-raw.network` (add `VLAN=vlan-wifi`)

Mirror the existing `*-net` pattern exactly (verified 2026-07-11):

`vlan-wifi.netdev`:
```ini
[NetDev]
Name=vlan-wifi
Kind=vlan

[VLAN]
Id=4
```
`vlan-wifi.network`:
```ini
[Match]
Name=vlan-wifi

[Network]
Bridge=br-wifi
```
`br-wifi.netdev`:
```ini
[NetDev]
Name=br-wifi
MACAddress=02:00:0a:01:04:01
Kind=bridge

[Bridge]
STP=yes
```
`br-wifi.network`:
```ini
[Match]
Name=br-wifi

[Network]
IPv6AcceptRA=no
# WiFi AP management (VLAN 4, 10.1.4.X) — see gwifi-openwrt
# docs/wisp-netboot-install-design.md. dnsmasq@internal deliberately
# does NOT serve this VLAN; wisp (10.1.4.2) is the DHCP/TFTP/DNS server.
Address=10.1.4.1/24
Address=2404:e80:a137:104::1/64

# No RA here: dnsmasq is excluded from br-wifi (enable-ra is global to the
# instance) and pucks are v4-only. wisp uses a static v6 gateway.
IPv6SendRA=no
ConfigureWithoutCarrier=yes
```

- [x] **Step 1:** Write the four files on ten64 (scp from a local `tmp/`
  staging dir, then `sudo install -m 0644 -o root -g root`).
- [x] **Step 2:** Add `VLAN=vlan-wifi` to `br-raw.network`'s `[Network]` VLAN
  list (after `VLAN=vlan-store`): `sudo` edit.
- [x] **Step 3:** Apply: `sudo networkctl reload`. (`reload` creates new
  netdevs on current systemd; if br-wifi doesn't appear, fall back to
  `sudo systemctl restart systemd-networkd` — warn user first: brief blip on
  all ten64 interfaces.)
- [x] **Step 4:** Verify: `ip -br addr show br-wifi` → `UP 10.1.4.1/24 2404:e80:a137:104::1/64`;
  `ip -br link show vlan-wifi` → `UP` with master br-raw... (vlan-wifi's
  master is br-wifi; it rides br-raw). `bridge vlan` not needed (Linux vlan
  subif, not vlan-aware bridge). From desktop: `ping -c2 10.1.4.1` succeeds
  (routed via existing paths).
- [x] **Step 5:** Confirm dnsmasq is NOT yet answering there:
  `dig +time=2 +tries=1 @10.1.4.1 wisp.welland.mithis.com` → connection
  refused/timeout is expected at this point (bind-dynamic hasn't been told to
  listen, but see Task 1.3 for the explicit exclusion).

### Task 1.3: ten64 dnsmasq — DNS-serve + DHCP-ignore VLAN 4 + README (D7)

> **Revised during execution (D7):** the original zone-forward approach is
> impossible — the internal instance is authoritative for the parent
> `welland.mithis.com` (`auth-zone`), so nested `server=/wifi…/` forwards are
> pre-empted by authoritative NXDOMAIN (verified: dead forward target still
> returned instant NXDOMAIN). Instead ten64 serves DNS on br-wifi itself
> (host-records generated in Phase 3) and only DHCP/boot is wisp's.

**Files (on ten64, root):**
- Create: `/etc/dnsmasq.d/internal/network-04-wifi.conf`
- Modify: `/etc/dnsmasq.d/README`
- Remove (installed by the first, pre-D7 version of this task):
  `/etc/dnsmasq.d/internal/network-04-wifi-IGNORED.conf` and the two
  `server=/wifi…/` + `server=/4.1.10…/` lines in `03-zone-forwarders.conf`.

`network-04-wifi.conf` (per-VLAN file pattern, but **no DHCP**):
```ini
# wifi: WiFi AP management (gale pucks)
# 10.1.4.0/24, VLAN 4
#
# SPLIT-ROLE VLAN — see gwifi-openwrt docs/wisp-netboot-install-design.md:
#   ten64 (this dnsmasq): DNS + routing. Puck host-records are generated
#     by gdoc2netcfg into generated/gwifi-pucks-dns.conf.
#   wisp (10.1.4.2): DHCP + TFTP netboot steering. The netboot-first puck
#     firmware must ONLY ever see wisp's DHCP answers (bootfile steering /
#     eMMC fallback), so this instance must NEVER serve DHCP here.

interface=br-wifi
listen-address=10.1.4.1
listen-address=2404:e80:a137:104::1
domain=wifi.welland.mithis.com,10.1.4.0/24
auth-zone=wifi.welland.mithis.com

# NO dhcp-range on purpose; belt-and-braces:
no-dhcp-interface=br-wifi
```

- [x] **Step 1:** Install `network-04-wifi.conf`; remove
  `network-04-wifi-IGNORED.conf`; restore `03-zone-forwarders.conf` to its
  monarto-only content.
- [x] **Step 2:** Update `/etc/dnsmasq.d/README`: directory-layout entry for
  `network-04-wifi.conf` describing the split-role VLAN (keep the existing
  comment style; drop any wifi zone-forward mention).
- [x] **Step 3:** Syntax check: `sudo dnsmasq --test -C /etc/dnsmasq.d/dnsmasq.internal.conf`
  → `syntax check OK`.
- [x] **Step 4:** `sudo systemctl restart dnsmasq@internal` then verify:
  `dig @127.0.0.1 google.com` still resolves (instance healthy);
  `dig @10.1.4.1 google.com` from the desktop resolves (DNS served on
  br-wifi — pucks' resolver works); `dig @10.1.4.1 ten64.welland.mithis.com`
  resolves (local data reachable via that listener).
- [x] **Step 5:** Verify NO DHCP on br-wifi: `sudo ss -ulpn | grep ':67'` on
  ten64 → dnsmasq's :67 sockets exist (other VLANs) but a DHCPDISCOVER on
  br-wifi gets no answer — full proof comes at Task 7.1 (ten64 journal shows
  nothing for the puck MACs); here confirm `no-dhcp-interface=br-wifi` is
  loaded via config dump: `sudo dnsmasq --test -C /etc/dnsmasq.d/dnsmasq.internal.conf`
  passing plus the file being in conf-dir is sufficient.
- [x] **Step 6:** Puck names resolve only after Phase 3 lands the generated
  host-records — `dig @10.1.4.1 puck12.wifi.welland.mithis.com` returning
  NXDOMAIN now is expected; re-check in Task 5.7.

---

## Phase 2 — wisp VM migration (VLAN 5 → VLAN 4)

### Task 2.1: Pre-move audit

- [x] **Step 1:** On wisp, hunt hardcoded 10.1.5.2 / old-VLAN assumptions:
  `ssh wisp.welland.mithis.com 'sudo grep -rn "10\.1\.5\.2" /etc /opt /home/tim --include="*" -l 2>&1 | grep -v Binary'`
  and check OpenWISP settings (`~/openwisp/`, supervisor configs, influxdb,
  nginx vhosts). Record findings; anything binding or advertising 10.1.5.2
  must be listed for fix-up in Step 2 of Task 2.4.
- [x] **Step 2:** Identify the LE cert renewal path:
  `ssh wisp.welland.mithis.com 'sudo ls /etc/letsencrypt/renewal/ && sudo cat /etc/letsencrypt/renewal/*.conf'`
  → note authenticator (HTTP-01 via nginx vs DNS-01). If HTTP-01: renewal
  needs port 80 reachable at whatever IP `wisp.welland.mithis.com` resolves to
  — fine after the DNS record moves (Task 2.4), but confirm the ACME server
  reaches it (external DNS!). Check ten64's *external* dnsmasq: does
  `wisp.welland.mithis.com` have a public record / port-forward? If the cert
  was issued via DNS-01 (certbot-hook-dnsmasq), nothing IP-related matters.
  **Record the answer in the runbook.** If HTTP-01 AND publicly port-forwarded
  to 10.1.5.2, the forward must be retargeted to 10.1.4.2 — add to Task 2.4.
- [x] **Step 3:** Snapshot rollback data: `sudo virsh dumpxml wisp > tmp/wisp-pre-move.xml`
  (on ten64, copy home); note current netplan yaml content (already captured:
  match `02:00:0a:01:05:02`, dhcp4, set-name net0).

### Task 2.2: Stage the guest's static network config (before the retarget)

**Files (on wisp, root):**
- Create: `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg`
- Replace: `/etc/netplan/50-cloud-init.yaml`

- [x] **Step 1:** Prevent cloud-init from regenerating network config:
  ```yaml
  # /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
  network: {config: disabled}
  ```
- [x] **Step 2:** Replace `/etc/netplan/50-cloud-init.yaml` (mode 0600 — netplan
  warns on world-readable):
  ```yaml
  # Static config — wisp lives on VLAN 4 (wifi, 10.1.4.0/24) and is itself
  # the DHCP server there; no DHCP client possible (chicken-and-egg).
  # See gwifi-openwrt docs/wisp-netboot-install-design.md (D6).
  network:
    version: 2
    ethernets:
      net0:
        match:
          macaddress: "02:00:0a:01:04:02"
        set-name: "net0"
        dhcp4: false
        addresses:
          - 10.1.4.2/24
          - 2404:e80:a137:104::2/64
        routes:
          - to: default
            via: 10.1.4.1
          - to: default
            via: 2404:e80:a137:104::1
        nameservers:
          addresses: [10.1.4.1]
  ```
  (Resolver = ten64's internal dnsmasq on br-wifi itself — D7; it serves DNS
  on 10.1.4.1 as of Task 1.3, on-link, no routed-query caveats.)
- [x] **Step 3:** `sudo netplan generate` → no errors (config is staged but the
  new MAC doesn't exist yet, so nothing changes at runtime). Do **not**
  `netplan apply`.

### Task 2.3: Retarget the libvirt NIC ⚠ STOP-AND-CONFIRM

OpenWISP goes down for the duration (~1 min). Confirm with the user before
starting. Console recovery path: `ssh ten64.welland.mithis.com` →
`sudo virsh console wisp` (serial getty on ttyAMA0 is enabled).

- [x] **Step 1:** `sudo virsh shutdown wisp` and poll `sudo virsh list --all`
  until `shut off` (≤60 s; if stuck, investigate before forcing).
- [x] **Step 2:** Edit the persistent XML — replace in the `<interface
  type='bridge'>` block: `<source bridge='br-net'/>` → `br-wifi`, and
  `<mac address='02:00:0a:01:05:02'/>` → `02:00:0a:01:04:02`. Non-interactive:
  ```sh
  sudo virsh dumpxml --inactive wisp > /tmp/wisp.xml   # ten64: /tmp fine
  # python one-liner or sed for the two exact strings, then:
  sudo virsh define /tmp/wisp.xml
  sudo virsh dumpxml --inactive wisp | grep -A3 "interface type='bridge'"  # verify both edits
  ```
- [x] **Step 3:** `sudo virsh start wisp`.
- [x] **Step 4:** Gate checks (from desktop):
  - `ping -c2 10.1.4.2` OK; `ssh tim@10.1.4.2 hostname` → `wisp.welland.mithis.com`
  - guest: `ip -br addr show net0` → `10.1.4.2/24` + v6; `ip route` → default via 10.1.4.1
  - resolver: `resolvectl query google.com` on wisp succeeds (on-link query
    to ten64's br-wifi listener at 10.1.4.1 — D7)
  - OpenWISP: `curl -sk https://10.1.4.2/ -o /dev/null -w '%{http_code}'` →
    200/302 (cert name mismatch by-IP is fine here; full check in Task 2.4)
- [x] **Step 5:** If any gate fails and can't be fixed within the session:
  rollback = shutdown, `virsh define` the saved pre-move XML, restore the
  original netplan yaml, start, verify 10.1.5.2 works again.

### Task 2.4: Move the DNS record + re-verify service

- [x] **Step 1:** Update wisp's row in the `Welland - IP Allocation` sheet tab
  (gid 1476589425): VLAN/network `net` → `wifi`, IP `10.1.5.2` → `10.1.4.2`.
  Reuse the Task 1.1 script pattern (find the row by hostname `wisp`, update
  the VLAN + IP cells via `values:update`). Read the tab's header row first to
  find the exact columns — do not guess.
- [x] **Step 2:** Regenerate + deploy on ten64 (documented procedure):
  ```sh
  ssh ten64.welland.mithis.com 'cd /opt/gdoc2netcfg && uv run gdoc2netcfg fetch && uv run gdoc2netcfg generate --force'
  # then the README copy steps for internal/generated + external/generated
  # and: sudo systemctl restart dnsmasq@internal dnsmasq@external
  ```
- [x] **Step 3:** Verify: `dig wisp.welland.mithis.com @10.1.5.1` → `10.1.4.2`;
  AAAA → `2404:e80:a137:104::2`. From desktop:
  `curl -s https://wisp.welland.mithis.com/ -o /dev/null -w '%{http_code}'` →
  200/302 with **valid cert** (v4 and v6: `curl -4` and `curl -6`).
- [x] **Step 4:** Fix anything the Task 2.1 audit flagged (old-IP references,
  port-forward retarget). Re-run a certbot dry-run if the renewal path was
  HTTP-01: `sudo certbot renew --dry-run`.
- [x] **Step 5:** Update the memory/runbook notes: wisp is now 10.1.4.2.

---

## Phase 3 — gdoc2netcfg `gwifi_pucks` generator

Work in a fresh local clone (repo lives on GitHub; ten64's checkout is the
deploy target, `/opt/gdoc2netcfg` is the production copy):

### Task 3.1: Clone + branch + baseline

- [ ] **Step 1:** `git clone git@github.com:mithro/gdoc2netcfg.git /home/tim/local/gwifi/gdoc2netcfg && cd /home/tim/local/gwifi/gdoc2netcfg && git checkout -b gwifi-pucks-generator`
  (This is a dedicated clone+branch — satisfies the branch/worktree rule.)
- [ ] **Step 2:** `uv sync` then baseline: `uv run pytest -q`. Expected: all
  pass. Record the count. Read `CLAUDE.md` and `docs/architecture.md` for
  repo-specific conventions before writing code.
- [ ] **Step 3:** Read these files to mimic patterns (do not skip):
  `src/gdoc2netcfg/sources/sheets.py` (fetch+cache), `sources/vlan_parser.py`
  (tab parser style), `generators/nagios.py` (simple generator),
  `cli/main.py:580-700` (generator registry + config wiring),
  `config.py` (toml schema), `tests/test_generators/` + `tests/fixtures/`
  (test style + fixture CSVs).

### Task 3.2: Pucks-tab source parser (TDD)

**Files:**
- Create: `src/gdoc2netcfg/sources/gwifi_pucks_parser.py`,
  `tests/test_sources/test_gwifi_pucks_parser.py`,
  `tests/fixtures/gwifi_pucks.csv`
- Modify: `gdoc2netcfg.toml.example` (`[sheets] gwifi_pucks = "…gid=210946497…"`)

Parser contract — `parse_gwifi_pucks(csv_text: str) -> list[PuckRecord]` where
`PuckRecord` is a frozen dataclass: `number: int`, `name: str` (`puck%02d`),
`serial: str`, `eth0: str`, `eth1: str` (colon-format, upper), `ip: str`
(`10.1.4.{100+number}`). Rules (spec §5.3):
- Only rows with `Firmware == "OpenWRT"` **and** non-empty Serial **and** MAC.
- Duplicate serials → `ValueError` (spec §5.3 constraints; test this alongside
  duplicate numbers).
- `eth0` column used when present, else the `MAC` column (they are the same
  device label MAC); `eth1` used when present, else derived `eth0 + 1` (the
  fleet-verified pattern; wrap within the last octet is an error → raise).
- `number` > 99 or duplicate `number` → `ValueError` (IP scheme breaks).

- [ ] **Step 1:** Write `tests/fixtures/gwifi_pucks.csv` — copy the real
  header + rows 1 (Google Original — excluded), 3 (empty serial — excluded),
  4 (full row incl. eth0/eth1), 5 (OpenWRT, MAC only — eth1 derived), 12.
- [ ] **Step 2:** Write the failing tests: filtering, name/ip derivation,
  eth1 derivation (`24:05:88:39:8A:08` → `24:05:88:39:8A:09`), duplicate
  number raises, number>99 raises, MAC normalization.
- [ ] **Step 3:** `uv run pytest tests/test_sources/test_gwifi_pucks_parser.py -v`
  → FAIL (module missing).
- [ ] **Step 4:** Implement the parser (mimic `vlan_parser.py` csv handling).
- [ ] **Step 5:** Tests pass; whole suite still green; commit
  (`feat(sources): parse Google WiFi Pucks tab into PuckRecords`).

### Task 3.3: Constraint — puck MACs vs. network inventory (TDD)

**Files:**
- Create: `src/gdoc2netcfg/constraints/gwifi_pucks_validation.py` + test file
  mirroring `tests/test_constraints/` style.

Contract: fail validation if any puck MAC collides with a MAC already present
in `NetworkInventory` (hosts data), or with another puck. Wire into the
constraints stage the same way existing validators register (read
`constraints/__init__.py` / `validators.py` for the mechanism).

- [ ] Steps: failing test (collision + clean cases) → run → implement →
  suite green → commit.

### Task 3.4: `gwifi_pucks` generator + CLI wiring (TDD)

**Files:**
- Create: `src/gdoc2netcfg/generators/gwifi_pucks.py`,
  `tests/test_generators/test_gwifi_pucks.py`
- Modify: `cli/main.py` (registry entry `"gwifi_pucks": ("gdoc2netcfg.generators.gwifi_pucks", "generate_gwifi_pucks")`),
  `gdoc2netcfg.toml.example` (`[generators.gwifi_pucks] output_dir = "wisp"`,
  and add to the `enabled` comment), `README.md` (procedure: scp step).

Output contract — `generate_gwifi_pucks(pucks: list[PuckRecord]) -> str`:
deterministic JSON (sorted by number, 2-space indent, trailing newline):
```json
{
  "version": 1,
  "generated_by": "gdoc2netcfg",
  "pucks": [
    {"name": "puck04", "number": 4, "serial": "2831HW00VZA",
     "eth0": "44:07:0B:01:87:B4", "eth1": "44:07:0B:01:87:B5",
     "ip": "10.1.4.104"}
  ]
}
```
(No timestamp inside the JSON — deterministic output means clean diffs and
idempotent deploys.) File written as `pucks.json` in the `wisp` output dir —
follow how other generators name their output files in `cmd_generate`.

**Second output (D7)** — `generate_gwifi_pucks_dns(pucks) -> str`, registered
as generator `gwifi_pucks_dns` with `output_dir = "internal"` so it lands in
ten64's `internal/generated/` via the normal copy procedure; file
`gwifi-pucks-dns.conf`:
```ini
# Generated by gdoc2netcfg gwifi_pucks_dns — puck names for the wifi VLAN.
# host-record provides A + PTR. DHCP for these devices lives on wisp
# (see gwifi-openwrt docs/wisp-netboot-install-design.md D7).
host-record=puck04.wifi.welland.mithis.com,10.1.4.104
```
(one line per puck, sorted by number; same header comment style as other
generated dnsmasq fragments).

- [ ] Steps: failing tests for BOTH outputs (golden JSON + golden dnsmasq
  fragment for fixture rows, determinism = byte-identical on second call) →
  run → implement → wire CLI + toml (two registry entries) → test
  `uv run gdoc2netcfg generate --stdout gwifi_pucks` and
  `--stdout gwifi_pucks_dns` against the live sheet → suite green → commit.

### Task 3.5: Deploy to ten64 + push

- [ ] **Step 1:** Push branch; open PR (`gh pr create`) titled
  "sources+generators: gwifi pucks identity for wisp netboot". Merge per
  user's normal flow (ask if unsure whether to self-merge).
- [ ] **Step 2:** On ten64: update `/opt/gdoc2netcfg` (git pull after merge),
  add `[sheets] gwifi_pucks` + `[generators.gwifi_pucks]` to the untracked
  `/opt/gdoc2netcfg/gdoc2netcfg.toml`, run fetch + generate, confirm
  `wisp/pucks.json` appears and contains the OpenWRT pucks.
- [ ] **Step 3:** Extend the documented update procedure (the `/etc/dnsmasq.d/README`
  block from Task 1.3 + gdoc2netcfg README): add
  `scp wisp/pucks.json wisp.welland.mithis.com:/tmp/pucks.json && ssh wisp.welland.mithis.com 'sudo install -m 0644 /tmp/pucks.json /etc/gwifi-netboot/pucks.json && sudo systemctl restart gwifi-netboot'`
  (path unit alternative rejected for simplicity — explicit restart is the
  documented procedure's style). Note: target dir exists after Phase 5 deploy.

---

## Phase 4 — wisp base services (dnsmasq + nginx + dirs)

### Task 4.1: dnsmasq on wisp

**Files (on wisp, root):**
- Create: `/etc/dnsmasq.d/gwifi.conf`, dir `/etc/dnsmasq.d/gwifi-generated/`,
  dirs `/srv/gwifi/tftp`, `/srv/gwifi/images`

- [x] **Step 1:** `sudo apt-get install -y dnsmasq` — Debian starts it
  immediately with defaults (listens on *:53 → conflicts with
  systemd-resolved's 127.0.0.53 stub only if it binds wildcard). Install with
  it masked first:
  ```sh
  sudo systemctl mask dnsmasq && sudo apt-get install -y dnsmasq
  ```
- [x] **Step 2:** Write `/etc/dnsmasq.d/gwifi.conf` (**DHCP+TFTP only, no
  DNS — D7**; ten64 at 10.1.4.1 is the VLAN's DNS server and resolver):
  ```ini
  # gale puck netboot — wisp serves DHCP + TFTP on VLAN 4 ONLY; DNS and
  # routing are ten64's (10.1.4.1). See gwifi-openwrt
  # docs/wisp-netboot-install-design.md (D7).
  port=0
  # ^ no DNS at all: never shadows systemd-resolved, never answers :53.
  bind-dynamic
  interface=net0

  # DHCP — .3-.99 reserved static/infra, .100-.199 pucks (fixed via
  # dhcp-host from gwifi-generated/) + dynamic fallback for unknown gale
  dhcp-range=10.1.4.100,10.1.4.199,255.255.255.0,1h
  dhcp-authoritative
  dhcp-rapid-commit
  dhcp-option=option:router,10.1.4.1
  dhcp-option=option:dns-server,10.1.4.1
  log-dhcp

  # TFTP for the installer FIT
  enable-tftp
  tftp-root=/srv/gwifi/tftp

  # Per-puck identity + arming state — owned by gwifi-netboot, never edit
  conf-dir=/etc/dnsmasq.d/gwifi-generated
  ```
  Note `/etc/dnsmasq.conf` default includes `/etc/dnsmasq.d`; verify
  (`grep conf-dir /etc/dnsmasq.conf`) — Debian ships `conf-dir=/etc/dnsmasq.d/,*.conf`
  which does NOT recurse into `gwifi-generated/` — hence the explicit
  `conf-dir=` line above. Create `/etc/dnsmasq.d/gwifi-generated/` with a
  placeholder `pucks.conf` containing only a comment header.
- [x] **Step 3:** (Removed by D7 — `port=0` eliminates all DNS/resolved
  interaction; no resolv-file needed since dnsmasq never resolves.)
- [x] **Step 4:** `sudo dnsmasq --test` → OK. `sudo systemctl unmask dnsmasq && sudo systemctl enable --now dnsmasq`.
- [x] **Step 5:** Verify: `sudo ss -ulpn | grep -E ':53|:67|:69'` → dnsmasq on
  :67/:69 only (no :53 anywhere); `resolvectl query google.com` still works
  (resolved untouched); from desktop `dig @10.1.4.1 google.com` works (ten64
  is the VLAN DNS — established in Task 1.3).
- [x] **Step 6:** TFTP smoke: `echo hi | sudo tee /srv/gwifi/tftp/probe.txt`,
  from desktop `curl -s tftp://10.1.4.2/probe.txt` → `hi`; remove probe.

### Task 4.2: nginx images vhost

> **Revised during execution:** implemented with a dedicated
> `server_name 10.1.4.2` on the shared wildcard :80 socket instead of
> `default_server` — the vhost file already carries catch-all
> `default_server` blocks, and the OpenWISP vhost had gained the bare IP as
> a server_name alias (from the 10.1.5.2 fix-up), which would have swallowed
> installer requests. The bare-IP alias was removed from the OpenWISP vhost;
> invariant verified: by-IP :80 -> images, by-name -> OpenWISP (200).

**Files (on wisp, root):** Create `/etc/nginx/sites-available/gwifi-images` +
symlink in `sites-enabled`.

```nginx
# Serves /srv/gwifi/images (factory.bin, manifest.json) to netbooted
# installers, which fetch by IP literal — hence default_server (D6: this
# socket is shared with the OpenWISP vhost).
server {
    listen 10.1.4.2:80 default_server;
    server_name _;
    root /srv/gwifi/images;
    autoindex off;
    add_header Cache-Control "no-cache";
    location / { try_files $uri =404; }
}
```

- [x] **Step 1:** Check the existing OpenWISP vhost's `listen` directives
  (`sudo nginx -T | grep -n listen`). If it has a bare `listen 80
  default_server`, the new block conflicts (duplicate default_server on the
  same addr:port set) — resolve by keeping OpenWISP's port-80 role for ACME
  (`/.well-known/acme-challenge/`) as a **location in the gwifi block**
  proxying/aliasing to the ACME webroot, or scope OpenWISP's port-80 listen
  to `server_name wisp.welland.mithis.com` without default_server. Decide
  from what's actually there; the invariant to preserve: **IP-literal
  requests land in the images block; ACME HTTP-01 for
  wisp.welland.mithis.com still works** (if renewal is HTTP-01 per Task 2.1).
- [x] **Step 2:** Install, `sudo nginx -t`, `sudo systemctl reload nginx`.
- [x] **Step 3:** Verify: `echo test | sudo tee /srv/gwifi/images/probe.txt`;
  from desktop `curl -s http://10.1.4.2/probe.txt` → `test`;
  `curl -s https://wisp.welland.mithis.com/` still OpenWISP. Remove probe.

---

## Phase 5 — `gwifi-netboot` service (in this repo)

All code under `tools/gwifi-netboot/` in the `wisp-netboot-install` worktree.
Mimic the `tools/fleet/` layout (pyproject.toml + uv.lock + package dir +
tests/) — that directory is on the `fleet-firmware-flash` branch only; read it
at `/home/tim/local/gwifi/gwifi-openwrt/.worktrees/fleet-firmware-flash/tools/fleet/`.
Stack: pure stdlib (`http.server`, `json`, `argparse`, `subprocess`) + pytest;
no framework — the API is 3 endpoints.

**File map:**
```
tools/gwifi-netboot/
  pyproject.toml            # name gwifi-netboot, requires-python >=3.11, pytest dev-dep
  gwifi_netboot/
    __init__.py
    identity.py             # load/validate pucks.json → Puck objects
    state.py                # state.json load/save/arm/disarm/record_event (atomic writes)
    render.py               # (identity, state) → dnsmasq fragment text
    dnsmasqctl.py           # --test gate + systemctl reload wrapper (injectable runner)
    httpd.py                # GET /manifest, GET /status, POST /phone-home
    cli.py                  # status | arm | disarm | render | serve
  systemd/
    gwifi-netboot.service   # runs `cli.py serve` as root (needs dnsmasq reload)
  deploy.sh                 # rsync tool → wisp:/opt/gwifi-netboot + install units
  tests/
    test_identity.py test_state.py test_render.py test_httpd.py test_cli.py
    fixtures/pucks.json
```

**Key behavioral contracts (from spec §5.4 — encode in tests):**
- Render: exactly one `dhcp-host=` line per puck:
  `dhcp-host=<eth0>,<eth1>,<ip>,<name>` unarmed;
  `…,<name>,set:install` armed. One global
  `dhcp-boot=tag:install,gale-installer.itb` line **only if ≥1 puck armed**.
  Header comment says "generated — do not edit". Deterministic ordering.
- State transitions: `phone-home(success|already-current)` → disarm + record;
  `phone-home(failed)` → record only, stays armed. Unknown MAC → record under
  `unknown/<mac>`, no crash, flagged in `status`.
- Reload path: write fragment to temp file → `dnsmasq --test` on a config
  snippet check (`dnsmasq --test --conf-file=<fragment>` accepts a fragment) →
  atomic rename into `/etc/dnsmasq.d/gwifi-generated/pucks.conf` →
  `systemctl reload dnsmasq` (dnsmasq re-reads dhcp-host files on SIGHUP?
  **No** — SIGHUP re-reads /etc/hosts + dhcp-hostsfile but NOT conf-dir. So:
  `systemctl restart dnsmasq`. Encode `restart`, not `reload`. Alternative
  `dhcp-hostsdir=` supports live adds but not removals/edits — restart is the
  only correct primitive here; it's a sub-second daemon).
- `serve` binds `10.1.4.2:8080` (configurable `--bind` for tests: 127.0.0.1:0).

### Task 5.1: Scaffold + identity module (TDD)
- [x] Failing tests: valid fixture loads (names/ips/macs), version≠1 rejected,
  duplicate MAC rejected, MACs normalized lowercase for dnsmasq. → implement
  `identity.py` → green → commit.

### Task 5.2: State module (TDD)
- [x] Failing tests: fresh state file auto-created; arm/disarm idempotent;
  phone-home transitions per contract above; unknown MAC path; atomic write
  (tmp+rename, survives simulated crash = no partial file); bounded history
  (keep last 20 events/puck). → implement `state.py` → green → commit.

### Task 5.3: Renderer (TDD, golden test)
- [x] Failing tests: golden fragment for fixture (2 pucks, one armed);
  no-armed → no dhcp-boot line; byte-determinism. → implement `render.py` →
  green → commit.

### Task 5.4: dnsmasqctl (TDD with injected runner)
- [x] Failing tests: happy path calls `dnsmasq --test` then atomic install
  then `systemctl restart dnsmasq`; --test failure → no install, no restart,
  raises; runner injected as callable so tests never exec real commands. →
  implement → green → commit.

### Task 5.5: HTTP API (TDD against a live 127.0.0.1 server thread)
- [x] Failing tests: `GET /manifest` returns the manifest file bytes
  (404 when absent); `GET /status` JSON merges identity+state;
  `POST /phone-home` happy/failed/unknown-mac per contract, triggers
  render+restart via injected dnsmasqctl, malformed JSON → 400.
  Also verify (here or at latest in the pilot) that `uclient-fetch` exits
  nonzero on HTTP 4xx/5xx — the installer's "non-200 = delivery failure,
  stay up" behavior depends on that exit-code mapping; if it doesn't, the
  installer must check the response body instead.
  Wire-compat details the installer relies on: the body is parsed as JSON
  **regardless of Content-Type** (`uclient-fetch --post-data` sends
  `application/x-www-form-urlencoded`), and response codes are pinned —
  200 for recorded results **including unknown-MAC** (the installer treats
  non-200 as delivery failure and stays up; an unknown MAC is a server-side
  bookkeeping event, not an installer error), 400 only for undecodable
  bodies/missing fields. → implement `httpd.py` (ThreadingHTTPServer) →
  green → commit.

### Task 5.6: CLI + systemd unit + deploy
- [x] Failing tests for CLI arg handling (arm/disarm/status/render call the
  right functions; `render --check` exits nonzero on invalid identity file).
  → implement `cli.py` → green → commit.
- [x] Write `systemd/gwifi-netboot.service`:
  ```ini
  [Unit]
  Description=gwifi puck netboot state + phone-home API
  After=network-online.target dnsmasq.service
  Wants=network-online.target

  [Service]
  Type=simple
  ExecStart=/usr/bin/uv run --project /opt/gwifi-netboot python -m gwifi_netboot.cli serve
  Restart=on-failure
  # root: writes /etc/dnsmasq.d/gwifi-generated + systemctl restart dnsmasq
  User=root

  [Install]
  WantedBy=multi-user.target
  ```
  (Verify `uv` exists on wisp — `ssh wisp which uv`; if absent, deploy.sh
  installs it or the unit uses a venv made by deploy.sh. Decide at deploy,
  record in runbook.)
- [x] Write `deploy.sh` (idempotent: rsync `tools/gwifi-netboot/` →
  `wisp:/opt/gwifi-netboot`, install unit, `systemctl daemon-reload`,
  `enable --now`, then `curl -s http://10.1.4.2:8080/status` smoke).
- [x] Run deploy; smoke-test `status` (empty identity OK until Phase 3 lands);
  commit.

### Task 5.7: End-to-end config integration on wisp

> **Execution notes:** wisp has no `uv`; the tool is pure stdlib so the unit
> runs `/usr/bin/python3 -m gwifi_netboot.cli serve` from
> `WorkingDirectory=/opt/gwifi-netboot` (no venv). `deploy.py` (python, not
> deploy.sh) stages via $HOME + sudo rsync (rsync had to be apt-installed on
> wisp). Identity was hand-deployed from a local generate pending the
> gdoc2netcfg PR #14 merge; the `dig @10.1.4.1 puck12...` check re-runs after
> the merge lands the ten64 host-records (tracked in Task 3.5).
- [x] Deploy real `pucks.json` (Task 3.5 output). `gwifi-netboot status`
  lists all OpenWRT pucks, none armed. Inspect
  `/etc/dnsmasq.d/gwifi-generated/pucks.conf` — dhcp-host lines present, no
  dhcp-boot. DNS (D7 — served by ten64 from the Phase-3 generated
  host-records): `dig @10.1.4.1 puck12.wifi.welland.mithis.com` → 10.1.4.112
  and `dig -x 10.1.4.112 @10.1.4.1` → puck12 name; from desktop plain
  `dig puck12.wifi.welland.mithis.com` resolves too.

---

## Phase 6 — Installer image + publish pipeline

### Task 6.1: `publish_gale_image.py` (TDD)

**Files:** `tools/gwifi-netboot/gwifi_netboot/publish.py`, CLI hook
`cli.py publish`, tests.

Contract: `publish(factory_bin: Path, images_dir: Path, image_id_file: Path|None)` —
computes sha256 + size; **`image_id` comes from the sidecar file**
`<factory.bin>.image-id` written by the image build (Task 6.2 bakes the same
id into `/etc/gwifi-image-id`, so manifest and on-eMMC marker always match) —
`image_id_file` defaults to that sidecar path and a missing sidecar is an
error; copies factory.bin into images_dir under a content-addressed name
`factory-<sha12>.bin`; atomically writes `manifest.json`:
```json
{"version": 1, "image_id": "gale-openwrt-abc123def456",
 "filename": "factory-abc123def456.bin",
 "sha256": "<full>", "size": 123456789, "force": []}
```
- [x] Failing tests (tmpdir images dir; atomicity = old manifest intact if
  copy interrupted — write manifest last) → implement → green → commit.

### Task 6.2: Bake `/etc/gwifi-image-id` into the production factory image

**Files:** Modify `gale-image/build-gale-image.sh` (+ its `files/` overlay
handling), `gale-image/README.md`.

- [x] **Step 1:** Read `gale-image/build-gale-image.sh` and `gale.config`
  to learn the overlay mechanism (it stages `files/` into the OpenWrt build).
- [x] **Step 2:** Stamp a **build id** (the image's own sha can't be baked
  into itself): the build writes
  `gale-openwrt-$(date -u +%Y%m%d%H%M%S)-g$(git rev-parse --short HEAD)`
  to `files/etc/gwifi-image-id` AND emits it as `<factory.bin>.image-id`
  next to the artifact; `publish` reads that sidecar (Task 6.1's contract)
  so manifest and baked marker always match.
- [x] **Step 3:** Rebuild the factory image (long: run in background, log,
  progress every 60 s). Verify the marker is inside:
  `openwrt/build_dir/...` or extract from the built squashfs
  (`unsquashfs -cat <rootfs> etc/gwifi-image-id`). Commit build-script change.

### Task 6.3: Installer overlay + build

**Files:**
- Create: `gale-installer/files/etc/uci-defaults/99-gale-autoinstall` (or
  init.d — see below), `gale-installer/files/usr/sbin/gale-autoinstall`,
  `gale-installer/installer.config` (config frag), `gale-installer/build-installer.sh`,
  `gale-installer/README.md`

The installer is the **initramfs** image (RAM-only) with an auto-run script.
Use an `/etc/init.d/gale-autoinstall` (START=99, `boot()` backgrounds
`/usr/sbin/gale-autoinstall > /dev/console 2>&1`) rather than uci-defaults
(uci-defaults is for config migration and runs before network is fully up;
init.d at 99 runs after netifd).

`/usr/sbin/gale-autoinstall` (complete logic; POSIX sh, busybox-safe):
```sh
#!/bin/sh
# gale eMMC auto-installer — see gwifi-openwrt docs/wisp-netboot-install-design.md §5.5
# Runs from the netbooted initramfs. Judge results via phone-home; serial
# console (ttyMSM0) shows progress. Any failure => report + STAY UP.

log() { echo "gale-autoinstall: $*"; }

SERVER=$(sed -n 's/.*tftpserverip=\([0-9.]*\).*/\1/p' /proc/cmdline)
[ -n "$SERVER" ] || { log "no tftpserverip in cmdline; aborting"; exit 1; }
API="http://$SERVER:8080"

# Guarded reads: NEVER `VAR=$(cat f 2>&1 || fallback)` — that captures the
# error text into VAR when f is missing. Test readability first instead
# (keeps the no-2>/dev/null convention AND clean values).
MAC=""
for f in /sys/class/net/wan/address /sys/class/net/eth0/address; do
    [ -r "$f" ] && MAC=$(cat "$f") && break
done
[ -n "$MAC" ] || { log "no MAC readable"; exit 1; }
SERIAL=unknown
# device-tree serial-number is NUL-terminated; tr strips it (busybox has no
# strings applet)
[ -r /proc/device-tree/serial-number ] \
    && SERIAL=$(tr -d '\0' < /proc/device-tree/serial-number)

phone_home() {  # $1=result $2=detail $3=image_id
    uclient-fetch -q -O - --post-data \
      "{\"serial\":\"$SERIAL\",\"mac\":\"$MAC\",\"result\":\"$1\",\"detail\":\"$2\",\"image_id\":\"$3\"}" \
      "$API/phone-home"
}

wait_net() {  # wan comes up via DHCP (default OpenWrt initramfs behavior)
    for i in $(seq 1 30); do
        ip -4 addr show 2>&1 | grep -q "10\.1\.4\." && return 0
        sleep 2
    done
    # last resort: force a dhcp client on whichever port has carrier
    for dev in eth0 eth1 wan lan; do udhcpc -n -q -i "$dev" 2>&1 && return 0; done
    return 1
}

wait_net || { log "no network"; exit 1; }

MANIFEST=$(uclient-fetch -q -O - "$API/manifest") || { log "manifest fetch failed"; exit 1; }
# busybox-safe JSON field extraction (flat manifest, no jq in image)
jfield() { echo "$MANIFEST" | sed -n "s/.*\"$1\":\s*\"\{0,1\}\([^\",}]*\)\"\{0,1\}.*/\1/p"; }
IMAGE_ID=$(jfield image_id); FILENAME=$(jfield filename); SHA=$(jfield sha256)
[ -n "$IMAGE_ID" ] && [ -n "$FILENAME" ] && [ -n "$SHA" ] || { log "bad manifest"; exit 1; }

# Idempotence: read the installed marker (spec §5.5 step 2)
CURRENT=""
mkdir -p /tmp/p2
if mount -o ro /dev/mmcblk0p2 /tmp/p2; then
    [ -r /tmp/p2/etc/gwifi-image-id ] && CURRENT=$(cat /tmp/p2/etc/gwifi-image-id)
    umount /tmp/p2          # nothing may hold the device during dd
fi
# NOTE: matches the MAC anywhere in the manifest body, not just the "force"
# array — safe ONLY because publish.py fully controls the flat manifest and
# no other field may contain MAC text. Revisit if the manifest grows fields.
FORCE=$(echo "$MANIFEST" | grep -io "\"$MAC\"" || true)
if [ "$CURRENT" = "$IMAGE_ID" ] && [ -z "$FORCE" ]; then
    log "already current ($IMAGE_ID)"
    phone_home already-current "marker match" "$IMAGE_ID" || { log "phone-home unreachable; staying up"; exit 1; }
    reboot; exit 0
fi

log "installing $IMAGE_ID (was: ${CURRENT:-none})"
uclient-fetch -q -O /tmp/factory.bin "http://$SERVER/$FILENAME" \
    || { phone_home failed "image fetch"; exit 1; }
GOT=$(sha256sum /tmp/factory.bin | cut -d' ' -f1)
[ "$GOT" = "$SHA" ] || { phone_home failed "sha256 mismatch $GOT" "$IMAGE_ID"; exit 1; }

dd if=/tmp/factory.bin of=/dev/mmcblk0 bs=4M conv=fsync \
    || { phone_home failed "dd write" "$IMAGE_ID"; exit 1; }
sync; partx -u /dev/mmcblk0 2>&1 || true

mount -o ro /dev/mmcblk0p2 /tmp/p2 || { phone_home failed "post-flash mount" "$IMAGE_ID"; exit 1; }
VERIFY=""
[ -r /tmp/p2/etc/gwifi-image-id ] && VERIFY=$(cat /tmp/p2/etc/gwifi-image-id)
umount /tmp/p2
[ "$VERIFY" = "$IMAGE_ID" ] || { phone_home failed "post-flash marker '$VERIFY'" "$IMAGE_ID"; exit 1; }

phone_home success "flashed+verified" "$IMAGE_ID" || { log "flashed OK but phone-home unreachable; staying up"; exit 1; }
log "success — rebooting to eMMC"
reboot
```
(Note the two deliberate stay-up-on-phone-home-failure paths — spec §5.5/§6.
`sed`/`grep` JSON parsing is acceptable because *we* control the flat manifest
format; document that constraint in `publish.py`.)

- [x] **Step 1:** Write files above. RAM check (spec open item): initramfs
  OpenWrt on gale has ~410 MiB free in /tmp (512 MiB RAM − ~100 MiB
  kernel+rootfs); factory.bin ≈ 40–60 MiB → comfortably fits. Verify the
  actual numbers during the pilot and record.
- [x] **Step 2:** `build-installer.sh`: reuse the netboot build (config +
  `openwrt-patches/0001-…-emit-raw-netboot-fit.patch` already applied in
  `/home/tim/local/gwifi/openwrt`) with `FILES=<abs path>/gale-installer/files`
  make override producing `…initramfs-fit-zImage.itb`; copy out as
  `gale-installer-<buildid>.itb` + stable symlink name `gale-installer.itb`.
  Long build → background + log + progress.
- [x] **Step 3:** Sanity: `xxd -l4 gale-installer.itb` → `d00dfeed` (raw FIT,
  NOT `.itb.vboot`); confirm the overlay is inside
  (`dumpimage -l` shows the FIT; extract initramfs is awkward — instead
  verify via build tree `build_dir/target-*/root-ipq40xx/usr/sbin/gale-autoinstall`).
- [x] **Step 4:** Commit (`gale-installer/` scripts; the .itb itself is a
  build artifact — gitignored like other bins).

### Task 6.4: Stage artifacts on wisp

- [x] **Step 1:** `uv run … cli.py publish <factory.bin>` output staged
  locally, then rsync `/srv/gwifi/images/` (manifest + factory-<sha>.bin) and
  `scp gale-installer.itb wisp:/srv/gwifi/tftp/gale-installer.itb`.
  Fold both into `deploy.sh` as a `--artifacts` mode.
- [x] **Step 2:** Verify from desktop: `curl http://10.1.4.2/manifest.json`
  (wait — manifest is served by nginx from images/ root: URL is
  `http://10.1.4.2/manifest.json`, while the API serves `GET /manifest` on
  :8080 by reading the same file. Both must return identical bytes; the
  installer uses the :8080 one per spec) and
  `curl -s tftp://10.1.4.2/gale-installer.itb | xxd -l4` → `d00dfeed`.

---

## Phase 7 — Pilot validation (puck 12 / WGD, s1 port 46) — spec §8

Wire-judged (console capture is mute). All dnsmasq observations via
`ssh wisp… 'journalctl -u dnsmasq -f'`; SNMP PoE-cycle of s1 port 46 per the
`rig_power_cycle.py`/RIG-POWER-CYCLE.md manual-fallback pattern (validate the
ifIndex for port 46 first — hardware moves ports; community via
`RIG_SNMP_WRITE_COMMUNITY`). Puck 12 MACs: eth0 `44:07:0B:01:A2:21`,
eth1 `44:07:0B:01:A2:22`; expected IP 10.1.4.112.

### Task 7.1: Switch port → VLAN 4 ⚠ STOP-AND-CONFIRM
- [ ] Confirm with user, then set s1 port 46 PVID 4 untagged (manual netgear
  UI/CLI acceptable; record exact steps in the runbook). Verify: PoE-cycle →
  wisp dnsmasq journal shows DHCPDISCOVER from `44:07:0b:01:a2:2x` in the
  dynamic range (identity may already pin it — either is a pass); **ten64**
  `journalctl -u dnsmasq@internal` shows NOTHING for those MACs (deliberate
  ignore proven).

### Task 7.2: Unarmed behavior (no bootfile → eMMC)
- [ ] With identity deployed and puck12 **unarmed**: PoE-cycle. Expect on
  wisp: DHCPACK 10.1.4.112 `puck12`, **no TFTP RRQ** for gale-installer.itb
  (grep the journal window), and (~1 min later) a *second* DHCP from the
  same MAC — the **booted eMMC OpenWrt** wan client. `ping 10.1.4.112`,
  `dig puck12.wifi.welland.mithis.com` → 10.1.4.112 from desktop.
  (Puck 12's current eMMC contents boot an older OpenWrt — fine, any eMMC
  boot proves fallback; if its eMMC is empty/broken, record and proceed —
  step 7.3 will install.)

### Task 7.3: Armed install round-trip
- [ ] `gwifi-netboot arm puck12` (via ssh) → confirm generated conf gained
  `set:install` + dhcp-boot line. PoE-cycle. Expect journal sequence: DHCPACK
  with bootfile → TFTP transfer of gale-installer.itb completes → (~2–4 min)
  phone-home `success` in `gwifi-netboot status` / service journal → state
  auto-disarmed → dnsmasq restarted (conf no longer has set:install).
- [ ] PoE-cycle again → no TFTP RRQ; eMMC boots the **new** image; ssh in
  (default OpenWrt: root, no pw on LAN side — the image is the production
  gale-image build; use its configured access) and
  `cat /etc/gwifi-image-id` matches the manifest. Record boot-to-ssh timing.

### Task 7.4: Idempotence + re-arm
- [ ] Re-arm puck12 without publishing a new image; PoE-cycle. Expect: TFTP
  of installer, then phone-home `already-current` (no dd — journal gap is
  short), auto-disarm, reboot to eMMC. This proves the stale-armed-state
  self-heal (spec §6).

### Task 7.5: Runbook + docs + wrap-up
- [ ] Write `docs/wisp-netboot-runbook.md`: arm/disarm, publish a new image,
  re-arm fleet, port-VLAN steps, troubleshooting table (no-DHCP / TFTP storm
  symptoms from fleet lore / phone-home missing / API down ⇒ parked
  installer), pilot timings, cert/renewal + resolver notes from Phase 2.
- [ ] Update `docs/wisp-netboot-install-design.md` status line → Implemented
  (pilot passed) with date.
- [ ] Final commits; push branch `wisp-netboot-install`; report fleet-rollout
  readiness (arming remaining pucks is a user decision — sheet Firmware
  column governs identity; pucks 1–2 stay untouched).
