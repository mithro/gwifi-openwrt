# wisp.monarto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a second, independent OpenWISP controller (`wisp.monarto`) on
`ten64.monarto.mithis.com`, and restructure `openwisp/` so one tree deploys either site.

**Architecture:** A new libvirt guest on ten64.monarto mirroring welland's live VM
(4 GiB / 2 vCPU / AAVMF UEFI / 20 G virtio-blk + cloud-init NoCloud seed), on `br-wifi`
with the MAC the site's existing `dhcp-host` reservation already prescribes. A new
`openwisp/create-vm.py` captures VM creation (today an undocumented manual step) as a
testable program. The Ansible tree gains per-site inventories so `playbook.yml` stops
hardcoding welland.

**Tech Stack:** Python 3 (`uv`), pytest, libvirt/`virsh`, QEMU aarch64, cloud-init
NoCloud, Ansible (`openwisp.openwisp2` 25.10.2), nginx, certbot.

**Spec:** `docs/superpowers/specs/2026-08-02-wisp-monarto-design.md` — read it first.
Decisions D1–D6 there are binding; this plan implements them.

---

## Before you start — orientation

You are working in the worktree `.worktrees/wisp-monarto` on branch `wisp-monarto`.
Never commit to the base worktree.

**Run the test suite like this** (from the repo root of the worktree):

```sh
cd tools/fleet && uv run --with pytest --with pyyaml pytest -q
```

Baseline is **149 passed**. `tools/fleet/pyproject.toml` sets `testpaths = ["tests"]`
and `pythonpath = ["."]`.

**Tests for `openwisp/` scripts live in `tools/fleet/tests/`** — that is the existing
convention (see `tools/fleet/tests/test_presence_template.py`, which tests
`openwisp/build-templates.py`). Scripts there are hyphenated and not importable as
modules, so tests load them via `importlib`:

```python
import importlib.util
import sys
from pathlib import Path

CV_PATH = Path(__file__).resolve().parents[3] / "openwisp" / "create-vm.py"

def _load():
    spec = importlib.util.spec_from_file_location("create_vm", CV_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod        # REQUIRED -- see below
    spec.loader.exec_module(mod)
    return mod
```

> **The `sys.modules` line is load-bearing.** A module that defines a
> dataclass under `from __future__ import annotations` makes `dataclasses`
> resolve its string annotations through `sys.modules[cls.__module__].__dict__`.
> Unregistered, that lookup returns `None` and the import dies with a bare
> `AttributeError: 'NoneType' object has no attribute '__dict__'` — pointing
> nowhere near the real cause. `create-vm.py` uses exactly that combination
> from Task 1 onward. This ordering is also what the importlib docs' own
> "importing a source file directly" recipe uses.
>
> Note `tools/fleet/tests/test_presence_template.py` still has the
> unregistered version. It passes today only because
> `openwisp/build-templates.py` happens not to combine those two features;
> worth fixing separately.

**Two hard rules from the spec, violated at your peril:**

1. **All remote calls to monarto pin IPv6** (`ssh -6`). Its IPv4 is a reverse proxy on a
   *different machine*; a tool that lands there will report nonsense (D5).
2. **Never `git add` `openwisp/.admin-credentials` or `openwisp/.wifi-secrets`.** Both
   are gitignored; keep it that way, and never copy them to a VM.

**Phase B touches live infrastructure.** Do not start it without the explicit
stop-and-confirm noted in each task.

---

## File structure

| File | Responsibility | Status |
|---|---|---|
| `openwisp/create-vm.py` | Site table; MAC derivation; pre-flight checks; XML + seed generation; `virsh` orchestration | **Create** |
| `tools/fleet/tests/test_create_vm.py` | Offline tests for all of the above | **Create** |
| `openwisp/inventories/welland` | welland host, `ansible_connection=local` | **Create** |
| `openwisp/inventories/monarto` | monarto host, `ansible_connection=local` | **Create** |
| `openwisp/group_vars/openwisp2.yml` | Shared vars (modules, TZ, InfluxDB, firmware map) | **Create** |
| `openwisp/host_vars/wisp.welland.mithis.com.yml` | welland-only vars | **Create** |
| `openwisp/host_vars/wisp.monarto.mithis.com.yml` | monarto-only vars | **Create** |
| `openwisp/playbook.yml` | Site-agnostic; vars lifted out | **Modify** |
| `openwisp/inventory` | Superseded by `inventories/` | **Delete** |
| `openwisp/README.md` | Correct the stale VLAN/IP; document two sites | **Modify** |

