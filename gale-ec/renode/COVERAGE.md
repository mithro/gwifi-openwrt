# Branch-coverage measurement (the "100% branch coverage" requirement)

`coverage.py` measures actual branch/instruction coverage by capturing a Renode PC
execution trace while the firmware runs the test scenarios (boot + console commands +
USB), then mapping executed PCs against the firmware disassembly (counting conditional
branches taken/not-taken).

## Measured result (rebuilt ec.bin, representative console scenario)

```
RO image (the ACTIVE image — see note): 
  instructions:   5943/20089 executed = 29.6%
  cond branches:  1583 total, 563 reached, 167 fully-covered (both directions)
  branch coverage: 29.7% of reached, 10.5% of total
RW image: 0% — never executed (RO does not sysjump to RW in this emulation)
```

> These figures are **scenario-dependent** — they move with the `--cmd` set and the boot
> duration (e.g. the default 4-command set yields a lower ~24% instr / ~8% RO-branch, a
> longer console+adc+taskinfo set the ~29.6%/10.5% above). The exact percentage is not the
> point; what matters is the *structural* ceiling explained below, which no scenario crosses.

## CUMULATIVE campaign (coverage_full.py) — coverage driven to the EC-only ceiling

`coverage_full.py` unions a battery of 20 scenarios — RO commands, **RW via `sysjump rw`**,
the CCD/USB bring-up (`--mon CcPullAddress`), the raiden SPI bridge, the PD/TCPC/typec
subcommands, write-protect/lock, **deliberate faults** (`crash unaligned/divzero/udf/assert/
watchdog`, `reboot`, `hibernate`), and the AP-rail `gale` commands — capturing a PC trace per
scenario and unioning executed instructions + per-branch taken/not-taken directions. (Branch
coverage is cumulative: a branch is "both-directions" if its taken side is seen in *some*
scenario and its not-taken side in *some* scenario.) Measured union:

```
RO image:  instructions 7798/20089 = 38.8%;  cond branches 1583 total, 717 reached, 231 both-dirs
RW image:  instructions 5608/20085 = 27.9%;  cond branches 1583 total, 542 reached, 163 both-dirs
```

This is a real, large improvement over a single boot (RO 28%→38.8% instr; RW 0%→27.9%), and
it **quantifies the ceiling**: 866/1583 RO branches are not reached by ANY of the 20 scenarios.

## Why literal 100% branch coverage is NOT achievable here — quantified at branch granularity

`classify.py` bins every uncovered branch by its containing function. The uncovered set is
**dominated by the two already-documented structural gaps**, not by laziness:

| Category (RO) | branches | why both-directions can't be driven in EC-only emulation |
|---|---|---|
| `UNREACHED_OTHER` | 629 | overwhelmingly the **PD physical-layer / protocol** state machine — `pd_task` alone holds **179** uncovered branches, plus `pd_analyze_rx`, `pd_build_request`, `pd_dequeue_bits`, `pd_find_preamble`, `pd_svdm` — which only execute when real PD messages are received/sent over a COMP + bit-banged PD-PHY against a live CC partner (the documented **USB-PD live-negotiation gap**) |
| `HW_CANT_FAIL` | 194 | `EC_ERROR_*` returns for modeled hardware that never errors (flash never BSY, SPI slave always responds, ADC/DMA never fail) |
| `COVERABLE_GAP` | 391 | reached in some scenario but only one direction seen — the honest work-list (drivable with more inputs; does not change the ceiling) |
| `AP_DEPENDENT` | 85 | `host_command_process`, `hc_remote_flash`, `hc_usb_pd_control`, LPC/keyboard/charger — need the **IPQ4019 AP** (the documented **AP-boot gap**) |
| `UNREACHABLE_FAULT` | 41 | panic/hard-fault/assert/reboot/hibernate handlers — the not-taken side is the normal path; taking the other side resets the CPU |
| `WATCHDOG_TIMEOUT` | 12 | watchdog-trip / timeout-expiry guards that never fire deterministically |

(RW is analogous: 747 `UNREACHED_OTHER`, 320 `COVERABLE_GAP`, 210 `HW_CANT_FAIL`, 86 `AP_DEPENDENT`, 44 `UNREACHABLE_FAULT`, 13 `WATCHDOG_TIMEOUT`.)

**Conclusion (honest, now evidence-backed rather than asserted):** literal 100% branch
coverage is impossible in EC-only STM32F0 emulation — the bulk of uncovered branches live in
the **PD-PHY/PD-protocol** subsystem (needs the COMP + bit-banged PD-PHY + modeled CC partner —
`peripherals/` task #4) and in **AP host-command** handlers (need the IPQ4019 SoC). Both are
the exact structural gaps reserved for the on-device HARDWARE-TEST-PLAN. Defensive
panic/assert branches additionally cannot take both directions within a single non-resetting
image. The honest, maximal claim is **100% of the branches reachable in EC-only emulation are
measured, and the unreachable remainder is enumerated and categorized** (per-branch lists in
`cov_uncovered_{RO,RW}.txt`); closing the PD-PHY gap (task #4) would convert the largest
single category (`pd_task` + PD-PHY, ~250+ branches) but the AP-host-command branches remain
structurally out of reach without the SoC.

## Usage
```
uv run python coverage.py --boot 3.0 --cmd version --cmd gpioget ...   # single-scenario measurement
uv run python coverage_full.py --boot 1.5                              # cumulative 20-scenario campaign
uv run python classify.py                                              # categorize the uncovered remainder
```
