<!-- SPDX-License-Identifier: Apache-2.0 -->
# wisp.welland netboot-install infrastructure — Design Spec

- **Date:** 2026-07-11
- **Status:** Approved by user (brainstorming session); pending spec review.
- **Goal:** Power-cycling a fleet-firmware gale puck on the wifi VLAN gets OpenWrt
  installed to its eMMC automatically, then boots from eMMC on every later cycle.
- **Depends on:** fleet netboot-first depthcharge payload `cd5ffa6` (already
  flashed / being flashed to the fleet; TFTP-retry fix + eMMC fallback proven),
  the `gale-openwrt-netboot-install.md` manual procedure (automated here), and
  the existing OpenWISP deployment on wisp.welland.mithis.com.

## 1. Summary

The pucks recorded in the "Google WiFi Pucks" sheet now run the netboot-first
depthcharge firmware: on every boot they DHCP, TFTP a bootfile if offered, and
fall back to the eMMC kernel otherwise. This design gives that firmware a
production server side:

- A new **VLAN 4 "wifi"** (10.1.4.0/24) for wireless-AP management. ten64
  routes it like every other trusted VLAN, but its dnsmasq **deliberately does
  not serve it**.
- **wisp.welland.mithis.com** (the OpenWISP VM) **moves onto VLAN 4**
  (10.1.5.2 → 10.1.4.2, single NIC) and owns DHCP + TFTP + HTTP + DNS for the
  pucks. Other VLANs reach OpenWISP via normal ten64 routing.
- **gdoc2netcfg** gains a generator that pushes puck *identity* (names, MACs,
  fixed IPs) to wisp. Identity only — no runtime state.
- A **`gwifi-netboot`** service on wisp owns all runtime state: which pucks are
  *armed* for install, what image is current, the phone-home endpoint, and the
  generated per-MAC dnsmasq config.
- An **idempotent installer image** (initramfs OpenWrt variant) that fetches
  the target image manifest, flashes the eMMC only when needed, verifies, and
  phones home.

## 2. Decisions and rationale (from brainstorming)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | VLAN 4 subnet | `10.1.4.0/24` | Consistent with the welland per-site `10.X.<vlan>.X/24` scheme; /16 global style is for cross-site VLANs (fpgas/sm). |
| D2 | Routing | ten64 routes (`br-wifi` = 10.1.4.1), wisp serves | Pucks stay reachable from int/roam via normal routing; wisp stays out of the datapath. dnsmasq@internal ignores the VLAN. |
| D3 | Install-state mechanism | Per-MAC armed state + phone-home, **and** an idempotent installer | Code-verified: a DHCP offer with no bootfile makes `netboot.c` fall through to eMMC in ~1–2 s (empty BOOTP `file` → TFTP fails → `vboot_select_and_load_kernel`). The installer's own version check guards against stale armed state. |
| D3a | kexec alternative | **Rejected** after investigation | Buildable (OpenWrt `CONFIG_KERNEL_KEXEC` + `kexec-tools` exist for ARM32) but requires stripping the CHROMEOS keyblock from eMMC p1, FIT parsing, kernel-cmdline recovery from the vboot config region, and an unproven kexec path on IPQ4019 (SCM/TZ secondary-core bringup, EDMA re-init). Also makes every production boot depend on wisp TFTP (~8 MB + an extra kernel boot ≈ 20–40 s). |
| D4 | Puck management interface | Untagged VLAN 4 on the wired port | Depthcharge netboot speaks untagged DHCP only; one switch-port config (PVID 4) serves both install and production. **Revises the 2026-06-05 autoprovision-mesh design R2** (mgmt was tagged VLAN 5); that doc is updated by the mesh work, not here. |
| D5 | Config service split | gdoc2netcfg pushes identity → wisp owns runtime | User decision: gdoc2netcfg stays a pure sheet→file pipeline; image state, arming, upgrades and phone-home are wisp-internal. |
| D6 | wisp VM homing | **Move** wisp onto VLAN 4 (single NIC, 10.1.4.2 static) rather than adding a second NIC | User decision: wisp is the wifi-management controller — everything it serves belongs to this VLAN; avoids dual-homing. Static addressing because VLAN 4 has no DHCP server other than wisp itself (chicken-and-egg). Other VLANs reach it routed via ten64. |

