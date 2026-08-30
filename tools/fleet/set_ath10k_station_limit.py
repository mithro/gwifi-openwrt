#!/usr/bin/env python3
"""Apply an ath10k-ct fwcfg to a puck via WRITE + REBOOT, verifying health.

WHY REBOOT, NOT A MODULE RELOAD
-------------------------------
fwcfg is read in ath10k_core_probe_fw() (core.c:4036), i.e. at driver PROBE,
so `wifi reload` and `wifi down/up` never re-read it.  A module reload does
re-probe -- and the fwcfg IS parsed -- but on this hardware
`rmmod/modprobe ath10k_pci` leaves the radio unable to bring up more than ONE
BSS per phy: hostapd then loops on "Failed to set beacon parameters" and only
2 of 6 interfaces appear.  Proven on puck12 2026-08-24 with the fwcfg REMOVED
and again with a stations-only fwcfg (no firmware-side change at all), so it
is the reload, not the values.  Only a reboot restores all 6 BSSes.

This also means an earlier conclusion was WRONG: peers=80/tids=160 appearing
to "break beacons" was the reload, not the value.  The only value failure
actually observed is peers=144/tids=288 -> "wmi unified ready event not
received" / "could not init core (-110)" and NO phy at all.

Usage: set_ath10k_station_limit.py <host> <stations> [peers] [tids]
       set_ath10k_station_limit.py <host> --clear

Fleet values are stations=64 peers=80 tids=160 (see gale-image/files/ and
the openwisp ansells-aps-base template, which ship the same file).
"""
import subprocess
import sys
import time

RADIOS = ["a000000.wifi", "a800000.wifi"]
EXPECT_IFACES = 6


def ssh(host, cmd, stdin=None, timeout=120):
    r = subprocess.run(
        ["ssh", "-4", "-o", "ConnectTimeout=20", "-o", "BatchMode=yes",
         "-o", "StrictHostKeyChecking=accept-new", f"root@{host}", cmd],
        input=stdin, capture_output=True, text=True, timeout=timeout)
    for ln in r.stderr.splitlines():
        if "clipboard" not in ln and ln.strip():
            print(f"    stderr: {ln}", file=sys.stderr)
    return r.returncode, r.stdout.strip()


def wait_back(host, budget=420):
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        rc, out = ssh(host, "echo ifaces=$(iw dev | grep -c Interface); "
                            "echo beacon=$(logread | grep -c 'Failed to set beacon'); "
                            "echo up=$(cut -d. -f1 /proc/uptime)", timeout=40)
        if rc == 0 and "ifaces=" in out:
            return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
        time.sleep(15)
    return None


def main():
    host = sys.argv[1]
    clearing = sys.argv[2] == "--clear"
    if clearing:
        body, label = None, "CLEAR"
    else:
        lines = [f"stations={sys.argv[2]}"]
        if len(sys.argv) > 3:
            lines.append(f"peers={sys.argv[3]}")
        if len(sys.argv) > 4:
            lines.append(f"tids={sys.argv[4]}")
        body = ("# ath10k-ct fwcfg -- read at driver probe (core.c:4036).\n"
                "# stations is driver-side only; peers/tids resize FIRMWARE\n"
                "# tables (wmi.c:7610-7611,7431).  peers=144/tids=288 makes the\n"
                "# firmware miss its ready event and NO phy registers.\n"
                + "\n".join(lines) + "\n")
        label = " ".join(lines)

    print(f"[{host}] {label}")
    for radio in RADIOS:
        if clearing:
            ssh(host, f"rm -f /lib/firmware/ath10k/fwcfg-ahb-{radio}.txt")
        else:
            ssh(host, f"cat > /lib/firmware/ath10k/fwcfg-ahb-{radio}.txt", stdin=body)

    # sync first: the fwcfg lives on the overlay and a reboot racing an
    # unflushed write would silently lose it, leaving the puck at defaults
    # while looking like the change was applied.
    ssh(host, "sync; sleep 1; sync")
    ssh(host, "(sleep 2; reboot) >/dev/null 2>&1 & echo scheduled", timeout=60)
    print("  rebooting…")
    time.sleep(45)
    st = wait_back(host)
    if st is None:
        print("  DID NOT COME BACK", file=sys.stderr)
        return 1

    print(f"  ifaces={st.get('ifaces')} beacon_errors={st.get('beacon')} "
          f"uptime={st.get('up')}s")
    ok = st.get("ifaces") == str(EXPECT_IFACES) and st.get("beacon") == "0"
    if not ok:
        # Auto-recover: a value the firmware cannot allocate leaves the AP off
        # the air (no phy at all, as peers=144 did), so never leave it stranded.
        print("  UNHEALTHY -- clearing fwcfg and rebooting back to defaults",
              file=sys.stderr)
        if clearing:
            return 2
        for radio in RADIOS:
            ssh(host, f"rm -f /lib/firmware/ath10k/fwcfg-ahb-{radio}.txt")
        ssh(host, "(sleep 2; reboot) >/dev/null 2>&1 & echo scheduled", timeout=60)
        time.sleep(45)
        back = wait_back(host)
        print(f"  recovered: {back}", file=sys.stderr)
        return 2
    if not clearing:
        _, applied = ssh(host, "dmesg | grep 'fwcfg key' | tail -4")
        print(f"  applied:\n{applied}")
    print("  OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
