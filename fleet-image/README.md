# fleet-image — shared base for gale/tenwrt/om2p

The common OpenWrt config fragment, overlay, build library, and verifier
helpers that `gale-image/`, `tenwrt-image/`, and `om2p-image/` specialize.
See `docs/fleet-image-base-design.md` for the full design (this file is the
short operational reference).

## Layout

- `base.config` — the shared "managed feature set": openwisp-config,
  openwisp-monitoring, mesh-capable-but-unconfigured batman-adv +
  wpad-mesh-mbedtls, usteer, luci, ip-full, tcpdump-mini, ethtool. Per-image
  fragments are concatenated AFTER this file and may turn any line off with
  an explicit `# CONFIG_PACKAGE_x is not set` (kconfig keeps the last
  assignment) — om2p does this for its 7168k slot.
- `files/` — the shared overlay: `etc/config/openwisp` (URL/secret
  placeholders, `management_interface 'br0.4'`) and
  `lib/gwifi/bootstrap.sh` (parameterized first-boot functions: create/edit
  `br0`, mgmt bridge-vlan + interface, dnsmasq/rebind, firewall zone).
- `build-lib.sh` — sourced by each image's build wrapper.
- `verify_lib.py` — shared verifier checks (`parse_secrets`,
  `check_no_placeholders`, `find_manifest`/`require_packages`).

## Wrapper contract

Each image's `build-<name>-image.sh` runs under `set -eu`, sets these
variables, then sources `build-lib.sh`:

| var | meaning |
|---|---|
| `HERE` | image dir (absolute) |
| `OWRT` | OpenWrt build tree |
| `FLEET_SECRETS` | secrets file path |
| `OVERLAYS` | ordered overlay dirs (later wins on same path) |
| `SECRETS_VARS` | required secret var names, rendered as `__NAME__` |
| `CHMOD_FILES` | render-root-relative files to `chmod 0755` |

Steps every image runs: `fleet_require_secrets`, `fleet_render`,
`fleet_render_only_gate`, `fleet_seed_config`, `fleet_build`. The library
does no internal error checking (a failing `cp`/`sed`/`make` inside a
function isn't caught there) — the wrapper's `set -e` is what turns that
into a hard abort. Overlay files carrying `__NAME__` placeholders must be
TEXT (binary files are not excluded from the `sed -i` substitution), and
secret values must be SINGLE-LINE (`fleet_esc` escapes `\ & |` but not
newlines).

## Opt-in steps

- `fleet_image_id` — stamps `etc/gwifi-image-id`; OPT-IN, called only by
  gale (the netboot installer's idempotence marker). Must run AFTER
  `fleet_render_only_gate` — a timestamped id would dirty every render
  byte-diff.
- Forced rootfs rebuild and `out/` artifact copy + sidecar are NOT library
  steps: they stay inline in the gale wrapper because the paths involved
  are target-specific (`bin/targets/<target>/<subtarget>/...`). om2p and
  tenwrt opt out of all three (image-id, rootfs-force, `out/`).

## No-regression gates

Introduced while respecializing gale/om2p onto this base:

1. **Render byte-diff** — render the overlay with `RENDER_ONLY=1` from the
   pre-refactor tree and from base+specialization, byte-diff the two
   `files/` trees.
2. **defconfig diff** — post-`make defconfig` `.config` must also match.
3. **uci-op equivalence** — `tests/fleet-image/test-*-bootstrap-*.sh` run
   the bootstrap script against a `uci`-stub harness (`tests/fleet-image/
   uci-stub`) and diff the recorded op sequence against a golden log, so a
   thin driver over `bootstrap.sh` is proven to issue the same writes as
   the pre-refactor monolith.

Run them via `tests/fleet-image/test-build-lib.sh`,
`test-gale-bootstrap-equivalence.sh`, `test-tenwrt-bootstrap-ops.sh`.

## Adding a new image

1. Create `<name>-image/` with its own `files/` overlay and `<name>.config`
   fragment (packages layered after `base.config`).
2. Write `build-<name>-image.sh`: set the wrapper-contract variables, source
   `fleet-image/build-lib.sh`, call `fleet_require_secrets`, `fleet_render`,
   `fleet_render_only_gate`, then a target-lines generator function passed to
   `fleet_seed_config`, then `fleet_build`.
3. Write `verify-<name>-image.py` using `verify_lib.py` helpers (manifest
   package asserts, no-placeholder check, overlay-presence asserts).
4. Add a `tests/fleet-image/test-<name>-bootstrap-*.sh` if the image ships
   its own first-boot driver, with a golden op-log.
5. Document it in `<name>-image/README.md` (prerequisites, build/verify
   commands, secret handling, outputs).

## Secrets

All fleet images read the repo-external
`/home/tim/local/gwifi/fleet-secrets.conf` via `FLEET_SECRETS=`. **Built
images bake secrets and must never be published from `bin/targets/`** — the
gale wrapper publishes only from its own `gale-image/out/` (see that
README's "Secret handling" section for why `bin/targets` is unsafe to
publish from).
