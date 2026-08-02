# wisp.monarto — second OpenWISP controller Design

Date: 2026-08-02
Status: approved (design). Nothing implemented; no VM created, no playbook
run, no live host modified.
Branch: `wisp-monarto` — based on `main` @ 520db6e.

## Goal

Stand up a second, independent OpenWISP controller — `wisp.monarto` on
`ten64.monarto.mithis.com` — mirroring the working `wisp.welland`
deployment, and restructure `openwisp/` so a single tree deploys either
site.

This is **sub-project 1 of 5** (see [Decomposition](#decomposition)). Its
done-condition is a reachable, TLS-valid, empty controller. Registering
devices is explicitly *not* part of it.

## Constraints (user-set)

- **Full parity with welland** is the eventual target, reached through the
  sub-project sequence below — not in one step.
- **Parameterise, one tree.** Do not fork a second copy of `openwisp/`.
  A fix must land once and serve both sites.
- Standing repo conventions apply: work on a branch in a worktree; `uv` for
  Python; ISO-8601 dates; small discrete commits; no `/tmp`; never discard
  stderr.

## Decomposition

"Full parity" spans several independent subsystems. They are specified and
built separately:

| # | Sub-project | Depends on | Status |
|---|-------------|-----------|--------|
| 1 | **Controller base + parameterisation** | — | **this spec** |
| 2 | Netboot stack (`gwifi-netboot`, netconsole, dnsmasq) | 1 | later |
| 3 | Templates, multi-site (`build-templates.py`) | 1 | later |
| 4 | Device onboarding | flash pipeline | **moot — no APs at monarto** |
| 5 | Presence + remote syslog | 3, 4 | **moot until 4** |

Sub-projects 4 and 5 are moot as of 2026-08-02: monarto has no wifi APs.
The `node{1,2,3}-wifi-google.monarto.mithis.com` names in DNS are
spreadsheet placeholders, and `ip neigh show dev br-wifi` on ten64.monarto
lists only `10.2.4.2` and `10.2.4.3`, both `FAILED`.

## Current state (verified live 2026-08-01/02)

### welland (the model)

| Property | Value |
|---|---|
| Host | `ten64.welland.mithis.com`, Debian forky/sid, libvirt/KVM aarch64 |
| Guest | `wisp` — 4 GiB RAM, 2 vCPU, machine `virt-10.2`, AAVMF UEFI |
| Disks | `/var/lib/libvirt/images/wisp.qcow2` (vda, virtio) + `wisp-seed.iso` (sda, scsi — cloud-init NoCloud) |
| NIC | MAC `02:00:0a:01:04:02`, bridge **`br-wifi`**, autostart **enabled** |
| Address | `10.1.4.2/24`, `2404:e80:a137:104::2/64`, **static netplan** |
| Edge | ten64 nginx: `:80` ACME + `@acme_fallback`, `:443` SNI passthrough → `10.1.4.2` |

### The README is stale — and why it matters

`openwisp/README.md` §1 and `playbook.yml` describe the VM as `br-net`,
VLAN 5, `10.1.5.2`. That is the **pre-migration** state.
`docs/wisp-netboot-install-plan.md` (Tasks 2.2–2.3) records the move to
`br-wifi` / VLAN 4 / `10.1.4.2`, and the live VM's MAC
(`02:00:0a:01:04:02`), DNS, and the vhost's `proxy_pass http://10.1.4.2`
all agree with the new address.

Consequence: `openwisp2_allowed_hosts: ["10.1.5.2"]` in `playbook.yml`
names an address the VM no longer holds. **This spec fixes it** rather than
faithfully replicating the error onto monarto.

### monarto (what already exists)

Substantially prepared — gdoc2netcfg has provisioned the site already:

- **DNS**: `wisp.monarto.mithis.com` → `10.2.4.2`, `2404:e80:a137:204::2`.
- **DHCP reservation**, in `/etc/dnsmasq.d/wifi/generated/wisp.conf`:
  `dhcp-host=02:00:0a:02:04:02,10.2.4.2,[2404:e80:a137:204::2],wisp`
- **`dnsmasq@wifi.service`** running on ten64.monarto.
- **Bridge** `br-wifi` = `10.2.4.1/24`, `2404:e80:a137:204::1/64`.
- **nginx vhost** generated at
  `/etc/nginx/gdoc2netcfg/sites-available/wisp.monarto.mithis.com`.
- libvirt + `qemu-system-aarch64` present; `homeassistant` VM running.

Missing: the VM itself, a staged guest image, and the
`sites-enabled` symlink for the vhost.

The MAC is therefore **prescribed, not chosen** — the reservation already
commits `02:00:0a:02:04:02`. The scheme embeds the IPv4
(`0a:02:04:02` → `10.2.4.2`).

## Architecture

```
ten64.monarto (Debian, libvirt/KVM aarch64)
  ├── homeassistant   (existing, untouched)
  └── wisp            (NEW)
        NIC 02:00:0a:02:04:02 → br-wifi → 10.2.4.2 (static)
        └── OpenWISP (same playbook, monarto vars) :443

  nginx on ten64.monarto:
    :80  /.well-known/acme-challenge → /var/www/acme, @acme_fallback → 10.2.4.2
    :443 ssl_preread SNI passthrough → 10.2.4.2:443
```

wisp terminates its own TLS; ten64 never decrypts for it. This is welland's
arrangement unchanged.

### D1 — Static addressing from day one (deviation from welland's history)

Welland is static *because it had to migrate there*. VLAN 4 is where wisp
itself later serves netboot DHCP, and `wisp-netboot-install-plan.md` states
the reason directly:

> "wisp lives on VLAN 4 (wifi, 10.1.4.0/24) and is itself the DHCP server
> there; no DHCP client possible (chicken-and-egg)."

Monarto's wisp *could* use DHCP today — ten64's reservation exists and wisp
is not yet serving. But sub-project 2 installs `dnsmasq` on wisp.monarto,
at which point the same retarget welland performed becomes necessary.
Static now costs nothing and skips a disruptive later migration.

The `dhcp-host` reservation is retained as documentation and belt-and-braces.

Note both DHCP servers coexist on welland's VLAN 4: ten64's `dnsmasq@wifi`
serves reservations, while wisp's instance is netboot-only (`port=0` — no
DNS at all, `bind-dynamic`, range `.100–.199`, TFTP).

### D2 — Separate inventory files, not one multi-host inventory

`ansible_connection=local` means the playbook configures **the machine it
runs on**. A single inventory listing both hosts would attempt to apply both
sites' configuration locally on whichever box the run happened on, silently
mis-configuring one. Separate inventory files make the site an explicit
argument that cannot be forgotten.

### D3 — `create-vm.py` as tooling, not a runbook

Welland's VM was built by hand; `README.md:54` states the cloud-init step
"is outside this directory". That gap is why replicating it required
reverse-engineering the live domain XML. Capturing it as a program (rather
than prose) makes a third site cheap and makes the MAC/bridge correctness
guard (D4) possible.

### D4 — Refuse on MAC/reservation disagreement

`create-vm.py` reads the site's `dhcp-host` line from the ten64 and
**aborts if the MAC it is about to use disagrees**. A typo yields a VM that
boots, receives no reservation, and fails confusingly much later; this
converts that into an immediate, explicit error.

### D5 — monarto is reachable directly only over IPv6

`*.monarto.mithis.com` resolves to both an internal AAAA and the shared
public IPv4 `87.121.95.37`, which is a **reverse proxy — a different
machine**. An ssh that falls back to IPv4 reaches the proxy and aborts with
`REMOTE HOST IDENTIFICATION HAS CHANGED`. Verified 2026-08-02:

| Endpoint | ED25519 fingerprint |
|---|---|
| public IPv4 (proxy) | `SHA256:L5xQuUuD82CYErpFLM3WF0NKSeZChzU0E7ba2tB6mUs` |
| internal IPv6 `2404:e80:a137:210::1` | `SHA256:ej3MHtv0cmAbDRohgqye+4xWi0dCdOFY+MHfxvH/Uv0` |
| stored `known_hosts` | `SHA256:ej3MHtv0cmAbDRohgqye+4xWi0dCdOFY+MHfxvH/Uv0` ✓ |

The stored key is correct; the warning is the only thing that catches a
wrong-host connection, so it must never be "fixed" by deleting the entry.

**Requirement:** every remote call in `create-vm.py` (and any later monarto
tooling) pins IPv6 — `ssh -6`, or an explicit address. A tool that silently
lands on the proxy would report nonsense about bridges and reservations.
This failure is intermittent, appearing only when the resolver falls back to
IPv4, so it must be designed out rather than noticed in testing.

### D6 — Do not pin the QEMU machine version

welland's domain uses `machine='virt-10.2'`, but the hosts are not on the
same QEMU: welland has **11.0.3** (libvirt 12.5.0), monarto **10.2.1**
(libvirt 12.0.0). `virt-10.2` is merely the *newest* type monarto offers, so
copying welland's pin works today and breaks the moment either host moves.

`create-vm.py` emits the unversioned `machine='virt'` alias and lets libvirt
canonicalise to the host's newest. `AAVMF_CODE.ms.fd` is present on both
hosts, so the loader path is portable as-is.

## Components

```
openwisp/
  playbook.yml                          # MODIFIED: site-agnostic
  requirements.yml                      # unchanged
  apt-preferences-influxdb              # unchanged
  inventories/
    welland                             # NEW: wisp.welland… ansible_connection=local
    monarto                             # NEW: wisp.monarto… ansible_connection=local
  group_vars/
    openwisp2.yml                       # NEW: shared vars
  host_vars/
    wisp.welland.mithis.com.yml         # NEW: site vars (allowed_hosts 10.1.4.2)
    wisp.monarto.mithis.com.yml         # NEW: site vars (allowed_hosts 10.2.4.2)
  create-vm.py                          # NEW
  tests/test_create_vm.py               # NEW
  README.md                             # MODIFIED: corrected + two-site
```

### Component 1 — Variable split

`group_vars/openwisp2.yml` (shared): module toggles, `openwisp2_time_zone`
(`Australia/Adelaide` — both sites are in South Australia), InfluxDB
posture, certbot settings, `OPENWISP_CUSTOM_OPENWRT_IMAGES`.

`host_vars/<fqdn>.yml` (per-site): `openwisp2_default_from_email`,
`openwisp2_allowed_hosts`, and the site's certbot contact.

The delta is deliberately tiny — three keys. `inventory_hostname` continues
to supply the nginx `server_name`, TLS CN, `ALLOWED_HOSTS` and the
`/etc/hosts` self-reference, so it must remain the FQDN (never a bare IP;
postfix breaks on an IP and turns some admin actions into HTTP 500s).

### Component 2 — `create-vm.py`

```
uv run openwisp/create-vm.py --site monarto [--dry-run]
```

Steps, in order:

1. Resolve site config (FQDN, IPv4/IPv6, gateway, bridge, MAC) from a
   declarative table in the script.
2. **Verify** the MAC against the ten64's `dhcp-host` reservation (D4);
   abort on mismatch.
3. Verify the bridge exists on the target ten64; abort if absent.
4. Refuse if a domain of that name already exists (no silent redefinition).
5. Fetch + checksum-verify the Debian 13 (trixie) arm64 generic cloud image.
6. Build the NoCloud seed ISO: `meta-data` (instance-id, hostname) and
   `user-data` (user `tim`, authorised key, passwordless sudo), plus the
   static netplan and `99-disable-network-config.cfg`.
7. Emit the domain XML (`machine='virt'`, unversioned — D6); `virsh define`;
   `virsh autostart`; `virsh start`.

All remote calls pin IPv6 (D5). `--dry-run` performs 1–4 and prints the XML
and seed contents without touching libvirt or writing any file to the
target — so the reservation, bridge and domain-collision checks can be
exercised against the real hosts with zero side effects.

Site facts live in one declarative table, so a third site is a table entry
plus a `host_vars` file.

### Component 3 — Edge enablement (one-time, on ten64.monarto)

```sh
ln -s /etc/nginx/gdoc2netcfg/sites-available/wisp.monarto.mithis.com \
      /etc/nginx/sites-enabled/wisp.monarto.mithis.com
nginx -t && systemctl reload nginx
```

**Must precede certbot.** Until it is done ten64 routes the name to its
default server and ACME validation returns 502.

### Component 4 — Deploy

On the new VM, as `tim` (passwordless sudo):

```sh
# 0. Get openwisp/ onto the box at ~/openwisp (rsync from the desktop),
#    EXCLUDING the secrets: .admin-credentials, .wifi-secrets.
sudo apt-get update && sudo apt-get install -y ansible git

# 1. Pin InfluxDB BEFORE the role adds the InfluxData repo (else `state:
#    latest` drifts to 1.12.x — see README §3).
sudo install -m 0644 ~/openwisp/apt-preferences-influxdb \
     /etc/apt/preferences.d/influxdb

# 2. Role + dependencies + collections.
ansible-galaxy install -r ~/openwisp/requirements.yml

# 3. Deploy, detached.
cd ~/openwisp
setsid bash -c 'ansible-playbook -i inventories/monarto playbook.yml; echo EXIT=$?' \
    > ~/openwisp/deploy.log 2>&1 < /dev/null &
```

Detached because the run takes ~15–40 min on 2 arm64 cores (it compiles
Django/GeoDjango and the OpenWISP modules into a venv). The `setsid`
wrapping is required: a bare `A && B && setsid C &` leaves the subshell
holding the SSH channel.

### Component 5 — Post-install

1. Change the seeded `admin`/`admin` password immediately; store alongside
   welland's in `openwisp/.admin-credentials` (mode 0600, never published).
2. Set the Organization and Site objects; record the org shared secret.
3. Confirm `OPENWISP_CUSTOM_OPENWRT_IMAGES` is present (5 entries).

## Error handling

| Failure | Detection | Response |
|---|---|---|
| MAC ≠ reservation | `create-vm.py` pre-flight (D4) | abort before defining |
| Bridge absent | `create-vm.py` pre-flight | abort |
| Domain exists | `virsh dominfo` | abort; never redefine |
| Image checksum mismatch | verify after fetch | abort; delete partial |
| ACME 502 | `certbot --dry-run` | enable vhost symlink first |
| LE rate limit | dry-run before real issue | back off; dry-run is unlimited |
| Playbook failure | `PLAY RECAP failed>0` | read `deploy.log`; re-run (role is idempotent) |
| welland regression | re-run against welland | see Testing |
| ssh lands on the IPv4 proxy | host-key mismatch (D5) | fix transport (`-6`); never edit `known_hosts` |

### Rollback

The monarto side is a new VM and one symlink, so rollback is cheap and
total: `virsh destroy wisp && virsh undefine --nvram wisp`, delete
`wisp.qcow2`/`wisp-seed.iso`, remove the `sites-enabled` symlink and reload
nginx. No existing monarto service is modified at any point — the
`homeassistant` VM, the dnsmasq instances and the generated nginx configs
are all untouched.

The welland side carries the only real risk (the variable refactor), and it
is a git revert plus a playbook re-run.

### Secrets

`openwisp/.admin-credentials` and `.wifi-secrets` are mode-0600 and
gitignored; they must not be copied to the VM in step 0, and the new
`host_vars` files must contain **no** secrets — only FQDN, e-mail,
allowed-hosts. Credentials stay on the desktop.

## Testing

**Offline (no hardware, CI-able):**

- `create-vm.py` site-config resolution: correct FQDN/IP/MAC/bridge per site.
- **MAC↔IP consistency**: the derived MAC's last four octets equal the IPv4
  (`02:00:0a:02:04:02` ⇔ `10.2.4.2`) — for both sites.
- Domain XML generation: memory, vCPU, UEFI loader, virtio-blk vda, seed
  sda, bridge, MAC, autostart.
- Seed contents: netplan matches the site's addressing; cloud-init network
  config disabled.
- Reservation-mismatch guard raises rather than proceeding (fixture, no ssh).
- Variable split: welland's resolved vars equal today's effective values
  **except** `allowed_hosts` (`10.1.5.2` → `10.1.4.2`) — pinning the intended
  change and catching accidental drift.
- `validate-firmware-images.py` still passes.

**Live acceptance:**

- Playbook `PLAY RECAP` `failed=0`.
- Services active *and enabled*: nginx, redis-server, influxdb, supervisor,
  postfix; supervisor shows `openwisp2`, `daphne`, `celery`, `celerybeat`,
  `celery_network`, `celery_monitoring`, `celery_firmware_upgrader` RUNNING.
- `manage.py check` → no issues.
- `https://wisp.monarto.mithis.com/admin/login/` → 200, `ssl_verify_result=0`
  with **no** `-k` (proves the real LE cert through ten64's passthrough).
- Full admin login round-trip lands on `/admin/`.
- InfluxDB is `1.8.10-1` (pin held), DB `openwisp2` present.

**welland non-regression** (gates the refactor):

- Re-run the playbook against welland: `failed=0`, and the only `changed`
  task attributable to this work is the `allowed_hosts` correction.
- welland's admin still serves 200 over HTTPS afterwards.

## Out of scope

Netboot stack; `build-templates.py` multi-site; device registration;
presence → HA MQTT; remote syslog. Each is a later sub-project with its own
spec. Nothing in this spec registers a device or pushes a template.

## Open questions

1. **Certbot contact e-mail for monarto** — welland uses `claude@mith.ro`.
   Reuse, or a site-specific address?
2. **Guest image staging** — fetch the Debian cloud image directly on
   ten64.monarto (needs egress), or stage from welland/big-storage?
3. **`.admin-credentials`** currently holds one site's credentials in a flat
   file. Extend to two entries, or one file per site?
