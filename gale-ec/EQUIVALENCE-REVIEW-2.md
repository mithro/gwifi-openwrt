# EC Firmware Equivalence RE-CERTIFICATION — gale (Google Wifi) ChromiumOS EC

**Status: COMPLETE — VERDICT: FUNCTIONALLY EQUIVALENT**

Independent, adversarial re-review #2. First review (EQUIVALENCE-REVIEW.md) flagged 4
MATERIAL USB-PD divergences; those were patched. This review independently disassembles
BOTH the original dump and the rebuilt-with-symbols ELF to (A) verify each of the 4 is now
semantically equivalent, (B) confirm no new divergence/regression in surrounding PD code.

- Ground truth dump: `/home/tim/local/gwifi/ec-rebuild/work/gale-RW.bin` (load 0x08010000), no symbols.
- Rebuilt (symbols):  `/home/tim/local/gwifi/ec-rebuild/ec/build/gale/RW/ec.RW.elf` (rebuilt 2026-06-05 15:38, newer than first review's artifacts — patches are in).
- Source:            `/home/tim/local/gwifi/ec-rebuild/ec/board/gale/` (usb_pd_config.h 15:37, usb_pd_policy.c 15:38, board.c 15:38 — all post-patch).
- Toolchains differ → instruction scheduling / registers / addresses / ~size-delta are NOT divergences. Judging SEMANTIC equivalence only.

Method: hand-disassembled each function in BOTH images with the gcc-5.4 objdump
(`-D -b binary -m arm -M force-thumb --adjust-vma=0x08010000` on the dump; `-d` on the ELF),
decoded the two switch jump tables byte-for-byte, and resolved every constant from
`ec/include/usb_pd.h`, `ec/include/usb_pd_tcpm.h`, `ec/chip/stm32/registers.h`.

## Constants resolved (from rebuilt source headers)
- TYPEC_CC_VOLT_SNK_DEF=5, SNK_1_5=6, SNK_3_0=7  → range test `(cc-5) u<= 2`.
- PD_DRP_TOGGLE_ON=0, TOGGLE_OFF=1, FORCE_SINK=2, FORCE_SOURCE=3 → `2 - locked` = locked?TOGGLE_OFF(1):FORCE_SINK(2).
- VDO_CMD_CCD_EN = VDO_CMD_VENDOR(14) = (10+14)&0x1f = 24.  PD_VDO_CMD(vdo)=vdo&0x1f.
- COMP_CSR: CMP1INSEL_VREF12=(1<<4)=0x10, CMP2INSEL_VREF12=(1<<20)=0x100000 → INSEL=0x00100010.
  CMP1INSEL_MASK=(7<<4), CMP2INSEL_MASK=(7<<20), CMP1EN=(1<<0), CMP2EN=(1<<16).
  clear-mask = ~(0x70|0x700000|1|0x10000) = 0xff8eff8e.  (INM4 would be (4<<4)|(4<<20)=0x00400040.)

================================================================================
## (A) The 4 patched functions — independently verified

### 1. pd_select_polarity  (inlined in tcpc_set_polarity)  — FIXED-MATCHES
DUMP tcpc_set_polarity @0x0801a4a0 ; ELF @0x0801a168.
COMP_CSR write is byte-equivalent in both:
  COMP_CSR(@0x4001001c) = (COMP_CSR & 0xff8eff8e) | 0x00100010 | (polarity ? CMP2EN(0x10000) : CMP1EN(1)).
- COMP_CSR address literal: DUMP 0x4001001c == ELF 0x4001001c. ✓
- clear mask: DUMP 0xff8eff8e == ELF 0xff8eff8e. ✓
- INSEL constant: DUMP 0x00100010 == ELF 0x00100010 (VREF1/2). ✓  **(was wrongly 0x00400040 INM4; now fixed)**
- enable polarity: both `polarity ? CMP2EN : CMP1EN`. ✓
RESULT: FIXED-MATCHES. The RX comparator inverting input is 1/2 VREFINT (~0.6V) as in the dump.

### 2. board_no_charger  — FIXED-MATCHES (instruction-for-instruction)
DUMP @0x08010260 ; ELF @0x080103a8. Both:
  push {r0,r1,r2,lr}; r0=0; r1=&cc1(sp); r2=&cc2(sp+4); bl tcpm_get_cc (DUMP 0x801b74a / ELF 0x801b220)
  r3=cc1; r3-=5; cmp #2; bls return    -> return if cc1 in {5,6,7}=SNK_DEF/1_5/3_0  ✓
  r3=cc2; r3-=5; cmp #2; bls return    -> same for cc2                                ✓
  bl system_is_locked (DUMP 0x8016584 / ELF 0x801629c)
  subs r3,r0,#1; sbcs r0,r3; movs r3,#2; subs r0,r3,r0   -> r0 = 2 - locked  (locked?1:2)  ✓
  bl pd_set_dual_role (DUMP 0x8013930 / ELF 0x8017b04)
RESULT: FIXED-MATCHES. Was previously `cc_mv>=200` + `pd_comm_enable(locked?0:1)` (wrong input AND wrong
function). Now uses CC *status* {SNK_DEF..SNK_3_0} and pd_set_dual_role(unlocked FORCE_SINK / locked TOGGLE_OFF).
The ELF target 0x8017b04 was independently disassembled and IS the genuine pd_set_dual_role body
(stores drp_state byte @0x20001d69; special-cases arg 2/1/3; calls set_state/tcpm_set_cc/pd_power_supply_reset/task_wake) — NOT pd_comm_enable.

### 3. pd_tx_enable  (inlined in pd_start_tx)  — FIXED-MATCHES
DUMP pd_start_tx @0x08013248 ; ELF @0x08013178. The shared SPI/TIM/DMA bring-up is unchanged
(literal pool identical: TIM16 base 0x40013000, 0x00000702, 0xffffc2c1, idiv 0x000927c0, GPIO_B 0x48000400).
The polarity-branched inline now matches the dump:
  r4 = 0x90<<23 = 0x48000000 (GPIO_A base) in both.
  polarity!=0 (CC2, PA6 TX / PA3 sense):
    gpio_set_alternate_function(GPIO_A=0x48000000, mask 0x40 (PA6), 0)   [both]
    MODER_A = (MODER_A & ~0xc0) | 0x40     -> PA3 (bits[7:6]) = output 0b01   [both: bics 0xc0; orr 0x40]
    gpio_set_level(idx 1 = USB_CC2_PD, 0)                                     [both]
  polarity==0 (CC1, PB4 TX / PA1 sense):
    gpio_set_alternate_function(GPIO_B=0x48000400, mask 0x10 (PB4), 0)   [both]
    MODER_A = (MODER_A & ~0x0c) | 0x04     -> PA1 (bits[3:2]) = output 0b01   [both: bics 0x0c; orr 0x04]
    gpio_set_level(idx 0 = USB_CC1_PD, 0)                                     [both]
RESULT: FIXED-MATCHES. Previously the reconstruction omitted the sense-pin force and instead re-asserted
the TX pin's alt MODER; now it forces the active CC's analog-sense pin (PA1/PA3) to GPIO output-low and
drives USB_CC{1,2}_PD low, exactly as the dump. Masks (0xc0/0x0c), output values (0x40/0x04), and
gpio_set_level indices (1/0) all match.

### 4. pd_custom_vdm  — FIXED-MATCHES (jump tables decoded byte-for-byte)
DUMP @0x08010720 ; ELF @0x08010758. Both: if cnt==0 return 0; cmd = payload[0]&0x1f;
switch dispatch `cmd-10` over range [0..14] (cmd 10..24), thumb1 case helper + byte table.

Jump-table decode (target = tablebase + 2*byte):
  cmd  | DUMP tbl@0x801073a            | ELF tbl@0x8010770
  10   | 0x08 -> 0x801074a VERSION     | 0x08 -> 0x8010780 VERSION
  11   | 0x11 -> 0x801075c SEND_INFO   | 0x10 -> 0x8010790 SEND_INFO
  12   | 0x11 -> 0x801075c READ_INFO   | 0x10 -> 0x8010790 READ_INFO
  13-20| 0x3a -> 0x80107ae default     | 0x39 -> 0x80107e2 default
  21   | 0x2c -> 0x8010792 CURRENT     | 0x2b -> 0x80107c6 CURRENT
  22-23| 0x3a -> 0x80107ae default     | 0x39 -> 0x80107e2 default
  24   | 0x32 -> 0x801079e CCD_EN      | 0x31 -> 0x80107d2 CCD_EN   <-- now present
Every command routes the same. The CCD_EN(24) handler is now present and identical:
  DUMP @0x801079e / ELF @0x80107d2:
    bl system_is_locked; subs r3,r0,#1; sbcs r0,r3; movs r3,#2; subs r0,r3,r0; bl pd_set_dual_role
  => pd_set_dual_role(locked ? TOGGLE_OFF(1) : FORCE_SINK(2)).  ✓
VERSION/INFO/CURRENT bodies match (format strings byte-equal in both images:
"version: %s\n", "DevId:%d.%d SW:%d RW:%d\n", "Current: %dmA\n"; info bit-field extraction equivalent).
RESULT: FIXED-MATCHES. Was previously a 12-entry table (range 10..21) that omitted CCD_EN; now 15-entry
(range 10..24) with CCD_EN -> pd_set_dual_role.

================================================================================
## (B) Regression check — surrounding PD code still matches (independently re-disassembled)

- pd_hw_init (DUMP @0x80134ec / ELF @0x08013430): gpio_config_module(MODULE_USB_PD=34,1);
  pd_set_pins_speed inline OSPEEDR_B |= 0x3c0 then |= 0x30000; APB2ENR |= 0x1000 (SPI1EN);
  TIM16/TIM1 setup; DMA prep. Same constants/order. MATCH.
- pd_set_pins_speed: 0x3c0 (PB3/PB4) and 0x30000 (PB8) — identical. MATCH.
- pd_tx_disable (inlined in tx_dma_done DUMP/ELF @0x08012ba0): MODER_B (PB4 bits[9:8]) -> 0x100;
  MODER_A (PA6 bits[13:12]) -> 0x1000. Both CC TX pins driven output-low. UNPERTURBED by the
  pd_tx_enable edit (separate inline). MATCH.
- pd_rx_enable_monitoring (ELF @0x0801313c): EXTI@0x40010414 = 0x600000; EXTI@0x40010400 |= 0x600000. MATCH.
- pd_rx_disable_monitoring (ELF @0x08013158): EXTI@0x40010400 &= 0xff9fffff (clear 21/22);
  EXTI@0x40010414 = 0x600000. MATCH.
- pd_snk_pdo[0]=0x2201912c, cnt=1; pd_src_pdo_cnt=0. Byte-identical to DUMP @0x801c53c. MATCH.
- pd_set_input_current_limit (ELF @0x08010714): cmp 5000(0x1388) && >2499(0x9c3) -> set_ap_power(1). MATCH.
- pd_check_* hooks: snk_is_vbus->1, board_checks->0, check_power_swap->0, check_data_swap->1,
  execute_data_swap/check_pr_role->no-op, check_dr_role->(flags&4 && dr_role==0)?pd_request_data_swap. MATCH.
- pd_set_dual_role body (ELF @0x08017b04): intact genuine body; the two patched callers correctly target it. MATCH.
No new divergence introduced by the patches.

================================================================================
## Remaining deltas (all IMMATERIAL)

1. cprintf channel index in pd_custom_vdm/pd debug prints: DUMP passes CC_USBPD=23, ELF passes 26.
   This is purely the console-channel enumerator value (depends on which optional CONSOLE_CHANNEL
   entries the build compiles in). It is the `chan` arg to cprintf — selects which console_channel_mask
   bit gates the debug line; does NOT change control flow, the action taken, or any hardware/register
   effect. Pervasive across the whole image (every cprintf), not introduced by these patches, default
   channel mask enables all channels. IMMATERIAL (build-configuration), per evaluation rules.
2. Build/version banner ("gale_v0.0.1-..." vs "gale_v1.1.5337-..."), addresses, register allocation,
   struct offsets, ~tens-of-bytes size delta. IMMATERIAL per spec.
3. command_cc 900mA lower bound (orig CC-status >=SNK_DEF i.e. cc_mv>=250 vs recon cc_mv>=200): this is
   a SEPARATE console-only diagnostic that was already IMMATERIAL in review #1 and is outside the 4
   patched functions; re-confirmed unchanged. Cosmetic 50mV band on the `gale cc` console line only.

================================================================================
## FINAL VERDICT

VERDICT: FUNCTIONALLY EQUIVALENT

All 4 previously-flagged MATERIAL USB-PD divergences are now semantically equivalent to the original
dump, verified by independent disassembly of both binaries (not by trusting source or prior claims).
No new divergence or regression was introduced; the surrounding PD PHY/policy code that review #1
verified as matching is still matching. The only remaining deltas are genuinely immaterial to
on-device behavior (console channel-index enumeration, build banner, addresses/registers/size).

### Per-patched-function table

| Patched function        | Result        | Evidence (DUMP addr / ELF addr; key constants)                                                                 |
|-------------------------|---------------|-----------------------------------------------------------------------------------------------------------------|
| pd_select_polarity      | FIXED-MATCHES | tcpc_set_polarity DUMP 0x0801a4a0 / ELF 0x0801a168; COMP_CSR@0x4001001c, clear 0xff8eff8e, INSEL 0x00100010 (VREF1/2), polarity?CMP2EN:CMP1EN — INM4 0x00400040 removed |
| board_no_charger        | FIXED-MATCHES | DUMP 0x08010260 / ELF 0x080103a8; tcpm_get_cc; return if cc∈{5,6,7}; pd_set_dual_role(2-locked) (ELF 0x8017b04) — no longer pd_comm_enable / cc_mv>=200 |
| pd_tx_enable            | FIXED-MATCHES | pd_start_tx DUMP 0x08013248 / ELF 0x08013178; pol!=0: PA6 alt + MODER_A&~0xc0|0x40 (PA3 out) + set_level(CC2_PD,0); pol==0: PB4 alt + MODER_A&~0x0c|0x04 (PA1 out) + set_level(CC1_PD,0) |
| pd_custom_vdm           | FIXED-MATCHES | DUMP 0x08010720 / ELF 0x08010758; 15-entry table range 10..24; cmd24 CCD_EN -> system_is_locked + pd_set_dual_role(locked?TOGGLE_OFF:FORCE_SINK) (DUMP 0x801079e / ELF 0x80107d2) |

### New divergences found: NONE.

### Remaining deltas classification:
- cprintf CC_USBPD channel index 23 vs 26 — IMMATERIAL (build console-channel enumeration; not a patch regression).
- build banner / addresses / regalloc / struct offsets / size — IMMATERIAL.
- command_cc 900mA bound [200,250)mV — IMMATERIAL (console-only; pre-existing, outside the 4 fixes).

VERDICT: FUNCTIONALLY EQUIVALENT
================================================================================
