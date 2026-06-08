<!-- SPDX-License-Identifier: Apache-2.0 -->
# gale boot process and SPI flash layout

Empirically validated end-to-end boot chain on Google Wifi (gale, IPQ4019).
Region behaviour and timing described here is grounded in live serial captures
from the AP console (`/dev/ttygwifi-ap`, SuzyQ if01 at 115200) across full
power-on → depthcharge boots, cross-checked against `cbfstool print`,
`futility show`, and an FMAP-aware byte-level region compare against the
factory image (`gale-spi-stock-2026-05-28.bin`).

## 1. Hardware actors

| Actor | Role |
|---|---|
| IPQ4019 SoC | The AP — Cortex-A7 ×4 ARMv7, with a tiny mask ROM in silicon and the rest of execution coming from SPI flash. Has BLSP UARTs, MMC controller, USB XHCI controller, multiple UARTs and SPI buses. |
| W25Q64FV | The 8 MiB SPI-NOR. Holds everything from SBL → coreboot → depthcharge. 4 KiB sector erase, 256 B page program. |
| STM32F072CB (EC) | Power sequencer, USB-PD, **CCD/SuzyQ debug bridge** (USART2↔USB if01 at 115200, plus the `raiden_debug_spi` USB endpoint used for the SPI bridge). |
| SLB9645TT (Infineon TPM, I²C) | Vboot rollback counters and PCR extends. |
| eMMC | Holds the actual kernel + rootfs + ChromeOS user data. depthcharge boots from here. |

## 2. SPI map with actual runtime roles

```
0x000000 ┬──────────────────── COREBOOT (CBFS, 3 MiB) ─────┐  RO_SECTION (3.875 MiB)
         │ 0x000000-0x01FFFF  raw bootblock (NOT CBFS) — Qualcomm-SBL-format header + boot code
         │ 0x020000           CBFS master header
         │                    fallback/verstage  (39 KiB) — vboot RO
         │                    fallback/romstage  (18 KiB) — DDR init (RO copy, used only on recovery)
         │                    fallback/ramstage  (28 KiB) — device init (RO copy, recovery only)
         │                    fallback/payload   (66 KiB) — RO depthcharge (recovery only)
         │                    cdt.mbn, ddr.mbn, tzbsp_no_xpu.mbn — Qualcomm DDR / TrustZone blobs
         │                    u-boot.dtb — device tree fragment in mrc_cache type
0x300000 ├── FMAP   (4 KiB)            — the region map itself, found by scanning for "__FMAP__"
         ├── GBB    (892 KiB)          — Google Binary Block:
         │                                rootkey  (verifies VBLOCK_A/B keyblocks)
         │                                recovery_key (verifies recovery kernel image)
         │                                HWID, bmpvf (unused on headless gale)
         │                                flags (currently 0x00000000)
         ├── RO_FRID (256 B)           — RO firmware version string (e.g., "google_gale.7651.1.0")
0x3E0000 ├── RO_VPD  (128 KiB)         — Per-device factory data: serial, mlb_serial, MAC, region,
                                          WiFi calibration vectors (calibration0/calibration1)        }  WP_RO (4 MiB)
0x400000 ┬── VBLOCK_A (8 KiB)          — Keyblock (data_key signed by GBB rootkey)
         │                              + Preamble (FW_MAIN_A body hash signed by data_key)
         │                              + flags (USE_RO_NORMAL is bit 0; see §4 below for caveat)
         │── RW_SECTION_A (1408 KiB)
         │     FW_MAIN_A (1336 KiB) — the actually-running RW firmware CBFS:
         │       fallback/romstage  (RW romstage — what coreboot loads after vboot OKs slot A)
         │       fallback/ramstage  (RW ramstage)
         │       fallback/payload   (RW depthcharge — this is the one that boots the kernel)
         │       cdt.mbn / ddr.mbn / tzbsp_no_xpu.mbn — RW copies of Qualcomm blobs (CAN differ
         │           from RO; e.g. stock A has tzbsp 393256 B vs B's 37928 B)
         │     RW_FWID_A (256 B)   — RW slot A firmware version string
         │     RW_SHARED/SHARED_DATA (64 KiB) — VbSharedDataHeader (vboot state passed verstage→
         │           ramstage→depthcharge; updated during boot)
0x560000 ├── RW_GPT_PRIMARY / RW_GPT_SECONDARY (128 KiB) — cached copy of eMMC GPT (lets verstage
         │                                                  see kernel partition table without
         │                                                  initializing MMC)
0x580000 ┬── VBLOCK_B + RW_SECTION_B + FW_MAIN_B + RW_FWID_B  — Slot B (same structure as A;
         │     A/B exist for safe field updates: write B, try B, if it fails fall back to A)
0x6E0000 ├── RW_VPD  (32 KiB)    — Post-manufacturing per-device data, mutable
0x6E8000 ├── RW_ELOG (32 KiB)    — Boot event log (recoveries, errors)
0x6F0000 ├── RW_NVRAM (64 KiB)   — The critical mutable state:
         │                          recovery_request bit, recovery_reason byte, recovery_subcode,
         │                          fw_try_next, fw_try_count, fw_result, dev_boot_*, ...
         │                          Vboot reads this in Phase 1 and writes back at the end.
0x700000 └── RW_LEGACY (1024 KiB) — Alternative payload slot (Ctrl+L from dev screen). EMPTY on
                                     gale (still 0xff).
```