## 3. Non-goals

- Production mesh/AP configuration content (OpenWISP templates, SSIDs, client
  VLAN trunking) — the autoprovision-mesh work owns that, including the
  mgmt-VLAN-4 revision (D4).
- Switch-port automation. Pilot port moves are manual (or via existing netgear
  tooling).
- IPv6 for pucks. `br-wifi` gets `2404:e80:a137:104::1/64` for scheme parity,
  but RA/DHCPv6 stay off; netboot is v4-only.
- Sheet write-back of install state. Phone-home state lives on wisp;
  `sync_sheet.py`-style sheet sync can be added later.
- SPI-firmware (depthcharge/EC) flashing — that is the fleet-firmware-flash
  rig's job. This design starts where a puck already netboots.

## 4. Current state (verified 2026-07-11)

- **Firmware:** payload `cd5ffa6` netboots on every boot; DHCP-without-bootfile
  → clean eMMC fallback (verified in `src/netboot/dhcp.c:535-539` +
  `netboot.c:164-169`); `tftpserverip=<ip>` is appended to the kernel cmdline.
- **ten64:** systemd-networkd; per-VLAN `vlan-<name>@br-raw` → `br-<name>`;
  `dnsmasq@internal` (DHCP+DNS+TFTP for all existing VLANs) with config
  generated by gdoc2netcfg from published-CSV tabs of the network spreadsheet.
  VLAN 4 unused. `03-zone-forwarders.conf` pattern exists for zone delegation.
- **wisp VM:** Debian 13 arm64 libvirt guest on ten64, single NIC on `br-net`
  (10.1.5.2/24, MAC `02:00:0a:01:05:02`), runs OpenWISP (nginx, redis,
  influxdb, supervisor; Ansible-deployed). No DHCP/TFTP.
- **Pucks sheet:** tab `Google WiFi Pucks` (gid 210946497) of the same Google
  doc gdoc2netcfg reads; anonymously fetchable via the published-CSV URL
  (verified). Columns include #, Firmware (target: "OpenWRT" vs "Google
  Original"), Serial, MAC (label = eth0/wan), eth0, eth1, Flash Status.
  12 rows; eth1 = eth0 + 1 where recorded.
- **Pilot:** puck 12 (WGD) on switch s1 (`sw-netgear-gsm7252ps-s1`, 10.1.5.22)
  port 46, powered by a 30 W PoE adapter → SNMP port power-cycle resets it.
- **Console:** rpi3b capture is currently mute — pilot validation is judged
  from the wire (dnsmasq logs, phone-home, ssh), never console alone.

## 5. Architecture

```
 Google Sheet (pucks tab, published CSV)
        │  gdoc2netcfg generate (ten64, existing update procedure)
        ▼
 pucks.json ──scp──► wisp:/etc/gwifi-netboot/pucks.json     [identity only]
                          │
                          ▼
        gwifi-netboot (wisp)  ◄──── POST /phone-home (installer)
        │  state.json (armed / installed / history)
        ▼
 dnsmasq fragment (per-MAC dhcp-host + install tags)
        │ reload
        ▼
 dnsmasq on wisp (single NIC, 10.1.4.2, VLAN 4): DHCP + TFTP + auth DNS wifi.welland
 nginx  on wisp 10.1.4.2:80: /images/ (factory.bin, manifest)  [+ OpenWISP vhost]

 puck power-cycle ─► DHCP ─► armed?  ──yes──► TFTP gale-installer.itb ─► RAM
                              │no                    OpenWrt installer:
                              ▼                      manifest → check eMMC id
                     no bootfile → TFTP fails        → flash+verify if stale
                     → eMMC OpenWrt boots            → phone-home → reboot
```

