#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# SPDX-License-Identifier: Apache-2.0
"""Clean PoE cold-boot of the rpi3b-gwifi flash rig (via the Netgear "s1" switch).

Order of operations:
  1. Pre-flight  -- confirm the welland VPN / switch is reachable (SNMP), then
     VALIDATE the rig's PoE port: ifAlias name, VLAN (PVID) 90, PoE admin-enabled
     and PoE *delivering power* must ALL agree on the same ifIndex. Ports move;
     never trust a remembered index.
  2. Shutdown    -- ssh the rig and 'sudo shutdown -h now', then POLL until it
     stops answering ssh (a real halt) so power is only cut once the OS is down.
     If the rig can't be reached to run shutdown, ABORT unless --force.
  3. Power cycle -- SNMP PoE off -> wait -> on (POWER-ETHERNET-MIB adminEnable).
  4. Recovery    -- POLL for PoE to deliver again, then POLL ssh until the rig
     answers, tolerating the boot window where ssh is refused / times out.

Deliberately does NOT touch USB / the gale EC -- verifying that is a separate job.

Communities default to the switch's standard values and can be overridden via
the environment (these are the well-known SNMP defaults, not real secrets):
  RIG_SNMP_READ_COMMUNITY   (default 'public')
  RIG_SNMP_WRITE_COMMUNITY  (default 'private')

The switch and the rig are reliable: if a cycle misbehaves, the bug is in THIS
script (a too-short timeout, a missed poll, a mis-parsed response) -- fix it here.
Progress prints at least every ~30 s and every line is flushed.

Usage:
  rig_power_cycle.py [--dry-run] [--force] [--ifindex N]
                     [--off-seconds S] [--recovery-timeout S]
Exit codes: 0 ok / 2 validation or reachability failure / 3 came back but ssh
never answered / 4 aborted (needs --force) / 5 write community missing/rejected.
"""
import argparse
import os
import subprocess
import sys
import time

SWITCH = "10.1.5.22"
SWITCH_NAME = "sw-netgear-gsm7252ps-s1"
RIG = "rpi3b-gwifi.iot.welland.mithis.com"
EXPECT_IFALIAS = "eth0.rpi3b-gwifi"
EXPECT_PVID = "90"
LAST_KNOWN_IFINDEX = 4

# Numeric OIDs (no MIB files needed). PoE columns are indexed group.port ("1.<port>").
OID_IFALIAS = "1.3.6.1.2.1.31.1.1.1.18"        # ifAlias.<ifIndex>
OID_PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1"        # dot1qPvid.<ifIndex>
OID_POE_ADMIN = "1.3.6.1.2.1.105.1.1.1.3.1"    # pethPsePortAdminEnable.1.<port>  1=on 2=off
OID_POE_DETECT = "1.3.6.1.2.1.105.1.1.1.6.1"   # pethPsePortDetectionStatus.1.<port>  3=delivering
OID_SYSUP = "1.3.6.1.2.1.1.3.0"                # sysUpTime.0 (reachability probe)

READ = os.environ.get("RIG_SNMP_READ_COMMUNITY", "public")
WRITE = os.environ.get("RIG_SNMP_WRITE_COMMUNITY", "private")


def log(msg):
    print(msg, flush=True)


def die(msg, code=2):
    print("FATAL: " + msg, flush=True)
    sys.exit(code)


