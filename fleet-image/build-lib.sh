#!/bin/sh
# fleet-image/build-lib.sh — shared build steps for the fleet images
# (docs/fleet-image-base-design.md §4.1/§4.3). Sourced by each image's build
# wrapper AFTER it sets:
#   HERE          image dir (absolute)
#   OWRT          OpenWrt build tree
#   FLEET_SECRETS secrets file path
#   OVERLAYS      ordered overlay dirs (later wins on same path)
#   SECRETS_VARS  required variable names; rendered as __NAME__ placeholders
#   CHMOD_FILES   render-root-relative files to chmod 0755 (may be empty)
# Steps every image runs: fleet_require_secrets, fleet_render,
# fleet_render_only_gate, fleet_seed_config, fleet_build.
# OPT-IN step (today: gale only — spec §4.1): fleet_image_id. It must come
# AFTER the RENDER_ONLY gate (a timestamped id would dirty the render
# byte-diff gates). Target-specific extras — forced rootfs rebuild, out/
# artifact copy + sidecar — are NOT library steps: they stay inline in the
# image wrapper (gale) because the paths involved are target-specific
# (bin/targets/<target>/<subtarget>/...); om2p opts out of all three.
#
# Contract: callers MUST run under `set -eu`. This library does no internal
# error checking of its own (a failing cp/sed/cat/make inside a function is
# not caught here) — the wrapper's `set -e` is what turns that into a hard
# abort instead of a silently-incomplete render/build.
#
# Overlay files that carry __NAME__ placeholders must be TEXT files (sed -i
# is used for substitution; binary files are not excluded and will be
# corrupted if matched). Secret values substituted via SECRETS_VARS must be
# SINGLE-LINE: fleet_esc escapes sed replacement metacharacters (\, &, |) but
# NOT newlines — a multi-line secret breaks the `sed -i "s|...|...|g"` call.

fleet_require_secrets() {
	[ -f "$FLEET_SECRETS" ] || {
		echo "missing $FLEET_SECRETS (set FLEET_SECRETS=/home/tim/local/gwifi/fleet-secrets.conf or copy fleet-secrets.conf.example)" >&2
		exit 1
	}
	# shellcheck disable=SC1090
	. "$FLEET_SECRETS"
	for _v in $SECRETS_VARS; do
		# SECRETS_VARS is a static, developer-written identifier list (never
		# runtime/user input) — eval here only ever indirects through names
		# the wrapper hardcoded, so it is safe.
		eval "_val=\${$_v:-}"
		[ -n "$_val" ] || { echo "missing $_v in $FLEET_SECRETS" >&2; exit 1; }
	done
}

# Escape sed replacement metacharacters (\, &, |) so a secret containing them
# substitutes literally (backslash first, to avoid double-escaping).
fleet_esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/&/\\&/g' -e 's/|/\\|/g'; }

fleet_render() {
	[ -n "${OWRT:-}" ] || { echo "fleet_render: OWRT not set" >&2; exit 1; }
	rm -rf "$OWRT/files"
	mkdir -p "$OWRT/files"
	for _d in $OVERLAYS; do cp -a "$_d/." "$OWRT/files/"; done
	for _v in $SECRETS_VARS; do
		eval "_val=\${$_v}"
		_e=$(fleet_esc "$_val")
		find "$OWRT/files" -type f -exec sed -i "s|__${_v}__|$_e|g" {} +
	done
	for _f in ${CHMOD_FILES:-}; do chmod 0755 "$OWRT/files/$_f"; done
}

fleet_render_only_gate() {
	if [ "${RENDER_ONLY:-0}" = "1" ]; then
		echo "rendered overlay to $OWRT/files (RENDER_ONLY)"
		exit 0
	fi
}

fleet_image_id() {  # $1 = image name prefix (e.g. gale-openwrt). OPT-IN.
	IMAGE_ID="$1-$(date -u +%Y%m%d%H%M%S)-g$(git -C "$HERE" rev-parse --short HEAD)"
	printf '%s\n' "$IMAGE_ID" > "$OWRT/files/etc/gwifi-image-id"
	echo "image id: $IMAGE_ID"
}

fleet_seed_config() {  # $1 = function printing target lines; $2 = per-image fragment (relative to $HERE)
	{ "$1"; cat "$HERE/../fleet-image/base.config"; cat "$HERE/$2"; } > "$OWRT/.config"
	( cd "$OWRT" && make defconfig )
}

fleet_build() { ( cd "$OWRT" && make -j"${JOBS:-6}" ); }