### 5.1 Network layer

- **Sheet:** add VLAN row to `Welland - VLAN Allocations`: `4, wifi, 10.X.4.X,
  255.255.255.0, /24, … , WiFi AP management`. gdoc2netcfg derives topology
  from this tab, so VLAN 4 becomes a first-class known VLAN.
- **ten64 systemd-networkd** (pattern-copy from an existing VLAN):
  - `vlan-wifi.netdev/.network` — 802.1q id 4 on `br-raw`.
  - `br-wifi.netdev/.network` — `10.1.4.1/24`, `2404:e80:a137:104::1/64`,
    forwarding on, same policy as other trusted VLANs.
- **ten64 dnsmasq@internal:**
  - **No** `network-04-wifi.conf`; add `except-interface=br-wifi` with a
    comment naming this design, so the ignoring is deliberate and documented.
  - Zone-forward `wifi.welland.mithis.com` → `10.1.4.2` in
    `03-zone-forwarders.conf` so puck names resolve site-wide.
  - Update `/etc/dnsmasq.d/README` accordingly.
- **Switch:** puck ports = PVID 4 untagged. Pilot: s1 port 46.

### 5.2 wisp VM migration + plumbing

wisp moves from VLAN 5 to VLAN 4 (D6): single NIC, `10.1.5.2` → `10.1.4.2`.
Brief OpenWISP downtime is acceptable (no pucks are under management yet).

- **libvirt (ten64):** retarget the existing interface — `<source bridge>`
  `br-net` → `br-wifi`, MAC `02:00:0a:01:05:02` → `02:00:0a:01:04:02` (the
  MAC-encodes-IP convention). Applied with the guest shut down; recovery path
  if the guest comes up unreachable is `virsh console wisp`.
- **Guest networking:** match the guest's existing network manager (verify at
  implementation; systemd-networkd is running): **static** `10.1.4.2/24`
  (VLAN 4 has no DHCP server other than wisp itself), gateway `10.1.4.1`,
  IPv6 `2404:e80:a137:104::2/64`. Resolver: ten64's internal dnsmasq via a
  routed listen address (e.g. `10.1.5.1`) — ten64's dnsmasq deliberately does
  not serve br-wifi, and wisp's own dnsmasq must not be a boot dependency of
  the guest's resolver. Verify routed queries are answered (no
  `local-service` restriction) during implementation; fall back to public
  resolvers if not. Guest config staged **before** the libvirt retarget,
  keyed to the new MAC.
- **Sheet + DNS record:** update wisp's row in the IP-allocation data
  (VLAN net→wifi, IP 10.1.4.2); gdoc2netcfg regeneration moves the
  `wisp.welland.mithis.com` A/AAAA records. TLS: the LE certificate is tied
  to the *name*, not the IP — verify the renewal path (DNS-01/HTTP-01) still
  works from the new VLAN during implementation.
- **Ordering:** ten64 VLAN plumbing (5.1) must exist before the retarget;
  post-move gate = OpenWISP HTTPS reachable from int + cert valid + ssh via
  the new address.
- **dnsmasq (new package install, single instance):**
  - Binds only the VLAN-4 interface (`bind-dynamic` + `interface=` scoping so
    it cannot shadow systemd-resolved on localhost).
  - `dhcp-range=10.1.4.100,10.1.4.199` + `dhcp-authoritative`; 10.1.4.3–99
    reserved for static/infra, .100+ for pucks (fixed per-MAC assignments from
    identity, range doubles as fallback for unknown gale MACs — see 5.4).
  - `dhcp-option=option:router,10.1.4.1`, dns-server = 10.1.4.2.
  - `enable-tftp`, `tftp-root=/srv/gwifi/tftp`.
  - Authoritative DNS: `auth-zone=wifi.welland.mithis.com` +
    `domain=wifi.welland.mithis.com,10.1.4.0/24`.
  - `conf-dir=/etc/dnsmasq.d/gwifi-generated` — owned by gwifi-netboot.
  - `log-dhcp` + leasefile under `/var/lib/misc/` (defaults).
