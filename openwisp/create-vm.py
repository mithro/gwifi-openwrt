#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create the `wisp` OpenWISP controller VM on a site's Ten64.

welland's wisp VM was built by hand and the procedure was never captured
(openwisp/README.md admits the cloud-init step "is outside this directory").
This script is that missing step, made reproducible and checkable.

See docs/superpowers/specs/2026-08-02-wisp-monarto-design.md for the design
decisions, in particular D4 (refuse on MAC/reservation disagreement),
D5 (monarto is IPv6-direct-only) and D6 (do not pin the QEMU machine version).
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass


def mac_for_ipv4(addr: str) -> str:
    """Derive the locally-administered MAC that encodes an IPv4 address.

    The fleet's addressing plan embeds the address in the MAC:
    ``10.2.4.2`` -> ``02:00:0a:02:04:02``.  This makes DHCP reservations
    self-documenting, and lets a typo be caught by comparison rather than
    by a VM that mysteriously never gets its lease.
    """
    parsed = ipaddress.ip_address(addr)
    if parsed.version != 4:
        raise ValueError(f"expected an IPv4 address, got {addr!r}")
    return "02:00:" + ":".join(f"{o:02x}" for o in parsed.packed)


@dataclass(frozen=True)
class Site:
    """Everything that differs between one site's wisp VM and another's."""

    name: str
    fqdn: str
    ten64: str
    ipv4: str
    gw4: str
    ipv6: str
    gw6: str
    bridge: str = "br-wifi"
    prefix4: int = 24
    prefix6: int = 64
    # ssh options for reaching this site's ten64.  monarto MUST pin IPv6:
    # its A record is a reverse proxy on a different machine (D5).
    ssh_opts: tuple[str, ...] = ()

    @property
    def mac(self) -> str:
        return mac_for_ipv4(self.ipv4)


SITES: dict[str, Site] = {
    "welland": Site(
        name="welland",
        fqdn="wisp.welland.mithis.com",
        ten64="ten64.welland.mithis.com",
        ipv4="10.1.4.2", gw4="10.1.4.1",
        ipv6="2404:e80:a137:104::2", gw6="2404:e80:a137:104::1",
    ),
    "monarto": Site(
        name="monarto",
        fqdn="wisp.monarto.mithis.com",
        ten64="ten64.monarto.mithis.com",
        ipv4="10.2.4.2", gw4="10.2.4.1",
        ipv6="2404:e80:a137:204::2", gw6="2404:e80:a137:204::1",
        ssh_opts=("-6",),
    ),
}


RESERVATION_PATH = "/etc/dnsmasq.d/wifi/generated/wisp.conf"


class PreflightError(RuntimeError):
    """A pre-flight check failed; nothing has been changed on the target."""


@dataclass(frozen=True)
class Reservation:
    mac: str
    ipv4: str
    ipv6: str | None


