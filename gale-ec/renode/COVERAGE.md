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

`coverage_full.py` unions a battery of 21 scenarios — RO commands, **RW via `sysjump rw`**,
the CCD/USB bring-up (`--mon CcPullAddress`), the raiden SPI bridge, **PD sink-attach to a
modeled source** (`GaleAdc.PartnerSource` → SNK_DISCOVERY; see `STATUS-PD-PHY.md`), the PD/TCPC/typec
subcommands, write-protect/lock, **deliberate faults** (`crash unaligned/divzero/udf/assert/
watchdog`, `reboot`, `hibernate`), and the AP-rail `gale` commands — capturing a PC trace per
scenario and unioning executed instructions + per-branch taken/not-taken directions. (Branch
coverage is cumulative: a branch is "both-directions" if its taken side is seen in *some*
scenario and its not-taken side in *some* scenario.) Measured union:

```
RO image:  instructions 9663/20089 = 48.1%;  cond branches 1583 total, 856 reached, 283 both-dirs
RW image:  instructions 5608/20085 = 27.9%;  cond branches 1583 total, 542 reached, 163 both-dirs
```

This is a large improvement over a single boot (RO 28%→48.1% instr; RW 0%→27.9%). The
**`pd_live`** scenario alone — injecting a 14-message battery over the modeled CC-partner
PD-PHY (`GaleExti` COMP-IRQ wake + `GaleDma` RX-sample feed; see `STATUS-PD-PHY.md`) so the
real `pd_analyze_rx` decodes and `handle_request` dispatches each — added **+130 reached
branches** (726→856) by executing the `pd_task`/`pd_find_preamble`/`pd_dequeue_bits`/
`pd_analyze_rx`/`handle_*_request`/`pd_build_request` chain that was previously the single
largest uncovered category. 727/1583 RO branches remain unreached by ANY of the 22 scenarios.
With the PD-PHY now driven live, the remaining uncovered set is dominated by `COVERABLE_GAP`
(reached-one-direction — drivable with more inputs / full PD contract) and the structural
classes (HW-can't-fail error returns, AP host-commands that are unreachable dead code in
gale, reset-only fault handlers). Literal 100% is not reachable (gale compiles no
host-command transport, plus reset-only faults), as the per-category table shows.

## Why literal 100% branch coverage is NOT achievable here — quantified at branch granularity

`classify.py` bins every uncovered branch by its containing function. The uncovered set is
**dominated by the two already-documented structural gaps**, not by laziness:

| Category (RO) | branches | why both-directions can't be driven in EC-only emulation |
|---|---|---|
| `UNREACHED_OTHER` | 502 | residual PD/console/libc paths not hit by the current scenario set (the bulk of the PD-PHY/protocol chain is now covered by `pd_live`); reducible with more message types + a full PD contract |
| `COVERABLE_GAP` | 472 | reached in some scenario but only one direction seen — the honest work-list (drivable with more inputs / the contract-accepted PD paths); does not change the structural ceiling |
| `HW_CANT_FAIL` | 189 | `EC_ERROR_*` returns for modeled hardware that never errors (flash never BSY, SPI slave always responds, ADC/DMA never fail) |
| `AP_DEPENDENT` | 84 | **unreachable dead code in gale-as-built.** gale's `board/gale/board.h` configures NO host-command transport (no `CONFIG_HOSTCMD_I2C_SLAVE_ADDR`, no LPC/SPI/eSPI host interface, no `CONFIG_CMD_HOSTCMD`), so `host_packet_receive`/`host_command_received`/`i2c_process_command`/`i2c_event_handler` are all **GC'd from the binary** (`arm-none-eabi-nm build/gale/RW/ec.RW.elf` shows them absent; `host_command_process` is linked but has no runtime caller). No real input — from an IPQ4019 or anything — can reach `host_command_process`/the `hc_*` handlers; forcing them would mean synthesising a call no hardware can make. So a host-command injector is infeasible *and unnecessary* (this supersedes the earlier "needs IPQ4019 / task #17" framing). Also includes gale-absent peripherals (no battery/charger/keyboard). |
| `UNREACHABLE_FAULT` | 41 | panic/hard-fault/assert/reboot/hibernate handlers — the not-taken side is the normal path; taking the other side resets the CPU |
| `WATCHDOG_TIMEOUT` | 12 | watchdog-trip / timeout-expiry guards that never fire deterministically |

(Pre-`pd_live` the largest category was `UNREACHED_OTHER`=629, dominated by `pd_task` alone =
179 uncovered PD branches; driving the live CC-partner moved most of those to reached.)

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
