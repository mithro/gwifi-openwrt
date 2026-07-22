#!/bin/sh
# update-netaddr-oui.sh — refresh netaddr's bundled IEEE registries in the
# OpenWISP virtualenv and rebuild the prebuilt indexes.
#
# netaddr ships a static snapshot of the IEEE OUI/IAB registries frozen at
# package-release time, so recent allocations (e.g. Espressif 7c:2c:67)
# raise NotRegisteredError and openwisp-monitoring stores empty WifiClient
# vendors. IEEE publishes the live registries; netaddr's own
# netaddr.eui.ieee module rebuilds the .idx files from the .txt files.
#
# Runs as root (writes into the venv). Atomic per-file: download to .new,
# validate non-trivial size, then move into place; on any failure the
# previous files stay.
set -eu

ENV=/opt/openwisp2/env
EUI_DIR=$(ls -d "$ENV"/lib/python*/site-packages/netaddr/eui | head -1)
[ -d "$EUI_DIR" ] || { echo "netaddr eui dir not found under $ENV" >&2; exit 1; }

fetch() {
    url=$1; dest=$2
    curl -fsSL --retry 3 --max-time 300 -o "$dest.new" "$url"
    # sanity: the live registries are multi-MB; a stub/error page is not
    size=$(wc -c < "$dest.new")
    if [ "$size" -lt 1000000 ]; then
        echo "refusing $url: only $size bytes (expected >1MB)" >&2
        rm -f "$dest.new"
        return 1
    fi
    mv "$dest.new" "$dest"
}

echo "eui dir: $EUI_DIR"
fetch https://standards-oui.ieee.org/oui/oui.txt "$EUI_DIR/oui.txt"
# IAB registry moved into MA-S; netaddr still parses the legacy iab format.
# Failure to refresh iab is non-fatal (tiny, rarely-hit registry).
fetch https://standards-oui.ieee.org/iab/iab.txt "$EUI_DIR/iab.txt" \
    || echo "WARNING: iab.txt refresh failed; keeping previous copy" >&2

# Rebuild oui.idx/iab.idx from the txt files (netaddr's own tooling).
"$ENV/bin/python" -m netaddr.eui.ieee

# Prove the refresh took: a post-2024 Espressif allocation must resolve.
"$ENV/bin/python" - <<'EOF'
import netaddr
org = netaddr.EUI("7c-2c-67-00-00-01").oui.registration().org
print("verify 7c:2c:67 ->", org)
assert "Espressif" in org, f"unexpected org: {org!r}"
EOF
echo "netaddr OUI registry refreshed OK"
