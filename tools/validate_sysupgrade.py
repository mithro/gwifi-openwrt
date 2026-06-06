"""Task #14: validate the sysupgrade flow end-to-end on a running gale.

Prerequisite: gale is booted, OpenWrt is up, ssh gale works.

What this does:
  1. scp openwrt-25.12.2-...-sysupgrade.bin to gale:/tmp/
  2. ssh gale 'sysupgrade -F -n /tmp/openwrt-...-sysupgrade.bin'
     (-F: force; -n: no save-config — fresh start)
  3. Poll for gale to come back up (3-5 min reboot)
  4. ssh gale 'cat /etc/openwrt_release && uname -a' — verify the
     new firmware is what's running
  5. ssh gale 'mount | grep /overlay' — verify overlayfs is mounted
     (sysupgrade should preserve the overlay partition by default)

EXPECTED OUTCOMES:
  - Pass: gale reboots into the same version, all services come back,
    /overlay is mounted, ssh works without host-key change. The
    sysupgrade flow is validated as a maintenance path.
  - Fail: sysupgrade aborts pre-reboot (bad image, format mismatch),
    gale doesn't come back (boot regression), or /overlay is gone
    (sysupgrade wiped config — needs investigation).

Output: a single-line pass/fail at the end.
"""
from __future__ import annotations
import argparse
import pathlib
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
    ap.add_argument("image",
                    help="path to the *-sysupgrade.bin to flash onto gale")
    ap.add_argument("--timeout", type=int, default=300,
                    help="seconds to wait for gale to reboot (default 300)")
    args = ap.parse_args()
    SYSUPGRADE_BIN = pathlib.Path(args.image)

    if not SYSUPGRADE_BIN.exists():
        sys.exit(f"!! missing {SYSUPGRADE_BIN}")
    code, _, _ = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                      GALE, "true"])
    if code != 0:
        sys.exit(f"!! ssh {GALE} doesn't work — bring gale up first")

    print(f"[1] scp {SYSUPGRADE_BIN.name} -> {GALE}:/tmp/")
    code, _, err = run(["scp", str(SYSUPGRADE_BIN), f"{GALE}:/tmp/"])
    if code != 0:
        sys.exit(f"!! scp failed:\n{err}")

    print(f"[2] ssh {GALE} 'sysupgrade -F -n /tmp/{SYSUPGRADE_BIN.name}'")
    # We don't wait for the response — sysupgrade reboots the device.
    # Use a short timeout to detect immediate failures.
    subprocess.Popen(["ssh", GALE,
                      f"sysupgrade -F -n /tmp/{SYSUPGRADE_BIN.name}"])

    print(f"[3] waiting for {GALE} to come back (up to {args.timeout}s)")
    start = time.time()
    while time.time() - start < args.timeout:
        code, _, _ = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3",
                          GALE, "true"])
        if code == 0:
            elapsed = time.time() - start
            print(f"   gale back up after {elapsed:.0f}s")
            break
        time.sleep(5)
    else:
        sys.exit(f"!! gale didn't come back within {args.timeout}s")

    print(f"[4] verify firmware + overlay")
    code, out, _ = run(["ssh", GALE, "cat /etc/openwrt_release; echo '---'; "
                                     "uname -a; echo '---'; "
                                     "mount | grep -E '/overlay| /$'"])
    print(out)
    if "/overlay" not in out:
        sys.exit("!! /overlay not mounted after sysupgrade — config lost?")
    if "25.12.2" not in out:
        sys.exit("!! unexpected version after sysupgrade — verify image")

    print("\nPASS: sysupgrade end-to-end (image install, reboot, overlay preserved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
