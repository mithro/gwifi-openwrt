#!/bin/sh
# build-lib.sh: overlay merge order (image overrides base), placeholder
# substitution (incl. sed metachars in secrets), chmod list, required-var
# enforcement, RENDER_ONLY gate.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
mkdir -p "$ROOT/tmp"
SB=$(mktemp -d "$ROOT/tmp/buildlib.XXXXXX") || exit 1
trap 'rm -rf "$SB"' EXIT INT TERM
fails=0
eq() { if [ "$2" = "$3" ]; then printf '  PASS %s\n' "$1"; \
       else printf '  FAIL %s (want [%s] got [%s])\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

mkdir -p "$SB/base/etc" "$SB/img/etc" "$SB/owrt"
printf 'base __OPENWISP_URL__\n' > "$SB/base/etc/shared"     # image overrides this
printf 'img __OPENWISP_SHARED_SECRET__\n' > "$SB/img/etc/shared"
printf 'only __OPENWISP_URL__\n' > "$SB/base/etc/baseonly"
cat > "$SB/secrets.conf" <<'EOF'
OPENWISP_URL="https://wisp.example"
OPENWISP_SHARED_SECRET="p&ss|w\0rd"
EOF

run_render() { (
	set -e
	HERE="$SB/img"; OWRT="$SB/owrt"; FLEET_SECRETS="$SB/secrets.conf"
	OVERLAYS="$SB/base $SB/img"; SECRETS_VARS="OPENWISP_URL OPENWISP_SHARED_SECRET"
	CHMOD_FILES="etc/baseonly"
	. "$ROOT/fleet-image/build-lib.sh"
	fleet_require_secrets
	fleet_render
) }
run_render || { echo "FAIL: render rc!=0"; exit 1; }

eq "image overrides base"  'img p&ss|w\0rd' "$(cat "$SB/owrt/files/etc/shared")"
eq "base-only substituted" 'only https://wisp.example' "$(cat "$SB/owrt/files/etc/baseonly")"
perms=$(stat -c %a "$SB/owrt/files/etc/baseonly")
eq "chmod applied" "755" "$perms"

# missing required var -> hard fail
if ( HERE="$SB/img" OWRT="$SB/owrt" FLEET_SECRETS="$SB/secrets.conf" \
     OVERLAYS="$SB/base" SECRETS_VARS="OPENWISP_URL NOSUCH_VAR" CHMOD_FILES=""; \
     . "$ROOT/fleet-image/build-lib.sh"; fleet_require_secrets ) 2> "$SB/missing-var.stderr"; then
	echo "  FAIL missing-var not rejected"; fails=$((fails+1))
else printf '  PASS missing var rejected\n'; fi

# fleet_render with OWRT unset -> hard fail (guard before the rm -rf)
if ( unset OWRT; HERE="$SB/img"; FLEET_SECRETS="$SB/secrets.conf"; \
     OVERLAYS="$SB/base"; SECRETS_VARS="OPENWISP_URL"; CHMOD_FILES=""; \
     . "$ROOT/fleet-image/build-lib.sh"; fleet_require_secrets; fleet_render ) \
     2> "$SB/owrt-unset.stderr"; then
	echo "  FAIL fleet_render with OWRT unset not rejected"; fails=$((fails+1))
else printf '  PASS fleet_render rejects unset OWRT\n'; fi

[ "$fails" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "$fails FAILED"; exit 1; }
