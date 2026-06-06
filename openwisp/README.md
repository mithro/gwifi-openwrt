# OpenWISP controller on the `wisp` VM

Self-hosted OpenWISP controller for centrally managing the OpenWRT fleet
(~12 Google WiFi pucks + other devices), running in a dedicated VM on the
Ten64 router (`ten64.welland.mithis.com`).

This directory is the **source of truth** for the deployment: the Ansible
playbook, inventory, pinned requirements, and the InfluxDB apt pin. The VM
provisions (and later upgrades) itself by running this playbook against
`localhost`.

> Status: deployed and verified — see [Verification](#verification-as-built).

---

## Verification (as-built)

Deployed and verified on 2026-06-05 (role `openwisp.openwisp2` 25.10.2,
`ansible-core` 2.19.4, Debian 13 / arm64). The playbook finished
`failed=0` (`ok=121 changed=87`) in ~9 minutes.

| Check                       | Result                                                            |
|-----------------------------|-------------------------------------------------------------------|
| Services active + enabled   | `nginx`, `redis-server`, `influxdb`, `supervisor`, `postfix` — all active **and enabled at boot** |
| OpenWISP processes (supervisor) | `openwisp2` (uwsgi), `daphne` (websockets), `celery`, `celerybeat`, `celery_network`, `celery_monitoring`, `celery_firmware_upgrader` — all RUNNING |
| `manage.py check`           | "System check identified no issues (0 silenced)"                  |
| Web UI                      | `http://…/admin/ → 301 → https`; `https://…/admin/login/ → 200`    |
| **TLS certificate**         | **Let's Encrypt** (issuer `YE1`, ECDSA, 90-day, auto-renewing); external `curl` no `-k` via ten64 SNI passthrough → `HTTP 200`, `ssl_verify_result=0` |
| **End-to-end admin login**  | `LOGIN_OK` — full HTTPS login round-trip lands on `/admin/`        |
| InfluxDB                    | `influxdb 1.8.10-1` (pin held; 1.12.x was available); `openwisp2` DB present; bound `localhost:8086`, auth off |
| Module versions (venv)      | controller 1.2.3, monitoring 1.2.1, network-topology 1.2, firmware-upgrader 1.2.1, users 1.2.2, Django 5.2.15 |
| Footprint                   | 3.3 GB disk used / 16 GB free; ~1.5 GiB RAM used, 2.4 GiB available |

Admin credentials are stored at `openwisp/.admin-credentials` (mode 0600,
sensitive — do not publish). Reach the controller in a browser at
`https://wisp.welland.mithis.com/admin` — a **trusted Let's Encrypt
certificate**, no warning (see §6 → TLS for how it's issued/renewed).

---

## 1. What runs where

| Thing            | Value                                                              |
|------------------|-------------------------------------------------------------------|
| Hypervisor host  | `ten64.welland.mithis.com` (Traverse Ten64, NXP LS1088A, aarch64) — libvirt/KVM `qemu:///system` |
| Guest VM         | `wisp` — Debian 13 (trixie) arm64, 2 vCPU, ~3.8 GiB RAM, 20 GB virtio-blk disk, AAVMF UEFI, autostart |
| Network          | bridge `br-net` = **VLAN 5** (management, "Network infrastructure") |
| Address          | `10.1.5.2` / `wisp.welland.mithis.com` (DHCP reservation, MAC `02:00:0a:01:05:02`) |
| OpenWISP role    | `openwisp.openwisp2` **25.10.2** (modules pinned `~=1.2.0`)         |
| Control plane    | Ansible runs **on the VM itself** (`ansible_connection=local`)      |

The VM substrate (libvirt on the Ten64) mirrors the existing Home Assistant
VM, but with a virtio-blk disk and a Debian cloud image guest. The VM itself
was provisioned with cloud-init (NoCloud `cidata` seed); that step is outside
this directory.

## 2. Why these choices

- **OpenWISP** (GPLv3, Django) is the only mature, self-hosted, open-source
  controller that covers the required feature set: centralized WiFi/SSID/radio
  config, per-SSID→VLAN mapping, switch-port VLANs, 802.11s mesh config,
  signal + connected-client + throughput reporting, multi-site, and a central
  web UI. Client steering (802.11k/v/r, band steering) is handled on-device by
  `usteer`/`dawn`, configured *through* OpenWISP templates — that is a later,
  separate piece of work.
- **`ansible-openwisp2`, not `docker-openwisp`** — the official Docker images
  are amd64-only, so they will not run on the aarch64 Ten64. The Ansible role
  installs natively on arm64.
- **Debian 13 (trixie)** — chosen for support longevity (full support to
  2028‑08, vs bookworm ending 2026‑07). Although the role's
  `system-requirements` doc page still lists only Debian 11/12, the role's
  `meta/main.yml` **does** declare `trixie` support and ships a dedicated
  `vars/debian-13.yml` (e.g. `ntpsec`, `libgdk-pixbuf-2.0-0`,
  `freeradius /etc/freeradius/3.0`). Trixie's hard deps (GeoDjango/SpatiaLite,
  Python wheels, InfluxDB 1.8) were verified to build on arm64 beforehand.
- **SQLite + SpatiaLite** (role default `openwisp_utils.db.backends.spatialite`)
  — right-sized for ~12 devices, no PostgreSQL/PostGIS daemon to run or patch.
- **Run Ansible on the box (`connection=local`)** — a self-managed appliance:
  no separate control node, no ProxyJump fragility for the hundreds of
  connections a run makes, and `inventory_hostname` is naturally the FQDN
  (used for the nginx `server_name`, TLS cert CN, `ALLOWED_HOSTS`, and the
  `/etc/hosts` self-reference). Upgrades are just "re-run the playbook here".
- **Modules enabled**: controller (always), monitoring (signal/clients/perf),
  network_topology (mesh viz), firmware_upgrader (central firmware). **Off**:
  radius and subnet_division (not in the requirements; avoid extra daemons).

## 3. The InfluxDB 1.8.10 pin (important)

OpenWISP monitoring stores time-series data in **InfluxDB 1.x**. The
`openwisp.influxdb` sub-role installs the `influxdb` package with
`state: latest` and exposes **no version variable**. The InfluxData
`stable main` apt repo has since continued the v1 line up to **1.12.x**, so an
unconstrained install would land on `1.12.4-1` — a version openwisp-monitoring
is not documented/tested against, and whose `influxdb.conf` layout the
sub-role's line-edits were not written for.

`apt-preferences-influxdb` (installed to `/etc/apt/preferences.d/influxdb`)
pins the package to **`1.8.10-1`** with `Pin-Priority: 1001`, making it *the*
candidate so `state: latest` resolves to it and never drifts. 1.8.10 is the
version verified to install cleanly on Debian 13 / arm64, and the version the
monitoring module targets.

> InfluxDB runs bound to `localhost:8086` with **authentication disabled** —
> the correct posture for a single-box install. Do **not** set
> `influxdb_admin_password`: the sub-role would then create an InfluxDB user
> `admin`, but openwisp-monitoring connects as `openwisp`, so writes would
> fail on a username mismatch.

## 4. Files in this directory

| File                       | Purpose                                                        |
|----------------------------|----------------------------------------------------------------|
| `requirements.yml`         | Pins openwisp.openwisp2 25.10.2 + geerlingguy.certbot 5.4.1 + collections. |
| `inventory`                | One host, `ansible_connection=local`, FQDN as `inventory_hostname`. |
| `playbook.yml`             | Module set, locale/email/allowed-hosts, Let's Encrypt TLS, + custom firmware-upgrader hardware (§9). |
| `apt-preferences-influxdb` | The InfluxDB 1.8.10 apt pin (→ `/etc/apt/preferences.d/influxdb`). |
| `validate-firmware-images.py` | Offline check of the `OPENWISP_CUSTOM_OPENWRT_IMAGES` map in `playbook.yml` (§9). |
| `provision-openmesh.py`    | Pre-provision the 6 Open-Mesh APs as OpenWISP devices (reads MACs from ten64 at runtime; §9). |
| `README.md`                | This document.                                                 |

## 5. Reproducing the deployment from scratch

These are the exact steps used. Run them **on the `wisp` VM** as user `tim`
(passwordless sudo). The VM must already exist with DNS/DHCP set up, and — for
the TLS cert to issue — the wisp vhost must be enabled on ten64 (§6 → TLS) so
the ACME challenge reaches the box.

```sh
# 0. Get this directory onto the box at ~/openwisp (e.g. scp/rsync/tar).

# 1. Bootstrap the control toolchain (ansible bundle brings the required
#    community.general / ansible.posix collections; git lets galaxy fetch the
#    role's git-sourced dependency roles).
sudo apt-get update
sudo apt-get install -y ansible git

# 2. Pin InfluxDB to 1.8.10 BEFORE the role adds the InfluxData repo.
sudo install -m 0644 ~/openwisp/apt-preferences-influxdb /etc/apt/preferences.d/influxdb

# 3. Install the role (25.10.2) + its dependencies + collections.
ansible-galaxy install -r ~/openwisp/requirements.yml
#    -> openwisp.openwisp2 (25.10.2), Stouts.postfix, openwisp.influxdb

# 4. Run the playbook against localhost. Takes ~15-40 min on 2 arm64 cores
#    (it compiles Django + GeoDjango + the OpenWISP modules in a venv at
#    /opt/openwisp2/env). Best run detached so it survives an SSH drop:
cd ~/openwisp
setsid bash -c 'ansible-playbook -i inventory playbook.yml; echo EXIT=$?' \
    > ~/openwisp/deploy.log 2>&1 < /dev/null &
#    ...then watch:  tail -f ~/openwisp/deploy.log
```

A clean run ends with a `PLAY RECAP` showing `failed=0`.

## 6. Post-install

1. **Change the admin password immediately.** The role seeds a superuser
   `admin` / `admin`. It was changed to a strong password stored at
   `openwisp/.admin-credentials` (sensitive, not published). To change it
   again non-interactively:
   ```sh
   echo "from django.contrib.auth import get_user_model as G; \
   u=G().objects.get(username='admin'); u.set_password('NEWPASS'); u.save()" \
     | sudo /opt/openwisp2/manage.py shell
   ```
2. **TLS — a trusted Let's Encrypt certificate (in place).**
   `https://wisp.welland.mithis.com/admin` serves a real Let's Encrypt cert
   (ECDSA, 90-day, auto-renewing) — no browser warning. How it works:
   - **wisp terminates its own TLS.** ten64 (the public edge) does *not*
     decrypt for wisp: its nginx `stream{}` block reads the TLS SNI
     (`ssl_preread`) and passes `:443` straight through to `wisp:443`. On `:80`
     it serves the ACME HTTP-01 challenge from `/var/www/acme`, falling back to
     proxying the challenge to `wisp:80`.
   - **Prerequisite (one-time, on ten64):** the wisp vhost generated by
     `gdoc2netcfg` at
     `/etc/nginx/gdoc2netcfg/sites-available/wisp.welland.mithis.com/` must be
     enabled by symlinking it into `/etc/nginx/sites-enabled/` (as the other
     hosts are), then `sudo nginx -t && sudo systemctl reload nginx`. Until
     that's done ten64 routes wisp to its default server and certbot can't
     validate (502).
   - **On wisp:** the `geerlingguy.certbot` role (in `playbook.yml`) issues the
     cert via HTTP-01 `--standalone` — it briefly stops nginx to bind `:80`; the
     challenge arrives through ten64's fallback — into
     `/etc/letsencrypt/live/wisp.welland.mithis.com/`. openwisp's nginx is
     pointed at it via `openwisp2_ssl_cert` / `openwisp2_ssl_key`.
   - **Renewal is hands-off:** the packaged root `certbot.timer` runs
     `certbot renew`, and the role's `/etc/letsencrypt/renewal-hooks/{pre,post}`
     scripts stop/start nginx around it (`certbot_auto_renew: false`, so
     geerlingguy's own — wrong-user — cron isn't added).
   - Tip: validate the path cheaply first with `sudo certbot certonly
     --standalone --dry-run -d wisp.welland.mithis.com --pre-hook 'systemctl
     stop nginx' --post-hook 'systemctl start nginx'`.
3. Update the default **Site** and **Organization** objects, and note the
   organization's **shared secret** (used for device auto-registration).

## 7. Upgrading

```sh
ansible-galaxy install --force -r ~/openwisp/requirements.yml   # bump version in requirements.yml first
cd ~/openwisp && ansible-playbook -i inventory playbook.yml
```

The InfluxDB pin keeps the time-series DB stable across upgrades. To move to a
newer InfluxDB v1 later: delete `/etc/apt/preferences.d/influxdb`,
`apt update`, `apt install --only-upgrade influxdb`, restart `influxdb` and the
`celery_monitoring` worker, and re-check writes.

## 8. Optional trims / knobs

- `openwisp2_postfix_install: false` — drop the local MTA if you do not want
  e-mail notifications (alerts then won't send, but the app is unaffected).
- `openwisp2_usage_metric_collection: false` — opt out of anonymous usage stats.
- `openwisp2_time_zone` — set to your locale (currently `Australia/Adelaide`).

## 9. Firmware upgrader — custom hardware (gwifi + Open-Mesh)

`openwisp2_firmware_upgrader` is enabled, but its stock board→image map
(`openwisp_firmware_upgrader/hardware.py`, ~73 entries) covers **none** of this
fleet. OpenWISP matches a device to a firmware image by testing `device.model`
— what the device reports via `ubus call system board` — against each image's
`boards` tuple (`models.py`: `model__in=boards`), so an unlisted board can have
no image uploaded or assigned. `playbook.yml` adds the missing entries through
the documented `OPENWISP_CUSTOM_OPENWRT_IMAGES` setting, injected verbatim into
`settings.py` via `openwisp2_extra_django_settings_instructions`. hardware.py
does `OrderedDict(custom).update(<stock>)`, so ours are **merged**, not a
replacement.

Added — model strings + image-type keys verified against the OpenWrt 25.12.2
source tree (build target in parens):

| Device | reports `model` | image-type key |
|--------|-----------------|----------------|
| Google WiFi puck — *gale* (`ipq40xx/chromium`) | `Google WiFi (Gale)` ¹ | `ipq40xx-chromium-google_wifi-squashfs-sysupgrade.bin` |
| Open-Mesh OM2P-LC (`ath79/generic`) | `OpenMesh OM2P-LC` | `ath79-generic-openmesh_om2p-lc-squashfs-sysupgrade.bin` |
| Open-Mesh OM2P v1/v2/v4 (`ath79/generic`) | `OpenMesh OM2P v{1,2,4}` | `ath79-generic-openmesh_om2p-v{1,2,4}-squashfs-sysupgrade.bin` |

¹ also aliased as `Google Wifi` — the label the pre-provisioned OpenWISP
devices carry — so an image can be assigned before they onboard and report the
full DTS model.

Fleet basis (gdoc2netcfg inventory): the Google WiFi pucks + 6 Open-Mesh
CloudTrax nodes (4× OM2P-LC, 2× OM2P). All OM2P hardware revisions are listed
because the reported model is revision-specific and the gdoc only records the
family; the extras are harmless (each only ever matches a device reporting that
exact model). The image-type **key is a label, not the uploaded filename** —
upload the real `openwrt-…-sysupgrade.bin` artifact and select the matching
type when creating the Firmware Image.

Validate the map offline (no change to the box):

```sh
uv run --with pyyaml python openwisp/validate-firmware-images.py
```

**Deployed 2026-06-06** — `playbook.yml` was applied; the live controller
reports `OPENWISP_CUSTOM_OPENWRT_IMAGES` (5 entries) and the firmware-upgrader
reverse map resolves all six board strings. The fleet's **6 Open-Mesh APs are
pre-provisioned** as devices in org `default` (4× OM2P-LC + 2× OM2P, keyed by
label MAC, `config=none`) via `provision-openmesh.py` — joining the 11 pucks
(17 devices total). They bind by MAC when they later auto-register (after being
flashed to OpenWrt).

**Recognition ≠ flashing.** The map only lets OpenWISP *recognise* the hardware
and hold an image for it; the actual upgrade uses the default
`OPENWISP_FIRMWARE_UPGRADERS_MAP` upgrader (`sysupgrade` over SSH). Two caveats
before relying on remote upgrades: (a) the gale pucks boot via depthcharge/
netboot — confirm `sysupgrade`-to-flash behaves (a custom upgrader may be
needed for the CHROMEOS-kernel layout); (b) the OM2P units run Open-Mesh/
CloudTrax stock firmware today and must be flashed to OpenWrt (factory image)
once before OpenWISP can manage them. Auto-matching a device to a Build also
requires the **Build's `os` field** to match the device's reported `os` string.

## 10. Next steps (beyond "controller is running")

- **Device onboarding**: install `openwisp-config` on the pucks; register via
  the org shared secret; push the first config.
- **Eth → WiFi-mesh → last-config fallback**: an on-device piece (mesh always
  up + route metrics + the agent's persisted last config). Decide mesh routing
  (batman-adv/OLSR for topology visualization vs pure 802.11s).
- **Client steering**: `usteer`/`dawn` via OpenWISP templates.
- **Firmware upgrader**: the hardware map for gwifi + Open-Mesh is in place
  (§9); still to validate the live `sysupgrade` path on the depthcharge-booted
  pucks and flash the OM2P units to OpenWrt first.

## 11. Gotchas learned (so the next person doesn't relive them)

- The role's `system-requirements.rst` lags reality — trust `meta/main.yml`
  `platforms` (lists `trixie`) and the `vars/debian-13.yml` file instead.
- `state: latest` on `influxdb` drifts to 1.12.x — hence the apt pin (§3).
- Detaching a long run over SSH: redirect the **whole** backgrounded group, or
  wrap the command in `setsid bash -c '…' > log 2>&1 < /dev/null &`. A bare
  `A && B && setsid C … &` leaves the subshell holding the SSH channel and
  `ssh` hangs until the run finishes.
- After rebuilding the VM, clear the stale host key:
  `ssh-keygen -f ~/.ssh/known_hosts.<host> -R 10.1.5.2`.
