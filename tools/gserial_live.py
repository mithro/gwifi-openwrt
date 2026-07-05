#!/usr/bin/env python3
"""Live hardware validation for gserial.py (EC/AP consoles over libusb).

Read-only. Runs the docstring's PENDING LIVE HARDWARE VALIDATION plan:
  1. EC round-trip: version + sysinfo, then repeat version to check no desync.
  2. AP console: open interface 1, read() (quiet while the AP is parked) with a
     clean timeout path and no exception.
  3. Kernel-driver reattach on close (reattach_kernel_driver=True) so the ttyUSB
     nodes return for the pyserial tools -- verified from the shell afterwards.

Exit 0 = every live check passed; nonzero = a check failed.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gserial  # noqa: E402

LOG = []


def logline(s):
    LOG.append(s)


def banner(t):
    print("\n===== %s =====" % t, flush=True)


def check(name, ok, detail=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" -- " + detail) if detail else ""), flush=True)
    return bool(ok)


def main():
    results = []

    banner("EC console (interface 0) round-trip")
    try:
        with gserial.GaleConsole(which='ec', logger=logline,
                                 reattach_kernel_driver=True) as ec:
            print("  bulk IN 0x%02x / bulk OUT 0x%02x on if%d" % (
                ec.bulk_in_address, ec.bulk_out_address,
                ec.interface_number), flush=True)

            t0 = time.time()
            v = ec.command('version')
            dt = time.time() - t0
            results.append(check(
                "version: prompt-terminated + banner",
                v.rstrip().endswith('>') and 'Chip:' in v and 'gale_v' in v,
                "%.3fs, %d chars" % (dt, len(v))))

            si = ec.command('sysinfo')
            flags = [ln.strip() for ln in si.splitlines()
                     if ln.strip().lower().startswith('flags:')]
            results.append(check(
                "sysinfo: has Flags line, prompt-terminated",
                bool(flags) and si.rstrip().endswith('>'),
                flags[0] if flags else "no Flags line"))

            n = 8
            ok_all = True
            times = []
            for i in range(n):
                t0 = time.time()
                r = ec.command('version')
                times.append(time.time() - t0)
                if not (r.rstrip().endswith('>') and 'gale_v' in r):
                    ok_all = False
                    print("    iter %d DESYNC tail=%r" % (i, r[-80:]),
                          flush=True)
            results.append(check(
                "%d repeated version round-trips, no desync" % n, ok_all,
                "per-cmd min %.3fs / max %.3fs" % (min(times), max(times))))
    except Exception as exc:  # noqa: BLE001 - report, don't crash the harness
        results.append(check("EC console session", False, repr(exc)))

    banner("AP console (interface 1) open + read")
    try:
        with gserial.GaleConsole(which='ap', logger=logline,
                                 reattach_kernel_driver=True) as ap:
            print("  bulk IN 0x%02x / bulk OUT 0x%02x on if%d" % (
                ap.bulk_in_address, ap.bulk_out_address,
                ap.interface_number), flush=True)
            got = bytearray()
            for _ in range(5):
                got += ap.read(200)
            # AP parked -> quiet is expected; the check is that if1 claims and
            # the timeout read path returns cleanly (no USBError leaked).
            results.append(check(
                "AP if1 claimed; read() timeout path clean", True,
                "%d bytes seen (0 expected while AP parked)" % len(got)))
    except Exception as exc:  # noqa: BLE001
        results.append(check("AP console session", False, repr(exc)))

    logdir = Path(__file__).resolve().parent / "tmp"
    logdir.mkdir(exist_ok=True)
    logpath = logdir / "gserial_live.log"
    logpath.write_text("\n".join(LOG))
    print("\n  transfer log (%d lines) -> %s" % (len(LOG), logpath), flush=True)

    banner("SUMMARY")
    npass = sum(1 for r in results if r)
    print("  %d/%d live checks passed" % (npass, len(results)), flush=True)
    return 0 if results and npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
