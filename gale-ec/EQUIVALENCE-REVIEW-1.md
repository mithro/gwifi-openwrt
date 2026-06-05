# EC Firmware Equivalence Review — gale (Google Wifi) ChromiumOS EC

**Status: COMPLETE — VERDICT: NOT EQUIVALENT (material USB-PD divergences)**

Independent, adversarial review: is the reconstructed-from-source RW firmware
functionally equivalent to the original dumped RW firmware?

- Ground truth dump: `/home/tim/local/gwifi/tmp/work/gale-RW.bin` (load 0x08010000)
- Reconstruction ELF: `/home/tim/local/gwifi/tmp/ec/build/gale/RW/ec.RW.elf` (symbols)
- Reconstructed source: `/home/tim/local/gwifi/tmp/ec/board/gale/`

Toolchains differ → instruction-level diffs are EXPECTED, not divergences.
Judging SEMANTIC equivalence only.

## Tooling note
- radare2 not installed. Using the gcc-5.4 `objdump` on the raw dump via
  `-D -b binary -m arm -M force-thumb --adjust-vma=0x08010000` and on the
  symbolized rebuilt ELF directly. Prior analysis scripts in work/ (parse_all.py)
  located the structures; I re-ran and independently verified the logic-bearing
  functions by hand-disassembling BOTH images.

## Running findings

