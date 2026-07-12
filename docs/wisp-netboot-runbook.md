<!-- SPDX-License-Identifier: Apache-2.0 -->
# wisp netboot — Operations Runbook

Day-2 operations for the gale puck netboot-install infrastructure.
Design: [`wisp-netboot-install-design.md`](wisp-netboot-install-design.md).
Plan/history: [`wisp-netboot-install-plan.md`](wisp-netboot-install-plan.md).

## Who does what

| Component | Host | Role |
|---|---|---|
| `dnsmasq@internal` | ten64 | DNS for VLAN 4 (10.1.4.1) incl. generated puck host-records; **never DHCP there** |
| `dnsmasq` | wisp (10.1.4.2) | DHCP `.100-.199` + TFTP (`/srv/gwifi/tftp`); `port=0` — no DNS |
| `gwifi-netboot.service` | wisp | arming state, rendered `/etc/dnsmasq.d/gwifi-generated/pucks.conf`, `:8080` manifest + phone-home API |
| nginx `gwifi-images` vhost | wisp | `http://10.1.4.2/` → `/srv/gwifi/images` (by-IP Host; name requests go to OpenWISP) |
| gdoc2netcfg | ten64 | identity: `wisp/pucks.json` + `internal/gwifi-pucks-dns.conf` from the pucks sheet |

## Common operations

All CLI commands run on wisp as root
(`ssh wisp.welland.mithis.com`, tool at `/opt/gwifi-netboot`):

```sh
alias gwn='sudo python3 -m gwifi_netboot.cli'   # from /opt/gwifi-netboot

gwn status                  # identity + armed + installed image per puck
gwn arm puck12              # netboot-install on its next power cycle
gwn arm --all               # whole fleet
gwn disarm puck12
gwn render                  # force re-render + dnsmasq restart
```

Watch an install live: `sudo journalctl -u dnsmasq -u gwifi-netboot -f`
(DHCPACK with bootfile → TFTP transfer → phone-home in the API log).

## Publish a new image

```sh
# 1. build (stamps /etc/gwifi-image-id + .image-id sidecar):
gale-image/build-gale-image.sh
# 2. publish into a local staging dir (writes manifest + content-addressed copy):
cd tools/gwifi-netboot
uv run python -m gwifi_netboot.cli --help  # (publish is a library call; see below)
uv run python -c "from pathlib import Path; from gwifi_netboot.publish import publish; print(publish(Path('$OWRT/bin/targets/ipq40xx/chromium/openwrt-ipq40xx-chromium-google_wifi-squashfs-factory.bin'), Path('stage/images')))"
# 3. build the installer if it changed: gale-installer/build-installer.sh
#    → cp gale-installer/out/gale-installer.itb stage/tftp/
# 4. deploy artifacts + service:
uv run deploy.py --artifacts stage
# 5. arm pucks; each power cycle installs, phones home, disarms itself.
```

## Identity updates (new puck / sheet change)

On ten64: `cd /opt/gdoc2netcfg && sudo make deploy` (regenerates dnsmasq
incl. `gwifi-pucks-dns.conf`), then push identity to wisp:

```sh
scp /opt/gdoc2netcfg/wisp/pucks.json wisp.welland.mithis.com:/tmp/pucks.json
ssh wisp.welland.mithis.com 'sudo install -m 0644 /tmp/pucks.json \
  /etc/gwifi-netboot/pucks.json && sudo systemctl restart gwifi-netboot'
```

Only rows with `Firmware == "OpenWRT"` + serial + MAC become identity; the
stock Google pucks are invisible to the netboot DHCP.

## Switch ports

Puck-facing ports: **PVID 4 untagged** (`wifi` VLAN). Pilot: s1
(`sw-netgear-gsm7252ps-s1`, 10.1.5.22) port 46, 30 W PoE adapter —
SNMP PoE port-cycle resets the puck (validate the ifIndex first; ports
move — see `tools/RIG-POWER-CYCLE.md` conventions on the fleet branch).

## Troubleshooting

