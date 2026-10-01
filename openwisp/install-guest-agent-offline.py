#!/usr/bin/python3
# SPDX-License-Identifier: Apache-2.0
"""One-off: install qemu-guest-agent into an existing wisp VM's disk, offline.

For VMs built by create-vm.py before it installed the agent (wisp.monarto,
2026-10-01): the domain has the guest-agent channel but nothing behind it,
and with the ssh key unavailable there is no other way in. Run as root ON THE
HYPERVISOR, detached so a dropped ssh session cannot kill it mid-install:

    sudo systemd-run --unit=wisp-ga-install --collect \\
        /usr/bin/python3 /path/install-guest-agent-offline.py wisp

Steps: graceful `virsh shutdown` (never destroy -- aborts if the guest will
not stop), attach the qcow2 via qemu-nbd, find the Debian root, chroot and
`apt-get install qemu-guest-agent` with a policy-rc.d so nothing starts in
the chroot, tear everything down, boot the VM and wait for guest-ping.
The VM is only restarted once the disk is cleanly detached.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

DOMAIN = sys.argv[1] if len(sys.argv) > 1 else "wisp"
MNT = pathlib.Path(f"/mnt/{DOMAIN}-ga-root")


def log(*a):
    print(*a, flush=True)


def run(argv, check=True, **kw):
    log("$", " ".join(argv))
    p = subprocess.run(argv, text=True, **kw)
    if check and p.returncode != 0:
        raise SystemExit(f"ABORT: rc={p.returncode} from {' '.join(argv)}")
    return p


def out(argv):
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE, check=True).stdout.strip()


def domstate():
    return out(["virsh", "domstate", DOMAIN])


def disk_path():
    for line in out(["virsh", "domblklist", DOMAIN]).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "vda":
            return parts[1]
    raise SystemExit("ABORT: no vda disk on the domain")


def free_nbd():
    run(["modprobe", "nbd", "max_part=16"])
    for i in range(16):
        dev = pathlib.Path(f"/sys/block/nbd{i}")
        if dev.exists() and (dev / "size").read_text().strip() == "0":
            return f"/dev/nbd{i}"
    raise SystemExit("ABORT: no free /dev/nbdN")


def find_root(nbd):
    """The ext4 partition holding etc/debian_version."""
    # qemu-nbd returns before the kernel has scanned the partition table
    # (seen 2026-10-01: lsblk listed only the bare nbd0), so wait for it.
    name = nbd[len("/dev/"):]
    deadline = time.time() + 30
    while not list(pathlib.Path(f"/sys/block/{name}").glob(f"{name}p*")):
        if time.time() > deadline:
            raise SystemExit(f"ABORT: no partitions appeared on {nbd}")
        run(["blockdev", "--rereadpt", nbd], check=False)
        time.sleep(1)
    run(["udevadm", "settle"])
    rows = out(["lsblk", "-rno", "NAME,FSTYPE", nbd]).splitlines()
    for row in rows:
        name, *fs = row.split()
        if fs != ["ext4"]:
            continue
        part = f"/dev/{name}"
        MNT.mkdir(exist_ok=True)
        run(["mount", "-o", "ro", part, str(MNT)])
        is_root = (MNT / "etc/debian_version").exists()
        run(["umount", str(MNT)])
        if is_root:
            return part
    raise SystemExit(f"ABORT: no Debian root partition on {nbd}: {rows}")


def main():
    if os.geteuid() != 0:
        raise SystemExit("run as root")
    image = disk_path()
    log("domain", DOMAIN, "disk", image, "state", domstate())

    # 1. graceful shutdown only
    if domstate() != "shut off":
        run(["virsh", "shutdown", DOMAIN])
        deadline = time.time() + 300
        while time.time() < deadline and domstate() != "shut off":
            time.sleep(5)
        if domstate() != "shut off":
            raise SystemExit("ABORT: guest did not shut down within 300 s; "
                             "NOT forcing it. Domain left as is.")
    log("domain is shut off")

    nbd = None
    mounts = []          # unmounted in reverse
    created_policy = None
    detached = False
    try:
        nbd = free_nbd()
        run(["qemu-nbd", "--connect", nbd, "--format", "qcow2", image])
        root = find_root(nbd)
        run(["mount", root, str(MNT)]); mounts.append(MNT)
        for src, dst, opts in (("proc", "proc", ["-t", "proc"]),
                               ("sysfs", "sys", ["-t", "sysfs"]),
                               ("/dev", "dev", ["--bind"]),
                               ("/dev/pts", "dev/pts", ["--bind"]),
                               ("tmpfs", "run", ["-t", "tmpfs"])):
            target = MNT / dst
            run(["mount", *opts, src, str(target)]); mounts.append(target)

        # DNS: the chroot shares the host's network namespace, so the host's
        # resolver config works verbatim. The guest's /etc/resolv.conf is
        # normally a symlink into /run (now our empty tmpfs).
        resolv = MNT / "etc/resolv.conf"
        host_resolv = pathlib.Path("/etc/resolv.conf").read_text()
        if resolv.is_symlink():
            tgt = os.readlink(resolv)
            tgt = MNT / tgt.lstrip("/") if tgt.startswith("/") else resolv.parent / tgt
            log("guest resolv.conf ->", tgt)
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_text(host_resolv)
        else:
            run(["mount", "--bind", "/etc/resolv.conf", str(resolv)]); mounts.append(resolv)

        log("guest apt sources:")
        for f in sorted((MNT / "etc/apt").glob("sources.list*")) + \
                sorted((MNT / "etc/apt/sources.list.d").glob("*")):
            if f.is_file():
                log(" ", f.relative_to(MNT), "|", " ".join(f.read_text().split())[:200])

        policy = MNT / "usr/sbin/policy-rc.d"
        if policy.exists():
            raise SystemExit("ABORT: guest already has a policy-rc.d; not touching it")
        policy.write_text("#!/bin/sh\nexit 101\n"); policy.chmod(0o755)
        created_policy = policy

        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        run(["chroot", str(MNT), "apt-get", "update"], env=env)
        run(["chroot", str(MNT), "apt-get", "install", "-y",
             "--no-install-recommends", "qemu-guest-agent"], env=env)
        st = out(["chroot", str(MNT), "dpkg-query", "-W",
                  "-f=${Status} ${Version}", "qemu-guest-agent"])
        log("installed:", st)
        if not st.startswith("install ok installed"):
            raise SystemExit("ABORT: package not installed")
    finally:
        if created_policy:
            created_policy.unlink()
            log("removed policy-rc.d")
        for m in reversed(mounts):
            run(["umount", str(m)], check=False)
        run(["sync"])
        if nbd:
            p = run(["qemu-nbd", "--disconnect", nbd], check=False)
            time.sleep(2)
            size = pathlib.Path(f"/sys/block/{nbd[5:]}/size").read_text().strip()
            detached = p.returncode == 0 and size == "0"
            log("nbd detached:", detached)
        else:
            detached = True
        if detached:
            run(["virsh", "start", DOMAIN], check=False)
        else:
            log("NOT starting the domain: disk still attached via", nbd)

    # 3. wait for the agent
    deadline = time.time() + 240
    while time.time() < deadline:
        p = subprocess.run(["virsh", "qemu-agent-command", DOMAIN,
                            json.dumps({"execute": "guest-ping"})],
                           text=True, capture_output=True)
        if p.returncode == 0:
            log("guest-ping OK:", p.stdout.strip())
            return
        time.sleep(5)
    raise SystemExit("guest agent did not answer within 240 s of boot")


if __name__ == "__main__":
    main()
