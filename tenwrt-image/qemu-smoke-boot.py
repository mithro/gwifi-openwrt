#!/usr/bin/env python3
"""qemu-smoke-boot.py — headless boot test for the ten64 Wi-Fi VM image.

Boots the built combined-efi.img under qemu-system-aarch64 (-M virt) and asserts the
image reaches first-boot: the kernel boots to userspace and 99-tenwrt-bootstrap prints its
completion marker on the serial console. No radio is required. KVM is used on aarch64
hosts; TCG otherwise. SKIPs (exit 0) if qemu or UEFI firmware is unavailable.

After boot, also asserts graceful ACPI shutdown: the image ships acpid (power button ->
/sbin/poweroff), so this is the same mechanism `virsh shutdown` (mode=acpi) uses. Once the
guest has booted, a QMP `system_powerdown` command injects the ACPI power button event; with
-no-reboot, a successful guest poweroff exits qemu, which this script waits for (up to
SMOKE_SHUTDOWN_TIMEOUT seconds). Set SMOKE_ACPI=0 to skip this phase and PASS on boot alone
(the pre-Task-10 behaviour).

Env knobs: SMOKE_TIMEOUT (boot phase, default 360s), SMOKE_SHUTDOWN_TIMEOUT (shutdown phase,
default 180s), SMOKE_ACPI=0 to disable the shutdown assertion.

Usage: uv run python tenwrt-image/qemu-smoke-boot.py [path/to/combined-efi.img]
"""
import glob
import gzip
import os
import platform
import select
import shutil
import subprocess
import sys
import time

OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt-armsr")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/armsr/armv8")
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp")
MARKER = "TENVM-BOOTSTRAP-COMPLETE"
BOOT_FALLBACK = "procd: - init complete -"     # accept as a weaker "kernel booted" signal
TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "360"))
SHUTDOWN_TIMEOUT = int(os.environ.get("SMOKE_SHUTDOWN_TIMEOUT", "180"))
ACPI_CHECK = os.environ.get("SMOKE_ACPI", "1") != "0"
MARKER_SETTLE = 30     # seconds to wait after MARKER for BOOT_FALLBACK before powering down anyway

# Prefer unified firmware images (usable directly via -bios); the split AAVMF_CODE.fd is
# last because it really wants a paired varstore.
FIRMWARE_CANDIDATES = [
    "/usr/share/qemu-efi-aarch64/QEMU_EFI.fd",
    "/usr/share/edk2/aarch64/QEMU_EFI.fd",
    "/usr/share/AAVMF/QEMU_EFI.fd",
    "/usr/share/qemu/edk2-aarch64-code.fd",
    "/usr/share/AAVMF/AAVMF_CODE.fd",
]


def skip(msg):
    print("SKIP: %s" % msg)
    sys.exit(0)


def qmp_powerdown(sock_path):
    """Connect to the QMP socket and inject the ACPI power button."""
    import json
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(10)          # a wedged-but-alive qemu must not hang readline() forever
    s.connect(sock_path)
    f = s.makefile("rw")
    f.readline()                                              # greeting banner
    f.write(json.dumps({"execute": "qmp_capabilities"}) + "\n"); f.flush()
    f.readline()                                              # {"return": {}}
    f.write(json.dumps({"execute": "system_powerdown"}) + "\n"); f.flush()
    s.close()


