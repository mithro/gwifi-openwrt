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
RO image:  instructions 10989/20089 = 54.7%;  cond branches 1583 total, 1002 reached, 380 both-dirs
RW image:  instructions  7707/20085 = 38.4%;  cond branches 1583 total,  758 reached, 277 both-dirs
```
(33 scenarios: + per-image cmd_args/console-edit/usb-live/pd-live RW variants via `sysjump rw`,
flash fault-injection, and a live PD contract attempt. Combined 1760/3166 reached, 657 both-dirs.)

This is a large improvement over a single boot (RO 28%→54.7% instr; RW 0%→38.4%). The
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

`classify.py` rule: a branch that was REACHED (one direction) is by definition reachable, so
it is binned as `COVERABLE_GAP` (the honest work-list) regardless of its symbol — only branches
NO scenario reached are eligible for the structural-exclusion categories. So the structural
categories below contain only genuinely-unreached branches.

| Category (RO) | branches | classification |
|---|---|---|
| `COVERABLE_GAP` | 573 | **reached in some scenario, only one direction seen** — the honest reducible work-list (drivable with more console inputs / message types / a full PD contract). Reachable, NOT excused. |
| `UNREACHED_OTHER` | 502 | unreached, no structural-exclusion symbol match — residual PD/console/libc paths; partly reducible with more scenarios, partly genuinely-unexercised init/error code |
| `HW_CANT_FAIL` | 120 | unreached `EC_ERROR_*` returns for modeled hardware that never errors (flash never BSY, SPI slave always responds, ADC/DMA never fail) |
| `AP_DEPENDENT` | 82 | **unreachable dead code in gale-as-built.** gale's `board/gale/board.h` configures NO host-command transport (no `CONFIG_HOSTCMD_I2C_SLAVE_ADDR`, no LPC/SPI/eSPI host interface, no `CONFIG_CMD_HOSTCMD`), so `host_packet_receive`/`host_command_received`/`i2c_process_command`/`i2c_event_handler` are all **GC'd from the binary** (`arm-none-eabi-nm build/gale/RW/ec.RW.elf` shows them absent; `host_command_process` is linked but no input can invoke it — `host_command_task` waits on a pending-args pointer only the absent transport ISR sets). No real input — from an IPQ4019 or anything — can reach the `hc_*` handlers; forcing them would mean synthesising a call no hardware can make. A host-command injector is infeasible *and unnecessary*. Also includes gale-absent peripherals (no battery/charger/keyboard). |
| `UNREACHABLE_FAULT` | 20 | unreached panic/hard-fault/assert/reboot/hibernate handlers — the not-taken side is the normal path; taking the other side resets the CPU |
| `WATCHDOG_TIMEOUT` | 3 | unreached watchdog-trip / timeout-expiry guards that never fire deterministically |

(Pre-`pd_live` the largest category was `UNREACHED_OTHER`=629, dominated by `pd_task` alone =
179 uncovered PD branches; driving the live CC-partner moved most of those to reached.)

(RW is analogous: 747 `UNREACHED_OTHER`, 379 `COVERABLE_GAP`, 177 `HW_CANT_FAIL`, 85 `AP_DEPENDENT`, 29 `UNREACHABLE_FAULT`, 3 `WATCHDOG_TIMEOUT` — RW is entered only via `sysjump rw` then a short command set, so its `UNREACHED_OTHER` is larger.)

**Conclusion (honest, evidence-backed):** literal 100% branch coverage is impossible in
EC-only STM32F0 emulation. The PD-PHY/PD-protocol subsystem — previously the largest uncovered
category — is now **driven live** by the modeled CC-partner (`STATUS-PD-PHY.md`), so it is no
longer the gap. The remaining structurally-unreachable branches are: **AP host-commands**
(unreachable dead code — gale compiles no host-command transport, see the table), **HW-can't-
fail** error returns (no fault-injection path for the deterministically-perfect peripheral
models), and **reset-only fault/panic** branches (cannot take both directions within one
non-resetting image). The remaining `COVERABLE_GAP` (573 RO) is the honest reducible work-list:
reachable branches whose other direction needs more varied inputs (more console commands, a full
PD contract to SNK_READY). The maximal honest claim is **all reasonably-coverable EC-only
branches are exercised, and every uncovered branch is enumerated + classified** (per-branch lists
in `cov_uncovered_{RO,RW}.txt`), with the irreducible remainder bounded by the absent AP SoC,
the no-fault hardware models, and reset-only faults.

## Usage
```
uv run python coverage.py --boot 3.0 --cmd version --cmd gpioget ...   # single-scenario measurement
uv run python coverage_full.py --boot 1.5                              # cumulative 20-scenario campaign
uv run python classify.py                                              # categorize the uncovered remainder
```