| Symptom | Meaning / action |
|---|---|
| Armed puck: DHCPACK but no TFTP RRQ in wisp journal | Bootfile missing from offer — check `pucks.conf` has `set:install` + `dhcp-boot` lines; `gwn render` |
| TFTP starts, transfer stalls/storms | See fleet lore: TFTP retry storm was a firmware bug fixed in payload cd5ffa6; confirm the puck runs it (sheet Depthcharge column) |
| No phone-home after TFTP completes | Installer running but can't reach `:8080` — check `gwifi-netboot` active, `curl http://10.1.4.2:8080/status`. Puck is parked in the RAM installer (by design); fix the API, power-cycle |
| Phone-home `failed: sha256 mismatch` | Corrupt download or manifest/image drift — re-publish (step above rewrites both atomically) |
| Phone-home `failed: post-flash marker` | Image built without the stamp — rebuild via `build-gale-image.sh` (never hand-copy a bare factory.bin) |
| Puck reinstalls on every cycle | Phone-home lost after success is self-healing (`already-current` next boot). If it persists: state file wedged — inspect `gwn status`, `/var/lib/gwifi-netboot/state.json` |
| Unknown gale on VLAN 4 | Gets a dynamic lease, **no bootfile**, boots its own eMMC. Appears in dnsmasq log only |
| dnsmasq won't restart on wisp | Fragment gated by `dnsmasq --test` — but check `journalctl -u dnsmasq`; last-good fragment stays if render failed |
| Puck DNS name doesn't resolve site-wide | `gwifi-pucks-dns.conf` missing from ten64 `internal/generated/` — run the identity update above |
| Phone-home serial is "unknown" | Normal — gale has no `/proc/device-tree/serial-number`; identity is MAC-keyed |
| Installed puck silent on VLAN 4 | The production image's bootstrap still assumes tagged-VLAN-5 mgmt (pre-D7 mesh design) — pending the mesh-image revision. Netboot/reinstall still works (firmware is VLAN-agnostic) |
| Switch fabric changes needed for a new puck port | VLAN 4 must exist end-to-end: see `create_vlan4.py` pattern (Q-BRIDGE via SNMP; FASTPATH agents answer commitFailed on sets they APPLY — always verify by read-back) |
| Installed image boots but goes silent | Proven killer (2026-07-11, puck12): **kmod-batman-adv** panics boot (image never reaches network — disabled in gale.config pending bench root-cause). Historical second killer — stp='1' port-RX death ~10 min post-boot — was root-caused to the qca8k lookup-state rmw bug (see storm entry below) and is FIXED by kernel patch 707; br-mgmt now ships stp='1' (validated 2026-07-12: 2× cold boots × 2 pucks on g080984b, 15+ min forwarding each, counters clean) |
| **VLAN 4 drowns / everything unreachable at once** | Broadcast storm. 2026-07-11 incident: a rebooting puck's PHY came out of the probe-time PSGMII calibration self-test effectively looped back (qca8k_phy_loopback_on_off() used the lookup-state VALUE as its rmw MASK — the DISABLED restore was a no-op; openwrt patch `707-net-dsa-qca8k-ipq4019-fix-lookup-state-rmw-masks.patch`), reflecting the switch's own traffic. The storming device's OWN counters stay near-zero (PHY-level reflection — invisible to its Linux stack). Fix: PoE-kill puck ports one at a time (`snmpset -v2c -c private 10.1.5.22 1.3.6.1.2.1.105.1.1.1.3.1.<port> i 2`) until the storm stops — recovery is instant; re-enable with `i 1`. Second hazard, same day: two WIRED pucks with 802.11s mesh enabled is an L2 loop waiting for a bridge — mesh0 ships disabled until batman-BLA (mesh design R3) |
| Agent registers as a junk random-MAC device | `openwisp.http.mac_interface` must be `wan` (label MAC, matches the pre-created G-NN devices); default br-lan fell back to a random bridge MAC. Baked in the overlay |
| Agent: curl exit 6/7, AAAA-only DNS | OpenWrt rebind protection drops RFC1918 A answers — `rebind_domain 'mithis.com'` is baked in the bootstrap |
| Agent crash-loop "must specify --uuid and --key, or --shared-secret" | openwisp-config CONSUMES shared_secret on registration (replaces with uuid+key). If you wipe uuid/key to force re-registration you must restore the secret (from gale-secrets.conf) |
| Stale G-NN config template | The 'gwifi-puck' template predates D7 (would move the lan port into br-roam!) — detached from G12 2026-07-12; the mesh work owns its revision. 'SSH Keys' template alone is safe |
| wisp itself unreachable | Static 10.1.4.2 on VLAN 4 (no DHCP dependency); recover via `sudo virsh console wisp` on ten64 |

## Cert / resolver notes (from the VLAN-4 migration, 2026-07-11)

- wisp = single NIC, static `10.1.4.2/24` + `2404:e80:a137:104::2/64`,
  gateways `.1`/`::1`, resolver `10.1.4.1` (netplan
  `/etc/netplan/50-cloud-init.yaml`; cloud-init network config disabled).
- LE cert: certbot **standalone** + stop/start-nginx hooks; the public path
  is ten64's generated proxy (ACME fallback → 10.1.4.2). Renewal dry-run
  verified post-migration. `wisp.welland.mithis.com` resolves to 10.1.4.2
  everywhere; OpenWISP vhost must NOT list the bare IP in `server_name`
  (the gwifi-images vhost owns Host `10.1.4.2`).