def find_image(argv):
    if len(argv) > 1:
        return argv[1]
    raw = sorted(glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img")))
    if raw:
        return raw[0]
    gz = sorted(glob.glob(os.path.join(IMAGE_DIR, "*combined-efi.img.gz")))
    if gz:
        os.makedirs(TMP, exist_ok=True)
        out = os.path.join(TMP, os.path.basename(gz[0])[:-3])
        with gzip.open(gz[0], "rb") as fi, open(out, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        return out
    return None


def main():
    qemu = shutil.which("qemu-system-aarch64")
    if not qemu:
        skip("qemu-system-aarch64 not found (apt install qemu-system-arm), or run on ten64")
    fw = next((f for f in FIRMWARE_CANDIDATES if os.path.isfile(f)), None)
    if not fw:
        skip("no aarch64 UEFI firmware found (apt install qemu-efi-aarch64); tried %s"
             % ", ".join(FIRMWARE_CANDIDATES))
    img = find_image(sys.argv)
    if not img or not os.path.isfile(img):
        sys.exit("ERROR: no combined-efi.img found in %s (build first)" % IMAGE_DIR)

    os.makedirs(TMP, exist_ok=True)
    disk = os.path.join(TMP, "smoke-disk.img")
    shutil.copyfile(img, disk)           # writable copy (UEFI/grub may write vars/state)
    cleanup = [disk]
    # if find_image decompressed a .gz into ./tmp, remove that scratch copy too
    if os.path.abspath(img).startswith(os.path.abspath(TMP) + os.sep):
        cleanup.append(img)

    qmp_sock = os.path.join(TMP, "smoke-qmp.sock")
    if os.path.exists(qmp_sock):
        os.remove(qmp_sock)          # stale socket from a killed prior run

    use_kvm = platform.machine() == "aarch64" and os.path.exists("/dev/kvm")
    cmd = [qemu, "-M", "virt", "-m", "512", "-no-reboot", "-nographic",
           "-bios", fw,
           "-drive", "file=%s,if=virtio,format=raw" % disk,
           "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0",
           "-qmp", "unix:%s,server,nowait" % qmp_sock]
    cmd += (["-cpu", "host", "-enable-kvm"] if use_kvm else ["-cpu", "cortex-a72"])
    print("Image:    %s" % img)
    print("Firmware: %s" % fw)
    print("Accel:    %s\n" % ("KVM" if use_kvm else "TCG (slow)"))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, bufsize=1)
    deadline = time.time() + TIMEOUT
    ok, booted, shutdown_ok = False, False, False
    marker_time = None              # set when MARKER is seen; starts the ACPI settle window
    fallback_after_marker = False   # BOOT_FALLBACK seen AFTER marker (acpid is definitely up)
    powerdown_sent = False
    qmp_error = None
    try:
        while time.time() < deadline:
            # select with a rolling slice so the deadline is honoured even if qemu
            # emits NO serial output (the OQ3 console-mismatch case) — a bare
            # blocking readline() would hang here forever.
            remaining = max(0.0, min(deadline - time.time(), 5.0))
            ready, _, _ = select.select([proc.stdout], [], [], remaining)
            if not ready:
                if proc.poll() is not None:
                    if powerdown_sent:
                        shutdown_ok = True
                    break
            else:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        if powerdown_sent:
                            shutdown_ok = True
                        break
                    continue           # poll slice expired; re-check deadline
                sys.stdout.write("  | " + line)
                if not powerdown_sent:
                    if MARKER in line and not ok:
                        ok = True
                        marker_time = time.time()
                        if not ACPI_CHECK:
                            break      # ACPI phase disabled: PASS on boot marker alone
                    elif BOOT_FALLBACK in line:
                        booted = True
                        if ok:
                            fallback_after_marker = True

            # boot phase -> shutdown phase: send the ACPI power button once the guest has
            # settled past the marker (init complete, i.e. acpid started) or 30s have passed.
            if (ok and ACPI_CHECK and not powerdown_sent
                    and (fallback_after_marker or time.time() - marker_time > MARKER_SETTLE)):
                powerdown_sent = True
                try:
                    qmp_powerdown(qmp_sock)
                except Exception as exc:
                    qmp_error = str(exc)
                    break
                deadline = time.time() + SHUTDOWN_TIMEOUT   # start the shutdown-phase clock
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        for _f in cleanup:
            if os.path.isfile(_f):
                os.remove(_f)
        if os.path.exists(qmp_sock):
            os.remove(qmp_sock)

    print()
    if ok:
        if not ACPI_CHECK:
            print("RESULT: PASS (saw %s)" % MARKER)
            sys.exit(0)
        if qmp_error is not None:
            print("RESULT: FAIL — QMP powerdown failed: %s" % qmp_error)
            sys.exit(1)
        if shutdown_ok:
            print("RESULT: PASS (saw %s; guest powered off via ACPI)" % MARKER)
            sys.exit(0)
        if not powerdown_sent:
            print("RESULT: FAIL — boot deadline expired before the ACPI settle window "
                  "completed (powerdown never sent) — raise SMOKE_TIMEOUT")
            sys.exit(1)
        print("RESULT: FAIL — guest ignored ACPI power button within %ds (acpid missing "
              "or not running?)" % SHUTDOWN_TIMEOUT)
        sys.exit(1)
    if booted:
        print("RESULT: FAIL — kernel booted but %s not seen (bootstrap did not "
              "complete). Check 99-tenwrt-bootstrap." % MARKER)
        sys.exit(1)
    print("RESULT: FAIL — no boot output recognised within %ds. Likely a serial-console "
          "mismatch; try adding 'console=ttyAMA0,115200' to the image grub cmdline, or "
          "run on ten64 under KVM." % TIMEOUT)
    sys.exit(1)


if __name__ == "__main__":
    main()