- **nginx:** additional server block, `listen 10.1.4.2:80`, root
  `/srv/gwifi/images/` (autoindex off, exact-file serving). The OpenWISP vhost
  is untouched.

### 5.3 Identity flow: gdoc2netcfg `gwifi_pucks` generator

New generator in gdoc2netcfg (branch `gwifi-pucks-generator`):

- **Source:** pucks tab via published CSV (same fetch/cache machinery as other
  tabs); new `[sheets] gwifi_pucks = <url>` entry in `gdoc2netcfg.toml`.
- **Filter:** rows with `Firmware == "OpenWRT"` and a non-empty Serial + MAC.
  ("Google Original" pucks 1–2 are excluded entirely — wisp never learns their
  MACs, so they get dynamic-range leases and no bootfile if ever plugged in.)
- **Emit `out/wisp/pucks.json`:** per puck:
  - `name`: `puck<NN>` (sheet `#` column, zero-padded to 2),
  - `serial`, `eth0`, `eth1` (eth1 derived as eth0+1 when the column is empty,
    matching the fleet's verified pattern),
  - `ip`: `10.1.4.<100+NN>` (deterministic; sheet # is the allocator).
- **Constraints stage:** MAC uniqueness vs. the rest of the network data;
  fail generation on duplicate serials/#s.
- **Deployment:** the documented ten64 update procedure gains one step:
  `scp out/wisp/pucks.json wisp:/etc/gwifi-netboot/pucks.json` (then
  `ssh wisp sudo systemctl reload gwifi-netboot` or equivalent trigger).

### 5.4 Runtime service on wisp: `gwifi-netboot`

Python/uv tool, code in `gwifi-openwrt` repo under `tools/gwifi-netboot/`,
deployed to wisp with systemd units. Responsibilities:

- **Inputs:**
  - `/etc/gwifi-netboot/pucks.json` — identity (from gdoc2netcfg).
  - `/var/lib/gwifi-netboot/state.json` — per-MAC runtime state: `armed`
    (bool), `installed_image_id`, `last_phone_home`, bounded event history.
  - `/srv/gwifi/images/manifest.json` — current target image: filename,
    sha256, size, `image_id`, optional per-MAC `force` list. Written by the
    image-publish step (see 5.5), served verbatim by the manifest endpoint.
- **Renders `/etc/dnsmasq.d/gwifi-generated/pucks.conf`:**
  - One `dhcp-host` line per puck (both MACs — a puck may be cabled by either
    port): unarmed `dhcp-host=<eth0>,<eth1>,<ip>,<name>`, armed
    `dhcp-host=<eth0>,<eth1>,<ip>,<name>,set:install` — a **single combined
    line**, never two lines for the same MAC (dnsmasq's duplicate-dhcp-host
    behavior is surprising and `--test` would not catch it).
  - A single `dhcp-boot=tag:install,gale-installer.itb` line.
  - Unarmed pucks get an offer with **no bootfile** → firmware falls back to
    eMMC (D3).
  - After render: `dnsmasq --test` the fragment, then reload dnsmasq; refuse
    to install a fragment that fails the syntax check.
- **HTTP API on `10.1.4.2:8080`** (stdlib/small-framework, systemd service):
  - `GET /manifest` → manifest.json content.
  - `POST /phone-home` — body: serial, mac, `image_id`, result
    (`success` / `already-current` / `failed`), free-text detail. Effects:
    update state, **disarm on success/already-current**, regenerate + reload
    dnsmasq, append to history. Failures never disarm.
  - `GET /status` → JSON of all pucks: identity + state (for humans/CLI).
- **CLI (same tool):** `gwifi-netboot status`, `arm <puck|--all>`,
  `disarm <puck|--all>`. Arming regenerates + reloads immediately.
- **Reload semantics:** identity file replaced → path/reload trigger
  regenerates; unknown MACs in state.json are kept but flagged in `status`.

### 5.5 Installer image (`gale-installer.itb`) — idempotent

Built from the existing OpenWrt netboot build (raw initramfs FIT, per
`openwrt-patches/`) plus a files overlay; build script in
`tools/gwifi-netboot/` (or `gale-image/`) alongside the fleet conventions:

- **Boot context:** `netboot.c` appends `tftpserverip=<wisp>` to the cmdline —
  the installer derives all URLs from it (`http://<ip>/images/…`,
  `http://<ip>:8080/…`). No baked server addresses.
- **Flow (init script, runs once network is up via `wan` DHCP):**
  1. Fetch `GET :8080/manifest`.
  2. Read the installed image id: mount eMMC p2 (squashfs) read-only, read
     `/etc/gwifi-image-id`, **then unmount** (nothing may hold the device
     when step 5 rewrites it). Unreadable/absent (blank or corrupt eMMC) ⇒
     treat as stale.
  3. `image_id` matches manifest and MAC not in `force` ⇒ phone-home
     `already-current`, reboot. (Guards against stale armed state — D3.)
  4. Otherwise: fetch `factory.bin` to RAM (`/tmp`; image ~a few hundred MB
     free on 512 MB RAM — verify fit at build time, factory.bin is ~40 MB),
     verify sha256 against manifest; mismatch ⇒ phone-home `failed`, stop.
  5. `dd` to `/dev/mmcblk0` + `sync` + partition re-read; mount new p2 and
     re-read `/etc/gwifi-image-id` as write-verification.
  6. Phone-home `success` (serial from VPD/cmdline, MACs, image_id), reboot.
  - Any error: phone-home `failed` with detail, **stay up** (serial shell
    reachable, puck still netbootable for a retry cycle). This includes
    phone-home delivery failure itself (e.g. dnsmasq up but the :8080 API
    down, even on an `already-current` result): the installer **stays up**
    rather than rebooting, so an armed-but-current puck parks in the RAM
    installer instead of hot-looping netboot until the API returns.
- **Production image marker:** the fleet factory image build bakes
  `/etc/gwifi-image-id` (e.g. `gale-openwrt-<version>-<date>-<shortsha>`), and
  the publish step writes the matching `manifest.json` + copies factory.bin
  into `/srv/gwifi/images/`. Publishing = one script:
  `publish_gale_image.py <factory.bin>` (computes sha/id, atomically swaps
  manifest).

### 5.6 DNS naming

- Pucks: `puck<NN>.wifi.welland.mithis.com` → fixed IP (dnsmasq dhcp-host +
  auth-zone on wisp).
- Site-wide resolution via the ten64 zone-forward (5.1).
- `wisp.welland.mithis.com` itself resolves to 10.1.4.2 after the migration
  (gdoc2netcfg-generated record; no extra alias needed).

## 6. Failure modes

| Failure | Behaviour |
|---|---|
| wisp down / dnsmasq dead | Puck DHCP times out (bounded resends) → eMMC fallback. Production pucks unaffected beyond a boot delay. |
| Armed but image fetch/verify fails | Phone-home `failed`, puck stays in RAM installer with serial shell; next power cycle retries (still armed). |
| Phone-home lost after successful flash | State stays armed → next boot re-enters installer, which sees `already-current`, phones home, disarms. Self-healing (D3). |
| dnsmasq/TFTP up but :8080 API down | Armed puck boots installer, phone-home fails → installer stays up (no reboot loop); disarm resolves on the next cycle after the API returns. Unarmed pucks unaffected. |
| Stale/duplicate MAC in sheet | gdoc2netcfg constraints stage fails generation loudly; wisp keeps last-good pucks.json. |
| Unknown gale plugged into VLAN 4 | Dynamic lease from .100–.199 range, **no bootfile** (no identity → not armed) → boots its eMMC. |
| Rendered dnsmasq fragment invalid | `dnsmasq --test` gate; last-good config stays live. |
| wisp guest misconfigured after migration | Static config, no DHCP dependency; recover via `virsh console wisp` on ten64. |
| Puck 1–2 (stock Google) on VLAN 4 | Not in identity; same as unknown gale. Stock firmware doesn't netboot anyway. |

## 7. Security posture

- VLAN 4 is a trusted-tier management VLAN; DHCP/TFTP/HTTP (all unauthenticated
  by nature) are scoped to `br-wifi` / wisp's VLAN-4 interface only — never
  the public or other
  VLANs. `except-interface` on ten64 and `interface=` scoping on wisp are both
  explicit.
- Phone-home is unauthenticated but only mutates state toward *disarm* on
  success; arming (the destructive direction) is CLI-only on wisp. A rogue
  on-VLAN device could phone-home `failed` noise or disarm a pending install —
  acceptable on a physically-controlled management VLAN; noted for later
  hardening (per-puck token in manifest) if VLAN 4 ever carries less-trusted
  gear.
- Images and manifest are integrity-checked (sha256) end-to-end from the
  publish step.

## 8. Pilot validation plan (puck 12 / WGD, s1 port 46)

Judge **from the wire** (console capture currently mute):

0. VM migration gate (5.2): OpenWISP HTTPS + ssh reachable at 10.1.4.2 from
   int, cert valid, `wisp.welland.mithis.com` resolving to the new address.
1. Move s1 port 46 to PVID 4 untagged; confirm link + dynamic-range DHCP
   *before* identity/arming (proves VLAN path + deliberate-ignore on ten64:
   ten64's dnsmasq log shows nothing for the puck's MACs).
2. Deploy identity (`pucks.json`) — puck 12 now gets its fixed IP + name, no
   bootfile; SNMP PoE-cycle → verify eMMC boot via dnsmasq log pattern
   (DHCP ack, no TFTP RRQ) and ssh/OpenWISP agent reachability.
3. `gwifi-netboot arm puck12` → PoE-cycle → dnsmasq shows TFTP of
   `gale-installer.itb`; phone-home `success` (or `already-current` on a
   re-run) arrives; state disarms.
4. PoE-cycle again → no TFTP RRQ, puck boots installed eMMC image, `puck12`
   resolves site-wide, reachable from int.
5. Re-arm and confirm the full reinstall round-trips (idempotence: second
   consecutive install with same manifest reports `already-current`).

## 9. Deliverables & repo layout

- **`gwifi-openwrt` branch `wisp-netboot-install`:**
  - `docs/wisp-netboot-install-design.md` (this doc) + an ops runbook
    (`docs/wisp-netboot-runbook.md`: arm/disarm, publish image, re-arm fleet,
    troubleshooting table).
  - `tools/gwifi-netboot/` — service + CLI + tests; systemd units; deploy
    script (rsync+ssh, idempotent).
  - Installer overlay + build script; `publish_gale_image.py`.
- **`gdoc2netcfg` branch `gwifi-pucks-generator`:** generator + constraints +
  tests + README/procedure update.
- **Host changes (ten64/wisp), applied during implementation and captured in
  the runbook:** networkd units, libvirt NIC retarget (wisp VM move to
  VLAN 4), guest static network config, dnsmasq configs, nginx block,
  `/etc/dnsmasq.d/README` update, VLAN sheet row + wisp IP-allocation move.

## 10. Open items deferred to implementation

- Verify wisp guest's network manager flavor before writing its config.
- Verify ten64's internal dnsmasq answers routed DNS queries from 10.1.4.2
  (wisp's post-move resolver), and that the LE cert renewal path for
  `wisp.welland.mithis.com` works from VLAN 4.
- Audit for anything that hardcodes wisp's old 10.1.5.2 address (OpenWISP
  settings, monitoring, firewall rules, ssh configs) before the move.
- Verify installer RAM headroom for factory.bin (initramfs + image in tmpfs on
  512 MB).
- Choose the exact reload trigger for identity pushes (systemd path unit vs.
  explicit ssh reload) when writing the deploy script.
- Confirm the netgear s1 CLI/SNMP steps for PVID 4 on port 46 (manual is
  acceptable for the pilot).