`create-vm.py` is one file because its parts are cohesive (a site table and the
operations derived from it) and it is ~250 lines. Do not split it.

---

# PHASE A — Offline (no hardware touched)

Everything in Phase A is testable with no network access. Complete it and get the suite
green before considering Phase B.

---

### Task 1: Site table and MAC derivation

The MAC scheme embeds the IPv4: `02:00:` followed by the four address octets in hex, so
`10.2.4.2` → `02:00:0a:02:04:02`. Making this a function (rather than four hand-typed
MACs) means the consistency test below can prove the table is self-consistent.

**Files:**
- Create: `openwisp/create-vm.py`
- Create: `tools/fleet/tests/test_create_vm.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
"""Offline tests for openwisp/create-vm.py."""
import importlib.util
import sys
from pathlib import Path

import pytest

CV_PATH = Path(__file__).resolve().parents[3] / "openwisp" / "create-vm.py"


def _load():
    """Load the hyphenated script as a module.

    ``sys.modules[spec.name] = mod`` BEFORE ``exec_module`` is required, not
    optional: a module defining a dataclass under ``from __future__ import
    annotations`` makes dataclasses resolve its string annotations via
    ``sys.modules[cls.__module__].__dict__``.  Unregistered, that lookup
    returns None and the import dies with a bare
    ``AttributeError: 'NoneType' object has no attribute '__dict__'``.
    This ordering is also what the importlib docs' own recipe uses.
    """
    spec = importlib.util.spec_from_file_location("create_vm", CV_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_mac_for_ipv4_encodes_the_address():
    cv = _load()
    assert cv.mac_for_ipv4("10.2.4.2") == "02:00:0a:02:04:02"
    assert cv.mac_for_ipv4("10.1.4.2") == "02:00:0a:01:04:02"


def test_mac_for_ipv4_rejects_non_ipv4():
    cv = _load()
    with pytest.raises(ValueError):
        cv.mac_for_ipv4("2404:e80:a137:204::2")


def test_both_sites_present():
    cv = _load()
    assert set(cv.SITES) == {"welland", "monarto"}


def test_site_macs_agree_with_their_ipv4():
    """The table cannot drift: every site's MAC must encode its own IPv4."""
    cv = _load()
    for name, site in cv.SITES.items():
        assert site.mac == cv.mac_for_ipv4(site.ipv4), name


def test_monarto_matches_the_live_reservation():
    """Pins the values ten64.monarto's dhcp-host line already commits to."""
    cv = _load()
    m = cv.SITES["monarto"]
    assert m.mac == "02:00:0a:02:04:02"
    assert m.ipv4 == "10.2.4.2"
    assert m.ipv6 == "2404:e80:a137:204::2"
    assert m.bridge == "br-wifi"
    assert m.fqdn == "wisp.monarto.mithis.com"


def test_monarto_pins_ipv6_transport():
    """D5: monarto's IPv4 is a reverse proxy on another host."""
    cv = _load()
    assert "-6" in cv.SITES["monarto"].ssh_opts
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tools/fleet && uv run --with pytest --with pyyaml pytest tests/test_create_vm.py -q`
Expected: collection error — `openwisp/create-vm.py` does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
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

import ipaddress
from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd tools/fleet && uv run --with pytest --with pyyaml pytest tests/test_create_vm.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```sh
git add openwisp/create-vm.py tools/fleet/tests/test_create_vm.py
git commit -m "openwisp: create-vm site table with IP-derived MACs"
```

---

### Task 2: Reservation pre-flight (D4)

`create-vm.py` must read the site's `dhcp-host` line off the Ten64 and refuse if it
disagrees with the MAC it is about to use. Parsing is pure and testable; the ssh call is
a separate seam so tests never touch the network.

**Files:**
- Modify: `openwisp/create-vm.py`
- Modify: `tools/fleet/tests/test_create_vm.py`

- [ ] **Step 1: Write the failing test**

