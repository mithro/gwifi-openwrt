<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fleet SPI-firmware flash: dev-key re-key + TFTP-first depthcharge (design)

Status: **design / spec** (2026-06-30). Drives the companion
`gale-fleet-firmware-flash-plan.md` runbook + the `tools/fleet/` scripts.

Flash every *stock* Google Wifi (`gale`) fleet puck's **SPI boot flash** with a
dev-key-re-keyed depthcharge that **TFTP-netboots first and falls back to the
eMMC vboot path**. This session is **firmware only — eMMC is never written here**.

## 1. Goal & scope

| | |
|---|---|
| **In scope (this session)** | Per-puck: back up SPI → build a dev-keyed, TFTP-first SPI image *from that puck's own dump* → flash the RW slots + GBB over SuzyQ → extract device identity → verify boot. Pilot one fresh-stock puck, checkpoint, then roll out the rest. |
| **Explicitly out of scope** | Writing eMMC. The eMMC gets a full OpenWrt later, **over the network**: the puck netboots an OpenWrt installer image from the server, and *that* flashes/upgrades eMMC. Same mechanism is the eMMC upgrade path forever (power-cycle into the netboot image → flash eMMC). |
| **Steady-state runtime** | **Netboot-primary**: every boot the puck TFTP-boots OpenWrt from a central DHCP/TFTP server; eMMC holds a dev-signed OpenWrt purely as fallback when the server is unreachable (populated in the later eMMC pass). |

## 2. Why a dev-key re-key (not just a payload swap)

Production `gale` ships GBB flags `0x00000000` (no dev mode) and verifies the RW
firmware slot against **Google's** production rootkey in GBB. To make the RO
verstage accept a *custom* depthcharge in `FW_MAIN_A`, the device must be
**re-keyed to the ChromeOS dev keys**: swap `GBB.rootkey` → dev rootkey, then
re-sign `VBLOCK_A`/`VBLOCK_B` with the dev firmware data key. This is only
possible because the **hardware write-protect screw has been removed on every
fleet device** (confirmed), so the WP_RO region (incl. GBB) is writable, and the
flash array protection bits are clear (`BP=CMP=WPS=0`; only the status register
is locked, which the EC-raiden writer bypasses).

Full boot chain, SPI map, and signing chain: [`gale-boot-process.md`](gale-boot-process.md).

## 3. The deployable artifact (shared across all pucks)

`depthcharge-ipq4019/depthcharge/build/depthcharge.elf` — the **standard**
depthcharge payload, with TFTP-first/eMMC-fallback compiled in
(`CONFIG_TRY_NETBOOT_FIRST=1`; on DHCP/TFTP failure it prints
`netboot: DHCP failed; falling through to vboot.` — the string verified via
`strings` on the built ELF (the older `gale-openwrt-netboot-install.md` §4 quotes
`=== Falling back to eMMC kernel partition ===`, which is **stale**; not a
verification gate either way, see §7) — then runs the normal
`VbSelectAndLoadKernel()` eMMC path). Built 2026-06-13, after fork HEAD
`c02e0cd`. This ELF is the *only* shared bit; everything else is per-puck.

> The fork's net-driver work that makes onboard-ethernet netboot possible is the
> already-complete `depthcharge-ipq4019` project — this design only **deploys**
> its output.

## 4. Per-puck pipeline

Each puck flows through five steps. **One read** (`chunk_read.py all`) serves
three masters: the undo backup, the build input, and the identity source.

