"""Task #18: stop the periodic gale reboots when AP is exercised.

Symptom (from earlier UART logs): ath10k-ct firmware logs
  "Firmware lacks feature flag indicating a retry limit of > 2 is OK,
   requested limit: 4"
then the SoC resets a few minutes later.

ROOT CAUSE: ath10k-ct (the community-maintained ath10k firmware) on
QCA4019 doesn't advertise the WMI feature bit for arbitrary retry
limits, but mac80211 / hostapd request a retry limit of 4 on this
hardware. The firmware enters a degraded state and the SoC eventually
watchdog-resets.

TWO FIXES (we apply both — they're independent and complementary):

Fix A (USER-SPACE, hostapd config): clamp the retry limit to 2 in
hostapd's per-AP config. UCI:
  uci set wireless.@wifi-iface[0].user_short_retry=2
  uci set wireless.@wifi-iface[0].user_long_retry=2
  uci commit wireless
  wifi reload

Fix B (FIRMWARE swap): replace ath10k-ct firmware with the upstream
"non-CT" firmware which DOES advertise the feature flag and accepts
retry limit > 2. OpenWrt package: ath10k-firmware-qca4019 (non-CT
flavor). Steps:
  opkg update
  opkg remove ath10k-ct-firmware-qca4019  (or similar; depends on what's installed)
  opkg install ath10k-firmware-qca4019
  reboot

Fix A is reversible via uci revert. Fix B is more permanent and is
what we want long-term. We do A immediately so the user can run their
AP for hours while we wait for the right moment to swap firmware.

Prereq: gale booted, ssh gale works.

This script just applies Fix A and reminds the user about Fix B.
Verifying stability requires actually running the AP for hours —
that's a manual check after this script returns.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time

GALE = "gale"


def run(cmd, **kw) -> tuple[int, str, str]:
    print(f"  $ {' '.join(str(c) for c in cmd)[:200]}")
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swap-firmware", action="store_true",
                    help="also perform Fix B (replace ath10k-ct with upstream)")
    args = ap.parse_args()

    code, _, _ = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                      GALE, "true"])
    if code != 0:
        sys.exit(f"!! ssh {GALE} not working — bring gale up first")

    print("[Fix A] clamp retry limits in hostapd config")
    cmd = ("uci set wireless.@wifi-iface[0].user_short_retry=2 && "
           "uci set wireless.@wifi-iface[0].user_long_retry=2 && "
           "uci commit wireless && "
           "wifi reload && "
           "sleep 3 && "
           "iw dev | grep -A1 Interface")
    code, out, err = run(["ssh", GALE, cmd])
    if code != 0:
        sys.exit(f"!! Fix A failed:\n{out}\n{err}")
    print(out)

    if args.swap_firmware:
        print("[Fix B] swap ath10k-ct for upstream ath10k-firmware-qca4019")
        cmd = ("opkg update && "
               "opkg list-installed | grep ath10k && "
               "opkg remove ath10k-firmware-qca4019-ct kmod-ath10k-ct && "
               "opkg install ath10k-firmware-qca4019 kmod-ath10k && "
               "echo 'rebooting in 5s'; sleep 5; reboot")
        code, out, err = run(["ssh", GALE, cmd])
        print(out)
        if code != 0:
            sys.exit(f"!! Fix B failed:\n{out}\n{err}")
        print("waiting 60s for gale to come back...")
        time.sleep(60)
        code, _, _ = run(["ssh", GALE, "true"])
        if code != 0:
            print("!! gale didn't reboot cleanly after Fix B — investigate")
            return 1

    print("\nPASS: retry-limit clamp applied" +
          (" + firmware swapped" if args.swap_firmware else ""))
    print("Run AP for >2h to verify stability is restored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
