# Gale SPI-flash "wedge": evidence ledger (2026-07-07)

**Device:** Google Wifi "gale", EC = STM32F072CB, stock FW `gale_v1.1.5337-0115719`.
**Symptom under study:** during USB-SPI bridge use, at a deterministic moment the
shared W25Q64 flash bus dies. This document is the running record of what has
been *measured* on real hardware, which hypotheses are dead (and what killed
them), and which remain live.

> An earlier revision of this file described a "shared-EPnR CTR clobber race"
> in `chip/stm32/usb_spi.c`. That theory was **disproven by usbmon capture**
> (host ops strictly serial; the wedge shows USB status SUCCESS with zeroed
> data, not lost completions) and is retired.

## 1. The reproducible event

Self-checking read burns (`budgetprobe --burn sread`) against a fixed FMAP
address, fresh session each run (EC reboot + park + bridge ENABLE):

| # | run | wedge at (after burn start) | small# at wedge |
|---|-----|------------------------------|-----------------|
| 1 | rc=4 | +0.368 s | 730 |
| 2 | rc=4 | +0.358 s | 580 |
| 3 | rc=4 | +0.364 s | 722 |
| 4 | rc=4 | +0.360 s | 624 |
| 5 | rc=4 | +0.365 s | 723 |
| 6 | rc=4 +2ms delay | ~+0.36 s | ~144 |
| 7 | rc=4 +drain(s) | ~+0.35 s | 55–101 |

**The wedge is wall-clock anchored: t = 0.363 s ± 0.005 after the bridge
comes up (rails-up + ~0.11 s), across transaction counts varying 10×.**
Burn start ≈ ENABLE + 110 ms; the rails (SYS_PWR_EN + VDD_3P3) rise inside
ENABLE handling, so the event sits at ≈ rails-up + 0.47 s.

Occasional runs (2 of ~12 at rc=4-shapes; prog k=2, wpp k=4) pass the window
and then run clean for 6000+ txns — the event either does not fire or fires
harmlessly, and never re-fires. **It is one-shot per session.**

## 2. The three post-wedge presentations (bimodal collapse)

* **Zeros-mode** (most runs under continuous traffic): every subsequent
  bridge transaction returns USB status `0x0000` (SUCCESS) with all-zero
  data — small reads, 32-byte reads, and RDID alike. Permanent for the
  session.
* **Hang-mode** (idle at event time, or sometimes mid-traffic): the next SPI
  transaction never completes; bulk IN times out; the EC console dies; the
  device may drop off the bus and/or become unopenable (EIO) for minutes,
  then eventually recovers via reboot (reset flags show reset-pin/soft/hard).
* **Post-idle first-touch death**: with 2 s of pure idle after bring-up, the
  *first* transaction afterwards hangs the EC outright.

The same deterministic event collapsing into different broken states across
runs suggests **corruption of shared state**, not a clean external signal.

## 3. Localization: EC↔flash, not USB, not the host

* usbmon: host bulk ops strictly serial; no foreign URBs; wedge transition is
  `SUCCESS+data` → `SUCCESS+zeros` on consecutive identical commands.
* **`spixfer rlen 0 0x1f 3` (EC console → EC-side `spi_transaction`, no USB
  data path) returns `Data: 000000` post-wedge.** The wedge lives between the
  EC's SPI master and the flash.
* Host autosuspend is disabled for the device (`power/control=on`).
* Mechanically: SPI2+DMA "complete" (status SUCCESS needs DMA completion; DMA
  needs SPI DRQs), while MISO (PB14, pull-down configured) reads 0x00 —
  i.e. **the flash is not driving** (CS not effective / flash ignoring /
  pins disconnected), or reads hang on a half-dead peripheral
  (`spi_master.c` FIFO loops have no timeout → hang-mode).

## 4. Hypotheses eliminated (with the killing evidence)

| hypothesis | killed by |
|---|---|
| Host creates overlapping IN/OUT on EP3 | usbmon: strictly serial |
| EPnR CTR-clobber race in `usb_spi.c` | wedge = SUCCESS+zeros, not lost completions |
| Host-side timing (delays/drains serialize) | made it *earlier* in count, same wall-clock |
| Linux autosuspend | `power/control=on`; wedge under continuous traffic |
| AP powered on by EC (`set_ap_power(1)`) | `set_ap_power_on()` prints `power on ap` unconditionally; post-wedge console backlog = `'> '` only; AP console 0 bytes; CPU rails measured off |
| CCD teardown (`ccd_set_mode(DISABLED)`) | any mode change calls `usb_release()` = USB disconnect; no disconnect at wedge (bulk keeps completing, dmesg silent) |
| `common/spi_flash.c` re-init under us | not built for gale (no `CONFIG_SPI_FLASH`); entry points are console-only |
| SYSCFG SPI2-DMA remap cleared at runtime | single writer: `board_config_pre_init`, boot-only, `|=` |
| I2C1 slave DMA fighting SPI2 on CH6/CH7 | F0 I2C driver is interrupt-only, no DMA |
| AP console USART2 DMA on CH6/CH7 | gale configures interrupt-mode USART |
| GPIOB bus-activity from a hidden master while parked | 60× GPIOB IDR watch: constant 0x9fcc, I2C idle-high, SPI idle |

## 5. Live threads

1. **Frame-length dependence**: rc=32 burns have run clean through the event
   window (2 clean runs so far; ×3 re-run in progress to exclude survivor
   luck — round-0 had 2/12 lucky survivors). If rc=32 truly never wedges,
   the event itself is *triggered* by small-frame traffic at t≈0.363 s, not
   merely revealed by it. If rc=32 does wedge, everything simplifies to a
   deterministic one-shot timer.
2. **PD task**: port state is `SNK_ACCESSORY` (debug accessory), polling CC
   via ADC every 100 ms at the highest task priority. No board-level PD
   timer found at ~350 ms; protocol-layer audit incomplete. Next
   observability step: `pd dump 2` before the burn + no-drain console
   harvest at wedge.
3. **Deterministic ~0.47 s-after-rails-up actor on the 3.3 V domain**
   (AP-side pad leakage onto shared flash pins /HOLD engagement, etc.):
   would need scope probes on CS/CLK/MISO/HOLD to progress.
4. **Reinit discriminator** (host DISABLE+ENABLE re-runs
   `usb_spi_board_enable`: rails, `gpio_config_module`, SPI2 clock+reset):
   if it revives the bus → lost-enable-state (firmware side); if not →
   external bus state. Wired into triage; first attempt lost to hang-mode;
   re-running.

## 6. Operational facts (for the flasher)

* `gflash.py` performed 270,603 transactions wedge-free; its session shape
  differs (it idles >0.5 s after ENABLE before hammering; large reads).
* A wedged EC is NOT recovered by USB reset (`greset`); post-wedge the EC
  can refuse new ENABLE control transfers until an MCU reboot (console
  `reboot` when alive, else eventual self-recovery, minutes).
* Fresh-session bring-up after an EC reboot is reliable: `sysinfo` unlocked,
  `gale power off` park, ENABLE, RDID=ef4017, and large-read burns run
  multi-second clean.
