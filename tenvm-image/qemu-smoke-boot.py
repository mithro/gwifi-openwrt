#!/usr/bin/env python3
"""qemu-smoke-boot.py — headless boot test for the ten64 Wi-Fi VM image.

Boots the built combined-efi.img under qemu-system-aarch64 (-M virt) and asserts the
image reaches first-boot: the kernel boots to userspace and 99-tenvm-bootstrap prints its
completion marker on the serial console. No radio is required. KVM is used on aarch64
hosts; TCG otherwise. SKIPs (exit 0) if qemu or UEFI firmware is unavailable.

Usage: uv run python tenvm-image/qemu-smoke-boot.py [path/to/combined-efi.img]
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

OWRT = os.environ.get("OWRT", "/home/tim/local/gwifi/openwrt")
IMAGE_DIR = os.path.join(OWRT, "bin/targets/armsr/armv8")
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp")
MARKER = "TENVM-BOOTSTRAP-COMPLETE"
BOOT_FALLBACK = "procd: - init complete -"     # accept as a weaker "kernel booted" signal
TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "360"))

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

    use_kvm = platform.machine() == "aarch64" and os.path.exists("/dev/kvm")
    cmd = [qemu, "-M", "virt", "-m", "512", "-no-reboot", "-nographic",
           "-bios", fw,
           "-drive", "file=%s,if=virtio,format=raw" % disk,
           "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0"]
    cmd += (["-cpu", "host", "-enable-kvm"] if use_kvm else ["-cpu", "cortex-a72"])
    print("Image:    %s" % img)
    print("Firmware: %s" % fw)
    print("Accel:    %s\n" % ("KVM" if use_kvm else "TCG (slow)"))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, bufsize=1)
    deadline = time.time() + TIMEOUT
    ok, booted = False, False
    try:
        while time.time() < deadline:
            # select with a rolling slice so the deadline is honoured even if qemu
            # emits NO serial output (the OQ3 console-mismatch case) — a bare
            # blocking readline() would hang here forever.
            remaining = max(0.0, min(deadline - time.time(), 5.0))
            ready, _, _ = select.select([proc.stdout], [], [], remaining)
            if not ready:
                if proc.poll() is not None:
                    break
                continue                  # poll slice expired; re-check deadline
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            sys.stdout.write("  | " + line)
            if MARKER in line:
                ok = True
                break
            if BOOT_FALLBACK in line:
                booted = True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        for _f in cleanup:
            if os.path.isfile(_f):
                os.remove(_f)

    print()
    if ok:
        print("RESULT: PASS (saw %s)" % MARKER)
        sys.exit(0)
    if booted:
        print("RESULT: FAIL — kernel booted but %s not seen (bootstrap did not "
              "complete). Check 99-tenvm-bootstrap." % MARKER)
        sys.exit(1)
    print("RESULT: FAIL — no boot output recognised within %ds. Likely a serial-console "
          "mismatch; try adding 'console=ttyAMA0,115200' to the image grub cmdline, or "
          "run on ten64 under KVM." % TIMEOUT)
    sys.exit(1)


if __name__ == "__main__":
    main()