```python
RESERVATION = (
    "# wisp — DHCP\n"
    "dhcp-host=02:00:0a:02:04:02,10.2.4.2,[2404:e80:a137:204::2],wisp\n"
)


def test_parse_reservation_extracts_mac_and_ips():
    cv = _load()
    r = cv.parse_reservation(RESERVATION)
    assert r.mac == "02:00:0a:02:04:02"
    assert r.ipv4 == "10.2.4.2"
    assert r.ipv6 == "2404:e80:a137:204::2"


def test_parse_reservation_is_case_insensitive_on_mac():
    cv = _load()
    r = cv.parse_reservation("dhcp-host=02:00:0A:02:04:02,10.2.4.2,wisp\n")
    assert r.mac == "02:00:0a:02:04:02"


def test_parse_reservation_raises_when_absent():
    cv = _load()
    with pytest.raises(cv.PreflightError, match="no dhcp-host"):
        cv.parse_reservation("# nothing here\n")


def test_check_reservation_accepts_matching(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_read_reservation", lambda site: RESERVATION)
    cv.check_reservation(cv.SITES["monarto"])          # must not raise


def test_check_reservation_refuses_mac_mismatch(monkeypatch):
    cv = _load()
    wrong = "dhcp-host=02:00:0a:02:04:99,10.2.4.2,wisp\n"
    monkeypatch.setattr(cv, "_read_reservation", lambda site: wrong)
    with pytest.raises(cv.PreflightError, match="MAC"):
        cv.check_reservation(cv.SITES["monarto"])


def test_check_reservation_refuses_ip_mismatch(monkeypatch):
    cv = _load()
    wrong = "dhcp-host=02:00:0a:02:04:02,10.2.4.99,wisp\n"
    monkeypatch.setattr(cv, "_read_reservation", lambda site: wrong)
    with pytest.raises(cv.PreflightError, match="IPv4"):
        cv.check_reservation(cv.SITES["monarto"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tools/fleet && uv run --with pytest --with pyyaml pytest tests/test_create_vm.py -q`
Expected: FAIL — `module 'create_vm' has no attribute 'parse_reservation'`

- [ ] **Step 3: Write the implementation**

```python
import re
import subprocess

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


def _ssh(site: Site, *argv: str) -> str:
    """Run a command on the site's ten64 and return stdout.

    ``site.ssh_opts`` carries the IPv6 pin for monarto (D5).  stderr is
    deliberately NOT suppressed: it is captured and folded into the error.
    """
    cmd = ["ssh", *site.ssh_opts, "-o", "ConnectTimeout=15",
           "-o", "BatchMode=yes", site.ten64, *argv]
    proc = subprocess.run(cmd, capture_output=True, text=True)
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
```

- [ ] **Step 4: Run to verify it passes**

Expected: `12 passed`

- [ ] **Step 5: Commit**

```sh
git add openwisp/create-vm.py tools/fleet/tests/test_create_vm.py
git commit -m "openwisp: create-vm refuses on dhcp-host reservation mismatch"
```

---

### Task 3: Domain XML generation (D6)

**Files:**
- Modify: `openwisp/create-vm.py`
- Modify: `tools/fleet/tests/test_create_vm.py`

- [ ] **Step 1: Write the failing test**

```python
import xml.etree.ElementTree as ET


def test_domain_xml_is_wellformed_and_named():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.findtext("name") == "wisp"


def test_domain_xml_matches_welland_shape():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.findtext("memory") == "4194304"          # 4 GiB, as welland
    assert root.findtext("vcpu") == "2"
    os_type = root.find("os/type")
    assert os_type.get("arch") == "aarch64"


def test_domain_xml_does_not_pin_machine_version():
    """D6: welland pins virt-10.2 but the hosts run different QEMU."""
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.find("os/type").get("machine") == "virt"


def test_domain_xml_uses_uefi_loader():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    assert root.findtext("os/loader") == "/usr/share/AAVMF/AAVMF_CODE.ms.fd"


def test_domain_xml_nic_is_on_the_right_bridge_with_the_right_mac():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    iface = root.find("devices/interface")
    assert iface.find("source").get("bridge") == "br-wifi"
    assert iface.find("mac").get("address") == "02:00:0a:02:04:02"
    assert iface.find("model").get("type") == "virtio"


def test_domain_xml_has_virtio_root_and_seed_cdrom():
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["monarto"]))
    targets = {d.find("target").get("dev"): d for d in root.findall("devices/disk")}
    assert targets["vda"].find("target").get("bus") == "virtio"
    assert targets["vda"].find("source").get("file").endswith("/wisp.qcow2")
    assert targets["sda"].find("source").get("file").endswith("/wisp-seed.iso")


def test_welland_xml_carries_its_own_identity():
    """The generator must be site-driven, not monarto-hardcoded."""
    cv = _load()
    root = ET.fromstring(cv.domain_xml(cv.SITES["welland"]))
    assert root.find("devices/interface/mac").get("address") == "02:00:0a:01:04:02"
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `no attribute 'domain_xml'`

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Expected: `19 passed`

- [ ] **Step 5: Commit**

```sh
git add openwisp/create-vm.py tools/fleet/tests/test_create_vm.py
git commit -m "openwisp: create-vm domain XML, unversioned virt machine"
```

---

### Task 4: cloud-init seed (netplan + user-data)

The guest must come up on its static address on **first** boot and stay there. Two
pieces do that: the NoCloud `network-config` supplies the addressing to cloud-init at
first boot, and `user-data` writes `99-disable-network-config.cfg` so later boots do not
regenerate it. This matches the end state welland reached by migration
(`docs/wisp-netboot-install-plan.md` Task 2.2), reached directly instead.

**Files:**
- Modify: `openwisp/create-vm.py`
- Modify: `tools/fleet/tests/test_create_vm.py`

- [ ] **Step 1: Write the failing test**

```python
import yaml