## 3. Boot timeline — what's actually observed on this hardware

**T+0 — Power on.** EC asserts `SYS_PWR_EN`; VDD_3P3_EN/2G_EN/1P35/1P1_CPU/1P8 all
go high; IPQ4019 reset releases. Cortex-A7 starts in mask ROM.

**T+~1 ms — IPQ4019 mask ROM.** Reads first several KiB of SPI at offset 0.
Expects a Qualcomm-format SBL header + signed image (the format the gale's stock
ChromiumOS coreboot was built to emit). Copies that into IPQ4019 internal SRAM.
Hands off.

**T+~10 ms — Raw bootblock.** Runs from SRAM. Minimum SoC init: clocks, SPI
controller, **UART0 (USART2 on the EC side)** — the EC's USART2↔USB if01 bridge
starts forwarding bytes from this moment on. First serial line seen:
`SF: Detected W25Q64 with sector size 0x1000, total 0x800000`.

Bootblock then:

- Reads FMAP at SPI `0x300000`
- Locates CBFS master header at SPI `0x20000`
- Loads `fallback/verstage` from RO CBFS (offset `0x1cf40` in CBFS = SPI `0x3cf40`, size 39036 B)
- Jumps to verstage

**T+~50 ms — Verstage (`coreboot-60d1b1c Jan 2017`, RO).** This is **vboot RO**.
Steps captured in live boot:

```
Phase 1
  FMAP: area GBB found @ 301000 (913152 bytes)         ← reads GBB
  VB2:vb2_check_recovery()                              ← reads RW_NVRAM (offset 0x6f0000),
                                                          checks recovery_request bit
                                                          (if set → skip RW evaluation entirely)
Phase 2                                                 ← unpack GBB rootkey
  VB2:vb2_unpack_key()
Phase 3                                                 ← read VBLOCK_A, verify
  FMAP: area VBLOCK_A found @ 400000 (8192 bytes)
  VB2:vb2_verify_keyblock() Checking key block signature
  VB2:vb2_verify_fw_preamble() Verifying preamble
Phase 4                                                 ← hash + verify FW_MAIN_A body
  FMAP: area FW_MAIN_A found @ 402000 (1367808 bytes)
  VB2:vb2api_init_hash() HW crypto for hash_alg 2 not supported, using SW   ← SHA-256 in software
  VB2:vb2_rsa_verify_digest()                           ← RSA digest verify of body hash
Slot A is selected                                      ← OUTCOME: chose slot A
```

Once vboot picks a slot, **it tells coreboot to switch CBFS context to that
slot's `FW_MAIN_<X>`**. Live evidence:

```
CBFS: 'VBOOT' located CBFS at [402000:485e40)            ← CBFS context is now FW_MAIN_A,
                                                            not the RO COREBOOT region
```

The bytes `402000:485e40` are FW_MAIN_A's range (offset 0x402000, size 0x83e40
≈ 528 KiB which is the *populated* CBFS span, smaller than the 1336 KiB region
size). Every subsequent CBFS load reads from this RW range, **not** the RO range.