### Tables (parse_all.py, re-run + spot-verified)
- gpio_list[]: 29 records, name/port/mask/flags **IDENTICAL** (DUMP @0x801c0d0, ELF @0x801bb90).
- ALTERNATE funcs: 7 records **IDENTICAL** (incl SPI_FLASH pull-down flag 0x4).
- pd_snk_pdo[0]=0x2201912c (5V/3A DUAL_ROLE|DATA_SWAP), cnt=1; pd_src_pdo_cnt=0. **MATCH** (DUMP @0x801c53c, prev word=1, next=0).
- adc_channels[]: CC1(3300/4096/AIN1) CC2(.. AIN3) VBUS(6600/4096/AIN8) CUR(6600/4096/AIN9). **IDENTICAL**.
- i2c_ports[]: {"slave",port0,100kbps,scl=GPIO25,sda=GPIO26}. ELF=('slave',0,100,25,26); DUMP record confirmed (the script's "NOT FOUND" was a string-search artifact — 'slave' string IS present, see below). gpio_list indices 25/26 = SLAVE_I2C_SCL(PB6)/SDA(PB7). **MATCH**.
- spi_devices[0]: {port0, div0, gpio_cs=GPIO19=SPI_FLASH_NSS}, used=1. **IDENTICAL** (DUMP @0x801bf90).
- USB device descriptor: VID=0x18d1 PID=0x500f class/sub/proto=0 maxpkt=64 bcdUSB=0x0200. **IDENTICAL**.
- usb_strings: [DESC, "Google Inc.", "Gale debug", VERSION, "EC_PD", "AP"]. **IDENTICAL** (only VERSION banner differs: dump "gale_v1.1.5337-0115719" vs rebuild "gale_v0.0.1-7c97ab0" — IMMATERIAL per spec).
- usb_muxes / board_ss_mux_driver vtable {init,set,get}: present in both; DUMP vtable @0x801bf80, port_addr=0, board_init=0. **MATCH** (logic verified below).
- command "gale" descriptor: name/handler/argdesc/help strings **IDENTICAL** (DUMP @0x801baa4).
- gale_subcommands[6]: order power,polarity,cc,vbus,dev,rec **IDENTICAL** in both.

### CRITICAL: set_ap_power_on / set_ap_power_off — VERIFIED IDENTICAL
Hand-disassembled both. gpio_set_level enum order:
- ON  (DUMP 0x80101c0 / ELF set_ap_power_on): cputs("power on ap"), then SET=1 in order
  **14 SYS_PWR_EN, 9 VDD_3P3_EN, 10 VDD_3P3_2G_EN, 13 VDD_1P8_EN, 11 VDD_1P35_EN, 12 VDD_1P1_CPU_EN**, ap_is_on=1.
- OFF (DUMP 0x801020c / ELF set_ap_power_off): cputs("power off ap"), then CLR=0 in order
  **17 MCU_INT_L, 12 VDD_1P1_CPU_EN, 11 VDD_1P35_EN, 13 VDD_1P8_EN, 10 VDD_3P3_2G_EN, 9 VDD_3P3_EN, 14 SYS_PWR_EN**, ap_is_on=0.
- Same rails, same order, no inter-rail delays in either. ccputs channel arg r0=0 (CC_COMMAND) in both. **MATCH.**
- set_ap_power(on): deferred dispatch on/off — both via hook_call_deferred(...,0). (verify dispatch wrapper next)

### usb_spi_board_enable / usb_spi_board_disable — VERIFIED IDENTICAL
DUMP enable @0x80105e4, disable @0x8010674; ELF enable @0x80105b8, disable @0x8010660.
Both ENABLE do, in order:
  VDD_1P35_EN=0; VDD_1P8_EN=0;
  if(!gpio_get(SYS_PWR_EN)){ SYS_PWR_EN=1; VDD_3P3_EN=1; usleep(25);} 
  else { while(!gpio_get(VDD_3P3_EN)){ SYS_PWR_EN=1; VDD_3P3_EN=1; usleep(25);} }
  gpio_config_module(MODULE_SPI_FLASH,1); gpio_set_flags(SPI_FLASH_NSS,0xa0=OUT_HIGH);
  OSPEEDR_B(0x48000408)|=0xff000000; APB1ENR(0x4002101c)|=0x4000(SPI2EN);
  APB1RSTR(0x40021010)|=0x4000 then &=~0x4000; spi_enable(0,1).
  (Codegen nit: DUMP shares the bring-up basic block between if/else; ELF duplicates it — same effect.)
Both DISABLE: APB1ENR&=~0x4000; gpio_config_module(MODULE_SPI_FLASH,0);
  gpio_set_flags(SPI_FLASH_NSS,0x10=INPUT); spi_enable(0,0). **MATCH.**

### board_config_pre_init — VERIFIED IDENTICAL
DUMP @0x80106a2, ELF @0x80106d4: APB2ENR(0x40021018)|=1 (SYSCFG clk);
SYSCFG_CFGR1(0x40010000)|=(1<<24) (SPI2 RX/TX DMA remap); return. **MATCH.**

### Small PD policy fns (ELF, by symbol; cross-checked to source)
- pd_is_valid_input_voltage: return (mv==5000). **MATCH.**
- pd_transition_voltage: bare bx lr (no-op). **MATCH.**
- pd_set_power_supply_ready: return 0. **MATCH.**

### PD policy cluster — verified DUMP vs ELF
DUMP @0x80106dc / ELF @0x0801070c **pd_set_input_current_limit**:
  if(supply_voltage==5000 && max_ma>2499) set_ap_power(1). Same constants. **MATCH.**
- pd_snk_is_vbus_provided=1, pd_board_checks=0, pd_check_power_swap=0,
  pd_check_data_swap=1, pd_execute_data_swap/pd_check_pr_role=no-op. **MATCH** (both images).
- pd_check_dr_role: if((flags&PD_FLAGS_PARTNER_DR_DATA bit2) && dr_role==PD_ROLE_UFP(0)) pd_request_data_swap. **MATCH** (both images).

### *** DIVERGENCE: pd_custom_vdm — DUMP handles VDO_CMD_CCD_EN, reconstruction does NOT ***
VDO_CMD_VENDOR(x) = (10+x)&0x1f. Resolved both switch jump tables (DUMP @0x8010720, ELF @0x08010750):
  cmd 10 VDO_CMD_VERSION   -> both: zero last word, cprintf "version: %s"      MATCH
  cmd 11 VDO_CMD_SEND_INFO -> both: info handler                                MATCH
  cmd 12 VDO_CMD_READ_INFO -> both: info handler (cnt==7 cprintf / cnt==6 store)MATCH
  cmd 21 VDO_CMD_CURRENT   -> both: cprintf "Current: %dmA"                     MATCH
  cmd 24 VDO_CMD_CCD_EN    -> DUMP: system_is_locked(); pd_comm_enable(locked?2:1)
                              ELF : *** falls through to default (return 0, NO action) ***
DUMP switch range is 10..24 (15-entry table); ELF range is 10..21 (12-entry table)
precisely because the reconstruction omits the CCD_EN case.
DUMP handler D @0x801079e: bl system_is_locked(0x8016584); r0 = 2 - !locked;
  bl pd_comm_enable(0x8013930) [confirmed: stores to pd_comm_enabled @0x20001ef8].
=> On the original device, a partner sending the Chrome-OS "CCD enable" vendor VDM
   toggles PD-comms debug accessory mode; on the reconstruction it is silently ignored.
   CLASSIFICATION: candidate MATERIAL (behavioral divergence on a real PD message),
   though only reachable via a Google-proprietary debug VDM. Re-assessed in verdict.
   CORRECTION (see below): 0x8013930 is pd_set_dual_role, NOT pd_comm_enable.
   So original CCD_EN does pd_set_dual_role(unlocked?FORCE_SINK:TOGGLE_OFF).

### *** MATERIAL DIVERGENCE: board_no_charger calls the WRONG function ***
Identified DUMP board_no_charger @0x8010260 (it is the routine pointed to by the
HOOK_INIT deferred descriptor board_no_charger_data @0x801be24, whose routine word
= 0x08010261; board_init @0x801044c schedules it via hook_call_deferred(...,SECOND)).

DUMP board_no_charger logic:
  tcpm_get_cc(0, &cc1, &cc2);                  // bl 0x801b74a (TCPM stub get_cc)
  if ((cc1-5) <= 2u) return;                   // cc1 status in {SNK_DEF,SNK_1_5,SNK_3_0} -> charger present
  if ((cc2-5) <= 2u) return;
  pd_set_dual_role(2 - system_is_locked());    // bl 0x8013930
       // unlocked -> pd_set_dual_role(PD_DRP_FORCE_SINK=2)
       // locked   -> pd_set_dual_role(PD_DRP_TOGGLE_OFF=1)

PROOF 0x8013930 == pd_set_dual_role (NOT pd_comm_enable):
  - stores arg to byte drp_state @0x20001ef8; special-cases arg==2 (PD_DRP_FORCE_SINK)
    and arg==0; conditionally calls set_state/tcpm_set_cc/pd_power_supply_reset/task_wake.
    Matches common/usb_pd_protocol.c pd_set_dual_role() body exactly.
  - (The ELF's real pd_comm_enable is a DIFFERENT function @0x8017d04: it stores to
    pd_comm_enabled @0x20001d68 and calls tcpm_set_rx_enable — unrelated.)

RECONSTRUCTION board_no_charger @0x80104e8 logic:
  if (cc1_mv >= 200 || cc2_mv >= 200) return;  // ADC voltage, not CC status
  pd_comm_enable(system_is_locked() ? 0 : 1);  // bl 0x8017d04  *** WRONG FUNCTION ***

Two distinct divergences here:
  (A) Decision input: original uses CC *status* {5,6,7} (== cc_volt >= PD_SNK_VA=250
      via cc_voltage_to_status in usb_pd_tcpc.c); reconstruction uses cc_mv >= 200.
      Differs only in the [200,250)mV band -> minor.
  (B) ACTION: original calls **pd_set_dual_role** (sets DRP power-role policy:
      FORCE_SINK when unlocked / TOGGLE_OFF when locked, driving the Type-C state
      machine + CC pull). Reconstruction calls **pd_comm_enable** (enable/disable BMC
      PD messaging). These are different subsystems with different on-wire/SM effects.
  (B) is a genuine behavioral divergence => **MATERIAL**.
  Note: the source explicitly flags this body "[APPROXIMATED]" — the approximation is
  functionally wrong (wrong function + locked-case logic flips: orig always sets a DRP
  state, recon disables PD comm when locked).

### command_cc / print_cc_current — minor threshold delta (diagnostic only)
DUMP command_cc @0x8010498: reads tcpm_get_cc(0,&cc1,&cc2) (CC *status* enum) AND
  adc_read_channel(0/1) for the mV display; selects advertised current by status:
  7(SNK_3_0)->3000, 6(SNK_1_5)->1500, 5(SNK_DEF)->900, else nothing.
RECON command_cc @0x08010498 + print_cc_current @0x0801045c: selects by ADC mV:
  cc_mv>=1230->3000, >=660->1500, >=200->900, else nothing.
cc_voltage_to_status() (common/usb_pd_tcpc.c) maps >=1230->SNK_3_0, >=660->SNK_1_5,
  >=PD_SNK_VA(250)->SNK_DEF. So 3000/1500 (1230/660) MATCH exactly; the 900mA lower
  bound differs: orig >=250 vs recon >=200, i.e. only for cc_mv in [200,250).
  This is the `gale cc` CONSOLE line only -> **IMMATERIAL** (cosmetic, 50mV band).

### set_ap_power wrapper — VERIFIED IDENTICAL
DUMP @0x8010568 / ELF @0x08010540: on->hook_call_deferred(set_ap_power_on_data,0);
off->hook_call_deferred(set_ap_power_off_data,0). Deferred routines confirmed
(board_no_charger 0x8010260, on 0x80101c0, off 0x801020c). **MATCH.**

### command_power/polarity/dev/rec/vbus + command_gale dispatch — VERIFIED IDENTICAL
- command_rec  (DUMP 0x801030c / ELF 0x8010270): !locked&&argc>1; parse_bool;
  gpio_set_flags(ENTERING_REC=16, v?OUT_LOW(0x60):INPUT(0x10)); "rec switch is %s". MATCH.
- command_dev  (DUMP 0x8010370 / ELF 0x80102d0): same, ENTERING_DEV=18. MATCH.
- command_polarity (DUMP 0x80103fc / ELF 0x8010358): strtoi; gpio_set_level(USB_CC_POLARITY=4,!!v); "%8s - %d". MATCH.
- command_vbus (DUMP 0x80103d4 / ELF 0x8010330): adc_read_channel(ADC_VBUS=2),(ADC_IN_CURRENT_SENSE=3). MATCH.
  (0x8010990 == adc_read_channel; original cc/vbus call it directly = pd_adc_read inlined.)
- command_gale (DUMP 0x8010290 / ELF 0x80103f0): argc<2 -> all 6 handlers(1,&name);
  else strncasecmp(argv[1],name,strlen(name)) dispatch; default EC_ERROR_PARAM1(11).
  Order power,polarity,cc,vbus,dev,rec in both. MATCH (DUMP copies const table to stack; codegen-only).
- command_power (DUMP 0x8010584 / ELF 0x0801055c): verified below.

### board_init — VERIFIED EQUIVALENT
DUMP @0x801044c / ELF @0x080103a8: 2x queue_init + usart_init(&ap_usart);
if(system_is_locked()) ap_usb.state->rx_disabled=1; else hook_call_deferred(board_no_charger_data, SECOND). Same calls + branch. (struct offsets differ; immaterial.) MATCH.

### SS mux (board_ss_mux set/get/init) — VERIFIED IDENTICAL
DUMP set 0x8010190 / get 0x801017c / init 0x80101b0 ; ELF set 0x801021c / get 0x801024a / init 0x801023c.
- set: gpio_set_level(USB_CC_POLARITY=4,(mux&MUX_POLARITY_INVERTED)?0:1);
       gpio_set_level(USB_SS_MUX_EN_L=5,(mux&MUX_USB_ENABLED)?0:1).
- get: *mux = gpio_get_level(EN_L)?0:MUX_USB_ENABLED.
- init: gpio_set_level(EN_L,1). **MATCH.**

### PD PHY (usb_pd_config.h inlines) — mostly MATCH; one real deviation in pd_tx_enable
Verified board-defining PHY facts identical in BOTH images:
- TX on SPI1; CC1 = PB4 (gpio_set_alternate_function mask 0x10), CC2 = PA6 (mask 0x40),
  selected by plug polarity (polarity!=0 -> PA6/CC2, ==0 -> PB4/CC1). Same in DUMP & ELF.
- gpio_set_alternate_function (shared chip code, DUMP 0x8011464 / ELF 0x80115d0) is byte-
  identical in logic and DOES set MODER to alt(0b10) for the masked pin. So the active CC
  line is correctly driven by SPI1 in alt mode in BOTH builds. (load-bearing PD TX behavior MATCHES)
- pd_rx_enable/disable_monitoring (EXTI bits 21/22 = 0x600000, EXTI@0x40010400/0x40010414) MATCH.
- pd_tx_disable: drives PB4 & PA6 MODER to output(01) in both (tx_dma_done inlines it). MATCH.

DEVIATION — extra pin handling in pd_tx_enable (DUMP pd_start_tx @0x8013248 vs ELF @0x8013158):
  ORIGINAL, after routing SPI1 to the active CC pin, ALSO forces that CC's *analog sense*
  pin to GPIO output-low:
    polarity=1: MODER_A=(MODER_A&~(3<<2... bits6,7=PA3))|0x40; gpio_set_level(USB_CC2_PD/idx1, 0)
    polarity=0: MODER_A=(MODER_A&~(bits2,3=PA1))|0x04;        gpio_set_level(USB_CC1_PD/idx0, 0)
    (PA1=USB_CC1_PD/AIN1, PA3=USB_CC2_PD/AIN3 — the CC ADC sense pins.)
  RECONSTRUCTION pd_tx_enable does NOT touch the sense pins; instead it adds a (redundant,
  harmless) re-assert of the TX pin's alt mode: MODER|=(2<<12) PA6 / (2<<8) PB4.
  Confirmed by two independent objdumps (aligned + pre-generated RW-dump.asm) — not a decode artifact.
  EFFECT: original momentarily reconfigures the active CC's sense pin (analog->output-low)
  for the duration of a PD transmit; reconstruction leaves it analog. The actual BMC TX
  signalling on the CC line is identical. Materiality: affects the discrete PHY's CC-sense
  pin state during TX (could matter for the internal RX comparator / ADC during half-duplex),
  but does not change which line is driven or the transmitted waveform.
  CLASSIFICATION: real board-PHY divergence -> conservatively MATERIAL (alters GPIO/register
  effects during PD TX), though plausibly benign on-wire. Not present in reconstruction.

### *** MATERIAL DIVERGENCE: PD RX comparator reference (pd_select_polarity) ***
tcpc_set_polarity (shared code) inlines the board macro pd_select_polarity.
COMP_CSR write (DUMP @0x801a4a0 / ELF @0x801a144):
  COMP_CSR = (COMP_CSR & 0xff8eff8e) | <INSEL> | (polarity ? CMP2EN(1<<16) : CMP1EN(1));
  - clear mask 0xff8eff8e  -> SAME in both (clears CMP1/2 INSEL fields + CMP1/2 EN)
  - EN selection polarity?CMP2:CMP1 -> SAME in both
  - <INSEL> constant:  DUMP = 0x00100010   vs   ELF = 0x00400040   *** DIFFERENT ***
    DUMP  0x00100010 = (1<<4)|(1<<20)  = CMP1INSEL_VREF12 | CMP2INSEL_VREF12  (1/2 VREFINT ~0.6V)
    ELF   0x00400040 = (4<<4)|(4<<20)  = CMP1INSEL_INM4   | CMP2INSEL_INM4    (INM4 external input)
=> The ORIGINAL gale sets the CC RX comparator inverting input to VREF1/2 (~0.6V internal ref);
   the RECONSTRUCTION sets it to INM4 (external pin). This is the threshold the discrete PD PHY
   uses to slice the incoming BMC waveform on the CC line.
   ROOT CAUSE: usb_pd_config.h was reconstructed from twinkie, which uses INM4; gale actually
   used VREF12. (board/twinkie/usb_pd_config.h line 125 == the INM4 the reconstruction copied.)
   CLASSIFICATION: **MATERIAL** — wrong comparator reference directly affects PD message
   reception; on hardware this can degrade or break PD RX (BMC decode).

### pd_hw_init pin speeds / SPI1 clock — VERIFIED IDENTICAL
DUMP @0x80134ec / ELF @0x0801340c:
- gpio_config_module(MODULE_USB_PD=34,1); OSPEEDR_B|=0x3c0 (PB3/PB4 hi-speed) |=0x30000 (PB8);
  APB2ENR|=0x1000 (SPI1EN). Same constants. TX timer TIM16 / RX TIM1 (shared chip code via macros). **MATCH.**

### Task list + stack sizes — VERIFIED IDENTICAL
DUMP table @0x801dfdc / ELF tasks_init @0x0801dca8: 5 entries (IDLE + 4) identical order &
stacks: IDLE=256, HOOKS=640, HOSTCMD=488, CONSOLE=488, PD_C0=640. Task name strings
HOOKS/HOSTCMD/CONSOLE/PD_C0 consecutive in both; no other named tasks. **MATCH.**

================================================================================
## FINAL VERDICT

**Status: COMPLETE**

VERDICT: NOT EQUIVALENT

The reconstruction is a very faithful match across the vast majority of the board
layer (GPIO table, alt-funcs, tasks+stacks, USB descriptors/strings, all console
commands incl. the critical set_ap_power rail order, raiden usb_spi bridge, I2C/ADC/
SPI/SS-mux tables, PDOs, most PD policy hooks, board_init, board_config_pre_init,
pin speeds/SPI1 clock). However it contains **multiple genuine behavioral divergences
in the USB-PD layer** — at least one of which (the RX comparator reference) would
plausibly break PD message reception on real gale hardware — so it is NOT functionally
equivalent to the dump.

### Per-area findings table

| Area | Result | Evidence / classification |
|------|--------|---------------------------|
| gpio_list[] (29 sigs) + ALTERNATE (7) | MATCH | byte-identical name/port/mask/flags; DUMP@0x801c0d0/0x801cbec |
| Task list + order + stack sizes | MATCH | IDLE/HOOKS640/HOSTCMD488/CONSOLE488/PD_C0640 identical; DUMP@0x801dfdc |
| set_ap_power_on/off (rail order+delays) | MATCH | ON 14,9,10,13,11,12 / OFF 17,12,11,13,10,9,14; no delays; DUMP 0x80101c0/0x801020c |
| set_ap_power wrapper (deferred dispatch) | MATCH | on/off->hook_call_deferred(...,0); DUMP 0x8010568 |
| command_gale + subcmd dispatch/order | MATCH | power,polarity,cc,vbus,dev,rec; strncasecmp; default PARAM1 |
| command_power/polarity/dev/rec/vbus | MATCH | gates, gpio idx/flags, adc channels all identical |
| command_cc current-band thresholds | DIVERGENCE — IMMATERIAL | 3000/1500 match (1230/660); 900mA bound orig>=250(VREF status) vs recon>=200; console-only, [200,250)mV |
| board_init / board_config_pre_init | MATCH | 2x queue_init+usart_init+locked branch; SYSCFG clk + SPI2 DMA remap |
| usb_spi bridge enable/disable + spi_devices[] | MATCH | identical rail seq, OSPEEDR/RCC/reset, cs gpio; DUMP 0x80105e4/0x8010674 |
| i2c_ports[] / adc_channels[] / usb_strings[] / VID:PID | MATCH | slave@0/100k scl25 sda26; CC1/CC2/VBUS/CUR; 0x18d1:0x500f; only version banner differs (IMMATERIAL) |
| SS-mux board_set/get/init | MATCH | polarity+EN_L logic identical; DUMP 0x8010190/0x801017c/0x80101b0 |
| pd_snk_pdo/pd_src_pdo (+counts) | MATCH | snk=0x2201912c(5V/3A DRP+DATA_SWAP) cnt1; src cnt0 |
| pd_set_input_current_limit | MATCH | ==5000 && >2499 -> set_ap_power(1); DUMP 0x80106dc |
| pd_check_power_swap/data_swap/dr_role/pr_role, pd_*_supply, pd_snk_is_vbus | MATCH | constants/no-ops identical (both images) |
| pd PHY: pin routing PA6/PB4, pin speeds, SPI1, TIM16/TIM1, EXTI, tx_disable | MATCH | gpio_set_alternate_function sets alt; OSPEEDR 0x3c0/0x30000; DUMP pd_hw_init 0x80134ec |
| **pd_custom_vdm VDO_CMD_CCD_EN(24)** | **DIVERGENCE — MATERIAL (niche)** | DUMP handles it (pd_set_dual_role); recon switch omits case -> ignored |
| **board_no_charger action** | **DIVERGENCE — MATERIAL** | DUMP calls **pd_set_dual_role**(FORCE_SINK/TOGGLE_OFF); recon calls **pd_comm_enable**(0/1) — wrong subsystem |
| **board_no_charger decision input** | DIVERGENCE — minor | DUMP uses CC status>=SNK_DEF(volt>=250); recon uses cc_mv>=200 ([200,250) band) |
| **pd_tx_enable sense-pin drive** | **DIVERGENCE — MATERIAL** | DUMP drives active CC's ADC pin (PA1/PA3) output-low during TX; recon does not |
| **pd_select_polarity comparator ref (INSEL)** | **DIVERGENCE — MATERIAL** | DUMP COMP INSEL=VREF12(0x00100010 ~0.6V) vs recon INM4(0x00400040 ext pin); breaks PD RX slicing |
| build banner / total size (~44 B) / addresses / reg-alloc / struct offsets | MATCH (immaterial) | per evaluation rules |

### Material divergences (summary)
1. pd_select_polarity: RX comparator inverting input VREF1/2 (orig) vs INM4 (recon).
   Highest-impact: directly sets the threshold for decoding received PD/BMC on CC. Root
   cause = usb_pd_config.h copied from board/twinkie (INM4) instead of gale's VREF12.
2. board_no_charger: original drives DRP policy via pd_set_dual_role; reconstruction calls
   pd_comm_enable — a different function/subsystem. Changes the 1-second-post-boot
   standalone behavior when no charger is present.
3. pd_tx_enable: original forces the active CC line's analog-sense pin to output-low for the
   duration of a PD transmit; reconstruction leaves it analog.
4. pd_custom_vdm: original responds to VDO_CMD_CCD_EN (debug "CCD enable") by calling
   pd_set_dual_role; reconstruction silently ignores it.

These are all in the **board layer** (board/gale/{board.c, usb_pd_config.h}) — exactly where
reconstruction risk lives — and the source even flags board_no_charger / command_cc as
"[APPROXIMATED]". Because #1 (and arguably #3) change real USB-PD signalling/decoding on
hardware, the recompiled firmware is NOT guaranteed to behave indistinguishably from the dump.

VERDICT: NOT EQUIVALENT
================================================================================