def test_network_config_is_static_on_the_sites_addresses():
    cv = _load()
    nc = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))
    eth = nc["network"]["ethernets"]["net0"]
    assert eth["dhcp4"] is False
    assert "10.2.4.2/24" in eth["addresses"]
    assert "2404:e80:a137:204::2/64" in eth["addresses"]


def test_network_config_matches_on_mac_and_renames_to_net0():
    cv = _load()
    eth = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))["network"]["ethernets"]["net0"]
    assert eth["match"]["macaddress"] == "02:00:0a:02:04:02"
    assert eth["set-name"] == "net0"


def test_network_config_has_both_default_routes():
    cv = _load()
    eth = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))["network"]["ethernets"]["net0"]
    vias = {r["via"] for r in eth["routes"]}
    assert vias == {"10.2.4.1", "2404:e80:a137:204::1"}


def test_network_config_resolver_is_the_site_router():
    cv = _load()
    eth = yaml.safe_load(cv.network_config(cv.SITES["monarto"]))["network"]["ethernets"]["net0"]
    assert eth["nameservers"]["addresses"] == ["10.2.4.1"]


def test_user_data_sets_hostname_to_the_fqdn():
    cv = _load()
    ud = yaml.safe_load(cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test"))
    assert ud["fqdn"] == "wisp.monarto.mithis.com"


def test_user_data_disables_cloud_init_network_regeneration():
    cv = _load()
    ud = yaml.safe_load(cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test"))
    paths = {f["path"]: f for f in ud["write_files"]}
    target = "/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"
    assert paths[target]["content"].strip() == "network: {config: disabled}"


def test_user_data_creates_tim_with_passwordless_sudo_and_key():
    cv = _load()
    ud = yaml.safe_load(cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test"))
    user = next(u for u in ud["users"] if u["name"] == "tim")
    assert "NOPASSWD:ALL" in user["sudo"]
    assert user["ssh_authorized_keys"] == ["ssh-ed25519 AAAA test"]


def test_user_data_carries_no_password():
    """Access is by key only; a seed ISO is world-readable on the host."""
    cv = _load()
    raw = cv.user_data(cv.SITES["monarto"], ssh_key="ssh-ed25519 AAAA test")
    assert "password" not in raw.lower()


def test_meta_data_instance_id_is_site_specific():
    cv = _load()
    md = yaml.safe_load(cv.meta_data(cv.SITES["monarto"]))
    assert md["instance-id"] == "wisp-monarto"
    assert md["local-hostname"] == "wisp"
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `no attribute 'network_config'`

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Expected: `28 passed`

- [ ] **Step 5: Commit**

```sh
git add openwisp/create-vm.py tools/fleet/tests/test_create_vm.py
git commit -m "openwisp: create-vm cloud-init seed with static addressing"
```

---

### Task 5: Remaining pre-flights, CLI and `--dry-run`

**Files:**
- Modify: `openwisp/create-vm.py`
- Modify: `tools/fleet/tests/test_create_vm.py`

- [ ] **Step 1: Write the failing test**

```python
def test_check_bridge_accepts_present(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-wifi", "br-net"])
    cv.check_bridge(cv.SITES["monarto"])


def test_check_bridge_refuses_absent(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-net"])
    with pytest.raises(cv.PreflightError, match="br-wifi"):
        cv.check_bridge(cv.SITES["monarto"])


def test_check_no_existing_domain_refuses_when_defined(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_domains", lambda s: ["homeassistant", "wisp"])
    with pytest.raises(cv.PreflightError, match="already exists"):
        cv.check_no_existing_domain(cv.SITES["monarto"])


def test_check_no_existing_domain_passes_when_absent(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_list_domains", lambda s: ["homeassistant"])
    cv.check_no_existing_domain(cv.SITES["monarto"])


def test_cli_rejects_unknown_site(capsys):
    cv = _load()
    with pytest.raises(SystemExit):
        cv.main(["--site", "nowhere"])


def test_dry_run_makes_no_changes(monkeypatch, capsys):
    """--dry-run runs every pre-flight but must never mutate the target."""
    cv = _load()
    monkeypatch.setattr(cv, "_read_reservation", lambda s: RESERVATION)
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-wifi"])
    monkeypatch.setattr(cv, "_list_domains", lambda s: ["homeassistant"])

    def _boom(*a, **k):
        raise AssertionError("dry-run must not mutate the target")

    monkeypatch.setattr(cv, "_apply", _boom)
    assert cv.main(["--site", "monarto", "--dry-run",
                    "--ssh-key", "ssh-ed25519 AAAA test"]) == 0
    out = capsys.readouterr().out
    assert "02:00:0a:02:04:02" in out
    assert "<name>wisp</name>" in out


def test_dry_run_still_reports_preflight_failure(monkeypatch):
    cv = _load()
    monkeypatch.setattr(cv, "_read_reservation",
                        lambda s: "dhcp-host=02:00:0a:02:04:99,10.2.4.2,wisp\n")
    monkeypatch.setattr(cv, "_list_bridges", lambda s: ["br-wifi"])
    monkeypatch.setattr(cv, "_list_domains", lambda s: [])
    assert cv.main(["--site", "monarto", "--dry-run",
                    "--ssh-key", "k"]) != 0
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `no attribute 'check_bridge'`

- [ ] **Step 3: Write the implementation**

```python
import argparse
import sys

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


def _apply(site: Site, xml: str, seed: dict[str, str]) -> None:  # pragma: no cover
    """Stage the image and seed, then define and start the VM.

    NOTE: the root disk is the DOWNLOADED cloud image, grown in place --
    never `qemu-img create`, which would yield a blank disk with no OS.
    """
    stage = "~/wisp-staging"                     # not /tmp, per repo convention
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
```

- [ ] **Step 4: Run to verify it passes**

Expected: `35 passed`; whole suite `cd tools/fleet && uv run --with pytest --with pyyaml pytest -q` → `184 passed`

- [ ] **Step 5: Commit**

```sh
git add openwisp/create-vm.py tools/fleet/tests/test_create_vm.py
git commit -m "openwisp: create-vm pre-flights, CLI and --dry-run"
```

---

### Task 6: Parameterise the Ansible tree (D2)

**Files:**
- Create: `openwisp/inventories/welland`, `openwisp/inventories/monarto`
- Create: `openwisp/group_vars/openwisp2.yml`
- Create: `openwisp/host_vars/wisp.welland.mithis.com.yml`, `.../wisp.monarto.mithis.com.yml`
- Modify: `openwisp/playbook.yml`
- Delete: `openwisp/inventory`
- Modify: `tools/fleet/tests/test_create_vm.py` (or a new `test_openwisp_inventory.py`)

- [ ] **Step 1: Write the failing test**

Create `tools/fleet/tests/test_openwisp_inventory.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""The openwisp/ Ansible tree must be site-parameterised, not welland-only."""
from pathlib import Path

import yaml

OW = Path(__file__).resolve().parents[3] / "openwisp"


def test_per_site_inventories_exist():
    assert (OW / "inventories" / "welland").is_file()
    assert (OW / "inventories" / "monarto").is_file()


def test_old_single_site_inventory_is_gone():
    assert not (OW / "inventory").exists()


def test_each_inventory_names_exactly_one_host_run_locally():
    """D2: ansible_connection=local configures whichever box the run is on,
    so an inventory must never list both sites."""
    for site, fqdn in (("welland", "wisp.welland.mithis.com"),
                       ("monarto", "wisp.monarto.mithis.com")):
        body = (OW / "inventories" / site).read_text()
        hosts = [ln.split()[0] for ln in body.splitlines()
                 if ln.strip() and not ln.startswith(("#", "["))]
        assert hosts == [fqdn], site
        assert "ansible_connection=local" in body


def test_allowed_hosts_is_the_current_address_per_site():
    """welland's playbook said 10.1.5.2 — an address the VM lost in the
    VLAN 4 migration."""
    for fqdn, ip in (("wisp.welland.mithis.com", "10.1.4.2"),
                     ("wisp.monarto.mithis.com", "10.2.4.2")):
        v = yaml.safe_load((OW / "host_vars" / f"{fqdn}.yml").read_text())
        assert v["openwisp2_allowed_hosts"] == [ip], fqdn


def test_stale_address_appears_nowhere():
    for p in list(OW.glob("*.yml")) + list((OW / "host_vars").glob("*.yml")) \
             + list((OW / "group_vars").glob("*.yml")):
        assert "10.1.5.2" not in p.read_text(), p


def test_from_email_is_site_specific():
    for fqdn in ("wisp.welland.mithis.com", "wisp.monarto.mithis.com"):
        v = yaml.safe_load((OW / "host_vars" / f"{fqdn}.yml").read_text())
        assert v["openwisp2_default_from_email"].endswith(f"@{fqdn}")


def test_shared_vars_hold_the_module_set_and_timezone():
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    assert g["openwisp2_monitoring"] is True
    assert g["openwisp2_network_topology"] is True
    assert g["openwisp2_firmware_upgrader"] is True
    assert g["openwisp2_radius"] is False
    assert g["openwisp2_time_zone"] == "Australia/Adelaide"


def test_playbook_has_no_site_specific_literals():
    body = (OW / "playbook.yml").read_text()
    for needle in ("welland", "monarto", "10.1.", "10.2."):
        assert needle not in body, needle


def test_firmware_map_survived_the_move():
    g = yaml.safe_load((OW / "group_vars" / "openwisp2.yml").read_text())
    blob = "\n".join(g["openwisp2_extra_django_settings_instructions"])
    for board in ("Google WiFi (Gale)", "OpenMesh OM2P-LC",
                  "OpenMesh OM2P v1", "OpenMesh OM2P v2", "OpenMesh OM2P v4"):
        assert board in blob
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tools/fleet && uv run --with pytest --with pyyaml pytest tests/test_openwisp_inventory.py -q`
Expected: FAIL — inventories missing.

- [ ] **Step 3: Implement**

`openwisp/inventories/monarto` (welland's is the same shape):

```ini
# OpenWISP runs Ansible against itself, so the controller provisions and
# later upgrades itself with no separate control node.
#
#   * inventory_hostname = wisp.monarto.mithis.com
#       -> nginx server_name, TLS cert CN, Django ALLOWED_HOSTS and the
#          /etc/hosts self-reference.
#       -> MUST be the FQDN, never a bare IP (postfix breaks on an IP,
#          which turns some admin actions into HTTP 500s).
#   * ansible_connection=local
#       -> tasks run on this machine directly.
#
# ONE host per file on purpose: with connection=local a second host would
# be configured onto whichever box the run happens on.  See D2 in
# docs/superpowers/specs/2026-08-02-wisp-monarto-design.md.
[openwisp2]
wisp.monarto.mithis.com ansible_connection=local
```

`openwisp/host_vars/wisp.monarto.mithis.com.yml`:

```yaml
---
# Site-specific values for monarto.  NO SECRETS HERE.
openwisp2_default_from_email: "openwisp@wisp.monarto.mithis.com"
# Fallback access by IP when DNS hiccups; the FQDN stays the primary,
# certificate-matching entry point.
openwisp2_allowed_hosts:
  - "10.2.4.2"
certbot_certs:
  - email: "claude@mith.ro"
    domains:
      - "wisp.monarto.mithis.com"
```

Move every other `vars:` entry from `playbook.yml` into
`group_vars/openwisp2.yml` **verbatim, comments included** — the comments explain
non-obvious choices (the InfluxDB auth trap, the firmware map rationale) and must not be
lost. Then reduce `playbook.yml`'s `vars:` to nothing and delete `openwisp/inventory`.

- [ ] **Step 4: Run to verify it passes**

Expected: `9 passed`; whole suite → `193 passed`

- [ ] **Step 5: Verify Ansible agrees the vars resolve**

```sh
cd openwisp && ansible-inventory -i inventories/monarto --host wisp.monarto.mithis.com
```
Expected: JSON including `openwisp2_allowed_hosts: ["10.2.4.2"]` and the shared vars.
(If `ansible` is not installed locally, defer this to Task 10 on the VM.)

- [ ] **Step 6: Commit**

```sh
git add openwisp/inventories openwisp/group_vars openwisp/host_vars \
        openwisp/playbook.yml tools/fleet/tests/test_openwisp_inventory.py
git rm openwisp/inventory
git commit -m "openwisp: per-site inventories; fix welland's stale allowed_hosts"
```

---

### Task 7: Documentation

**Files:**
- Modify: `openwisp/README.md`

- [ ] **Step 1: Correct §1 "What runs where"** — it currently says `br-net`, VLAN 5,
  `10.1.5.2`, MAC `02:00:0a:01:05:02`. Replace with the verified live values
  (`br-wifi`, VLAN 4, `10.1.4.2`, `02:00:0a:01:04:02`) and note that the VM moved
  (`docs/wisp-netboot-install-plan.md` Task 2.3).

- [ ] **Step 2: Make §1 a two-site table** — welland and monarto side by side.

- [ ] **Step 3: Update §5** — `ansible-playbook -i inventories/<site> playbook.yml`,
  and add the `create-vm.py` step ahead of it, replacing "that step is outside this
  directory".

- [ ] **Step 4: Sanity check** — `grep -rn "10\.1\.5\.2\|br-net" openwisp/README.md`
  returns nothing.

- [ ] **Step 5: Commit**

```sh
git add openwisp/README.md
git commit -m "openwisp: README -- correct the VLAN 4 move, document both sites"
```

---

# PHASE B — Live infrastructure

> **STOP.** Do not begin Phase B without explicit confirmation from the user. Phase A
> must be complete and the suite green first.

Reminder: **every monarto ssh needs `-6`** (D5).

---

### Task 8: Enable the nginx vhost on ten64.monarto

Must precede certbot: until the symlink exists, ten64 routes the name to its default
server and ACME validation returns 502.

- [ ] **Step 1:** Confirm the generated vhost is present.

```sh
ssh -6 ten64.monarto.mithis.com \
  'sudo ls /etc/nginx/gdoc2netcfg/sites-available/wisp.monarto.mithis.com'
```

- [ ] **Step 2:** Symlink and reload.

```sh
ssh -6 ten64.monarto.mithis.com '
  sudo ln -s /etc/nginx/gdoc2netcfg/sites-available/wisp.monarto.mithis.com \
             /etc/nginx/sites-enabled/wisp.monarto.mithis.com &&
  sudo nginx -t && sudo systemctl reload nginx'
```
Expected: `syntax is ok` / `test is successful`.

- [ ] **Step 3:** Confirm it routes (502/504 is the CORRECT answer here — the vhost is
  live and the backend does not exist yet; a 200 would mean it is hitting the default
  server).

```sh
curl -sS -o /dev/null -w '%{http_code}\n' http://wisp.monarto.mithis.com/
```

---

### Task 9: Create the VM

- [ ] **Step 1: Dry-run against the real host** — exercises all three pre-flights,
  changes nothing.

```sh
uv run openwisp/create-vm.py --site monarto --dry-run \
      --ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
```
Expected: exit 0; XML with `02:00:0a:02:04:02`, `br-wifi`, `machine='virt'`.

- [ ] **Step 2: Create it.** Drop `--dry-run`. Watch for the pre-flights passing.

- [ ] **Step 3: Verify the domain.**

```sh
ssh -6 ten64.monarto.mithis.com \
  'sudo virsh list --all; sudo virsh dominfo wisp | grep -i autostart'
```
Expected: `wisp running`, `Autostart: enable`.

- [ ] **Step 4: Verify it took the reserved address** (this proves the MAC, the bridge,
  and the netplan all agree).

```sh
ping6 -c3 wisp.monarto.mithis.com
ssh -6 ten64.monarto.mithis.com 'ip neigh show dev br-wifi | grep 10.2.4.2'
```

- [ ] **Step 5:** `ssh -6 tim@wisp.monarto.mithis.com 'hostname; ip -br addr show net0'`
  Expected: `wisp.monarto.mithis.com`, `10.2.4.2/24` and `2404:e80:a137:204::2/64`.

**Rollback if anything is wrong:** `sudo virsh destroy wisp; sudo virsh undefine --nvram wisp;
sudo rm /var/lib/libvirt/images/wisp{.qcow2,-seed.iso}`.

---

### Task 10: Deploy OpenWISP

- [ ] **Step 1:** Copy the tree, **excluding secrets**.

```sh
rsync -a --exclude='.admin-credentials' --exclude='.wifi-secrets' \
      --exclude='__pycache__' openwisp/ tim@wisp.monarto.mithis.com:~/openwisp/
ssh -6 tim@wisp.monarto.mithis.com 'ls -a ~/openwisp | grep -c credentials'
```
Expected: `0`.

- [ ] **Step 2:** Toolchain + the InfluxDB pin **before** the role adds the repo.

```sh
ssh -6 tim@wisp.monarto.mithis.com '
  sudo apt-get update && sudo apt-get install -y ansible git &&
  sudo install -m 0644 ~/openwisp/apt-preferences-influxdb \
       /etc/apt/preferences.d/influxdb'
```

- [ ] **Step 3:** `ansible-galaxy install -r ~/openwisp/requirements.yml`

- [ ] **Step 4:** Run detached (15–40 min on 2 arm64 cores). The `setsid` wrapper is
  required — a bare `... &` leaves the subshell holding the SSH channel.

```sh
ssh -6 tim@wisp.monarto.mithis.com 'cd ~/openwisp &&
  setsid bash -c "ansible-playbook -i inventories/monarto playbook.yml; echo EXIT=\$?" \
    > ~/openwisp/deploy.log 2>&1 < /dev/null &'
```

- [ ] **Step 5:** Poll `tail -n 30 ~/openwisp/deploy.log` until `PLAY RECAP`.
  Expected: `failed=0`.

---

### Task 11: TLS and post-install

- [ ] **Step 1: Dry-run the cert** (unlimited; the real issue is rate-limited).

```sh
ssh -6 tim@wisp.monarto.mithis.com 'sudo certbot certonly --standalone --dry-run \
  -d wisp.monarto.mithis.com --pre-hook "systemctl stop nginx" \
  --post-hook "systemctl start nginx"'
```

- [ ] **Step 2:** If the dry-run succeeded the playbook's certbot role has already
  issued the real cert; confirm from **off-box, without `-k`**:

```sh
curl -sS -o /dev/null -w 'http=%{http_code} verify=%{ssl_verify_result}\n' \
  https://wisp.monarto.mithis.com/admin/login/
```
Expected: `http=200 verify=0`.

- [ ] **Step 3: Change the seeded admin password** (role seeds `admin`/`admin`).

```sh
ssh -6 tim@wisp.monarto.mithis.com 'echo "from django.contrib.auth import get_user_model as G; \
u=G().objects.get(username=\"admin\"); u.set_password(\"NEWPASS\"); u.save()" \
  | sudo /opt/openwisp2/manage.py shell'
```
Record it in `openwisp/.admin-credentials` (0600, **never** committed).

- [ ] **Step 4: Service checks.**

```sh
ssh -6 tim@wisp.monarto.mithis.com '
  systemctl is-active nginx redis-server influxdb supervisor postfix;
  sudo supervisorctl status;
  sudo /opt/openwisp2/manage.py check;
  influx -execute "SHOW DATABASES" 2>&1 | head;
  dpkg -l influxdb | tail -1'
```
Expected: all `active`; 7 supervisor programs RUNNING; "no issues"; `openwisp2` DB;
InfluxDB `1.8.10-1`.

- [ ] **Step 5:** Set the Organization and Site objects in the admin UI; record the org
  shared secret.

---

### Task 12: welland non-regression

> This is the gate on the refactor. Do not skip it.

- [ ] **Step 1:** Copy the refactored tree to welland's VM (same exclusions as Task 10).

- [ ] **Step 2:** Re-run the playbook there:
  `ansible-playbook -i inventories/welland playbook.yml`

- [ ] **Step 3:** Expected `failed=0`, and the **only** changed task attributable to this
  work is the `ALLOWED_HOSTS` correction (`10.1.5.2` → `10.1.4.2`). Anything else changed
  means a var was dropped or altered in the move — investigate before proceeding.

- [ ] **Step 4:** Confirm welland still serves:

```sh
curl -sS -o /dev/null -w 'http=%{http_code} verify=%{ssl_verify_result}\n' \
  https://wisp.welland.mithis.com/admin/login/
```
Expected: `http=200 verify=0`.

- [ ] **Step 5: Commit** any fixes, then finish the branch with
  @superpowers:finishing-a-development-branch.

---

## Done when

- `cd tools/fleet && uv run --with pytest --with pyyaml pytest -q` → **193 passed**
- `https://wisp.monarto.mithis.com/admin/login/` → 200, `ssl_verify_result=0`, no `-k`
- Admin login round-trip succeeds
- welland re-run is `failed=0` with only the `allowed_hosts` change
- `10.1.5.2` appears nowhere in `openwisp/`

**Not done here** (later sub-projects): netboot stack, `build-templates.py` multi-site,
device onboarding, presence, syslog. Nothing in this plan registers a device or pushes a
template.