def parse_reservation(text: str) -> Reservation:
    """Parse the `dhcp-host=` line out of a generated dnsmasq fragment."""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("dhcp-host="):
            continue
        fields = line[len("dhcp-host="):].split(",")
        mac = fields[0].strip().lower()
        v4 = next((f.strip() for f in fields
                   if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", f.strip())), None)
        v6 = next((f.strip()[1:-1] for f in fields
                   if f.strip().startswith("[") and f.strip().endswith("]")), None)
        if v4 is None:
            raise PreflightError(f"dhcp-host line has no IPv4: {line!r}")
        return Reservation(mac=mac, ipv4=v4, ipv6=v6)
    raise PreflightError(f"no dhcp-host line found in {RESERVATION_PATH}")


def ssh_argv(site: Site, argv: Sequence[str]) -> list[str]:
    """Build the local ssh argv, with the remote command as ONE quoted word.

    ssh concatenates its trailing arguments with spaces and hands the result
    to the remote LOGIN SHELL, which parses it again.  Passing argv through
    unquoted therefore loses all structure: ``["sh", "-c", "cd X && curl Y"]``
    arrives as ``sh -c cd X && curl Y``, where the login shell runs a no-op
    ``cd`` (with X as $0) and then runs curl in ITS OWN cwd -- $HOME.

    ``shlex.join`` collapses argv into a single correctly-quoted word, so the
    remote shell passes it through intact.  Tilde still expands, because the
    expansion happens in the inner shell.
    """
    return ["ssh", *site.ssh_opts, "-o", "ConnectTimeout=15",
            "-o", "BatchMode=yes", site.ten64, shlex.join(argv)]


def _ssh(site: Site, *argv: str) -> str:
    """Run a command on the site's ten64 and return stdout.

    ``site.ssh_opts`` carries the IPv6 pin for monarto (D5).  stderr is
    deliberately NOT suppressed: it is captured and folded into the error.
    """
    proc = subprocess.run(ssh_argv(site, argv), capture_output=True, text=True)
    if proc.returncode != 0:
        raise PreflightError(
            f"ssh to {site.ten64} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip()}")
    return proc.stdout


def _read_reservation(site: Site) -> str:      # pragma: no cover - network
    return _ssh(site, "sudo", "cat", RESERVATION_PATH)


def check_reservation(site: Site) -> None:
    """Refuse unless the site's live dhcp-host reservation matches the table.

    A MAC typo would otherwise produce a VM that boots, never receives its
    reservation, and fails confusingly much later.
    """
    got = parse_reservation(_read_reservation(site))
    if got.mac != site.mac:
        raise PreflightError(
            f"{site.name}: reservation MAC {got.mac} != planned {site.mac}")
    if got.ipv4 != site.ipv4:
        raise PreflightError(
            f"{site.name}: reservation IPv4 {got.ipv4} != planned {site.ipv4}")


IMAGES = "/var/lib/libvirt/images"
MEMORY_KIB = 4194304        # 4 GiB — matches welland
VCPUS = 2
LOADER = "/usr/share/AAVMF/AAVMF_CODE.ms.fd"


def domain_xml(site: Site) -> str:
    """Render the libvirt domain XML for a site's wisp VM.

    Deliberately uses the UNVERSIONED ``virt`` machine alias (D6): welland's
    domain says ``virt-10.2``, but welland runs QEMU 11.0.3 and monarto
    10.2.1, so a pinned version is portable only by luck.  libvirt
    canonicalises ``virt`` to the host's newest on define.
    """
    return f"""<domain type='kvm'>
  <name>wisp</name>
  <memory unit='KiB'>{MEMORY_KIB}</memory>
  <currentMemory unit='KiB'>{MEMORY_KIB}</currentMemory>
  <vcpu placement='static'>{VCPUS}</vcpu>
  <os>
    <type arch='aarch64' machine='virt'>hvm</type>
    <loader readonly='yes' type='pflash' format='raw'>{LOADER}</loader>
  </os>
  <features><acpi/><gic version='3'/></features>
  <cpu mode='host-passthrough' check='none'/>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>/usr/bin/qemu-system-aarch64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='{IMAGES}/wisp.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='{IMAGES}/wisp-seed.iso'/>
      <target dev='sda' bus='scsi'/>
      <readonly/>
    </disk>
    <controller type='scsi' model='virtio-scsi'/>
    <interface type='bridge'>
      <mac address='{site.mac}'/>
      <source bridge='{site.bridge}'/>
      <model type='virtio'/>
    </interface>
    <console type='pty'><target type='serial' port='0'/></console>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
    <rng model='virtio'><backend model='random'>/dev/urandom</backend></rng>
  </devices>
</domain>
"""


def network_config(site: Site) -> str:
    """NoCloud network-config: static, matching welland's end state.

    Static rather than DHCP by design (D1).  VLAN 4 is where wisp itself
    will later serve netboot DHCP, and a DHCP client on a VLAN it also
    serves is the chicken-and-egg welland had to migrate away from.
    """
    return f"""network:
  version: 2
  ethernets:
    net0:
      match:
        macaddress: "{site.mac}"
      set-name: "net0"
      dhcp4: false
      dhcp6: false
      addresses:
        - {site.ipv4}/{site.prefix4}
        - "{site.ipv6}/{site.prefix6}"
      routes:
        - to: default
          via: {site.gw4}
        - to: default
          via: "{site.gw6}"
      nameservers:
        addresses: [{site.gw4}]
"""


def meta_data(site: Site) -> str:
    return f"instance-id: wisp-{site.name}\nlocal-hostname: wisp\n"


def user_data(site: Site, *, ssh_key: str) -> str:
    """NoCloud user-data: the `tim` admin account and the network freeze.

    No password is set anywhere: the seed ISO sits readable on the
    hypervisor, so key-only access is the only safe posture.
    """
    return f"""#cloud-config
fqdn: {site.fqdn}
prefer_fqdn_over_hostname: true
users:
  - name: tim
    groups: [sudo]
    shell: /bin/bash
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    ssh_authorized_keys:
      - "{ssh_key}"
ssh_pwauth: false
write_files:
  - path: /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
    permissions: "0644"
    content: |
      network: {{config: disabled}}
package_update: true
"""


DEBIAN_IMAGE_URL = (
    "https://cloud.debian.org/images/cloud/trixie/latest/"
    "debian-13-genericcloud-arm64.qcow2"
)
DISK_SIZE = "20G"          # matches welland


def _list_bridges(site: Site) -> list[str]:        # pragma: no cover - network
    out = _ssh(site, "ip", "-br", "link", "show", "type", "bridge")
    return [ln.split()[0] for ln in out.splitlines() if ln.strip()]


def _list_domains(site: Site) -> list[str]:        # pragma: no cover - network
    out = _ssh(site, "sudo", "virsh", "list", "--all", "--name")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def check_bridge(site: Site) -> None:
    if site.bridge not in _list_bridges(site):
        raise PreflightError(
            f"{site.name}: bridge {site.bridge} not present on {site.ten64}")


def check_no_existing_domain(site: Site) -> None:
    if "wisp" in _list_domains(site):
        raise PreflightError(
            f"{site.name}: domain 'wisp' already exists on {site.ten64}; "
            "refusing to redefine it")


def staging_dir(home: str) -> str:
    """Absolute staging path under the remote home.

    MUST be absolute.  ``ssh_argv`` quotes every argument, so a bare argv
    element is entirely literal -- no tilde expansion, no ``$VAR``, no glob.
    ``mkdir -p '~/wisp-staging'`` therefore creates a directory literally
    NAMED ``~``.  Shell features only work inside an explicit ``sh -c``.

    (Not /tmp, per the repo convention.)
    """
    return f"{home}/wisp-staging"


def remote_home(site: Site) -> str:
    """Resolve the ten64's home directory to an absolute path.

    Done once so every staging path below is absolute and unambiguous.  The
    expansion happens inside ``sh -c``, which is the only place a shell
    feature survives ssh_argv's quoting.
    """
    home = _ssh(site, "sh", "-c", 'printf %s "$HOME"').strip()
    if not home.startswith("/"):
        raise PreflightError(
            f"{site.name}: could not resolve remote $HOME (got {home!r})")
    return home


def _apply(site: Site, xml: str, seed: dict[str, str]) -> None:  # pragma: no cover
    """Stage the image and seed, then define and start the VM.

    NOTE: the root disk is the DOWNLOADED cloud image, grown in place --
    never `qemu-img create`, which would yield a blank disk with no OS.
    """
    stage = staging_dir(remote_home(site))
    _ssh(site, "mkdir", "-p", stage)

    # 1. Fetch the guest image and verify it against Debian's SHA512SUMS.
    #    ten64.monarto has egress (verified: 302 from cloud.debian.org).
    base = DEBIAN_IMAGE_URL.rsplit("/", 1)[-1]
    _ssh(site, "sh", "-c",
         f"cd {stage} && curl -fLsS -O {DEBIAN_IMAGE_URL} "
         f"&& curl -fLsS -O {DEBIAN_IMAGE_URL.rsplit('/', 1)[0]}/SHA512SUMS "
         f"&& grep ' {base}$' SHA512SUMS | sha512sum -c -")

    # 2. Install as the root disk and grow it to the welland-matching size.
    _ssh(site, "sudo", "cp", f"{stage}/{base}", f"{IMAGES}/wisp.qcow2")
    _ssh(site, "sudo", "qemu-img", "resize", f"{IMAGES}/wisp.qcow2", DISK_SIZE)

    # 3. Build the NoCloud seed ISO.  The volume label MUST be `cidata`;
    #    cloud-init discovers the datasource by that label alone.
    for name, body in seed.items():
        _ssh(site, "sh", "-c",
             f"cat > {stage}/{name} <<'__EOF__'\n{body}__EOF__")
    _ssh(site, "sh", "-c",
         f"cd {stage} && genisoimage -quiet -output wisp-seed.iso "
         f"-volid cidata -joliet -rock user-data meta-data network-config")
    _ssh(site, "sudo", "cp", f"{stage}/wisp-seed.iso", f"{IMAGES}/wisp-seed.iso")

    # 4. Define, autostart, start.
    _ssh(site, "sh", "-c",
         f"cat > {stage}/wisp.xml <<'__EOF__'\n{xml}__EOF__")
    _ssh(site, "sudo", "virsh", "define", f"{stage}/wisp.xml")
    _ssh(site, "sudo", "virsh", "autostart", "wisp")
    _ssh(site, "sudo", "virsh", "start", "wisp")

    # 5. The seed carries no secrets (key-only, no password), but there is no
    #    reason to leave the staging copy lying about.
    _ssh(site, "rm", "-rf", stage)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True, choices=sorted(SITES))
    ap.add_argument("--ssh-key", required=True,
                    help="public key authorised for `tim` in the guest")
    ap.add_argument("--dry-run", action="store_true",
                    help="run every pre-flight and print the artefacts; "
                         "change nothing")
    args = ap.parse_args(argv)

    site = SITES[args.site]
    xml = domain_xml(site)
    seed = {
        "meta-data": meta_data(site),
        "user-data": user_data(site, ssh_key=args.ssh_key),
        "network-config": network_config(site),
    }

    try:
        check_reservation(site)
        check_bridge(site)
        check_no_existing_domain(site)
    except PreflightError as exc:
        print(f"PRE-FLIGHT FAILED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"# site={site.name} fqdn={site.fqdn} mac={site.mac}")
        print(xml)
        for name, body in seed.items():
            print(f"# --- {name} ---\n{body}")
        return 0

    _apply(site, xml, seed)
    return 0


if __name__ == "__main__":                          # pragma: no cover
    raise SystemExit(main())
