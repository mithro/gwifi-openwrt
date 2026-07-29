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

# 3. service enabled + registered with procd
/etc/init.d/presence-detector enable
/etc/init.d/presence-detector restart
sleep 3
if ubus call service list '{{"name":"presence-detector"}}' | grep -q presence-detector; then
    result service OK running
else
    result service FAIL not-registered
fi

# 4. no fresh presence-detector errors in syslog (MQTT auth/connect failures land here)
errs=$(logread | grep presence-detector | tail -n 20 | grep -ci error)
if [ "$errs" = "0" ]; then
    result mqtt OK no-errors
else
    result mqtt FAIL "syslog-errors=$errs"
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