**T+~150 ms — Romstage from RW CBFS** (`coreboot-9ff56ab Dec 2018`, RW build):

```
CBFS: Locating 'fallback/romstage'
CBFS: Found @ offset 0 size 469a
coreboot-9ff56ab Wed Dec 19 18:42:09 UTC 2018 romstage starting...
```

Romstage:

- Reads `cdt.mbn` from RW CBFS (Qualcomm Customer Data Table — board DDR params)
- Reads `ddr.mbn` from RW CBFS (Qualcomm DDR training table)
- Initializes DDR
- `SDI Entry: 0x860038d` — System Debug Image entry, Qualcomm-specific
- Maps DRAM as writeback
- Initializes CBMEM (the in-memory database coreboot uses for cross-stage data) at `0x8727f000` and `0x8727ec00`
- Creates the `vboot_handoff` structure (passes vboot state to ramstage)
- Reads tristate GPIOs → board ID `10`
- "Copying FW preamble" — saves preamble to CBMEM for later stages
- Loads `fallback/ramstage` from RW CBFS

**T+~300 ms — Ramstage from RW CBFS:**

- Re-reads FMAP (each stage independently scans, because they don't share memory state cleanly)
- Reads `RO_VPD` and `RW_VPD` for per-device data
- Enumerates devices (just `CPU_CLUSTER:0` on gale — most peripherals are SoC-internal)
- Allocates address-space resources (the three RAM regions: `0x80000000-0x8724bfff`, `0x87280000-0x874fffff`, `0x88000000-0x9fffffff`)
- **Loads + starts TZBSP** (`tzbsp_no_xpu.mbn` from RW CBFS) — this is the TrustZone/secure-monitor blob that runs at EL3
- Initializes USB HOST1 XHCI controller (`0x8a00000`, version `5533270a`)
- **Reads WiFi calibration from VPD** (`wifi_base64_calibration0`, `wifi_base64_calibration1`) and copies them to CBMEM where depthcharge/kernel can find them
- Writes the **coreboot table** at `0x8724c000` — this is what depthcharge/kernel reads to learn memory map, CBMEM locations, etc.
- Reads tristate GPIOs again → board ID `10`
- Builds a 5-GPIO table for the payload:

```
NAME           | PORT      | POLARITY | VALUE
developer      | 0x29      | low      | high
recovery       | 0x39      | low      | low
write protect  | 0x35      | low      | low
power          | undefined | low      | low
lid            | undefined | low      | high
```

- Loads `fallback/payload` from RW CBFS (RW depthcharge):
  - CBFS file at offset `0x26800` size `0x10341` = 66369 B (file-internal offsets in FW_MAIN_A's CBFS)
  - Compression = LZMA, decompresses to `0x88104040`
  - Memsz `0x1249b70` (~18.6 MiB after decompression — bounce buffer at `0x9ffcf000` used)
  - Entry point `0x88104041`
  - Jumps

**T+~1.5 s — Depthcharge runs.** Captured init:

```
Starting depthcharge on gale...
clock_config_mmc : 1
WW_RING: initialized controller found at 0x32             ← LED ring at I²C 0x32
The GBB signature is at 0x88004020 and is:  24 47 42 42   ← '$GBB' magic
Wipe memory regions: [...]                                 ← zeroes out unused DRAM
Initializing XHCI USB controller at 0x8a00000.
Calling VbSelectAndLoadKernel().
TPM: TlclRead(0x1008, 13)                                 ← TPM kernel rollback counter
TPM: RollbackKernelRead 10001                             ← counter value
```

Depthcharge's `VbSelectAndLoadKernel()`:

- **Normal mode**: scans eMMC partitions, looks for KERN-A and KERN-B partitions with valid headers, verifies kernel image signature against GBB's kernel subkey, loads best-priority + try-counter kernel, sets up bootargs, jumps to kernel entry.
- **Recovery mode** (NVRAM `recovery_request=1`): calls `VbBootRecovery()` — loops waiting for a recovery USB device or for the user to release the recovery button.
- **Dev mode**: shows the dev-screen ("OS verification is off…") and offers Ctrl+D (continue), Ctrl+U (USB boot if allowed), Ctrl+L (legacy from `RW_LEGACY` if allowed). On gale (headless), no screen — but it still polls for keystrokes.

**T+~3 s+ — Kernel runs.** Linux. From whatever path got picked.

## 4. The A/B slot model as it actually operates on gale

```
Cold boot
  │
  ├── Bootblock (RO, always)
  ├── Verstage  (RO, always)
  │     │
  │     │  vboot reads RW_NVRAM:
  │     │     fw_try_next  : "try A or B next?" — set by chromeOS after writing an update
  │     │     fw_try_count : number of tries left for fw_try_next
  │     │     fw_result    : last boot's outcome (success/failure/trying)
  │     │     recovery_request : 1 = force recovery this boot
  │     │     recovery_reason  : why recovery was requested
  │     │
  │     │  vboot determines target slot (default A) and verifies it:
  │     │     keyblock signature (against GBB rootkey)
  │     │     preamble signature (against keyblock's data_key)
  │     │     body hash (computes SHA-256 over FW_MAIN_<X>, verifies against preamble's hash)
  │     │
  │     ▼
  │     If slot A passes  → CBFS context switches to FW_MAIN_A → continue with RW
  │     If slot A fails   → try B
  │     If B also fails   → set recovery_request, reboot
  │     If recovery_request was already 1 → skip the try, go straight to recovery (RO)
  ▼
  Normal path                            Recovery path
  ─────────────                          ─────────────
  RW romstage   (from FW_MAIN_A)         RO romstage   (from COREBOOT)
  RW ramstage   (from FW_MAIN_A)         RO ramstage   (from COREBOOT)
  RW depthcharge (FW_MAIN_A/payload)     RO depthcharge (COREBOOT/payload)
  │                                       │
  │  Normal kernel boot                   │  VbBootRecovery():
  │  VbSelectAndLoadKernel():             │    headless: silently wait for USB
  │    scan eMMC KERN-A / KERN-B          │    sighted: display "insert recovery media"
  │    verify against kernel subkey       │    if USB inserted: verify with recovery_key
  │    load to DRAM, jump                 │      load recovery kernel from USB
  │                                       │
  │  On any failure: set recovery_request │  Until something interrupts: stay in this loop
  │  in NVRAM, reboot                     │
```

**Note on USE_RO_NORMAL.** The preamble flag `VB_FIRMWARE_PREAMBLE_USE_RO_NORMAL`
(bit 0) is set in this gale's stock VBLOCK_A and VBLOCK_B. In principle this
flag tells vboot "skip RW body load and continue from RO". On this device
the flag is **not honoured** — runtime shows vboot doing full body hashing
(Phase 4) and on success switching CBFS context to `FW_MAIN_A` and loading
RW romstage/ramstage/payload from the RW slot. Almost certainly the cause is
that gale's coreboot doesn't pass `VB_INIT_FLAG_RO_NORMAL_SUPPORT` into vboot's
`VbInit()`, so the preamble request is ignored. Treat the flag as cosmetic on
this hardware — **the body is verified and the RW chain runs**.

## 5. Diagnostic progression (this session)

Tracked as each layer of damage to the SPI flash was repaired and the boot was
re-tested. Each fix moved the failure point one stage downstream:

| Fix done | vboot got to | Final outcome |
|---|---|---|
| Bootblock only | verstage Phase 3 keyblock | `Wrong key size for algorithm` → recovery |
| + GBB rootkey | verstage Phase 3 keyblock parse | `Key block signature off end of block` → recovery |
| + VBLOCK_A/B headers | verstage Phase 4 body hash | `Digest check failed!` → recovery |
| + FW_MAIN_A/B bodies | All vboot phases pass, RW romstage→ramstage→depthcharge runs | Depthcharge `VbSelectAndLoadKernel` fails at eMMC → sets `recovery_reason=0x5b` → reboot → recovery sticks |

Observed steady state with everything repaired but eMMC empty: the device boots
**once** through the RW path (RW coreboot Dec 2018 → RW depthcharge → fail to
find an eMMC kernel) → reboots → all subsequent boots go straight to recovery
(RO coreboot Jan 2017 → RO depthcharge → `VbBootRecovery() waiting for manual
recovery`).

## 6. Region-by-region role table

| Region | Read by | Mutability in normal operation | Role |
|---|---|---|---|
| Raw bootblock (`0x0-0x1FFFF`) | IPQ4019 mask ROM | Immutable (WP-protected in production) | Qualcomm-signed SBL + early SoC init |
| `COREBOOT/fallback/verstage` | bootblock | RO | Vboot decision logic; runs even on normal-path boots |
| `COREBOOT/fallback/{romstage,ramstage,payload}` | verstage (recovery only on healthy device) | RO | Recovery firmware. Includes RO depthcharge that does `VbBootRecovery`. |
| `COREBOOT/cdt.mbn`, `ddr.mbn`, `tzbsp_no_xpu.mbn` | RO romstage (recovery only) | RO | Recovery-path Qualcomm blobs |
| `COREBOOT/u-boot.dtb` (mrc_cache type) | RO ramstage | RO | Device tree fragment (recovery-path) |
| `FMAP` | bootblock + verstage (each stage rescans) | RO | Region map itself |
| `GBB.rootkey` | verstage Phase 2 | RO | Verifies VBLOCK keyblocks |
| `GBB.recovery_key` | depthcharge in recovery mode | RO | Verifies recovery kernel from USB |
| `GBB.HWID` | depthcharge + crossystem | RO | Board identifier |
| `GBB.flags` | bootblock/verstage/depthcharge at various points | RO | Boot policy (dev_switch, legacy boot, serial enable, etc.) — currently `0x00000000` |
| `RO_FRID` | crossystem/depthcharge | RO | Reports "ro_fwid" |
| `RO_VPD` | RW ramstage (for WiFi calibration), kernel | RO | Per-device factory identity |
| `VBLOCK_A` keyblock | verstage Phase 3 | RO once written by updater | Signing chain: rootkey → data_key |
| `VBLOCK_A` preamble | verstage Phase 3-4 | RO once written | Body hash + flags + firmware_version |
| `FW_MAIN_A` CBFS (entire body, hashed) | verstage Phase 4 (hashes); coreboot post-vboot (loads stages from) | RO once written; chromeOS updater rewrites entire slot atomically | Where romstage/ramstage/depthcharge actually load from in normal boot |
| `RW_FWID_A` | crossystem/updater | RO once written | "rw_fwid_a" string |
| `RW_SHARED` / `SHARED_DATA` | written by verstage; read by ramstage and depthcharge | RW (per boot) | `VbSharedDataHeader` — vboot state passed between stages |
| `RW_GPT_PRIMARY/SECONDARY` | depthcharge | RW (chromeOS writes when partitions change) | Cached eMMC GPT |
| `VBLOCK_B` + `FW_MAIN_B` + `RW_FWID_B` | (mirror of A) | RW | The *other* RW slot for A/B updates |
| `RW_VPD` | ramstage, depthcharge, userspace | RW | Mutable per-device data |
| `RW_ELOG` | coreboot append, mosys read | RW | Boot event log |
| `RW_NVRAM` | verstage Phase 1; written by verstage and depthcharge | RW (every boot) | The mutable boot state: try counters, recovery_request, recovery_reason, dev flags |
| `RW_LEGACY` | RW depthcharge if dev+legacy enabled (Ctrl+L) | RW (rarely written) | Alt payload (empty on gale) |

## 7. The signing chain

```
GBB.rootkey  ──signs──▶  VBLOCK_A.keyblock.data_key
                                      │
                                      └──signs──▶  VBLOCK_A.preamble
                                                      │
                                                      contains body_hash of FW_MAIN_A
                                                                            │
                                                                            verified by vboot Phase 4

GBB.recovery_key ──signs──▶ recovery kernel partition on USB or eMMC

(kernel_subkey from VBLOCK preamble ──signs──▶ kernel partition on eMMC verified by depthcharge)
```

When chromeOS updates the firmware:

- Writes new bytes into FW_MAIN_B (the inactive slot)
- Writes new VBLOCK_B with re-signed preamble (body hash of the new bytes, signed by the data_key, keyblock signed by rootkey)
- Updates RW_NVRAM with `fw_try_next=B`, `fw_try_count=N`, `fw_result=trying`
- Reboots
- Verstage Phase 1 reads NVRAM, sees try_next=B → tries B
- If B verifies and the kernel boots and chromeOS reports success → `fw_result=success`, B becomes primary
- If B fails → decrement try_count, eventually fall back to A

This is why both slots and the try-counter machinery exist: rollback-safe field updates.