```
 ┌─ 1. BACK UP ──────────────────────────────────────────────────────────┐
 │ chunk_read.py all → backups/gale-<serial>-<YYYY-MM-DD>-pre-flash.bin    │
 │ gate: 8 MiB, FMAP parses, futility show = GOOGLE rootkey (still stock), │
 │       VPD serial matches the printed label                             │
 └────────────────────────────────────────────────────────────────────────┘
 ┌─ 2. EXTRACT IDENTITY ─────────────────────────────────────────────────┐
 │ parse RO_VPD/RW_VPD + GBB HWID + RO_FRID from the dump →               │
 │ local record inventory/<serial>.json  (source of truth; powers the    │
 │ serial-match guard; sheet sync is a separate, decoupled step)         │
 └────────────────────────────────────────────────────────────────────────┘
 ┌─ 3. BUILD (one combined image) ───────────────────────────────────────┐
 │ build_gale_fleet_image.py <live.bin> <out.bin>                        │
 │   a. GBB rootkey → dev rootkey                                         │
 │   b. extend FW_MAIN_A CBFS trailer to fill the FMAP region            │
 │   c. FW_MAIN_A/fallback/payload ← depthcharge.elf (lzma)              │
 │   d. mirror A→B so BOTH slots carry the TFTP-first payload            │
 │   e. re-sign VBLOCK_A and VBLOCK_B (dev keys, flags=0, body_size=full) │
 │   f. GATE: futility verify must pass; diff_regions shows ONLY          │
 │      GBB + FW_MAIN_A/B + VBLOCK_A/B changed (RO_VPD untouched)         │
 └────────────────────────────────────────────────────────────────────────┘
 ┌─ 4. FLASH (one parking session, RO-last) ─────────────────────────────┐
 │ flash_gale_fleet.py <out.bin> <expected-serial>                       │
 │   guard: refuse unless target's live VPD serial == expected-serial    │
 │   write order:  RW_SECTION_A → RW_SECTION_B → GBB+RO_FRID (--allow-ro) │
 │   re-park AP between regions (writes auto-power-on the AP)             │
 └────────────────────────────────────────────────────────────────────────┘
 ┌─ 5. VERIFY + RECORD ──────────────────────────────────────────────────┐
 │ power on, capture AP serial; confirm dev-keyed RW slot boots (not     │
 │ recovery); pilot also proves netboot + fallback (see §7).             │
 │ append result to inventory/<serial>.json; sync to the sheet.          │
 └────────────────────────────────────────────────────────────────────────┘
```

### Regions (verified from FMAP of a real dump)

| Region | Offset | Size | Touched? |
|---|---|---|---|
| `GBB` | `0x301000` | 891.8 KiB | yes — rootkey field |
| `RO_FRID` | `0x3DFF00` | 256 B | rewritten identical (in the GBB span write) |
| `RO_VPD` | `0x3E0000` | 128 KiB | **no** (per-device identity preserved) |
| `VBLOCK_A` | `0x400000` | 8 KiB | yes — re-signed |
| `FW_MAIN_A` | `0x402000` | 1335.8 KiB | yes — new payload |
| `RW_SECTION_A` | `0x400000` | 1408 KiB | written (encloses VBLOCK_A+FW_MAIN_A) |
| `VBLOCK_B`/`FW_MAIN_B`/`RW_SECTION_B` | `0x580000` | 1408 KiB | yes — mirrored A |
| `RW_VPD` | `0x6E0000` | 32 KiB | **no** |

`RO_VPD` carries serial, mlb_serial, MAC(s), region, and the **WiFi calibration
vectors** — never written, which is why every image must be built from its own
puck's dump (there is no golden image).

## 5. The combined-image build (generalizing the `tmp/` prototypes)

Merges the proven `build_devkey_bringup.py` + `build_depthcharge_image_v2.py`
into one script. Transformations on a copy of the live dump:

1. `futility gbb_utility --set -k devkeys/root_key.vbpubk <out>` — dev rootkey.
2. `extend_cbfs_empty.py` — grow FW_MAIN_A's CBFS empty trailer to the region size
   so `body_size` in the new preamble matches coreboot's runtime CBFS bound.
3. `cbfstool <out> remove/add-payload -r FW_MAIN_A -n fallback/payload -f depthcharge.elf -c lzma`.
4. **Mirror the body A→B**: copy the rebuilt **`FW_MAIN_A`** region (1335.8 KiB)
   verbatim onto **`FW_MAIN_B`** (identical size). Only the `FW_MAIN_B` *body* is
   overwritten — `RW_FWID_B`, `RW_SHARED`, and the rest of `RW_SECTION_B` are left
   untouched (keeps the §5.6 diff gate honest). A full-body copy (not a partial
   splice) is required because stock A and B bodies differ — e.g. tzbsp blob
   393256 B (A) vs 37928 B (B) per `gale-boot-process.md` §2.
