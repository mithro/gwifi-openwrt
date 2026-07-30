# SPDX-License-Identifier: Apache-2.0
"""Pure logic for the presence-detector fleet deploy.

deploy_presence.py does the ssh I/O; this module builds the remote sh script
and parses its RESULT lines.  Fail loud on malformed output (house rule).
"""

PACKAGES: tuple[str, ...] = ("python3", "python3-paho-mqtt")
STEPS: tuple[str, ...] = ("files", "apk", "service", "mqtt")

_SCRIPT = """\
set -u
result() {{ echo "RESULT $1 $2 $3"; }}

# 1. template files must already be delivered (runbook orders template first)
missing=""
for f in /opt/presence-detector/presence-detector.py \\
         /etc/presence-detector/settings.json \\
         /etc/init.d/presence-detector; do
    [ -e "$f" ] || missing="$missing $f"
done
if [ -n "$missing" ]; then
    result files FAIL "missing:$missing"
else
    result files OK -
fi

# 2. packages (apk exit code is authoritative; output goes to stderr for the log)
if apk update >&2 && apk add {packages} >&2; then
    result apk OK installed
else
    result apk FAIL "apk-exit=$?"
fi

# 3. service enabled + registered with procd (poll: startup is not instant)
/etc/init.d/presence-detector enable
/etc/init.d/presence-detector restart
registered=""
i=0
while [ "$i" -lt 15 ]; do
    if ubus call service list '{{"name":"presence-detector"}}' | grep -q presence-detector; then
        registered="yes"
        break
    fi
    i=$((i + 1))
    sleep 1
done
if [ -n "$registered" ]; then
    result service OK running
else
    result service FAIL not-registered
fi

# 4. positive-evidence syslog check: absence of "error" is not proof of health
# if there is no log evidence at all (logread empty/missing, service not yet
# logging).  The vendored script logs "Starting ubus watchers on interfaces
# ..." at startup, "MQTT broker seems to be offline, sleeping..." on
# broker-connect failure, and publish failures as lines containing "Error".
#
# POLL rather than sample once: the daemon connects to the broker and runs its
# first station sync AFTER procd reports it registered, so a single immediate
# read races startup and reports a healthy deploy as no-log-evidence (observed
# on all six pucks during the 2026-07-30 rollout).
i=0
lines=""
while [ "$i" -lt 20 ]; do
    lines=$(logread | grep presence-detector | tail -n 40)
    [ -n "$lines" ] && break
    i=$((i + 1))
    sleep 1
done
if [ -z "$lines" ]; then
    result mqtt FAIL no-log-evidence
elif printf '%s\\n' "$lines" | grep -Eqi 'error|offline, sleeping'; then
    result mqtt FAIL errors-in-log
else
    result mqtt OK log-evidence
fi
"""


def build_install_script() -> str:
    """The sh script run on each puck over ssh (stdin)."""
    return _SCRIPT.format(packages=" ".join(PACKAGES))


def parse_results(text: str) -> dict[str, tuple[bool, str]]:
    """Parse RESULT lines into {step: (ok, detail)}; raise on drift."""
    out: dict[str, tuple[bool, str]] = {}
    for line in text.splitlines():
        if not line.startswith("RESULT "):
            continue
        parts = line.split(None, 3)
        if len(parts) != 4 or parts[2] not in ("OK", "FAIL"):
            raise ValueError(f"malformed RESULT line: {line!r}")
        _, step, verdict, detail = parts
        if step in out:
            raise ValueError(f"duplicate RESULT for step {step!r}")
        out[step] = (verdict == "OK", detail)
    missing = [s for s in STEPS if s not in out]
    if missing:
        raise ValueError(f"missing RESULT for step(s): {', '.join(missing)}")
    return out
