# Uncovered branches by function — named + caused (captured gale EC firmware)

## Methodology & confidence
- **Branch cause** — the `cmp/tst/...` condition, the compared register/immediate, and exactly which direction is missing — is derived **directly from the captured disassembly (always exact)**. The operand **provenance** hint (`= word [r5+0x54]`, `= computed (subs #4)`, etc.) is the nearest **in-basic-block** definition, found by a control-flow-aware backward walk that stops at unconditional flow breaks; values defined further upstream are reported as *"carried in from a preceding basic block"* rather than guessed.
- **Function name / signature / source line** come from the **rebuilt ELF's DWARF** (vendored in-repo at `renode/data/rebuilt-RO.elf`), mapped to captured addresses by a disassembly fingerprint (instruction count + cmp-immediate multiset + **loaded scalar-constant multiset**, which is shift-invariant) within an anchor-interpolated window, then `addr2line`.
- **conf:exact / conf:high** — fingerprint distance 0 / ≤3: name+source reliable. **conf:approx** — best-effort match; the *name* may occasionally be wrong (the rebuilt has no 1:1 counterpart, or a fingerprint collision), but the disassembly **cause is still exact**.
- The per-branch **rebuilt C line** is `addr2line(reb_func_start + branch_offset)`; reliable when the internal layout matches (it does for faithful reconstructions), best-effort for conf:approx.
- RO functions shown (0x0800xxxx); each function notes how many of its uncovered branches are in the **RW mirror** (0x0801xxxx, identical code).

**1072 uncovered branches across 191 functions.**

## 0x08000260  `board_no_charger`  (conf:exact)
**Signature:** `static void board_no_charger(void);`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/board.c:452  | rebuilt @ 0x8000398 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x0801027a** (RW mirror) [nottaken-only] — `cmp r3, #2` then `bls`: taken when r3 <=u constant 2. r3 = computed (subs #5). MISSING direction (nottaken-only) needs r3 <=u constant 2.
  - rebuilt C (board.c:463): `if (cc2 >= TYPEC_CC_VOLT_SNK_DEF && cc2 <= TYPEC_CC_VOLT_SNK_3_0)`
  - **What:** an `if` test — `if (cc2 >= TYPEC_CC_VOLT_SNK_DEF && cc2 <= TYPEC_CC_VOLT_SNK_3_0)`. When the condition holds it runs `return;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800030c  `command_rec`  (conf:approx)
**Signature:** `static int command_rec(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/board.c:394  | rebuilt @ 0x8000260 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800034a** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0x10). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (board.c:404): `ccprintf("rec switch is %s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("rec switch is %s\n",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801034a** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0x10). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (board.c:404): `ccprintf("rec switch is %s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("rec switch is %s\n",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000370  `command_dev`  (conf:approx)
**Signature:** `static int command_dev(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/board.c:378  | rebuilt @ 0x80002c0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080003ae** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0x12). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (board.c:388): `ccprintf("dev switch is %s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("dev switch is %s\n",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080103ae** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0x12). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (board.c:388): `ccprintf("dev switch is %s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("dev switch is %s\n",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800044c  `board_init`  (conf:approx)
**Signature:** `static void board_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/board.c:291  | rebuilt @ 0x80003c8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800046e** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds #4). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (board.c:304): `if (system_is_locked())`
  - **What:** an `if` test — `if (system_is_locked())`. When the condition holds it runs `ap_usb.state->rx_disabled = 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801046e** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds #4). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (board.c:304): `if (system_is_locked())`
  - **What:** an `if` test — `if (system_is_locked())`. When the condition holds it runs `ap_usb.state->rx_disabled = 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08000498  `pd_custom_vdm`  (conf:approx)
**Signature:** `int pd_custom_vdm(int port, int cnt, uint32_t *payload, uint32_t **rpayload)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/usb_pd_policy.c:136  | rebuilt @ 0x8000728 | 4 uncovered (0 unreached, 4 one-dir; 4 in RW mirror)

- **0x080104c6** (RW mirror) [nottaken-only] — `cmp r3, #7` then `beq`: taken when r3 == constant 7. r3 = word [sp+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 7.
  - rebuilt C (usb_pd_policy.c:148): `*(payload + cnt - 1) = 0;`
  - **What:** a conditional derived from this statement — `*(payload + cnt - 1) = 0;`. When the condition holds it runs `CPRINTF("version: %s\n", (char *)(payload+1));`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080104de** (RW mirror) [nottaken-only] — `cmp r3, #7` then `beq`: taken when r3 == constant 7. r3 = word [sp+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 7.
  - rebuilt C (usb_pd_policy.c:158): `CPRINTF("DevId:%d.%d SW:%d RW:%d\n",`
  - **What:** a conditional derived from this statement — `CPRINTF("DevId:%d.%d SW:%d RW:%d\n",`. When the condition holds it runs `HW_DEV_ID_MAJ(dev_id),`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080104e2** (RW mirror) [nottaken-only] — `cmp r3, #6` then `beq`: taken when r3 == constant 6. r3 = word [sp+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 6.
  - rebuilt C (usb_pd_policy.c:158): `CPRINTF("DevId:%d.%d SW:%d RW:%d\n",`
  - **What:** a conditional derived from this statement — `CPRINTF("DevId:%d.%d SW:%d RW:%d\n",`. When the condition holds it runs `HW_DEV_ID_MAJ(dev_id),`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080104e6** (RW mirror) [taken-only] — `cmp r3, #5` then `bne`: taken when r3 != constant 5. r3 = word [sp+4] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 5.
  - rebuilt C (usb_pd_policy.c:158): `CPRINTF("DevId:%d.%d SW:%d RW:%d\n",`
  - **What:** a conditional derived from this statement — `CPRINTF("DevId:%d.%d SW:%d RW:%d\n",`. When the condition holds it runs `HW_DEV_ID_MAJ(dev_id),`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080005e4  `usb_spi_board_enable`  (conf:approx)
**Signature:** `void usb_spi_board_enable(struct usb_spi_config const *config)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/board.c:146  | rebuilt @ 0x80005b0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080005fe** [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0xe). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (board.c:154): `if (!gpio_get_level(GPIO_SYS_PWR_EN)) {`
  - **What:** an `if` test — `if (!gpio_get_level(GPIO_SYS_PWR_EN)) {`. When the condition holds it runs `gpio_set_level(GPIO_SYS_PWR_EN, 1);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080105fe** (RW mirror) [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0xe). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (board.c:154): `if (!gpio_get_level(GPIO_SYS_PWR_EN)) {`
  - **What:** an `if` test — `if (!gpio_get_level(GPIO_SYS_PWR_EN)) {`. When the condition holds it runs `gpio_set_level(GPIO_SYS_PWR_EN, 1);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08000710  `pd_check_dr_role`  (conf:high)
**Signature:** `void pd_check_dr_role(int port, int dr_role, int flags)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/usb_pd_policy.c:121  | rebuilt @ 0x8000716 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08000718** [nottaken-only] — `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = function argument r1. MISSING direction (nottaken-only) needs r1 != constant 0.
  - rebuilt C (usb_pd_policy.c:123 (discriminator 1)): `if ((flags & PD_FLAGS_PARTNER_DR_DATA) && dr_role == PD_ROLE_UFP)`
  - **What:** an `if` test — `if ((flags & PD_FLAGS_PARTNER_DR_DATA) && dr_role == PD_ROLE_UFP)`. When the condition holds it runs `pd_request_data_swap(port);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010718** (RW mirror) [nottaken-only] — `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = function argument r1. MISSING direction (nottaken-only) needs r1 != constant 0.
  - rebuilt C (usb_pd_policy.c:123 (discriminator 1)): `if ((flags & PD_FLAGS_PARTNER_DR_DATA) && dr_role == PD_ROLE_UFP)`
  - **What:** an `if` test — `if ((flags & PD_FLAGS_PARTNER_DR_DATA) && dr_role == PD_ROLE_UFP)`. When the condition holds it runs `pd_request_data_swap(port);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000720  `pd_custom_vdm`  (conf:approx)
**Signature:** `int pd_custom_vdm(int port, int cnt, uint32_t *payload, uint32_t **rpayload)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/board/gale/usb_pd_policy.c:136  | rebuilt @ 0x8000728 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x0800075e** [taken-only] — `cmp r1, #7` then `bne`: taken when r1 != constant 7. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant 7.
  - rebuilt C (usb_pd_policy.c:155): `dev_id = VDO_INFO_HW_DEV_ID(payload[6]);`
  - **What:** a conditional derived from this statement — `dev_id = VDO_INFO_HW_DEV_ID(payload[6]);`. When the condition holds it runs `is_rw = VDO_INFO_IS_RW(payload[6]);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08000782** [taken-only] — `cmp r1, #6` then `bne`: taken when r1 != constant 6. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant 6.
  - rebuilt C (usb_pd_policy.c:165): `pd_dev_store_rw_hash(port, dev_id, payload + 1,`
  - **What:** a conditional derived from this statement — `pd_dev_store_rw_hash(port, dev_id, payload + 1,`. When the condition holds it runs `SYSTEM_IMAGE_UNKNOWN);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801075e** (RW mirror) [taken-only] — `cmp r1, #7` then `bne`: taken when r1 != constant 7. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant 7.
  - rebuilt C (usb_pd_policy.c:155): `dev_id = VDO_INFO_HW_DEV_ID(payload[6]);`
  - **What:** a conditional derived from this statement — `dev_id = VDO_INFO_HW_DEV_ID(payload[6]);`. When the condition holds it runs `is_rw = VDO_INFO_IS_RW(payload[6]);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08010782** (RW mirror) [taken-only] — `cmp r1, #6` then `bne`: taken when r1 != constant 6. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant 6.
  - rebuilt C (usb_pd_policy.c:165): `pd_dev_store_rw_hash(port, dev_id, payload + 1,`
  - **What:** a conditional derived from this statement — `pd_dev_store_rw_hash(port, dev_id, payload + 1,`. When the condition holds it runs `SYSTEM_IMAGE_UNKNOWN);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080007c4  `clock_wait_bus_cycles`  (conf:approx)
**Signature:** `void clock_wait_bus_cycles(enum bus_type bus, uint32_t cycles)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/clock-stm32f0.c:479  | rebuilt @ 0x80009e4 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x080007e4** [nottaken-only] — `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:489): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `void clock_enable_module(enum module_id module, int enable)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080007fe** [nottaken-only] — `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:85): `STM32_RTC_WPR = 0x53;`
  - **What:** a conditional derived from this statement — `STM32_RTC_WPR = 0x53;`. When the condition holds it runs `static inline uint32_t rtc_to_sec(uint32_t rtc)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080107e4** (RW mirror) [nottaken-only] — `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:489): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `void clock_enable_module(enum module_id module, int enable)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080107fe** (RW mirror) [nottaken-only] — `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:85): `STM32_RTC_WPR = 0x53;`
  - **What:** a conditional derived from this statement — `STM32_RTC_WPR = 0x53;`. When the condition holds it runs `static inline uint32_t rtc_to_sec(uint32_t rtc)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000834  `adc_init`  (conf:high)
**Signature:** `static void adc_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/adc-stm32f0.c:349  | rebuilt @ 0x80007c8 | 7 uncovered (2 unreached, 5 one-dir; 4 in RW mirror)

- **0x08000846** [taken-only] — `lsls r1, r1, #0x1f` sets flags from a shifted value (bit test) then `bmi`. operand = word [r2+0] (a struct/buffer field). MISSING (taken-only) needs the tested bit clear.
  - rebuilt C (adc-stm32f0.c:354 (discriminator 1)): `if (STM32_RCC_APB2ENR & (1 << 9) && (STM32_ADC_CR & STM32_ADC_CR_ADEN))`
  - **What:** an `if` test — `if (STM32_RCC_APB2ENR & (1 << 9) && (STM32_ADC_CR & STM32_ADC_CR_ADEN))`. When the condition holds it runs `return;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08000858** [nottaken-only] — `cmp r3, #0` then `blt`: taken when r3 < constant 0. r3 = word [r2+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 < constant 0.
  - rebuilt C (adc-stm32f0.c:364): `while (STM32_ADC_CR & STM32_ADC_CR_ADCAL)`
  - **What:** a loop condition — `while (STM32_ADC_CR & STM32_ADC_CR_ADCAL)`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800087a** [taken-only] — `tst r1, r3` then `bne`: tests bits of r1 (= word [r0+0] (a struct/buffer field)) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (adc-stm32f0.c:379): `while (!(STM32_ADC_ISR & STM32_ADC_ISR_ADRDY))`
  - **What:** a loop condition — `while (!(STM32_ADC_ISR & STM32_ADC_ISR_ADRDY))`. When the condition holds it runs `STM32_ADC_CR = STM32_ADC_CR_ADEN;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08010840** (RW mirror) [nottaken-only] — `tst r1, r0` then `beq`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r0. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (adc-stm32f0.c:354): `if (STM32_RCC_APB2ENR & (1 << 9) && (STM32_ADC_CR & STM32_ADC_CR_ADEN))`
  - **What:** an `if` test — `if (STM32_RCC_APB2ENR & (1 << 9) && (STM32_ADC_CR & STM32_ADC_CR_ADEN))`. When the condition holds it runs `return;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010846** (RW mirror) [taken-only] — `lsls r1, r1, #0x1f` sets flags from a shifted value (bit test) then `bmi`. operand = word [r2+0] (a struct/buffer field). MISSING (taken-only) needs the tested bit clear.
  - rebuilt C (adc-stm32f0.c:354 (discriminator 1)): `if (STM32_RCC_APB2ENR & (1 << 9) && (STM32_ADC_CR & STM32_ADC_CR_ADEN))`
  - **What:** an `if` test — `if (STM32_RCC_APB2ENR & (1 << 9) && (STM32_ADC_CR & STM32_ADC_CR_ADEN))`. When the condition holds it runs `return;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08010858** (RW mirror) [unreached] — `cmp r3, #0` then `blt`: taken when r3 < constant 0. r3 = word [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r3 < constant 0.
  - rebuilt C (adc-stm32f0.c:364): `while (STM32_ADC_CR & STM32_ADC_CR_ADCAL)`
  - **What:** a loop condition — `while (STM32_ADC_CR & STM32_ADC_CR_ADCAL)`. When the condition holds it runs `;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801087a** (RW mirror) [unreached] — `tst r1, r3` then `bne`: tests bits of r1 (= word [r0+0] (a struct/buffer field)) against mask r3. MISSING (unreached) needs the masked bits zero.
  - rebuilt C (adc-stm32f0.c:379): `while (!(STM32_ADC_ISR & STM32_ADC_ISR_ADRDY))`
  - **What:** a loop condition — `while (!(STM32_ADC_ISR & STM32_ADC_ISR_ADRDY))`. When the condition holds it runs `STM32_ADC_CR = STM32_ADC_CR_ADEN;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x0800089c  `adc_read_all_channels`  (conf:approx)
**Signature:** `int adc_read_all_channels(int *data)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/adc-stm32f0.c:288  | rebuilt @ 0x80008a4 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080008e8** [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r7+0] (a struct/buffer field). MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (adc-stm32f0.c:318): `STM32_ADC_ISR = 0xe;`
  - **What:** a conditional derived from this statement — `STM32_ADC_ISR = 0xe;`. When the condition holds it runs `STM32_ADC_IER |= profile.ier_reg;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080108e8** (RW mirror) [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r7+0] (a struct/buffer field). MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (adc-stm32f0.c:318): `STM32_ADC_ISR = 0xe;`
  - **What:** a conditional derived from this statement — `STM32_ADC_ISR = 0xe;`. When the condition holds it runs `STM32_ADC_IER |= profile.ier_reg;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08000990  `adc_read_channel`  (conf:approx)
**Signature:** `int adc_read_channel(enum adc_channel ch)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/adc-stm32f0.c:255  | rebuilt @ 0x8000830 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080009da** [nottaken-only] — `tst r0, r3` then `beq`: tests bits of r0 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (adc-stm32f0.c:284): `return value * adc->factor_mul / adc->factor_div + adc->shift;`
  - **What:** a conditional derived from this statement — `return value * adc->factor_mul / adc->factor_div + adc->shift;`. When the condition holds it runs `int adc_read_all_channels(int *data)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080109da** (RW mirror) [nottaken-only] — `tst r0, r3` then `beq`: tests bits of r0 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (adc-stm32f0.c:284): `return value * adc->factor_mul / adc->factor_div + adc->shift;`
  - **What:** a conditional derived from this statement — `return value * adc->factor_mul / adc->factor_div + adc->shift;`. When the condition holds it runs `int adc_read_all_channels(int *data)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000ac0  `clock_init`  (conf:approx)
**Signature:** `void clock_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/clock-stm32f0.c:521  | rebuilt @ 0x8000a88 | 5 uncovered (1 unreached, 4 one-dir; 3 in RW mirror)

- **0x08000ae4** [nottaken-only] — `tst r2, r1` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r1. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:296): `STM32_RCC_CR2 |= 1 << 16;`
  - **What:** a conditional derived from this statement — `STM32_RCC_CR2 |= 1 << 16;`. When the condition holds it runs `while (!(STM32_RCC_CR2 & (1 << 17)))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000aee** [nottaken-only] — `cmp r2, #0xc` then `bne`: taken when r2 != constant 0xc. r2 = computed (ands r1). MISSING direction (nottaken-only) needs r2 != constant 0xc.
  - rebuilt C (clock-stm32f0.c:298): `while (!(STM32_RCC_CR2 & (1 << 17)))`
  - **What:** a loop condition — `while (!(STM32_RCC_CR2 & (1 << 17)))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010aca** (RW mirror) [nottaken-only] — `tst r2, r1` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r1. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:532): `STM32_FLASH_ACR = STM32_FLASH_ACR_LATENCY | STM32_FLASH_ACR_PRFTEN;`
  - **What:** a conditional derived from this statement — `STM32_FLASH_ACR = STM32_FLASH_ACR_LATENCY | STM32_FLASH_ACR_PRFTEN;`. When the condition holds it runs `config_hispeed_clock();`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010ae4** (RW mirror) [unreached] — `tst r2, r1` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r1. MISSING (unreached) needs the masked bits zero.
  - rebuilt C (clock-stm32f0.c:296): `STM32_RCC_CR2 |= 1 << 16;`
  - **What:** a conditional derived from this statement — `STM32_RCC_CR2 |= 1 << 16;`. When the condition holds it runs `while (!(STM32_RCC_CR2 & (1 << 17)))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08010aee** (RW mirror) [nottaken-only] — `cmp r2, #0xc` then `bne`: taken when r2 != constant 0xc. r2 = computed (ands r1). MISSING direction (nottaken-only) needs r2 != constant 0xc.
  - rebuilt C (clock-stm32f0.c:298): `while (!(STM32_RCC_CR2 & (1 << 17)))`
  - **What:** a loop condition — `while (!(STM32_RCC_CR2 & (1 << 17)))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000b34  `rtc_init`  (conf:approx)
**Signature:** `void rtc_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/clock-stm32f0.c:496  | rebuilt @ 0x8000a14 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08000b52** [nottaken-only] — `tst r0, r3` then `beq`: tests bits of r0 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:501 (discriminator 1)): `while (!(STM32_RTC_ISR & STM32_RTC_ISR_INITF))`
  - **What:** a loop condition — `while (!(STM32_RTC_ISR & STM32_RTC_ISR_INITF))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000b68** [nottaken-only] — `tst r1, r3` then `bne`: tests bits of r1 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:509 (discriminator 1)): `while (STM32_RTC_ISR & STM32_RTC_ISR_INITF)`
  - **What:** a loop condition — `while (STM32_RTC_ISR & STM32_RTC_ISR_INITF)`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010b52** (RW mirror) [nottaken-only] — `tst r0, r3` then `beq`: tests bits of r0 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:501 (discriminator 1)): `while (!(STM32_RTC_ISR & STM32_RTC_ISR_INITF))`
  - **What:** a loop condition — `while (!(STM32_RTC_ISR & STM32_RTC_ISR_INITF))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010b68** (RW mirror) [nottaken-only] — `tst r1, r3` then `bne`: tests bits of r1 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (clock-stm32f0.c:509 (discriminator 1)): `while (STM32_RTC_ISR & STM32_RTC_ISR_INITF)`
  - **What:** a loop condition — `while (STM32_RTC_ISR & STM32_RTC_ISR_INITF)`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000d00  `dma_wait`  (conf:approx)
**Signature:** `int dma_wait(enum dma_channel channel)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/dma.c:246  | rebuilt @ 0x8000c08 | 6 uncovered (0 unreached, 6 one-dir; 3 in RW mirror)

- **0x08000d34** [nottaken-only] — `cmp r5, r3` then `bhi`: taken when r5 >u r3 (= word [sp+4] (a struct/buffer field)). r5 = register r5. MISSING direction (nottaken-only) needs r5 >u r3 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (dma.c:253): `if (deadline.val <= get_time().val)`
  - **What:** an `if` test — `if (deadline.val <= get_time().val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000d36** [nottaken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= word [sp+4] (a struct/buffer field)). r5 = register r5. MISSING direction (nottaken-only) needs r5 != r3 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (dma.c:253): `if (deadline.val <= get_time().val)`
  - **What:** an `if` test — `if (deadline.val <= get_time().val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000d3a** [nottaken-only] — `cmp r4, r2` then `bls`: taken when r4 <=u r2 (= word [sp+0] (a struct/buffer field)). r4 = register r4. MISSING direction (nottaken-only) needs r4 <=u r2 (= word [sp+0] (a struct/buffer field)).
  - rebuilt C (dma.c:253): `if (deadline.val <= get_time().val)`
  - **What:** an `if` test — `if (deadline.val <= get_time().val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010d34** (RW mirror) [nottaken-only] — `cmp r5, r3` then `bhi`: taken when r5 >u r3 (= word [sp+4] (a struct/buffer field)). r5 = register r5. MISSING direction (nottaken-only) needs r5 >u r3 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (dma.c:253): `if (deadline.val <= get_time().val)`
  - **What:** an `if` test — `if (deadline.val <= get_time().val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010d36** (RW mirror) [nottaken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= word [sp+4] (a struct/buffer field)). r5 = register r5. MISSING direction (nottaken-only) needs r5 != r3 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (dma.c:253): `if (deadline.val <= get_time().val)`
  - **What:** an `if` test — `if (deadline.val <= get_time().val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010d3a** (RW mirror) [nottaken-only] — `cmp r4, r2` then `bls`: taken when r4 <=u r2 (= word [sp+0] (a struct/buffer field)). r4 = register r4. MISSING direction (nottaken-only) needs r4 <=u r2 (= word [sp+0] (a struct/buffer field)).
  - rebuilt C (dma.c:253): `if (deadline.val <= get_time().val)`
  - **What:** an `if` test — `if (deadline.val <= get_time().val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000dfc  `dma_event_interrupt_channel_1`  (conf:high)
**Signature:** `void dma_event_interrupt_channel_1(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/dma.c:308  | rebuilt @ 0x8000cf4 | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x08000e04** [taken-only] — `lsls r3, r3, #0x1e` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (dma.c:309): `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(STM32_DMAC_CH1)) {`
  - **What:** an `if` test — `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(STM32_DMAC_CH1)) {`. When the condition holds it runs `dma_clear_isr(STM32_DMAC_CH1);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08000e12** [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (dma.c:311): `if (dma_irq[STM32_DMAC_CH1].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[STM32_DMAC_CH1].cb != NULL)`. When the condition holds it runs `(*dma_irq[STM32_DMAC_CH1].cb)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08010e04** (RW mirror) [taken-only] — `lsls r3, r3, #0x1e` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (dma.c:309): `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(STM32_DMAC_CH1)) {`
  - **What:** an `if` test — `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(STM32_DMAC_CH1)) {`. When the condition holds it runs `dma_clear_isr(STM32_DMAC_CH1);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08010e12** (RW mirror) [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (dma.c:311): `if (dma_irq[STM32_DMAC_CH1].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[STM32_DMAC_CH1].cb != NULL)`. When the condition holds it runs `(*dma_irq[STM32_DMAC_CH1].cb)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08000e24  `dma_event_interrupt_channel_2_3`  (conf:approx)
**Signature:** `void dma_event_interrupt_channel_2_3(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/dma.c:319  | rebuilt @ 0x8000d1c | 6 uncovered (2 unreached, 4 one-dir; 4 in RW mirror)

- **0x08000e3c** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (dma.c:325): `if (dma_irq[i].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[i].cb != NULL)`. When the condition holds it runs `(*dma_irq[i].cb)(dma_irq[i].cb_data);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08000e54** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (dma.c:325): `if (dma_irq[i].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[i].cb != NULL)`. When the condition holds it runs `(*dma_irq[i].cb)(dma_irq[i].cb_data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010e2e** (RW mirror) [taken-only] — `lsls r3, r3, #0x1a` sets flags from a shifted value (bit test) then `bpl`. operand = word [r1+0] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (dma.c:323): `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`
  - **What:** an `if` test — `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`. When the condition holds it runs `dma_clear_isr(i);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08010e3c** (RW mirror) [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+8] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (dma.c:325): `if (dma_irq[i].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[i].cb != NULL)`. When the condition holds it runs `(*dma_irq[i].cb)(dma_irq[i].cb_data);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08010e46** (RW mirror) [taken-only] — `lsls r3, r3, #0x16` sets flags from a shifted value (bit test) then `bpl`. operand = word [r4+0] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (dma.c:323): `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`
  - **What:** an `if` test — `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`. When the condition holds it runs `dma_clear_isr(i);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08010e54** (RW mirror) [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+0x10] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (dma.c:325): `if (dma_irq[i].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[i].cb != NULL)`. When the condition holds it runs `(*dma_irq[i].cb)(dma_irq[i].cb_data);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08000e64  `dma_event_interrupt_channel_4_7`  (conf:approx)
**Signature:** `void dma_event_interrupt_channel_4_7(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/dma.c:333  | rebuilt @ 0x8000d5c | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x08000e76** [taken-only] — `tst r2, r3` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (dma.c:337): `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`
  - **What:** an `if` test — `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`. When the condition holds it runs `dma_clear_isr(i);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08000e84** [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (dma.c:339): `if (dma_irq[i].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[i].cb != NULL)`. When the condition holds it runs `(*dma_irq[i].cb)(dma_irq[i].cb_data);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08010e76** (RW mirror) [taken-only] — `tst r2, r3` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (dma.c:337): `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`
  - **What:** an `if` test — `if (STM32_DMA1_REGS->isr & STM32_DMA_ISR_TCIF(i)) {`. When the condition holds it runs `dma_clear_isr(i);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08010e84** (RW mirror) [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (dma.c:339): `if (dma_irq[i].cb != NULL)`
  - **What:** an `if` test — `if (dma_irq[i].cb != NULL)`. When the condition holds it runs `(*dma_irq[i].cb)(dma_irq[i].cb_data);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08000f00  `dma_event_interrupt_channel_2_3`  (conf:approx)
**Signature:** `void dma_event_interrupt_channel_2_3(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/dma.c:319  | rebuilt @ 0x8000d1c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08000f28** [nottaken-only] — `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = computed (adds r4, #1). MISSING direction (nottaken-only) needs r3 <= constant 0.
  - rebuilt C (dma.c:324): `dma_clear_isr(i);`
  - **What:** a conditional derived from this statement — `dma_clear_isr(i);`. When the condition holds it runs `if (dma_irq[i].cb != NULL)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010f28** (RW mirror) [nottaken-only] — `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = computed (adds r4, #1). MISSING direction (nottaken-only) needs r3 <= constant 0.
  - rebuilt C (dma.c:324): `dma_clear_isr(i);`
  - **What:** a conditional derived from this statement — `dma_clear_isr(i);`. When the condition holds it runs `if (dma_irq[i].cb != NULL)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08000f44  `write_optb`  (conf:approx)
**Signature:** `static int write_optb(int byte, uint8_t value);`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/flash-f.c:162  | rebuilt @ 0x8000e28 | 16 uncovered (2 unreached, 14 one-dir; 8 in RW mirror)

- **0x08000f50** [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash-f.c:167): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000f8e** [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash-f.c:110): `rv = wait_busy();`
  - **What:** a conditional derived from this statement — `rv = wait_busy();`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000f9a** [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash-f.c:114): `rv = unlock(OPT_LOCK);`
  - **What:** a conditional derived from this statement — `rv = unlock(OPT_LOCK);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000fb4** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:122): `rv = wait_busy();`
  - **What:** a conditional derived from this statement — `rv = wait_busy();`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000fc8** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (lsls r5, #1). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:153): `rv = write_optb(i * 2, optb[i]);`
  - **What:** a conditional derived from this statement — `rv = write_optb(i * 2, optb[i]);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08000fd6** [unreached] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = computed (adds r0, #0). MISSING direction (unreached) needs r4 != constant 0.
  - rebuilt C (flash-f.c:183): `rv = unlock(OPT_LOCK);`
  - **What:** a conditional derived from this statement — `rv = unlock(OPT_LOCK);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08000fe6** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (lsls r0, #2). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:188): `STM32_FLASH_CR |= OPTPG;`
  - **What:** a conditional derived from this statement — `STM32_FLASH_CR |= OPTPG;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001008** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:200): `return EC_SUCCESS;`
  - **What:** a conditional derived from this statement — `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010f50** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash-f.c:167): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010f8e** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash-f.c:110): `rv = wait_busy();`
  - **What:** a conditional derived from this statement — `rv = wait_busy();`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010f9a** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash-f.c:114): `rv = unlock(OPT_LOCK);`
  - **What:** a conditional derived from this statement — `rv = unlock(OPT_LOCK);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010fb4** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:122): `rv = wait_busy();`
  - **What:** a conditional derived from this statement — `rv = wait_busy();`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010fc8** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (lsls r5, #1). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:153): `rv = write_optb(i * 2, optb[i]);`
  - **What:** a conditional derived from this statement — `rv = write_optb(i * 2, optb[i]);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08010fd6** (RW mirror) [unreached] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = computed (adds r0, #0). MISSING direction (unreached) needs r4 != constant 0.
  - rebuilt C (flash-f.c:183): `rv = unlock(OPT_LOCK);`
  - **What:** a conditional derived from this statement — `rv = unlock(OPT_LOCK);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08010fe6** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (lsls r0, #2). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:188): `STM32_FLASH_CR |= OPTPG;`
  - **What:** a conditional derived from this statement — `STM32_FLASH_CR |= OPTPG;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011008** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:200): `return EC_SUCCESS;`
  - **What:** a conditional derived from this statement — `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08001024  `flash_physical_write`  (conf:approx)
**Signature:** `int flash_physical_write(int offset, int size, const char *data)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/flash-f.c:207  | rebuilt @ 0x8000f00 | 7 uncovered (1 unreached, 6 one-dir; 6 in RW mirror)

- **0x080010b8** [taken-only] — `tst r7, r6` then `beq`: tests bits of r7 (= word [r6+0] (a struct/buffer field)) against mask r6. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (flash-f.c:264): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `int flash_physical_erase(int offset, int size)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801103c** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:213): `res = EC_ERROR_UNKNOWN;`
  - **What:** a conditional derived from this statement — `res = EC_ERROR_UNKNOWN;`. When the condition holds it runs `goto exit_wr;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011084** (RW mirror) [nottaken-only] — `cmp r6, r0` then `bge`: taken when r6 >= r0 (= function argument r0). r6 = computed (movs #0). MISSING direction (nottaken-only) needs r6 >= r0 (= function argument r0).
  - rebuilt C (flash-f.c:237): `data += 2;`
  - **What:** a conditional derived from this statement — `data += 2;`. When the condition holds it runs `for (i = 0; (STM32_FLASH_SR & 1) && (i < FLASH_TIMEOUT_LOOP);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801109e** (RW mirror) [taken-only] — `tst r7, r1` then `beq`: tests bits of r7 (= word [r2+0] (a struct/buffer field)) against mask r1. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (flash-f.c:251): `if (STM32_FLASH_SR & 0x14) {`
  - **What:** an `if` test — `if (STM32_FLASH_SR & 0x14) {`. When the condition holds it runs `res = EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080110a2** (RW mirror) [unreached] — `cmp r6, r0` then `bge`: taken when r6 >= r0 (= a value carried in from a preceding basic block). r6 = computed (movs #0). MISSING direction (unreached) needs r6 >= r0 (= a value carried in from a preceding basic block).
  - rebuilt C (flash-f.c:251): `if (STM32_FLASH_SR & 0x14) {`
  - **What:** an `if` test — `if (STM32_FLASH_SR & 0x14) {`. When the condition holds it runs `res = EC_ERROR_UNKNOWN;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080110ae** (RW mirror) [nottaken-only] — `tst r7, r6` then `bne`: tests bits of r7 (= word [r2+0] (a struct/buffer field)) against mask r6. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (flash-f.c:259): `STM32_FLASH_CR &= ~PG;`
  - **What:** a conditional derived from this statement — `STM32_FLASH_CR &= ~PG;`. When the condition holds it runs `lock();`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080110b8** (RW mirror) [taken-only] — `tst r7, r6` then `beq`: tests bits of r7 (= word [r6+0] (a struct/buffer field)) against mask r6. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (flash-f.c:264): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `int flash_physical_erase(int offset, int size)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080010e0  `flash_physical_erase`  (conf:approx)
**Signature:** `int flash_physical_erase(int offset, int size)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/flash-f.c:267  | rebuilt @ 0x8000fa4 | 10 uncovered (0 unreached, 10 one-dir; 6 in RW mirror)

- **0x080010f4** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r0, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (flash-f.c:270): `if (unlock(PRG_LOCK) != EC_SUCCESS)`
  - **What:** an `if` test — `if (unlock(PRG_LOCK) != EC_SUCCESS)`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800111e** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:284): `if (flash_is_erased(offset, CONFIG_FLASH_ERASE_SIZE))`
  - **What:** an `if` test — `if (flash_is_erased(offset, CONFIG_FLASH_ERASE_SIZE))`. When the condition holds it runs `continue;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001166** [taken-only] — `cmp r1, r3` then `bls`: taken when r1 <=u r3 (= word [sp+0x14] (a struct/buffer field)). r1 = word [sp+4] (a struct/buffer field). MISSING direction (taken-only) needs r1 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (flash-f.c:305): `if (STM32_FLASH_SR & 1) {`
  - **What:** an `if` test — `if (STM32_FLASH_SR & 1) {`. When the condition holds it runs `res = EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001174** [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= a value carried in from a preceding basic block). r1 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r1 != r3 (= a value carried in from a preceding basic block).
  - rebuilt C (flash-f.c:302 (discriminator 1)): `(get_time().val < deadline.val)) {`
  - **What:** a conditional derived from this statement — `(get_time().val < deadline.val)) {`. When the condition holds it runs `usleep(300);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080110f4** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r0, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (flash-f.c:270): `if (unlock(PRG_LOCK) != EC_SUCCESS)`
  - **What:** an `if` test — `if (unlock(PRG_LOCK) != EC_SUCCESS)`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801111e** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:284): `if (flash_is_erased(offset, CONFIG_FLASH_ERASE_SIZE))`
  - **What:** an `if` test — `if (flash_is_erased(offset, CONFIG_FLASH_ERASE_SIZE))`. When the condition holds it runs `continue;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011154** (RW mirror) [taken-only] — `tst r3, r0` then `beq`: tests bits of r3 (= word [r6+0] (a struct/buffer field)) against mask r0. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (flash-f.c:299): `deadline.val = get_time().val + FLASH_TIMEOUT_US;`
  - **What:** a conditional derived from this statement — `deadline.val = get_time().val + FLASH_TIMEOUT_US;`. When the condition holds it runs `while ((STM32_FLASH_SR & 1) &&`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011166** (RW mirror) [taken-only] — `cmp r1, r3` then `bls`: taken when r1 <=u r3 (= word [sp+0x14] (a struct/buffer field)). r1 = word [sp+4] (a struct/buffer field). MISSING direction (taken-only) needs r1 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (flash-f.c:305): `if (STM32_FLASH_SR & 1) {`
  - **What:** an `if` test — `if (STM32_FLASH_SR & 1) {`. When the condition holds it runs `res = EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011174** (RW mirror) [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= a value carried in from a preceding basic block). r1 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r1 != r3 (= a value carried in from a preceding basic block).
  - rebuilt C (flash-f.c:302 (discriminator 1)): `(get_time().val < deadline.val)) {`
  - **What:** a conditional derived from this statement — `(get_time().val < deadline.val)) {`. When the condition holds it runs `usleep(300);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801117a** (RW mirror) [taken-only] — `cmp r3, r2` then `bhi`: taken when r3 >u r2 (= a value carried in from a preceding basic block). r3 = word [sp+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 <=u r2 (= a value carried in from a preceding basic block).
  - rebuilt C (flash-f.c:303): `usleep(300);`
  - **What:** a conditional derived from this statement — `usleep(300);`. When the condition holds it runs `if (STM32_FLASH_SR & 1) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800125c  `flash_pre_init`  (conf:approx)
**Signature:** `int flash_pre_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/flash-f.c:407  | rebuilt @ 0x800111c | 13 uncovered (6 unreached, 7 one-dir; 7 in RW mirror)

- **0x08001270** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:412): `if (flash_physical_restore_state())`
  - **What:** an `if` test — `if (flash_physical_restore_state())`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001280** [taken-only] — flags from `ands r3, r6` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (flash-f.c:422): `if (prot_flags & EC_FLASH_PROTECT_GPIO_ASSERTED) {`
  - **What:** an `if` test — `if (prot_flags & EC_FLASH_PROTECT_GPIO_ASSERTED) {`. When the condition holds it runs `if ((prot_flags & EC_FLASH_PROTECT_RO_AT_BOOT) &&`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001288** [unreached] — `cmp r6, #1` then `bne`: taken when r6 != constant 1. r6 = computed (ands r5). MISSING direction (unreached) needs r6 != constant 1.
  - rebuilt C (flash-f.c:423): `if ((prot_flags & EC_FLASH_PROTECT_RO_AT_BOOT) &&`
  - **What:** an `if` test — `if ((prot_flags & EC_FLASH_PROTECT_RO_AT_BOOT) &&`. When the condition holds it runs `!(prot_flags & EC_FLASH_PROTECT_RO_NOW)) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080012ba** [unreached] — `cmp r7, r0` then `bne`: taken when r7 != r0 (= function argument r0). r7 = computed (adds r1, #0). MISSING direction (unreached) needs r7 != r0 (= function argument r0).
  - rebuilt C (flash-f.c:391): `if (flash_physical_get_protect_at_boot(i) != ro_at_boot)`
  - **What:** an `if` test — `if (flash_physical_get_protect_at_boot(i) != ro_at_boot)`. When the condition holds it runs `return 1;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080012c0** [unreached] — `cmp r3, #0x10` then `bne`: taken when r3 != constant 0x10. r3 = computed (adds r3, r6). MISSING direction (unreached) needs r3 != constant 0x10.
  - rebuilt C (flash-f.c:390): `for (i = ro_wp_region_start; i < ro_wp_region_end; i++)`
  - **What:** a loop condition — `for (i = ro_wp_region_start; i < ro_wp_region_end; i++)`. When the condition holds it runs `if (flash_physical_get_protect_at_boot(i) != ro_at_boot)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080012e0** [nottaken-only] — `lsls r3, r0, #0x19` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r5, #0x1e). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (flash-f.c:460): `if ((flash_physical_get_valid_flags() & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`
  - **What:** an `if` test — `if ((flash_physical_get_valid_flags() & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`. When the condition holds it runs `(!!(prot_flags & EC_FLASH_PROTECT_ALL_AT_BOOT) !=`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011270** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (flash-f.c:412): `if (flash_physical_restore_state())`
  - **What:** an `if` test — `if (flash_physical_restore_state())`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011278** (RW mirror) [nottaken-only] — flags from `ands r4, r3` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash-f.c:419): `if (reset_flags & RESET_FLAG_SYSJUMP)`
  - **What:** an `if` test — `if (reset_flags & RESET_FLAG_SYSJUMP)`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011280** (RW mirror) [taken-only] — flags from `ands r3, r6` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (flash-f.c:422): `if (prot_flags & EC_FLASH_PROTECT_GPIO_ASSERTED) {`
  - **What:** an `if` test — `if (prot_flags & EC_FLASH_PROTECT_GPIO_ASSERTED) {`. When the condition holds it runs `if ((prot_flags & EC_FLASH_PROTECT_RO_AT_BOOT) &&`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011288** (RW mirror) [unreached] — `cmp r6, #1` then `bne`: taken when r6 != constant 1. r6 = computed (ands r5). MISSING direction (unreached) needs r6 != constant 1.
  - rebuilt C (flash-f.c:423): `if ((prot_flags & EC_FLASH_PROTECT_RO_AT_BOOT) &&`
  - **What:** an `if` test — `if ((prot_flags & EC_FLASH_PROTECT_RO_AT_BOOT) &&`. When the condition holds it runs `!(prot_flags & EC_FLASH_PROTECT_RO_NOW)) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080112ba** (RW mirror) [unreached] — `cmp r7, r0` then `bne`: taken when r7 != r0 (= function argument r0). r7 = computed (adds r1, #0). MISSING direction (unreached) needs r7 != r0 (= function argument r0).
  - rebuilt C (flash-f.c:391): `if (flash_physical_get_protect_at_boot(i) != ro_at_boot)`
  - **What:** an `if` test — `if (flash_physical_get_protect_at_boot(i) != ro_at_boot)`. When the condition holds it runs `return 1;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080112c0** (RW mirror) [unreached] — `cmp r3, #0x10` then `bne`: taken when r3 != constant 0x10. r3 = computed (adds r3, r6). MISSING direction (unreached) needs r3 != constant 0x10.
  - rebuilt C (flash-f.c:390): `for (i = ro_wp_region_start; i < ro_wp_region_end; i++)`
  - **What:** a loop condition — `for (i = ro_wp_region_start; i < ro_wp_region_end; i++)`. When the condition holds it runs `if (flash_physical_get_protect_at_boot(i) != ro_at_boot)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080112e0** (RW mirror) [nottaken-only] — `lsls r3, r0, #0x19` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r5, #0x1e). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (flash-f.c:460): `if ((flash_physical_get_valid_flags() & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`
  - **What:** an `if` test — `if ((flash_physical_get_valid_flags() & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`. When the condition holds it runs `(!!(prot_flags & EC_FLASH_PROTECT_ALL_AT_BOOT) !=`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x080013b0  `gpio_set_flags_by_mask`  (conf:approx)
**Signature:** `void gpio_set_flags_by_mask(uint32_t port, uint32_t mask, uint32_t flags)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/gpio-f0-l.c:75  | rebuilt @ 0x8001274 | 5 uncovered (0 unreached, 5 one-dir; 1 in RW mirror)

- **0x080013da** [taken-only] — `lsls r1, r5, #0x1e` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (gpio-f0-l.c:82): `if (flags & GPIO_PULL_UP)`
  - **What:** an `if` test — `if (flags & GPIO_PULL_UP)`. When the condition holds it runs `val |= 0x55555555 & mask2;	/* Pull Up = 01 */`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800142e** [taken-only] — `lsls r3, r5, #0xe` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (gpio-f0-l.c:122): `val |= 0xaaaaaaaa & mask2;`
  - **What:** a conditional derived from this statement — `val |= 0xaaaaaaaa & mask2;`. When the condition holds it runs `STM32_GPIO_MODER(port) = val;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800143a** [taken-only] — `lsls r3, r5, #0x17` sets flags from a shifted value (bit test) then `bpl`. operand = a global/constant (pc-relative load). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (gpio-f0-l.c:127): `ASSERT(!(flags & (GPIO_INT_F_LOW | GPIO_INT_F_HIGH)));`
  - **What:** a conditional derived from this statement — `ASSERT(!(flags & (GPIO_INT_F_LOW | GPIO_INT_F_HIGH)));`. When the condition holds it runs `if (flags & GPIO_INT_F_RISING)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001446** [taken-only] — `lsls r3, r5, #0x16` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r7). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (gpio-f0-l.c:127 (discriminator 1)): `ASSERT(!(flags & (GPIO_INT_F_LOW | GPIO_INT_F_HIGH)));`
  - **What:** a conditional derived from this statement — `ASSERT(!(flags & (GPIO_INT_F_LOW | GPIO_INT_F_HIGH)));`. When the condition holds it runs `if (flags & GPIO_INT_F_RISING)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801142e** (RW mirror) [taken-only] — `lsls r3, r5, #0xe` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (gpio-f0-l.c:122): `val |= 0xaaaaaaaa & mask2;`
  - **What:** a conditional derived from this statement — `val |= 0xaaaaaaaa & mask2;`. When the condition holds it runs `STM32_GPIO_MODER(port) = val;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080014fc  `gpio_pre_init`  (conf:approx)
**Signature:** `void gpio_pre_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/gpio.c:24  | rebuilt @ 0x80013dc | 2 uncovered (0 unreached, 2 one-dir; 2 in RW mirror)

- **0x08011516** (RW mirror) [taken-only] — `cmp r5, #0` then `bne`: taken when r5 != constant 0. r5 = computed (adds r0, #0). MISSING direction (taken-only) needs r5 == constant 0.
  - rebuilt C (gpio.c:35): `if (!is_warm)`
  - **What:** an `if` test — `if (!is_warm)`. When the condition holds it runs `gpio_enable_clocks();`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801152a** (RW mirror) [nottaken-only] — `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = register r5. MISSING direction (nottaken-only) needs r5 == constant 0.
  - rebuilt C (gpio.c:49): `if (is_warm)`
  - **What:** an `if` test — `if (is_warm)`. When the condition holds it runs `flags &= ~(GPIO_LOW | GPIO_HIGH);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08001580  `gpio_interrupt`  (conf:approx)
**Signature:** `void __keep gpio_interrupt(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/gpio.c:105  | rebuilt @ 0x8001464 | 3 uncovered (1 unreached, 2 one-dir; 2 in RW mirror)

- **0x080015a6** [taken-only] — `cmp r0, r3` then `bge`: taken when r0 >= r3 (= word [r5+0] (a struct/buffer field)). r0 = function argument r0. MISSING direction (taken-only) needs r0 < r3 (= word [r5+0] (a struct/buffer field)).
  - rebuilt C (gpio.c:117): `gpio_irq_handlers[signal](signal);`
  - **What:** a conditional derived from this statement — `gpio_irq_handlers[signal](signal);`. When the condition holds it runs `#ifdef CHIP_FAMILY_STM32F0`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011596** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [sp+0xc] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (gpio.c:114): `bit = get_next_bit(&pending);`
  - **What:** a conditional derived from this statement — `bit = get_next_bit(&pending);`. When the condition holds it runs `signal = exti_events[bit];`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080115a6** (RW mirror) [unreached] — `cmp r0, r3` then `bge`: taken when r0 >= r3 (= word [r5+0] (a struct/buffer field)). r0 = function argument r0. MISSING direction (unreached) needs r0 >= r3 (= word [r5+0] (a struct/buffer field)).
  - rebuilt C (gpio.c:117): `gpio_irq_handlers[signal](signal);`
  - **What:** a conditional derived from this statement — `gpio_irq_handlers[signal](signal);`. When the condition holds it runs `#ifdef CHIP_FAMILY_STM32F0`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08001770  `i2c_init`  (conf:approx)
**Signature:** `static void i2c_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/i2c-stm32f0.c:565  | rebuilt @ 0x8001650 | 9 uncovered (2 unreached, 7 one-dir; 5 in RW mirror)

- **0x080017a2** [nottaken-only] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = word [r7+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 != constant 0.
  - rebuilt C (i2c-stm32f0.c:149): `STM32_RCC_CFGR3 |= 0x10;`
  - **What:** a conditional derived from this statement — `STM32_RCC_CFGR3 |= 0x10;`. When the condition holds it runs `#endif`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080017c0** [nottaken-only] — `cmp r2, r3` then `beq`: taken when r2 == r3 (= computed (lsls r3, #1)). r2 = word [r7+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == r3 (= computed (lsls r3, #1)).
  - rebuilt C (i2c-stm32f0.c:159): `freq = I2C_FREQ_1000KHZ;`
  - **What:** a conditional derived from this statement — `freq = I2C_FREQ_1000KHZ;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080017ca** [taken-only] — `cmp r2, r3` then `beq`: taken when r2 == r3 (= computed (lsls r3, #2)). r2 = word [r7+8] (a struct/buffer field). MISSING direction (taken-only) needs r2 != r3 (= computed (lsls r3, #2)).
  - rebuilt C (i2c-stm32f0.c:157): `switch (p->kbps) {`
  - **What:** a `switch` dispatch on the value — `switch (p->kbps) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080017d0** [unreached] — `cmp r2, #0x64` then `beq`: taken when r2 == constant 0x64. r2 = word [r7+8] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0x64.
  - rebuilt C (i2c-stm32f0.c:168): `CPRINTS("I2C bad speed %d kBps", p->kbps);`
  - **What:** a conditional derived from this statement — `CPRINTS("I2C bad speed %d kBps", p->kbps);`. When the condition holds it runs `freq = I2C_FREQ_100KHZ;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08011798** (RW mirror) [taken-only] — `tst r1, r3` then `bne`: tests bits of r1 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (i2c-stm32f0.c:134): `STM32_RCC_APB1ENR |= 1 << (21 + port);`
  - **What:** a conditional derived from this statement — `STM32_RCC_APB1ENR |= 1 << (21 + port);`. When the condition holds it runs `if (port == STM32_I2C1_PORT) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080117a2** (RW mirror) [nottaken-only] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = word [r7+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 != constant 0.
  - rebuilt C (i2c-stm32f0.c:149): `STM32_RCC_CFGR3 |= 0x10;`
  - **What:** a conditional derived from this statement — `STM32_RCC_CFGR3 |= 0x10;`. When the condition holds it runs `#endif`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080117c0** (RW mirror) [nottaken-only] — `cmp r2, r3` then `beq`: taken when r2 == r3 (= computed (lsls r3, #1)). r2 = word [r7+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == r3 (= computed (lsls r3, #1)).
  - rebuilt C (i2c-stm32f0.c:159): `freq = I2C_FREQ_1000KHZ;`
  - **What:** a conditional derived from this statement — `freq = I2C_FREQ_1000KHZ;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080117ca** (RW mirror) [taken-only] — `cmp r2, r3` then `beq`: taken when r2 == r3 (= computed (lsls r3, #2)). r2 = word [r7+8] (a struct/buffer field). MISSING direction (taken-only) needs r2 != r3 (= computed (lsls r3, #2)).
  - rebuilt C (i2c-stm32f0.c:157): `switch (p->kbps) {`
  - **What:** a `switch` dispatch on the value — `switch (p->kbps) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080117d0** (RW mirror) [unreached] — `cmp r2, #0x64` then `beq`: taken when r2 == constant 0x64. r2 = word [r7+8] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0x64.
  - rebuilt C (i2c-stm32f0.c:168): `CPRINTS("I2C bad speed %d kBps", p->kbps);`
  - **What:** a conditional derived from this statement — `CPRINTS("I2C bad speed %d kBps", p->kbps);`. When the condition holds it runs `freq = I2C_FREQ_100KHZ;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08001854  `i2c2_event_interrupt`  (conf:approx)
**Signature:** `void i2c2_event_interrupt(void) { i2c_event_handler(I2C_PORT_EC); }`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/i2c-stm32f0.c:405  | rebuilt @ 0x8001728 | 13 uncovered (6 unreached, 7 one-dir; 12 in RW mirror)

- **0x0800191c** [nottaken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r1+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == constant 0.
  - rebuilt C (i2c-stm32f0.c:356): `if (port == I2C_PORT_EC && tx_index)`
  - **What:** an `if` test — `if (port == I2C_PORT_EC && tx_index)`. When the condition holds it runs `tx_index--;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011860** (RW mirror) [taken-only] — `tst r3, r4` then `beq`: tests bits of r3 (= word [r2+0] (a struct/buffer field)) against mask r4. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (i2c-stm32f0.c:287): `if (i2c_isr & (STM32_I2C_ISR_ARLO | STM32_I2C_ISR_BERR)) {`
  - **What:** an `if` test — `if (i2c_isr & (STM32_I2C_ISR_ARLO | STM32_I2C_ISR_BERR)) {`. When the condition holds it runs `rx_pending = 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801187e** (RW mirror) [taken-only] — `lsls r1, r3, #0x1c` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r4). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (i2c-stm32f0.c:300): `if (i2c_isr & STM32_I2C_ISR_ADDR) {`
  - **What:** an `if` test — `if (i2c_isr & STM32_I2C_ISR_ADDR) {`. When the condition holds it runs `if (i2c_isr & STM32_I2C_ISR_DIR) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801188a** (RW mirror) [unreached] — `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = computed (ands r3). MISSING direction (unreached) needs r1 == constant 0.
  - rebuilt C (i2c-stm32f0.c:301): `if (i2c_isr & STM32_I2C_ISR_DIR) {`
  - **What:** an `if` test — `if (i2c_isr & STM32_I2C_ISR_DIR) {`. When the condition holds it runs `STM32_I2C_ISR(port) |= STM32_I2C_ISR_TXE;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080118c0** (RW mirror) [taken-only] — `tst r3, r0` then `beq`: tests bits of r3 (= function argument r3) against mask r0. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (i2c-stm32f0.c:321): `if (i2c_isr & STM32_I2C_ISR_STOP) {`
  - **What:** an `if` test — `if (i2c_isr & STM32_I2C_ISR_STOP) {`. When the condition holds it runs `#ifdef TCPCI_I2C_SLAVE`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080118ec** (RW mirror) [taken-only] — `lsls r2, r3, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = a global/constant (pc-relative load). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (i2c-stm32f0.c:346): `if (i2c_isr & STM32_I2C_ISR_RXNE)`
  - **What:** an `if` test — `if (i2c_isr & STM32_I2C_ISR_RXNE)`. When the condition holds it runs `host_buffer[buf_idx++] = STM32_I2C_RXDR(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011902** (RW mirror) [taken-only] — `tst r3, r0` then `beq`: tests bits of r3 (= function argument r3) against mask r0. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (i2c-stm32f0.c:350): `if (i2c_isr & STM32_I2C_ISR_NACK) {`
  - **What:** an `if` test — `if (i2c_isr & STM32_I2C_ISR_NACK) {`. When the condition holds it runs `STM32_I2C_CR1(port) &= ~STM32_I2C_CR1_TXIE;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801191c** (RW mirror) [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r1+4] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (i2c-stm32f0.c:356): `if (port == I2C_PORT_EC && tx_index)`
  - **What:** an `if` test — `if (port == I2C_PORT_EC && tx_index)`. When the condition holds it runs `tx_index--;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08011926** (RW mirror) [taken-only] — `tst r3, r0` then `beq`: tests bits of r3 (= function argument r3) against mask r0. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (i2c-stm32f0.c:361): `if (i2c_isr & STM32_I2C_ISR_TXIS) {`
  - **What:** an `if` test — `if (i2c_isr & STM32_I2C_ISR_TXIS) {`. When the condition holds it runs `if (port == I2C_PORT_EC) { /* host is waiting for PD response */`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011930** (RW mirror) [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r3+0x24] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (i2c-stm32f0.c:363): `if (tx_pending) {`
  - **What:** an `if` test — `if (tx_pending) {`. When the condition holds it runs `if (tx_index < tx_end) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801193a** (RW mirror) [unreached] — `cmp r2, r0` then `bge`: taken when r2 >= r0 (= word [r3+8] (a struct/buffer field)). r2 = word [r3+4] (a struct/buffer field). MISSING direction (unreached) needs r2 >= r0 (= word [r3+8] (a struct/buffer field)).
  - rebuilt C (i2c-stm32f0.c:364): `if (tx_index < tx_end) {`
  - **What:** an `if` test — `if (tx_index < tx_end) {`. When the condition holds it runs `STM32_I2C_TXDR(port) =`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801195a** (RW mirror) [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0x20] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (i2c-stm32f0.c:378): `} else if (rx_pending) {`
  - **What:** an `if` test — `} else if (rx_pending) {`. When the condition holds it runs `host_i2c_resp_port = port;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801198c** (RW mirror) [unreached] — `cmp r3, #0xd9` then `bhi`: taken when r3 >u constant 0xd9. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r3 >u constant 0xd9.
  - rebuilt C (i2c-stm32f0.c:245): `if (*buff >= EC_COMMAND_PROTOCOL_3) {`
  - **What:** an `if` test — `if (*buff >= EC_COMMAND_PROTOCOL_3) {`. When the condition holds it runs `i2c_packet.driver_result = EC_RES_SUCCESS;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080019f8  `spi_dma_wait`  (conf:approx)
**Signature:** `static int spi_dma_wait(int port)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/spi_master.c:160  | rebuilt @ 0x80018c8 | 18 uncovered (0 unreached, 18 one-dir; 9 in RW mirror)

- **0x08001a10** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r6, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (spi_master.c:167): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001a40** [nottaken-only] — `cmp r3, r5` then `bhi`: taken when r3 >u r5 (= register r5). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u r5 (= register r5).
  - rebuilt C (spi_master.c:173): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001a42** [nottaken-only] — `cmp r3, r5` then `bne`: taken when r3 != r5 (= register r5). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != r5 (= register r5).
  - rebuilt C (spi_master.c:173): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001a46** [taken-only] — `cmp r2, r4` then `bls`: taken when r2 <=u r4 (= register r4). r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (taken-only) needs r2 >u r4 (= register r4).
  - rebuilt C (spi_master.c:173): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001a50** [nottaken-only] — `lsls r3, r3, #0x18` sets flags from a shifted value (bit test) then `bmi`. operand = word [r3+8] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (spi_master.c:172 (discriminator 1)): `while ((spi->sr & STM32_SPI_SR_FTLVL) || (spi->sr & STM32_SPI_SR_BSY))`
  - **What:** a loop condition — `while ((spi->sr & STM32_SPI_SR_FTLVL) || (spi->sr & STM32_SPI_SR_BSY))`. When the condition holds it runs `if (get_time().val > timeout.val)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001a6a** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (spi_master.c:180): `rv = dma_wait(dma_rx_option[port].channel);`
  - **What:** a conditional derived from this statement — `rv = dma_wait(dma_rx_option[port].channel);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001a96** [nottaken-only] — `cmp r3, r7` then `bhi`: taken when r3 >u r7 (= register r7). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u r7 (= register r7).
  - rebuilt C (spi_master.c:187): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001a98** [nottaken-only] — `cmp r3, r7` then `bne`: taken when r3 != r7 (= register r7). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != r7 (= register r7).
  - rebuilt C (spi_master.c:187): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001a9c** [taken-only] — `cmp r2, r6` then `bls`: taken when r2 <=u r6 (= register r6). r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (taken-only) needs r2 >u r6 (= register r6).
  - rebuilt C (spi_master.c:187): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011a10** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r6, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (spi_master.c:167): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011a40** (RW mirror) [nottaken-only] — `cmp r3, r5` then `bhi`: taken when r3 >u r5 (= register r5). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u r5 (= register r5).
  - rebuilt C (spi_master.c:173): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011a42** (RW mirror) [nottaken-only] — `cmp r3, r5` then `bne`: taken when r3 != r5 (= register r5). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != r5 (= register r5).
  - rebuilt C (spi_master.c:173): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011a46** (RW mirror) [taken-only] — `cmp r2, r4` then `bls`: taken when r2 <=u r4 (= register r4). r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (taken-only) needs r2 >u r4 (= register r4).
  - rebuilt C (spi_master.c:173): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011a50** (RW mirror) [nottaken-only] — `lsls r3, r3, #0x18` sets flags from a shifted value (bit test) then `bmi`. operand = word [r3+8] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (spi_master.c:172 (discriminator 1)): `while ((spi->sr & STM32_SPI_SR_FTLVL) || (spi->sr & STM32_SPI_SR_BSY))`
  - **What:** a loop condition — `while ((spi->sr & STM32_SPI_SR_FTLVL) || (spi->sr & STM32_SPI_SR_BSY))`. When the condition holds it runs `if (get_time().val > timeout.val)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011a6a** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (spi_master.c:180): `rv = dma_wait(dma_rx_option[port].channel);`
  - **What:** a conditional derived from this statement — `rv = dma_wait(dma_rx_option[port].channel);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011a96** (RW mirror) [nottaken-only] — `cmp r3, r7` then `bhi`: taken when r3 >u r7 (= register r7). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u r7 (= register r7).
  - rebuilt C (spi_master.c:187): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011a98** (RW mirror) [nottaken-only] — `cmp r3, r7` then `bne`: taken when r3 != r7 (= register r7). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != r7 (= register r7).
  - rebuilt C (spi_master.c:187): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011a9c** (RW mirror) [taken-only] — `cmp r2, r6` then `bls`: taken when r2 <=u r6 (= register r6). r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (taken-only) needs r2 >u r6 (= register r6).
  - rebuilt C (spi_master.c:187): `if (get_time().val > timeout.val)`
  - **What:** an `if` test — `if (get_time().val > timeout.val)`. When the condition holds it runs `return EC_ERROR_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08001ac0  `spi_enable`  (conf:approx)
**Signature:** `int spi_enable(int port, int enable)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/spi_master.c:134  | rebuilt @ 0x800198c | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08001af0** [taken-only] — `cmp r3, r1` then `bge`: taken when r3 >= r1 (= byte [r1+1] (a struct/buffer field)). r3 = computed (adds r2, #0). MISSING direction (taken-only) needs r3 < r1 (= byte [r1+1] (a struct/buffer field)).
  - rebuilt C (spi_master.c:74): `if ((spi_devices[i].port == port) &&`
  - **What:** an `if` test — `if ((spi_devices[i].port == port) &&`. When the condition holds it runs `(div < spi_devices[i].div))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001b60** [taken-only] — `tst r0, r1` then `beq`: tests bits of r0 (= word [r3+8] (a struct/buffer field)) against mask r1. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (spi_master.c:124): `while (spi->sr & STM32_SPI_SR_FTLVL)`
  - **What:** a loop condition — `while (spi->sr & STM32_SPI_SR_FTLVL)`. When the condition holds it runs `dummy = spi->dr;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011af0** (RW mirror) [taken-only] — `cmp r3, r1` then `bge`: taken when r3 >= r1 (= byte [r1+1] (a struct/buffer field)). r3 = computed (adds r2, #0). MISSING direction (taken-only) needs r3 < r1 (= byte [r1+1] (a struct/buffer field)).
  - rebuilt C (spi_master.c:74): `if ((spi_devices[i].port == port) &&`
  - **What:** an `if` test — `if ((spi_devices[i].port == port) &&`. When the condition holds it runs `(div < spi_devices[i].div))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011b60** (RW mirror) [taken-only] — `tst r0, r1` then `beq`: tests bits of r0 (= word [r3+8] (a struct/buffer field)) against mask r1. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (spi_master.c:124): `while (spi->sr & STM32_SPI_SR_FTLVL)`
  - **What:** a loop condition — `while (spi->sr & STM32_SPI_SR_FTLVL)`. When the condition holds it runs `dummy = spi->dr;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08001b8c  `spi_transaction_async`  (conf:approx)
**Signature:** `int spi_transaction_async(const struct spi_device_t *spi_device, const uint8_t *txdata, int txlen, uint8_t *rxdata, int rxlen)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/spi_master.c:199  | rebuilt @ 0x8001a68 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08001bc0** [taken-only] — `tst r1, r2` then `beq`: tests bits of r1 (= word [r3+8] (a struct/buffer field)) against mask r2. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (spi_master.c:215): `(void) (uint8_t) spi->dr;`
  - **What:** a conditional derived from this statement — `(void) (uint8_t) spi->dr;`. When the condition holds it runs `rv = spi_dma_start(port, txdata, buf, txlen);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001c04** [nottaken-only] — flags from `subs r6, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (spi_master.c:222): `if (rv != EC_SUCCESS)`
  - **What:** an `if` test — `if (rv != EC_SUCCESS)`. When the condition holds it runs `goto err_free;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011bc0** (RW mirror) [taken-only] — `tst r1, r2` then `beq`: tests bits of r1 (= word [r3+8] (a struct/buffer field)) against mask r2. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (spi_master.c:215): `(void) (uint8_t) spi->dr;`
  - **What:** a conditional derived from this statement — `(void) (uint8_t) spi->dr;`. When the condition holds it runs `rv = spi_dma_start(port, txdata, buf, txlen);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011c04** (RW mirror) [nottaken-only] — flags from `subs r6, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (spi_master.c:222): `if (rv != EC_SUCCESS)`
  - **What:** an `if` test — `if (rv != EC_SUCCESS)`. When the condition holds it runs `goto err_free;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08001d78  `system_pre_init`  (conf:approx)
**Signature:** `void system_pre_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/system.c:182  | rebuilt @ 0x8001c64 | 13 uncovered (0 unreached, 13 one-dir; 7 in RW mirror)

- **0x08001db4** [nottaken-only] — `tst r0, r1` then `beq`: tests bits of r0 (= word [r3+0] (a struct/buffer field)) against mask r1. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (system.c:204 (discriminator 1)): `while (!(STM32_RCC_CSR & (1 << 1)))`
  - **What:** a loop condition — `while (!(STM32_RCC_CSR & (1 << 1)))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001e0c** [nottaken-only] — `lsls r2, r3, #0x14` sets flags from a shifted value (bit test) then `bmi`. operand = function argument r2. MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (system.c:132): `flags &= ~CONSOLE_BIT_MASK;`
  - **What:** a conditional derived from this statement — `flags &= ~CONSOLE_BIT_MASK;`. When the condition holds it runs `STM32_RCC_CSR |= 1 << 24;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001e2c** [taken-only] — `tst r6, r3` then `beq`: tests bits of r6 (= register r6) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (system.c:156): `if (raw_cause & 0x04000000)`
  - **What:** an `if` test — `if (raw_cause & 0x04000000)`. When the condition holds it runs `flags |= RESET_FLAG_RESET_PIN;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001e46** [taken-only] — `cmp r3, #0x50` then `bne`: taken when r3 != constant 0x50. r3 = computed (ands r4). MISSING direction (taken-only) needs r3 == constant 0x50.
  - rebuilt C (system.c:173): `if ((flags & (RESET_FLAG_HIBERNATE | RESET_FLAG_WATCHDOG)) ==`
  - **What:** an `if` test — `if ((flags & (RESET_FLAG_HIBERNATE | RESET_FLAG_WATCHDOG)) ==`. When the condition holds it runs `(RESET_FLAG_HIBERNATE | RESET_FLAG_WATCHDOG)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08001e6c** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (orrs r0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (system.c:233): `if (reason || info || exception) {`
  - **What:** an `if` test — `if (reason || info || exception) {`. When the condition holds it runs `panic_set_reason(reason, info, exception);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08001e70** [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (uxtb r2). MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (system.c:233): `if (reason || info || exception) {`
  - **What:** an `if` test — `if (reason || info || exception) {`. When the condition holds it runs `panic_set_reason(reason, info, exception);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011db4** (RW mirror) [nottaken-only] — `tst r0, r1` then `beq`: tests bits of r0 (= word [r3+0] (a struct/buffer field)) against mask r1. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (system.c:204 (discriminator 1)): `while (!(STM32_RCC_CSR & (1 << 1)))`
  - **What:** a loop condition — `while (!(STM32_RCC_CSR & (1 << 1)))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011dc4** (RW mirror) [taken-only] — `cmp r0, r4` then `beq`: taken when r0 == r4 (= computed (lsls r4, #8)). r0 = computed (ands r4). MISSING direction (taken-only) needs r0 != r4 (= computed (lsls r4, #8)).
  - rebuilt C (system.c:216): `if ((STM32_RCC_BDCR & 0x00018300) != 0x00008200) {`
  - **What:** an `if` test — `if ((STM32_RCC_BDCR & 0x00018300) != 0x00008200) {`. When the condition holds it runs `STM32_RCC_BDCR |= 0x00010000;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011e0c** (RW mirror) [nottaken-only] — `lsls r2, r3, #0x14` sets flags from a shifted value (bit test) then `bmi`. operand = function argument r2. MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (system.c:132): `flags &= ~CONSOLE_BIT_MASK;`
  - **What:** a conditional derived from this statement — `flags &= ~CONSOLE_BIT_MASK;`. When the condition holds it runs `STM32_RCC_CSR |= 1 << 24;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011e2c** (RW mirror) [taken-only] — `tst r6, r3` then `beq`: tests bits of r6 (= register r6) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (system.c:156): `if (raw_cause & 0x04000000)`
  - **What:** an `if` test — `if (raw_cause & 0x04000000)`. When the condition holds it runs `flags |= RESET_FLAG_RESET_PIN;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011e46** (RW mirror) [taken-only] — `cmp r3, #0x50` then `bne`: taken when r3 != constant 0x50. r3 = computed (ands r4). MISSING direction (taken-only) needs r3 == constant 0x50.
  - rebuilt C (system.c:173): `if ((flags & (RESET_FLAG_HIBERNATE | RESET_FLAG_WATCHDOG)) ==`
  - **What:** an `if` test — `if ((flags & (RESET_FLAG_HIBERNATE | RESET_FLAG_WATCHDOG)) ==`. When the condition holds it runs `(RESET_FLAG_HIBERNATE | RESET_FLAG_WATCHDOG)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08011e6c** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (orrs r0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (system.c:233): `if (reason || info || exception) {`
  - **What:** an `if` test — `if (reason || info || exception) {`. When the condition holds it runs `panic_set_reason(reason, info, exception);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011e70** (RW mirror) [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (uxtb r2). MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (system.c:233): `if (reason || info || exception) {`
  - **What:** an `if` test — `if (reason || info || exception) {`. When the condition holds it runs `panic_set_reason(reason, info, exception);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08001f08  `system_set_vbnvcontext`  (conf:approx)
**Signature:** `int system_set_vbnvcontext(const uint8_t *block)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/system.c:361  | rebuilt @ 0x8001df0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08001f1e** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r4, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (system.c:371): `if (err)`
  - **What:** an `if` test — `if (err)`. When the condition holds it runs `return err;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011f1e** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r4, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (system.c:371): `if (err)`
  - **What:** an `if` test — `if (err)`. When the condition holds it runs `return err;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08001fcc  `uart_tx_flush`  (conf:high)
**Signature:** `void uart_tx_flush(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/uart.c:88  | rebuilt @ 0x8001ed8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08001fd4** [nottaken-only] — `tst r2, r3` then `beq`: tests bits of r2 (= word [r1+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (uart.c:88 (discriminator 1)): `while (!(STM32_USART_SR(UARTN_BASE) & STM32_USART_SR_TXE))`
  - **What:** a loop condition — `while (!(STM32_USART_SR(UARTN_BASE) & STM32_USART_SR_TXE))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08011fd4** (RW mirror) [nottaken-only] — `tst r2, r3` then `beq`: tests bits of r2 (= word [r1+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (uart.c:88 (discriminator 1)): `while (!(STM32_USART_SR(UARTN_BASE) & STM32_USART_SR_TXE))`
  - **What:** a loop condition — `while (!(STM32_USART_SR(UARTN_BASE) & STM32_USART_SR_TXE))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08001ffc  `uart_write_char`  (conf:high)
**Signature:** `void uart_write_char(char c)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/uart.c:146  | rebuilt @ 0x8001f4c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08002004** [nottaken-only] — `tst r2, r3` then `beq`: tests bits of r2 (= word [r1+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (uart.c:146 (discriminator 1)): `while (!uart_tx_ready())`
  - **What:** a loop condition — `while (!uart_tx_ready())`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012004** (RW mirror) [nottaken-only] — `tst r2, r3` then `beq`: tests bits of r2 (= word [r1+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (uart.c:146 (discriminator 1)): `while (!uart_tx_ready())`
  - **What:** a loop condition — `while (!uart_tx_ready())`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002020  `usart_tx_interrupt_handler`  (conf:approx)
**Signature:** `static void usart_tx_interrupt_handler(struct usart_config const *config)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usart_tx_interrupt.c:51  | rebuilt @ 0x80021e4 | 5 uncovered (0 unreached, 5 one-dir; 3 in RW mirror)

- **0x08002044** [taken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r5+4] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0.
  - rebuilt C (usart_tx_interrupt.c:59): `STM32_USART_TDR(base) = byte;`
  - **What:** a conditional derived from this statement — `STM32_USART_TDR(base) = byte;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002078** [taken-only] — flags from `orrs r2, r1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (usb-stm32f0.c:13): `STM32_USB_BCDR |= (1 << 15) /* DPPU */;`
  - **What:** a conditional derived from this statement — `STM32_USB_BCDR |= (1 << 15) /* DPPU */;`. When the condition holds it runs `void usb_disconnect(void)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012044** (RW mirror) [taken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r5+4] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0.
  - rebuilt C (usart_tx_interrupt.c:59): `STM32_USART_TDR(base) = byte;`
  - **What:** a conditional derived from this statement — `STM32_USART_TDR(base) = byte;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012052** (RW mirror) [nottaken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r5+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == constant 0.
  - rebuilt C (usart_tx_interrupt.c:69): `STM32_USART_CR1(base) |= STM32_USART_CR1_TXEIE;`
  - **What:** a conditional derived from this statement — `STM32_USART_CR1(base) |= STM32_USART_CR1_TXEIE;`. When the condition holds it runs `} else {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012078** (RW mirror) [taken-only] — flags from `orrs r2, r1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (usb-stm32f0.c:13): `STM32_USB_BCDR |= (1 << 15) /* DPPU */;`
  - **What:** a conditional derived from this statement — `STM32_USB_BCDR |= (1 << 15) /* DPPU */;`. When the condition holds it runs `void usb_disconnect(void)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08002130  `usart_variant_disable`  (conf:high)
**Signature:** `static void usart_variant_disable(struct usart_config const *config)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usart-stm32f0.c:45  | rebuilt @ 0x8002038 | 8 uncovered (6 unreached, 2 one-dir; 4 in RW mirror)

- **0x0800213a** [taken-only] — `cmp r4, #1` then `bls`: taken when r4 <=u constant 1. r4 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r4 >u constant 1.
  - rebuilt C (usart-stm32f0.c:52): `if ((index == 0) ||`
  - **What:** an `if` test — `if ((index == 0) ||`. When the condition holds it runs `(index == 1) ||`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800213e** [unreached] — `cmp r4, #2` then `bne`: taken when r4 != constant 2. r4 = word [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r4 != constant 2.
  - rebuilt C (usart-stm32f0.c:53): `(index == 1) ||`
  - **What:** a conditional derived from this statement — `(index == 1) ||`. When the condition holds it runs `(index == 2 && configs[3] == NULL) ||`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08002146** [unreached] — `cmp r4, #3` then `bne`: taken when r4 != constant 3. r4 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r4 != constant 3.
  - rebuilt C (usart-stm32f0.c:54 (discriminator 1)): `(index == 2 && configs[3] == NULL) ||`
  - **What:** a conditional derived from this statement — `(index == 2 && configs[3] == NULL) ||`. When the condition holds it runs `(index == 3 && configs[2] == NULL))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800214c** [unreached] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r5+8] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 0.
  - rebuilt C (usart-stm32f0.c:55): `(index == 3 && configs[2] == NULL))`
  - **What:** a conditional derived from this statement — `(index == 3 && configs[2] == NULL))`. When the condition holds it runs `task_disable_irq(config->hw->irq);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801213a** (RW mirror) [taken-only] — `cmp r4, #1` then `bls`: taken when r4 <=u constant 1. r4 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r4 >u constant 1.
  - rebuilt C (usart-stm32f0.c:52): `if ((index == 0) ||`
  - **What:** an `if` test — `if ((index == 0) ||`. When the condition holds it runs `(index == 1) ||`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801213e** (RW mirror) [unreached] — `cmp r4, #2` then `bne`: taken when r4 != constant 2. r4 = word [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r4 != constant 2.
  - rebuilt C (usart-stm32f0.c:53): `(index == 1) ||`
  - **What:** a conditional derived from this statement — `(index == 1) ||`. When the condition holds it runs `(index == 2 && configs[3] == NULL) ||`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012146** (RW mirror) [unreached] — `cmp r4, #3` then `bne`: taken when r4 != constant 3. r4 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r4 != constant 3.
  - rebuilt C (usart-stm32f0.c:54 (discriminator 1)): `(index == 2 && configs[3] == NULL) ||`
  - **What:** a conditional derived from this statement — `(index == 2 && configs[3] == NULL) ||`. When the condition holds it runs `(index == 3 && configs[2] == NULL))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801214c** (RW mirror) [unreached] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r5+8] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 0.
  - rebuilt C (usart-stm32f0.c:55): `(index == 3 && configs[2] == NULL))`
  - **What:** a conditional derived from this statement — `(index == 3 && configs[2] == NULL))`. When the condition holds it runs `task_disable_irq(config->hw->irq);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080021f8  `usart_set_baud_f0_l`  (conf:high)
**Signature:** `void usart_set_baud_f0_l(struct usart_config const *config, int frequency_hz)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usart.c:76  | rebuilt @ 0x80020f0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08002212** [nottaken-only] — `cmp r0, #0xf` then `ble`: taken when r0 <= constant 0xf. r0 = computed (adds r1, r0). MISSING direction (nottaken-only) needs r0 <= constant 0xf.
  - rebuilt C (usart.c:80): `if (div / 16 > 0) {`
  - **What:** an `if` test — `if (div / 16 > 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012212** (RW mirror) [nottaken-only] — `cmp r0, #0xf` then `ble`: taken when r0 <= constant 0xf. r0 = computed (adds r1, r0). MISSING direction (nottaken-only) needs r0 <= constant 0xf.
  - rebuilt C (usart.c:80): `if (div / 16 > 0) {`
  - **What:** an `if` test — `if (div / 16 > 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002278  `usart_rx_interrupt_handler`  (conf:high)
**Signature:** `static void usart_rx_interrupt_handler(struct usart_config const *config)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usart_rx_interrupt-stm32f0.c:25  | rebuilt @ 0x8002170 | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x08002282** [taken-only] — `lsls r2, r2, #0x1a` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0x1c] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (usart_rx_interrupt-stm32f0.c:29): `if (status & STM32_USART_SR_RXNE) {`
  - **What:** an `if` test — `if (status & STM32_USART_SR_RXNE) {`. When the condition holds it runs `uint8_t byte = STM32_USART_RDR(base);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002296** [unreached] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r0+0x1c] (a struct/buffer field). MISSING direction (unreached) needs r0 != constant 0.
  - rebuilt C (usart_rx_interrupt-stm32f0.c:32): `if (!queue_add_unit(config->producer.queue, &byte))`
  - **What:** an `if` test — `if (!queue_add_unit(config->producer.queue, &byte))`. When the condition holds it runs `atomic_add(&config->state->rx_dropped, 1);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012282** (RW mirror) [taken-only] — `lsls r2, r2, #0x1a` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0x1c] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (usart_rx_interrupt-stm32f0.c:29): `if (status & STM32_USART_SR_RXNE) {`
  - **What:** an `if` test — `if (status & STM32_USART_SR_RXNE) {`. When the condition holds it runs `uint8_t byte = STM32_USART_RDR(base);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012296** (RW mirror) [unreached] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r0+0x1c] (a struct/buffer field). MISSING direction (unreached) needs r0 != constant 0.
  - rebuilt C (usart_rx_interrupt-stm32f0.c:32): `if (!queue_add_unit(config->producer.queue, &byte))`
  - **What:** an `if` test — `if (!queue_add_unit(config->producer.queue, &byte))`. When the condition holds it runs `atomic_add(&config->state->rx_dropped, 1);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080022b6  `usart_flush`  (conf:approx)
**Signature:** `static void usart_flush(struct consumer const *consumer)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usart_tx_interrupt.c:36  | rebuilt @ 0x80021ae | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080022ce** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usart_tx_interrupt.c:46 (discriminator 1)): `while (queue_count(consumer->queue))`
  - **What:** a loop condition — `while (queue_count(consumer->queue))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080122ce** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usart_tx_interrupt.c:46 (discriminator 1)): `while (queue_count(consumer->queue))`
  - **What:** a loop condition — `while (queue_count(consumer->queue))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x080022f0  `ep0_tx`  (conf:approx)
**Signature:** `static void ep0_tx(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb.c:204  | rebuilt @ 0x80025cc | 9 uncovered (2 unreached, 7 one-dir; 5 in RW mirror)

- **0x08002306** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r6+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb.c:207): `set_addr = 0;`
  - **What:** a conditional derived from this statement — `set_addr = 0;`. When the condition holds it runs `CPRINTF("SETAD %02x\n", STM32_USB_DADDR);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08002312** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r6+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb.c:208): `CPRINTF("SETAD %02x\n", STM32_USB_DADDR);`
  - **What:** a conditional derived from this statement — `CPRINTF("SETAD %02x\n", STM32_USB_DADDR);`. When the condition holds it runs `if (desc_ptr) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002330** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r6+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb.c:213): `memcpy_to_usbram(EP0_BUF_TX_SRAM_ADDR, desc_ptr, len);`
  - **What:** a conditional derived from this statement — `memcpy_to_usbram(EP0_BUF_TX_SRAM_ADDR, desc_ptr, len);`. When the condition holds it runs `btable_ep[0].tx_count = len;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002354** [unreached] — `cmp r2, r3` then `bhs`: taken when r2 >=u r3 (= word [r5+0x1c] (a struct/buffer field)). r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (unreached) needs r2 >=u r3 (= word [r5+0x1c] (a struct/buffer field)).
  - rebuilt C (usb.c:217): `STM32_TOGGLE_EP(0, EP_TX_MASK, EP_TX_VALID,`
  - **What:** a conditional derived from this statement — `STM32_TOGGLE_EP(0, EP_TX_MASK, EP_TX_VALID,`. When the condition holds it runs `desc_left ? 0 : EP_STATUS_OUT);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012300** (RW mirror) [nottaken-only] — `lsls r3, r3, #0x19` sets flags from a shifted value (bit test) then `bmi`. operand = word [r3+0x1c] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (usb.c:206): `STM32_USB_DADDR = set_addr | 0x80;`
  - **What:** a conditional derived from this statement — `STM32_USB_DADDR = set_addr | 0x80;`. When the condition holds it runs `set_addr = 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012306** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r6+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb.c:207): `set_addr = 0;`
  - **What:** a conditional derived from this statement — `set_addr = 0;`. When the condition holds it runs `CPRINTF("SETAD %02x\n", STM32_USB_DADDR);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012312** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r6+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb.c:208): `CPRINTF("SETAD %02x\n", STM32_USB_DADDR);`
  - **What:** a conditional derived from this statement — `CPRINTF("SETAD %02x\n", STM32_USB_DADDR);`. When the condition holds it runs `if (desc_ptr) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012330** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r6+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb.c:213): `memcpy_to_usbram(EP0_BUF_TX_SRAM_ADDR, desc_ptr, len);`
  - **What:** a conditional derived from this statement — `memcpy_to_usbram(EP0_BUF_TX_SRAM_ADDR, desc_ptr, len);`. When the condition holds it runs `btable_ep[0].tx_count = len;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012354** (RW mirror) [unreached] — `cmp r2, r3` then `bhs`: taken when r2 >=u r3 (= word [r5+0x1c] (a struct/buffer field)). r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (unreached) needs r2 >=u r3 (= word [r5+0x1c] (a struct/buffer field)).
  - rebuilt C (usb.c:217): `STM32_TOGGLE_EP(0, EP_TX_MASK, EP_TX_VALID,`
  - **What:** a conditional derived from this statement — `STM32_TOGGLE_EP(0, EP_TX_MASK, EP_TX_VALID,`. When the condition holds it runs `desc_left ? 0 : EP_STATUS_OUT);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080023dc  `usb_flush`  (conf:approx)
**Signature:** `static void usb_flush(struct consumer const *consumer)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb-stream.c:81  | rebuilt @ 0x8002274 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x080023f4** [nottaken-only] — `cmp r2, #0x30` then `beq`: taken when r2 == constant 0x30. r2 = computed (ands r1). MISSING direction (nottaken-only) needs r2 == constant 0x30.
  - rebuilt C (usb-stream.c:85 (discriminator 3)): `while (tx_valid(config) || queue_count(consumer->queue))`
  - **What:** a loop condition — `while (tx_valid(config) || queue_count(consumer->queue))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080023fe** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usb-stream.c:85 (discriminator 2)): `while (tx_valid(config) || queue_count(consumer->queue))`
  - **What:** a loop condition — `while (tx_valid(config) || queue_count(consumer->queue))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080123f4** (RW mirror) [nottaken-only] — `cmp r2, #0x30` then `beq`: taken when r2 == constant 0x30. r2 = computed (ands r1). MISSING direction (nottaken-only) needs r2 == constant 0x30.
  - rebuilt C (usb-stream.c:85 (discriminator 3)): `while (tx_valid(config) || queue_count(consumer->queue))`
  - **What:** a loop condition — `while (tx_valid(config) || queue_count(consumer->queue))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080123fe** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usb-stream.c:85 (discriminator 2)): `while (tx_valid(config) || queue_count(consumer->queue))`
  - **What:** a loop condition — `while (tx_valid(config) || queue_count(consumer->queue))`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002408  `usb_stream_deferred`  (conf:approx)
**Signature:** `void usb_stream_deferred(struct usb_stream_config const *config)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb-stream.c:99  | rebuilt @ 0x80022a0 | 9 uncovered (0 unreached, 9 one-dir; 5 in RW mirror)

- **0x0800241c** [nottaken-only] — `cmp r2, r5` then `beq`: taken when r2 == r5 (= computed (movs #0x30)). r2 = computed (ands r5). MISSING direction (nottaken-only) needs r2 == r5 (= computed (movs #0x30)).
  - rebuilt C (usb-stream.c:100): `if (!tx_valid(config) && tx_write(config))`
  - **What:** an `if` test — `if (!tx_valid(config) && tx_write(config))`. When the condition holds it runs `STM32_TOGGLE_EP(config->endpoint, EP_TX_MASK, EP_TX_VALID, 0);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800243c** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r0+0x1c] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb-stream.c:100): `if (!tx_valid(config) && tx_write(config))`
  - **What:** an `if` test — `if (!tx_valid(config) && tx_write(config))`. When the condition holds it runs `STM32_TOGGLE_EP(config->endpoint, EP_TX_MASK, EP_TX_VALID, 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002484** [nottaken-only] — `cmp r7, r0` then `bhs`: taken when r7 >=u r0 (= word [r4+0x24] (a struct/buffer field)). r7 = computed (lsrs r7, #0x16). MISSING direction (nottaken-only) needs r7 >=u r0 (= word [r4+0x24] (a struct/buffer field)).
  - rebuilt C (usb-stream.c:27): `if (count >= queue_space(config->producer.queue))`
  - **What:** an `if` test — `if (count >= queue_space(config->producer.queue))`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08002494** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r4+0x24] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb-stream.c:103): `if (!rx_valid(config) && !rx_disabled(config) && rx_read(config))`
  - **What:** an `if` test — `if (!rx_valid(config) && !rx_disabled(config) && rx_read(config))`. When the condition holds it runs `STM32_TOGGLE_EP(config->endpoint, EP_RX_MASK, EP_RX_VALID, 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801241c** (RW mirror) [nottaken-only] — `cmp r2, r5` then `beq`: taken when r2 == r5 (= computed (movs #0x30)). r2 = computed (ands r5). MISSING direction (nottaken-only) needs r2 == r5 (= computed (movs #0x30)).
  - rebuilt C (usb-stream.c:100): `if (!tx_valid(config) && tx_write(config))`
  - **What:** an `if` test — `if (!tx_valid(config) && tx_write(config))`. When the condition holds it runs `STM32_TOGGLE_EP(config->endpoint, EP_TX_MASK, EP_TX_VALID, 0);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801243c** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r0+0x1c] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb-stream.c:100): `if (!tx_valid(config) && tx_write(config))`
  - **What:** an `if` test — `if (!tx_valid(config) && tx_write(config))`. When the condition holds it runs `STM32_TOGGLE_EP(config->endpoint, EP_TX_MASK, EP_TX_VALID, 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012462** (RW mirror) [nottaken-only] — `cmp r2, r5` then `beq`: taken when r2 == r5 (= computed (lsls r5, #6)). r2 = computed (ands r5). MISSING direction (nottaken-only) needs r2 == r5 (= computed (lsls r5, #6)).
  - rebuilt C (usb-stream.c:103): `if (!rx_valid(config) && !rx_disabled(config) && rx_read(config))`
  - **What:** an `if` test — `if (!rx_valid(config) && !rx_disabled(config) && rx_read(config))`. When the condition holds it runs `STM32_TOGGLE_EP(config->endpoint, EP_RX_MASK, EP_RX_VALID, 0);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012484** (RW mirror) [nottaken-only] — `cmp r7, r0` then `bhs`: taken when r7 >=u r0 (= word [r4+0x24] (a struct/buffer field)). r7 = computed (lsrs r7, #0x16). MISSING direction (nottaken-only) needs r7 >=u r0 (= word [r4+0x24] (a struct/buffer field)).
  - rebuilt C (usb-stream.c:27): `if (count >= queue_space(config->producer.queue))`
  - **What:** an `if` test — `if (count >= queue_space(config->producer.queue))`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012494** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r4+0x24] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb-stream.c:103): `if (!rx_valid(config) && !rx_disabled(config) && rx_read(config))`
  - **What:** an `if` test — `if (!rx_valid(config) && !rx_disabled(config) && rx_read(config))`. When the condition holds it runs `STM32_TOGGLE_EP(config->endpoint, EP_RX_MASK, EP_RX_VALID, 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800250c  `usb_stream_reset`  (conf:approx)
**Signature:** `void usb_stream_reset(struct usb_stream_config const *config)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb-stream.c:130  | rebuilt @ 0x8002388 | 3 uncovered (0 unreached, 3 one-dir; 1 in RW mirror)

- **0x08002530** [nottaken-only] — `cmp r3, #0x3f` then `bhi`: taken when r3 >u constant 0x3f. r3 = word [r0+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u constant 0x3f.
  - rebuilt C (usb-stream.c:123): `if (bytes < 64)`
  - **What:** an `if` test — `if (bytes < 64)`. When the condition holds it runs `return bytes << 9;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800255c** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb-stream.c:141): `STM32_USB_EP(i) = ((i <<  0) | /* Endpoint Addr*/`
  - **What:** a conditional derived from this statement — `STM32_USB_EP(i) = ((i <<  0) | /* Endpoint Addr*/`. When the condition holds it runs `(2 <<  4) | /* TX NAK */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012530** (RW mirror) [nottaken-only] — `cmp r3, #0x3f` then `bhi`: taken when r3 >u constant 0x3f. r3 = word [r0+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u constant 0x3f.
  - rebuilt C (usb-stream.c:123): `if (bytes < 64)`
  - **What:** an `if` test — `if (bytes < 64)`. When the condition holds it runs `return bytes << 9;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800260c  `usb_interrupt`  (conf:approx)
**Signature:** `void usb_interrupt(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb.c:254  | rebuilt @ 0x800248c | 5 uncovered (3 unreached, 2 one-dir; 5 in RW mirror)

- **0x08012616** (RW mirror) [taken-only] — `lsls r3, r4, #0x15` sets flags from a shifted value (bit test) then `bpl`. operand = function argument r3. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (usb.c:257): `if ((status & (1 << 10)))`
  - **What:** an `if` test — `if ((status & (1 << 10)))`. When the condition holds it runs `usb_reset();`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012624** (RW mirror) [unreached] — `cmp r6, #0x10` then `bne`: taken when r6 != constant 0x10. r6 = computed (adds #4). MISSING direction (unreached) needs r6 != constant 0x10.
  - rebuilt C (usb.c:242): `for (ep = 0; ep < USB_EP_COUNT; ep++)`
  - **What:** a loop condition — `for (ep = 0; ep < USB_EP_COUNT; ep++)`. When the condition holds it runs `usb_ep_reset[ep]();`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801263e** (RW mirror) [taken-only] — `cmp r3, #0` then `bge`: taken when r3 >= constant 0. r3 = a global/constant (pc-relative load). MISSING direction (taken-only) needs r3 < constant 0.
  - rebuilt C (usb.c:260): `if (status & (1 << 15)) {`
  - **What:** an `if` test — `if (status & (1 << 15)) {`. When the condition holds it runs `int ep = status & 0x000f;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012646** (RW mirror) [unreached] — `cmp r3, #3` then `bhi`: taken when r3 >u constant 3. r3 = computed (ands r4). MISSING direction (unreached) needs r3 >u constant 3.
  - rebuilt C (usb.c:262): `if (ep < USB_EP_COUNT) {`
  - **What:** an `if` test — `if (ep < USB_EP_COUNT) {`. When the condition holds it runs `if (status & 0x0010)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801264c** (RW mirror) [unreached] — `lsls r2, r4, #0x1b` sets flags from a shifted value (bit test) then `bpl`. operand = halfword [r3+0] (a struct/buffer field). MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb.c:263): `if (status & 0x0010)`
  - **What:** an `if` test — `if (status & 0x0010)`. When the condition holds it runs `usb_ep_rx[ep]();`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080026f0  `memcpy_to_usbram`  (conf:high)
**Signature:** `void *memcpy_to_usbram(void *dest, const void *src, size_t n)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb.c:350  | rebuilt @ 0x8002570 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08002700** [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = function argument r2. MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (usb.c:359 (discriminator 1)): `if (unaligned && n) {`
  - **What:** an `if` test — `if (unaligned && n) {`. When the condition holds it runs `n--;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012700** (RW mirror) [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = function argument r2. MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (usb.c:359 (discriminator 1)): `if (unaligned && n) {`
  - **What:** an `if` test — `if (unaligned && n) {`. When the condition holds it runs `n--;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080027e8  `ep0_rx`  (conf:approx)
**Signature:** `static void ep0_rx(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb.c:99  | rebuilt @ 0x8002668 | 15 uncovered (9 unreached, 6 one-dir; 15 in RW mirror)

- **0x080127fe** (RW mirror) [taken-only] — `cmp r4, #1` then `bne`: taken when r4 != constant 1. r4 = computed (ands r3). MISSING direction (taken-only) needs r4 == constant 1.
  - rebuilt C (usb.c:106): `if ((req & USB_RECIP_MASK) == USB_RECIP_INTERFACE) {`
  - **What:** an `if` test — `if ((req & USB_RECIP_MASK) == USB_RECIP_INTERFACE) {`. When the condition holds it runs `uint8_t iface = ep0_buf_rx[2] & 0xff;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012808** (RW mirror) [unreached] — `cmp r3, #3` then `bls`: taken when r3 <=u constant 3. r3 = computed (uxtb r3). MISSING direction (unreached) needs r3 <=u constant 3.
  - rebuilt C (usb.c:108): `if (iface < USB_IFACE_COUNT &&`
  - **What:** an `if` test — `if (iface < USB_IFACE_COUNT &&`. When the condition holds it runs `usb_iface_request[iface](ep0_buf_rx, ep0_buf_tx))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801281c** (RW mirror) [unreached] — `cmp r0, r6` then `bne`: taken when r0 != r6 (= a value carried in from a preceding basic block). r0 = computed (adds #0x40). MISSING direction (unreached) needs r0 != r6 (= a value carried in from a preceding basic block).
  - rebuilt C (usb.c:108 (discriminator 1)): `if (iface < USB_IFACE_COUNT &&`
  - **What:** an `if` test — `if (iface < USB_IFACE_COUNT &&`. When the condition holds it runs `usb_iface_request[iface](ep0_buf_rx, ep0_buf_tx))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012828** (RW mirror) [taken-only] — `cmp r3, r4` then `bne`: taken when r3 != r4 (= computed (lsls r4, #3)). r3 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r3 == r4 (= computed (lsls r4, #3)).
  - rebuilt C (usb.c:115): `if (req == (USB_DIR_IN | (USB_REQ_GET_DESCRIPTOR << 8))) {`
  - **What:** an `if` test — `if (req == (USB_DIR_IN | (USB_REQ_GET_DESCRIPTOR << 8))) {`. When the condition holds it runs `uint8_t type = ep0_buf_rx[1] >> 8;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012832** (RW mirror) [unreached] — `cmp r6, #2` then `beq`: taken when r6 == constant 2. r6 = computed (lsrs r3, #8). MISSING direction (unreached) needs r6 == constant 2.
  - rebuilt C (usb.c:121): `switch (type) {`
  - **What:** a `switch` dispatch on the value — `switch (type) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012836** (RW mirror) [unreached] — `cmp r6, #3` then `beq`: taken when r6 == constant 3. r6 = computed (lsrs r3, #8). MISSING direction (unreached) needs r6 == constant 3.
  - rebuilt C (usb.c:121): `switch (type) {`
  - **What:** a `switch` dispatch on the value — `switch (type) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801283a** (RW mirror) [unreached] — `cmp r6, #1` then `bne`: taken when r6 != constant 1. r6 = computed (lsrs r3, #8). MISSING direction (unreached) needs r6 != constant 1.
  - rebuilt C (usb.c:121): `switch (type) {`
  - **What:** a `switch` dispatch on the value — `switch (type) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801284e** (RW mirror) [unreached] — `cmp r3, #5` then `bhi`: taken when r3 >u constant 5. r3 = computed (uxtb r3). MISSING direction (unreached) needs r3 >u constant 5.
  - rebuilt C (usb.c:137): `if (idx >= USB_STR_COUNT)`
  - **What:** an `if` test — `if (idx >= USB_STR_COUNT)`. When the condition holds it runs `goto unknown_req;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012860** (RW mirror) [unreached] — `cmp r4, r3` then `ble`: taken when r4 <= r3 (= halfword [r3+0x3e] (a struct/buffer field)). r4 = byte [r1+0] (a struct/buffer field). MISSING direction (unreached) needs r4 <= r3 (= halfword [r3+0x3e] (a struct/buffer field)).
  - rebuilt C (usb.c:150): `len = MIN(ep0_buf_rx[3], len);`
  - **What:** a conditional derived from this statement — `len = MIN(ep0_buf_rx[3], len);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012866** (RW mirror) [unreached] — `cmp r4, #0x3f` then `ble`: taken when r4 <= constant 0x3f. r4 = computed (adds r3, #0). MISSING direction (unreached) needs r4 <= constant 0x3f.
  - rebuilt C (usb.c:155): `if (len >= USB_MAX_PACKET_SIZE) {`
  - **What:** an `if` test — `if (len >= USB_MAX_PACKET_SIZE) {`. When the condition holds it runs `desc_left = len - USB_MAX_PACKET_SIZE;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012882** (RW mirror) [unreached] — `cmp r6, #2` then `bne`: taken when r6 != constant 2. r6 = register r6. MISSING direction (unreached) needs r6 != constant 2.
  - rebuilt C (usb.c:161): `if (type == USB_DT_CONFIGURATION)`
  - **What:** an `if` test — `if (type == USB_DT_CONFIGURATION)`. When the condition holds it runs `ep0_buf_tx[1] = USB_DESC_SIZE;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080128aa** (RW mirror) [taken-only] — `cmp r3, #0x80` then `bne`: taken when r3 != constant 0x80. r3 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r3 == constant 0x80.
  - rebuilt C (usb.c:168): `} else if (req == (USB_DIR_IN | (USB_REQ_GET_STATUS << 8))) {`
  - **What:** an `if` test — `} else if (req == (USB_DIR_IN | (USB_REQ_GET_STATUS << 8))) {`. When the condition holds it runs `uint16_t zero = 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080128da** (RW mirror) [nottaken-only] — flags from `ands r4, r2` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (usb.c:175): `} else if ((req & 0xff) == USB_DIR_OUT) {`
  - **What:** an `if` test — `} else if ((req & 0xff) == USB_DIR_OUT) {`. When the condition holds it runs `switch (req >> 8) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080128e0** (RW mirror) [nottaken-only] — `cmp r3, #5` then `beq`: taken when r3 == constant 5. r3 = computed (lsrs r3, #8). MISSING direction (nottaken-only) needs r3 == constant 5.
  - rebuilt C (usb.c:176): `switch (req >> 8) {`
  - **What:** a `switch` dispatch on the value — `switch (req >> 8) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080128e4** (RW mirror) [nottaken-only] — `cmp r3, #9` then `beq`: taken when r3 == constant 9. r3 = computed (lsrs r3, #8). MISSING direction (nottaken-only) needs r3 == constant 9.
  - rebuilt C (usb.c:176): `switch (req >> 8) {`
  - **What:** a `switch` dispatch on the value — `switch (req >> 8) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002948  `memcpy_from_usbram`  (conf:approx)
**Signature:** `void *memcpy_from_usbram(void *dest, const void *src, size_t n)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb.c:380  | rebuilt @ 0x80027c8 | 3 uncovered (0 unreached, 3 one-dir; 1 in RW mirror)

- **0x0800295a** [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = function argument r2. MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (usb.c:386 (discriminator 1)): `if (unaligned && n) {`
  - **What:** an `if` test — `if (unaligned && n) {`. When the condition holds it runs `n--;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002972** [taken-only] — `cmp r3, r7` then `beq`: taken when r3 == r7 (= computed (lsls r7, #1)). r3 = computed (movs #0). MISSING direction (taken-only) needs r3 != r7 (= computed (lsls r7, #1)).
  - rebuilt C (usb.c:393): `for (i = 0; i < n / 2; i++) {`
  - **What:** a loop condition — `for (i = 0; i < n / 2; i++) {`. When the condition holds it runs `usb_uint value = *s++;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801295a** (RW mirror) [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = function argument r2. MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (usb.c:386 (discriminator 1)): `if (unaligned && n) {`
  - **What:** an `if` test — `if (unaligned && n) {`. When the condition holds it runs `n--;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08002a10  `usb_wait_console`  (conf:approx)
**Signature:** `static int usb_wait_console(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_console.c:147  | rebuilt @ 0x8002898 | 5 uncovered (1 unreached, 4 one-dir; 3 in RW mirror)

- **0x08002a6a** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usb_console.c:165 (discriminator 1)): `if (timestamp_expired(deadline, NULL) ||`
  - **What:** an `if` test — `if (timestamp_expired(deadline, NULL) ||`. When the condition holds it runs `in_interrupt_context()) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08002a88** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (usb_console.c:164 (discriminator 1)): `while (usb_console_tx_valid() || !is_reset) {`
  - **What:** a loop condition — `while (usb_console_tx_valid() || !is_reset) {`. When the condition holds it runs `if (timestamp_expired(deadline, NULL) ||`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012a4a** (RW mirror) [nottaken-only] — `cmp r3, #0x30` then `bne`: taken when r3 != constant 0x30. r3 = computed (ands r2). MISSING direction (nottaken-only) needs r3 != constant 0x30.
  - rebuilt C (usb_console.c:164): `while (usb_console_tx_valid() || !is_reset) {`
  - **What:** a loop condition — `while (usb_console_tx_valid() || !is_reset) {`. When the condition holds it runs `if (timestamp_expired(deadline, NULL) ||`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012a6a** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usb_console.c:165 (discriminator 1)): `if (timestamp_expired(deadline, NULL) ||`
  - **What:** an `if` test — `if (timestamp_expired(deadline, NULL) ||`. When the condition holds it runs `in_interrupt_context()) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012a88** (RW mirror) [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (usb_console.c:164 (discriminator 1)): `while (usb_console_tx_valid() || !is_reset) {`
  - **What:** a loop condition — `while (usb_console_tx_valid() || !is_reset) {`. When the condition holds it runs `if (timestamp_expired(deadline, NULL) ||`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08002acc  `con_ep_rx`  (conf:approx)
**Signature:** `static void con_ep_rx(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_console.c:73  | rebuilt @ 0x8002950 | 6 uncovered (4 unreached, 2 one-dir; 3 in RW mirror)

- **0x08002ae0** [taken-only] — `cmp r2, r3` then `bge`: taken when r2 >= r3 (= computed (lsrs r3, #0x16)). r2 = computed (movs #0). MISSING direction (taken-only) needs r2 < r3 (= computed (lsrs r3, #0x16)).
  - rebuilt C (usb_console.c:75 (discriminator 1)): `for (i = 0; i < (btable_ep[USB_EP_CONSOLE].rx_count & 0x3ff); i++) {`
  - **What:** a loop condition — `for (i = 0; i < (btable_ep[USB_EP_CONSOLE].rx_count & 0x3ff); i++) {`. When the condition holds it runs `int rx_buf_next = RX_BUF_NEXT(rx_buf_head);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002aee** [unreached] — `cmp r4, r3` then `beq`: taken when r4 == r3 (= word [r1+8] (a struct/buffer field)). r4 = computed (ands r5). MISSING direction (unreached) needs r4 == r3 (= word [r1+8] (a struct/buffer field)).
  - rebuilt C (usb_console.c:77): `if (rx_buf_next != rx_buf_tail) {`
  - **What:** an `if` test — `if (rx_buf_next != rx_buf_tail) {`. When the condition holds it runs `rx_buf[rx_buf_head] = ((i & 1) ?`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08002afc** [unreached] — `lsls r6, r2, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = register r6. MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_console.c:79 (discriminator 1)): `(ep_buf_rx[i >> 1] >> 8) :`
  - **What:** a conditional derived from this statement — `(ep_buf_rx[i >> 1] >> 8) :`. When the condition holds it runs `(ep_buf_rx[i >> 1] & 0xff));`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012ae0** (RW mirror) [taken-only] — `cmp r2, r3` then `bge`: taken when r2 >= r3 (= computed (lsrs r3, #0x16)). r2 = computed (movs #0). MISSING direction (taken-only) needs r2 < r3 (= computed (lsrs r3, #0x16)).
  - rebuilt C (usb_console.c:75 (discriminator 1)): `for (i = 0; i < (btable_ep[USB_EP_CONSOLE].rx_count & 0x3ff); i++) {`
  - **What:** a loop condition — `for (i = 0; i < (btable_ep[USB_EP_CONSOLE].rx_count & 0x3ff); i++) {`. When the condition holds it runs `int rx_buf_next = RX_BUF_NEXT(rx_buf_head);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012aee** (RW mirror) [unreached] — `cmp r4, r3` then `beq`: taken when r4 == r3 (= word [r1+8] (a struct/buffer field)). r4 = computed (ands r5). MISSING direction (unreached) needs r4 == r3 (= word [r1+8] (a struct/buffer field)).
  - rebuilt C (usb_console.c:77): `if (rx_buf_next != rx_buf_tail) {`
  - **What:** an `if` test — `if (rx_buf_next != rx_buf_tail) {`. When the condition holds it runs `rx_buf[rx_buf_head] = ((i & 1) ?`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012afc** (RW mirror) [unreached] — `lsls r6, r2, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = register r6. MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_console.c:79 (discriminator 1)): `(ep_buf_rx[i >> 1] >> 8) :`
  - **What:** a conditional derived from this statement — `(ep_buf_rx[i >> 1] >> 8) :`. When the condition holds it runs `(ep_buf_rx[i >> 1] & 0xff));`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08002b38  `ep_reset`  (conf:high)
**Signature:** `static void ep_reset(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_console.c:94  | rebuilt @ 0x80029c4 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08002b5a** [nottaken-only] — `cmp r2, r1` then `bne`: taken when r2 != r1 (= computed (movs #0)). r2 = word [r3+0x4c] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r1 (= computed (movs #0)).
  - rebuilt C (usb_console.c:101): `STM32_USB_EP(USB_EP_CONSOLE) = (USB_EP_CONSOLE | /* Endpoint Addr */`
  - **What:** a conditional derived from this statement — `STM32_USB_EP(USB_EP_CONSOLE) = (USB_EP_CONSOLE | /* Endpoint Addr */`. When the condition holds it runs `(2 << 4)       | /* TX NAK        */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012b5a** (RW mirror) [nottaken-only] — `cmp r2, r1` then `bne`: taken when r2 != r1 (= computed (movs #0)). r2 = word [r3+0x4c] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r1 (= computed (movs #0)).
  - rebuilt C (usb_console.c:101): `STM32_USB_EP(USB_EP_CONSOLE) = (USB_EP_CONSOLE | /* Endpoint Addr */`
  - **What:** a conditional derived from this statement — `STM32_USB_EP(USB_EP_CONSOLE) = (USB_EP_CONSOLE | /* Endpoint Addr */`. When the condition holds it runs `(2 << 4)       | /* TX NAK        */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002b8c  `usb_getc`  (conf:high)
**Signature:** `int usb_getc(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_console.c:191  | rebuilt @ 0x8002a18 | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x08002b94** [taken-only] — `cmp r1, r2` then `beq`: taken when r1 == r2 (= word [r3+4] (a struct/buffer field)). r1 = word [r3+8] (a struct/buffer field). MISSING direction (taken-only) needs r1 != r2 (= word [r3+4] (a struct/buffer field)).
  - rebuilt C (usb_console.c:191): `if (rx_buf_tail == rx_buf_head)`
  - **What:** an `if` test — `if (rx_buf_tail == rx_buf_head)`. When the condition holds it runs `return -1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002b9c** [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (usb_console.c:194): `if (!is_enabled)`
  - **What:** an `if` test — `if (!is_enabled)`. When the condition holds it runs `return -1;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012b94** (RW mirror) [taken-only] — `cmp r1, r2` then `beq`: taken when r1 == r2 (= word [r3+4] (a struct/buffer field)). r1 = word [r3+8] (a struct/buffer field). MISSING direction (taken-only) needs r1 != r2 (= word [r3+4] (a struct/buffer field)).
  - rebuilt C (usb_console.c:191): `if (rx_buf_tail == rx_buf_head)`
  - **What:** an `if` test — `if (rx_buf_tail == rx_buf_head)`. When the condition holds it runs `return -1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012b9c** (RW mirror) [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (usb_console.c:194): `if (!is_enabled)`
  - **What:** an `if` test — `if (!is_enabled)`. When the condition holds it runs `return -1;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08002bc0  `usb_putc`  (conf:approx)
**Signature:** `int usb_putc(int c)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_console.c:203  | rebuilt @ 0x8002a4c | 1 uncovered (0 unreached, 1 one-dir; 0 in RW mirror)

- **0x08002bce** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usb_console.c:208): `if (ret)`
  - **What:** an `if` test — `if (ret)`. When the condition holds it runs `return ret;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002be4  `usb_puts`  (conf:high)
**Signature:** `int usb_puts(const char *outstr)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_console.c:218  | rebuilt @ 0x8002a70 | 3 uncovered (0 unreached, 3 one-dir; 1 in RW mirror)

- **0x08002bf2** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usb_console.c:223): `if (ret)`
  - **What:** an `if` test — `if (ret)`. When the condition holds it runs `return ret;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08002c04** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb_console.c:228): `if (__tx_char(&tx_idx, *outstr++) != 0)`
  - **What:** an `if` test — `if (__tx_char(&tx_idx, *outstr++) != 0)`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012bf2** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (usb_console.c:223): `if (ret)`
  - **What:** an `if` test — `if (ret)`. When the condition holds it runs `return ret;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002c64  `tx_dma_done`  (conf:approx)
**Signature:** `static void tx_dma_done(void *data)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_pd_phy.c:288  | rebuilt @ 0x8002af0 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08002c78** [nottaken-only] — `tst r4, r3` then `bne`: tests bits of r4 (= word [r6+8] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (usb_pd_phy.c:295 (discriminator 1)): `while (spi->sr & STM32_SPI_SR_BSY)`
  - **What:** a loop condition — `while (spi->sr & STM32_SPI_SR_BSY)`. When the condition holds it runs `; /* wait for BSY == 0 */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08002c80** [nottaken-only] — `tst r4, r3` then `bne`: tests bits of r4 (= word [r5+8] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (usb_pd_phy.c:299): `pd_phy[port].tim_tx->cr1 &= ~1;`
  - **What:** a conditional derived from this statement — `pd_phy[port].tim_tx->cr1 &= ~1;`. When the condition holds it runs `pd_tx_disable(port, polarity);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012c78** (RW mirror) [nottaken-only] — `tst r4, r3` then `bne`: tests bits of r4 (= word [r6+8] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (usb_pd_phy.c:295 (discriminator 1)): `while (spi->sr & STM32_SPI_SR_BSY)`
  - **What:** a loop condition — `while (spi->sr & STM32_SPI_SR_BSY)`. When the condition holds it runs `; /* wait for BSY == 0 */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012c80** (RW mirror) [nottaken-only] — `tst r4, r3` then `bne`: tests bits of r4 (= word [r5+8] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (usb_pd_phy.c:299): `pd_phy[port].tim_tx->cr1 &= ~1;`
  - **What:** a conditional derived from this statement — `pd_phy[port].tim_tx->cr1 &= ~1;`. When the condition holds it runs `pd_tx_disable(port, polarity);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08002d0c  `pd_dequeue_bits`  (conf:approx)
**Signature:** `int pd_dequeue_bits(int port, int off, int len, uint32_t *val)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_pd_phy.c:110  | rebuilt @ 0x8002b94 | 8 uncovered (0 unreached, 8 one-dir; 4 in RW mirror)

- **0x08002d90** [taken-only] — `lsls r3, r3, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0x10] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (usb_pd_phy.c:100): `if (dma_bytes_done(rx, PD_MAX_RAW_SIZE) < nb) {`
  - **What:** an `if` test — `if (dma_bytes_done(rx, PD_MAX_RAW_SIZE) < nb) {`. When the condition holds it runs `CPRINTS("PD TMOUT RX %d/%d",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002d9c** [taken-only] — `cmp r0, r5` then `bge`: taken when r0 >= r5 (= register r5). r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 < r5 (= register r5).
  - rebuilt C (usb_pd_phy.c:101): `CPRINTS("PD TMOUT RX %d/%d",`
  - **What:** a conditional derived from this statement — `CPRINTS("PD TMOUT RX %d/%d",`. When the condition holds it runs `dma_bytes_done(rx, PD_MAX_RAW_SIZE), nb);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002db6** [nottaken-only] — `cmp r5, #0` then `blt`: taken when r5 < constant 0. r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 < constant 0.
  - rebuilt C (usb_pd_phy.c:119): `cnt = samples[off] - samples[off-1];`
  - **What:** a conditional derived from this statement — `cnt = samples[off] - samples[off-1];`. When the condition holds it runs `if (!cnt || (cnt > 3*PERIOD))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08002de2** [taken-only] — `cmp r3, #6` then `bls`: taken when r3 <=u constant 6. r3 = computed (uxtb r3). MISSING direction (taken-only) needs r3 >u constant 6.
  - rebuilt C (usb_pd_phy.c:136): `pd_phy[port].d_last = (pd_phy[port].d_last >> 1)`
  - **What:** a conditional derived from this statement — `pd_phy[port].d_last = (pd_phy[port].d_last >> 1)`. When the condition holds it runs `| (cnt <= PERIOD_THRESHOLD ? 0x80000000 : 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012d90** (RW mirror) [taken-only] — `lsls r3, r3, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0x10] (a struct/buffer field). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (usb_pd_phy.c:100): `if (dma_bytes_done(rx, PD_MAX_RAW_SIZE) < nb) {`
  - **What:** an `if` test — `if (dma_bytes_done(rx, PD_MAX_RAW_SIZE) < nb) {`. When the condition holds it runs `CPRINTS("PD TMOUT RX %d/%d",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012d9c** (RW mirror) [taken-only] — `cmp r0, r5` then `bge`: taken when r0 >= r5 (= register r5). r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 < r5 (= register r5).
  - rebuilt C (usb_pd_phy.c:101): `CPRINTS("PD TMOUT RX %d/%d",`
  - **What:** a conditional derived from this statement — `CPRINTS("PD TMOUT RX %d/%d",`. When the condition holds it runs `dma_bytes_done(rx, PD_MAX_RAW_SIZE), nb);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012db6** (RW mirror) [nottaken-only] — `cmp r5, #0` then `blt`: taken when r5 < constant 0. r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 < constant 0.
  - rebuilt C (usb_pd_phy.c:119): `cnt = samples[off] - samples[off-1];`
  - **What:** a conditional derived from this statement — `cnt = samples[off] - samples[off-1];`. When the condition holds it runs `if (!cnt || (cnt > 3*PERIOD))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08012de2** (RW mirror) [taken-only] — `cmp r3, #6` then `bls`: taken when r3 <=u constant 6. r3 = computed (uxtb r3). MISSING direction (taken-only) needs r3 >u constant 6.
  - rebuilt C (usb_pd_phy.c:136): `pd_phy[port].d_last = (pd_phy[port].d_last >> 1)`
  - **What:** a conditional derived from this statement — `pd_phy[port].d_last = (pd_phy[port].d_last >> 1)`. When the condition holds it runs `| (cnt <= PERIOD_THRESHOLD ? 0x80000000 : 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08002e5c  `pd_find_preamble`  (conf:approx)
**Signature:** `int pd_find_preamble(int port)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_pd_phy.c:154  | rebuilt @ 0x8002ce8 | 8 uncovered (6 unreached, 2 one-dir; 4 in RW mirror)

- **0x08002e88** [taken-only] — `cmp r7, r6` then `bhs`: taken when r7 >=u r6 (= computed (adds r3, #1)). r7 = computed (subs r2, r7). MISSING direction (taken-only) needs r7 <u r6 (= computed (adds r3, #1)).
  - rebuilt C (usb_pd_phy.c:169 (discriminator 2)): `while ((PD_MAX_RAW_SIZE - rx->cndtr < bit + 1) &&`
  - **What:** a loop condition — `while ((PD_MAX_RAW_SIZE - rx->cndtr < bit + 1) &&`. When the condition holds it runs `!(pd_phy[port].tim_rx->sr & 4))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08002e90** [unreached] — `cmp r7, r6` then `bhs`: taken when r7 >=u r6 (= computed (adds r3, #1)). r7 = computed (subs r2, r7). MISSING direction (unreached) needs r7 >=u r6 (= computed (adds r3, #1)).
  - rebuilt C (usb_pd_phy.c:170 (discriminator 1)): `!(pd_phy[port].tim_rx->sr & 4))`
  - **What:** a conditional derived from this statement — `!(pd_phy[port].tim_rx->sr & 4))`. When the condition holds it runs `;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08002e98** [unreached] — `lsls r7, r7, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = word [r7+0x10] (a struct/buffer field). MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_pd_phy.c:172): `if (pd_phy[port].tim_rx->sr & 4) {`
  - **What:** an `if` test — `if (pd_phy[port].tim_rx->sr & 4) {`. When the condition holds it runs `CPRINTS("PD TMOUT RX %d/%d",`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08002ea0** [unreached] — `lsls r7, r7, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = word [r7+0x10] (a struct/buffer field). MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_pd_phy.c:173): `CPRINTS("PD TMOUT RX %d/%d",`
  - **What:** a conditional derived from this statement — `CPRINTS("PD TMOUT RX %d/%d",`. When the condition holds it runs `PD_MAX_RAW_SIZE - rx->cndtr, bit);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012e88** (RW mirror) [taken-only] — `cmp r7, r6` then `bhs`: taken when r7 >=u r6 (= computed (adds r3, #1)). r7 = computed (subs r2, r7). MISSING direction (taken-only) needs r7 <u r6 (= computed (adds r3, #1)).
  - rebuilt C (usb_pd_phy.c:169 (discriminator 2)): `while ((PD_MAX_RAW_SIZE - rx->cndtr < bit + 1) &&`
  - **What:** a loop condition — `while ((PD_MAX_RAW_SIZE - rx->cndtr < bit + 1) &&`. When the condition holds it runs `!(pd_phy[port].tim_rx->sr & 4))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08012e90** (RW mirror) [unreached] — `cmp r7, r6` then `bhs`: taken when r7 >=u r6 (= computed (adds r3, #1)). r7 = computed (subs r2, r7). MISSING direction (unreached) needs r7 >=u r6 (= computed (adds r3, #1)).
  - rebuilt C (usb_pd_phy.c:170 (discriminator 1)): `!(pd_phy[port].tim_rx->sr & 4))`
  - **What:** a conditional derived from this statement — `!(pd_phy[port].tim_rx->sr & 4))`. When the condition holds it runs `;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012e98** (RW mirror) [unreached] — `lsls r7, r7, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = word [r7+0x10] (a struct/buffer field). MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_pd_phy.c:172): `if (pd_phy[port].tim_rx->sr & 4) {`
  - **What:** an `if` test — `if (pd_phy[port].tim_rx->sr & 4) {`. When the condition holds it runs `CPRINTS("PD TMOUT RX %d/%d",`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08012ea0** (RW mirror) [unreached] — `lsls r7, r7, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = word [r7+0x10] (a struct/buffer field). MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_pd_phy.c:173): `CPRINTS("PD TMOUT RX %d/%d",`
  - **What:** a conditional derived from this statement — `CPRINTS("PD TMOUT RX %d/%d",`. When the condition holds it runs `PD_MAX_RAW_SIZE - rx->cndtr, bit);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08002fd8  `pd_write_last_edge`  (conf:approx)
**Signature:** `int pd_write_last_edge(int port, int bit_off)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_pd_phy.c:223  | rebuilt @ 0x8002e5c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800301e** [taken-only] — `cmp r2, #0x1f` then `bne`: taken when r2 != constant 0x1f. r2 = function argument r2. MISSING direction (taken-only) needs r2 == constant 0x1f.
  - rebuilt C (usb_pd_phy.c:234): `msg[word_idx++] |= 1 << bit_idx;`
  - **What:** a conditional derived from this statement — `msg[word_idx++] |= 1 << bit_idx;`. When the condition holds it runs `msg[word_idx] = 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801301e** (RW mirror) [taken-only] — `cmp r2, #0x1f` then `bne`: taken when r2 != constant 0x1f. r2 = function argument r2. MISSING direction (taken-only) needs r2 == constant 0x1f.
  - rebuilt C (usb_pd_phy.c:234): `msg[word_idx++] |= 1 << bit_idx;`
  - **What:** a conditional derived from this statement — `msg[word_idx++] |= 1 << bit_idx;`. When the condition holds it runs `msg[word_idx] = 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800336c  `pd_rx_handler`  (conf:approx)
**Signature:** `void pd_rx_handler(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_pd_phy.c:450  | rebuilt @ 0x80031ec | 4 uncovered (2 unreached, 2 one-dir; 3 in RW mirror)

- **0x080033b8** [nottaken-only] — `cmp r7, #0` then `bne`: taken when r7 != constant 0. r7 = word [r6+0x1c] (a struct/buffer field). MISSING direction (nottaken-only) needs r7 != constant 0.
  - rebuilt C (usb_pd_phy.c:478): `if ((rx_edge_ts[i][rx_edge_ts_idx[i]].val -`
  - **What:** an `if` test — `if ((rx_edge_ts[i][rx_edge_ts_idx[i]].val -`. When the condition holds it runs `rx_edge_ts[i][next_idx].val)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801337c** (RW mirror) [taken-only] — `tst r2, r3` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (usb_pd_phy.c:456): `if (pending & EXTI_COMP_MASK(i)) {`
  - **What:** an `if` test — `if (pending & EXTI_COMP_MASK(i)) {`. When the condition holds it runs `rx_edge_ts[i][rx_edge_ts_idx[i]].val = get_time().val;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080133b8** (RW mirror) [unreached] — `cmp r7, #0` then `bne`: taken when r7 != constant 0. r7 = word [r6+0x1c] (a struct/buffer field). MISSING direction (unreached) needs r7 != constant 0.
  - rebuilt C (usb_pd_phy.c:478): `if ((rx_edge_ts[i][rx_edge_ts_idx[i]].val -`
  - **What:** an `if` test — `if ((rx_edge_ts[i][rx_edge_ts_idx[i]].val -`. When the condition holds it runs `rx_edge_ts[i][next_idx].val)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080133bc** (RW mirror) [unreached] — `cmp r6, #0x13` then `bls`: taken when r6 <=u constant 0x13. r6 = computed (subs r6, r2). MISSING direction (unreached) needs r6 <=u constant 0x13.
  - rebuilt C (usb_pd_phy.c:492): `STM32_EXTI_PR = EXTI_COMP_MASK(i);`
  - **What:** a conditional derived from this statement — `STM32_EXTI_PR = EXTI_COMP_MASK(i);`. When the condition holds it runs `rx_edge_ts_idx[i] = next_idx;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x0800360c  `usb_spi_deferred`  (conf:approx)
**Signature:** `void usb_spi_deferred(struct usb_spi_config const *config)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_spi.c:70  | rebuilt @ 0x8003490 | 15 uncovered (0 unreached, 15 one-dir; 8 in RW mirror)

- **0x0800362a** [nottaken-only] — `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r5 == constant 0.
  - rebuilt C (usb_spi.c:79): `if (enabled) usb_spi_board_enable(config);`
  - **What:** an `if` test — `if (enabled) usb_spi_board_enable(config);`. When the condition holds it runs `else         usb_spi_board_disable(config);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08003660** [nottaken-only] — `cmp r2, #0x20` then `bge`: taken when r2 >= constant 0x20. r2 = computed (asrs r2, #1). MISSING direction (nottaken-only) needs r2 >= constant 0x20.
  - rebuilt C (usb_spi.c:28): `size_t   count = MAX((bytes + 1) / 2, USB_MAX_PACKET_SIZE / 2);`
  - **What:** a conditional derived from this statement — `size_t   count = MAX((bytes + 1) / 2, USB_MAX_PACKET_SIZE / 2);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080036a2** [nottaken-only] — `cmp r2, #0x3e` then `bhi`: taken when r2 >u constant 0x3e. r2 = computed (uxtb r2). MISSING direction (nottaken-only) needs r2 >u constant 0x3e.
  - rebuilt C (usb_spi.c:96): `} else if (write_count > USB_SPI_MAX_WRITE_COUNT ||`
  - **What:** an `if` test — `} else if (write_count > USB_SPI_MAX_WRITE_COUNT ||`. When the condition holds it runs `write_count != (count - 2)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080036b2** [nottaken-only] — `cmp r5, #0x3e` then `bhi`: taken when r5 >u constant 0x3e. r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 >u constant 0x3e.
  - rebuilt C (usb_spi.c:99): `} else if (read_count > USB_SPI_MAX_READ_COUNT) {`
  - **What:** an `if` test — `} else if (read_count > USB_SPI_MAX_READ_COUNT) {`. When the condition holds it runs `config->buffer[0] = USB_SPI_READ_COUNT_INVALID;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080036c4** [nottaken-only] — `cmp r0, #4` then `beq`: taken when r0 == constant 4. r0 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r0 == constant 4.
  - rebuilt C (usb_spi.c:16): `switch (error) {`
  - **What:** a `switch` dispatch on the value — `switch (error) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080036ca** [nottaken-only] — `cmp r0, #6` then `beq`: taken when r0 == constant 6. r0 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r0 == constant 6.
  - rebuilt C (usb_spi.c:16): `switch (error) {`
  - **What:** a `switch` dispatch on the value — `switch (error) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080036ce** [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_spi.c:17): `case EC_SUCCESS:       return USB_SPI_SUCCESS;`
  - **What:** a `case` comparison — `case EC_SUCCESS:       return USB_SPI_SUCCESS;`. When the condition holds it runs `case EC_ERROR_TIMEOUT: return USB_SPI_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801362a** (RW mirror) [nottaken-only] — `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r5 == constant 0.
  - rebuilt C (usb_spi.c:79): `if (enabled) usb_spi_board_enable(config);`
  - **What:** an `if` test — `if (enabled) usb_spi_board_enable(config);`. When the condition holds it runs `else         usb_spi_board_disable(config);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08013660** (RW mirror) [nottaken-only] — `cmp r2, #0x20` then `bge`: taken when r2 >= constant 0x20. r2 = computed (asrs r2, #1). MISSING direction (nottaken-only) needs r2 >= constant 0x20.
  - rebuilt C (usb_spi.c:28): `size_t   count = MAX((bytes + 1) / 2, USB_MAX_PACKET_SIZE / 2);`
  - **What:** a conditional derived from this statement — `size_t   count = MAX((bytes + 1) / 2, USB_MAX_PACKET_SIZE / 2);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080136a2** (RW mirror) [nottaken-only] — `cmp r2, #0x3e` then `bhi`: taken when r2 >u constant 0x3e. r2 = computed (uxtb r2). MISSING direction (nottaken-only) needs r2 >u constant 0x3e.
  - rebuilt C (usb_spi.c:96): `} else if (write_count > USB_SPI_MAX_WRITE_COUNT ||`
  - **What:** an `if` test — `} else if (write_count > USB_SPI_MAX_WRITE_COUNT ||`. When the condition holds it runs `write_count != (count - 2)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080136a8** (RW mirror) [taken-only] — `cmp r2, r3` then `beq`: taken when r2 == r3 (= computed (subs #2)). r2 = computed (uxtb r2). MISSING direction (taken-only) needs r2 != r3 (= computed (subs #2)).
  - rebuilt C (usb_spi.c:96 (discriminator 1)): `} else if (write_count > USB_SPI_MAX_WRITE_COUNT ||`
  - **What:** an `if` test — `} else if (write_count > USB_SPI_MAX_WRITE_COUNT ||`. When the condition holds it runs `write_count != (count - 2)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080136b2** (RW mirror) [nottaken-only] — `cmp r5, #0x3e` then `bhi`: taken when r5 >u constant 0x3e. r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 >u constant 0x3e.
  - rebuilt C (usb_spi.c:99): `} else if (read_count > USB_SPI_MAX_READ_COUNT) {`
  - **What:** an `if` test — `} else if (read_count > USB_SPI_MAX_READ_COUNT) {`. When the condition holds it runs `config->buffer[0] = USB_SPI_READ_COUNT_INVALID;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080136c4** (RW mirror) [nottaken-only] — `cmp r0, #4` then `beq`: taken when r0 == constant 4. r0 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r0 == constant 4.
  - rebuilt C (usb_spi.c:16): `switch (error) {`
  - **What:** a `switch` dispatch on the value — `switch (error) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080136ca** (RW mirror) [nottaken-only] — `cmp r0, #6` then `beq`: taken when r0 == constant 6. r0 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r0 == constant 6.
  - rebuilt C (usb_spi.c:16): `switch (error) {`
  - **What:** a `switch` dispatch on the value — `switch (error) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080136ce** (RW mirror) [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_spi.c:17): `case EC_SUCCESS:       return USB_SPI_SUCCESS;`
  - **What:** a `case` comparison — `case EC_SUCCESS:       return USB_SPI_SUCCESS;`. When the condition holds it runs `case EC_ERROR_TIMEOUT: return USB_SPI_TIMEOUT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080037c0  `usb_spi_interface`  (conf:high)
**Signature:** `int usb_spi_interface(struct usb_spi_config const *config, usb_uint *rx_buf, usb_uint *tx_buf)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/usb_spi.c:146  | rebuilt @ 0x8003648 | 13 uncovered (7 unreached, 6 one-dir; 7 in RW mirror)

- **0x080037dc** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = halfword [r3+2] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_spi.c:156): `if (setup.wValue  != 0 ||`
  - **What:** an `if` test — `if (setup.wValue  != 0 ||`. When the condition holds it runs `setup.wIndex  != config->interface ||`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080037e6** [nottaken-only] — `cmp r3, r2` then `bne`: taken when r3 != r2 (= word [r4+4] (a struct/buffer field)). r3 = halfword [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != r2 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (usb_spi.c:156 (discriminator 1)): `if (setup.wValue  != 0 ||`
  - **What:** an `if` test — `if (setup.wValue  != 0 ||`. When the condition holds it runs `setup.wIndex  != config->interface ||`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080037ee** [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = halfword [r3+6] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (usb_spi.c:157): `setup.wIndex  != config->interface ||`
  - **What:** a conditional derived from this statement — `setup.wIndex  != config->interface ||`. When the condition holds it runs `setup.wLength != 0)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080037f6** [nottaken-only] — `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r1 == constant 0.
  - rebuilt C (usb_spi.c:161): `if (!config->state->enabled_device)`
  - **What:** an `if` test — `if (!config->state->enabled_device)`. When the condition holds it runs `return 1;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080037fe** [taken-only] — `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = byte [r1+1] (a struct/buffer field). MISSING direction (taken-only) needs r1 != constant 0.
  - rebuilt C (usb_spi.c:164): `switch (setup.bRequest) {`
  - **What:** a `switch` dispatch on the value — `switch (setup.bRequest) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08003802** [unreached] — `cmp r1, r0` then `bne`: taken when r1 != r0 (= function argument r0). r1 = byte [r1+1] (a struct/buffer field). MISSING direction (unreached) needs r1 != r0 (= function argument r0).
  - rebuilt C (usb_spi.c:164): `switch (setup.bRequest) {`
  - **What:** a `switch` dispatch on the value — `switch (setup.bRequest) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080137d4** (RW mirror) [taken-only] — `cmp r3, #0x41` then `bne`: taken when r3 != constant 0x41. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0x41.
  - rebuilt C (usb_spi.c:151): `if (setup.bmRequestType != (USB_DIR_OUT |`
  - **What:** an `if` test — `if (setup.bmRequestType != (USB_DIR_OUT |`. When the condition holds it runs `USB_TYPE_VENDOR |`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080137dc** (RW mirror) [unreached] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = halfword [r3+2] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 0.
  - rebuilt C (usb_spi.c:156): `if (setup.wValue  != 0 ||`
  - **What:** an `if` test — `if (setup.wValue  != 0 ||`. When the condition holds it runs `setup.wIndex  != config->interface ||`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080137e6** (RW mirror) [unreached] — `cmp r3, r2` then `bne`: taken when r3 != r2 (= word [r4+4] (a struct/buffer field)). r3 = halfword [r3+4] (a struct/buffer field). MISSING direction (unreached) needs r3 != r2 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (usb_spi.c:156 (discriminator 1)): `if (setup.wValue  != 0 ||`
  - **What:** an `if` test — `if (setup.wValue  != 0 ||`. When the condition holds it runs `setup.wIndex  != config->interface ||`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080137ee** (RW mirror) [unreached] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = halfword [r3+6] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 0.
  - rebuilt C (usb_spi.c:157): `setup.wIndex  != config->interface ||`
  - **What:** a conditional derived from this statement — `setup.wIndex  != config->interface ||`. When the condition holds it runs `setup.wLength != 0)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080137f6** (RW mirror) [unreached] — `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = word [r3+4] (a struct/buffer field). MISSING direction (unreached) needs r1 == constant 0.
  - rebuilt C (usb_spi.c:161): `if (!config->state->enabled_device)`
  - **What:** an `if` test — `if (!config->state->enabled_device)`. When the condition holds it runs `return 1;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080137fe** (RW mirror) [unreached] — `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = byte [r1+1] (a struct/buffer field). MISSING direction (unreached) needs r1 == constant 0.
  - rebuilt C (usb_spi.c:164): `switch (setup.bRequest) {`
  - **What:** a `switch` dispatch on the value — `switch (setup.bRequest) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08013802** (RW mirror) [unreached] — `cmp r1, r0` then `bne`: taken when r1 != r0 (= function argument r0). r1 = byte [r1+1] (a struct/buffer field). MISSING direction (unreached) needs r1 != r0 (= function argument r0).
  - rebuilt C (usb_spi.c:164): `switch (setup.bRequest) {`
  - **What:** a `switch` dispatch on the value — `switch (setup.bRequest) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08003850  `command_adc`  (conf:approx)
**Signature:** `static int command_adc(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/adc.c:33  | rebuilt @ 0x8003718 | 6 uncovered (0 unreached, 6 one-dir; 3 in RW mirror)

- **0x08003866** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = byte [r7+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (adc.c:21): `if (!name || !*name)`
  - **What:** an `if` test — `if (!name || !*name)`. When the condition holds it runs `return ADC_CH_COUNT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08003886** [taken-only] — flags from `adds r2, r0, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (adc.c:43): `if (v == ADC_READ_ERROR)`
  - **What:** an `if` test — `if (v == ADC_READ_ERROR)`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080038a0** [taken-only] — flags from `adds r2, r0, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (adc.c:45): `ccprintf("  %s = %d\n", adc_channels[i].name, v);`
  - **What:** a conditional derived from this statement — `ccprintf("  %s = %d\n", adc_channels[i].name, v);`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08013866** (RW mirror) [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = byte [r7+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (adc.c:21): `if (!name || !*name)`
  - **What:** an `if` test — `if (!name || !*name)`. When the condition holds it runs `return ADC_CH_COUNT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08013886** (RW mirror) [taken-only] — flags from `adds r2, r0, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (adc.c:43): `if (v == ADC_READ_ERROR)`
  - **What:** an `if` test — `if (v == ADC_READ_ERROR)`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080138a0** (RW mirror) [taken-only] — flags from `adds r2, r0, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (adc.c:45): `ccprintf("  %s = %d\n", adc_channels[i].name, v);`
  - **What:** a conditional derived from this statement — `ccprintf("  %s = %d\n", adc_channels[i].name, v);`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08003a30  `console_putc`  (conf:approx)
**Signature:** `static int console_putc(int c)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/console.c:276  | rebuilt @ 0x800393c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08003a42** [taken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = computed (adds r0, #0). MISSING direction (taken-only) needs r4 != constant 0.
  - rebuilt C (console.c:280): `return rv1 == EC_SUCCESS ? rv2 : rv1;`
  - **What:** a ternary `?:` test — `return rv1 == EC_SUCCESS ? rv2 : rv1;`. When the condition holds it runs `#ifndef CONFIG_EXPERIMENTAL_CONSOLE`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08013a42** (RW mirror) [taken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = computed (adds r0, #0). MISSING direction (taken-only) needs r4 != constant 0.
  - rebuilt C (console.c:280): `return rv1 == EC_SUCCESS ? rv2 : rv1;`
  - **What:** a ternary `?:` test — `return rv1 == EC_SUCCESS ? rv2 : rv1;`. When the condition holds it runs `#ifndef CONFIG_EXPERIMENTAL_CONSOLE`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08003a60  `command_help`  (conf:approx)
**Signature:** `static int command_help(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/console.c:686  | rebuilt @ 0x80039c8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08003adc** [nottaken-only] — flags from `subs r4, r2, #0` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (console.c:714 (discriminator 4)): `if (cmd->shorthelp)`
  - **What:** an `if` test — `if (cmd->shorthelp)`. When the condition holds it runs `ccprintf("%s\n", cmd->shorthelp);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08013adc** (RW mirror) [nottaken-only] — flags from `subs r4, r2, #0` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (console.c:714 (discriminator 4)): `if (cmd->shorthelp)`
  - **What:** an `if` test — `if (cmd->shorthelp)`. When the condition holds it runs `ccprintf("%s\n", cmd->shorthelp);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08003c00  `console_handle_char`  (conf:approx)
**Signature:** `static void console_handle_char(int c)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/console.c:458  | rebuilt @ 0x8003b20 | 8 uncovered (0 unreached, 8 one-dir; 4 in RW mirror)

- **0x08003ca2** [nottaken-only] — `cmp r5, #0x7e` then `bne`: taken when r5 != constant 0x7e. r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 != constant 0x7e.
  - rebuilt C (console.c:439): `if (c == '~')`
  - **What:** an `if` test — `if (c == '~')`. When the condition holds it runs `return KEY_DEL;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08003d08** [taken-only] — `cmp r5, #0xc` then `beq`: taken when r5 == constant 0xc. r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 != constant 0xc.
  - rebuilt C (console.c:494): `switch (c) {`
  - **What:** a `switch` dispatch on the value — `switch (c) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08003eae** [nottaken-only] — `cmp r2, #0x14` then `bne`: taken when r2 != constant 0x14. r2 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r2 != constant 0x14.
  - rebuilt C (console.c:255): `ccprintf("Command returned error %d\n", rv);`
  - **What:** a conditional derived from this statement — `ccprintf("Command returned error %d\n", rv);`. When the condition holds it runs `#ifdef CONFIG_CONSOLE_CMDHELP`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08003eea** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r5+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (console.c:536): `break;`
  - **What:** a conditional derived from this statement — `break;`. When the condition holds it runs `#ifndef CONFIG_EXPERIMENTAL_CONSOLE`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08013ca2** (RW mirror) [nottaken-only] — `cmp r5, #0x7e` then `bne`: taken when r5 != constant 0x7e. r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 != constant 0x7e.
  - rebuilt C (console.c:439): `if (c == '~')`
  - **What:** an `if` test — `if (c == '~')`. When the condition holds it runs `return KEY_DEL;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08013d08** (RW mirror) [taken-only] — `cmp r5, #0xc` then `beq`: taken when r5 == constant 0xc. r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 != constant 0xc.
  - rebuilt C (console.c:494): `switch (c) {`
  - **What:** a `switch` dispatch on the value — `switch (c) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08013eae** (RW mirror) [nottaken-only] — `cmp r2, #0x14` then `bne`: taken when r2 != constant 0x14. r2 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r2 != constant 0x14.
  - rebuilt C (console.c:255): `ccprintf("Command returned error %d\n", rv);`
  - **What:** a conditional derived from this statement — `ccprintf("Command returned error %d\n", rv);`. When the condition holds it runs `#ifdef CONFIG_CONSOLE_CMDHELP`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08013eea** (RW mirror) [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r5+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (console.c:536): `break;`
  - **What:** a conditional derived from this statement — `break;`. When the condition holds it runs `#ifndef CONFIG_EXPERIMENTAL_CONSOLE`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800409c  `console_task`  (conf:approx)
**Signature:** `void console_task(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/console.c:648  | rebuilt @ 0x8003f78 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080040ca** [taken-only] — flags from `adds r3, r0, #1` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (console.c:672): `if (c == -1)`
  - **What:** an `if` test — `if (c == -1)`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080140ca** (RW mirror) [taken-only] — flags from `adds r3, r0, #1` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (console.c:672): `if (c == -1)`
  - **What:** an `if` test — `if (c == -1)`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080040e4  `cputs`  (conf:approx)
**Signature:** `int cputs(enum console_channel channel, const char *outstr)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/console_output.c:42  | rebuilt @ 0x8003fc0 | 1 uncovered (0 unreached, 1 one-dir; 0 in RW mirror)

- **0x08004104** [taken-only] — `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = computed (adds r0, #0). MISSING direction (taken-only) needs r5 != constant 0.
  - rebuilt C (console_output.c:52): `return rv1 == EC_SUCCESS ? rv2 : rv1;`
  - **What:** a ternary `?:` test — `return rv1 == EC_SUCCESS ? rv2 : rv1;`. When the condition holds it runs `int cprintf(enum console_channel channel, const char *format, ...)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080041fc  `cprints`  (conf:approx)
**Signature:** `int cprints(enum console_channel channel, const char *format, ...)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/console_output.c:76  | rebuilt @ 0x80040d8 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08004226** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [sp+0x1c] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (console_output.c:88): `if (r)`
  - **What:** an `if` test — `if (r)`. When the condition holds it runs `rv = r;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08004244** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r4, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (console_output.c:99): `return r ? r : rv;`
  - **What:** a ternary `?:` test — `return r ? r : rv;`. When the condition holds it runs `void cflush(void)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014226** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [sp+0x1c] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (console_output.c:88): `if (r)`
  - **What:** an `if` test — `if (r)`. When the condition holds it runs `rv = r;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08014244** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r4, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (console_output.c:99): `return r ? r : rv;`
  - **What:** a ternary `?:` test — `return r ? r : rv;`. When the condition holds it runs `void cflush(void)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08004264  `flash_command_get_info`  (conf:approx)
**Signature:** `static int flash_command_get_info(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:739  | rebuilt @ 0x8004140 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080042b2** [taken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = computed (subs #8). MISSING direction (taken-only) needs r2 == constant 0.
  - rebuilt C (flash.c:765): `if (!r->write_ideal_size)`
  - **What:** an `if` test — `if (!r->write_ideal_size)`. When the condition holds it runs `r->write_ideal_size =`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080142b2** (RW mirror) [taken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = computed (subs #8). MISSING direction (taken-only) needs r2 == constant 0.
  - rebuilt C (flash.c:765): `if (!r->write_ideal_size)`
  - **What:** an `if` test — `if (!r->write_ideal_size)`. When the condition holds it runs `r->write_ideal_size =`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080042de  `flash_command_region_info`  (conf:high)
**Signature:** `static int flash_command_region_info(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:903  | rebuilt @ 0x80041ba | 6 uncovered (2 unreached, 4 one-dir; 3 in RW mirror)

- **0x080042fa** [nottaken-only] — `cmp r2, #1` then `beq`: taken when r2 == constant 1. r2 = computed (orrs r1). MISSING direction (nottaken-only) needs r2 == constant 1.
  - rebuilt C (flash.c:907): `switch (p->region) {`
  - **What:** a `switch` dispatch on the value — `switch (p->region) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080042fe** [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (orrs r1). MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (flash.c:907): `switch (p->region) {`
  - **What:** a `switch` dispatch on the value — `switch (p->region) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08004302** [unreached] — `cmp r2, #2` then `bne`: taken when r2 != constant 2. r2 = computed (orrs r1). MISSING direction (unreached) needs r2 != constant 2.
  - rebuilt C (flash.c:907): `switch (p->region) {`
  - **What:** a `switch` dispatch on the value — `switch (p->region) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080142fa** (RW mirror) [nottaken-only] — `cmp r2, #1` then `beq`: taken when r2 == constant 1. r2 = computed (orrs r1). MISSING direction (nottaken-only) needs r2 == constant 1.
  - rebuilt C (flash.c:907): `switch (p->region) {`
  - **What:** a `switch` dispatch on the value — `switch (p->region) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080142fe** (RW mirror) [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (orrs r1). MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (flash.c:907): `switch (p->region) {`
  - **What:** a `switch` dispatch on the value — `switch (p->region) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08014302** (RW mirror) [unreached] — `cmp r2, #2` then `bne`: taken when r2 != constant 2. r2 = computed (orrs r1). MISSING direction (unreached) needs r2 != constant 2.
  - rebuilt C (flash.c:907): `switch (p->region) {`
  - **What:** a `switch` dispatch on the value — `switch (p->region) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x0800433a  `flash_range_ok`  (conf:high)
**Signature:** `int flash_range_ok(int offset, int size_req, int align)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:95  | rebuilt @ 0x8004240 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08004346** [nottaken-only] — `cmp r1, r0` then `blt`: taken when r1 < r0 (= computed (movs #0)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 < r0 (= computed (movs #0)).
  - rebuilt C (flash.c:96): `if (offset < 0 || size_req < 0 ||`
  - **What:** an `if` test — `if (offset < 0 || size_req < 0 ||`. When the condition holds it runs `offset + size_req > CONFIG_FLASH_SIZE ||`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014346** (RW mirror) [nottaken-only] — `cmp r1, r0` then `blt`: taken when r1 < r0 (= computed (movs #0)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 < r0 (= computed (movs #0)).
  - rebuilt C (flash.c:96): `if (offset < 0 || size_req < 0 ||`
  - **What:** an `if` test — `if (offset < 0 || size_req < 0 ||`. When the condition holds it runs `offset + size_req > CONFIG_FLASH_SIZE ||`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08004386  `flash_is_erased`  (conf:high)
**Signature:** `int flash_is_erased(uint32_t offset, int size)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:260  | rebuilt @ 0x800428c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080043a2** [taken-only] — flags from `adds r1, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash.c:270): `if (*ptr != CONFIG_FLASH_ERASED_VALUE32)`
  - **What:** an `if` test — `if (*ptr != CONFIG_FLASH_ERASED_VALUE32)`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080143a2** (RW mirror) [taken-only] — flags from `adds r1, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (flash.c:270): `if (*ptr != CONFIG_FLASH_ERASED_VALUE32)`
  - **What:** an `if` test — `if (*ptr != CONFIG_FLASH_ERASED_VALUE32)`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080043d6  `flash_command_read`  (conf:approx)
**Signature:** `static int flash_command_read(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:786  | rebuilt @ 0x80042dc | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800440a** [nottaken-only] — `cmp r1, r3` then `bhi`: taken when r1 >u r3 (= halfword [r0+0x14] (a struct/buffer field)). r1 = computed (orrs r3). MISSING direction (nottaken-only) needs r1 >u r3 (= halfword [r0+0x14] (a struct/buffer field)).
  - rebuilt C (flash.c:788): `uint32_t offset = p->offset + EC_FLASH_REGION_START;`
  - **What:** a conditional derived from this statement — `uint32_t offset = p->offset + EC_FLASH_REGION_START;`. When the condition holds it runs `if (p->size > args->response_max)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801440a** (RW mirror) [nottaken-only] — `cmp r1, r3` then `bhi`: taken when r1 >u r3 (= halfword [r0+0x14] (a struct/buffer field)). r1 = computed (orrs r3). MISSING direction (nottaken-only) needs r1 >u r3 (= halfword [r0+0x14] (a struct/buffer field)).
  - rebuilt C (flash.c:788): `uint32_t offset = p->offset + EC_FLASH_REGION_START;`
  - **What:** a conditional derived from this statement — `uint32_t offset = p->offset + EC_FLASH_REGION_START;`. When the condition holds it runs `if (p->size > args->response_max)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08004428  `flash_write`  (conf:approx)
**Signature:** `int flash_write(int offset, int size, const char *data)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:313  | rebuilt @ 0x8004334 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x08014444** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #5). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (flash.c:323): `if (vboot_hash_in_progress())`
  - **What:** an `if` test — `if (vboot_hash_in_progress())`. When the condition holds it runs `vboot_hash_abort();`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08004498  `flash_get_protect`  (conf:approx)
**Signature:** `uint32_t flash_get_protect(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:397  | rebuilt @ 0x80043fc | 12 uncovered (4 unreached, 8 one-dir; 6 in RW mirror)

- **0x080044ac** [taken-only] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = function argument r0. MISSING direction (taken-only) needs r0 == constant 2.
  - rebuilt C (flash.c:410): `flags |= EC_FLASH_PROTECT_GPIO_ASSERTED;`
  - **What:** a conditional derived from this statement — `flags |= EC_FLASH_PROTECT_GPIO_ASSERTED;`. When the condition holds it runs `#endif`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080044d6** [taken-only] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r0 == constant 2.
  - rebuilt C (flash.c:430): `if (not_protected[is_ro])`
  - **What:** an `if` test — `if (not_protected[is_ro])`. When the condition holds it runs `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080044e8** [nottaken-only] — `cmp r6, r3` then `beq`: taken when r6 == r3 (= computed (adds r3, r2)). r6 = register r6. MISSING direction (nottaken-only) needs r6 == r3 (= computed (adds r3, r2)).
  - rebuilt C (flash.c:435): `if (flags & bank_flag)`
  - **What:** an `if` test — `if (flags & bank_flag)`. When the condition holds it runs `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080044ee** [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = register r6. MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (flash.c:436): `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`
  - **What:** a conditional derived from this statement — `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080044f6** [unreached] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = computed (movs #7). MISSING direction (unreached) needs r0 != constant 2.
  - rebuilt C (flash.c:448): `if ((flags & EC_FLASH_PROTECT_ALL_NOW) &&`
  - **What:** an `if` test — `if ((flags & EC_FLASH_PROTECT_ALL_NOW) &&`. When the condition holds it runs `!(flags & EC_FLASH_PROTECT_RO_NOW))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800450c** [unreached] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r4, r3). MISSING direction (unreached) needs r0 == constant 0.
  - rebuilt C (flash.c:542): `ccprintf("Usable:  %4d KB\n", CONFIG_FLASH_SIZE / 1024);`
  - **What:** a conditional derived from this statement — `ccprintf("Usable:  %4d KB\n", CONFIG_FLASH_SIZE / 1024);`. When the condition holds it runs `ccprintf("Write:   %4d B (ideal %d B)\n", CONFIG_FLASH_WRITE_SIZE,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080144ac** (RW mirror) [nottaken-only] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 2.
  - rebuilt C (flash.c:410): `flags |= EC_FLASH_PROTECT_GPIO_ASSERTED;`
  - **What:** a conditional derived from this statement — `flags |= EC_FLASH_PROTECT_GPIO_ASSERTED;`. When the condition holds it runs `#endif`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080144d6** (RW mirror) [nottaken-only] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 != constant 2.
  - rebuilt C (flash.c:430): `if (not_protected[is_ro])`
  - **What:** an `if` test — `if (not_protected[is_ro])`. When the condition holds it runs `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080144e8** (RW mirror) [nottaken-only] — `cmp r6, r3` then `beq`: taken when r6 == r3 (= computed (adds r3, r2)). r6 = register r6. MISSING direction (nottaken-only) needs r6 == r3 (= computed (adds r3, r2)).
  - rebuilt C (flash.c:435): `if (flags & bank_flag)`
  - **What:** an `if` test — `if (flags & bank_flag)`. When the condition holds it runs `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080144ee** (RW mirror) [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = register r6. MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (flash.c:436): `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`
  - **What:** a conditional derived from this statement — `flags |= EC_FLASH_PROTECT_ERROR_INCONSISTENT;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080144f6** (RW mirror) [unreached] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = computed (movs #7). MISSING direction (unreached) needs r0 != constant 2.
  - rebuilt C (flash.c:448): `if ((flags & EC_FLASH_PROTECT_ALL_NOW) &&`
  - **What:** an `if` test — `if ((flags & EC_FLASH_PROTECT_ALL_NOW) &&`. When the condition holds it runs `!(flags & EC_FLASH_PROTECT_RO_NOW))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801450c** (RW mirror) [unreached] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r4, r3). MISSING direction (unreached) needs r0 == constant 0.
  - rebuilt C (flash.c:542): `ccprintf("Usable:  %4d KB\n", CONFIG_FLASH_SIZE / 1024);`
  - **What:** a conditional derived from this statement — `ccprintf("Usable:  %4d KB\n", CONFIG_FLASH_SIZE / 1024);`. When the condition holds it runs `ccprintf("Write:   %4d B (ideal %d B)\n", CONFIG_FLASH_WRITE_SIZE,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x0800451c  `flash_set_protect`  (conf:approx)
**Signature:** `int flash_set_protect(uint32_t mask, uint32_t flags)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:457  | rebuilt @ 0x800468e | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08004538** [taken-only] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = computed (movs #8). MISSING direction (taken-only) needs r0 == constant 2.
  - rebuilt C (flash.c:491): `if ((mask & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`
  - **What:** an `if` test — `if ((mask & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`. When the condition holds it runs `!(flags & EC_FLASH_PROTECT_ALL_AT_BOOT)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08004572** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (mov sp). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (flash.c:513): `rv = flash_protect_at_boot(FLASH_WP_ALL);`
  - **What:** a conditional derived from this statement — `rv = flash_protect_at_boot(FLASH_WP_ALL);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08014538** (RW mirror) [nottaken-only] — `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = computed (movs #8). MISSING direction (nottaken-only) needs r0 != constant 2.
  - rebuilt C (flash.c:491): `if ((mask & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`
  - **What:** an `if` test — `if ((mask & EC_FLASH_PROTECT_ALL_AT_BOOT) &&`. When the condition holds it runs `!(flags & EC_FLASH_PROTECT_ALL_AT_BOOT)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014572** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (mov sp). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (flash.c:513): `rv = flash_protect_at_boot(FLASH_WP_ALL);`
  - **What:** a conditional derived from this statement — `rv = flash_protect_at_boot(FLASH_WP_ALL);`. When the condition holds it runs `if (rv)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080045a8  `command_flash_info`  (conf:approx)
**Signature:** `static int command_flash_info(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:539  | rebuilt @ 0x800446c | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x080045f6** [nottaken-only] — `lsls r3, r4, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r4, #0x1c). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (flash.c:553): `if (i & EC_FLASH_PROTECT_RO_AT_BOOT)`
  - **What:** an `if` test — `if (i & EC_FLASH_PROTECT_RO_AT_BOOT)`. When the condition holds it runs `ccputs(" ro_at_boot");`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004626** [taken-only] — `lsls r3, r4, #0x1b` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r4, #0x1d). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (flash.c:561): `if (i & EC_FLASH_PROTECT_ERROR_STUCK)`
  - **What:** an `if` test — `if (i & EC_FLASH_PROTECT_ERROR_STUCK)`. When the condition holds it runs `ccputs(" STUCK");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080145f6** (RW mirror) [nottaken-only] — `lsls r3, r4, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r4, #0x1c). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (flash.c:553): `if (i & EC_FLASH_PROTECT_RO_AT_BOOT)`
  - **What:** an `if` test — `if (i & EC_FLASH_PROTECT_RO_AT_BOOT)`. When the condition holds it runs `ccputs(" ro_at_boot");`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014626** (RW mirror) [taken-only] — `lsls r3, r4, #0x1b` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r4, #0x1d). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (flash.c:561): `if (i & EC_FLASH_PROTECT_ERROR_STUCK)`
  - **What:** an `if` test — `if (i & EC_FLASH_PROTECT_ERROR_STUCK)`. When the condition holds it runs `ccputs(" STUCK");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080046dc  `flash_command_write`  (conf:approx)
**Signature:** `static int flash_command_write(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:811  | rebuilt @ 0x800459c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080046fc** [taken-only] — `lsls r3, r0, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r2). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (flash.c:815): `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`
  - **What:** an `if` test — `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`. When the condition holds it runs `return EC_RES_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080146fc** (RW mirror) [taken-only] — `lsls r3, r0, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r2). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (flash.c:815): `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`
  - **What:** an `if` test — `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`. When the condition holds it runs `return EC_RES_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800475c  `flash_command_erase`  (conf:approx)
**Signature:** `static int flash_command_erase(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:834  | rebuilt @ 0x800461e | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800477c** [taken-only] — `lsls r3, r0, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r2). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (flash.c:838): `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`
  - **What:** an `if` test — `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`. When the condition holds it runs `return EC_RES_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801477c** (RW mirror) [taken-only] — `lsls r3, r0, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r2). MISSING (taken-only) needs the tested bit set.
  - rebuilt C (flash.c:838): `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`
  - **What:** an `if` test — `if (flash_get_protect() & EC_FLASH_PROTECT_ALL_NOW)`. When the condition holds it runs `return EC_RES_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080047cc  `flash_set_protect`  (conf:approx)
**Signature:** `int flash_set_protect(uint32_t mask, uint32_t flags)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/flash.c:457  | rebuilt @ 0x800468e | 13 uncovered (2 unreached, 11 one-dir; 6 in RW mirror)

- **0x080047f8** [nottaken-only] — `tst r0, r3` then `beq`: tests bits of r0 (= function argument r0) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (flash.c:493): `if (flash_get_protect() & EC_FLASH_PROTECT_RO_AT_BOOT)`
  - **What:** an `if` test — `if (flash_get_protect() & EC_FLASH_PROTECT_RO_AT_BOOT)`. When the condition holds it runs `range = FLASH_WP_RO;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004828** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #2). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (flash.c:514): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `retval = rv;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08004830** [taken-only] — `tst r6, r3` then `beq`: tests bits of r6 (= register r6) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - rebuilt C (flash.c:518): `if ((mask & EC_FLASH_PROTECT_RO_NOW) &&`
  - **What:** an `if` test — `if ((mask & EC_FLASH_PROTECT_RO_NOW) &&`. When the condition holds it runs `(flags & EC_FLASH_PROTECT_RO_NOW)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08004834** [unreached] — `tst r5, r3` then `beq`: tests bits of r5 (= register r5) against mask r3. MISSING (unreached) needs the masked bits zero.
  - rebuilt C (flash.c:518 (discriminator 1)): `if ((mask & EC_FLASH_PROTECT_RO_NOW) &&`
  - **What:** an `if` test — `if ((mask & EC_FLASH_PROTECT_RO_NOW) &&`. When the condition holds it runs `(flags & EC_FLASH_PROTECT_RO_NOW)) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800483e** [unreached] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (unreached) needs r0 == constant 0.
  - rebuilt C (flash.c:521): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `retval = rv;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800484a** [nottaken-only] — `tst r5, r3` then `beq`: tests bits of r5 (= register r5) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (flash.c:525 (discriminator 1)): `if ((mask & EC_FLASH_PROTECT_ALL_NOW) &&`
  - **What:** an `if` test — `if ((mask & EC_FLASH_PROTECT_ALL_NOW) &&`. When the condition holds it runs `(flags & EC_FLASH_PROTECT_ALL_NOW)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004854** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #1). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (flash.c:528): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `retval = rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080147f8** (RW mirror) [nottaken-only] — `tst r0, r3` then `beq`: tests bits of r0 (= function argument r0) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (flash.c:493): `if (flash_get_protect() & EC_FLASH_PROTECT_RO_AT_BOOT)`
  - **What:** an `if` test — `if (flash_get_protect() & EC_FLASH_PROTECT_RO_AT_BOOT)`. When the condition holds it runs `range = FLASH_WP_RO;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014828** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #2). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (flash.c:514): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `retval = rv;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08014834** (RW mirror) [nottaken-only] — `tst r5, r3` then `beq`: tests bits of r5 (= register r5) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (flash.c:518 (discriminator 1)): `if ((mask & EC_FLASH_PROTECT_RO_NOW) &&`
  - **What:** an `if` test — `if ((mask & EC_FLASH_PROTECT_RO_NOW) &&`. When the condition holds it runs `(flags & EC_FLASH_PROTECT_RO_NOW)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801483e** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (flash.c:521): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `retval = rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801484a** (RW mirror) [nottaken-only] — `tst r5, r3` then `beq`: tests bits of r5 (= register r5) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (flash.c:525 (discriminator 1)): `if ((mask & EC_FLASH_PROTECT_ALL_NOW) &&`
  - **What:** an `if` test — `if ((mask & EC_FLASH_PROTECT_ALL_NOW) &&`. When the condition holds it runs `(flags & EC_FLASH_PROTECT_ALL_NOW)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014854** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #1). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (flash.c:528): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `retval = rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08004954  `gpio_config_pins`  (conf:approx)
**Signature:** `static int gpio_config_pins(enum module_id id, uint32_t port, uint32_t pin_mask, int enable)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/gpio.c:53  | rebuilt @ 0x800483c | 8 uncovered (0 unreached, 8 one-dir; 4 in RW mirror)

- **0x08004970** [taken-only] — `cmp r6, r3` then `bne`: taken when r6 != r3 (= word [r4+0] (a struct/buffer field)). r6 = computed (adds r1, #0). MISSING direction (taken-only) needs r6 == r3 (= word [r4+0] (a struct/buffer field)).
  - rebuilt C (gpio.c:65 (discriminator 1)): `if ((port != GPIO_CONFIG_ALL_PORTS) && (port != af->port))`
  - **What:** an `if` test — `if ((port != GPIO_CONFIG_ALL_PORTS) && (port != af->port))`. When the condition holds it runs `continue;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800497c** [nottaken-only] — `cmp r5, r2` then `bne`: taken when r5 != r2 (= word [r4+4] (a struct/buffer field)). r5 = computed (ands r2). MISSING direction (nottaken-only) needs r5 != r2 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (gpio.c:72): `if ((af->mask & pin_mask) == pin_mask) {`
  - **What:** an `if` test — `if ((af->mask & pin_mask) == pin_mask) {`. When the condition holds it runs `if (!(af->flags & GPIO_DEFAULT))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004982** [nottaken-only] — `lsls r2, r3, #0x12` sets flags from a shifted value (bit test) then `bmi`. operand = word [r4+4] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (gpio.c:73): `if (!(af->flags & GPIO_DEFAULT))`
  - **What:** an `if` test — `if (!(af->flags & GPIO_DEFAULT))`. When the condition holds it runs `gpio_set_flags_by_mask(`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080049ac** [nottaken-only] — flags from `adds r3, r6, #1` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (gpio.c:78 (discriminator 4)): `gpio_set_alternate_function(`
  - **What:** a conditional derived from this statement — `gpio_set_alternate_function(`. When the condition holds it runs `af->port,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014970** (RW mirror) [taken-only] — `cmp r6, r3` then `bne`: taken when r6 != r3 (= word [r4+0] (a struct/buffer field)). r6 = computed (adds r1, #0). MISSING direction (taken-only) needs r6 == r3 (= word [r4+0] (a struct/buffer field)).
  - rebuilt C (gpio.c:65 (discriminator 1)): `if ((port != GPIO_CONFIG_ALL_PORTS) && (port != af->port))`
  - **What:** an `if` test — `if ((port != GPIO_CONFIG_ALL_PORTS) && (port != af->port))`. When the condition holds it runs `continue;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801497c** (RW mirror) [nottaken-only] — `cmp r5, r2` then `bne`: taken when r5 != r2 (= word [r4+4] (a struct/buffer field)). r5 = computed (ands r2). MISSING direction (nottaken-only) needs r5 != r2 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (gpio.c:72): `if ((af->mask & pin_mask) == pin_mask) {`
  - **What:** an `if` test — `if ((af->mask & pin_mask) == pin_mask) {`. When the condition holds it runs `if (!(af->flags & GPIO_DEFAULT))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014982** (RW mirror) [nottaken-only] — `lsls r2, r3, #0x12` sets flags from a shifted value (bit test) then `bmi`. operand = word [r4+4] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (gpio.c:73): `if (!(af->flags & GPIO_DEFAULT))`
  - **What:** an `if` test — `if (!(af->flags & GPIO_DEFAULT))`. When the condition holds it runs `gpio_set_flags_by_mask(`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080149ac** (RW mirror) [nottaken-only] — flags from `adds r3, r6, #1` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (gpio.c:78 (discriminator 4)): `gpio_set_alternate_function(`
  - **What:** a conditional derived from this statement — `gpio_set_alternate_function(`. When the condition holds it runs `af->port,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08004a20  `print_gpio_info`  (conf:approx)
**Signature:** `static void print_gpio_info(int gpio)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/gpio_commands.c:81  | rebuilt @ 0x8004908 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08004a30** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (gpio_commands.c:84): `if (!gpio_is_implemented(gpio))`
  - **What:** an `if` test — `if (!gpio_is_implemented(gpio))`. When the condition holds it runs `return;  /* Skip unsupported signals */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004a4e** [taken-only] — flags from `ands r3, r4` then `bpl`; MISSING direction (taken-only) needs the result to make `bpl` go the other way
  - rebuilt C (gpio_commands.c:49): `if (v && !(last_val[i / 8] & (1 << (i % 8)))) {`
  - **What:** an `if` test — `if (v && !(last_val[i / 8] & (1 << (i % 8)))) {`. When the condition holds it runs `last_val[i / 8] |= 1 << (i % 8);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08014a30** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (gpio_commands.c:84): `if (!gpio_is_implemented(gpio))`
  - **What:** an `if` test — `if (!gpio_is_implemented(gpio))`. When the condition holds it runs `return;  /* Skip unsupported signals */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014a4e** (RW mirror) [taken-only] — flags from `ands r3, r4` then `bpl`; MISSING direction (taken-only) needs the result to make `bpl` go the other way
  - rebuilt C (gpio_commands.c:49): `if (v && !(last_val[i / 8] & (1 << (i % 8)))) {`
  - **What:** an `if` test — `if (v && !(last_val[i / 8] & (1 << (i % 8)))) {`. When the condition holds it runs `last_val[i / 8] |= 1 << (i % 8);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08004b0e  `set`  (conf:approx)
**Signature:** `static enum ec_error_list set(const char *name, int value)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/gpio_commands.c:61  | rebuilt @ 0x80049f8 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08004b26** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (gpio_commands.c:67): `if (!gpio_is_implemented(signal))`
  - **What:** an `if` test — `if (!gpio_is_implemented(signal))`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004b30** [taken-only] — `lsls r3, r0, #0x1a` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (gpio_commands.c:70): `if (!(gpio_get_default_flags(signal) & GPIO_OUTPUT))`
  - **What:** an `if` test — `if (!(gpio_get_default_flags(signal) & GPIO_OUTPUT))`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08014b26** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (gpio_commands.c:67): `if (!gpio_is_implemented(signal))`
  - **What:** an `if` test — `if (!gpio_is_implemented(signal))`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014b30** (RW mirror) [taken-only] — `lsls r3, r0, #0x1a` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (gpio_commands.c:70): `if (!(gpio_get_default_flags(signal) & GPIO_OUTPUT))`
  - **What:** an `if` test — `if (!(gpio_get_default_flags(signal) & GPIO_OUTPUT))`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08004b3e  `gpio_command_set`  (conf:high)
**Signature:** `static int gpio_command_set(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/gpio_commands.c:263  | rebuilt @ 0x8004a28 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08004b48** [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (gpio_commands.c:266): `if (system_is_locked())`
  - **What:** an `if` test — `if (system_is_locked())`. When the condition holds it runs `return EC_RES_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004b56** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (gpio_commands.c:269): `if (set(p->name, p->val) != EC_SUCCESS)`
  - **What:** an `if` test — `if (set(p->name, p->val) != EC_SUCCESS)`. When the condition holds it runs `return EC_RES_ERROR;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014b48** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (gpio_commands.c:266): `if (system_is_locked())`
  - **What:** an `if` test — `if (system_is_locked())`. When the condition holds it runs `return EC_RES_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014b56** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (gpio_commands.c:269): `if (set(p->name, p->val) != EC_SUCCESS)`
  - **What:** an `if` test — `if (set(p->name, p->val) != EC_SUCCESS)`. When the condition holds it runs `return EC_RES_ERROR;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08004cbc  `hook_call_deferred`  (conf:approx)
**Signature:** `int hook_call_deferred(const struct deferred_data *data, int us)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/hooks.c:135  | rebuilt @ 0x8004bac | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08004cd8** [taken-only] — flags from `adds r3, r1, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (hooks.c:141): `if (us == -1) {`
  - **What:** an `if` test — `if (us == -1) {`. When the condition holds it runs `__deferred_until[i] = 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08014cd8** (RW mirror) [taken-only] — flags from `adds r3, r1, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (hooks.c:141): `if (us == -1) {`
  - **What:** an `if` test — `if (us == -1) {`. When the condition holds it runs `__deferred_until[i] = 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08004d30  `hook_task`  (conf:approx)
**Signature:** `void hook_task(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/hooks.c:163  | rebuilt @ 0x8004c18 | 13 uncovered (0 unreached, 13 one-dir; 8 in RW mirror)

- **0x08004d74** [nottaken-only] — `cmp r7, r2` then `bhi`: taken when r7 >u r2 (= word [r3+4] (a struct/buffer field)). r7 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r7 >u r2 (= word [r3+4] (a struct/buffer field)).
  - rebuilt C (hooks.c:183): `if (__deferred_until[i] && __deferred_until[i] < t) {`
  - **What:** an `if` test — `if (__deferred_until[i] && __deferred_until[i] < t) {`. When the condition holds it runs `CPRINTS("hook call deferred 0x%p",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004dee** [nottaken-only] — `cmp r5, r3` then `bhi`: taken when r5 >u r3 (= word [sp+0xc] (a struct/buffer field)). r5 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r5 >u r3 (= word [sp+0xc] (a struct/buffer field)).
  - rebuilt C (hooks.c:217): `if (last_tick + HOOK_TICK_INTERVAL > t)`
  - **What:** an `if` test — `if (last_tick + HOOK_TICK_INTERVAL > t)`. When the condition holds it runs `next = last_tick + HOOK_TICK_INTERVAL - t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004df0** [nottaken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= word [sp+0xc] (a struct/buffer field)). r5 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r5 != r3 (= word [sp+0xc] (a struct/buffer field)).
  - rebuilt C (hooks.c:217): `if (last_tick + HOOK_TICK_INTERVAL > t)`
  - **What:** an `if` test — `if (last_tick + HOOK_TICK_INTERVAL > t)`. When the condition holds it runs `next = last_tick + HOOK_TICK_INTERVAL - t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004e22** [nottaken-only] — `cmp r3, r5` then `bhi`: taken when r3 >u r5 (= word [r4+4] (a struct/buffer field)). r3 = function argument r3. MISSING direction (nottaken-only) needs r3 >u r5 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (hooks.c:227): `if (__deferred_until[i] < t)`
  - **What:** an `if` test — `if (__deferred_until[i] < t)`. When the condition holds it runs `next = 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08004e38** [nottaken-only] — `cmp ip, r7` then `bhi`: taken when ip >u r7 (= computed (adds r5, #0)). ip = computed (mov r6). MISSING direction (nottaken-only) needs ip >u r7 (= computed (adds r5, #0)).
  - rebuilt C (hooks.c:229): `else if (__deferred_until[i] - t < next)`
  - **What:** an `if` test — `else if (__deferred_until[i] - t < next)`. When the condition holds it runs `next = __deferred_until[i] - t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014d74** (RW mirror) [nottaken-only] — `cmp r7, r2` then `bhi`: taken when r7 >u r2 (= word [r3+4] (a struct/buffer field)). r7 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r7 >u r2 (= word [r3+4] (a struct/buffer field)).
  - rebuilt C (hooks.c:183): `if (__deferred_until[i] && __deferred_until[i] < t) {`
  - **What:** an `if` test — `if (__deferred_until[i] && __deferred_until[i] < t) {`. When the condition holds it runs `CPRINTS("hook call deferred 0x%p",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014da2** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (hooks.c:195): `if (t - last_tick >= HOOK_TICK_INTERVAL) {`
  - **What:** an `if` test — `if (t - last_tick >= HOOK_TICK_INTERVAL) {`. When the condition holds it runs `#ifdef CONFIG_HOOK_DEBUG`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014dc4** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (hooks.c:205): `if (t - last_second >= SECOND) {`
  - **What:** an `if` test — `if (t - last_second >= SECOND) {`. When the condition holds it runs `#ifdef CONFIG_HOOK_DEBUG`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014dee** (RW mirror) [nottaken-only] — `cmp r5, r3` then `bhi`: taken when r5 >u r3 (= word [sp+0xc] (a struct/buffer field)). r5 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r5 >u r3 (= word [sp+0xc] (a struct/buffer field)).
  - rebuilt C (hooks.c:217): `if (last_tick + HOOK_TICK_INTERVAL > t)`
  - **What:** an `if` test — `if (last_tick + HOOK_TICK_INTERVAL > t)`. When the condition holds it runs `next = last_tick + HOOK_TICK_INTERVAL - t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014df0** (RW mirror) [nottaken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= word [sp+0xc] (a struct/buffer field)). r5 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r5 != r3 (= word [sp+0xc] (a struct/buffer field)).
  - rebuilt C (hooks.c:217): `if (last_tick + HOOK_TICK_INTERVAL > t)`
  - **What:** an `if` test — `if (last_tick + HOOK_TICK_INTERVAL > t)`. When the condition holds it runs `next = last_tick + HOOK_TICK_INTERVAL - t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014e22** (RW mirror) [nottaken-only] — `cmp r3, r5` then `bhi`: taken when r3 >u r5 (= word [r4+4] (a struct/buffer field)). r3 = function argument r3. MISSING direction (nottaken-only) needs r3 >u r5 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (hooks.c:227): `if (__deferred_until[i] < t)`
  - **What:** an `if` test — `if (__deferred_until[i] < t)`. When the condition holds it runs `next = 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014e38** (RW mirror) [nottaken-only] — `cmp ip, r7` then `bhi`: taken when ip >u r7 (= computed (adds r5, #0)). ip = computed (mov r6). MISSING direction (nottaken-only) needs ip >u r7 (= computed (adds r5, #0)).
  - rebuilt C (hooks.c:229): `else if (__deferred_until[i] - t < next)`
  - **What:** an `if` test — `else if (__deferred_until[i] - t < next)`. When the condition holds it runs `next = __deferred_until[i] - t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014e4c** (RW mirror) [taken-only] — `cmp r0, #0` then `bgt`: taken when r0 > constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r0 <= constant 0.
  - rebuilt C (hooks.c:238): `if (next > 0 && !defer_new_call)`
  - **What:** an `if` test — `if (next > 0 && !defer_new_call)`. When the condition holds it runs `task_wait_event(next);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08004f48  `host_command_read_test`  (conf:high)
**Signature:** `static int host_command_read_test(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/host_command.c:456  | rebuilt @ 0x8004e28 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08004f7e** [nottaken-only] — `cmp r3, #0x20` then `bhi`: taken when r3 >u constant 0x20. r3 = computed (lsrs r3, #2). MISSING direction (nottaken-only) needs r3 >u constant 0x20.
  - rebuilt C (host_command.c:460): `int offset = p->offset;`
  - **What:** a conditional derived from this statement — `int offset = p->offset;`. When the condition holds it runs `int size = p->size / sizeof(uint32_t);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08014f7e** (RW mirror) [nottaken-only] — `cmp r3, #0x20` then `bhi`: taken when r3 >u constant 0x20. r3 = computed (lsrs r3, #2). MISSING direction (nottaken-only) needs r3 >u constant 0x20.
  - rebuilt C (host_command.c:460): `int offset = p->offset;`
  - **What:** a conditional derived from this statement — `int offset = p->offset;`. When the condition holds it runs `int size = p->size / sizeof(uint32_t);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800500c  `host_command_read_memmap`  (conf:approx)
**Signature:** `static int host_command_read_memmap(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/host_command.c:484  | rebuilt @ 0x8004eb8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800501c** [nottaken-only] — `cmp r2, #0xff` then `bgt`: taken when r2 > constant 0xff. r2 = computed (adds r3, r5). MISSING direction (nottaken-only) needs r2 > constant 0xff.
  - rebuilt C (host_command.c:491): `if (size > EC_MEMMAP_SIZE || offset > EC_MEMMAP_SIZE ||`
  - **What:** an `if` test — `if (size > EC_MEMMAP_SIZE || offset > EC_MEMMAP_SIZE ||`. When the condition holds it runs `offset + size > EC_MEMMAP_SIZE)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801501c** (RW mirror) [nottaken-only] — `cmp r2, #0xff` then `bgt`: taken when r2 > constant 0xff. r2 = computed (adds r3, r5). MISSING direction (nottaken-only) needs r2 > constant 0xff.
  - rebuilt C (host_command.c:491): `if (size > EC_MEMMAP_SIZE || offset > EC_MEMMAP_SIZE ||`
  - **What:** an `if` test — `if (size > EC_MEMMAP_SIZE || offset > EC_MEMMAP_SIZE ||`. When the condition holds it runs `offset + size > EC_MEMMAP_SIZE)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08005038  `host_command_test_protocol`  (conf:approx)
**Signature:** `static int host_command_test_protocol(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/host_command.c:654  | rebuilt @ 0x8004ee4 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08005054** [taken-only] — `cmp r5, #0x20` then `bls`: taken when r5 <=u constant 0x20. r5 = computed (orrs r3). MISSING direction (taken-only) needs r5 >u constant 0x20.
  - rebuilt C (host_command.c:657): `int copy_len = MIN(p->ret_len, sizeof(r->buf)); /* p,r bufs same size */`
  - **What:** a conditional derived from this statement — `int copy_len = MIN(p->ret_len, sizeof(r->buf)); /* p,r bufs same size */`. When the condition holds it runs `memset(r->buf, 0, sizeof(r->buf));`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015054** (RW mirror) [taken-only] — `cmp r5, #0x20` then `bls`: taken when r5 <=u constant 0x20. r5 = computed (orrs r3). MISSING direction (taken-only) needs r5 >u constant 0x20.
  - rebuilt C (host_command.c:657): `int copy_len = MIN(p->ret_len, sizeof(r->buf)); /* p,r bufs same size */`
  - **What:** a conditional derived from this statement — `int copy_len = MIN(p->ret_len, sizeof(r->buf)); /* p,r bufs same size */`. When the condition holds it runs `memset(r->buf, 0, sizeof(r->buf));`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080050fc  `host_command_get_cmd_versions`  (conf:high)
**Signature:** `static int host_command_get_cmd_versions(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/host_command.c:506  | rebuilt @ 0x8004fb0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800513a** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (host_command.c:518): `r->version_mask = cmd->version_mask;`
  - **What:** a conditional derived from this statement — `r->version_mask = cmd->version_mask;`. When the condition holds it runs `args->response_size = sizeof(*r);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801513a** (RW mirror) [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (host_command.c:518): `r->version_mask = cmd->version_mask;`
  - **What:** a conditional derived from this statement — `r->version_mask = cmd->version_mask;`. When the condition holds it runs `args->response_size = sizeof(*r);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08005160  `host_command_test_protocol`  (conf:approx)
**Signature:** `static int host_command_test_protocol(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/host_command.c:654  | rebuilt @ 0x8004ee4 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x0801516a** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (host_command.c:657): `int copy_len = MIN(p->ret_len, sizeof(r->buf)); /* p,r bufs same size */`
  - **What:** a conditional derived from this statement — `int copy_len = MIN(p->ret_len, sizeof(r->buf)); /* p,r bufs same size */`. When the condition holds it runs `memset(r->buf, 0, sizeof(r->buf));`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x080051c0  `host_command_process`  (conf:approx)
**Signature:** `enum ec_status host_command_process(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/host_command.c:563  | rebuilt @ 0x800518c | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x080051fe** [nottaken-only] — `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r1 != constant 0.
  - rebuilt C (host_command.c:545): `if (args->command == hc_prev_cmd &&`
  - **What:** an `if` test — `if (args->command == hc_prev_cmd &&`. When the condition holds it runs `t - hc_prev_time < HCDEBUG_MAX_REPEAT_DELAY) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08005260** [taken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = a global/constant (pc-relative load). MISSING direction (taken-only) needs r3 == constant 0.
  - rebuilt C (host_command.c:366): `for (cmd = __hcmds; cmd < __hcmds_end; cmd++) {`
  - **What:** a loop condition — `for (cmd = __hcmds; cmd < __hcmds_end; cmd++) {`. When the condition holds it runs `if (command == cmd->command)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080151fe** (RW mirror) [nottaken-only] — `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r1 != constant 0.
  - rebuilt C (host_command.c:545): `if (args->command == hc_prev_cmd &&`
  - **What:** an `if` test — `if (args->command == hc_prev_cmd &&`. When the condition holds it runs `t - hc_prev_time < HCDEBUG_MAX_REPEAT_DELAY) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015260** (RW mirror) [taken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = a global/constant (pc-relative load). MISSING direction (taken-only) needs r3 == constant 0.
  - rebuilt C (host_command.c:366): `for (cmd = __hcmds; cmd < __hcmds_end; cmd++) {`
  - **What:** a loop condition — `for (cmd = __hcmds; cmd < __hcmds_end; cmd++) {`. When the condition holds it runs `if (command == cmd->command)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005430  `host_command_task`  (conf:approx)
**Signature:** `void host_command_task(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/host_command.c:389  | rebuilt @ 0x800529c | 6 uncovered (0 unreached, 6 one-dir; 4 in RW mirror)

- **0x0800549a** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (host_command.c:409): `if (t0.val - t1.val > CONFIG_HOSTCMD_RATE_LIMITING_MIN_REST)`
  - **What:** an `if` test — `if (t0.val - t1.val > CONFIG_HOSTCMD_RATE_LIMITING_MIN_REST)`. When the condition holds it runs `t_recess = t0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080054c2** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (host_command.c:417): `if (t1.val - t_recess.val > CONFIG_HOSTCMD_RATE_LIMITING_PERIOD)`
  - **What:** an `if` test — `if (t1.val - t_recess.val > CONFIG_HOSTCMD_RATE_LIMITING_PERIOD)`. When the condition holds it runs `usleep(CONFIG_HOSTCMD_RATE_LIMITING_RECESS);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015478** (RW mirror) [nottaken-only] — `lsls r3, r6, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = word [sp+0x14] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (host_command.c:402): `if ((evt & TASK_EVENT_CMD_PENDING) && pending_args) {`
  - **What:** an `if` test — `if ((evt & TASK_EVENT_CMD_PENDING) && pending_args) {`. When the condition holds it runs `pending_args->result =`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015480** (RW mirror) [nottaken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r7+0x18] (a struct/buffer field). MISSING direction (nottaken-only) needs r6 == constant 0.
  - rebuilt C (host_command.c:402 (discriminator 1)): `if ((evt & TASK_EVENT_CMD_PENDING) && pending_args) {`
  - **What:** an `if` test — `if ((evt & TASK_EVENT_CMD_PENDING) && pending_args) {`. When the condition holds it runs `pending_args->result =`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801549a** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (host_command.c:409): `if (t0.val - t1.val > CONFIG_HOSTCMD_RATE_LIMITING_MIN_REST)`
  - **What:** an `if` test — `if (t0.val - t1.val > CONFIG_HOSTCMD_RATE_LIMITING_MIN_REST)`. When the condition holds it runs `t_recess = t0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080154c2** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (host_command.c:417): `if (t1.val - t_recess.val > CONFIG_HOSTCMD_RATE_LIMITING_PERIOD)`
  - **What:** an `if` test — `if (t1.val - t_recess.val > CONFIG_HOSTCMD_RATE_LIMITING_PERIOD)`. When the condition holds it runs `usleep(CONFIG_HOSTCMD_RATE_LIMITING_RECESS);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x080054e8  `main`  (conf:approx)
**Signature:** `test_mockable __keep int main(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/main.c:37  | rebuilt @ 0x8005354 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x0801552c** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0x1c). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (main.c:123): `if (system_jumped_to_this_image()) {`
  - **What:** an `if` test — `if (system_jumped_to_this_image()) {`. When the condition holds it runs `CPRINTS("UART initialized after sysjump");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005590  `command_mem_dump`  (conf:approx)
**Signature:** `static int command_mem_dump(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/memory_commands.c:60  | rebuilt @ 0x8005400 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x080055d0** [nottaken-only] — `cmp r7, #1` then `beq`: taken when r7 == constant 1. r7 = computed (subs #1). MISSING direction (nottaken-only) needs r7 == constant 1.
  - rebuilt C (memory_commands.c:85): `if (argc < 2)`
  - **What:** an `if` test — `if (argc < 2)`. When the condition holds it runs `return EC_ERROR_PARAM_COUNT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08005606** [nottaken-only] — `cmp r4, #3` then `bhi`: taken when r4 >u constant 3. r4 = register r4. MISSING direction (nottaken-only) needs r4 >u constant 3.
  - rebuilt C (memory_commands.c:27): `switch (fmt) {`
  - **What:** a `switch` dispatch on the value — `switch (fmt) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080155d0** (RW mirror) [nottaken-only] — `cmp r7, #1` then `beq`: taken when r7 == constant 1. r7 = computed (subs #1). MISSING direction (nottaken-only) needs r7 == constant 1.
  - rebuilt C (memory_commands.c:85): `if (argc < 2)`
  - **What:** an `if` test — `if (argc < 2)`. When the condition holds it runs `return EC_ERROR_PARAM_COUNT;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015606** (RW mirror) [nottaken-only] — `cmp r4, #3` then `bhi`: taken when r4 >u constant 3. r4 = register r4. MISSING direction (nottaken-only) needs r4 >u constant 3.
  - rebuilt C (memory_commands.c:27): `switch (fmt) {`
  - **What:** a `switch` dispatch on the value — `switch (fmt) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x080057e2  `panic_txchar`  (conf:high)
**Signature:** `static int panic_txchar(void *context, int c)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/panic_output.c:31  | rebuilt @ 0x8005652 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080057f6** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (panic_output.c:36 (discriminator 1)): `while (!uart_tx_ready())`
  - **What:** a loop condition — `while (!uart_tx_ready())`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080157f6** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (panic_output.c:36 (discriminator 1)): `while (!uart_tx_ready())`
  - **What:** a loop condition — `while (!uart_tx_ready())`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08005804  `command_crash`  (conf:approx)
**Signature:** `static int command_crash(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/panic_output.c:159  | rebuilt @ 0x800574c | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x0800583e** [taken-only] — flags from `subs r6, r0, #0` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (panic_output.c:169): `if (argc >= 3 && !strcasecmp(argv[2], "unsigned"))`
  - **What:** an `if` test — `if (argc >= 3 && !strcasecmp(argv[2], "unsigned"))`. When the condition holds it runs `ccprintf("%08x", (unsigned long)1 / zero);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800588a** [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+4] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (panic_output.c:179): `ccprintf("%08x", *(volatile int *)0xcdef);`
  - **What:** a conditional derived from this statement — `ccprintf("%08x", *(volatile int *)0xcdef);`. When the condition holds it runs `} else if (!strcasecmp(argv[1], "watchdog")) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801583e** (RW mirror) [taken-only] — flags from `subs r6, r0, #0` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (panic_output.c:169): `if (argc >= 3 && !strcasecmp(argv[2], "unsigned"))`
  - **What:** an `if` test — `if (argc >= 3 && !strcasecmp(argv[2], "unsigned"))`. When the condition holds it runs `ccprintf("%08x", (unsigned long)1 / zero);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801588a** (RW mirror) [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+4] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (panic_output.c:179): `ccprintf("%08x", *(volatile int *)0xcdef);`
  - **What:** a conditional derived from this statement — `ccprintf("%08x", *(volatile int *)0xcdef);`. When the condition holds it runs `} else if (!strcasecmp(argv[1], "watchdog")) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080058b8  `command_panicinfo`  (conf:exact)
**Signature:** `static int command_panicinfo(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/panic_output.c:197  | rebuilt @ 0x8005674 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080058c8** [nottaken-only] — `lsls r3, r3, #0x1e` sets flags from a shifted value (bit test) then `bmi`. operand = byte [r4+2] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (panic_output.c:199): `ccprintf("Saved panic data:%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Saved panic data:%s\n",`. When the condition holds it runs `(pdata_ptr->flags & PANIC_DATA_FLAG_OLD_CONSOLE ?`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080158c8** (RW mirror) [nottaken-only] — `lsls r3, r3, #0x1e` sets flags from a shifted value (bit test) then `bmi`. operand = byte [r4+2] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (panic_output.c:199): `ccprintf("Saved panic data:%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Saved panic data:%s\n",`. When the condition holds it runs `(pdata_ptr->flags & PANIC_DATA_FLAG_OLD_CONSOLE ?`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800590c  `panic_printf`  (conf:approx)
**Signature:** `void panic_printf(const char *format, ...)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/panic_output.c:59  | rebuilt @ 0x80056e8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08005916** [taken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= a global/constant (pc-relative load)). r2 = word [r4+0x70] (a struct/buffer field). MISSING direction (taken-only) needs r2 == r3 (= a global/constant (pc-relative load)).
  - rebuilt C (panic_output.c:63): `uart_flush_output();`
  - **What:** a conditional derived from this statement — `uart_flush_output();`. When the condition holds it runs `va_start(args, format);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015916** (RW mirror) [taken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= a global/constant (pc-relative load)). r2 = word [r4+0x70] (a struct/buffer field). MISSING direction (taken-only) needs r2 == r3 (= a global/constant (pc-relative load)).
  - rebuilt C (panic_output.c:63): `uart_flush_output();`
  - **What:** a conditional derived from this statement — `uart_flush_output();`. When the condition holds it runs `va_start(args, format);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080059b8  `vfnprintf`  (conf:approx)
**Signature:** `int vfnprintf(int (*addchar)(void *context, int c), void *context,`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/printf.c:55  | rebuilt @ 0x800588c | 16 uncovered (0 unreached, 16 one-dir; 8 in RW mirror)

- **0x080059fa** [nottaken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == constant 0.
  - rebuilt C (printf.c:86 (discriminator 1)): `if (c == '%' || c == '\0') {`
  - **What:** an `if` test — `if (c == '%' || c == '\0') {`. When the condition holds it runs `if (addchar(context, '%'))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08005b82** [nottaken-only] — `cmp r4, #0x54` then `beq`: taken when r4 == constant 0x54. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == constant 0x54.
  - rebuilt C (printf.c:191): `v = va_arg(args, uint64_t);`
  - **What:** a conditional derived from this statement — `v = va_arg(args, uint64_t);`. When the condition holds it runs `} else {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08005bc8** [taken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= a global/constant (pc-relative load)). r5 = computed (adds r0, #0). MISSING direction (taken-only) needs r5 == r3 (= a global/constant (pc-relative load)).
  - rebuilt C (printf.c:197): `switch (c) {`
  - **What:** a `switch` dispatch on the value — `switch (c) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08005c6e** [taken-only] — `cmp r3, r7` then `ble`: taken when r3 <= r7 (= a value carried in from a preceding basic block). r3 = word [sp+0x10] (a struct/buffer field). MISSING direction (taken-only) needs r3 > r7 (= a value carried in from a preceding basic block).
  - rebuilt C (printf.c:266): `if (flags & PF_NEGATIVE)`
  - **What:** an `if` test — `if (flags & PF_NEGATIVE)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08005cb8** [nottaken-only] — `lsls r3, r3, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = word [sp+4] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (printf.c:288 (discriminator 4)): `if (addchar(context, flags & PF_PADZERO ? '0' : ' '))`
  - **What:** an `if` test — `if (addchar(context, flags & PF_PADZERO ? '0' : ' '))`. When the condition holds it runs `return EC_ERROR_OVERFLOW;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08005cde** [nottaken-only] — `cmp r4, #0x70` then `beq`: taken when r4 == constant 0x70. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == constant 0x70.
  - rebuilt C (printf.c:292): `while (*vstr && --precision >= 0)`
  - **What:** a loop condition — `while (*vstr && --precision >= 0)`. When the condition holds it runs `if (addchar(context, *vstr++))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08005cf8** [taken-only] — `cmp r3, r1` then `beq`: taken when r3 == r1 (= computed (lsls r1, #0x18)). r3 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r3 != r1 (= computed (lsls r1, #0x18)).
  - rebuilt C (printf.c:296): `if (addchar(context, ' '))`
  - **What:** an `if` test — `if (addchar(context, ' '))`. When the condition holds it runs `return EC_ERROR_OVERFLOW;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08005d7a** [taken-only] — `cmp r4, #0x54` then `bne`: taken when r4 != constant 0x54. r4 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r4 == constant 0x54.
  - rebuilt C (printf.c:197): `switch (c) {`
  - **What:** a `switch` dispatch on the value — `switch (c) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080159fa** (RW mirror) [nottaken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == constant 0.
  - rebuilt C (printf.c:86 (discriminator 1)): `if (c == '%' || c == '\0') {`
  - **What:** an `if` test — `if (c == '%' || c == '\0') {`. When the condition holds it runs `if (addchar(context, '%'))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015b82** (RW mirror) [nottaken-only] — `cmp r4, #0x54` then `beq`: taken when r4 == constant 0x54. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == constant 0x54.
  - rebuilt C (printf.c:191): `v = va_arg(args, uint64_t);`
  - **What:** a conditional derived from this statement — `v = va_arg(args, uint64_t);`. When the condition holds it runs `} else {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015bc8** (RW mirror) [taken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= a global/constant (pc-relative load)). r5 = computed (adds r0, #0). MISSING direction (taken-only) needs r5 == r3 (= a global/constant (pc-relative load)).
  - rebuilt C (printf.c:197): `switch (c) {`
  - **What:** a `switch` dispatch on the value — `switch (c) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015c6e** (RW mirror) [taken-only] — `cmp r3, r7` then `ble`: taken when r3 <= r7 (= a value carried in from a preceding basic block). r3 = word [sp+0x10] (a struct/buffer field). MISSING direction (taken-only) needs r3 > r7 (= a value carried in from a preceding basic block).
  - rebuilt C (printf.c:266): `if (flags & PF_NEGATIVE)`
  - **What:** an `if` test — `if (flags & PF_NEGATIVE)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015cb8** (RW mirror) [nottaken-only] — `lsls r3, r3, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = word [sp+4] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (printf.c:288 (discriminator 4)): `if (addchar(context, flags & PF_PADZERO ? '0' : ' '))`
  - **What:** an `if` test — `if (addchar(context, flags & PF_PADZERO ? '0' : ' '))`. When the condition holds it runs `return EC_ERROR_OVERFLOW;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015cde** (RW mirror) [nottaken-only] — `cmp r4, #0x70` then `beq`: taken when r4 == constant 0x70. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == constant 0x70.
  - rebuilt C (printf.c:292): `while (*vstr && --precision >= 0)`
  - **What:** a loop condition — `while (*vstr && --precision >= 0)`. When the condition holds it runs `if (addchar(context, *vstr++))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08015cf8** (RW mirror) [taken-only] — `cmp r3, r1` then `beq`: taken when r3 == r1 (= computed (lsls r1, #0x18)). r3 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r3 != r1 (= computed (lsls r1, #0x18)).
  - rebuilt C (printf.c:296): `if (addchar(context, ' '))`
  - **What:** an `if` test — `if (addchar(context, ' '))`. When the condition holds it runs `return EC_ERROR_OVERFLOW;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015d7a** (RW mirror) [taken-only] — `cmp r4, #0x54` then `bne`: taken when r4 != constant 0x54. r4 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r4 == constant 0x54.
  - rebuilt C (printf.c:197): `switch (c) {`
  - **What:** a `switch` dispatch on the value — `switch (c) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005da8  `queue_read_safe`  (conf:approx)
**Signature:** `static void queue_read_safe(struct queue const *q, void *dest, size_t head, size_t transfer, void *(*memcpy)(void *dest,`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue.c:171  | rebuilt @ 0x8005c8a | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08005db8** [taken-only] — `cmp r5, r3` then `bls`: taken when r5 <=u r3 (= computed (subs r3, r2)). r5 = computed (subs r4, #0). MISSING direction (taken-only) needs r5 >u r3 (= computed (subs r3, r2)).
  - rebuilt C (queue.c:172): `size_t first = MIN(transfer, q->buffer_units - head);`
  - **What:** a conditional derived from this statement — `size_t first = MIN(transfer, q->buffer_units - head);`. When the condition holds it runs `memcpy(dest,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08005dd0** [taken-only] — `cmp r5, r4` then `bhs`: taken when r5 >=u r4 (= register r4). r5 = computed (adds r3, #0). MISSING direction (taken-only) needs r5 <u r4 (= register r4).
  - rebuilt C (queue.c:178): `if (first < transfer)`
  - **What:** an `if` test — `if (first < transfer)`. When the condition holds it runs `memcpy(((uint8_t *) dest) + first * q->unit_bytes,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015db8** (RW mirror) [taken-only] — `cmp r5, r3` then `bls`: taken when r5 <=u r3 (= computed (subs r3, r2)). r5 = computed (subs r4, #0). MISSING direction (taken-only) needs r5 >u r3 (= computed (subs r3, r2)).
  - rebuilt C (queue.c:172): `size_t first = MIN(transfer, q->buffer_units - head);`
  - **What:** a conditional derived from this statement — `size_t first = MIN(transfer, q->buffer_units - head);`. When the condition holds it runs `memcpy(dest,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015dd0** (RW mirror) [taken-only] — `cmp r5, r4` then `bhs`: taken when r5 >=u r4 (= register r4). r5 = computed (adds r3, #0). MISSING direction (taken-only) needs r5 <u r4 (= register r4).
  - rebuilt C (queue.c:178): `if (first < transfer)`
  - **What:** an `if` test — `if (first < transfer)`. When the condition holds it runs `memcpy(((uint8_t *) dest) + first * q->unit_bytes,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005e16  `queue_read_safe`  (conf:approx)
**Signature:** `static void queue_read_safe(struct queue const *q, void *dest, size_t head, size_t transfer, void *(*memcpy)(void *dest,`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue.c:171  | rebuilt @ 0x8005c8a | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x08005e34** [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r1, #0). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (queue.c:174): `memcpy(dest,`
  - **What:** a conditional derived from this statement — `memcpy(dest,`. When the condition holds it runs `q->buffer + head * q->unit_bytes,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08005e3c** [unreached] — `cmp r4, r3` then `blo`: taken when r4 <u r3 (= computed (ands r7)). r4 = computed (ands r7). MISSING direction (unreached) needs r4 <u r3 (= computed (ands r7)).
  - rebuilt C (queue.c:178): `if (first < transfer)`
  - **What:** an `if` test — `if (first < transfer)`. When the condition holds it runs `memcpy(((uint8_t *) dest) + first * q->unit_bytes,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08015e34** (RW mirror) [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r1, #0). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (queue.c:174): `memcpy(dest,`
  - **What:** a conditional derived from this statement — `memcpy(dest,`. When the condition holds it runs `q->buffer + head * q->unit_bytes,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015e3c** (RW mirror) [unreached] — `cmp r4, r3` then `blo`: taken when r4 <u r3 (= computed (ands r7)). r4 = computed (ands r7). MISSING direction (unreached) needs r4 <u r3 (= computed (ands r7)).
  - rebuilt C (queue.c:178): `if (first < transfer)`
  - **What:** an `if` test — `if (first < transfer)`. When the condition holds it runs `memcpy(((uint8_t *) dest) + first * q->unit_bytes,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08005e56  `queue_advance_head`  (conf:approx)
**Signature:** `size_t queue_advance_head(struct queue const *q, size_t count)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue.c:100  | rebuilt @ 0x8005d5a | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08005e64** [taken-only] — `cmp r4, r6` then `bls`: taken when r4 <=u r6 (= computed (adds r1, #0)). r4 = computed (subs r0, #0). MISSING direction (taken-only) needs r4 >u r6 (= computed (adds r1, #0)).
  - rebuilt C (queue.c:101): `size_t transfer = MIN(count, queue_count(q));`
  - **What:** a conditional derived from this statement — `size_t transfer = MIN(count, queue_count(q));`. When the condition holds it runs `q->state->head += transfer;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015e64** (RW mirror) [taken-only] — `cmp r4, r6` then `bls`: taken when r4 <=u r6 (= computed (adds r1, #0)). r4 = computed (subs r0, #0). MISSING direction (taken-only) needs r4 >u r6 (= computed (adds r1, #0)).
  - rebuilt C (queue.c:101): `size_t transfer = MIN(count, queue_count(q));`
  - **What:** a conditional derived from this statement — `size_t transfer = MIN(count, queue_count(q));`. When the condition holds it runs `q->state->head += transfer;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005ea2  `queue_add_unit`  (conf:approx)
**Signature:** `size_t queue_add_unit(struct queue const *q, const void *src)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue.c:122  | rebuilt @ 0x8005da2 | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x08005eb4** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (queue.c:125): `if (queue_space(q) == 0)`
  - **What:** an `if` test — `if (queue_space(q) == 0)`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08005ec0** [unreached] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = word [r5+0xc] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 1.
  - rebuilt C (queue.c:128): `if (q->unit_bytes == 1)`
  - **What:** an `if` test — `if (q->unit_bytes == 1)`. When the condition holds it runs `q->buffer[tail] = *((uint8_t *) src);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08015eb4** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (queue.c:125): `if (queue_space(q) == 0)`
  - **What:** an `if` test — `if (queue_space(q) == 0)`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015ec0** (RW mirror) [unreached] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = word [r5+0xc] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 1.
  - rebuilt C (queue.c:128): `if (q->unit_bytes == 1)`
  - **What:** an `if` test — `if (q->unit_bytes == 1)`. When the condition holds it runs `q->buffer[tail] = *((uint8_t *) src);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08005edc  `queue_add_memcpy`  (conf:approx)
**Signature:** `return queue_add_memcpy(q, src, count, memcpy);`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue.c:147  | rebuilt @ 0x8005ddc | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08005f02** [taken-only] — `cmp r6, r3` then `bls`: taken when r6 <=u r3 (= computed (subs r3, r0)). r6 = computed (subs r5, #0). MISSING direction (taken-only) needs r6 >u r3 (= computed (subs r3, r0)).
  - rebuilt C (queue.c:152): `memcpy(q->buffer + tail * q->unit_bytes,`
  - **What:** a conditional derived from this statement — `memcpy(q->buffer + tail * q->unit_bytes,`. When the condition holds it runs `src,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08005f18** [taken-only] — `cmp r6, r5` then `bhs`: taken when r6 >=u r5 (= register r5). r6 = computed (adds r3, #0). MISSING direction (taken-only) needs r6 <u r5 (= register r5).
  - rebuilt C (queue.c:158): `((uint8_t const *) src) + first * q->unit_bytes,`
  - **What:** a conditional derived from this statement — `((uint8_t const *) src) + first * q->unit_bytes,`. When the condition holds it runs `(transfer - first) * q->unit_bytes);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015f02** (RW mirror) [taken-only] — `cmp r6, r3` then `bls`: taken when r6 <=u r3 (= computed (subs r3, r0)). r6 = computed (subs r5, #0). MISSING direction (taken-only) needs r6 >u r3 (= computed (subs r3, r0)).
  - rebuilt C (queue.c:152): `memcpy(q->buffer + tail * q->unit_bytes,`
  - **What:** a conditional derived from this statement — `memcpy(q->buffer + tail * q->unit_bytes,`. When the condition holds it runs `src,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015f18** (RW mirror) [taken-only] — `cmp r6, r5` then `bhs`: taken when r6 >=u r5 (= register r5). r6 = computed (adds r3, #0). MISSING direction (taken-only) needs r6 <u r5 (= register r5).
  - rebuilt C (queue.c:158): `((uint8_t const *) src) + first * q->unit_bytes,`
  - **What:** a conditional derived from this statement — `((uint8_t const *) src) + first * q->unit_bytes,`. When the condition holds it runs `(transfer - first) * q->unit_bytes);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005f36  `queue_add_unit`  (conf:approx)
**Signature:** `size_t queue_add_unit(struct queue const *q, const void *src)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue.c:122  | rebuilt @ 0x8005da2 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08005f4a** [taken-only] — `cmp r5, r6` then `bls`: taken when r5 <=u r6 (= computed (adds r2, #0)). r5 = computed (subs r0, #0). MISSING direction (taken-only) needs r5 >u r6 (= computed (adds r2, #0)).
  - rebuilt C (queue.c:128): `if (q->unit_bytes == 1)`
  - **What:** an `if` test — `if (q->unit_bytes == 1)`. When the condition holds it runs `q->buffer[tail] = *((uint8_t *) src);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015f4a** (RW mirror) [taken-only] — `cmp r5, r6` then `bls`: taken when r5 <=u r6 (= computed (adds r2, #0)). r5 = computed (subs r0, #0). MISSING direction (taken-only) needs r5 >u r6 (= computed (adds r2, #0)).
  - rebuilt C (queue.c:128): `if (q->unit_bytes == 1)`
  - **What:** an `if` test — `if (q->unit_bytes == 1)`. When the condition holds it runs `q->buffer[tail] = *((uint8_t *) src);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005f70  `queue_add_direct`  (conf:high)
**Signature:** `void queue_add_direct(struct queue_policy const *policy, size_t count)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue_policies.c:13  | rebuilt @ 0x8005ea0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08005f7e** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (queue_policies.c:17 (discriminator 1)): `if (count && direct->consumer->ops->written)`
  - **What:** an `if` test — `if (count && direct->consumer->ops->written)`. When the condition holds it runs `direct->consumer->ops->written(direct->consumer, count);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015f7e** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (queue_policies.c:17 (discriminator 1)): `if (count && direct->consumer->ops->written)`
  - **What:** an `if` test — `if (count && direct->consumer->ops->written)`. When the condition holds it runs `direct->consumer->ops->written(direct->consumer, count);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08005f84  `queue_add_direct`  (conf:exact)
**Signature:** `void queue_add_direct(struct queue_policy const *policy, size_t count)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/queue_policies.c:13  | rebuilt @ 0x8005ea0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08005f92** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (queue_policies.c:17 (discriminator 1)): `if (count && direct->consumer->ops->written)`
  - **What:** an `if` test — `if (count && direct->consumer->ops->written)`. When the condition holds it runs `direct->consumer->ops->written(direct->consumer, count);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08015f92** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (queue_policies.c:17 (discriminator 1)): `if (count && direct->consumer->ops->written)`
  - **What:** an `if` test — `if (count && direct->consumer->ops->written)`. When the condition holds it runs `direct->consumer->ops->written(direct->consumer, count);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080062c0  `command_spixfer`  (conf:approx)
**Signature:** `static int command_spixfer(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/spi_commands.c:16  | rebuilt @ 0x80061d0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08006344** [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (spi_commands.c:48): `if (!rv)`
  - **What:** an `if` test — `if (!rv)`. When the condition holds it runs `ccprintf("Data: %.*h\n", v, data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016344** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (spi_commands.c:48): `if (!rv)`
  - **What:** an `if` test — `if (!rv)`. When the condition holds it runs `ccprintf("Data: %.*h\n", v, data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800639c  `system_get_image_copy`  (conf:exact)
**Signature:** `test_mockable enum system_image_copy_t system_get_image_copy(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:338  | rebuilt @ 0x80062ac | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080063aa** [taken-only] — `cmp r1, r2` then `bls`: taken when r1 <=u r2 (= a global/constant (pc-relative load)). r1 = computed (adds r3, r2). MISSING direction (taken-only) needs r1 >u r2 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080163aa** (RW mirror) [nottaken-only] — `cmp r1, r2` then `bls`: taken when r1 <=u r2 (= a global/constant (pc-relative load)). r1 = computed (adds r3, r2). MISSING direction (nottaken-only) needs r1 <=u r2 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800642c  `command_reboot`  (conf:high)
**Signature:** `static int command_reboot(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:943  | rebuilt @ 0x800633c | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08006454** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r5+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (system.c:948 (discriminator 1)): `if (!strcasecmp(argv[i], "hard") ||`
  - **What:** an `if` test — `if (!strcasecmp(argv[i], "hard") ||`. When the condition holds it runs `!strcasecmp(argv[i], "cold")) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006460** [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r5+0] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (system.c:951): `} else if (!strcasecmp(argv[i], "soft")) {`
  - **What:** an `if` test — `} else if (!strcasecmp(argv[i], "soft")) {`. When the condition holds it runs `flags &= ~SYSTEM_RESET_HARD;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016454** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r5+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (system.c:948 (discriminator 1)): `if (!strcasecmp(argv[i], "hard") ||`
  - **What:** an `if` test — `if (!strcasecmp(argv[i], "hard") ||`. When the condition holds it runs `!strcasecmp(argv[i], "cold")) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016460** (RW mirror) [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r5+0] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (system.c:951): `} else if (!strcasecmp(argv[i], "soft")) {`
  - **What:** an `if` test — `} else if (!strcasecmp(argv[i], "soft")) {`. When the condition holds it runs `flags &= ~SYSTEM_RESET_HARD;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08006528  `host_command_vbnvcontext`  (conf:high)
**Signature:** `int host_command_vbnvcontext(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:1128  | rebuilt @ 0x8006458 | 8 uncovered (4 unreached, 4 one-dir; 4 in RW mirror)

- **0x08006542** [taken-only] — flags from `orrs r3, r2` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (system.c:1132): `switch (p->op) {`
  - **What:** a `switch` dispatch on the value — `switch (p->op) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08006546** [unreached] — `cmp r3, #1` then `beq`: taken when r3 == constant 1. r3 = computed (orrs r2). MISSING direction (unreached) needs r3 == constant 1.
  - rebuilt C (system.c:1132): `switch (p->op) {`
  - **What:** a `switch` dispatch on the value — `switch (p->op) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08006552** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (system.c:1135): `if (system_get_vbnvcontext(r->block))`
  - **What:** an `if` test — `if (system_get_vbnvcontext(r->block))`. When the condition holds it runs `return EC_RES_ERROR;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006562** [unreached] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds #4). MISSING direction (unreached) needs r0 == constant 0.
  - rebuilt C (system.c:1140): `if (system_set_vbnvcontext(p->block))`
  - **What:** an `if` test — `if (system_set_vbnvcontext(p->block))`. When the condition holds it runs `return EC_RES_ERROR;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016542** (RW mirror) [taken-only] — flags from `orrs r3, r2` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (system.c:1132): `switch (p->op) {`
  - **What:** a `switch` dispatch on the value — `switch (p->op) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016546** (RW mirror) [unreached] — `cmp r3, #1` then `beq`: taken when r3 == constant 1. r3 = computed (orrs r2). MISSING direction (unreached) needs r3 == constant 1.
  - rebuilt C (system.c:1132): `switch (p->op) {`
  - **What:** a `switch` dispatch on the value — `switch (p->op) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016552** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (system.c:1135): `if (system_get_vbnvcontext(r->block))`
  - **What:** an `if` test — `if (system_get_vbnvcontext(r->block))`. When the condition holds it runs `return EC_RES_ERROR;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016562** (RW mirror) [unreached] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds #4). MISSING direction (unreached) needs r0 == constant 0.
  - rebuilt C (system.c:1140): `if (system_set_vbnvcontext(p->block))`
  - **What:** an `if` test — `if (system_set_vbnvcontext(p->block))`. When the condition holds it runs `return EC_RES_ERROR;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080065d0  `system_print_reset_flags`  (conf:approx)
**Signature:** `void system_print_reset_flags(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:196  | rebuilt @ 0x80064d8 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x080165d8** (RW mirror) [taken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r5+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0.
  - rebuilt C (system.c:200): `if (!reset_flags) {`
  - **What:** an `if` test — `if (!reset_flags) {`. When the condition holds it runs `CPUTS("unknown");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08006634  `system_add_jump_tag`  (conf:approx)
**Signature:** `int system_add_jump_tag(uint16_t tag, int version, int size, const void *data)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:221  | rebuilt @ 0x800653c | 6 uncovered (0 unreached, 6 one-dir; 3 in RW mirror)

- **0x08006646** [nottaken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == constant 0.
  - rebuilt C (system.c:225): `if (!jdata || jdata->magic != JUMP_DATA_MAGIC)`
  - **What:** an `if` test — `if (!jdata || jdata->magic != JUMP_DATA_MAGIC)`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006654** [nottaken-only] — `cmp r4, #0xff` then `bgt`: taken when r4 > constant 0xff. r4 = computed (adds r2, #0). MISSING direction (nottaken-only) needs r4 > constant 0xff.
  - rebuilt C (system.c:229): `if (size > 255)`
  - **What:** an `if` test — `if (size > 255)`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006672** [nottaken-only] — `cmp r4, r5` then `beq`: taken when r4 == r5 (= computed (movs #0)). r4 = register r4. MISSING direction (nottaken-only) needs r4 == r5 (= computed (movs #0)).
  - rebuilt C (system.c:237): `if (size)`
  - **What:** an `if` test — `if (size)`. When the condition holds it runs `memcpy(t + 1, data, size);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016646** (RW mirror) [nottaken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == constant 0.
  - rebuilt C (system.c:225): `if (!jdata || jdata->magic != JUMP_DATA_MAGIC)`
  - **What:** an `if` test — `if (!jdata || jdata->magic != JUMP_DATA_MAGIC)`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016654** (RW mirror) [nottaken-only] — `cmp r4, #0xff` then `bgt`: taken when r4 > constant 0xff. r4 = computed (adds r2, #0). MISSING direction (nottaken-only) needs r4 > constant 0xff.
  - rebuilt C (system.c:229): `if (size > 255)`
  - **What:** an `if` test — `if (size > 255)`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016672** (RW mirror) [nottaken-only] — `cmp r4, r5` then `beq`: taken when r4 == r5 (= computed (movs #0)). r4 = register r4. MISSING direction (nottaken-only) needs r4 == r5 (= computed (movs #0)).
  - rebuilt C (system.c:237): `if (size)`
  - **What:** an `if` test — `if (size)`. When the condition holds it runs `memcpy(t + 1, data, size);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800668c  `system_get_jump_tag`  (conf:approx)
**Signature:** `const uint8_t *system_get_jump_tag(uint16_t tag, int *version, int *size)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:244  | rebuilt @ 0x8006594 | 9 uncovered (5 unreached, 4 one-dir; 5 in RW mirror)

- **0x08006694** [nottaken-only] — flags from `subs r4, r3, #0` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (system.c:244): `{`
  - **What:** a conditional derived from this statement — `{`. When the condition holds it runs `const struct jump_tag *t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080066be** [taken-only] — `cmp r3, r7` then `bne`: taken when r3 != r7 (= register r7). r3 = halfword [r0+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == r7 (= register r7).
  - rebuilt C (system.c:256): `if (t->tag != tag)`
  - **What:** an `if` test — `if (t->tag != tag)`. When the condition holds it runs `continue;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080066c2** [unreached] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = register r6. MISSING direction (unreached) needs r6 == constant 0.
  - rebuilt C (system.c:260): `if (size)`
  - **What:** an `if` test — `if (size)`. When the condition holds it runs `if (version)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080066c8** [unreached] — `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = register r5. MISSING direction (unreached) needs r5 == constant 0.
  - rebuilt C (system.c:262): `if (version)`
  - **What:** an `if` test — `if (version)`. When the condition holds it runs `return (const uint8_t *)(t + 1);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016694** (RW mirror) [nottaken-only] — flags from `subs r4, r3, #0` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (system.c:244): `{`
  - **What:** a conditional derived from this statement — `{`. When the condition holds it runs `const struct jump_tag *t;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080166a6** (RW mirror) [taken-only] — `cmp r4, r3` then `bge`: taken when r4 >= r3 (= word [sp+4] (a struct/buffer field)). r4 = computed (movs #0). MISSING direction (taken-only) needs r4 < r3 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (system.c:252): `while (used < jdata->jump_tag_total) {`
  - **What:** a loop condition — `while (used < jdata->jump_tag_total) {`. When the condition holds it runs `t = (const struct jump_tag *)(system_usable_ram_end() + used);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080166be** (RW mirror) [unreached] — `cmp r3, r7` then `bne`: taken when r3 != r7 (= register r7). r3 = halfword [r0+0] (a struct/buffer field). MISSING direction (unreached) needs r3 != r7 (= register r7).
  - rebuilt C (system.c:256): `if (t->tag != tag)`
  - **What:** an `if` test — `if (t->tag != tag)`. When the condition holds it runs `continue;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080166c2** (RW mirror) [unreached] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = register r6. MISSING direction (unreached) needs r6 == constant 0.
  - rebuilt C (system.c:260): `if (size)`
  - **What:** an `if` test — `if (size)`. When the condition holds it runs `if (version)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080166c8** (RW mirror) [unreached] — `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = register r5. MISSING direction (unreached) needs r5 == constant 0.
  - rebuilt C (system.c:262): `if (version)`
  - **What:** an `if` test — `if (version)`. When the condition holds it runs `return (const uint8_t *)(t + 1);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080066dc  `get_size`  (conf:high)
**Signature:** `static uint32_t get_size(enum system_image_copy_t copy)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:128  | rebuilt @ 0x80065e4 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080066f8** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (system.c:400 (discriminator 1)): `for (size--; size > 0 && image[size] != 0xea; size--)`
  - **What:** a loop condition — `for (size--; size > 0 && image[size] != 0xea; size--)`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080166f8** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (system.c:400 (discriminator 1)): `for (size--; size > 0 && image[size] != 0xea; size--)`
  - **What:** a loop condition — `for (size--; size > 0 && image[size] != 0xea; size--)`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800670c  `system_unsafe_to_overwrite`  (conf:approx)
**Signature:** `test_mockable int system_unsafe_to_overwrite(uint32_t offset, uint32_t size)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:408  | rebuilt @ 0x8006614 | 7 uncovered (2 unreached, 5 one-dir; 3 in RW mirror)

- **0x0800671c** [taken-only] — `cmp r0, r4` then `bls`: taken when r0 <=u r4 (= a global/constant (pc-relative load)). r0 = computed (adds r3, r0). MISSING direction (taken-only) needs r0 >u r4 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:342): `if (my_addr >= CONFIG_RW_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RW_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RW_MEM_OFF + CONFIG_RW_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08006726** [unreached] — `cmp r3, r4` then `bhi`: taken when r3 >u r4 (= a global/constant (pc-relative load)). r3 = computed (adds r3, r0). MISSING direction (unreached) needs r3 >u r4 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:427): `if ((offset >= r_offset && offset < (r_offset + r_size)) ||`
  - **What:** an `if` test — `if ((offset >= r_offset && offset < (r_offset + r_size)) ||`. When the condition holds it runs `(r_offset >= offset && r_offset < (offset + size)))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800672e** [unreached] — `cmp r2, r4` then `bls`: taken when r2 <=u r4 (= a global/constant (pc-relative load)). r2 = function argument r2. MISSING direction (unreached) needs r2 <=u r4 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:419): `r_offset = CONFIG_EC_WRITABLE_STORAGE_OFF +`
  - **What:** a conditional derived from this statement — `r_offset = CONFIG_EC_WRITABLE_STORAGE_OFF +`. When the condition holds it runs `CONFIG_RW_STORAGE_OFF;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08006744** [taken-only] — `cmp r3, r2` then `blo`: taken when r3 <u r2 (= a value carried in from a preceding basic block). r3 = computed (movs #0). MISSING direction (taken-only) needs r3 >=u r2 (= a value carried in from a preceding basic block).
  - rebuilt C (system.c:429): `return 1;`
  - **What:** a conditional derived from this statement — `return 1;`. When the condition holds it runs `else`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801671c** (RW mirror) [nottaken-only] — `cmp r0, r4` then `bls`: taken when r0 <=u r4 (= a global/constant (pc-relative load)). r0 = computed (adds r3, r0). MISSING direction (nottaken-only) needs r0 <=u r4 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:342): `if (my_addr >= CONFIG_RW_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RW_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RW_MEM_OFF + CONFIG_RW_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016726** (RW mirror) [nottaken-only] — `cmp r3, r4` then `bhi`: taken when r3 >u r4 (= a global/constant (pc-relative load)). r3 = computed (adds r3, r0). MISSING direction (nottaken-only) needs r3 >u r4 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:427): `if ((offset >= r_offset && offset < (r_offset + r_size)) ||`
  - **What:** an `if` test — `if ((offset >= r_offset && offset < (r_offset + r_size)) ||`. When the condition holds it runs `(r_offset >= offset && r_offset < (offset + size)))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016744** (RW mirror) [taken-only] — `cmp r3, r2` then `blo`: taken when r3 <u r2 (= a value carried in from a preceding basic block). r3 = computed (movs #0). MISSING direction (taken-only) needs r3 >=u r2 (= a value carried in from a preceding basic block).
  - rebuilt C (system.c:429): `return 1;`
  - **What:** a conditional derived from this statement — `return 1;`. When the condition holds it runs `else`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800675c  `system_get_image_copy`  (conf:exact)
**Signature:** `test_mockable enum system_image_copy_t system_get_image_copy(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:338  | rebuilt @ 0x8006668 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800676a** [taken-only] — `cmp r0, r1` then `bls`: taken when r0 <=u r1 (= a global/constant (pc-relative load)). r0 = computed (adds r2, r3). MISSING direction (taken-only) needs r0 >u r1 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801676a** (RW mirror) [nottaken-only] — `cmp r0, r1` then `bls`: taken when r0 <=u r1 (= a global/constant (pc-relative load)). r0 = computed (adds r2, r3). MISSING direction (nottaken-only) needs r0 <=u r1 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08006794  `command_sysinfo`  (conf:high)
**Signature:** `static int command_sysinfo(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:810  | rebuilt @ 0x80066a0 | 7 uncovered (2 unreached, 5 one-dir; 2 in RW mirror)

- **0x080067c0** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r4+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (system.c:815): `ccprintf("Jumped: %s\n", system_jumped_to_this_image() ? "yes" : "no");`
  - **What:** a ternary `?:` test — `ccprintf("Jumped: %s\n", system_jumped_to_this_image() ? "yes" : "no");`. When the condition holds it runs `ccputs("Flags: ");`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080067de** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (system.c:819): `ccputs(" locked");`
  - **What:** a conditional derived from this statement — `ccputs(" locked");`. When the condition holds it runs `if (force_locked)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080067ec** [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+0] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (system.c:821): `ccputs(" (forced)");`
  - **What:** a conditional derived from this statement — `ccputs(" (forced)");`. When the condition holds it runs `if (disable_jump)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080067fa** [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+0x14] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (system.c:823): `ccputs(" jump-disabled");`
  - **What:** a conditional derived from this statement — `ccputs(" jump-disabled");`. When the condition holds it runs `} else`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08006814** [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = byte [r4+0xc] (a struct/buffer field). MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (system.c:829): `ccprintf("Reboot at shutdown: %d\n", reboot_at_shutdown);`
  - **What:** a conditional derived from this statement — `ccprintf("Reboot at shutdown: %d\n", reboot_at_shutdown);`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080167c0** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r4+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (system.c:815): `ccprintf("Jumped: %s\n", system_jumped_to_this_image() ? "yes" : "no");`
  - **What:** a ternary `?:` test — `ccprintf("Jumped: %s\n", system_jumped_to_this_image() ? "yes" : "no");`. When the condition holds it runs `ccputs("Flags: ");`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080167fa** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+0x14] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (system.c:823): `ccputs(" jump-disabled");`
  - **What:** a conditional derived from this statement — `ccputs(" jump-disabled");`. When the condition holds it runs `} else`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08006874  `system_run_image_copy`  (conf:approx)
**Signature:** `int system_run_image_copy(enum system_image_copy_t copy)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:536  | rebuilt @ 0x800677c | 16 uncovered (6 unreached, 10 one-dir; 8 in RW mirror)

- **0x08006886** [taken-only] — `cmp r3, r1` then `bls`: taken when r3 <=u r1 (= a global/constant (pc-relative load)). r3 = computed (adds r2, r3). MISSING direction (taken-only) needs r3 >u r1 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080068a0** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (system.c:544): `if (system_is_locked()) {`
  - **What:** an `if` test — `if (system_is_locked()) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080068a6** [unreached] — `cmp r4, #1` then `bne`: taken when r4 != constant 1. r4 = computed (lsls r3, #1). MISSING direction (unreached) needs r4 != constant 1.
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080068aa** [unreached] — `cmp r5, #2` then `bne`: taken when r5 != constant 2. r5 = register r5. MISSING direction (unreached) needs r5 != constant 2.
  - rebuilt C (system.c:105): `switch (copy) {`
  - **What:** a `switch` dispatch on the value — `switch (copy) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080068b2** [unreached] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r3+0x14] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 0.
  - rebuilt C (system.c:105): `switch (copy) {`
  - **What:** a `switch` dispatch on the value — `switch (copy) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080068c8** [nottaken-only] — `cmp r4, r2` then `blo`: taken when r4 <u r2 (= computed (adds r0, #0)). r4 = word [r2+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 <u r2 (= computed (adds r0, #0)).
  - rebuilt C (system.c:107): `return CONFIG_PROGRAM_MEMORY_BASE + CONFIG_RO_MEM_OFF;`
  - **What:** a conditional derived from this statement — `return CONFIG_PROGRAM_MEMORY_BASE + CONFIG_RO_MEM_OFF;`. When the condition holds it runs `case SYSTEM_IMAGE_RW:`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080068de** [nottaken-only] — `cmp r4, r2` then `bhs`: taken when r4 >=u r2 (= computed (adds r1, r2)). r4 = register r4. MISSING direction (nottaken-only) needs r4 >=u r2 (= computed (adds r1, r2)).
  - rebuilt C (system.c:130): `return CONFIG_RO_SIZE;`
  - **What:** a conditional derived from this statement — `return CONFIG_RO_SIZE;`. When the condition holds it runs `case SYSTEM_IMAGE_RW:`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080068e2** [nottaken-only] — `cmp r5, #4` then `bhi`: taken when r5 >u constant 4. r5 = register r5. MISSING direction (nottaken-only) needs r5 >u constant 4.
  - rebuilt C (system.c:588): `if (init_addr < base || init_addr >= base + get_size(copy))`
  - **What:** an `if` test — `if (init_addr < base || init_addr >= base + get_size(copy))`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016886** (RW mirror) [nottaken-only] — `cmp r3, r1` then `bls`: taken when r3 <=u r1 (= a global/constant (pc-relative load)). r3 = computed (adds r2, r3). MISSING direction (nottaken-only) needs r3 <=u r1 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080168a0** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (system.c:544): `if (system_is_locked()) {`
  - **What:** an `if` test — `if (system_is_locked()) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080168a6** (RW mirror) [unreached] — `cmp r4, #1` then `bne`: taken when r4 != constant 1. r4 = computed (lsls r3, #1). MISSING direction (unreached) needs r4 != constant 1.
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080168aa** (RW mirror) [unreached] — `cmp r5, #2` then `bne`: taken when r5 != constant 2. r5 = register r5. MISSING direction (unreached) needs r5 != constant 2.
  - rebuilt C (system.c:105): `switch (copy) {`
  - **What:** a `switch` dispatch on the value — `switch (copy) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080168b2** (RW mirror) [unreached] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r3+0x14] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 0.
  - rebuilt C (system.c:105): `switch (copy) {`
  - **What:** a `switch` dispatch on the value — `switch (copy) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080168c8** (RW mirror) [nottaken-only] — `cmp r4, r2` then `blo`: taken when r4 <u r2 (= computed (adds r0, #0)). r4 = word [r2+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 <u r2 (= computed (adds r0, #0)).
  - rebuilt C (system.c:107): `return CONFIG_PROGRAM_MEMORY_BASE + CONFIG_RO_MEM_OFF;`
  - **What:** a conditional derived from this statement — `return CONFIG_PROGRAM_MEMORY_BASE + CONFIG_RO_MEM_OFF;`. When the condition holds it runs `case SYSTEM_IMAGE_RW:`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080168de** (RW mirror) [nottaken-only] — `cmp r4, r2` then `bhs`: taken when r4 >=u r2 (= computed (adds r1, r2)). r4 = register r4. MISSING direction (nottaken-only) needs r4 >=u r2 (= computed (adds r1, r2)).
  - rebuilt C (system.c:130): `return CONFIG_RO_SIZE;`
  - **What:** a conditional derived from this statement — `return CONFIG_RO_SIZE;`. When the condition holds it runs `case SYSTEM_IMAGE_RW:`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080168e2** (RW mirror) [nottaken-only] — `cmp r5, #4` then `bhi`: taken when r5 >u constant 4. r5 = register r5. MISSING direction (nottaken-only) needs r5 >u constant 4.
  - rebuilt C (system.c:588): `if (init_addr < base || init_addr >= base + get_size(copy))`
  - **What:** an `if` test — `if (init_addr < base || init_addr >= base + get_size(copy))`. When the condition holds it runs `return EC_ERROR_UNKNOWN;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08006964  `host_command_reboot`  (conf:approx)
**Signature:** `int host_command_reboot(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:1160  | rebuilt @ 0x8006874 | 7 uncovered (1 unreached, 6 one-dir; 2 in RW mirror)

- **0x08006996** [taken-only] — `cmp r2, #1` then `bls`: taken when r2 <=u constant 1. r2 = computed (subs r0, #1). MISSING direction (taken-only) needs r2 >u constant 1.
  - rebuilt C (system.c:1180): `if (p.cmd == EC_REBOOT_JUMP_RO ||`
  - **What:** an `if` test — `if (p.cmd == EC_REBOOT_JUMP_RO ||`. When the condition holds it runs `p.cmd == EC_REBOOT_JUMP_RW ||`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800699c** [unreached] — `cmp r0, #4` then `bne`: taken when r0 != constant 4. r0 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r0 != constant 4.
  - rebuilt C (system.c:1181): `p.cmd == EC_REBOOT_JUMP_RW ||`
  - **What:** a conditional derived from this statement — `p.cmd == EC_REBOOT_JUMP_RW ||`. When the condition holds it runs `p.cmd == EC_REBOOT_COLD ||`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080069ba** [nottaken-only] — `cmp r0, #5` then `beq`: taken when r0 == constant 5. r0 = byte [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 == constant 5.
  - rebuilt C (system.c:1191): `switch (handle_pending_reboot(p.cmd)) {`
  - **What:** a `switch` dispatch on the value — `switch (handle_pending_reboot(p.cmd)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080069be** [nottaken-only] — `cmp r0, #7` then `beq`: taken when r0 == constant 7. r0 = byte [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 == constant 7.
  - rebuilt C (system.c:1191): `switch (handle_pending_reboot(p.cmd)) {`
  - **What:** a `switch` dispatch on the value — `switch (handle_pending_reboot(p.cmd)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080069c2** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = byte [r4+0] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (system.c:1191): `switch (handle_pending_reboot(p.cmd)) {`
  - **What:** a `switch` dispatch on the value — `switch (handle_pending_reboot(p.cmd)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080169be** (RW mirror) [nottaken-only] — `cmp r0, #7` then `beq`: taken when r0 == constant 7. r0 = byte [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 == constant 7.
  - rebuilt C (system.c:1191): `switch (handle_pending_reboot(p.cmd)) {`
  - **What:** a `switch` dispatch on the value — `switch (handle_pending_reboot(p.cmd)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080169c2** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = byte [r4+0] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (system.c:1191): `switch (handle_pending_reboot(p.cmd)) {`
  - **What:** a `switch` dispatch on the value — `switch (handle_pending_reboot(p.cmd)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080069d8  `command_sysjump`  (conf:approx)
**Signature:** `static int command_sysjump(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:902  | rebuilt @ 0x80068e8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08006a2e** [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (system.c:924): `if (system_is_locked())`
  - **What:** an `if` test — `if (system_is_locked())`. When the condition holds it runs `return EC_ERROR_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016a2e** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (system.c:924): `if (system_is_locked())`
  - **What:** an `if` test — `if (system_is_locked())`. When the condition holds it runs `return EC_ERROR_ACCESS_DENIED;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08006a7c  `system_get_version`  (conf:approx)
**Signature:** `const char *system_get_version(enum system_image_copy_t copy)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:602  | rebuilt @ 0x800698c | 8 uncovered (0 unreached, 8 one-dir; 4 in RW mirror)

- **0x08006a8c** [taken-only] — `cmp r2, r3` then `bls`: taken when r2 <=u r3 (= a global/constant (pc-relative load)). r2 = computed (adds r5, r3). MISSING direction (taken-only) needs r2 >u r3 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08006aa4** [nottaken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = computed (lsls r4, #1). MISSING direction (nottaken-only) needs r4 == constant 0.
  - rebuilt C (system.c:616): `return "";`
  - **What:** a conditional derived from this statement — `return "";`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006afa** [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= computed (orrs r2)). r1 = computed (orrs r3). MISSING direction (nottaken-only) needs r1 != r3 (= computed (orrs r2)).
  - rebuilt C (system.c:647): `if (v->cookie1 == version_data.cookie1 &&`
  - **What:** an `if` test — `if (v->cookie1 == version_data.cookie1 &&`. When the condition holds it runs `v->cookie2 == version_data.cookie2)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006b40** [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= computed (orrs r2)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 != r3 (= computed (orrs r2)).
  - rebuilt C (system.c:647 (discriminator 1)): `if (v->cookie1 == version_data.cookie1 &&`
  - **What:** an `if` test — `if (v->cookie1 == version_data.cookie1 &&`. When the condition holds it runs `v->cookie2 == version_data.cookie2)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016a8c** (RW mirror) [nottaken-only] — `cmp r2, r3` then `bls`: taken when r2 <=u r3 (= a global/constant (pc-relative load)). r2 = computed (adds r5, r3). MISSING direction (nottaken-only) needs r2 <=u r3 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016aa4** (RW mirror) [nottaken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = computed (lsls r4, #1). MISSING direction (nottaken-only) needs r4 == constant 0.
  - rebuilt C (system.c:616): `return "";`
  - **What:** a conditional derived from this statement — `return "";`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016afa** (RW mirror) [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= computed (orrs r2)). r1 = computed (orrs r3). MISSING direction (nottaken-only) needs r1 != r3 (= computed (orrs r2)).
  - rebuilt C (system.c:647): `if (v->cookie1 == version_data.cookie1 &&`
  - **What:** an `if` test — `if (v->cookie1 == version_data.cookie1 &&`. When the condition holds it runs `v->cookie2 == version_data.cookie2)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016b40** (RW mirror) [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= computed (orrs r2)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 != r3 (= computed (orrs r2)).
  - rebuilt C (system.c:647 (discriminator 1)): `if (v->cookie1 == version_data.cookie1 &&`
  - **What:** an `if` test — `if (v->cookie1 == version_data.cookie1 &&`. When the condition holds it runs `v->cookie2 == version_data.cookie2)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08006b6c  `host_command_get_version`  (conf:approx)
**Signature:** `static int host_command_get_version(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:1056  | rebuilt @ 0x8006a78 | 4 uncovered (1 unreached, 3 one-dir; 2 in RW mirror)

- **0x08006bb2** [taken-only] — `cmp ip, r7` then `bls`: taken when ip <=u r7 (= a global/constant (pc-relative load)). ip = computed (mov r3). MISSING direction (taken-only) needs ip >u r7 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08006bbc** [unreached] — `cmp r2, r7` then `bhi`: taken when r2 >u r7 (= a global/constant (pc-relative load)). r2 = computed (adds r2, r7). MISSING direction (unreached) needs r2 >u r7 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:342): `if (my_addr >= CONFIG_RW_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RW_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RW_MEM_OFF + CONFIG_RW_SIZE))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016bb2** (RW mirror) [nottaken-only] — `cmp ip, r7` then `bls`: taken when ip <=u r7 (= a global/constant (pc-relative load)). ip = computed (mov r3). MISSING direction (nottaken-only) needs ip <=u r7 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:338): `if (my_addr >= CONFIG_RO_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RO_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RO_MEM_OFF + CONFIG_RO_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016bbc** (RW mirror) [nottaken-only] — `cmp r2, r7` then `bhi`: taken when r2 >u r7 (= a global/constant (pc-relative load)). r2 = computed (adds r2, r7). MISSING direction (nottaken-only) needs r2 >u r7 (= a global/constant (pc-relative load)).
  - rebuilt C (system.c:342): `if (my_addr >= CONFIG_RW_MEM_OFF &&`
  - **What:** an `if` test — `if (my_addr >= CONFIG_RW_MEM_OFF &&`. When the condition holds it runs `my_addr < (CONFIG_RW_MEM_OFF + CONFIG_RW_SIZE))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08006bec  `command_sysinfo`  (conf:approx)
**Signature:** `static int command_sysinfo(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:810  | rebuilt @ 0x80066a0 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08006c4a** [taken-only] — `cmp r0, #0x31` then `bgt`: taken when r0 > constant 0x31. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 <= constant 0x31.
  - rebuilt C (system.c:821): `ccputs(" (forced)");`
  - **What:** a conditional derived from this statement — `ccputs(" (forced)");`. When the condition holds it runs `if (disable_jump)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08006c7c** [taken-only] — `cmp r3, #0x76` then `bne`: taken when r3 != constant 0x76. r3 = byte [r4+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0x76.
  - rebuilt C (system.c:832): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `DECLARE_CONSOLE_COMMAND(sysinfo, command_sysinfo,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016c4a** (RW mirror) [taken-only] — `cmp r0, #0x31` then `bgt`: taken when r0 > constant 0x31. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 <= constant 0x31.
  - rebuilt C (system.c:821): `ccputs(" (forced)");`
  - **What:** a conditional derived from this statement — `ccputs(" (forced)");`. When the condition holds it runs `if (disable_jump)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016c7c** (RW mirror) [taken-only] — `cmp r3, #0x76` then `bne`: taken when r3 != constant 0x76. r3 = byte [r4+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0x76.
  - rebuilt C (system.c:832): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `DECLARE_CONSOLE_COMMAND(sysinfo, command_sysinfo,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08006ce4  `system_common_pre_init`  (conf:high)
**Signature:** `void system_common_pre_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/system.c:680  | rebuilt @ 0x8006b68 | 10 uncovered (6 unreached, 4 one-dir; 8 in RW mirror)

- **0x08006d12** [nottaken-only] — `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = word [r0+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 <= constant 0.
  - rebuilt C (system.c:708 (discriminator 1)): `if (jdata->magic == JUMP_DATA_MAGIC &&`
  - **What:** an `if` test — `if (jdata->magic == JUMP_DATA_MAGIC &&`. When the condition holds it runs `jdata->version >= 1 &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006d40** [nottaken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r0+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r6 == constant 0.
  - rebuilt C (system.c:733 (discriminator 1)): `if (delta && jdata->jump_tag_total) {`
  - **What:** an `if` test — `if (delta && jdata->jump_tag_total) {`. When the condition holds it runs `uint8_t *d = (uint8_t *)system_usable_ram_end();`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016d12** (RW mirror) [nottaken-only] — `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = word [r0+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 <= constant 0.
  - rebuilt C (system.c:708 (discriminator 1)): `if (jdata->magic == JUMP_DATA_MAGIC &&`
  - **What:** an `if` test — `if (jdata->magic == JUMP_DATA_MAGIC &&`. When the condition holds it runs `jdata->version >= 1 &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016d18** (RW mirror) [taken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r4+8] (a struct/buffer field). MISSING direction (taken-only) needs r2 == constant 0.
  - rebuilt C (system.c:709): `jdata->version >= 1 &&`
  - **What:** a conditional derived from this statement — `jdata->version >= 1 &&`. When the condition holds it runs `reset_flags == 0) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016d2a** (RW mirror) [unreached] — `cmp r3, #1` then `beq`: taken when r3 == constant 1. r3 = function argument r3. MISSING direction (unreached) needs r3 == constant 1.
  - rebuilt C (system.c:726): `if (jdata->version == 1)`
  - **What:** an `if` test — `if (jdata->version == 1)`. When the condition holds it runs `delta = 0;  /* No tags in v1, so no need for move */`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016d2e** (RW mirror) [unreached] — `cmp r3, #2` then `beq`: taken when r3 == constant 2. r3 = function argument r3. MISSING direction (unreached) needs r3 == constant 2.
  - rebuilt C (system.c:728): `else if (jdata->version == 2)`
  - **What:** an `if` test — `else if (jdata->version == 2)`. When the condition holds it runs `delta = sizeof(struct jump_data) - JUMP_DATA_SIZE_V2;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016d36** (RW mirror) [unreached] — flags from `subs r5, r5, r3` then `bne`; MISSING direction (unreached) needs the result to make `bne` go the other way
  - rebuilt C (system.c:733): `if (delta && jdata->jump_tag_total) {`
  - **What:** an `if` test — `if (delta && jdata->jump_tag_total) {`. When the condition holds it runs `uint8_t *d = (uint8_t *)system_usable_ram_end();`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016d40** (RW mirror) [unreached] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r0+8] (a struct/buffer field). MISSING direction (unreached) needs r6 == constant 0.
  - rebuilt C (system.c:733 (discriminator 1)): `if (delta && jdata->jump_tag_total) {`
  - **What:** an `if` test — `if (delta && jdata->jump_tag_total) {`. When the condition holds it runs `uint8_t *d = (uint8_t *)system_usable_ram_end();`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016d56** (RW mirror) [unreached] — `cmp r1, #1` then `bgt`: taken when r1 > constant 1. r1 = word [r3+0x10] (a struct/buffer field). MISSING direction (unreached) needs r1 > constant 1.
  - rebuilt C (system.c:739): `if (jdata->version < 2)`
  - **What:** an `if` test — `if (jdata->version < 2)`. When the condition holds it runs `jdata->jump_tag_total = 0;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016d5e** (RW mirror) [unreached] — `cmp r1, #2` then `bne`: taken when r1 != constant 2. r1 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r1 != constant 2.
  - rebuilt C (system.c:743): `if (jdata->version < 3)`
  - **What:** an `if` test — `if (jdata->version < 3)`. When the condition holds it runs `jdata->reserved0 = 0;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08006dcc  `host_command_console_snapshot`  (conf:approx)
**Signature:** `static int host_command_console_snapshot(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:331  | rebuilt @ 0x8006f4c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08006df2** [nottaken-only] — `cmp r1, r2` then `blo`: taken when r1 <u r2 (= word [r3+0x30] (a struct/buffer field)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 <u r2 (= word [r3+0x30] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:350): `if (tx_buf[tx_snapshot_tail])`
  - **What:** an `if` test — `if (tx_buf[tx_snapshot_tail])`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016df2** (RW mirror) [nottaken-only] — `cmp r1, r2` then `blo`: taken when r1 <u r2 (= word [r3+0x30] (a struct/buffer field)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 <u r2 (= word [r3+0x30] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:350): `if (tx_buf[tx_snapshot_tail])`
  - **What:** an `if` test — `if (tx_buf[tx_snapshot_tail])`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08006e30  `usleep`  (conf:approx)
**Signature:** `void usleep(unsigned us)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/timer.c:152  | rebuilt @ 0x8006cf4 | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x08006e54** [nottaken-only] — `cmp r0, r5` then `bhs`: taken when r0 >=u r5 (= a value carried in from a preceding basic block). r0 = computed (subs r0, r6). MISSING direction (nottaken-only) needs r0 >=u r5 (= a value carried in from a preceding basic block).
  - rebuilt C (timer.c:162 (discriminator 1)): `ASSERT(us);`
  - **What:** a conditional derived from this statement — `ASSERT(us);`. When the condition holds it runs `do {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006e7a** [unreached] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r4 != constant 0.
  - rebuilt C (atomic.h:37): `ATOMIC_OP(orr, addr, bits);`
  - **What:** a conditional derived from this statement — `ATOMIC_OP(orr, addr, bits);`. When the condition holds it runs `static inline void atomic_add(uint32_t volatile *addr, uint32_t value)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016e54** (RW mirror) [nottaken-only] — `cmp r0, r5` then `bhs`: taken when r0 >=u r5 (= a value carried in from a preceding basic block). r0 = computed (subs r0, r6). MISSING direction (nottaken-only) needs r0 >=u r5 (= a value carried in from a preceding basic block).
  - rebuilt C (timer.c:162 (discriminator 1)): `ASSERT(us);`
  - **What:** a conditional derived from this statement — `ASSERT(us);`. When the condition holds it runs `do {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016e7a** (RW mirror) [unreached] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r4 != constant 0.
  - rebuilt C (atomic.h:37): `ATOMIC_OP(orr, addr, bits);`
  - **What:** a conditional derived from this statement — `ATOMIC_OP(orr, addr, bits);`. When the condition holds it runs `static inline void atomic_add(uint32_t volatile *addr, uint32_t value)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08006e80  `get_time`  (conf:high)
**Signature:** `timestamp_t get_time(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/timer.c:175  | rebuilt @ 0x8006d60 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08006e90** [taken-only] — `cmp r7, r5` then `beq`: taken when r7 == r5 (= word [r6+0x30] (a struct/buffer field)). r7 = word [r6+0x30] (a struct/buffer field). MISSING direction (taken-only) needs r7 != r5 (= word [r6+0x30] (a struct/buffer field)).
  - rebuilt C (timer.c:179): `if (ts.le.hi != clksrc_high) {`
  - **What:** an `if` test — `if (ts.le.hi != clksrc_high) {`. When the condition holds it runs `ts.le.hi = clksrc_high;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016e90** (RW mirror) [taken-only] — `cmp r7, r5` then `beq`: taken when r7 == r5 (= word [r6+0x30] (a struct/buffer field)). r7 = word [r6+0x30] (a struct/buffer field). MISSING direction (taken-only) needs r7 != r5 (= word [r6+0x30] (a struct/buffer field)).
  - rebuilt C (timer.c:179): `if (ts.le.hi != clksrc_high) {`
  - **What:** an `if` test — `if (ts.le.hi != clksrc_high) {`. When the condition holds it runs `ts.le.hi = clksrc_high;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08006ec4  `process_timers`  (conf:approx)
**Signature:** `void process_timers(int overflow)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/timer.c:53  | rebuilt @ 0x8006da4 | 12 uncovered (0 unreached, 12 one-dir; 7 in RW mirror)

- **0x08006f0e** [nottaken-only] — `cmp r2, r0` then `bhi`: taken when r2 >u r0 (= word [sp+4] (a struct/buffer field)). r2 = word [r2+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 >u r0 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (timer.c:71): `if (timer_deadline[tskid].val <= now.val)`
  - **What:** an `if` test — `if (timer_deadline[tskid].val <= now.val)`. When the condition holds it runs `expire_timer(tskid);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006f42** [nottaken-only] — `cmp ip, r0` then `bne`: taken when ip != r0 (= word [sp+4] (a struct/buffer field)). ip = computed (mov r0). MISSING direction (nottaken-only) needs ip != r0 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (timer.c:73): `else if ((timer_deadline[tskid].le.hi ==`
  - **What:** an `if` test — `else if ((timer_deadline[tskid].le.hi ==`. When the condition holds it runs `now.le.hi) &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006f60** [nottaken-only] — bne flag set by an earlier op; missing direction needs the condition to be !=
  - rebuilt C (timer.c:82): `} while (timer_running & ~running_t0);`
  - **What:** a conditional derived from this statement — `} while (timer_running & ~running_t0);`. When the condition holds it runs `if (next.le.hi == 0xffffffff) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006f84** [nottaken-only] — `cmp r6, r3` then `bhi`: taken when r6 >u r3 (= word [sp+0x14] (a struct/buffer field)). r6 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r6 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (timer.c:93): `} while (next.val <= get_time().val);`
  - **What:** a conditional derived from this statement — `} while (next.val <= get_time().val);`. When the condition holds it runs `#ifndef CONFIG_HW_SPECIFIC_UDELAY`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08006f86** [nottaken-only] — `cmp r6, r3` then `bne`: taken when r6 != r3 (= word [sp+0x14] (a struct/buffer field)). r6 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r6 != r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (timer.c:93): `} while (next.val <= get_time().val);`
  - **What:** a conditional derived from this statement — `} while (next.val <= get_time().val);`. When the condition holds it runs `#ifndef CONFIG_HW_SPECIFIC_UDELAY`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016f0e** (RW mirror) [nottaken-only] — `cmp r2, r0` then `bhi`: taken when r2 >u r0 (= word [sp+4] (a struct/buffer field)). r2 = word [r2+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 >u r0 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (timer.c:71): `if (timer_deadline[tskid].val <= now.val)`
  - **What:** an `if` test — `if (timer_deadline[tskid].val <= now.val)`. When the condition holds it runs `expire_timer(tskid);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016f16** (RW mirror) [taken-only] — `cmp r1, r0` then `bhi`: taken when r1 >u r0 (= word [sp+0xc] (a struct/buffer field)). r1 = word [r2+8] (a struct/buffer field). MISSING direction (taken-only) needs r1 <=u r0 (= word [sp+0xc] (a struct/buffer field)).
  - rebuilt C (timer.c:71): `if (timer_deadline[tskid].val <= now.val)`
  - **What:** an `if` test — `if (timer_deadline[tskid].val <= now.val)`. When the condition holds it runs `expire_timer(tskid);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016f42** (RW mirror) [nottaken-only] — `cmp ip, r0` then `bne`: taken when ip != r0 (= word [sp+4] (a struct/buffer field)). ip = computed (mov r0). MISSING direction (nottaken-only) needs ip != r0 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (timer.c:73): `else if ((timer_deadline[tskid].le.hi ==`
  - **What:** an `if` test — `else if ((timer_deadline[tskid].le.hi ==`. When the condition holds it runs `now.le.hi) &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016f60** (RW mirror) [nottaken-only] — bne flag set by an earlier op; missing direction needs the condition to be !=
  - rebuilt C (timer.c:82): `} while (timer_running & ~running_t0);`
  - **What:** a conditional derived from this statement — `} while (timer_running & ~running_t0);`. When the condition holds it runs `if (next.le.hi == 0xffffffff) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016f84** (RW mirror) [nottaken-only] — `cmp r6, r3` then `bhi`: taken when r6 >u r3 (= word [sp+0x14] (a struct/buffer field)). r6 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r6 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (timer.c:93): `} while (next.val <= get_time().val);`
  - **What:** a conditional derived from this statement — `} while (next.val <= get_time().val);`. When the condition holds it runs `#ifndef CONFIG_HW_SPECIFIC_UDELAY`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016f86** (RW mirror) [nottaken-only] — `cmp r6, r3` then `bne`: taken when r6 != r3 (= word [sp+0x14] (a struct/buffer field)). r6 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r6 != r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (timer.c:93): `} while (next.val <= get_time().val);`
  - **What:** a conditional derived from this statement — `} while (next.val <= get_time().val);`. When the condition holds it runs `#ifndef CONFIG_HW_SPECIFIC_UDELAY`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08016f8a** (RW mirror) [nottaken-only] — `cmp r4, r2` then `bls`: taken when r4 <=u r2 (= word [sp+0x10] (a struct/buffer field)). r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 <=u r2 (= word [sp+0x10] (a struct/buffer field)).
  - rebuilt C (timer.c:94): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `#ifndef CONFIG_HW_SPECIFIC_UDELAY`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08006fd8  `timer_init`  (conf:approx)
**Signature:** `void timer_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/timer.c:227  | rebuilt @ 0x8006eb8 | 6 uncovered (4 unreached, 2 one-dir; 3 in RW mirror)

- **0x08006fe8** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a global/constant (pc-relative load). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (timer.c:236): `if (ts && version == 1 && size == sizeof(timestamp_t)) {`
  - **What:** an `if` test — `if (ts && version == 1 && size == sizeof(timestamp_t)) {`. When the condition holds it runs `clksrc_high = ts->le.hi;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08006fee** [unreached] — `cmp r3, #1` then `bne`: taken when r3 != constant 1. r3 = word [sp+4] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 1.
  - rebuilt C (timer.c:236 (discriminator 1)): `if (ts && version == 1 && size == sizeof(timestamp_t)) {`
  - **What:** an `if` test — `if (ts && version == 1 && size == sizeof(timestamp_t)) {`. When the condition holds it runs `clksrc_high = ts->le.hi;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08006ff4** [unreached] — `cmp r3, #8` then `bne`: taken when r3 != constant 8. r3 = word [sp+0] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 8.
  - rebuilt C (timer.c:236 (discriminator 2)): `if (ts && version == 1 && size == sizeof(timestamp_t)) {`
  - **What:** an `if` test — `if (ts && version == 1 && size == sizeof(timestamp_t)) {`. When the condition holds it runs `clksrc_high = ts->le.hi;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016fe8** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a global/constant (pc-relative load). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (timer.c:236): `if (ts && version == 1 && size == sizeof(timestamp_t)) {`
  - **What:** an `if` test — `if (ts && version == 1 && size == sizeof(timestamp_t)) {`. When the condition holds it runs `clksrc_high = ts->le.hi;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08016fee** (RW mirror) [unreached] — `cmp r3, #1` then `bne`: taken when r3 != constant 1. r3 = word [sp+4] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 1.
  - rebuilt C (timer.c:236 (discriminator 1)): `if (ts && version == 1 && size == sizeof(timestamp_t)) {`
  - **What:** an `if` test — `if (ts && version == 1 && size == sizeof(timestamp_t)) {`. When the condition holds it runs `clksrc_high = ts->le.hi;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08016ff4** (RW mirror) [unreached] — `cmp r3, #8` then `bne`: taken when r3 != constant 8. r3 = word [sp+0] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 8.
  - rebuilt C (timer.c:236 (discriminator 2)): `if (ts && version == 1 && size == sizeof(timestamp_t)) {`
  - **What:** an `if` test — `if (ts && version == 1 && size == sizeof(timestamp_t)) {`. When the condition holds it runs `clksrc_high = ts->le.hi;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08007014  `__tx_char`  (conf:high)
**Signature:** `static int __tx_char(void *context, int c)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:60  | rebuilt @ 0x8006ef4 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x0800702a** [taken-only] — `cmp r2, r1` then `bne`: taken when r2 != r1 (= word [r3+4] (a struct/buffer field)). r2 = computed (lsrs r2, #0x17). MISSING direction (taken-only) needs r2 == r1 (= word [r3+4] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:74): `if (tx_buf_next == tx_buf_tail)`
  - **What:** an `if` test — `if (tx_buf_next == tx_buf_tail)`. When the condition holds it runs `return 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08007038** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (uart_buffering.c:64 (discriminator 1)): `if (c == '\n' && __tx_char(NULL, '\r'))`
  - **What:** an `if` test — `if (c == '\n' && __tx_char(NULL, '\r'))`. When the condition holds it runs `return 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801702a** (RW mirror) [taken-only] — `cmp r2, r1` then `bne`: taken when r2 != r1 (= word [r3+4] (a struct/buffer field)). r2 = computed (lsrs r2, #0x17). MISSING direction (taken-only) needs r2 == r1 (= word [r3+4] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:74): `if (tx_buf_next == tx_buf_tail)`
  - **What:** an `if` test — `if (tx_buf_next == tx_buf_tail)`. When the condition holds it runs `return 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017038** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (uart_buffering.c:64 (discriminator 1)): `if (c == '\n' && __tx_char(NULL, '\r'))`
  - **What:** an `if` test — `if (c == '\n' && __tx_char(NULL, '\r'))`. When the condition holds it runs `return 1;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800706c  `host_command_console_read`  (conf:approx)
**Signature:** `static int host_command_console_read(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:398  | rebuilt @ 0x8006fec | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08007088** [nottaken-only] — `cmp r3, r1` then `beq`: taken when r3 == r1 (= word [r2+0] (a struct/buffer field)). r3 = computed (lsrs r3, #0x17). MISSING direction (nottaken-only) needs r3 == r1 (= word [r2+0] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:411): `if (p->subcmd == CONSOLE_READ_NEXT)`
  - **What:** an `if` test — `if (p->subcmd == CONSOLE_READ_NEXT)`. When the condition holds it runs `return console_read_helper(args, &tx_snapshot_tail);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017088** (RW mirror) [nottaken-only] — `cmp r3, r1` then `beq`: taken when r3 == r1 (= word [r2+0] (a struct/buffer field)). r3 = computed (lsrs r3, #0x17). MISSING direction (nottaken-only) needs r3 == r1 (= word [r2+0] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:411): `if (p->subcmd == CONSOLE_READ_NEXT)`
  - **What:** an `if` test — `if (p->subcmd == CONSOLE_READ_NEXT)`. When the condition holds it runs `return console_read_helper(args, &tx_snapshot_tail);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x080070a8  `console_read_helper`  (conf:exact)
**Signature:** `static int console_read_helper(struct host_cmd_handler_args *args, int *tail)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:367  | rebuilt @ 0x8006f98 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x080070ba** [taken-only] — `cmp r3, r5` then `bne`: taken when r3 != r5 (= word [r4+0xc] (a struct/buffer field)). r3 = word [r1+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == r5 (= word [r4+0xc] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:375): `while (*tail != tx_snapshot_head &&`
  - **What:** a loop condition — `while (*tail != tx_snapshot_head &&`. When the condition holds it runs `args->response_size < args->response_max - 1) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080070d8** [nottaken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = byte [r3+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r6 == constant 0.
  - rebuilt C (uart_buffering.c:382): `if (tx_buf[*tail]) {`
  - **What:** an `if` test — `if (tx_buf[*tail]) {`. When the condition holds it runs `args->response_size++;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080170ba** (RW mirror) [taken-only] — `cmp r3, r5` then `bne`: taken when r3 != r5 (= word [r4+0xc] (a struct/buffer field)). r3 = word [r1+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == r5 (= word [r4+0xc] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:375): `while (*tail != tx_snapshot_head &&`
  - **What:** a loop condition — `while (*tail != tx_snapshot_head &&`. When the condition holds it runs `args->response_size < args->response_max - 1) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080170d8** (RW mirror) [nottaken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = byte [r3+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r6 == constant 0.
  - rebuilt C (uart_buffering.c:382): `if (tx_buf[*tail]) {`
  - **What:** an `if` test — `if (tx_buf[*tail]) {`. When the condition holds it runs `args->response_size++;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x080070fc  `host_command_console_read`  (conf:high)
**Signature:** `static int host_command_console_read(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:398  | rebuilt @ 0x8006fec | 6 uncovered (4 unreached, 2 one-dir; 3 in RW mirror)

- **0x08007112** [taken-only] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r2 == constant 1.
  - rebuilt C (uart_buffering.c:411): `if (p->subcmd == CONSOLE_READ_NEXT)`
  - **What:** an `if` test — `if (p->subcmd == CONSOLE_READ_NEXT)`. When the condition holds it runs `return console_read_helper(args, &tx_snapshot_tail);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800711a** [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (uart_buffering.c:413): `else if (p->subcmd == CONSOLE_READ_RECENT)`
  - **What:** an `if` test — `else if (p->subcmd == CONSOLE_READ_RECENT)`. When the condition holds it runs `return console_read_helper(args,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800711e** [unreached] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 1.
  - rebuilt C (uart_buffering.c:414): `return console_read_helper(args,`
  - **What:** a conditional derived from this statement — `return console_read_helper(args,`. When the condition holds it runs `&tx_last_snapshot_head);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08017112** (RW mirror) [taken-only] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r2 == constant 1.
  - rebuilt C (uart_buffering.c:411): `if (p->subcmd == CONSOLE_READ_NEXT)`
  - **What:** an `if` test — `if (p->subcmd == CONSOLE_READ_NEXT)`. When the condition holds it runs `return console_read_helper(args, &tx_snapshot_tail);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801711a** (RW mirror) [unreached] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
  - rebuilt C (uart_buffering.c:413): `else if (p->subcmd == CONSOLE_READ_RECENT)`
  - **What:** an `if` test — `else if (p->subcmd == CONSOLE_READ_RECENT)`. When the condition holds it runs `return console_read_helper(args,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801711e** (RW mirror) [unreached] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 1.
  - rebuilt C (uart_buffering.c:414): `return console_read_helper(args,`
  - **What:** a conditional derived from this statement — `return console_read_helper(args,`. When the condition holds it runs `&tx_last_snapshot_head);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08007134  `uart_process_input`  (conf:approx)
**Signature:** `void uart_process_input(void);`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:195  | rebuilt @ 0x800707c | 5 uncovered (0 unreached, 5 one-dir; 3 in RW mirror)

- **0x08007140** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (uart_buffering.c:199): `while (uart_rx_available()) {`
  - **What:** a loop condition — `while (uart_rx_available()) {`. When the condition holds it runs `int c = uart_read_char();`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08007168** [nottaken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= word [r3+0] (a struct/buffer field)). r2 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r3 (= word [r3+0] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:218): `console_has_input();`
  - **What:** a conditional derived from this statement — `console_has_input();`. When the condition holds it runs `#endif /* !CONFIG_UART_RX_DMA */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017140** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (uart_buffering.c:199): `while (uart_rx_available()) {`
  - **What:** a loop condition — `while (uart_rx_available()) {`. When the condition holds it runs `int c = uart_read_char();`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017148** (RW mirror) [taken-only] — `cmp r1, r2` then `beq`: taken when r1 == r2 (= word [r4+4] (a struct/buffer field)). r1 = word [r4+0] (a struct/buffer field). MISSING direction (taken-only) needs r1 != r2 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:201): `int rx_buf_next = RX_BUF_NEXT(rx_buf_head);`
  - **What:** a conditional derived from this statement — `int rx_buf_next = RX_BUF_NEXT(rx_buf_head);`. When the condition holds it runs `#ifdef CONFIG_UART_INPUT_FILTER`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017168** (RW mirror) [nottaken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= word [r3+0] (a struct/buffer field)). r2 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r3 (= word [r3+0] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:218): `console_has_input();`
  - **What:** a conditional derived from this statement — `console_has_input();`. When the condition holds it runs `#endif /* !CONFIG_UART_RX_DMA */`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08007174  `uart_process_input`  (conf:high)
**Signature:** `void uart_process_input(void);`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:195  | rebuilt @ 0x800707c | 3 uncovered (1 unreached, 2 one-dir; 3 in RW mirror)

- **0x08017180** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (uart_buffering.c:199): `while (uart_rx_available()) {`
  - **What:** a loop condition — `while (uart_rx_available()) {`. When the condition holds it runs `int c = uart_read_char();`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017192** (RW mirror) [unreached] — `cmp r3, r2` then `beq`: taken when r3 == r2 (= word [r4+0x1c] (a struct/buffer field)). r3 = computed (ands r2). MISSING direction (unreached) needs r3 == r2 (= word [r4+0x1c] (a struct/buffer field)).
  - rebuilt C (uart_buffering.c:209): `if (rx_buf_next != rx_buf_tail) {`
  - **What:** an `if` test — `if (rx_buf_next != rx_buf_tail) {`. When the condition holds it runs `rx_buf[rx_buf_head] = c;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080171a6** (RW mirror) [taken-only] — `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 != constant 0.
  - rebuilt C (uart_buffering.c:217): `if (got_input)`
  - **What:** an `if` test — `if (got_input)`. When the condition holds it runs `console_has_input();`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080071d0  `uart_puts`  (conf:high)
**Signature:** `int uart_puts(const char *outstr)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:233  | rebuilt @ 0x80070d8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080071e4** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (uart_buffering.c:236): `if (__tx_char(NULL, *outstr++) != 0)`
  - **What:** an `if` test — `if (__tx_char(NULL, *outstr++) != 0)`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080171e4** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (uart_buffering.c:236): `if (__tx_char(NULL, *outstr++) != 0)`
  - **What:** an `if` test — `if (__tx_char(NULL, *outstr++) != 0)`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08007214  `uart_flush_output`  (conf:exact)
**Signature:** `void uart_flush_output(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/uart_buffering.c:267  | rebuilt @ 0x800711c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800722e** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (uart_buffering.c:274): `if (in_interrupt_context()) {`
  - **What:** an `if` test — `if (in_interrupt_context()) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801722e** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (uart_buffering.c:274): `if (in_interrupt_context()) {`
  - **What:** an `if` test — `if (in_interrupt_context()) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08007274  `stub_pd_board_check_request`  (conf:exact)
**Signature:** `static int stub_pd_board_check_request(uint32_t rdo)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_policy.c:64  | rebuilt @ 0x800717c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08007288** [taken-only] — `cmp r3, r2` then `bgt`: taken when r3 > r2 (= word [r2+0] (a struct/buffer field)). r3 = computed (lsrs r3, #0x1d). MISSING direction (taken-only) needs r3 <= r2 (= word [r2+0] (a struct/buffer field)).
  - rebuilt C (usb_pd_policy.c:68): `return (!idx || idx > pd_src_pdo_cnt) ?`
  - **What:** a ternary `?:` test — `return (!idx || idx > pd_src_pdo_cnt) ?`. When the condition holds it runs `EC_ERROR_INVAL : EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017288** (RW mirror) [taken-only] — `cmp r3, r2` then `bgt`: taken when r3 > r2 (= word [r2+0] (a struct/buffer field)). r3 = computed (lsrs r3, #0x1d). MISSING direction (taken-only) needs r3 <= r2 (= word [r2+0] (a struct/buffer field)).
  - rebuilt C (usb_pd_policy.c:68): `return (!idx || idx > pd_src_pdo_cnt) ?`
  - **What:** a ternary `?:` test — `return (!idx || idx > pd_src_pdo_cnt) ?`. When the condition holds it runs `EC_ERROR_INVAL : EC_SUCCESS;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08007294  `pd_check_requested_voltage`  (conf:approx)
**Signature:** `int pd_check_requested_voltage(uint32_t rdo)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_policy.c:36  | rebuilt @ 0x800719c | 8 uncovered (6 unreached, 2 one-dir; 4 in RW mirror)

- **0x0800729e** [taken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (usb_pd_policy.c:44): `if (pd_board_check_request(rdo))`
  - **What:** an `if` test — `if (pd_board_check_request(rdo))`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080072b6** [unreached] — `cmp r1, r3` then `bhi`: taken when r1 >u r3 (= computed (lsrs r3, #0x16)). r1 = computed (lsrs r1, #0x16). MISSING direction (unreached) needs r1 >u r3 (= computed (lsrs r3, #0x16)).
  - rebuilt C (usb_pd_policy.c:50): `if (op_ma > pdo_ma)`
  - **What:** an `if` test — `if (op_ma > pdo_ma)`. When the condition holds it runs `return EC_ERROR_INVAL; /* too much op current */`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080072be** [unreached] — `cmp r0, r3` then `bls`: taken when r0 <=u r3 (= computed (lsrs r3, #0x16)). r0 = computed (lsrs r0, #0x16). MISSING direction (unreached) needs r0 <=u r3 (= computed (lsrs r3, #0x16)).
  - rebuilt C (usb_pd_policy.c:52): `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`
  - **What:** an `if` test — `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`. When the condition holds it runs `return EC_ERROR_INVAL; /* too much max current */`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080072c2** [unreached] — `lsls r5, r5, #5` sets flags from a shifted value (bit test) then `bpl`. operand = register r5. MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_pd_policy.c:52 (discriminator 1)): `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`
  - **What:** an `if` test — `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`. When the condition holds it runs `return EC_ERROR_INVAL; /* too much max current */`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801729e** (RW mirror) [taken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (usb_pd_policy.c:44): `if (pd_board_check_request(rdo))`
  - **What:** an `if` test — `if (pd_board_check_request(rdo))`. When the condition holds it runs `return EC_ERROR_INVAL;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080172b6** (RW mirror) [unreached] — `cmp r1, r3` then `bhi`: taken when r1 >u r3 (= computed (lsrs r3, #0x16)). r1 = computed (lsrs r1, #0x16). MISSING direction (unreached) needs r1 >u r3 (= computed (lsrs r3, #0x16)).
  - rebuilt C (usb_pd_policy.c:50): `if (op_ma > pdo_ma)`
  - **What:** an `if` test — `if (op_ma > pdo_ma)`. When the condition holds it runs `return EC_ERROR_INVAL; /* too much op current */`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080172be** (RW mirror) [unreached] — `cmp r0, r3` then `bls`: taken when r0 <=u r3 (= computed (lsrs r3, #0x16)). r0 = computed (lsrs r0, #0x16). MISSING direction (unreached) needs r0 <=u r3 (= computed (lsrs r3, #0x16)).
  - rebuilt C (usb_pd_policy.c:52): `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`
  - **What:** an `if` test — `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`. When the condition holds it runs `return EC_ERROR_INVAL; /* too much max current */`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080172c2** (RW mirror) [unreached] — `lsls r5, r5, #5` sets flags from a shifted value (bit test) then `bpl`. operand = register r5. MISSING (unreached) needs the tested bit clear.
  - rebuilt C (usb_pd_policy.c:52 (discriminator 1)): `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`
  - **What:** an `if` test — `if (max_ma > pdo_ma && !(rdo & RDO_CAP_MISMATCH))`. When the condition holds it runs `return EC_ERROR_INVAL; /* too much max current */`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080072f0  `pd_build_request`  (conf:approx)
**Signature:** `int pd_build_request(int cnt, uint32_t *src_caps, uint32_t *rdo, uint32_t *ma, uint32_t *mv, enum pd_request_type req_type)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_policy.c:156  | rebuilt @ 0x80071f8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08007370** [nottaken-only] — `cmp r2, r1` then `bgt`: taken when r2 > r1 (= word [sp+4] (a struct/buffer field)). r2 = word [sp+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 > r1 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (usb_pd_policy.c:122): `if ((uw > max_uw) && (mv <= max_mv)) {`
  - **What:** an `if` test — `if ((uw > max_uw) && (mv <= max_mv)) {`. When the condition holds it runs `ret = i;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017370** (RW mirror) [nottaken-only] — `cmp r2, r1` then `bgt`: taken when r2 > r1 (= word [sp+4] (a struct/buffer field)). r2 = word [sp+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 > r1 (= word [sp+4] (a struct/buffer field)).
  - rebuilt C (usb_pd_policy.c:122): `if ((uw > max_uw) && (mv <= max_mv)) {`
  - **What:** an `if` test — `if ((uw > max_uw) && (mv <= max_mv)) {`. When the condition holds it runs `ret = i;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08007488  `set_state`  (conf:approx)
**Signature:** `static inline void set_state(int port, enum pd_states next_state)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:262  | rebuilt @ 0x8007460 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800751e** [taken-only] — `cmp r5, #0xf` then `bne`: taken when r5 != constant 0xf. r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 == constant 0xf.
  - rebuilt C (usb_pd_protocol.c:283): `if (next_state == PD_STATE_SRC_DISCONNECTED ||`
  - **What:** an `if` test — `if (next_state == PD_STATE_SRC_DISCONNECTED ||`. When the condition holds it runs `next_state == PD_STATE_SNK_DISCONNECTED) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801751e** (RW mirror) [taken-only] — `cmp r5, #0xf` then `bne`: taken when r5 != constant 0xf. r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 == constant 0xf.
  - rebuilt C (usb_pd_protocol.c:283): `if (next_state == PD_STATE_SRC_DISCONNECTED ||`
  - **What:** an `if` test — `if (next_state == PD_STATE_SRC_DISCONNECTED ||`. When the condition holds it runs `next_state == PD_STATE_SNK_DISCONNECTED) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800752c  `hc_remote_rw_hash_entry`  (conf:approx)
**Signature:** `static int hc_remote_rw_hash_entry(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:3297  | rebuilt @ 0x8007540 | 8 uncovered (6 unreached, 2 one-dir; 4 in RW mirror)

- **0x0800753c** [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (orrs r0). MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (usb_pd_protocol.c:3302): `if (!p->dev_id)`
  - **What:** an `if` test — `if (!p->dev_id)`. When the condition holds it runs `return EC_RES_INVALID_PARAM;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08007556** [unreached] — `cmp r2, r4` then `beq`: taken when r2 == r4 (= computed (orrs r7)). r2 = function argument r2. MISSING direction (unreached) needs r2 == r4 (= computed (orrs r7)).
  - rebuilt C (usb_pd_protocol.c:3305 (discriminator 2)): `for (i = 0; i < RW_HASH_ENTRIES; i++) {`
  - **What:** a loop condition — `for (i = 0; i < RW_HASH_ENTRIES; i++) {`. When the condition holds it runs `if (p->dev_id == rw_hash_table[i].dev_id) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800755c** [unreached] — `cmp r3, #4` then `bne`: taken when r3 != constant 4. r3 = computed (adds #1). MISSING direction (unreached) needs r3 != constant 4.
  - rebuilt C (usb_pd_protocol.c:3313): `idx = rw_hash_next_idx;`
  - **What:** a conditional derived from this statement — `idx = rw_hash_next_idx;`. When the condition holds it runs `rw_hash_next_idx = rw_hash_next_idx + 1;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08007566** [unreached] — `cmp r4, #4` then `bne`: taken when r4 != constant 4. r4 = computed (adds r3, #1). MISSING direction (unreached) needs r4 != constant 4.
  - rebuilt C (usb_pd_protocol.c:3316): `rw_hash_next_idx = 0;`
  - **What:** a conditional derived from this statement — `rw_hash_next_idx = 0;`. When the condition holds it runs `memcpy(&rw_hash_table[idx], p, sizeof(*p));`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801753c** (RW mirror) [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (orrs r0). MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (usb_pd_protocol.c:3302): `if (!p->dev_id)`
  - **What:** an `if` test — `if (!p->dev_id)`. When the condition holds it runs `return EC_RES_INVALID_PARAM;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017556** (RW mirror) [unreached] — `cmp r2, r4` then `beq`: taken when r2 == r4 (= computed (orrs r7)). r2 = function argument r2. MISSING direction (unreached) needs r2 == r4 (= computed (orrs r7)).
  - rebuilt C (usb_pd_protocol.c:3305 (discriminator 2)): `for (i = 0; i < RW_HASH_ENTRIES; i++) {`
  - **What:** a loop condition — `for (i = 0; i < RW_HASH_ENTRIES; i++) {`. When the condition holds it runs `if (p->dev_id == rw_hash_table[i].dev_id) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801755c** (RW mirror) [unreached] — `cmp r3, #4` then `bne`: taken when r3 != constant 4. r3 = computed (adds #1). MISSING direction (unreached) needs r3 != constant 4.
  - rebuilt C (usb_pd_protocol.c:3313): `idx = rw_hash_next_idx;`
  - **What:** a conditional derived from this statement — `idx = rw_hash_next_idx;`. When the condition holds it runs `rw_hash_next_idx = rw_hash_next_idx + 1;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08017566** (RW mirror) [unreached] — `cmp r4, #4` then `bne`: taken when r4 != constant 4. r4 = computed (adds r3, #1). MISSING direction (unreached) needs r4 != constant 4.
  - rebuilt C (usb_pd_protocol.c:3316): `rw_hash_next_idx = 0;`
  - **What:** a conditional derived from this statement — `rw_hash_next_idx = 0;`. When the condition holds it runs `memcpy(&rw_hash_table[idx], p, sizeof(*p));`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x08007584  `hc_remote_pd_dev_info`  (conf:approx)
**Signature:** `static int hc_remote_pd_dev_info(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:3327  | rebuilt @ 0x8007598 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08007592** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r7+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:3334): `r->dev_id = pd[*port].dev_id;`
  - **What:** a conditional derived from this statement — `r->dev_id = pd[*port].dev_id;`. When the condition holds it runs `if (r->dev_id) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017592** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r7+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:3334): `r->dev_id = pd[*port].dev_id;`
  - **What:** a conditional derived from this statement — `r->dev_id = pd[*port].dev_id;`. When the condition holds it runs `if (r->dev_id) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08007624  `send_source_cap`  (conf:approx)
**Signature:** `static int send_source_cap(int port)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:391  | rebuilt @ 0x80076a0 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800762e** [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (usb_pd_protocol.c:404): `header = PD_HEADER(PD_CTRL_REJECT, pd[port].power_role,`
  - **What:** a conditional derived from this statement — `header = PD_HEADER(PD_CTRL_REJECT, pd[port].power_role,`. When the condition holds it runs `pd[port].data_role, pd[port].msg_id, 0);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801762e** (RW mirror) [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (usb_pd_protocol.c:404): `header = PD_HEADER(PD_CTRL_REJECT, pd[port].power_role,`
  - **What:** a conditional derived from this statement — `header = PD_HEADER(PD_CTRL_REJECT, pd[port].power_role,`. When the condition holds it runs `pd[port].data_role, pd[port].msg_id, 0);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800769c  `pd_send_request_msg`  (conf:approx)
**Signature:** `static int pd_send_request_msg(int port, int always_send_request)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:585  | rebuilt @ 0x8007714 | 5 uncovered (2 unreached, 3 one-dir; 2 in RW mirror)

- **0x080076e0** [taken-only] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = register r4. MISSING direction (taken-only) needs r4 == constant 0.
  - rebuilt C (usb_pd_protocol.c:623 (discriminator 1)): `return EC_SUCCESS;`
  - **What:** a conditional derived from this statement — `return EC_SUCCESS;`. When the condition holds it runs `CPRINTF("Req C%d [%d] %dmV %dmA", port, RDO_POS(rdo),`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080076ea** [unreached] — `cmp r3, r2` then `beq`: taken when r3 == r2 (= word [sp+0x18] (a struct/buffer field)). r3 = word [r3+4] (a struct/buffer field). MISSING direction (unreached) needs r3 == r2 (= word [sp+0x18] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:625): `CPRINTF("Req C%d [%d] %dmV %dmA", port, RDO_POS(rdo),`
  - **What:** a conditional derived from this statement — `CPRINTF("Req C%d [%d] %dmV %dmA", port, RDO_POS(rdo),`. When the condition holds it runs `supply_voltage, curr_limit);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08007706** [nottaken-only] — `lsls r3, r3, #5` sets flags from a shifted value (bit test) then `bpl`. operand = word [sp+0x10] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit clear.
  - rebuilt C (usb_pd_protocol.c:628): `CPRINTF(" Mismatch");`
  - **What:** a conditional derived from this statement — `CPRINTF(" Mismatch");`. When the condition holds it runs `CPRINTF("\n");`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080176e0** (RW mirror) [taken-only] — `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = register r4. MISSING direction (taken-only) needs r4 == constant 0.
  - rebuilt C (usb_pd_protocol.c:623 (discriminator 1)): `return EC_SUCCESS;`
  - **What:** a conditional derived from this statement — `return EC_SUCCESS;`. When the condition holds it runs `CPRINTF("Req C%d [%d] %dmV %dmA", port, RDO_POS(rdo),`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080176ea** (RW mirror) [unreached] — `cmp r3, r2` then `beq`: taken when r3 == r2 (= word [sp+0x18] (a struct/buffer field)). r3 = word [r3+4] (a struct/buffer field). MISSING direction (unreached) needs r3 == r2 (= word [sp+0x18] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:625): `CPRINTF("Req C%d [%d] %dmV %dmA", port, RDO_POS(rdo),`
  - **What:** a conditional derived from this statement — `CPRINTF("Req C%d [%d] %dmV %dmA", port, RDO_POS(rdo),`. When the condition holds it runs `supply_voltage, curr_limit);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080078d8  `pd_execute_hard_reset`  (conf:approx)
**Signature:** `void pd_execute_hard_reset(int port)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:503  | rebuilt @ 0x8007938 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x0801790c** (RW mirror) [taken-only] — `cmp r3, #1` then `bhi`: taken when r3 >u constant 1. r3 = computed (subs #0xd). MISSING direction (taken-only) needs r3 <=u constant 1.
  - rebuilt C (usb_pd_protocol.c:527): `tcpm_set_cc(port, TYPEC_CC_RD);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RD);`. When the condition holds it runs `pd_power_supply_reset(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08007978  `pd_request_power_swap`  (conf:high)
**Signature:** `void pd_request_power_swap(int port)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:783  | rebuilt @ 0x80079c8 | 1 uncovered (0 unreached, 1 one-dir; 0 in RW mirror)

- **0x08007988** [taken-only] — `cmp r3, #0x19` then `bne`: taken when r3 != constant 0x19. r3 = byte [r3+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0x19.
  - rebuilt C (usb_pd_protocol.c:784): `if (pd[port].task_state == PD_STATE_SRC_READY)`
  - **What:** an `if` test — `if (pd[port].task_state == PD_STATE_SRC_READY)`. When the condition holds it runs `set_state(port, PD_STATE_SRC_SWAP_INIT);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x080079e4  `pd_send_vdm`  (conf:approx)
**Signature:** `void pd_send_vdm(int port, uint32_t vid, int cmd, const uint32_t *data, int count)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:1048  | rebuilt @ 0x8007a34 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x080079f0** [taken-only] — `cmp r3, #6` then `ble`: taken when r3 <= constant 6. r3 = word [sp+0x18] (a struct/buffer field). MISSING direction (taken-only) needs r3 > constant 6.
  - rebuilt C (usb_pd_protocol.c:1049): `if (count > VDO_MAX_SIZE - 1) {`
  - **What:** an `if` test — `if (count > VDO_MAX_SIZE - 1) {`. When the condition holds it runs `CPRINTF("VDM over max size\n");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080179f0** (RW mirror) [taken-only] — `cmp r3, #6` then `ble`: taken when r3 <= constant 6. r3 = word [sp+0x18] (a struct/buffer field). MISSING direction (taken-only) needs r3 > constant 6.
  - rebuilt C (usb_pd_protocol.c:1049): `if (count > VDO_MAX_SIZE - 1) {`
  - **What:** an `if` test — `if (count > VDO_MAX_SIZE - 1) {`. When the condition holds it runs `CPRINTF("VDM over max size\n");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08007a60  `hc_remote_flash`  (conf:approx)
**Signature:** `static int hc_remote_flash(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:3199  | rebuilt @ 0x8007aac | 12 uncovered (0 unreached, 12 one-dir; 6 in RW mirror)

- **0x08007b5c** [taken-only] — `cmp r1, r3` then `bls`: taken when r1 <=u r3 (= word [sp+0x14] (a struct/buffer field)). r1 = word [sp+0xc] (a struct/buffer field). MISSING direction (taken-only) needs r1 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:3267 (discriminator 1)): `(get_time().val < timeout.val))`
  - **What:** a conditional derived from this statement — `(get_time().val < timeout.val))`. When the condition holds it runs `task_wait_event(10*MSEC);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08007b68** [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= a value carried in from a preceding basic block). r1 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r1 != r3 (= a value carried in from a preceding basic block).
  - rebuilt C (usb_pd_protocol.c:3268): `task_wait_event(10*MSEC);`
  - **What:** a conditional derived from this statement — `task_wait_event(10*MSEC);`. When the condition holds it runs `if (pd[port].vdm_state > 0)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08007b7e** [taken-only] — `cmp r5, r3` then `bls`: taken when r5 <=u r3 (= word [sp+0x14] (a struct/buffer field)). r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:3281 (discriminator 1)): `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`
  - **What:** a loop condition — `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`. When the condition holds it runs `task_wait_event(50*MSEC);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08007baa** [nottaken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= a value carried in from a preceding basic block). r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 != r3 (= a value carried in from a preceding basic block).
  - rebuilt C (usb_pd_protocol.c:3273): `return EC_RES_SUCCESS;`
  - **What:** a conditional derived from this statement — `return EC_RES_SUCCESS;`. When the condition holds it runs `default:`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08007bb4** [nottaken-only] — flags from `adds r2, #1` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_pd_protocol.c:3281 (discriminator 1)): `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`
  - **What:** a loop condition — `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`. When the condition holds it runs `task_wait_event(50*MSEC);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08007bb8** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (usb_pd_protocol.c:3284 (discriminator 1)): `if ((pd[port].vdm_state > 0) ||`
  - **What:** an `if` test — `if ((pd[port].vdm_state > 0) ||`. When the condition holds it runs `(pd[port].vdm_state == VDM_STATE_ERR_TMOUT))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017b5c** (RW mirror) [taken-only] — `cmp r1, r3` then `bls`: taken when r1 <=u r3 (= word [sp+0x14] (a struct/buffer field)). r1 = word [sp+0xc] (a struct/buffer field). MISSING direction (taken-only) needs r1 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:3267 (discriminator 1)): `(get_time().val < timeout.val))`
  - **What:** a conditional derived from this statement — `(get_time().val < timeout.val))`. When the condition holds it runs `task_wait_event(10*MSEC);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017b68** (RW mirror) [nottaken-only] — `cmp r1, r3` then `bne`: taken when r1 != r3 (= a value carried in from a preceding basic block). r1 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r1 != r3 (= a value carried in from a preceding basic block).
  - rebuilt C (usb_pd_protocol.c:3268): `task_wait_event(10*MSEC);`
  - **What:** a conditional derived from this statement — `task_wait_event(10*MSEC);`. When the condition holds it runs `if (pd[port].vdm_state > 0)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017b7e** (RW mirror) [taken-only] — `cmp r5, r3` then `bls`: taken when r5 <=u r3 (= word [sp+0x14] (a struct/buffer field)). r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 >u r3 (= word [sp+0x14] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:3281 (discriminator 1)): `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`
  - **What:** a loop condition — `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`. When the condition holds it runs `task_wait_event(50*MSEC);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017baa** (RW mirror) [nottaken-only] — `cmp r5, r3` then `bne`: taken when r5 != r3 (= a value carried in from a preceding basic block). r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 != r3 (= a value carried in from a preceding basic block).
  - rebuilt C (usb_pd_protocol.c:3273): `return EC_RES_SUCCESS;`
  - **What:** a conditional derived from this statement — `return EC_RES_SUCCESS;`. When the condition holds it runs `default:`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017bb4** (RW mirror) [nottaken-only] — flags from `adds r2, #1` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_pd_protocol.c:3281 (discriminator 1)): `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`
  - **What:** a loop condition — `while ((pd[port].vdm_state > 0) && (get_time().val < timeout.val))`. When the condition holds it runs `task_wait_event(50*MSEC);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017bb8** (RW mirror) [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (usb_pd_protocol.c:3284 (discriminator 1)): `if ((pd[port].vdm_state > 0) ||`
  - **What:** an `if` test — `if ((pd[port].vdm_state > 0) ||`. When the condition holds it runs `(pd[port].vdm_state == VDM_STATE_ERR_TMOUT))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08007c44  `pd_set_dual_role`  (conf:approx)
**Signature:** `void pd_set_dual_role(enum pd_dual_role_states state)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:1242  | rebuilt @ 0x8007c8c | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x08007c5e** [taken-only] — `cmp r3, #0xf` then `bne`: taken when r3 != constant 0xf. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0xf.
  - rebuilt C (usb_pd_protocol.c:1261): `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`
  - **What:** a conditional derived from this statement — `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`. When the condition holds it runs `pd[i].power_role = PD_ROLE_SINK;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08007c8a** [taken-only] — `cmp r3, #4` then `bne`: taken when r3 != constant 4. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 4.
  - rebuilt C (usb_pd_protocol.c:1274): `if (pd[i].power_role == PD_ROLE_SINK &&`
  - **What:** an `if` test — `if (pd[i].power_role == PD_ROLE_SINK &&`. When the condition holds it runs `drp_state == PD_DRP_FORCE_SOURCE) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017c5e** (RW mirror) [taken-only] — `cmp r3, #0xf` then `bne`: taken when r3 != constant 0xf. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0xf.
  - rebuilt C (usb_pd_protocol.c:1261): `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`
  - **What:** a conditional derived from this statement — `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`. When the condition holds it runs `pd[i].power_role = PD_ROLE_SINK;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017c8a** (RW mirror) [taken-only] — `cmp r3, #4` then `bne`: taken when r3 != constant 4. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 4.
  - rebuilt C (usb_pd_protocol.c:1274): `if (pd[i].power_role == PD_ROLE_SINK &&`
  - **What:** an `if` test — `if (pd[i].power_role == PD_ROLE_SINK &&`. When the condition holds it runs `drp_state == PD_DRP_FORCE_SOURCE) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08007e70  `pd_comm_enable`  (conf:approx)
**Signature:** `void pd_comm_enable(int enable)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:1316  | rebuilt @ 0x8007eb4 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08007e94** [taken-only] — `cmp r3, #6` then `bne`: taken when r3 != constant 6. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 6.
  - rebuilt C (usb_pd_protocol.c:1331): `if (enable && pd[i].task_state == PD_STATE_SNK_DISCOVERY)`
  - **What:** an `if` test — `if (enable && pd[i].task_state == PD_STATE_SNK_DISCOVERY)`. When the condition holds it runs `set_state_timeout(i,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08017e94** (RW mirror) [taken-only] — `cmp r3, #6` then `bne`: taken when r3 != constant 6. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 6.
  - rebuilt C (usb_pd_protocol.c:1331): `if (enable && pd[i].task_state == PD_STATE_SNK_DISCOVERY)`
  - **What:** an `if` test — `if (enable && pd[i].task_state == PD_STATE_SNK_DISCOVERY)`. When the condition holds it runs `set_state_timeout(i,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08007ef0  `pd_set_dual_role`  (conf:approx)
**Signature:** `void pd_set_dual_role(enum pd_dual_role_states state)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:1242  | rebuilt @ 0x8007c8c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08007f08** [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (usb_pd_protocol.c:1261): `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`
  - **What:** a conditional derived from this statement — `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`. When the condition holds it runs `pd[i].power_role = PD_ROLE_SINK;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08017f08** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (usb_pd_protocol.c:1261): `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`
  - **What:** a conditional derived from this statement — `&& pd[i].task_state == PD_STATE_SRC_DISCONNECTED))) {`. When the condition holds it runs `pd[i].power_role = PD_ROLE_SINK;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08007f8e  `pd_task`  (conf:approx)
**Signature:** `void pd_task(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:1387  | rebuilt @ 0x8007f24 | 177 uncovered (39 unreached, 138 one-dir; 95 in RW mirror)

- **0x08008024** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (lsrs r3, #0x1e). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:1107): `switch (pd[port].vdm_state) {`
  - **What:** a `switch` dispatch on the value — `switch (pd[port].vdm_state) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008028** [nottaken-only] — `cmp r2, #1` then `bls`: taken when r2 <=u constant 1. r2 = computed (subs #4). MISSING direction (nottaken-only) needs r2 <=u constant 1.
  - rebuilt C (usb_pd_protocol.c:1107): `switch (pd[port].vdm_state) {`
  - **What:** a `switch` dispatch on the value — `switch (pd[port].vdm_state) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008032** [unreached] — `cmp r2, #1` then `bls`: taken when r2 <=u constant 1. r2 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r2 <=u constant 1.
  - rebuilt C (usb_pd_protocol.c:1110): `if (!pd_is_connected(port)) {`
  - **What:** an `if` test — `if (!pd_is_connected(port)) {`. When the condition holds it runs `pd[port].vdm_state = VDM_STATE_ERR_BUSY;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800806a** [nottaken-only] — `cmp r2, r3` then `blo`: taken when r2 <u r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r5+0x54] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 <u r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1126): `res = pd_transmit(port, TCPC_TX_SOP, header,`
  - **What:** a conditional derived from this statement — `res = pd_transmit(port, TCPC_TX_SOP, header,`. When the condition holds it runs `pd[port].vdo_data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800806c** [nottaken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r5+0x54] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1126): `res = pd_transmit(port, TCPC_TX_SOP, header,`
  - **What:** a conditional derived from this statement — `res = pd_transmit(port, TCPC_TX_SOP, header,`. When the condition holds it runs `pd[port].vdo_data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008072** [nottaken-only] — `cmp r3, r1` then `bhs`: taken when r3 >=u r1 (= word [sp+0x30] (a struct/buffer field)). r3 = word [r5+0x50] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >=u r1 (= word [sp+0x30] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1126): `res = pd_transmit(port, TCPC_TX_SOP, header,`
  - **What:** a conditional derived from this statement — `res = pd_transmit(port, TCPC_TX_SOP, header,`. When the condition holds it runs `pd[port].vdo_data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080080a6** [nottaken-only] — `cmp r2, r3` then `blo`: taken when r2 <u r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r6+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 <u r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1090): `timeout = PD_T_VDM_SNDR_RSP;`
  - **What:** a conditional derived from this statement — `timeout = PD_T_VDM_SNDR_RSP;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080080a8** [nottaken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r6+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1090): `timeout = PD_T_VDM_SNDR_RSP;`
  - **What:** a conditional derived from this statement — `timeout = PD_T_VDM_SNDR_RSP;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080080c4** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb_pd_protocol.c:1132): `pd[port].vdm_timeout.val = get_time().val +`
  - **What:** a conditional derived from this statement — `pd[port].vdm_timeout.val = get_time().val +`. When the condition holds it runs `vdm_get_ready_timeout(pd[port].vdo_data[0]);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800826e** [nottaken-only] — `cmp r5, #1` then `bne`: taken when r5 != constant 1. r5 = register r5. MISSING direction (nottaken-only) needs r5 != constant 1.
  - rebuilt C (usb_pd_protocol.c:728): `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`
  - **What:** an `if` test — `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`. When the condition holds it runs `if (!pd_check_requested_voltage(payload[0])) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008278** [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [sp+0x4c] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:728): `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`
  - **What:** an `if` test — `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`. When the condition holds it runs `if (!pd_check_requested_voltage(payload[0])) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008284** [unreached] — `cmp r0, #0` then `bge`: taken when r0 >= constant 0. r0 = computed (adds r7, #0). MISSING direction (unreached) needs r0 >= constant 0.
  - rebuilt C (usb_pd_protocol.c:730): `if (send_control(port, PD_CTRL_ACCEPT) < 0)`
  - **What:** an `if` test — `if (send_control(port, PD_CTRL_ACCEPT) < 0)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080082ec** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (movs #0x98). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:751): `if (DUAL_ROLE_IF_ELSE(port,`
  - **What:** an `if` test — `if (DUAL_ROLE_IF_ELSE(port,`. When the condition holds it runs `pd[port].task_state == PD_STATE_SNK_READY,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008318** [nottaken-only] — `cmp r3, #0x1a` then `beq`: taken when r3 == constant 0x1a. r3 = byte [r3+6] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0x1a.
  - rebuilt C (usb_pd_protocol.c:757): `pd_transmit(port, TCPC_TX_BIST_MODE_2, 0,`
  - **What:** a conditional derived from this statement — `pd_transmit(port, TCPC_TX_BIST_MODE_2, 0,`. When the condition holds it runs `NULL);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008338** [taken-only] — `cmp r6, #3` then `bne`: taken when r6 != constant 3. r6 = computed (lsrs r6, #0x1e). MISSING direction (taken-only) needs r6 == constant 3.
  - rebuilt C (usb_pd_protocol.c:767): `pd[port].flags |= PD_FLAGS_SNK_CAP_RECVD;`
  - **What:** a conditional derived from this statement — `pd[port].flags |= PD_FLAGS_SNK_CAP_RECVD;`. When the condition holds it runs `pd_update_pdo_flags(port, payload[0]);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800837e** [taken-only] — `cmp r0, #0` then `ble`: taken when r0 <= constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r0 > constant 0.
  - rebuilt C (usb_pd_protocol.c:477): `pd[port].vdm_timeout.val = get_time().val +`
  - **What:** a conditional derived from this statement — `pd[port].vdm_timeout.val = get_time().val +`. When the condition holds it runs `PD_T_VDM_BUSY;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008404** [nottaken-only] — `cmp r3, #0x14` then `beq`: taken when r3 == constant 0x14. r3 = byte [r5+6] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0x14.
  - rebuilt C (usb_pd_protocol.c:498): `CPRINTF("Unhandled VDM VID %04x CMD %04x\n",`
  - **What:** a conditional derived from this statement — `CPRINTF("Unhandled VDM VID %04x CMD %04x\n",`. When the condition holds it runs `PD_VDO_VID(payload[0]), payload[0] & 0xFFFF);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080084e8** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (movs #0). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:916): `else if (pd[port].task_state == PD_STATE_SRC_SWAP_INIT)`
  - **What:** an `if` test — `else if (pd[port].task_state == PD_STATE_SRC_SWAP_INIT)`. When the condition holds it runs `set_state(port, PD_STATE_SRC_READY);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008518** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (orrs r2). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:933): `} else if (pd[port].task_state == PD_STATE_DR_SWAP) {`
  - **What:** an `if` test — `} else if (pd[port].task_state == PD_STATE_DR_SWAP) {`. When the condition holds it runs `pd_dr_swap(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008562** [taken-only] — `cmp r3, r2` then `beq`: taken when r3 == r2 (= computed (movs #0)). r3 = computed (adds r6, r4). MISSING direction (taken-only) needs r3 != r2 (= computed (movs #0)).
  - rebuilt C (usb_pd_protocol.c:959): `execute_soft_reset(port);`
  - **What:** a conditional derived from this statement — `execute_soft_reset(port);`. When the condition holds it runs `send_control(port, PD_CTRL_ACCEPT);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008584** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb_pd_protocol.c:971): `pd[port].flags &= ~PD_FLAGS_CHECK_PR_ROLE;`
  - **What:** a conditional derived from this statement — `pd[port].flags &= ~PD_FLAGS_CHECK_PR_ROLE;`. When the condition holds it runs `set_state(port,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080085a2** [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (movs #0x98). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (usb_pd_protocol.c:984): `if (pd_check_data_swap(port, pd[port].data_role)) {`
  - **What:** an `if` test — `if (pd_check_data_swap(port, pd[port].data_role)) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080085b8** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:991): `if (send_control(port, PD_CTRL_ACCEPT) >= 0)`
  - **What:** an `if` test — `if (send_control(port, PD_CTRL_ACCEPT) >= 0)`. When the condition holds it runs `pd_dr_swap(port);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080086a4** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1557): `(!(pd[port].flags & PD_FLAGS_TRY_SRC) &&`
  - **What:** a conditional derived from this statement — `(!(pd[port].flags & PD_FLAGS_TRY_SRC) &&`. When the condition holds it runs `drp_state != PD_DRP_FORCE_SOURCE &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080086f6** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1563): `next_role_swap = get_time().val + PD_T_DRP_SNK;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SNK;`. When the condition holds it runs `pd[port].try_src_marker = get_time().val`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080086f8** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1563): `next_role_swap = get_time().val + PD_T_DRP_SNK;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SNK;`. When the condition holds it runs `pd[port].try_src_marker = get_time().val`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080086fe** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1563): `next_role_swap = get_time().val + PD_T_DRP_SNK;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SNK;`. When the condition holds it runs `pd[port].try_src_marker = get_time().val`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800876a** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1584): `} else if (cc1 == TYPEC_CC_VOLT_RA &&`
  - **What:** an `if` test — `} else if (cc1 == TYPEC_CC_VOLT_RA &&`. When the condition holds it runs `cc2 == TYPEC_CC_VOLT_RA) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800876c** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1584): `} else if (cc1 == TYPEC_CC_VOLT_RA &&`
  - **What:** an `if` test — `} else if (cc1 == TYPEC_CC_VOLT_RA &&`. When the condition holds it runs `cc2 == TYPEC_CC_VOLT_RA) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800879a** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1597): `if (new_cc_state != pd[port].cc_state) {`
  - **What:** an `if` test — `if (new_cc_state != pd[port].cc_state) {`. When the condition holds it runs `pd[port].cc_debounce = get_time().val +`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080087a2** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1598): `pd[port].cc_debounce = get_time().val +`
  - **What:** a conditional derived from this statement — `pd[port].cc_debounce = get_time().val +`. When the condition holds it runs `PD_T_CC_DEBOUNCE;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008806** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1675 (discriminator 1)): `if ((pd[port].cc_state == PD_CC_AUDIO_ACC &&`
  - **What:** an `if` test — `if ((pd[port].cc_state == PD_CC_AUDIO_ACC &&`. When the condition holds it runs `(cc1 != TYPEC_CC_VOLT_RA ||`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800880c** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1676): `(cc1 != TYPEC_CC_VOLT_RA ||`
  - **What:** a conditional derived from this statement — `(cc1 != TYPEC_CC_VOLT_RA ||`. When the condition holds it runs `cc2 != TYPEC_CC_VOLT_RA)) ||`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800885c** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1690): `if (get_time().val < pd[port].src_recover) {`
  - **What:** an `if` test — `if (get_time().val < pd[port].src_recover) {`. When the condition holds it runs `timeout = 50*MSEC;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800888a** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1702): `break;`
  - **What:** a conditional derived from this statement — `break;`. When the condition holds it runs `case PD_STATE_SRC_STARTUP:`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008890** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1705): `if (pd[port].last_state != pd[port].task_state) {`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080088a4** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1710): `pd[port].flags |= PD_FLAGS_DATA_SWAPPED;`
  - **What:** a conditional derived from this statement — `pd[port].flags |= PD_FLAGS_DATA_SWAPPED;`. When the condition holds it runs `caps_count = 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008910** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1743): `set_state_timeout(port,`
  - **What:** a conditional derived from this statement — `set_state_timeout(port,`. When the condition holds it runs `get_time().val +`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008958** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1764): `pd[port].flags |=`
  - **What:** a conditional derived from this statement — `pd[port].flags |=`. When the condition holds it runs `PD_FLAGS_PREVIOUS_PD_CONN;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800896e** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1768): `caps_count++;`
  - **What:** a conditional derived from this statement — `caps_count++;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008a14** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1806): `set_state(port, PD_STATE_SRC_READY);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SRC_READY);`. When the condition holds it runs `} else {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008a42** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1820 (discriminator 1)): `if (incoming_packet ||`
  - **What:** an `if` test — `if (incoming_packet ||`. When the condition holds it runs `(pd[port].vdm_state == VDM_STATE_BUSY))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008a78** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1832): `} else if (debug_level >= 1 &&`
  - **What:** an `if` test — `} else if (debug_level >= 1 &&`. When the condition holds it runs `snk_cap_count == PD_SNK_CAP_RETRIES+1) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008a84** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1832 (discriminator 1)): `} else if (debug_level >= 1 &&`
  - **What:** an `if` test — `} else if (debug_level >= 1 &&`. When the condition holds it runs `snk_cap_count == PD_SNK_CAP_RETRIES+1) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008a8e** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1839): `if (pd[port].flags & PD_FLAGS_CHECK_PR_ROLE) {`
  - **What:** an `if` test — `if (pd[port].flags & PD_FLAGS_CHECK_PR_ROLE) {`. When the condition holds it runs `pd_check_pr_role(port, PD_ROLE_SOURCE,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008ab2** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1847): `if (pd[port].flags & PD_FLAGS_CHECK_DR_ROLE) {`
  - **What:** an `if` test — `if (pd[port].flags & PD_FLAGS_CHECK_DR_ROLE) {`. When the condition holds it runs `pd_check_dr_role(port, pd[port].data_role,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008abc** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1848): `pd_check_dr_role(port, pd[port].data_role,`
  - **What:** a conditional derived from this statement — `pd_check_dr_role(port, pd[port].data_role,`. When the condition holds it runs `pd[port].flags);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008ada** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1858): `pd_send_vdm(port, USB_SID_PD,`
  - **What:** a conditional derived from this statement — `pd_send_vdm(port, USB_SID_PD,`. When the condition holds it runs `CMD_DISCOVER_IDENT, NULL, 0);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008ae0** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1858): `pd_send_vdm(port, USB_SID_PD,`
  - **What:** a conditional derived from this statement — `pd_send_vdm(port, USB_SID_PD,`. When the condition holds it runs `CMD_DISCOVER_IDENT, NULL, 0);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008b56** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1886): `res = send_control(port, PD_CTRL_DR_SWAP);`
  - **What:** a conditional derived from this statement — `res = send_control(port, PD_CTRL_DR_SWAP);`. When the condition holds it runs `if (res < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008b66** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1894): `set_state(port, res == -1 ?`
  - **What:** a ternary `?:` test — `set_state(port, res == -1 ?`. When the condition holds it runs `PD_STATE_SOFT_RESET :`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008bc6** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1917): `set_state(port, res == -1 ?`
  - **What:** a ternary `?:` test — `set_state(port, res == -1 ?`. When the condition holds it runs `PD_STATE_SOFT_RESET :`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008bce** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1917 (discriminator 4)): `set_state(port, res == -1 ?`
  - **What:** a ternary `?:` test — `set_state(port, res == -1 ?`. When the condition holds it runs `PD_STATE_SOFT_RESET :`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008bf6** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008c16** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1523): `timeout = 500*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 500*MSEC;`. When the condition holds it runs `switch (this_state) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008c26** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008c2c** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1939): `if (pd[port].last_state != pd[port].task_state) {`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state) {`. When the condition holds it runs `pd_power_supply_reset(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008ce8** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1974): `pd_rx_disable_monitoring(port);`
  - **What:** a conditional derived from this statement — `pd_rx_disable_monitoring(port);`. When the condition holds it runs `pd_hw_release(port);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008d0c** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1980): `task_wait_event(-1);`
  - **What:** a conditional derived from this statement — `task_wait_event(-1);`. When the condition holds it runs `pd_hw_init(port, PD_ROLE_DEFAULT);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008d70** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2014): `if (pd[port].flags & PD_FLAGS_TRY_SRC) {`
  - **What:** an `if` test — `if (pd[port].flags & PD_FLAGS_TRY_SRC) {`. When the condition holds it runs `if (get_time().val > pd[port].try_src_marker)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008dee** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2032): `next_role_swap = get_time().val + PD_T_DRP_SRC;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SRC;`. When the condition holds it runs `timeout = 2*MSEC;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008dfe** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2035): `timeout = 2*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 2*MSEC;`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008e00** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2032): `next_role_swap = get_time().val + PD_T_DRP_SRC;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SRC;`. When the condition holds it runs `timeout = 2*MSEC;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008e08** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2039): `tcpm_get_cc(port, &cc1, &cc2);`
  - **What:** a conditional derived from this statement — `tcpm_get_cc(port, &cc1, &cc2);`. When the condition holds it runs `if (cc1 == TYPEC_CC_VOLT_OPEN &&`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008e24** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2044): `timeout = 5*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 5*MSEC;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008e2e** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008e40** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008e42** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008e48** [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08008ef4** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2129): `set_state(port, PD_STATE_SNK_DISCONNECTED);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SNK_DISCONNECTED);`. When the condition holds it runs `#ifdef CONFIG_CASE_CLOSED_DEBUG`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008ef8** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2131): `ccd_set_mode(CCD_MODE_DISABLED);`
  - **What:** a conditional derived from this statement — `ccd_set_mode(CCD_MODE_DISABLED);`. When the condition holds it runs `#endif`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008f0a** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2137): `if (pd[port].last_state != pd[port].task_state)`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state)`. When the condition holds it runs `pd[port].flags |= PD_FLAGS_DATA_SWAPPED;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08008f3c** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202 (discriminator 4)): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08008f70** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2166): `snk_hard_reset_vbus_off = 1;`
  - **What:** a conditional derived from this statement — `snk_hard_reset_vbus_off = 1;`. When the condition holds it runs `set_state_timeout(port,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08009002** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080090aa** [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2282): `if (incoming_packet ||`
  - **What:** an `if` test — `if (incoming_packet ||`. When the condition holds it runs `(pd[port].vdm_state == VDM_STATE_BUSY))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009102** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2303): `pd_check_dr_role(port, pd[port].data_role,`
  - **What:** a conditional derived from this statement — `pd_check_dr_role(port, pd[port].data_role,`. When the condition holds it runs `pd[port].flags);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800914e** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2324): `if (res < 0) {`
  - **What:** an `if` test — `if (res < 0) {`. When the condition holds it runs `timeout = 10*MSEC;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080091d8** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2366): `tcpm_set_cc(port, TYPEC_CC_RP);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RP);`. When the condition holds it runs `if (pd_set_power_supply_ready(port)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800924c** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2399): `pd[port].power_role = PD_ROLE_SOURCE;`
  - **What:** a conditional derived from this statement — `pd[port].power_role = PD_ROLE_SOURCE;`. When the condition holds it runs `pd_update_roles(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08009260** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2402): `timeout = 10*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 10*MSEC;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08009390** [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2570): `set_state(port, DUAL_ROLE_IF_ELSE(port,`
  - **What:** a conditional derived from this statement — `set_state(port, DUAL_ROLE_IF_ELSE(port,`. When the condition holds it runs `PD_STATE_SNK_DISCONNECTED,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018024** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (lsrs r3, #0x1e). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:1107): `switch (pd[port].vdm_state) {`
  - **What:** a `switch` dispatch on the value — `switch (pd[port].vdm_state) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018028** (RW mirror) [nottaken-only] — `cmp r2, #1` then `bls`: taken when r2 <=u constant 1. r2 = computed (subs #4). MISSING direction (nottaken-only) needs r2 <=u constant 1.
  - rebuilt C (usb_pd_protocol.c:1107): `switch (pd[port].vdm_state) {`
  - **What:** a `switch` dispatch on the value — `switch (pd[port].vdm_state) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018032** (RW mirror) [unreached] — `cmp r2, #1` then `bls`: taken when r2 <=u constant 1. r2 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r2 <=u constant 1.
  - rebuilt C (usb_pd_protocol.c:1110): `if (!pd_is_connected(port)) {`
  - **What:** an `if` test — `if (!pd_is_connected(port)) {`. When the condition holds it runs `pd[port].vdm_state = VDM_STATE_ERR_BUSY;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801806a** (RW mirror) [nottaken-only] — `cmp r2, r3` then `blo`: taken when r2 <u r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r5+0x54] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 <u r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1126): `res = pd_transmit(port, TCPC_TX_SOP, header,`
  - **What:** a conditional derived from this statement — `res = pd_transmit(port, TCPC_TX_SOP, header,`. When the condition holds it runs `pd[port].vdo_data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801806c** (RW mirror) [nottaken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r5+0x54] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1126): `res = pd_transmit(port, TCPC_TX_SOP, header,`
  - **What:** a conditional derived from this statement — `res = pd_transmit(port, TCPC_TX_SOP, header,`. When the condition holds it runs `pd[port].vdo_data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018072** (RW mirror) [nottaken-only] — `cmp r3, r1` then `bhs`: taken when r3 >=u r1 (= word [sp+0x30] (a struct/buffer field)). r3 = word [r5+0x50] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >=u r1 (= word [sp+0x30] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1126): `res = pd_transmit(port, TCPC_TX_SOP, header,`
  - **What:** a conditional derived from this statement — `res = pd_transmit(port, TCPC_TX_SOP, header,`. When the condition holds it runs `pd[port].vdo_data);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080180a6** (RW mirror) [nottaken-only] — `cmp r2, r3` then `blo`: taken when r2 <u r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r6+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 <u r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1090): `timeout = PD_T_VDM_SNDR_RSP;`
  - **What:** a conditional derived from this statement — `timeout = PD_T_VDM_SNDR_RSP;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080180a8** (RW mirror) [nottaken-only] — `cmp r2, r3` then `bne`: taken when r2 != r3 (= word [sp+0x34] (a struct/buffer field)). r2 = word [r6+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != r3 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:1090): `timeout = PD_T_VDM_SNDR_RSP;`
  - **What:** a conditional derived from this statement — `timeout = PD_T_VDM_SNDR_RSP;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080180c4** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb_pd_protocol.c:1132): `pd[port].vdm_timeout.val = get_time().val +`
  - **What:** a conditional derived from this statement — `pd[port].vdm_timeout.val = get_time().val +`. When the condition holds it runs `vdm_get_ready_timeout(pd[port].vdo_data[0]);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801826e** (RW mirror) [nottaken-only] — `cmp r5, #1` then `bne`: taken when r5 != constant 1. r5 = register r5. MISSING direction (nottaken-only) needs r5 != constant 1.
  - rebuilt C (usb_pd_protocol.c:728): `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`
  - **What:** an `if` test — `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`. When the condition holds it runs `if (!pd_check_requested_voltage(payload[0])) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018278** (RW mirror) [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [sp+0x4c] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:728): `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`
  - **What:** an `if` test — `if ((pd[port].power_role == PD_ROLE_SOURCE) && (cnt == 1))`. When the condition holds it runs `if (!pd_check_requested_voltage(payload[0])) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018284** (RW mirror) [unreached] — `cmp r0, #0` then `bge`: taken when r0 >= constant 0. r0 = computed (adds r7, #0). MISSING direction (unreached) needs r0 >= constant 0.
  - rebuilt C (usb_pd_protocol.c:730): `if (send_control(port, PD_CTRL_ACCEPT) < 0)`
  - **What:** an `if` test — `if (send_control(port, PD_CTRL_ACCEPT) < 0)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018318** (RW mirror) [nottaken-only] — `cmp r3, #0x1a` then `beq`: taken when r3 == constant 0x1a. r3 = byte [r3+6] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0x1a.
  - rebuilt C (usb_pd_protocol.c:757): `pd_transmit(port, TCPC_TX_BIST_MODE_2, 0,`
  - **What:** a conditional derived from this statement — `pd_transmit(port, TCPC_TX_BIST_MODE_2, 0,`. When the condition holds it runs `NULL);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018338** (RW mirror) [taken-only] — `cmp r6, #3` then `bne`: taken when r6 != constant 3. r6 = computed (lsrs r6, #0x1e). MISSING direction (taken-only) needs r6 == constant 3.
  - rebuilt C (usb_pd_protocol.c:767): `pd[port].flags |= PD_FLAGS_SNK_CAP_RECVD;`
  - **What:** a conditional derived from this statement — `pd[port].flags |= PD_FLAGS_SNK_CAP_RECVD;`. When the condition holds it runs `pd_update_pdo_flags(port, payload[0]);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801837e** (RW mirror) [taken-only] — `cmp r0, #0` then `ble`: taken when r0 <= constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r0 > constant 0.
  - rebuilt C (usb_pd_protocol.c:477): `pd[port].vdm_timeout.val = get_time().val +`
  - **What:** a conditional derived from this statement — `pd[port].vdm_timeout.val = get_time().val +`. When the condition holds it runs `PD_T_VDM_BUSY;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018404** (RW mirror) [nottaken-only] — `cmp r3, #0x14` then `beq`: taken when r3 == constant 0x14. r3 = byte [r5+6] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0x14.
  - rebuilt C (usb_pd_protocol.c:498): `CPRINTF("Unhandled VDM VID %04x CMD %04x\n",`
  - **What:** a conditional derived from this statement — `CPRINTF("Unhandled VDM VID %04x CMD %04x\n",`. When the condition holds it runs `PD_VDO_VID(payload[0]), payload[0] & 0xFFFF);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018446** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bgt`: taken when r3 > constant 0. r3 = word [r3+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 > constant 0.
  - rebuilt C (usb_pd_protocol.c:421): `uint16_t header = PD_HEADER(PD_DATA_SINK_CAP, pd[port].power_role,`
  - **What:** a conditional derived from this statement — `uint16_t header = PD_HEADER(PD_DATA_SINK_CAP, pd[port].power_role,`. When the condition holds it runs `pd[port].data_role, pd[port].msg_id, pd_snk_pdo_cnt);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018488** (RW mirror) [taken-only] — `cmp r3, #0xd` then `bne`: taken when r3 != constant 0xd. r3 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r3 == constant 0xd.
  - rebuilt C (usb_pd_protocol.c:873): `set_state(port, PD_STATE_SNK_SWAP_STANDBY);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SNK_SWAP_STANDBY);`. When the condition holds it runs `} else if (pd[port].task_state == PD_STATE_SRC_SWAP_STANDBY) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080184e8** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (movs #0). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:916): `else if (pd[port].task_state == PD_STATE_SRC_SWAP_INIT)`
  - **What:** an `if` test — `else if (pd[port].task_state == PD_STATE_SRC_SWAP_INIT)`. When the condition holds it runs `set_state(port, PD_STATE_SRC_READY);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018518** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (orrs r2). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:933): `} else if (pd[port].task_state == PD_STATE_DR_SWAP) {`
  - **What:** an `if` test — `} else if (pd[port].task_state == PD_STATE_DR_SWAP) {`. When the condition holds it runs `pd_dr_swap(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018562** (RW mirror) [taken-only] — `cmp r3, r2` then `beq`: taken when r3 == r2 (= computed (movs #0)). r3 = computed (adds r6, r4). MISSING direction (taken-only) needs r3 != r2 (= computed (movs #0)).
  - rebuilt C (usb_pd_protocol.c:959): `execute_soft_reset(port);`
  - **What:** a conditional derived from this statement — `execute_soft_reset(port);`. When the condition holds it runs `send_control(port, PD_CTRL_ACCEPT);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018584** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb_pd_protocol.c:971): `pd[port].flags &= ~PD_FLAGS_CHECK_PR_ROLE;`
  - **What:** a conditional derived from this statement — `pd[port].flags &= ~PD_FLAGS_CHECK_PR_ROLE;`. When the condition holds it runs `set_state(port,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080185a2** (RW mirror) [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (movs #0x98). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (usb_pd_protocol.c:984): `if (pd_check_data_swap(port, pd[port].data_role)) {`
  - **What:** an `if` test — `if (pd_check_data_swap(port, pd[port].data_role)) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080185b8** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:991): `if (send_control(port, PD_CTRL_ACCEPT) >= 0)`
  - **What:** an `if` test — `if (send_control(port, PD_CTRL_ACCEPT) >= 0)`. When the condition holds it runs `pd_dr_swap(port);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080186a4** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1557): `(!(pd[port].flags & PD_FLAGS_TRY_SRC) &&`
  - **What:** a conditional derived from this statement — `(!(pd[port].flags & PD_FLAGS_TRY_SRC) &&`. When the condition holds it runs `drp_state != PD_DRP_FORCE_SOURCE &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080186d2** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1560): `pd[port].power_role = PD_ROLE_SINK;`
  - **What:** a conditional derived from this statement — `pd[port].power_role = PD_ROLE_SINK;`. When the condition holds it runs `set_state(port, PD_STATE_SNK_DISCONNECTED);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080186e0** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1562): `tcpm_set_cc(port, TYPEC_CC_RD);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RD);`. When the condition holds it runs `next_role_swap = get_time().val + PD_T_DRP_SNK;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080186f6** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1563): `next_role_swap = get_time().val + PD_T_DRP_SNK;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SNK;`. When the condition holds it runs `pd[port].try_src_marker = get_time().val`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080186f8** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1563): `next_role_swap = get_time().val + PD_T_DRP_SNK;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SNK;`. When the condition holds it runs `pd[port].try_src_marker = get_time().val`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080186fe** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1563): `next_role_swap = get_time().val + PD_T_DRP_SNK;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SNK;`. When the condition holds it runs `pd[port].try_src_marker = get_time().val`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801876a** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1584): `} else if (cc1 == TYPEC_CC_VOLT_RA &&`
  - **What:** an `if` test — `} else if (cc1 == TYPEC_CC_VOLT_RA &&`. When the condition holds it runs `cc2 == TYPEC_CC_VOLT_RA) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801876c** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1584): `} else if (cc1 == TYPEC_CC_VOLT_RA &&`
  - **What:** an `if` test — `} else if (cc1 == TYPEC_CC_VOLT_RA &&`. When the condition holds it runs `cc2 == TYPEC_CC_VOLT_RA) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018772** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1590): `set_state(port, PD_STATE_SRC_DISCONNECTED);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SRC_DISCONNECTED);`. When the condition holds it runs `timeout = 5*MSEC;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801879a** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1597): `if (new_cc_state != pd[port].cc_state) {`
  - **What:** an `if` test — `if (new_cc_state != pd[port].cc_state) {`. When the condition holds it runs `pd[port].cc_debounce = get_time().val +`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080187a2** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1598): `pd[port].cc_debounce = get_time().val +`
  - **What:** a conditional derived from this statement — `pd[port].cc_debounce = get_time().val +`. When the condition holds it runs `PD_T_CC_DEBOUNCE;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080187c4** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1602): `} else if (get_time().val <`
  - **What:** an `if` test — `} else if (get_time().val <`. When the condition holds it runs `pd[port].cc_debounce) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018806** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1675 (discriminator 1)): `if ((pd[port].cc_state == PD_CC_AUDIO_ACC &&`
  - **What:** an `if` test — `if ((pd[port].cc_state == PD_CC_AUDIO_ACC &&`. When the condition holds it runs `(cc1 != TYPEC_CC_VOLT_RA ||`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801880c** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1676): `(cc1 != TYPEC_CC_VOLT_RA ||`
  - **What:** a conditional derived from this statement — `(cc1 != TYPEC_CC_VOLT_RA ||`. When the condition holds it runs `cc2 != TYPEC_CC_VOLT_RA)) ||`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801885c** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1690): `if (get_time().val < pd[port].src_recover) {`
  - **What:** an `if` test — `if (get_time().val < pd[port].src_recover) {`. When the condition holds it runs `timeout = 50*MSEC;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801888a** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1702): `break;`
  - **What:** a conditional derived from this statement — `break;`. When the condition holds it runs `case PD_STATE_SRC_STARTUP:`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018890** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1705): `if (pd[port].last_state != pd[port].task_state) {`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080188a4** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1710): `pd[port].flags |= PD_FLAGS_DATA_SWAPPED;`
  - **What:** a conditional derived from this statement — `pd[port].flags |= PD_FLAGS_DATA_SWAPPED;`. When the condition holds it runs `caps_count = 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018910** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1743): `set_state_timeout(port,`
  - **What:** a conditional derived from this statement — `set_state_timeout(port,`. When the condition holds it runs `get_time().val +`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801896e** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1768): `caps_count++;`
  - **What:** a conditional derived from this statement — `caps_count++;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080189e6** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1795): `get_time().val +`
  - **What:** a conditional derived from this statement — `get_time().val +`. When the condition holds it runs `PD_POWER_SUPPLY_TURN_ON_DELAY,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018a14** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1806): `set_state(port, PD_STATE_SRC_READY);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SRC_READY);`. When the condition holds it runs `} else {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018a42** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1820 (discriminator 1)): `if (incoming_packet ||`
  - **What:** an `if` test — `if (incoming_packet ||`. When the condition holds it runs `(pd[port].vdm_state == VDM_STATE_BUSY))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018a78** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1832): `} else if (debug_level >= 1 &&`
  - **What:** an `if` test — `} else if (debug_level >= 1 &&`. When the condition holds it runs `snk_cap_count == PD_SNK_CAP_RETRIES+1) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018a84** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1832 (discriminator 1)): `} else if (debug_level >= 1 &&`
  - **What:** an `if` test — `} else if (debug_level >= 1 &&`. When the condition holds it runs `snk_cap_count == PD_SNK_CAP_RETRIES+1) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018a8e** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1839): `if (pd[port].flags & PD_FLAGS_CHECK_PR_ROLE) {`
  - **What:** an `if` test — `if (pd[port].flags & PD_FLAGS_CHECK_PR_ROLE) {`. When the condition holds it runs `pd_check_pr_role(port, PD_ROLE_SOURCE,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018ab2** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1847): `if (pd[port].flags & PD_FLAGS_CHECK_DR_ROLE) {`
  - **What:** an `if` test — `if (pd[port].flags & PD_FLAGS_CHECK_DR_ROLE) {`. When the condition holds it runs `pd_check_dr_role(port, pd[port].data_role,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018abc** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1848): `pd_check_dr_role(port, pd[port].data_role,`
  - **What:** a conditional derived from this statement — `pd_check_dr_role(port, pd[port].data_role,`. When the condition holds it runs `pd[port].flags);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018ada** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1858): `pd_send_vdm(port, USB_SID_PD,`
  - **What:** a conditional derived from this statement — `pd_send_vdm(port, USB_SID_PD,`. When the condition holds it runs `CMD_DISCOVER_IDENT, NULL, 0);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018ae0** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1858): `pd_send_vdm(port, USB_SID_PD,`
  - **What:** a conditional derived from this statement — `pd_send_vdm(port, USB_SID_PD,`. When the condition holds it runs `CMD_DISCOVER_IDENT, NULL, 0);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018b56** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1886): `res = send_control(port, PD_CTRL_DR_SWAP);`
  - **What:** a conditional derived from this statement — `res = send_control(port, PD_CTRL_DR_SWAP);`. When the condition holds it runs `if (res < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018b66** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1894): `set_state(port, res == -1 ?`
  - **What:** a ternary `?:` test — `set_state(port, res == -1 ?`. When the condition holds it runs `PD_STATE_SOFT_RESET :`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018bc6** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1917): `set_state(port, res == -1 ?`
  - **What:** a ternary `?:` test — `set_state(port, res == -1 ?`. When the condition holds it runs `PD_STATE_SOFT_RESET :`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018bce** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1917 (discriminator 4)): `set_state(port, res == -1 ?`
  - **What:** a ternary `?:` test — `set_state(port, res == -1 ?`. When the condition holds it runs `PD_STATE_SOFT_RESET :`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018bf6** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018c16** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1523): `timeout = 500*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 500*MSEC;`. When the condition holds it runs `switch (this_state) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018c26** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018c2c** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1939): `if (pd[port].last_state != pd[port].task_state) {`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state) {`. When the condition holds it runs `pd_power_supply_reset(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018c92** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1956): `break;`
  - **What:** a conditional derived from this statement — `break;`. When the condition holds it runs `tcpm_set_cc(port, TYPEC_CC_RD);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018ce8** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1974): `pd_rx_disable_monitoring(port);`
  - **What:** a conditional derived from this statement — `pd_rx_disable_monitoring(port);`. When the condition holds it runs `pd_hw_release(port);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018cfc** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1979): `while (pd[port].task_state == PD_STATE_SUSPENDED)`
  - **What:** a loop condition — `while (pd[port].task_state == PD_STATE_SUSPENDED)`. When the condition holds it runs `task_wait_event(-1);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018d0c** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:1980): `task_wait_event(-1);`
  - **What:** a conditional derived from this statement — `task_wait_event(-1);`. When the condition holds it runs `pd_hw_init(port, PD_ROLE_DEFAULT);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018d70** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2014): `if (pd[port].flags & PD_FLAGS_TRY_SRC) {`
  - **What:** an `if` test — `if (pd[port].flags & PD_FLAGS_TRY_SRC) {`. When the condition holds it runs `if (get_time().val > pd[port].try_src_marker)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018dee** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2032): `next_role_swap = get_time().val + PD_T_DRP_SRC;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SRC;`. When the condition holds it runs `timeout = 2*MSEC;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018dfe** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2035): `timeout = 2*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 2*MSEC;`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018e00** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2032): `next_role_swap = get_time().val + PD_T_DRP_SRC;`
  - **What:** a conditional derived from this statement — `next_role_swap = get_time().val + PD_T_DRP_SRC;`. When the condition holds it runs `timeout = 2*MSEC;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018e08** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2039): `tcpm_get_cc(port, &cc1, &cc2);`
  - **What:** a conditional derived from this statement — `tcpm_get_cc(port, &cc1, &cc2);`. When the condition holds it runs `if (cc1 == TYPEC_CC_VOLT_OPEN &&`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018e24** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2044): `timeout = 5*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 5*MSEC;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018e2e** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018e40** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018e42** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018e48** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2051): `if (get_time().val < pd[port].cc_debounce)`
  - **What:** an `if` test — `if (get_time().val < pd[port].cc_debounce)`. When the condition holds it runs `break;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08018ef4** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2129): `set_state(port, PD_STATE_SNK_DISCONNECTED);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SNK_DISCONNECTED);`. When the condition holds it runs `#ifdef CONFIG_CASE_CLOSED_DEBUG`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018ef8** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2131): `ccd_set_mode(CCD_MODE_DISABLED);`
  - **What:** a conditional derived from this statement — `ccd_set_mode(CCD_MODE_DISABLED);`. When the condition holds it runs `#endif`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018f0a** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2137): `if (pd[port].last_state != pd[port].task_state)`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state)`. When the condition holds it runs `pd[port].flags |= PD_FLAGS_DATA_SWAPPED;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018f3c** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202 (discriminator 4)): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08018f70** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2166): `snk_hard_reset_vbus_off = 1;`
  - **What:** a conditional derived from this statement — `snk_hard_reset_vbus_off = 1;`. When the condition holds it runs `set_state_timeout(port,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08018fa0** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2189): `&& pd_comm_enabled) {`
  - **What:** a conditional derived from this statement — `&& pd_comm_enabled) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019002** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:202): `pd[port].timeout_state = timeout_state;`
  - **What:** a conditional derived from this statement — `pd[port].timeout_state = timeout_state;`. When the condition holds it runs `int pd_is_connected(int port)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019088** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2270): `get_time().val +`
  - **What:** a conditional derived from this statement — `get_time().val +`. When the condition holds it runs `PD_T_PS_TRANSITION,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080190aa** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2282): `if (incoming_packet ||`
  - **What:** an `if` test — `if (incoming_packet ||`. When the condition holds it runs `(pd[port].vdm_state == VDM_STATE_BUSY))`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x08019102** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2303): `pd_check_dr_role(port, pd[port].data_role,`
  - **What:** a conditional derived from this statement — `pd_check_dr_role(port, pd[port].data_role,`. When the condition holds it runs `pd[port].flags);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019142** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2322): `if (pd[port].last_state != pd[port].task_state) {`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state) {`. When the condition holds it runs `res = send_control(port, PD_CTRL_PR_SWAP);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801914e** (RW mirror) [unreached] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2324): `if (res < 0) {`
  - **What:** an `if` test — `if (res < 0) {`. When the condition holds it runs `timeout = 10*MSEC;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080191c4** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2364): `if (pd[port].last_state != pd[port].task_state) {`
  - **What:** an `if` test — `if (pd[port].last_state != pd[port].task_state) {`. When the condition holds it runs `tcpm_set_cc(port, TYPEC_CC_RP);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080191d2** (RW mirror) [nottaken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2366): `tcpm_set_cc(port, TYPEC_CC_RP);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RP);`. When the condition holds it runs `if (pd_set_power_supply_ready(port)) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x080191d8** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2366): `tcpm_set_cc(port, TYPEC_CC_RP);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RP);`. When the condition holds it runs `if (pd_set_power_supply_ready(port)) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019222** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2388): `tcpm_set_cc(port, TYPEC_CC_RD);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RD);`. When the condition holds it runs `pd_power_supply_reset(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801924c** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2399): `pd[port].power_role = PD_ROLE_SOURCE;`
  - **What:** a conditional derived from this statement — `pd[port].power_role = PD_ROLE_SOURCE;`. When the condition holds it runs `pd_update_roles(port);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019260** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2402): `timeout = 10*MSEC;`
  - **What:** a conditional derived from this statement — `timeout = 10*MSEC;`. When the condition holds it runs `break;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019390** (RW mirror) [taken-only] — (branch not in linear decode — likely data/jump-table region)
  - rebuilt C (usb_pd_protocol.c:2570): `set_state(port, DUAL_ROLE_IF_ELSE(port,`
  - **What:** a conditional derived from this statement — `set_state(port, DUAL_ROLE_IF_ELSE(port,`. When the condition holds it runs `PD_STATE_SNK_DISCONNECTED,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08009510  `pd_request_source_voltage`  (conf:approx)
**Signature:** `void pd_request_source_voltage(int port, int mv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:2839  | rebuilt @ 0x80095e0 | 10 uncovered (0 unreached, 10 one-dir; 5 in RW mirror)

- **0x08009538** [nottaken-only] — `cmp r3, r1` then `bhi`: taken when r3 >u r1 (= word [sp+0x34] (a struct/buffer field)). r3 = word [r6+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u r1 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:2848): `tcpm_set_cc(port, TYPEC_CC_RD);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RD);`. When the condition holds it runs `set_state(port, PD_STATE_SNK_DISCONNECTED);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800953a** [nottaken-only] — `cmp r3, r1` then `bne`: taken when r3 != r1 (= word [sp+0x34] (a struct/buffer field)). r3 = word [r6+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != r1 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:2848): `tcpm_set_cc(port, TYPEC_CC_RD);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RD);`. When the condition holds it runs `set_state(port, PD_STATE_SNK_DISCONNECTED);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009552** [nottaken-only] — `cmp r4, r3` then `ble`: taken when r4 <= r3 (= a global/constant (pc-relative load)). r4 = register r4. MISSING direction (nottaken-only) needs r4 <= r3 (= a global/constant (pc-relative load)).
  - rebuilt C (usb_pd_protocol.c:2853): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `void pd_set_external_voltage_limit(int port, int mv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009566** [nottaken-only] — `cmp ip, r6` then `bhi`: taken when ip >u r6 (= computed (adds r3, #0)). ip = computed (mov r5). MISSING direction (nottaken-only) needs ip >u r6 (= computed (adds r3, #0)).
  - rebuilt C (usb_pd_protocol.c:2879): `if (!strcasecmp(argv[1], "dualrole")) {`
  - **What:** an `if` test — `if (!strcasecmp(argv[1], "dualrole")) {`. When the condition holds it runs `if (argc < 3) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009568** [nottaken-only] — `cmp ip, r6` then `bne`: taken when ip != r6 (= computed (adds r3, #0)). ip = computed (mov r5). MISSING direction (nottaken-only) needs ip != r6 (= computed (adds r3, #0)).
  - rebuilt C (usb_pd_protocol.c:2879): `if (!strcasecmp(argv[1], "dualrole")) {`
  - **What:** an `if` test — `if (!strcasecmp(argv[1], "dualrole")) {`. When the condition holds it runs `if (argc < 3) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019538** (RW mirror) [nottaken-only] — `cmp r3, r1` then `bhi`: taken when r3 >u r1 (= word [sp+0x34] (a struct/buffer field)). r3 = word [r6+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u r1 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:2848): `tcpm_set_cc(port, TYPEC_CC_RD);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RD);`. When the condition holds it runs `set_state(port, PD_STATE_SNK_DISCONNECTED);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801953a** (RW mirror) [nottaken-only] — `cmp r3, r1` then `bne`: taken when r3 != r1 (= word [sp+0x34] (a struct/buffer field)). r3 = word [r6+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != r1 (= word [sp+0x34] (a struct/buffer field)).
  - rebuilt C (usb_pd_protocol.c:2848): `tcpm_set_cc(port, TYPEC_CC_RD);`
  - **What:** a conditional derived from this statement — `tcpm_set_cc(port, TYPEC_CC_RD);`. When the condition holds it runs `set_state(port, PD_STATE_SNK_DISCONNECTED);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019552** (RW mirror) [nottaken-only] — `cmp r4, r3` then `ble`: taken when r4 <= r3 (= a global/constant (pc-relative load)). r4 = register r4. MISSING direction (nottaken-only) needs r4 <= r3 (= a global/constant (pc-relative load)).
  - rebuilt C (usb_pd_protocol.c:2853): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `void pd_set_external_voltage_limit(int port, int mv)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019566** (RW mirror) [nottaken-only] — `cmp ip, r6` then `bhi`: taken when ip >u r6 (= computed (adds r3, #0)). ip = computed (mov r5). MISSING direction (nottaken-only) needs ip >u r6 (= computed (adds r3, #0)).
  - rebuilt C (usb_pd_protocol.c:2879): `if (!strcasecmp(argv[1], "dualrole")) {`
  - **What:** an `if` test — `if (!strcasecmp(argv[1], "dualrole")) {`. When the condition holds it runs `if (argc < 3) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019568** (RW mirror) [nottaken-only] — `cmp ip, r6` then `bne`: taken when ip != r6 (= computed (adds r3, #0)). ip = computed (mov r5). MISSING direction (nottaken-only) needs ip != r6 (= computed (adds r3, #0)).
  - rebuilt C (usb_pd_protocol.c:2879): `if (!strcasecmp(argv[1], "dualrole")) {`
  - **What:** an `if` test — `if (!strcasecmp(argv[1], "dualrole")) {`. When the condition holds it runs `if (argc < 3) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800959e  `pd_request_source_voltage`  (conf:approx)
**Signature:** `void pd_request_source_voltage(int port, int mv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:2839  | rebuilt @ 0x80095e0 | 13 uncovered (6 unreached, 7 one-dir; 7 in RW mirror)

- **0x080095cc** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb_pd_protocol.c:2849): `set_state(port, PD_STATE_SNK_DISCONNECTED);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SNK_DISCONNECTED);`. When the condition holds it runs `task_wake(PD_PORT_TO_TASK_ID(port));`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080095e4** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (usb_pd_protocol.c:2870): `{`
  - **What:** a conditional derived from this statement — `{`. When the condition holds it runs `int port;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009678** [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:2911): `if (!strcasecmp(argv[1], "dump")) {`
  - **What:** an `if` test — `if (!strcasecmp(argv[1], "dump")) {`. When the condition holds it runs `int level;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009684** [unreached] — `cmp r3, #5` then `bne`: taken when r3 != constant 5. r3 = byte [r5+6] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 5.
  - rebuilt C (usb_pd_protocol.c:2915): `ccprintf("dump level: %d\n", debug_level);`
  - **What:** a conditional derived from this statement — `ccprintf("dump level: %d\n", debug_level);`. When the condition holds it runs `else {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800968c** [unreached] — `cmp r3, #0x22` then `bne`: taken when r3 != constant 0x22. r3 = byte [r5+6] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 0x22.
  - rebuilt C (usb_pd_protocol.c:2917): `level = strtoi(argv[2], &e, 10);`
  - **What:** a conditional derived from this statement — `level = strtoi(argv[2], &e, 10);`. When the condition holds it runs `if (*e)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080096a4** [unreached] — `asrs r3, r0, #1` sets flags from a shifted value (bit test) then `bhi`. operand = byte [r5+6] (a struct/buffer field). MISSING (unreached) needs the tested bit set.
  - rebuilt C (usb_pd_protocol.c:2920): `debug_level = level;`
  - **What:** a conditional derived from this statement — `debug_level = level;`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080195cc** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (usb_pd_protocol.c:2849): `set_state(port, PD_STATE_SNK_DISCONNECTED);`
  - **What:** a conditional derived from this statement — `set_state(port, PD_STATE_SNK_DISCONNECTED);`. When the condition holds it runs `task_wake(PD_PORT_TO_TASK_ID(port));`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x080195e4** (RW mirror) [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (usb_pd_protocol.c:2870): `{`
  - **What:** a conditional derived from this statement — `{`. When the condition holds it runs `int port;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801964a** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = byte [r5+5] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:2900): `pd_set_dual_role(PD_DRP_TOGGLE_OFF);`
  - **What:** a conditional derived from this statement — `pd_set_dual_role(PD_DRP_TOGGLE_OFF);`. When the condition holds it runs `else if (!strcasecmp(argv[2], "sink"))`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019678** (RW mirror) [nottaken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:2911): `if (!strcasecmp(argv[1], "dump")) {`
  - **What:** an `if` test — `if (!strcasecmp(argv[1], "dump")) {`. When the condition holds it runs `int level;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019684** (RW mirror) [unreached] — `cmp r3, #5` then `bne`: taken when r3 != constant 5. r3 = byte [r5+6] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 5.
  - rebuilt C (usb_pd_protocol.c:2915): `ccprintf("dump level: %d\n", debug_level);`
  - **What:** a conditional derived from this statement — `ccprintf("dump level: %d\n", debug_level);`. When the condition holds it runs `else {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801968c** (RW mirror) [unreached] — `cmp r3, #0x22` then `bne`: taken when r3 != constant 0x22. r3 = byte [r5+6] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 0x22.
  - rebuilt C (usb_pd_protocol.c:2917): `level = strtoi(argv[2], &e, 10);`
  - **What:** a conditional derived from this statement — `level = strtoi(argv[2], &e, 10);`. When the condition holds it runs `if (*e)`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x080196a4** (RW mirror) [unreached] — `asrs r3, r0, #1` sets flags from a shifted value (bit test) then `bhi`. operand = byte [r5+6] (a struct/buffer field). MISSING (unreached) needs the tested bit set.
  - rebuilt C (usb_pd_protocol.c:2920): `debug_level = level;`
  - **What:** a conditional derived from this statement — `debug_level = level;`. When the condition holds it runs `return EC_SUCCESS;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x080096d8  `pd_request_source_voltage`  (conf:approx)
**Signature:** `void pd_request_source_voltage(int port, int mv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:2839  | rebuilt @ 0x80095e0 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x080196f0** (RW mirror) [taken-only] — `cmp r2, #1` then `bhi`: taken when r2 >u constant 1. r2 = computed (subs #8). MISSING direction (taken-only) needs r2 <=u constant 1.
  - rebuilt C (usb_pd_protocol.c:2842): `if (pd[port].task_state == PD_STATE_SNK_READY ||`
  - **What:** an `if` test — `if (pd[port].task_state == PD_STATE_SNK_READY ||`. When the condition holds it runs `pd[port].task_state == PD_STATE_SNK_TRANSITION) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800971c  `command_pd`  (conf:approx)
**Signature:** `static int command_pd(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_protocol.c:2870  | rebuilt @ 0x8009624 | 10 uncovered (0 unreached, 10 one-dir; 5 in RW mirror)

- **0x08009748** [taken-only] — `cmp r0, #3` then `bls`: taken when r0 <=u constant 3. r0 = byte [r3+1] (a struct/buffer field). MISSING direction (taken-only) needs r0 >u constant 3.
  - rebuilt C (usb_pd_protocol.c:2882): `switch (drp_state) {`
  - **What:** a `switch` dispatch on the value — `switch (drp_state) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08009876** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:2987): `pd[port].power_role = PD_ROLE_SOURCE;`
  - **What:** a conditional derived from this statement — `pd[port].power_role = PD_ROLE_SOURCE;`. When the condition holds it runs `tcpm_set_cc(port, TYPEC_CC_RP);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009aae** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:3053): `} else if (!strncasecmp(argv[3], "curr", 4)) {`
  - **What:** an `if` test — `} else if (!strncasecmp(argv[3], "curr", 4)) {`. When the condition holds it runs `pd_send_vdm(port, USB_VID_GOOGLE, VDO_CMD_CURRENT,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009b1e** [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = byte [r0+0] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:3069): `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`
  - **What:** a conditional derived from this statement — `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`. When the condition holds it runs `"State: %s, Flags: 0x%04x\n",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08009b52** [nottaken-only] — `lsls r2, r2, #0x13` sets flags from a shifted value (bit test) then `bmi`. operand = halfword [r2+2] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (usb_pd_protocol.c:3069): `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`
  - **What:** a conditional derived from this statement — `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`. When the condition holds it runs `"State: %s, Flags: 0x%04x\n",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019748** (RW mirror) [taken-only] — `cmp r0, #3` then `bls`: taken when r0 <=u constant 3. r0 = byte [r3+1] (a struct/buffer field). MISSING direction (taken-only) needs r0 >u constant 3.
  - rebuilt C (usb_pd_protocol.c:2882): `switch (drp_state) {`
  - **What:** a `switch` dispatch on the value — `switch (drp_state) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019876** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:2987): `pd[port].power_role = PD_ROLE_SOURCE;`
  - **What:** a conditional derived from this statement — `pd[port].power_role = PD_ROLE_SOURCE;`. When the condition holds it runs `tcpm_set_cc(port, TYPEC_CC_RP);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019aae** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (usb_pd_protocol.c:3053): `} else if (!strncasecmp(argv[3], "curr", 4)) {`
  - **What:** an `if` test — `} else if (!strncasecmp(argv[3], "curr", 4)) {`. When the condition holds it runs `pd_send_vdm(port, USB_VID_GOOGLE, VDO_CMD_CURRENT,`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019b1e** (RW mirror) [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = byte [r0+0] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_protocol.c:3069): `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`
  - **What:** a conditional derived from this statement — `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`. When the condition holds it runs `"State: %s, Flags: 0x%04x\n",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019b52** (RW mirror) [nottaken-only] — `lsls r2, r2, #0x13` sets flags from a shifted value (bit test) then `bmi`. operand = halfword [r2+2] (a struct/buffer field). MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (usb_pd_protocol.c:3069): `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`
  - **What:** a conditional derived from this statement — `ccprintf("Port C%d CC%d, %s - Role: %s-%s%s "`. When the condition holds it runs `"State: %s, Flags: 0x%04x\n",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08009c30  `crc32_init`  (conf:approx)
**Signature:** `static inline void crc32_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/chip/stm32/crc_hw.h:14  | rebuilt @ 0x8009b14 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x08009c50** [nottaken-only] — `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (crc_hw.h:22 (discriminator 1)): `while (STM32_CRC_CR & 1)`
  - **What:** a loop condition — `while (STM32_CRC_CR & 1)`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019c50** (RW mirror) [nottaken-only] — `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
  - rebuilt C (crc_hw.h:22 (discriminator 1)): `while (STM32_CRC_CR & 1)`
  - **What:** a loop condition — `while (STM32_CRC_CR & 1)`. When the condition holds it runs `;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x08009cc4  `command_tcpc`  (conf:approx)
**Signature:** `static int command_tcpc(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_tcpc.c:1310  | rebuilt @ 0x8009c00 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x08019d78** (RW mirror) [taken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = byte [r2+0xa] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
  - rebuilt C (usb_pd_tcpc.c:1351): `ccprintf("Port C%d, %s - CC:%d, CC0:%d, CC1:%d\n"`
  - **What:** a conditional derived from this statement — `ccprintf("Port C%d, %s - CC:%d, CC0:%d, CC1:%d\n"`. When the condition holds it runs `"Alert: 0x%02x Mask: 0x%04x\n"`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x08009eb0  `pd_analyze_rx`  (conf:approx)
**Signature:** `int pd_analyze_rx(int port, uint32_t *payload)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_tcpc.c:609  | rebuilt @ 0x8009de8 | 14 uncovered (0 unreached, 14 one-dir; 7 in RW mirror)

- **0x08009edc** [nottaken-only] — `cmp r4, #0` then `ble`: taken when r4 <= constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 <= constant 0.
  - rebuilt C (usb_pd_tcpc.c:631): `while (bit > 0) {`
  - **What:** a loop condition — `while (bit > 0) {`. When the condition holds it runs `bit = pd_dequeue_bits(port, bit, 20, &val);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009f04** [nottaken-only] — `cmp r3, r2` then `bne`: taken when r3 != r2 (= a global/constant (pc-relative load)). r3 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r3 != r2 (= a global/constant (pc-relative load)).
  - rebuilt C (usb_pd_tcpc.c:639): `CPRINTF("SOP''\n");`
  - **What:** a conditional derived from this statement — `CPRINTF("SOP''\n");`. When the condition holds it runs `return PD_RX_ERR_UNSUPPORTED_SOP;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009f16** [nottaken-only] — `cmp r4, #0` then `blt`: taken when r4 < constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 < constant 0.
  - rebuilt C (usb_pd_tcpc.c:649): `bit = decode_short(port, bit, &header);`
  - **What:** a conditional derived from this statement — `bit = decode_short(port, bit, &header);`. When the condition holds it runs `#ifdef CONFIG_COMMON_RUNTIME`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009f68** [nottaken-only] — `cmp r4, #0` then `ble`: taken when r4 <= constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 <= constant 0.
  - rebuilt C (usb_pd_tcpc.c:547 (discriminator 4)): `off = decode_short(port, off, (uint16_t *)val32);`
  - **What:** a conditional derived from this statement — `off = decode_short(port, off, (uint16_t *)val32);`. When the condition holds it runs `return decode_short(port, off, ((uint16_t *)val32 + 1));`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009fb2** [nottaken-only] — `cmp r3, r6` then `beq`: taken when r3 == r6 (= register r6). r3 = word [sp+0x20] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == r6 (= register r6).
  - rebuilt C (usb_pd_tcpc.c:680): `bit = PD_RX_ERR_CRC;`
  - **What:** a conditional derived from this statement — `bit = PD_RX_ERR_CRC;`. When the condition holds it runs `if (debug_level >= 1)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08009fc0** [taken-only] — `cmp r2, #0` then `ble`: taken when r2 <= constant 0. r2 = word [r2+0x7c] (a struct/buffer field). MISSING direction (taken-only) needs r2 > constant 0.
  - rebuilt C (usb_pd_tcpc.c:682): `CPRINTF("CRC%d %08x <> %08x\n", port, pcrc, ccrc);`
  - **What:** a conditional derived from this statement — `CPRINTF("CRC%d %08x <> %08x\n", port, pcrc, ccrc);`. When the condition holds it runs `goto packet_err;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08009fde** [nottaken-only] — flags from `subs r4, r0, #0` then `blt`; MISSING direction (nottaken-only) needs the result to make `blt` go the other way
  - rebuilt C (usb_pd_tcpc.c:692): `if (bit < 0 || eop != PD_EOP) {`
  - **What:** an `if` test — `if (bit < 0 || eop != PD_EOP) {`. When the condition holds it runs `msg = "EOP";`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019edc** (RW mirror) [nottaken-only] — `cmp r4, #0` then `ble`: taken when r4 <= constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 <= constant 0.
  - rebuilt C (usb_pd_tcpc.c:631): `while (bit > 0) {`
  - **What:** a loop condition — `while (bit > 0) {`. When the condition holds it runs `bit = pd_dequeue_bits(port, bit, 20, &val);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019f04** (RW mirror) [nottaken-only] — `cmp r3, r2` then `bne`: taken when r3 != r2 (= a global/constant (pc-relative load)). r3 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r3 != r2 (= a global/constant (pc-relative load)).
  - rebuilt C (usb_pd_tcpc.c:639): `CPRINTF("SOP''\n");`
  - **What:** a conditional derived from this statement — `CPRINTF("SOP''\n");`. When the condition holds it runs `return PD_RX_ERR_UNSUPPORTED_SOP;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019f16** (RW mirror) [nottaken-only] — `cmp r4, #0` then `blt`: taken when r4 < constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 < constant 0.
  - rebuilt C (usb_pd_tcpc.c:649): `bit = decode_short(port, bit, &header);`
  - **What:** a conditional derived from this statement — `bit = decode_short(port, bit, &header);`. When the condition holds it runs `#ifdef CONFIG_COMMON_RUNTIME`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019f68** (RW mirror) [nottaken-only] — `cmp r4, #0` then `ble`: taken when r4 <= constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 <= constant 0.
  - rebuilt C (usb_pd_tcpc.c:547 (discriminator 4)): `off = decode_short(port, off, (uint16_t *)val32);`
  - **What:** a conditional derived from this statement — `off = decode_short(port, off, (uint16_t *)val32);`. When the condition holds it runs `return decode_short(port, off, ((uint16_t *)val32 + 1));`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019fb2** (RW mirror) [nottaken-only] — `cmp r3, r6` then `beq`: taken when r3 == r6 (= register r6). r3 = word [sp+0x20] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == r6 (= register r6).
  - rebuilt C (usb_pd_tcpc.c:680): `bit = PD_RX_ERR_CRC;`
  - **What:** a conditional derived from this statement — `bit = PD_RX_ERR_CRC;`. When the condition holds it runs `if (debug_level >= 1)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x08019fc0** (RW mirror) [taken-only] — `cmp r2, #0` then `ble`: taken when r2 <= constant 0. r2 = word [r2+0x7c] (a struct/buffer field). MISSING direction (taken-only) needs r2 > constant 0.
  - rebuilt C (usb_pd_tcpc.c:682): `CPRINTF("CRC%d %08x <> %08x\n", port, pcrc, ccrc);`
  - **What:** a conditional derived from this statement — `CPRINTF("CRC%d %08x <> %08x\n", port, pcrc, ccrc);`. When the condition holds it runs `goto packet_err;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x08019fde** (RW mirror) [nottaken-only] — flags from `subs r4, r0, #0` then `blt`; MISSING direction (nottaken-only) needs the result to make `blt` go the other way
  - rebuilt C (usb_pd_tcpc.c:692): `if (bit < 0 || eop != PD_EOP) {`
  - **What:** an `if` test — `if (bit < 0 || eop != PD_EOP) {`. When the condition holds it runs `msg = "EOP";`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800a05c  `tcpc_run`  (conf:approx)
**Signature:** `int tcpc_run(int port, int evt)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_tcpc.c:760  | rebuilt @ 0x8009f90 | 10 uncovered (2 unreached, 8 one-dir; 5 in RW mirror)

- **0x0800a1b2** [taken-only] — `cmp r6, #0` then `bge`: taken when r6 >= constant 0. r6 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r6 < constant 0.
  - rebuilt C (usb_pd_tcpc.c:808): `if (res >= 0)`
  - **What:** an `if` test — `if (res >= 0)`. When the condition holds it runs `alert(port, TCPC_REG_ALERT_TX_SUCCESS);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800a1c6** [taken-only] — `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = word [r3+0x7c] (a struct/buffer field). MISSING direction (taken-only) needs r3 > constant 0.
  - rebuilt C (usb_pd_tcpc.c:429): `CPRINTF("TX NOACK%d %04x/%d\n", port, header, cnt);`
  - **What:** a conditional derived from this statement — `CPRINTF("TX NOACK%d %04x/%d\n", port, header, cnt);`. When the condition holds it runs `return PD_TX_ERR_GOODCRC;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800a2aa** [unreached] — flags from `adds r3, r6, #1` then `bne`; MISSING direction (unreached) needs the result to make `bne` go the other way
  - rebuilt C (usb_pd_tcpc.c:813): `alert(port, TCPC_REG_ALERT_TX_DISCARDED);`
  - **What:** a conditional derived from this statement — `alert(port, TCPC_REG_ALERT_TX_DISCARDED);`. When the condition holds it runs `} else {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800a312** [nottaken-only] — `cmp r0, #0xf9` then `bgt`: taken when r0 > constant 0xf9. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 > constant 0xf9.
  - rebuilt C (usb_pd_tcpc.c:273): `*buf_ptr = *buf_ptr == RX_BUFFER_SIZE ? 0 : *buf_ptr + 1;`
  - **What:** a ternary `?:` test — `*buf_ptr = *buf_ptr == RX_BUFFER_SIZE ? 0 : *buf_ptr + 1;`. When the condition holds it runs `static inline int encode_short(int port, int off, uint16_t val16)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800a398** [nottaken-only] — `cmp r0, #0` then `blt`: taken when r0 < constant 0. r0 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r0 < constant 0.
  - rebuilt C (usb_pd_tcpc.c:854): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `#ifndef CONFIG_USB_POWER_DELIVERY`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801a0f8** (RW mirror) [taken-only] — `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r2 != constant 0.
  - rebuilt C (usb_pd_tcpc.c:791): `res = send_validate_message(port,`
  - **What:** a conditional derived from this statement — `res = send_validate_message(port,`. When the condition holds it runs `pd[port].tx_head,`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801a1b2** (RW mirror) [taken-only] — `cmp r6, #0` then `bge`: taken when r6 >= constant 0. r6 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r6 < constant 0.
  - rebuilt C (usb_pd_tcpc.c:808): `if (res >= 0)`
  - **What:** an `if` test — `if (res >= 0)`. When the condition holds it runs `alert(port, TCPC_REG_ALERT_TX_SUCCESS);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801a2aa** (RW mirror) [unreached] — flags from `adds r3, r6, #1` then `bne`; MISSING direction (unreached) needs the result to make `bne` go the other way
  - rebuilt C (usb_pd_tcpc.c:813): `alert(port, TCPC_REG_ALERT_TX_DISCARDED);`
  - **What:** a conditional derived from this statement — `alert(port, TCPC_REG_ALERT_TX_DISCARDED);`. When the condition holds it runs `} else {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801a312** (RW mirror) [nottaken-only] — `cmp r0, #0xf9` then `bgt`: taken when r0 > constant 0xf9. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 > constant 0xf9.
  - rebuilt C (usb_pd_tcpc.c:273): `*buf_ptr = *buf_ptr == RX_BUFFER_SIZE ? 0 : *buf_ptr + 1;`
  - **What:** a ternary `?:` test — `*buf_ptr = *buf_ptr == RX_BUFFER_SIZE ? 0 : *buf_ptr + 1;`. When the condition holds it runs `static inline int encode_short(int port, int off, uint16_t val16)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801a398** (RW mirror) [nottaken-only] — `cmp r0, #0` then `blt`: taken when r0 < constant 0. r0 = computed (adds r7, #0). MISSING direction (nottaken-only) needs r0 < constant 0.
  - rebuilt C (usb_pd_tcpc.c:854): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `#ifndef CONFIG_USB_POWER_DELIVERY`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800a408  `tcpc_alert_status_clear`  (conf:high)
**Signature:** `int tcpc_alert_status_clear(int port, uint16_t mask)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/usb_pd_tcpc.c:893  | rebuilt @ 0x800a2f8 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800a430** [taken-only] — `cmp r4, r5` then `beq`: taken when r4 == r5 (= word [r4+0x50] (a struct/buffer field)). r4 = computed (adds r6, #1). MISSING direction (taken-only) needs r4 != r5 (= word [r4+0x50] (a struct/buffer field)).
  - rebuilt C (usb_pd_tcpc.c:902): `if (!rx_buf_is_empty(port))`
  - **What:** an `if` test — `if (!rx_buf_is_empty(port))`. When the condition holds it runs `mask &= ~TCPC_REG_ALERT_RX_STATUS;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801a430** (RW mirror) [taken-only] — `cmp r4, r5` then `beq`: taken when r4 == r5 (= word [r4+0x50] (a struct/buffer field)). r4 = computed (adds r6, #1). MISSING direction (taken-only) needs r4 != r5 (= word [r4+0x50] (a struct/buffer field)).
  - rebuilt C (usb_pd_tcpc.c:902): `if (!rx_buf_is_empty(port))`
  - **What:** an `if` test — `if (!rx_buf_is_empty(port))`. When the condition holds it runs `mask &= ~TCPC_REG_ALERT_RX_STATUS;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800a580  `uint64divmod`  (conf:approx)
**Signature:** `int uint64divmod(uint64_t *n, int d)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/util.c:338  | rebuilt @ 0x800a7fc | 6 uncovered (2 unreached, 4 one-dir; 3 in RW mirror)

- **0x0800a5ac** [taken-only] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = byte [r3+3] (a struct/buffer field). MISSING direction (taken-only) needs r2 == constant 1.
  - rebuilt C (util.c:352): `return r;`
  - **What:** a conditional derived from this statement — `return r;`. When the condition holds it runs `} else if (d == 16) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800a5b2** [unreached] — `cmp r0, r2` then `bgt`: taken when r0 > r2 (= a global/constant (pc-relative load)). r0 = computed (uxtb r4). MISSING direction (unreached) needs r0 > r2 (= a global/constant (pc-relative load)).
  - rebuilt C (util.c:355): `*n >>= 4;`
  - **What:** a conditional derived from this statement — `*n >>= 4;`. When the condition holds it runs `return r;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800a5dc** [nottaken-only] — `cmp r0, #0xf9` then `bgt`: taken when r0 > constant 0xf9. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 > constant 0xf9.
  - rebuilt C (util.c:364): `return r;`
  - **What:** a conditional derived from this statement — `return r;`. When the condition holds it runs `for (mask = (1ULL << 63); mask; mask >>= 1) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801a5ac** (RW mirror) [taken-only] — `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = byte [r3+3] (a struct/buffer field). MISSING direction (taken-only) needs r2 == constant 1.
  - rebuilt C (util.c:352): `return r;`
  - **What:** a conditional derived from this statement — `return r;`. When the condition holds it runs `} else if (d == 16) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801a5b2** (RW mirror) [unreached] — `cmp r0, r2` then `bgt`: taken when r0 > r2 (= a global/constant (pc-relative load)). r0 = computed (uxtb r4). MISSING direction (unreached) needs r0 > r2 (= a global/constant (pc-relative load)).
  - rebuilt C (util.c:355): `*n >>= 4;`
  - **What:** a conditional derived from this statement — `*n >>= 4;`. When the condition holds it runs `return r;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801a5dc** (RW mirror) [nottaken-only] — `cmp r0, #0xf9` then `bgt`: taken when r0 > constant 0xf9. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 > constant 0xf9.
  - rebuilt C (util.c:364): `return r;`
  - **What:** a conditional derived from this statement — `return r;`. When the condition holds it runs `for (mask = (1ULL << 63); mask; mask >>= 1) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800a672  `strncasecmp`  (conf:approx)
**Signature:** `int strncasecmp(const char *s1, const char *s2, size_t size)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/util.c:61  | rebuilt @ 0x800a520 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800a6a0** [nottaken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = byte [r6+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 == constant 0.
  - rebuilt C (util.c:72): `} while (*(s1++) && *(s2++) && --size);`
  - **What:** a conditional derived from this statement — `} while (*(s1++) && *(s2++) && --size);`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801a6a0** (RW mirror) [nottaken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = byte [r6+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 == constant 0.
  - rebuilt C (util.c:72): `} while (*(s1++) && *(s2++) && --size);`
  - **What:** a conditional derived from this statement — `} while (*(s1++) && *(s2++) && --size);`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800a6ba  `strcasecmp`  (conf:approx)
**Signature:** `int strcasecmp(const char *s1, const char *s2)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/util.c:50  | rebuilt @ 0x800a568 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800a6e2** [taken-only] — `cmp r5, #0` then `bne`: taken when r5 != constant 0. r5 = byte [r6+0] (a struct/buffer field). MISSING direction (taken-only) needs r5 == constant 0.
  - rebuilt C (util.c:56 (discriminator 1)): `} while (*(s1++) && *(s2++));`
  - **What:** a conditional derived from this statement — `} while (*(s1++) && *(s2++));`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801a6e2** (RW mirror) [taken-only] — `cmp r5, #0` then `bne`: taken when r5 != constant 0. r5 = byte [r6+0] (a struct/buffer field). MISSING direction (taken-only) needs r5 == constant 0.
  - rebuilt C (util.c:56 (discriminator 1)): `} while (*(s1++) && *(s2++));`
  - **What:** a conditional derived from this statement — `} while (*(s1++) && *(s2++));`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800a842  `memcpy`  (conf:approx)
**Signature:** `void *memcpy(void *dest, const void *src, size_t len)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/util.c:175  | rebuilt @ 0x800a6f2 | 1 uncovered (0 unreached, 1 one-dir; 0 in RW mirror)

- **0x0800a85c** [nottaken-only] — `cmp r2, r3` then `blo`: taken when r2 <u r3 (= computed (adds r0, r6)). r2 = computed (adds r0, r2). MISSING direction (nottaken-only) needs r2 <u r3 (= computed (adds r0, r6)).
  - rebuilt C (util.c:190): `if ((uintptr_t)tail < (((uintptr_t)d + 3) & ~3))`
  - **What:** an `if` test — `if ((uintptr_t)tail < (((uintptr_t)d + 3) & ~3))`. When the condition holds it runs `head = tail;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800a8cc  `memmove`  (conf:high)
**Signature:** `void *memmove(void *dest, const void *src, size_t len)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/util.c:257  | rebuilt @ 0x800a77e | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800a8f4** [nottaken-only] — `cmp r0, r1` then `bhi`: taken when r0 >u r1 (= computed (adds r2, #0)). r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 >u r1 (= computed (adds r2, #0)).
  - rebuilt C (util.c:279): `if ((uintptr_t)tail > ((uintptr_t)d & ~3))`
  - **What:** an `if` test — `if ((uintptr_t)tail > ((uintptr_t)d & ~3))`. When the condition holds it runs `head = tail;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801a8f4** (RW mirror) [nottaken-only] — `cmp r0, r1` then `bhi`: taken when r0 >u r1 (= computed (adds r2, #0)). r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 >u r1 (= computed (adds r2, #0)).
  - rebuilt C (util.c:279): `if ((uintptr_t)tail > ((uintptr_t)d & ~3))`
  - **What:** an `if` test — `if ((uintptr_t)tail > ((uintptr_t)d & ~3))`. When the condition holds it runs `head = tail;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800aa40  `vboot_hash_start`  (conf:approx)
**Signature:** `static int vboot_hash_start(uint32_t offset, uint32_t size, const uint8_t *nonce, int nonce_size)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/vboot_hash.c:154  | rebuilt @ 0x800a8d0 | 8 uncovered (0 unreached, 8 one-dir; 4 in RW mirror)

- **0x0800aa50** [nottaken-only] — `cmp r0, r6` then `bhi`: taken when r0 >u r6 (= computed (lsls r6, #0xa)). r0 = function argument r0. MISSING direction (nottaken-only) needs r0 >u r6 (= computed (lsls r6, #0xa)).
  - rebuilt C (vboot_hash.c:163): `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`
  - **What:** an `if` test — `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`. When the condition holds it runs `offset + size > CONFIG_FLASH_SIZE || nonce_size < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800aa5a** [nottaken-only] — `cmp r7, r6` then `bhi`: taken when r7 >u r6 (= computed (lsls r6, #0xa)). r7 = computed (adds r0, r1). MISSING direction (nottaken-only) needs r7 >u r6 (= computed (lsls r6, #0xa)).
  - rebuilt C (vboot_hash.c:163 (discriminator 2)): `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`
  - **What:** an `if` test — `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`. When the condition holds it runs `offset + size > CONFIG_FLASH_SIZE || nonce_size < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800aa5e** [nottaken-only] — `cmp r3, #0` then `blt`: taken when r3 < constant 0. r3 = function argument r3. MISSING direction (nottaken-only) needs r3 < constant 0.
  - rebuilt C (vboot_hash.c:163 (discriminator 2)): `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`
  - **What:** an `if` test — `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`. When the condition holds it runs `offset + size > CONFIG_FLASH_SIZE || nonce_size < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800aa88** [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = register r6. MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (vboot_hash.c:179): `if (nonce_size)`
  - **What:** an `if` test — `if (nonce_size)`. When the condition holds it runs `SHA256_update(&ctx, nonce, nonce_size);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801aa50** (RW mirror) [nottaken-only] — `cmp r0, r6` then `bhi`: taken when r0 >u r6 (= computed (lsls r6, #0xa)). r0 = function argument r0. MISSING direction (nottaken-only) needs r0 >u r6 (= computed (lsls r6, #0xa)).
  - rebuilt C (vboot_hash.c:163): `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`
  - **What:** an `if` test — `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`. When the condition holds it runs `offset + size > CONFIG_FLASH_SIZE || nonce_size < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801aa5a** (RW mirror) [nottaken-only] — `cmp r7, r6` then `bhi`: taken when r7 >u r6 (= computed (lsls r6, #0xa)). r7 = computed (adds r0, r1). MISSING direction (nottaken-only) needs r7 >u r6 (= computed (lsls r6, #0xa)).
  - rebuilt C (vboot_hash.c:163 (discriminator 2)): `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`
  - **What:** an `if` test — `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`. When the condition holds it runs `offset + size > CONFIG_FLASH_SIZE || nonce_size < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801aa5e** (RW mirror) [nottaken-only] — `cmp r3, #0` then `blt`: taken when r3 < constant 0. r3 = function argument r3. MISSING direction (nottaken-only) needs r3 < constant 0.
  - rebuilt C (vboot_hash.c:163 (discriminator 2)): `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`
  - **What:** an `if` test — `if (offset > CONFIG_FLASH_SIZE || size > CONFIG_FLASH_SIZE ||`. When the condition holds it runs `offset + size > CONFIG_FLASH_SIZE || nonce_size < 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801aa88** (RW mirror) [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = register r6. MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (vboot_hash.c:179): `if (nonce_size)`
  - **What:** an `if` test — `if (nonce_size)`. When the condition holds it runs `SHA256_update(&ctx, nonce, nonce_size);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800aacc  `fill_response`  (conf:high)
**Signature:** `static void fill_response(struct ec_response_vboot_hash *r, int request_offset)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/vboot_hash.c:351  | rebuilt @ 0x800a95c | 6 uncovered (0 unreached, 6 one-dir; 3 in RW mirror)

- **0x0800aad4** [nottaken-only] — flags from `adds r2, r1, #2` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (vboot_hash.c:343): `if (offset == EC_VBOOT_HASH_OFFSET_RO)`
  - **What:** an `if` test — `if (offset == EC_VBOOT_HASH_OFFSET_RO)`. When the condition holds it runs `return CONFIG_EC_PROTECTED_STORAGE_OFF + CONFIG_RO_STORAGE_OFF;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800aad8** [nottaken-only] — flags from `adds r3, r1, #3` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (vboot_hash.c:345): `if (offset == EC_VBOOT_HASH_OFFSET_RW)`
  - **What:** an `if` test — `if (offset == EC_VBOOT_HASH_OFFSET_RW)`. When the condition holds it runs `return CONFIG_EC_WRITABLE_STORAGE_OFF + CONFIG_RW_STORAGE_OFF;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800aae6** [nottaken-only] — `cmp r3, r2` then `bne`: taken when r3 != r2 (= word [r4+4] (a struct/buffer field)). r3 = computed (lsls r3, #9). MISSING direction (nottaken-only) needs r3 != r2 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (vboot_hash.c:356): `else if (get_offset(request_offset) == data_offset && hash &&`
  - **What:** an `if` test — `else if (get_offset(request_offset) == data_offset && hash &&`. When the condition holds it runs `!want_abort) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801aad4** (RW mirror) [nottaken-only] — flags from `adds r2, r1, #2` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (vboot_hash.c:343): `if (offset == EC_VBOOT_HASH_OFFSET_RO)`
  - **What:** an `if` test — `if (offset == EC_VBOOT_HASH_OFFSET_RO)`. When the condition holds it runs `return CONFIG_EC_PROTECTED_STORAGE_OFF + CONFIG_RO_STORAGE_OFF;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801aad8** (RW mirror) [nottaken-only] — flags from `adds r3, r1, #3` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - rebuilt C (vboot_hash.c:345): `if (offset == EC_VBOOT_HASH_OFFSET_RW)`
  - **What:** an `if` test — `if (offset == EC_VBOOT_HASH_OFFSET_RW)`. When the condition holds it runs `return CONFIG_EC_WRITABLE_STORAGE_OFF + CONFIG_RW_STORAGE_OFF;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801aae6** (RW mirror) [nottaken-only] — `cmp r3, r2` then `bne`: taken when r3 != r2 (= word [r4+4] (a struct/buffer field)). r3 = computed (lsls r3, #9). MISSING direction (nottaken-only) needs r3 != r2 (= word [r4+4] (a struct/buffer field)).
  - rebuilt C (vboot_hash.c:356): `else if (get_offset(request_offset) == data_offset && hash &&`
  - **What:** an `if` test — `else if (get_offset(request_offset) == data_offset && hash &&`. When the condition holds it runs `!want_abort) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800ab64  `vboot_hash_next_chunk`  (conf:approx)
**Signature:** `static void vboot_hash_next_chunk(void);`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/vboot_hash.c:106  | rebuilt @ 0x800a9f4 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800abc4** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+0x14] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (vboot_hash.c:136): `if (want_abort)`
  - **What:** an `if` test — `if (want_abort)`. When the condition holds it runs `vboot_hash_abort();`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801abc4** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+0x14] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (vboot_hash.c:136): `if (want_abort)`
  - **What:** an `if` test — `if (want_abort)`. When the condition holds it runs `vboot_hash_abort();`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800abe4  `command_hash`  (conf:approx)
**Signature:** `static int command_hash(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/vboot_hash.c:267  | rebuilt @ 0x800aa74 | 8 uncovered (2 unreached, 6 one-dir; 4 in RW mirror)

- **0x0800ac14** [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r5+0x14] (a struct/buffer field). MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (vboot_hash.c:277): `if (want_abort)`
  - **What:** an `if` test — `if (want_abort)`. When the condition holds it runs `ccprintf("(aborting)\n");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800acc0** [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (vboot_hash.c:314): `if (*e)`
  - **What:** an `if` test — `if (*e)`. When the condition holds it runs `return EC_ERROR_PARAM2;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800acc8** [taken-only] — `cmp r5, #4` then `bne`: taken when r5 != constant 4. r5 = register r5. MISSING direction (taken-only) needs r5 == constant 4.
  - rebuilt C (vboot_hash.c:309): `offset = strtoi(argv[1], &e, 0);`
  - **What:** a conditional derived from this statement — `offset = strtoi(argv[1], &e, 0);`. When the condition holds it runs `if (*e)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800acdc** [unreached] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 0.
  - rebuilt C (vboot_hash.c:320): `if (*e)`
  - **What:** an `if` test — `if (*e)`. When the condition holds it runs `return EC_ERROR_PARAM3;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801ac14** (RW mirror) [taken-only] — `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r5+0x14] (a struct/buffer field). MISSING direction (taken-only) needs r6 != constant 0.
  - rebuilt C (vboot_hash.c:277): `if (want_abort)`
  - **What:** an `if` test — `if (want_abort)`. When the condition holds it runs `ccprintf("(aborting)\n");`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801acc0** (RW mirror) [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (vboot_hash.c:314): `if (*e)`
  - **What:** an `if` test — `if (*e)`. When the condition holds it runs `return EC_ERROR_PARAM2;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801acc8** (RW mirror) [taken-only] — `cmp r5, #4` then `bne`: taken when r5 != constant 4. r5 = register r5. MISSING direction (taken-only) needs r5 == constant 4.
  - rebuilt C (vboot_hash.c:309): `offset = strtoi(argv[1], &e, 0);`
  - **What:** a conditional derived from this statement — `offset = strtoi(argv[1], &e, 0);`. When the condition holds it runs `if (*e)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801acdc** (RW mirror) [unreached] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 0.
  - rebuilt C (vboot_hash.c:320): `if (*e)`
  - **What:** an `if` test — `if (*e)`. When the condition holds it runs `return EC_ERROR_PARAM3;`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x0800ad2c  `host_command_vboot_hash`  (conf:approx)
**Signature:** `static int host_command_vboot_hash(struct host_cmd_handler_args *args)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/vboot_hash.c:408  | rebuilt @ 0x800abc0 | 14 uncovered (4 unreached, 10 one-dir; 7 in RW mirror)

- **0x0800ada2** [nottaken-only] — `cmp r3, #0x40` then `bhi`: taken when r3 >u constant 0x40. r3 = byte [r4+2] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u constant 0x40.
  - rebuilt C (vboot_hash.c:378): `int size = p->size;`
  - **What:** a conditional derived from this statement — `int size = p->size;`. When the condition holds it runs `int rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800ada6** [taken-only] — flags from `adds r3, r0, #2` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (vboot_hash.c:394): `size = system_get_image_used(SYSTEM_IMAGE_RW);`
  - **What:** a conditional derived from this statement — `size = system_get_image_used(SYSTEM_IMAGE_RW);`. When the condition holds it runs `rv = vboot_hash_start(offset, size, p->nonce_data, p->nonce_size);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800adb6** [taken-only] — flags from `adds r3, r0, #3` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (vboot_hash.c:397): `rv = vboot_hash_start(offset, size, p->nonce_data, p->nonce_size);`
  - **What:** a conditional derived from this statement — `rv = vboot_hash_start(offset, size, p->nonce_data, p->nonce_size);`. When the condition holds it runs `if (rv == EC_SUCCESS)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800add0** [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (lsls r0, #9). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (vboot_hash.c:354): `if (in_progress)`
  - **What:** an `if` test — `if (in_progress)`. When the condition holds it runs `r->status = EC_VBOOT_HASH_STATUS_BUSY;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800add6** [unreached] — `cmp r0, #5` then `bne`: taken when r0 != constant 5. r0 = computed (lsls r0, #9). MISSING direction (unreached) needs r0 != constant 5.
  - rebuilt C (vboot_hash.c:415): `fill_response(r, p->offset);`
  - **What:** a conditional derived from this statement — `fill_response(r, p->offset);`. When the condition holds it runs `args->response_size = sizeof(*r);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800ade0** [nottaken-only] — `cmp r3, #3` then `beq`: taken when r3 == constant 3. r3 = byte [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 3.
  - rebuilt C (vboot_hash.c:415): `fill_response(r, p->offset);`
  - **What:** a conditional derived from this statement — `fill_response(r, p->offset);`. When the condition holds it runs `args->response_size = sizeof(*r);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800ae16** [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r7+0] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (vboot_hash.c:441): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `DECLARE_HOST_COMMAND(EC_CMD_VBOOT_HASH,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801ada2** (RW mirror) [nottaken-only] — `cmp r3, #0x40` then `bhi`: taken when r3 >u constant 0x40. r3 = byte [r4+2] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u constant 0x40.
  - rebuilt C (vboot_hash.c:378): `int size = p->size;`
  - **What:** a conditional derived from this statement — `int size = p->size;`. When the condition holds it runs `int rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801ada6** (RW mirror) [taken-only] — flags from `adds r3, r0, #2` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (vboot_hash.c:394): `size = system_get_image_used(SYSTEM_IMAGE_RW);`
  - **What:** a conditional derived from this statement — `size = system_get_image_used(SYSTEM_IMAGE_RW);`. When the condition holds it runs `rv = vboot_hash_start(offset, size, p->nonce_data, p->nonce_size);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801adb6** (RW mirror) [taken-only] — flags from `adds r3, r0, #3` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - rebuilt C (vboot_hash.c:397): `rv = vboot_hash_start(offset, size, p->nonce_data, p->nonce_size);`
  - **What:** a conditional derived from this statement — `rv = vboot_hash_start(offset, size, p->nonce_data, p->nonce_size);`. When the condition holds it runs `if (rv == EC_SUCCESS)`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801add0** (RW mirror) [taken-only] — `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (lsls r0, #9). MISSING direction (taken-only) needs r0 != constant 0.
  - rebuilt C (vboot_hash.c:354): `if (in_progress)`
  - **What:** an `if` test — `if (in_progress)`. When the condition holds it runs `r->status = EC_VBOOT_HASH_STATUS_BUSY;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801add6** (RW mirror) [unreached] — `cmp r0, #5` then `bne`: taken when r0 != constant 5. r0 = computed (lsls r0, #9). MISSING direction (unreached) needs r0 != constant 5.
  - rebuilt C (vboot_hash.c:415): `fill_response(r, p->offset);`
  - **What:** a conditional derived from this statement — `fill_response(r, p->offset);`. When the condition holds it runs `args->response_size = sizeof(*r);`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801ade0** (RW mirror) [nottaken-only] — `cmp r3, #3` then `beq`: taken when r3 == constant 3. r3 = byte [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 3.
  - rebuilt C (vboot_hash.c:415): `fill_response(r, p->offset);`
  - **What:** a conditional derived from this statement — `fill_response(r, p->offset);`. When the condition holds it runs `args->response_size = sizeof(*r);`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801ae16** (RW mirror) [unreached] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r7+0] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
  - rebuilt C (vboot_hash.c:441): `}`
  - **What:** a conditional derived from this statement — `}`. When the condition holds it runs `DECLARE_HOST_COMMAND(EC_CMD_VBOOT_HASH,`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x0800ae2c  `vboot_hash_invalidate`  (conf:approx)
**Signature:** `int vboot_hash_invalidate(int offset, int size)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/common/vboot_hash.c:188  | rebuilt @ 0x800acb0 | 6 uncovered (0 unreached, 6 one-dir; 3 in RW mirror)

- **0x0800ae3c** [nottaken-only] — flags from `adds r5, r2, r1` then `bmi`; MISSING direction (nottaken-only) needs the result to make `bmi` go the other way
  - rebuilt C (vboot_hash.c:190 (discriminator 2)): `if (offset < 0 || size <= 0 || offset + size < 0)`
  - **What:** an `if` test — `if (offset < 0 || size <= 0 || offset + size < 0)`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800ae4a** [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (vboot_hash.c:201): `if (data_size > 0 &&`
  - **What:** an `if` test — `if (data_size > 0 &&`. When the condition holds it runs `(offset + size <= data_offset || offset >= data_offset + data_size))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800ae58** [nottaken-only] — `cmp r2, r3` then `bhs`: taken when r2 >=u r3 (= computed (adds r4, r3)). r2 = function argument r2. MISSING direction (nottaken-only) needs r2 >=u r3 (= computed (adds r4, r3)).
  - rebuilt C (vboot_hash.c:202): `(offset + size <= data_offset || offset >= data_offset + data_size))`
  - **What:** a conditional derived from this statement — `(offset + size <= data_offset || offset >= data_offset + data_size))`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801ae3c** (RW mirror) [nottaken-only] — flags from `adds r5, r2, r1` then `bmi`; MISSING direction (nottaken-only) needs the result to make `bmi` go the other way
  - rebuilt C (vboot_hash.c:190 (discriminator 2)): `if (offset < 0 || size <= 0 || offset + size < 0)`
  - **What:** an `if` test — `if (offset < 0 || size <= 0 || offset + size < 0)`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801ae4a** (RW mirror) [nottaken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - rebuilt C (vboot_hash.c:201): `if (data_size > 0 &&`
  - **What:** an `if` test — `if (data_size > 0 &&`. When the condition holds it runs `(offset + size <= data_offset || offset >= data_offset + data_size))`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801ae58** (RW mirror) [nottaken-only] — `cmp r2, r3` then `bhs`: taken when r2 >=u r3 (= computed (adds r4, r3)). r2 = function argument r2. MISSING direction (nottaken-only) needs r2 >=u r3 (= computed (adds r4, r3)).
  - rebuilt C (vboot_hash.c:202): `(offset + size <= data_offset || offset >= data_offset + data_size))`
  - **What:** a conditional derived from this statement — `(offset + size <= data_offset || offset >= data_offset + data_size))`. When the condition holds it runs `return 0;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800afa0  `panic_data_print`  (conf:approx)
**Signature:** `void panic_data_print(const struct panic_data *pdata)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/panic.c:81  | rebuilt @ 0x800ae20 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800afd2** [taken-only] — `cmp r7, #0` then `beq`: taken when r7 == constant 0. r7 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r7 != constant 0.
  - rebuilt C (panic.c:91): `panic_printf("\n=== %s EXCEPTION: %02x ====== xPSR: %08x ===\n",`
  - **What:** a conditional derived from this statement — `panic_printf("\n=== %s EXCEPTION: %02x ====== xPSR: %08x ===\n",`. When the condition holds it runs `in_handler ? "HANDLER" : "PROCESS",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801afd2** (RW mirror) [taken-only] — `cmp r7, #0` then `beq`: taken when r7 == constant 0. r7 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r7 != constant 0.
  - rebuilt C (panic.c:91): `panic_printf("\n=== %s EXCEPTION: %02x ====== xPSR: %08x ===\n",`
  - **What:** a conditional derived from this statement — `panic_printf("\n=== %s EXCEPTION: %02x ====== xPSR: %08x ===\n",`. When the condition holds it runs `in_handler ? "HANDLER" : "PROCESS",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800b05c  `report_panic`  (conf:approx)
**Signature:** `void __keep report_panic(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/panic.c:107  | rebuilt @ 0x800aedc | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800b086** [nottaken-only] — flags from `ands r3, r1` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (panic.c:122): `if ((sp & 3) == 0 &&`
  - **What:** an `if` test — `if ((sp & 3) == 0 &&`. When the condition holds it runs `sp >= CONFIG_RAM_BASE &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b086** (RW mirror) [nottaken-only] — flags from `ands r3, r1` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (panic.c:122): `if ((sp & 3) == 0 &&`
  - **What:** an `if` test — `if ((sp & 3) == 0 &&`. When the condition holds it runs `sp >= CONFIG_RAM_BASE &&`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b14c  `panic_get_reason`  (conf:exact)
**Signature:** `void panic_get_reason(uint32_t *reason, uint32_t *info, uint8_t *exception)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/panic.c:195  | rebuilt @ 0x800afcc | 4 uncovered (2 unreached, 2 one-dir; 2 in RW mirror)

- **0x0800b156** [taken-only] — `cmp r5, r4` then `bne`: taken when r5 != r4 (= a global/constant (pc-relative load)). r5 = word [r3+0x70] (a struct/buffer field). MISSING direction (taken-only) needs r5 == r4 (= a global/constant (pc-relative load)).
  - rebuilt C (panic.c:198): `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`
  - **What:** an `if` test — `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`. When the condition holds it runs `pdata_ptr->struct_version == 2) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800b15c** [unreached] — `cmp r3, #2` then `bne`: taken when r3 != constant 2. r3 = byte [r3+1] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 2.
  - rebuilt C (panic.c:198 (discriminator 1)): `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`
  - **What:** an `if` test — `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`. When the condition holds it runs `pdata_ptr->struct_version == 2) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801b156** (RW mirror) [taken-only] — `cmp r5, r4` then `bne`: taken when r5 != r4 (= a global/constant (pc-relative load)). r5 = word [r3+0x70] (a struct/buffer field). MISSING direction (taken-only) needs r5 == r4 (= a global/constant (pc-relative load)).
  - rebuilt C (panic.c:198): `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`
  - **What:** an `if` test — `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`. When the condition holds it runs `pdata_ptr->struct_version == 2) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b15c** (RW mirror) [unreached] — `cmp r3, #2` then `bne`: taken when r3 != constant 2. r3 = byte [r3+1] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 2.
  - rebuilt C (panic.c:198 (discriminator 1)): `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`
  - **What:** an `if` test — `if (pdata_ptr->magic == PANIC_DATA_MAGIC &&`. When the condition holds it runs `pdata_ptr->struct_version == 2) {`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.

## 0x0800b18c  `bus_fault_handler`  (conf:exact)
**Signature:** `void bus_fault_handler(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/panic.c:210  | rebuilt @ 0x800b00c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800b194** [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (panic.c:211): `if (!bus_fault_ignored)`
  - **What:** an `if` test — `if (!bus_fault_ignored)`. When the condition holds it runs `exception_panic();`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b194** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (panic.c:211): `if (!bus_fault_ignored)`
  - **What:** an `if` test — `if (!bus_fault_ignored)`. When the condition holds it runs `exception_panic();`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b2c0  `__svc_handler`  (conf:approx)
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/task.c:190  | rebuilt @ 0x800b184 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x0801b2fc** (RW mirror) [nottaken-only] — `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r5+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - rebuilt C (task.c:224 (discriminator 1)): `if (desched && !current->events) {`
  - **What:** an `if` test — `if (desched && !current->events) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b350  `svc_handler`  (conf:high)
**Signature:** `void svc_handler(int desched, task_id_t resched)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/task.c:254  | rebuilt @ 0x800b230 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x0801b35c** (RW mirror) [taken-only] — `cmp r1, r0` then `beq`: taken when r1 == r0 (= function argument r0). r1 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r1 != r0 (= function argument r0).
  - rebuilt C (task.c:261): `if (current_task != prev)`
  - **What:** an `if` test — `if (current_task != prev)`. When the condition holds it runs `__switchto(prev, current_task);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800b388  `task_set_event`  (conf:approx)
**Signature:** `uint32_t task_set_event(task_id_t tskid, uint32_t event, int wait)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/task.c:366  | rebuilt @ 0x800b268 | 1 uncovered (0 unreached, 1 one-dir; 1 in RW mirror)

- **0x0801b3c4** (RW mirror) [nottaken-only] — `cmp r3, r0` then `beq`: taken when r3 == r0 (= computed (movs #0)). r3 = word [r6+0x78] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == r0 (= computed (movs #0)).
  - rebuilt C (task.c:376): `atomic_or(&tasks_ready, 1 << tskid);`
  - **What:** a conditional derived from this statement — `atomic_or(&tasks_ready, 1 << tskid);`. When the condition holds it runs `if (start_called) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b42c  `task_wait_event_mask`  (conf:approx)
**Signature:** `uint32_t task_wait_event_mask(uint32_t event_mask, int timeout_us)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/task.c:409  | rebuilt @ 0x800b328 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800b46c** [nottaken-only] — `cmp r6, #0` then `ble`: taken when r6 <= constant 0. r6 = register r6. MISSING direction (nottaken-only) needs r6 <= constant 0.
  - rebuilt C (task.c:421): `time_remaining_us = deadline - get_time().val;`
  - **What:** a conditional derived from this statement — `time_remaining_us = deadline - get_time().val;`. When the condition holds it runs `if (timeout_us > 0 && time_remaining_us <= 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b46c** (RW mirror) [nottaken-only] — `cmp r6, #0` then `ble`: taken when r6 <= constant 0. r6 = register r6. MISSING direction (nottaken-only) needs r6 <= constant 0.
  - rebuilt C (task.c:421): `time_remaining_us = deadline - get_time().val;`
  - **What:** a conditional derived from this statement — `time_remaining_us = deadline - get_time().val;`. When the condition holds it runs `if (timeout_us > 0 && time_remaining_us <= 0) {`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b520  `mutex_unlock`  (conf:high)
**Signature:** `void mutex_unlock(struct mutex *mtx)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/task.c:522  | rebuilt @ 0x800b438 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800b530** [taken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r4 != constant 0.
  - rebuilt C (task.c:533): `waiters &= ~(1 << id);`
  - **What:** a conditional derived from this statement — `waiters &= ~(1 << id);`. When the condition holds it runs `task_set_event(id, TASK_EVENT_MUTEX, 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b530** (RW mirror) [taken-only] — `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r4 != constant 0.
  - rebuilt C (task.c:533): `waiters &= ~(1 << id);`
  - **What:** a conditional derived from this statement — `waiters &= ~(1 << id);`. When the condition holds it runs `task_set_event(id, TASK_EVENT_MUTEX, 0);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800b610  `task_pre_init`  (conf:approx)
**Signature:** `void task_pre_init(void)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/task.c:621  | rebuilt @ 0x800b52c | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800b6a0** [taken-only] — `cmp r7, #3` then `bls`: taken when r7 <=u constant 3. r7 = byte [r2+1] (a struct/buffer field). MISSING direction (taken-only) needs r7 >u constant 3.
  - rebuilt C (task.c:494): `~(0x3 << prio_shift)) |`
  - **What:** a conditional derived from this statement — `~(0x3 << prio_shift)) |`. When the condition holds it runs `(prio << prio_shift);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b6a0** (RW mirror) [taken-only] — `cmp r7, #3` then `bls`: taken when r7 <=u constant 3. r7 = byte [r2+1] (a struct/buffer field). MISSING direction (taken-only) needs r7 >u constant 3.
  - rebuilt C (task.c:494): `~(0x3 << prio_shift)) |`
  - **What:** a conditional derived from this statement — `~(0x3 << prio_shift)) |`. When the condition holds it runs `(prio << prio_shift);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800b72a  `tcpm_init`  (conf:approx)
**Signature:** `int tcpm_init(int port)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/driver/tcpm/stub.c:53  | rebuilt @ 0x800b64a | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800b73c** [nottaken-only] — flags from `subs r1, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (stub.c:58): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b73c** (RW mirror) [nottaken-only] — flags from `subs r1, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - rebuilt C (stub.c:58): `if (rv)`
  - **What:** an `if` test — `if (rv)`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b7f8  `__gnu_thumb1_case_uhi`  (conf:approx)
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/thumb_case.S:56  | rebuilt @ 0x800b636 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x0800b806** [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (thumb_case.S:63): `add     lr, lr, r1`
  - **What:** a conditional derived from this statement — `add     lr, lr, r1`. When the condition holds it runs `pop     {r0, r1}`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800b814** [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #3). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (stub.c:42): `rv = tcpc_alert_mask_set(port, mask);`
  - **What:** a conditional derived from this statement — `rv = tcpc_alert_mask_set(port, mask);`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b806** (RW mirror) [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (thumb_case.S:63): `add     lr, lr, r1`
  - **What:** a conditional derived from this statement — `add     lr, lr, r1`. When the condition holds it runs `pop     {r0, r1}`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b814** (RW mirror) [nottaken-only] — `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #3). MISSING direction (nottaken-only) needs r0 != constant 0.
  - rebuilt C (stub.c:42): `rv = tcpc_alert_mask_set(port, mask);`
  - **What:** a conditional derived from this statement — `rv = tcpc_alert_mask_set(port, mask);`. When the condition holds it runs `return rv;`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b824  `mutex_unlock`  (conf:approx)
**Signature:** `void mutex_unlock(struct mutex *mtx)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/core/cortex-m0/task.c:522  | rebuilt @ 0x800b438 | 4 uncovered (0 unreached, 4 one-dir; 2 in RW mirror)

- **0x0800b838** [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (task.c:531): `while (waiters) {`
  - **What:** a loop condition — `while (waiters) {`. When the condition holds it runs `task_id_t id = __fls(waiters);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800b84a** [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (task.c:536): `task_set_event(id, TASK_EVENT_MUTEX, 0);`
  - **What:** a conditional derived from this statement — `task_set_event(id, TASK_EVENT_MUTEX, 0);`. When the condition holds it runs `atomic_clear(&tsk->events, TASK_EVENT_MUTEX);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b838** (RW mirror) [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (task.c:531): `while (waiters) {`
  - **What:** a loop condition — `while (waiters) {`. When the condition holds it runs `task_id_t id = __fls(waiters);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b84a** (RW mirror) [taken-only] — `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - rebuilt C (task.c:536): `task_set_event(id, TASK_EVENT_MUTEX, 0);`
  - **What:** a conditional derived from this statement — `task_set_event(id, TASK_EVENT_MUTEX, 0);`. When the condition holds it runs `atomic_clear(&tsk->events, TASK_EVENT_MUTEX);`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800b85c  `usb_mux_set`  (conf:approx)
**Signature:** `void usb_mux_set(int port, enum typec_mux mux_mode, enum usb_switch usb_mode, int polarity)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/driver/usb_mux.c:39  | rebuilt @ 0x800b770 | 2 uncovered (0 unreached, 2 one-dir; 1 in RW mirror)

- **0x0800b880** [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_mux.c:53): `CPRINTS("Error setting mux port(%d): %d", port, res);`
  - **What:** a conditional derived from this statement — `CPRINTS("Error setting mux port(%d): %d", port, res);`. When the condition holds it runs `return;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b880** (RW mirror) [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_mux.c:53): `CPRINTS("Error setting mux port(%d): %d", port, res);`
  - **What:** a conditional derived from this statement — `CPRINTS("Error setting mux port(%d): %d", port, res);`. When the condition holds it runs `return;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.

## 0x0800b8b8  `usb_mux_get`  (conf:approx)
**Signature:** `int usb_mux_get(int port, const char **dp_str, const char **usb_str)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/driver/usb_mux.c:64  | rebuilt @ 0x800b7cc | 8 uncovered (0 unreached, 8 one-dir; 4 in RW mirror)

- **0x0800b8d6** [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_mux.c:70): `res = mux->driver->get(mux->port_addr, &mux_state);`
  - **What:** a conditional derived from this statement — `res = mux->driver->get(mux->port_addr, &mux_state);`. When the condition holds it runs `if (res) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800b8ea** [nottaken-only] — `lsls r3, r2, #0x1d` sets flags from a shifted value (bit test) then `bmi`. operand = a value carried in from a preceding basic block. MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (usb_mux.c:76): `dp = mux_state & MUX_POLARITY_INVERTED ? "DP2" : "DP1";`
  - **What:** a ternary `?:` test — `dp = mux_state & MUX_POLARITY_INVERTED ? "DP2" : "DP1";`. When the condition holds it runs `usb = mux_state & MUX_POLARITY_INVERTED ? "USB2" : "USB1";`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800b8fa** [taken-only] — `lsls r6, r2, #0x1e` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (usb_mux.c:79 (discriminator 4)): `*dp_str = mux_state & MUX_DP_ENABLED ? dp : NULL;`
  - **What:** a ternary `?:` test — `*dp_str = mux_state & MUX_DP_ENABLED ? dp : NULL;`. When the condition holds it runs `return *dp_str || *usb_str;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0800b910** [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (usb_mux.c:82 (discriminator 4)): `return *dp_str || *usb_str;`
  - **What:** a conditional derived from this statement — `return *dp_str || *usb_str;`. When the condition holds it runs `void usb_mux_flip(int port)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b8d6** (RW mirror) [taken-only] — flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - rebuilt C (usb_mux.c:70): `res = mux->driver->get(mux->port_addr, &mux_state);`
  - **What:** a conditional derived from this statement — `res = mux->driver->get(mux->port_addr, &mux_state);`. When the condition holds it runs `if (res) {`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b8ea** (RW mirror) [nottaken-only] — `lsls r3, r2, #0x1d` sets flags from a shifted value (bit test) then `bmi`. operand = a value carried in from a preceding basic block. MISSING (nottaken-only) needs the tested bit set.
  - rebuilt C (usb_mux.c:76): `dp = mux_state & MUX_POLARITY_INVERTED ? "DP2" : "DP1";`
  - **What:** a ternary `?:` test — `dp = mux_state & MUX_POLARITY_INVERTED ? "DP2" : "DP1";`. When the condition holds it runs `usb = mux_state & MUX_POLARITY_INVERTED ? "USB2" : "USB1";`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b8fa** (RW mirror) [taken-only] — `lsls r6, r2, #0x1e` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs the tested bit set.
  - rebuilt C (usb_mux.c:79 (discriminator 4)): `*dp_str = mux_state & MUX_DP_ENABLED ? dp : NULL;`
  - **What:** a ternary `?:` test — `*dp_str = mux_state & MUX_DP_ENABLED ? dp : NULL;`. When the condition holds it runs `return *dp_str || *usb_str;`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b910** (RW mirror) [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (usb_mux.c:82 (discriminator 4)): `return *dp_str || *usb_str;`
  - **What:** a conditional derived from this statement — `return *dp_str || *usb_str;`. When the condition holds it runs `void usb_mux_flip(int port)`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.

## 0x0800b934  `command_typec`  (conf:approx)
**Signature:** `static int command_typec(int argc, char **argv)`
**Source:** /home/tim/local/gwifi/ec-rebuild/ec/driver/usb_mux.c:109  | rebuilt @ 0x800b848 | 6 uncovered (2 unreached, 4 one-dir; 3 in RW mirror)

- **0x0800b9ae** [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (usb_mux.c:133): `ccprintf("Superspeed %s%s%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Superspeed %s%s%s\n",`. When the condition holds it runs `dp_str ? dp_str : "",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0800b9b8** [unreached] — `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r1 == constant 0.
  - rebuilt C (usb_mux.c:133 (discriminator 10)): `ccprintf("Superspeed %s%s%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Superspeed %s%s%s\n",`. When the condition holds it runs `dp_str ? dp_str : "",`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0800b9be** [taken-only] — `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant 0.
  - rebuilt C (usb_mux.c:133 (discriminator 14)): `ccprintf("Superspeed %s%s%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Superspeed %s%s%s\n",`. When the condition holds it runs `dp_str ? dp_str : "",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
- **0x0801b9ae** (RW mirror) [nottaken-only] — `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - rebuilt C (usb_mux.c:133): `ccprintf("Superspeed %s%s%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Superspeed %s%s%s\n",`. When the condition holds it runs `dp_str ? dp_str : "",`.
  - **Triggers when:** so far the condition has only ever been **false** (fall-through); the **true** path (branch taken) is never exercised. To cover it, supply an input/state that makes the condition above evaluate **true**.
- **0x0801b9b8** (RW mirror) [unreached] — `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r1 == constant 0.
  - rebuilt C (usb_mux.c:133 (discriminator 10)): `ccprintf("Superspeed %s%s%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Superspeed %s%s%s\n",`. When the condition holds it runs `dp_str ? dp_str : "",`.
  - **Triggers when:** the basic block is **never executed at all** — no test reaches this point yet. Covering it requires first satisfying the enclosing condition(s) so control flow arrives here, then exercising this test.
- **0x0801b9be** (RW mirror) [taken-only] — `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant 0.
  - rebuilt C (usb_mux.c:133 (discriminator 14)): `ccprintf("Superspeed %s%s%s\n",`
  - **What:** a conditional derived from this statement — `ccprintf("Superspeed %s%s%s\n",`. When the condition holds it runs `dp_str ? dp_str : "",`.
  - **Triggers when:** so far the condition has only ever been **true** (this branch taken); the **false / fall-through** path is never exercised. To cover it, supply an input/state that makes the condition above evaluate **false**.