5. Sign **both** vblocks with the dev keyblock + `dev_firmware_data_key`,
   `--kernelkey kernel_subkey.vbpubk`, `--version 1`, `--flags 0` (drop
   `USE_RO_NORMAL` so the body hash is really checked, offline and at runtime),
   each over its own slot's full `FW_MAIN_<X>` as the firmware volume. This
   standardizes on the v2 per-slot `vbutil_firmware` + splice method (not the
   bring-up's whole-image `futility sign` with mixed normal/dev keyblocks); since
   the mirrored bodies are now identical, a single dev keyblock signs both slots.
6. **Gate:** `futility verify <out>` passes **and** `diff_regions.py` shows only
   `GBB`, `FW_MAIN_A/B`, `VBLOCK_A/B` differ from the live dump.

Keys: `depthcharge-ipq4019/vboot_reference/tests/devkeys/` (all present).

## 6. Flash order, safety rails, recovery

- **RO-last ordering** (`RW_SECTION_A` → `RW_SECTION_B` → `GBB+RO_FRID`): if any
  write fails mid-way, GBB still holds the Google rootkey, so the puck remains
  stock-bootable (or at worst falls to recovery on the untouched stock
  recovery_key). The GBB write needs `--allow-ro`.
- **Serial-match guard (new — the prototypes lacked it):** the flasher reads the
  target's live VPD serial over the bridge and **refuses to write** unless it
  equals the serial the image was built from. Prevents flashing one puck's
  re-keyed image (with another's VPD assumptions) onto the wrong unit. Read path:
  a partial bridge read of `RO_VPD` (`0x3E0000:0x20000`) then VPD-parse — one
  short extra SuzyQ session before the write.
- **Chunk size:** `0x1000` (4 KiB, proven) for the pilot; evaluate `0x4000`
  (16 KiB, the documented per-session ceiling — 4× fewer SuzyQ sessions) for the
  fleet once the pilot validates timing.
- **Recovery / rollback:** re-flash the puck's `pre-flash.bin` (full chip or
  affected regions) over SuzyQ → bone stock. The EC/SuzyQ path is independent of
  AP boot state, so even a non-booting AP is recoverable without opening the case.

## 7. Verification

**Pilot (full proof):**
1. Power on, capture AP serial. Expect RW coreboot (Dec 2018) → depthcharge →
   TFTP attempt. **Immediate recovery would mean vboot rejected our dev-keyed slot** (fail).
2. With DHCP/TFTP up on the cabled NIC serving a known-good OpenWrt netboot FIT
   (e.g. `tmp/active-netboot.itb`), confirm DHCP → TFTP → OpenWrt boots into RAM
   (serial login). = **netboot-first proven**.
3. Stop TFTP, reboot. depthcharge waits the link/DHCP timeout, falls through to
   the vboot/eMMC path (lands in recovery since eMMC is still stock — **expected**,
   eMMC is deferred). = **fallback path proven**.

**Fleet (lighter):** steps 1–2 per puck (boots dev-keyed slot; netboots). Step 3
is structurally proven by the pilot.

## 8. Identity extraction → spreadsheet mapping

Parse from each puck's dump and write to the
[Google Wifi Pucks sheet](https://docs.google.com/spreadsheets/d/1fFm2irzmnLb7RQNmAi4DmAm2_c61wrd5A2j3ZzdqIWE/edit?gid=210946497)
(`gwifi_sheets.py` targets this same sheet/gid). Existing cols: A=# B=Model
C=Firmware D=Serial E=MAC F=SetupNet G=SetupCode. New (dump-derived,
authoritative — not OCR):

| Data | Source |
|---|---|
| **VPD identity**: mlb_serial, region, all MACs (ethernet + wifi) | RO_VPD / RW_VPD |
| **HWID** | `futility gbb_utility --get --hwid` |
| **RO firmware version** | `RO_FRID` string (e.g. `google_gale.7651.1.0`) |
| **Flash bookkeeping**: backup path, flashed-image sha256, flash date/status | this pipeline |

Extraction writes `inventory/<serial>.json` first (works with no network); the
**sheet sync is a decoupled step**, so a missing/expired credential never stalls
a flash. Match dump-serial → sheet row by Serial(D).

**Auth (open action item):** the host's old `~/local/sheets_token.json` is gone
and `gcloud` is not installed. Resolution path: locate a moved token, **or**
reuse/create a service account under the **`gdoc2netcfg`** GCP project
(`~/github/mithro/gdoc2netcfg` has the existing auth pattern) and share the sheet
with the SA. Blocks only the sheet-sync step, not flashing.

## 9. Pilot → checkpoint → rollout

1. **Pre-flight** (§11) — once.
2. **Pilot** a *fresh stock* puck end-to-end with full verification (§7). The
   existing dev-keyed bring-up unit can't validate the fresh-stock path.
3. **Checkpoint** — review pilot results before touching more pucks.
4. **Rollout** the remaining stock pucks (lighter verify), recording each.

## 10. Deliverables (`gwifi-openwrt/tools/fleet/`)

| File | Role |
|---|---|
| `build_gale_fleet_image.py` | §5 combined per-puck image builder (+ `futility verify` gate). |
| `flash_gale_fleet.py` | §6 flasher with serial-match guard + RO-last order. |
| `extract_identity.py` | §8 VPD/HWID/RO_FRID parser → `inventory/<serial>.json`. |
| `sync_sheet.py` | §8 push inventory records to the sheet (SA/token auth). |
| `flash_one_puck.py` | orchestrates steps 1–5 for a single puck (the operator entrypoint). |
| `docs/gale-fleet-firmware-flash-plan.md` | the step-by-step runbook. |

Reuses existing `gwifi-openwrt/tools/`: `chunk_read.py`, `raiden_write_region.py`,
`raiden_sr.py`, `ec_console.py`, `fmap_dump.py`. Also **ports `extend_cbfs_empty.py`
and `diff_regions.py` from `tmp/` into `tools/fleet/`** — the build step §5.2 and
the diff gates (§4, §5.6, §12) depend on them. Backups + `inventory/` live
**outside git** (per-device VPD/identity).

## 11. Pre-flight checklist

- [ ] SuzyQ enumerates (`18d1:500f`); `ec_console.py "gale version"` responds.
- [ ] Flash array unprotected (`raiden_sr.py`: `BP=CMP=WPS=0`); WP screw out (confirmed).
- [ ] Host NIC cabled to puck **WAN** port; DHCP/TFTP (dnsmasq) staged with a
      known-good OpenWrt netboot FIT.
- [ ] Artifacts current (✓ verified), dev keys present (✓), helper scripts present (✓).
- [ ] Fleet inventory: enumerate pucks, mark stock vs already-flashed (sheet
      Firmware col), pick the fresh-stock pilot.
- [ ] `backups/` + `inventory/` dirs created outside git.
- [ ] Sheet auth resolved (or accept TSV/local-only until then).

## 12. Risks

| Risk | Mitigation |
|---|---|
| Wrong image → wrong puck (corrupts VPD assumptions) | Serial-match guard in the flasher (§6). |
| Per-device VPD/calibration loss | RO_VPD never written; build is per-puck; offline diff gate (§5.6). |
| Partial flash bricks a unit | RO-last order leaves it stock-bootable; SuzyQ recovery always available (§6). |
| Per-puck flash time (RW_SECTION_A at 4 KiB chunks = hundreds of sessions) | 16 KiB chunks for the fleet after the pilot validates timing. |
| Sheet credential missing | Decoupled sync; local inventory is source of truth (§8). |

## 13. Decisions locked

Image = **single combined image / one flash session**. Slot B = **both slots
netboot-first** (A=B). Sheet IDs = **VPD identity + HWID + RO firmware version +
flash bookkeeping**. Auth = **find moved token, else `gdoc2netcfg` service
account**. eMMC = **deferred to a later network-driven pass**.
