# gwifi puck OpenWISP config — design (approved 2026-06-05)

> **BUILT 2026-06-05** — implemented as the `gwifi-puck` default template (org
> `default`), attached to all 11 pucks; validated by rendering with
> netjsonconfig 1.2.1. Reproducible builder: `build-templates.py`. Ports
> finalized as `wan` (trunk) / `lan` (access). Not live until pucks onboard.
> One deviation from §"OpenWISP implementation": shipped as a **single
> comprehensive template** (not 5 fragments) — more robust for the
> interdependent DSA/batman config; split later if desired.

Config layer for the 11 gwifi pucks (gale/ipq4019, OpenWrt 25.12.x, DSA),
managed as OpenWISP templates (netjsonconfig → UCI). SSID passphrases and VLAN
IDs are sourced from ten64's live config; nothing goes live until a puck
onboards (all pucks are `config=none` today — review in the OpenWISP UI first).

## Decisions (from ten64 + user)

| SSID | Radio(s) | VLAN | Security | Notes |
|------|----------|------|----------|-------|
| `ansells` | radio0 (2.4) + radio1 (5) | **20** (roam) | **WPA3-SAE** + 802.11r/k/v | fast, modern devices, roams wifi↔ethernet |
| `ansells-iot` | radio0 (2.4) | **90** (iot) | WPA2-PSK | low-power ESP32/IoT |
| `ansells-guest` | radio1 (5) | **99** (guest) | WPA2-PSK + AP isolation | isolated |

- VLAN IDs from ten64 systemd-networkd: `net`=5, `roam`=20, `iot`=90, `guest`=99.
- Passphrases from ten64 hostapd (`hostapd.wlan-roam.conf`, `hostapd.wlan-iot.conf`),
  seeded into OpenWISP as template variables (never hardcoded in the template body).
- `country=AU`. Fixed channels: 2.4 GHz = ch 6, 5 GHz = ch 36 (mesh coherence).
- **ten64 coordination:** ten64's `ansells` (currently WPA2 on `wlan-roam`) is
  upgraded to WPA3 so same-SSID roaming between ten64 and pucks works. Pucks
  supersede the Google/Nest mesh on roam VLAN 20.

## Per-puck L2 architecture

- One VLAN-filtering bridge `br-lan` carrying VLANs 5/20/90/99.
- **Mesh:** 802.11s mesh-point on **both** radios → both enslaved to
  **batman-adv** (`bat0`). batman-adv transports all four VLANs and is visible
  in OpenWISP network-topology. **Bridge-Loop-Avoidance (BLA) on** so a wired
  uplink + the mesh coexist without loops; batman-adv metrics prefer wired.
- **Eth ports:** Port1 = **trunk** (tagged 5/20/90/99) — wired uplink to ten64
  or daisy-chain. Port2 = **access/untagged PVID 20** — wired `ansells` jack.
- **Management:** mgmt interface on VLAN 5, DHCP from ten64 dnsmasq; pulls
  config from wisp (10.1.5.2) over HTTPS (trusted LE cert).
- **Roaming:** `ansells` uses FT-SAE (802.11r) + 802.11k/v across all pucks
  (one mobility domain). Band steering / load steering = the usteer/dawn layer
  (separate, later).

## OpenWISP implementation

Default templates (auto-applied to all 11 pucks, org `default`):

1. `gwifi-base` — country, radios (channels/htmode), `br-lan` VLAN-filtering
   bridge + bridge-vlans, the two eth ports (trunk + access), mgmt VLAN 5.
2. `gwifi-wifi-ansells` — dual-band WPA3-SAE SSID → VLAN 20, FT/k/v.
3. `gwifi-wifi-iot` — 2.4 GHz WPA2-PSK SSID → VLAN 90.
4. `gwifi-wifi-guest` — 5 GHz WPA2-PSK SSID + isolation → VLAN 99.
5. `gwifi-mesh` — 802.11s on both radios + batman-adv (`bat0`, BLA) → `br-lan`.

netjsonconfig covers radios + wireless (AP/802.11s) + bridge interfaces; DSA
bridge-vlan, batman-adv, and switch-port tagging that the NetJSON schema doesn't
model are emitted via raw UCI (netjsonconfig `files` / interface extensions).
Rendered UCI is validated with the OpenWISP **config preview** (no live device
needed) before relying on it.

## Out of scope (separate later work)

- Client steering daemon (usteer/dawn) — band/load steering, 802.11v BTM kicking.
- Full Eth→mesh→last-config failover refinement (metrics/STP tuning beyond BLA).
- Image build: the gale OpenWrt image must include `wpad-mesh-openssl` (802.11s
  + SAE/WPA3), `kmod-batman-adv`, and `openwisp-config` — a build-side checklist.
