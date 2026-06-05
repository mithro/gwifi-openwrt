# gale EC reconstruction — fidelity report

## Result

`make BOARD=gale` builds `ec.bin` (131072 B), and an **independent reviewer
certified it FUNCTIONALLY EQUIVALENT** to the on-device dump
(see [`EQUIVALENCE-REVIEW-2.md`](EQUIVALENCE-REVIEW-2.md)).

- **Reset vectors: byte-identical** — RO `SP=0x200004c0 PC=0x080000ed`; RW `PC=0x080100ed`.
- **FMAP: matches the dump exactly** — `EC_RO`/`EC_RW` (64 KB each), `RO_FRID@0xc4`,
  `RW_FWID@0x100c4`. (Only the FMAP self-offset differs, a downstream effect of the size delta.)
- **RO content size:** 58036 B vs dump's 58016 B (**+20 B**, = the version-banner length).

## Method — differential reverse-engineering

~95% of the 128 KB image is **public** code at `firmware-gale-8281.B`
(`common`/`chip/stm32`/`core/cortex-m0`/`driver`); only `board/gale` was missing.
Board data structures and logic were decoded from the on-flash tables with
radare2 / `arm-none-eabi-objdump`, cross-checked against the live EC
(`gpioget`/`taskinfo`/`version`/`flashinfo`) and the `servo_micro`/`ryu` templates,
then each board function was disassembled in both the dump and the rebuilt ELF and
compared semantically (the two were built with different-era toolchains, so
register/scheduling/address differences are expected and immaterial).

### Recovered exactly from the binary
- All **29 GPIO signals** (ports/pins/flags) + **7 ALTERNATE** mux entries
- **USB descriptors** — VID:PID `18d1:500f` "Gale debug"; IF0 EC_PD console / IF1 AP console / IF3 raiden SPI
- **4 ADC channels**; **task set** `HOOKS / HOSTCMD / CONSOLE / PD_C0` (+ idle), stacks 640/488/488/640
- **`command_gale`** + every subcommand (power/polarity/cc/vbus/dev/rec) and the exact **`set_ap_power` rail sequencing** (no inter-rail delays)
- **`spi_devices[]`** (the W25Q64 AP-flash raiden bridge), `i2c_ports[]`, `usb_strings[]`, SS-mux
- **USB-PD policy** — PDOs (`pd_snk_pdo=0x2201912c`, src empty), `pd_check_*` hooks, `pd_set_input_current_limit`, and the PD PHY (comparator, SPI1, TIM16/TIM1, EXTI)

## Two review passes (independent, adversarial, disassembly-based)

1. [`EQUIVALENCE-REVIEW-1.md`](EQUIVALENCE-REVIEW-1.md) — verdict **NOT EQUIVALENT**: 4 material USB-PD divergences found:
   (a) `pd_select_polarity` used the INM4 external pin instead of the internal VREF1/2 comparator reference (a `board/twinkie`-copy bug — would degrade PD RX);
   (b) `board_no_charger` called `pd_comm_enable` instead of `pd_set_dual_role`;
   (c) `pd_tx_enable` didn't force the active CC sense-pin low during transmit;
   (d) `pd_custom_vdm` omitted the `VDO_CMD_CCD_EN` case.
2. All 4 fixed, each re-verified **instruction-for-instruction** against the original.
3. [`EQUIVALENCE-REVIEW-2.md`](EQUIVALENCE-REVIEW-2.md) — re-certification: verdict **FUNCTIONALLY EQUIVALENT**; all 4 *FIXED-MATCHES*, no regressions.

## Documented immaterial deltas (do NOT affect on-device behavior)
- `console_channel` enum: `CC_USBPD` index 26 (rebuild) vs 23 (dump) — only labels which debug channel a print appears on.
- `command_cc` current-display lower bound 200 vs 250 mV — console readout only.
- Version banner/timestamp; instruction scheduling/addresses/struct offsets; the ~20 B size delta.

## Toolchain
`gcc-arm-none-eabi 5.4.1` (2016q3). The EC tree pins only the `arm-none-eabi`
tuple (`core/cortex-m0/build.mk`), with no version — and the upstream EC docs say
to use the distro `gcc-arm-none-eabi` — so version-exactness was never required;
this era-matches the firmware's 2016-10-03 build date. Verification is therefore
structural/semantic, not byte-exact (byte-exactness was never a goal).