def _run(cmd, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout
    except FileNotFoundError as e:
        die("required tool not found: %s (%s)" % (cmd[0], e))


# ---------------------------------------------------------------- SNMP helpers
def snmp_get(oid, community=None, timeout=8):
    community = community or READ
    rc, out, err = _run(
        ["snmpget", "-v2c", "-c", community, "-Ovq", "-t", "3", "-r", "1",
         SWITCH, oid], timeout)
    if rc != 0:
        return None, (out + err).strip()
    return out.strip().strip('"'), None


def snmp_set_int(oid, value, timeout=10):
    if not WRITE:
        die("RIG_SNMP_WRITE_COMMUNITY is not set -- required to change PoE power "
            "(export it; never store it in a file).", code=5)
    rc, out, err = _run(
        ["snmpset", "-v2c", "-c", WRITE, "-t", "3", "-r", "1",
         SWITCH, oid, "i", str(value)], timeout)
    return rc == 0, (out + err).strip()


def find_ifindex_by_alias():
    rc, out, err = _run(
        ["snmpbulkwalk", "-v2c", "-c", READ, "-Oqn", "-t", "3", "-r", "1",
         SWITCH, OID_IFALIAS], timeout=45)
    if rc != 0:
        die("could not walk ifAlias to find the rig's port: %s" % (out + err).strip())
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip().strip('"') == EXPECT_IFALIAS:
            return int(parts[0].rsplit(".", 1)[1])
    die("no switch port has ifAlias %r -- has the rig been re-cabled/renamed?"
        % EXPECT_IFALIAS)


# ------------------------------------------------------------- SSH reachability
def ssh_probe(timeout=12):
    """Classify the rig's reachability. Returns (state, detail):
      up          ssh worked, rig answered
      unreachable ssh refused / timed out (rig down, halted, or still booting)
      authfail    sshd answered but auth failed (missing/rejected key, host-key)
      dnsfail     hostname won't resolve (DNS / welland VPN down)
      netfail     no route / network unreachable (VPN down)
    """
    rc, out, err = _run(
        ["ssh", "-4", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
         "-o", "StrictHostKeyChecking=accept-new", RIG, "echo RIG_SSH_OK"],
        timeout)
    if "RIG_SSH_OK" in out:
        return "up", None
    blob = (out + err).lower()
    if ("could not resolve" in blob or "name or service not known" in blob
            or "nodename nor servname" in blob or "temporary failure in name" in blob):
        return "dnsfail", (out + err).strip()
    if "no route to host" in blob or "network is unreachable" in blob:
        return "netfail", (out + err).strip()
    if ("permission denied" in blob or "publickey" in blob
            or "no such identity" in blob or "host key verification failed" in blob
            or "too many authentication failures" in blob):
        return "authfail", (out + err).strip()
    return "unreachable", (out + err).strip()


def explain_ssh_state(state):
    return {
        "dnsfail": "cannot resolve %s -- is the welland VPN up?" % RIG,
        "netfail": "no route to %s -- is the welland VPN up?" % RIG,
        "authfail": "ssh auth failed -- missing/rejected key or host-key change",
        "unreachable": "ssh refused/timed out (rig down, halted, or still booting)",
    }.get(state, state)


# --------------------------------------------------------------- major stages
def preflight_switch():
    log("[1/4] pre-flight: switch %s (%s) reachable over SNMP?" % (SWITCH, SWITCH_NAME))
    up, err = snmp_get(OID_SYSUP)
    if up is None:
        die("switch %s did not answer SNMP (%s).\n"
            "  Likely the welland VPN is down, or the read community is wrong "
            "(RIG_SNMP_READ_COMMUNITY)." % (SWITCH, err), code=2)
    log("  switch is up (sysUpTime=%s). read community OK." % up)


def validate_port(ifindex_override):
    log("[2/4] validating the rig's PoE port (ports move -- all checks must agree)")
    if ifindex_override:
        idx = ifindex_override
        log("  using --ifindex %d" % idx)
    else:
        idx = LAST_KNOWN_IFINDEX
        alias, _ = snmp_get("%s.%d" % (OID_IFALIAS, idx))
        if alias != EXPECT_IFALIAS:
            log("  ifIndex %d ifAlias=%r != %r -- searching for the real port..."
                % (idx, alias, EXPECT_IFALIAS))
            idx = find_ifindex_by_alias()
            log("  found ifAlias %r on ifIndex %d" % (EXPECT_IFALIAS, idx))

    alias, _ = snmp_get("%s.%d" % (OID_IFALIAS, idx))
    pvid, _ = snmp_get("%s.%d" % (OID_PVID, idx))
    admin, _ = snmp_get("%s.%d" % (OID_POE_ADMIN, idx))
    detect, _ = snmp_get("%s.%d" % (OID_POE_DETECT, idx))
    checks = [
        ("ifAlias", alias, EXPECT_IFALIAS, alias == EXPECT_IFALIAS),
        ("PVID", pvid, EXPECT_PVID, str(pvid) == EXPECT_PVID),
        ("PoE admin", admin, "1 (enabled)", str(admin) == "1"),
        ("PoE detect", detect, "3 (delivering)", str(detect) == "3"),
    ]
    for name, got, want, ok in checks:
        log("    %-11s ifIndex %d = %-22s want %-16s %s"
            % (name, idx, repr(got), want, "OK" if ok else "<-- MISMATCH"))
    if not all(ok for *_, ok in checks):
        die("port validation FAILED -- refusing to cut power on the wrong port.\n"
            "  Walk the cable / re-check the switch, or pass --ifindex once verified.",
            code=2)
    log("  port validated: ifIndex %d (physical port 1/0/%d), delivering power." % (idx, idx))
    return idx


def test_write_community(idx):
    """Confirm the write community works with a true no-op (set admin to its
    current value) BEFORE we halt the rig -- so we never strand it powered-off."""
    log("  confirming write community (harmless no-op set)...")
    cur, _ = snmp_get("%s.%d" % (OID_POE_ADMIN, idx))
    ok, detail = snmp_set_int("%s.%d" % (OID_POE_ADMIN, idx), cur or 1)
    if not ok:
        die("write community rejected by the switch (%s).\n"
            "  Check RIG_SNMP_WRITE_COMMUNITY." % detail, code=5)
    log("  write community OK.")


def clean_shutdown(force):
    log("[3/4] clean shutdown of the rig")
    state, detail = ssh_probe()
    if state == "up":
        log("  rig reachable; issuing 'sudo shutdown -h now'")
        _run(["ssh", "-4", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
              "-o", "StrictHostKeyChecking=accept-new", RIG, "sudo shutdown -h now"],
             timeout=15)
        log("  polling until the rig stops answering ssh (real halt)...")
        t0 = last = time.time()
        while time.time() - t0 < 120:
            time.sleep(5)
            st, _ = ssh_probe(timeout=8)
            el = int(time.time() - t0)
            if st != "up":
                log("  rig stopped answering ssh after %ds -- halted." % el)
                time.sleep(3)  # let the OS finish flushing before we cut power
                return
            if time.time() - last >= 30:
                log("  [+%ds] rig still up, waiting for halt..." % el)
                last = time.time()
        log("  rig still answered ssh after 120s; proceeding to cut power anyway.")
        return
    # Could not reach the rig to shut it down.
    if force:
        log("  rig NOT reachable for clean shutdown (%s) -- --force given, "
            "hard power-cycling." % explain_ssh_state(state))
        return
    die("cannot run 'shutdown' on the rig: %s.\n"
        "  Nothing was changed. Re-run with --force to hard power-cycle the rig "
        "without a clean shutdown." % explain_ssh_state(state), code=4)


def poe_cycle(idx, off_seconds):
    log("[4/4] power cycle: PoE off %ds -> on (port 1/0/%d)" % (off_seconds, idx))
    ok, detail = snmp_set_int("%s.%d" % (OID_POE_ADMIN, idx), 2)
    if not ok:
        die("failed to set PoE OFF: %s" % detail, code=5)
    # Poll-confirm it actually went to admin-disabled.
    for _ in range(5):
        v, _ = snmp_get("%s.%d" % (OID_POE_ADMIN, idx))
        if str(v) == "2":
            break
        time.sleep(1)
    log("  PoE OFF confirmed; waiting %ds..." % off_seconds)
    t0 = time.time()
    while time.time() - t0 < off_seconds:
        time.sleep(2)
    ok, detail = snmp_set_int("%s.%d" % (OID_POE_ADMIN, idx), 1)
    if not ok:
        die("failed to set PoE ON: %s -- RIG MAY BE POWERED OFF, retry the ON set!"
            % detail, code=5)
    for _ in range(5):
        v, _ = snmp_get("%s.%d" % (OID_POE_ADMIN, idx))
        if str(v) == "1":
            break
        time.sleep(1)
    log("  PoE ON.")


def wait_recovery(idx, recovery_timeout):
    # (a) PoE delivering again.
    log("  waiting for the switch to deliver PoE again...")
    t0 = last = time.time()
    while time.time() - t0 < 60:
        d, _ = snmp_get("%s.%d" % (OID_POE_DETECT, idx))
        el = int(time.time() - t0)
        if str(d) == "3":
            log("  PoE delivering power (%ds)." % el)
            break
        if time.time() - last >= 30:
            log("  [+%ds] PoE not delivering yet (detect=%s), polling..." % (el, d))
            last = time.time()
        time.sleep(4)
    # (b) ssh answers.
    log("  waiting for the rig to boot + answer ssh (up to %ds)..." % recovery_timeout)
    t0 = last = time.time()
    last_state = None
    while time.time() - t0 < recovery_timeout:
        st, detail = ssh_probe(timeout=8)
        el = int(time.time() - t0)
        if st == "up":
            log("  RIG IS BACK: answering ssh %ds after power-on." % el)
            return 0, st
        if st != last_state:
            log("  [+%ds] ssh: %s" % (el, explain_ssh_state(st)))
            last_state = st
        elif time.time() - last >= 30:
            log("  [+%ds] still waiting (%s), polling..." % (el, st))
            last = time.time()
        time.sleep(6)
    log("  rig did NOT answer ssh within %ds of power-on (last state: %s)."
        % (recovery_timeout, explain_ssh_state(last_state or "unknown")))
    return 3, last_state


def main():
    ap = argparse.ArgumentParser(description="Clean PoE cold-boot of rpi3b-gwifi.")
    ap.add_argument("--dry-run", action="store_true",
                    help="pre-flight + port validation only; change nothing")
    ap.add_argument("--force", action="store_true",
                    help="hard power-cycle even if the rig can't be cleanly shut down")
    ap.add_argument("--ifindex", type=int, default=None,
                    help="override the switch ifIndex (still validated)")
    ap.add_argument("--off-seconds", type=int, default=8,
                    help="how long to hold PoE off (default 8)")
    ap.add_argument("--recovery-timeout", type=int, default=240,
                    help="max seconds to wait for ssh after power-on (default 240)")
    args = ap.parse_args()

    log("=== rig_power_cycle: %s via %s ===" % (RIG, SWITCH_NAME))
    log("    started %s  (dry_run=%s force=%s)"
        % (time.strftime("%Y-%m-%d %H:%M:%S"), args.dry_run, args.force))
    wall0 = time.time()

    preflight_switch()
    idx = validate_port(args.ifindex)

    if args.dry_run:
        log("dry-run: validation passed; not shutting down or cycling power.")
        return 0

    test_write_community(idx)
    clean_shutdown(args.force)
    poe_cycle(idx, args.off_seconds)
    code, state = wait_recovery(idx, args.recovery_timeout)

    dt = int(time.time() - wall0)
    if code == 0:
        log("=== DONE: rig power-cycled and back up in %ds. (USB/EC not checked "
            "-- that's a separate step.) ===" % dt)
    else:
        log("=== INCOMPLETE after %ds: power was cycled but the rig isn't "
            "answering ssh (%s). It may still be booting -- re-probe, and if it "
            "persists check the rig/VPN. ===" % (dt, explain_ssh_state(state or "?")))
    return code


if __name__ == "__main__":
    sys.exit(main())
