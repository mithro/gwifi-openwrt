# Why each uncovered branch is not reached — and what would reach it

Generated from the verified `UNCOVERED-BY-FUNCTION.md`. Every uncovered-branch-bearing function is assigned a **reason class**; *why* and *what's required* are stated at the class level (derived from the source subsystem + the disassembled missing-direction), with function notes where independently confirmed.

Coverage state legend: **unreached** = block never executed; **taken-only** / **nottaken-only** = reached but the compare only ever went one way.

## R1 — PD state machine — blocking dispatcher  (276 branches, 23 functions)
**Why not reached:** pd_task and the policy handlers it calls run inside the cooperative dispatcher at 0x8007f8e; the protocol state (`pd[port].task_state`) only advances when LIVE PD traffic arrives in the right order. Direct function-calls cannot drive them, and many SOURCE / swap / error states are entered only one-directionally by the campaign, so the compare against a state/flag/field has only ever gone one way.

**What would be required:** Deliver a specific message TYPE+FIELD while the firmware sits in the exact target state — which usually first requires DRIVING the firmware into that state (e.g. SRC_GET_SINK_CAP, a swap, a retry-exhaust, or the data-request handler 0x80083f0 which is only reached in SRC_DISCOVERY). Several targets need a state the partner model can't currently push the firmware into.

- **`pd_task`** (usb_pd_protocol.c, conf:approx) — 177 uncovered [39 unreached, 77 taken-only, 61 nottaken-only]
  - `0x08008024` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (lsrs r3, #0x1e). MISSING direction (nottaken-only) needs r3 != constant 0.
  - `0x08008028` [nottaken-only] `cmp r2, #1` then `bls`: taken when r2 <=u constant 1. r2 = computed (subs #4). MISSING direction (nottaken-only) needs r2 <=u constant 1.
- **`pd_request_source_voltage`** (usb_pd_protocol.c, conf:approx) — 13 uncovered [6 unreached, 3 taken-only, 4 nottaken-only]
  - `0x080095cc` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 != constant 0.
  - `0x080095e4` [nottaken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
- **`hc_remote_flash`** (usb_pd_protocol.c, conf:approx) — 12 uncovered [4 taken-only, 8 nottaken-only]
  - `0x08007b5c` [taken-only] `cmp r1, r3` then `bls`: taken when r1 <=u r3 (= word [sp+0x14] (a struct/buffer field)). r1 = word [sp+0xc] (a struct/buffer field). MISSING direction (taken-o…
  - `0x08007b68` [nottaken-only] `cmp r1, r3` then `bne`: taken when r1 != r3 (= a value carried in from a preceding basic block). r1 = a value carried in from a preceding basic block. MISSING …
- **`pd_request_source_voltage`** (usb_pd_protocol.c, conf:approx) — 10 uncovered [10 nottaken-only]
  - `0x08009538` [nottaken-only] `cmp r3, r1` then `bhi`: taken when r3 >u r1 (= word [sp+0x34] (a struct/buffer field)). r3 = word [r6+0x14] (a struct/buffer field). MISSING direction (nottake…
  - `0x0800953a` [nottaken-only] `cmp r3, r1` then `bne`: taken when r3 != r1 (= word [sp+0x34] (a struct/buffer field)). r3 = word [r6+0x14] (a struct/buffer field). MISSING direction (nottake…
- **`command_pd`** (usb_pd_protocol.c, conf:approx) — 10 uncovered [4 taken-only, 6 nottaken-only]
  - `0x08009748` [taken-only] `cmp r0, #3` then `bls`: taken when r0 <=u constant 3. r0 = byte [r3+1] (a struct/buffer field). MISSING direction (taken-only) needs r0 >u constant 3.
  - `0x08009876` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
- **`pd_check_requested_voltage`** (usb_pd_policy.c, conf:approx) — 8 uncovered [6 unreached, 2 taken-only]
  - `0x0800729e` [taken-only] flags from `subs r4, r0, #0` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - `0x080072b6` [unreached] `cmp r1, r3` then `bhi`: taken when r1 >u r3 (= computed (lsrs r3, #0x16)). r1 = computed (lsrs r1, #0x16). MISSING direction (unreached) needs r1 >u r3 (= comp…
- **`hc_remote_rw_hash_entry`** (usb_pd_protocol.c, conf:approx) — 8 uncovered [6 unreached, 2 taken-only]
  - `0x0800753c` [taken-only] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (orrs r0). MISSING direction (taken-only) needs r2 != constant 0.
  - `0x08007556` [unreached] `cmp r2, r4` then `beq`: taken when r2 == r4 (= computed (orrs r7)). r2 = function argument r2. MISSING direction (unreached) needs r2 == r4 (= computed (orrs r…
- **`pd_send_request_msg`** (usb_pd_protocol.c, conf:approx) — 5 uncovered [2 unreached, 2 taken-only, 1 nottaken-only]
  - `0x080076e0` [taken-only] `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = register r4. MISSING direction (taken-only) needs r4 == constant 0.
  - `0x080076ea` [unreached] `cmp r3, r2` then `beq`: taken when r3 == r2 (= word [sp+0x18] (a struct/buffer field)). r3 = word [r3+4] (a struct/buffer field). MISSING direction (unreached)…
- **`pd_custom_vdm`** (usb_pd_policy.c, conf:approx) — 4 uncovered [1 taken-only, 3 nottaken-only]
- **`pd_custom_vdm`** (usb_pd_policy.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x0800075e` [taken-only] `cmp r1, #7` then `bne`: taken when r1 != constant 7. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant …
  - `0x08000782` [taken-only] `cmp r1, #6` then `bne`: taken when r1 != constant 6. r1 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r1 == constant …
- **`pd_set_dual_role`** (usb_pd_protocol.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x08007c5e` [taken-only] `cmp r3, #0xf` then `bne`: taken when r3 != constant 0xf. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0xf.
  - `0x08007c8a` [taken-only] `cmp r3, #4` then `bne`: taken when r3 != constant 4. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 4.
- **`pd_check_dr_role`** (usb_pd_policy.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x08000718` [nottaken-only] `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = function argument r1. MISSING direction (nottaken-only) needs r1 != constant 0.
- **`stub_pd_board_check_request`** (usb_pd_policy.c, conf:exact) — 2 uncovered [2 taken-only]
  - `0x08007288` [taken-only] `cmp r3, r2` then `bgt`: taken when r3 > r2 (= word [r2+0] (a struct/buffer field)). r3 = computed (lsrs r3, #0x1d). MISSING direction (taken-only) needs r3 <= …
- **`pd_build_request`** (usb_pd_policy.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08007370` [nottaken-only] `cmp r2, r1` then `bgt`: taken when r2 > r1 (= word [sp+4] (a struct/buffer field)). r2 = word [sp+8] (a struct/buffer field). MISSING direction (nottaken-only)…
- **`set_state`** (usb_pd_protocol.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800751e` [taken-only] `cmp r5, #0xf` then `bne`: taken when r5 != constant 0xf. r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 == const…
- **`hc_remote_pd_dev_info`** (usb_pd_protocol.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08007592` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = byte [r7+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
- **`send_source_cap`** (usb_pd_protocol.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800762e` [nottaken-only] `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
- **`pd_send_vdm`** (usb_pd_protocol.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x080079f0` [taken-only] `cmp r3, #6` then `ble`: taken when r3 <= constant 6. r3 = word [sp+0x18] (a struct/buffer field). MISSING direction (taken-only) needs r3 > constant 6.
- **`pd_comm_enable`** (usb_pd_protocol.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x08007e94` [taken-only] `cmp r3, #6` then `bne`: taken when r3 != constant 6. r3 = byte [r4+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 6.
- **`pd_set_dual_role`** (usb_pd_protocol.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08007f08` [nottaken-only] flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
- **`pd_execute_hard_reset`** (usb_pd_protocol.c, conf:approx) — 1 uncovered [1 taken-only]
- **`pd_request_power_swap`** (usb_pd_protocol.c, conf:high) — 1 uncovered [1 taken-only]
  - `0x08007988` [taken-only] `cmp r3, #0x19` then `bne`: taken when r3 != constant 0x19. r3 = byte [r3+6] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0x19.
- **`pd_request_source_voltage`** (usb_pd_protocol.c, conf:approx) — 1 uncovered [1 taken-only]

## R2 — PD receive / phy bit-decode  (53 branches, 9 functions)
**Why not reached:** These decode the raw BMC/4b5b line: preamble search, bit dequeue, symbol/CRC checks. The campaign stages WELL-FORMED messages at the message layer (dma1 StageResponse), so the malformed-symbol, bad-preamble, truncated/over-long-frame, and bad-5b-code arms never execute.

**What would be required:** Inject raw RX BITSTREAMS one layer below the current message staging: short/long preambles, illegal 5b codes, truncated frames, deliberate CRC/symbol errors — i.e. extend the phy model to feed the decoder arbitrary edge sequences rather than pre-validated frames.

- **`pd_analyze_rx`** (usb_pd_tcpc.c, conf:approx) — 14 uncovered [2 taken-only, 12 nottaken-only]
  - `0x08009edc` [nottaken-only] `cmp r4, #0` then `ble`: taken when r4 <= constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 <= consta…
  - `0x08009f04` [nottaken-only] `cmp r3, r2` then `bne`: taken when r3 != r2 (= a global/constant (pc-relative load)). r3 = a value carried in from a preceding basic block. MISSING direction (…
- **`tcpc_run`** (usb_pd_tcpc.c, conf:approx) — 10 uncovered [2 unreached, 4 taken-only, 4 nottaken-only]
  - `0x0800a1b2` [taken-only] `cmp r6, #0` then `bge`: taken when r6 >= constant 0. r6 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r6 < constant 0…
  - `0x0800a1c6` [taken-only] `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = word [r3+0x7c] (a struct/buffer field). MISSING direction (taken-only) needs r3 > constant 0.
- **`pd_dequeue_bits`** (usb_pd_phy.c, conf:approx) — 8 uncovered [6 taken-only, 2 nottaken-only]
  - `0x08002d90` [taken-only] `lsls r3, r3, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0x10] (a struct/buffer field). MISSING (taken-only) needs the tes…
  - `0x08002d9c` [taken-only] `cmp r0, r5` then `bge`: taken when r0 >= r5 (= register r5). r0 = computed (adds r7, #0). MISSING direction (taken-only) needs r0 < r5 (= register r5).
- **`pd_find_preamble`** (usb_pd_phy.c, conf:approx) — 8 uncovered [6 unreached, 2 taken-only]
  - `0x08002e88` [taken-only] `cmp r7, r6` then `bhs`: taken when r7 >=u r6 (= computed (adds r3, #1)). r7 = computed (subs r2, r7). MISSING direction (taken-only) needs r7 <u r6 (= computed…
  - `0x08002e90` [unreached] `cmp r7, r6` then `bhs`: taken when r7 >=u r6 (= computed (adds r3, #1)). r7 = computed (subs r2, r7). MISSING direction (unreached) needs r7 >=u r6 (= computed…
- **`tx_dma_done`** (usb_pd_phy.c, conf:approx) — 4 uncovered [4 nottaken-only]
  - `0x08002c78` [nottaken-only] `tst r4, r3` then `bne`: tests bits of r4 (= word [r6+8] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - `0x08002c80` [nottaken-only] `tst r4, r3` then `bne`: tests bits of r4 (= word [r5+8] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
- **`pd_rx_handler`** (usb_pd_phy.c, conf:approx) — 4 uncovered [2 unreached, 1 taken-only, 1 nottaken-only]
  - `0x080033b8` [nottaken-only] `cmp r7, #0` then `bne`: taken when r7 != constant 0. r7 = word [r6+0x1c] (a struct/buffer field). MISSING direction (nottaken-only) needs r7 != constant 0.
- **`pd_write_last_edge`** (usb_pd_phy.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800301e` [taken-only] `cmp r2, #0x1f` then `bne`: taken when r2 != constant 0x1f. r2 = function argument r2. MISSING direction (taken-only) needs r2 == constant 0x1f.
- **`tcpc_alert_status_clear`** (usb_pd_tcpc.c, conf:high) — 2 uncovered [2 taken-only]
  - `0x0800a430` [taken-only] `cmp r4, r5` then `beq`: taken when r4 == r5 (= word [r4+0x50] (a struct/buffer field)). r4 = computed (adds r6, #1). MISSING direction (taken-only) needs r4 !=…
- **`command_tcpc`** (usb_pd_tcpc.c, conf:approx) — 1 uncovered [1 taken-only]

## R3 — Peripheral-model gap (SPI/DMA/I2C/ADC/USART/USB-ep)  (258 branches, 51 functions)
**Why not reached:** The branch is gated on a hardware status bit, completion event, or error flag that the Renode peripheral model does not generate: SPI DMA transfer-complete/busy timing, DMA half-transfer, I2C ARLO/BERR/AF in a specific phase, USART overrun, USB ep enumeration sub-states, ADC EOC timing.

**What would be required:** Extend the peripheral model to produce the missing status/event at the right moment (or inject the bus error in the exact phase). This is emulator work, not stimulus crafting.

- **`spi_dma_wait`** (spi_master.c, conf:approx) — 18 uncovered [4 taken-only, 14 nottaken-only]
  - `0x08001a10` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r6, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
  - `0x08001a40` [nottaken-only] `cmp r3, r5` then `bhi`: taken when r3 >u r5 (= register r5). r3 = word [sp+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u r5 (= r…
- **`ep0_rx`** (usb.c, conf:approx) — 15 uncovered [9 unreached, 3 taken-only, 3 nottaken-only]
- **`usb_spi_deferred`** (usb_spi.c, conf:approx) — 15 uncovered [3 taken-only, 12 nottaken-only]
  - `0x0800362a` [nottaken-only] `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r5 == constant 0.
  - `0x08003660` [nottaken-only] `cmp r2, #0x20` then `bge`: taken when r2 >= constant 0x20. r2 = computed (asrs r2, #1). MISSING direction (nottaken-only) needs r2 >= constant 0x20.
- **`i2c2_event_interrupt`** (i2c-stm32f0.c, conf:approx) — 13 uncovered [6 unreached, 6 taken-only, 1 nottaken-only]
  - `0x0800191c` [nottaken-only] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r1+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == constant 0.
- **`usb_spi_interface`** (usb_spi.c, conf:high) — 13 uncovered [7 unreached, 2 taken-only, 4 nottaken-only]
  - `0x080037dc` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = halfword [r3+2] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - `0x080037e6` [nottaken-only] `cmp r3, r2` then `bne`: taken when r3 != r2 (= word [r4+4] (a struct/buffer field)). r3 = halfword [r3+4] (a struct/buffer field). MISSING direction (nottaken-…
- **`i2c_init`** (i2c-stm32f0.c, conf:approx) — 9 uncovered [2 unreached, 3 taken-only, 4 nottaken-only]
  - `0x080017a2` [nottaken-only] `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = word [r7+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 != constant 0.
  - `0x080017c0` [nottaken-only] `cmp r2, r3` then `beq`: taken when r2 == r3 (= computed (lsls r3, #1)). r2 = word [r7+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 ==…
- **`ep0_tx`** (usb.c, conf:approx) — 9 uncovered [2 unreached, 4 taken-only, 3 nottaken-only]
  - `0x08002306` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r6+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - `0x08002312` [taken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r6+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
- **`usb_stream_deferred`** (usb-stream.c, conf:approx) — 9 uncovered [4 taken-only, 5 nottaken-only]
  - `0x0800241c` [nottaken-only] `cmp r2, r5` then `beq`: taken when r2 == r5 (= computed (movs #0x30)). r2 = computed (ands r5). MISSING direction (nottaken-only) needs r2 == r5 (= computed (m…
  - `0x0800243c` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r0+0x1c] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
- **`usart_variant_disable`** (usart-stm32f0.c, conf:high) — 8 uncovered [6 unreached, 2 taken-only]
  - `0x0800213a` [taken-only] `cmp r4, #1` then `bls`: taken when r4 <=u constant 1. r4 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r4 >u constant 1.
  - `0x0800213e` [unreached] `cmp r4, #2` then `bne`: taken when r4 != constant 2. r4 = word [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r4 != constant 2.
- **`gpio_config_pins`** (gpio.c, conf:approx) — 8 uncovered [2 taken-only, 6 nottaken-only]
  - `0x08004970` [taken-only] `cmp r6, r3` then `bne`: taken when r6 != r3 (= word [r4+0] (a struct/buffer field)). r6 = computed (adds r1, #0). MISSING direction (taken-only) needs r6 == r3…
  - `0x0800497c` [nottaken-only] `cmp r5, r2` then `bne`: taken when r5 != r2 (= word [r4+4] (a struct/buffer field)). r5 = computed (ands r2). MISSING direction (nottaken-only) needs r5 != r2 …
- **`dma_wait`** (dma.c, conf:approx) — 6 uncovered [6 nottaken-only]
  - `0x08000d34` [nottaken-only] `cmp r5, r3` then `bhi`: taken when r5 >u r3 (= word [sp+4] (a struct/buffer field)). r5 = register r5. MISSING direction (nottaken-only) needs r5 >u r3 (= word…
  - `0x08000d36` [nottaken-only] `cmp r5, r3` then `bne`: taken when r5 != r3 (= word [sp+4] (a struct/buffer field)). r5 = register r5. MISSING direction (nottaken-only) needs r5 != r3 (= word…
- **`dma_event_interrupt_channel_2_3`** (dma.c, conf:approx) — 6 uncovered [2 unreached, 3 taken-only, 1 nottaken-only]
  - `0x08000e3c` [taken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
  - `0x08000e54` [nottaken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
- **`con_ep_rx`** (usb_console.c, conf:approx) — 6 uncovered [4 unreached, 2 taken-only]
  - `0x08002ae0` [taken-only] `cmp r2, r3` then `bge`: taken when r2 >= r3 (= computed (lsrs r3, #0x16)). r2 = computed (movs #0). MISSING direction (taken-only) needs r2 < r3 (= computed (l…
  - `0x08002aee` [unreached] `cmp r4, r3` then `beq`: taken when r4 == r3 (= word [r1+8] (a struct/buffer field)). r4 = computed (ands r5). MISSING direction (unreached) needs r4 == r3 (= w…
- **`command_adc`** (adc.c, conf:approx) — 6 uncovered [4 taken-only, 2 nottaken-only]
  - `0x08003866` [nottaken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = byte [r7+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
  - `0x08003886` [taken-only] flags from `adds r2, r0, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
- **`host_command_console_read`** (uart_buffering.c, conf:high) — 6 uncovered [4 unreached, 2 taken-only]
  - `0x08007112` [taken-only] `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r2 == constant …
  - `0x0800711a` [unreached] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
- **`gpio_set_flags_by_mask`** (gpio-f0-l.c, conf:approx) — 5 uncovered [5 taken-only]
  - `0x080013da` [taken-only] `lsls r1, r5, #0x1e` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) need…
  - `0x0800142e` [taken-only] `lsls r3, r5, #0xe` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) needs…
- **`usart_tx_interrupt_handler`** (usart_tx_interrupt.c, conf:approx) — 5 uncovered [4 taken-only, 1 nottaken-only]
  - `0x08002044` [taken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r5+4] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0.
  - `0x08002078` [taken-only] flags from `orrs r2, r1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
- **`usb_interrupt`** (usb.c, conf:approx) — 5 uncovered [3 unreached, 2 taken-only]
- **`usb_wait_console`** (usb_console.c, conf:approx) — 5 uncovered [1 unreached, 4 nottaken-only]
  - `0x08002a6a` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 != consta…
  - `0x08002a88` [nottaken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
- **`uart_process_input`** (uart_buffering.c, conf:approx) — 5 uncovered [1 taken-only, 4 nottaken-only]
  - `0x08007140` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
  - `0x08007168` [nottaken-only] `cmp r2, r3` then `bne`: taken when r2 != r3 (= word [r3+0] (a struct/buffer field)). r2 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only…
- **`clock_wait_bus_cycles`** (clock-stm32f0.c, conf:approx) — 4 uncovered [4 nottaken-only]
  - `0x080007e4` [nottaken-only] `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
  - `0x080007fe` [nottaken-only] `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
- **`dma_event_interrupt_channel_1`** (dma.c, conf:high) — 4 uncovered [2 unreached, 2 taken-only]
  - `0x08000e04` [taken-only] `lsls r3, r3, #0x1e` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0] (a struct/buffer field). MISSING (taken-only) needs the tested…
  - `0x08000e12` [unreached] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r3 == constant 0.
- **`dma_event_interrupt_channel_4_7`** (dma.c, conf:approx) — 4 uncovered [2 unreached, 2 taken-only]
  - `0x08000e76` [taken-only] `tst r2, r3` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r3. MISSING (taken-only) needs the masked bits zero.
  - `0x08000e84` [unreached] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r3+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
- **`spi_enable`** (spi_master.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x08001af0` [taken-only] `cmp r3, r1` then `bge`: taken when r3 >= r1 (= byte [r1+1] (a struct/buffer field)). r3 = computed (adds r2, #0). MISSING direction (taken-only) needs r3 < r1 …
  - `0x08001b60` [taken-only] `tst r0, r1` then `beq`: tests bits of r0 (= word [r3+8] (a struct/buffer field)) against mask r1. MISSING (taken-only) needs the masked bits zero.
- **`spi_transaction_async`** (spi_master.c, conf:approx) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x08001bc0` [taken-only] `tst r1, r2` then `beq`: tests bits of r1 (= word [r3+8] (a struct/buffer field)) against mask r2. MISSING (taken-only) needs the masked bits zero.
  - `0x08001c04` [nottaken-only] flags from `subs r6, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
- **`usart_rx_interrupt_handler`** (usart_rx_interrupt-stm32f0.c, conf:high) — 4 uncovered [2 unreached, 2 taken-only]
  - `0x08002282` [taken-only] `lsls r2, r2, #0x1a` sets flags from a shifted value (bit test) then `bpl`. operand = word [r3+0x1c] (a struct/buffer field). MISSING (taken-only) needs the tes…
  - `0x08002296` [unreached] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r0+0x1c] (a struct/buffer field). MISSING direction (unreached) needs r0 != constant 0.
- **`usb_flush`** (usb-stream.c, conf:approx) — 4 uncovered [4 nottaken-only]
  - `0x080023f4` [nottaken-only] `cmp r2, #0x30` then `beq`: taken when r2 == constant 0x30. r2 = computed (ands r1). MISSING direction (nottaken-only) needs r2 == constant 0x30.
  - `0x080023fe` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`usb_getc`** (usb_console.c, conf:high) — 4 uncovered [2 unreached, 2 taken-only]
  - `0x08002b94` [taken-only] `cmp r1, r2` then `beq`: taken when r1 == r2 (= word [r3+4] (a struct/buffer field)). r1 = word [r3+8] (a struct/buffer field). MISSING direction (taken-only) n…
  - `0x08002b9c` [unreached] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r2+0] (a struct/buffer field). MISSING direction (unreached) needs r2 == constant 0.
- **`__tx_char`** (uart_buffering.c, conf:high) — 4 uncovered [4 taken-only]
  - `0x0800702a` [taken-only] `cmp r2, r1` then `bne`: taken when r2 != r1 (= word [r3+4] (a struct/buffer field)). r2 = computed (lsrs r2, #0x17). MISSING direction (taken-only) needs r2 ==…
  - `0x08007038` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
- **`console_read_helper`** (uart_buffering.c, conf:exact) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x080070ba` [taken-only] `cmp r3, r5` then `bne`: taken when r3 != r5 (= word [r4+0xc] (a struct/buffer field)). r3 = word [r1+0] (a struct/buffer field). MISSING direction (taken-only)…
  - `0x080070d8` [nottaken-only] `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = byte [r3+0x14] (a struct/buffer field). MISSING direction (nottaken-only) needs r6 == constant 0.
- **`gpio_interrupt`** (gpio.c, conf:approx) — 3 uncovered [1 unreached, 2 taken-only]
  - `0x080015a6` [taken-only] `cmp r0, r3` then `bge`: taken when r0 >= r3 (= word [r5+0] (a struct/buffer field)). r0 = function argument r0. MISSING direction (taken-only) needs r0 < r3 (=…
- **`usb_stream_reset`** (usb-stream.c, conf:approx) — 3 uncovered [3 nottaken-only]
  - `0x08002530` [nottaken-only] `cmp r3, #0x3f` then `bhi`: taken when r3 >u constant 0x3f. r3 = word [r0+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u constant 0…
  - `0x0800255c` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
- **`memcpy_from_usbram`** (usb.c, conf:approx) — 3 uncovered [3 taken-only]
  - `0x0800295a` [taken-only] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = function argument r2. MISSING direction (taken-only) needs r2 != constant 0.
  - `0x08002972` [taken-only] `cmp r3, r7` then `beq`: taken when r3 == r7 (= computed (lsls r7, #1)). r3 = computed (movs #0). MISSING direction (taken-only) needs r3 != r7 (= computed (lsl…
- **`usb_puts`** (usb_console.c, conf:high) — 3 uncovered [1 taken-only, 2 nottaken-only]
  - `0x08002bf2` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - `0x08002c04` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
- **`uart_process_input`** (uart_buffering.c, conf:high) — 3 uncovered [1 unreached, 2 taken-only]
- **`usb_spi_board_enable`** (board.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x080005fe` [taken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0xe). MISSING direction (taken-only) needs r0 == constant 0.
- **`adc_read_all_channels`** (adc-stm32f0.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x080008e8` [taken-only] `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r7+0] (a struct/buffer field). MISSING direction (taken-only) needs r6 != constant 0.
- **`adc_read_channel`** (adc-stm32f0.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x080009da` [nottaken-only] `tst r0, r3` then `beq`: tests bits of r0 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
- **`dma_event_interrupt_channel_2_3`** (dma.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08000f28` [nottaken-only] `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = computed (adds r4, #1). MISSING direction (nottaken-only) needs r3 <= constant 0.
- **`uart_tx_flush`** (uart.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x08001fd4` [nottaken-only] `tst r2, r3` then `beq`: tests bits of r2 (= word [r1+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
- **`uart_write_char`** (uart.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x08002004` [nottaken-only] `tst r2, r3` then `beq`: tests bits of r2 (= word [r1+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
- **`usart_set_baud_f0_l`** (usart.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x08002212` [nottaken-only] `cmp r0, #0xf` then `ble`: taken when r0 <= constant 0xf. r0 = computed (adds r1, r0). MISSING direction (nottaken-only) needs r0 <= constant 0xf.
- **`usart_flush`** (usart_tx_interrupt.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x080022ce` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`memcpy_to_usbram`** (usb.c, conf:high) — 2 uncovered [2 taken-only]
  - `0x08002700` [taken-only] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = function argument r2. MISSING direction (taken-only) needs r2 != constant 0.
- **`ep_reset`** (usb_console.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x08002b5a` [nottaken-only] `cmp r2, r1` then `bne`: taken when r2 != r1 (= computed (movs #0)). r2 = word [r3+0x4c] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != …
- **`command_spixfer`** (spi_commands.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08006344` [nottaken-only] flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
- **`host_command_console_snapshot`** (uart_buffering.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08006df2` [nottaken-only] `cmp r1, r2` then `blo`: taken when r1 <u r2 (= word [r3+0x30] (a struct/buffer field)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 <…
- **`host_command_console_read`** (uart_buffering.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08007088` [nottaken-only] `cmp r3, r1` then `beq`: taken when r3 == r1 (= word [r2+0] (a struct/buffer field)). r3 = computed (lsrs r3, #0x17). MISSING direction (nottaken-only) needs r3…
- **`uart_puts`** (uart_buffering.c, conf:high) — 2 uncovered [2 taken-only]
  - `0x080071e4` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
- **`uart_flush_output`** (uart_buffering.c, conf:exact) — 2 uncovered [1 taken-only, 1 nottaken-only]
  - `0x0800722e` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
- **`usb_putc`** (usb_console.c, conf:approx) — 1 uncovered [1 nottaken-only]
  - `0x08002bce` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.

## R4 — Boot / init alternate-precondition  (37 branches, 8 functions)
**Why not reached:** *_init / *_pre_init run ONCE during a single boot, so only one hardware configuration is exercised. The dark arms depend on a different boot-time register value, clock/PLL state, option-byte state, reset cause, or RO-vs-RW jump context.

**What would be required:** Boot under the alternate precondition: RO vs RW (sysjump — partly done), plus a model that presents the specific RCC/FLASH/PWR/reset-flag register states the untaken arm checks for.

- **`flash_pre_init`** (flash-f.c, conf:approx) — 13 uncovered [6 unreached, 2 taken-only, 5 nottaken-only]
  - `0x08001270` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 != constant 0.
  - `0x08001280` [taken-only] flags from `ands r3, r6` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
- **`adc_init`** (adc-stm32f0.c, conf:high) — 7 uncovered [2 unreached, 3 taken-only, 2 nottaken-only]
  - `0x08000846` [taken-only] `lsls r1, r1, #0x1f` sets flags from a shifted value (bit test) then `bmi`. operand = word [r2+0] (a struct/buffer field). MISSING (taken-only) needs the tested…
  - `0x08000858` [nottaken-only] `cmp r3, #0` then `blt`: taken when r3 < constant 0. r3 = word [r2+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 < constant 0.
- **`clock_init`** (clock-stm32f0.c, conf:approx) — 5 uncovered [1 unreached, 4 nottaken-only]
  - `0x08000ae4` [nottaken-only] `tst r2, r1` then `beq`: tests bits of r2 (= word [r3+0] (a struct/buffer field)) against mask r1. MISSING (nottaken-only) needs the masked bits nonzero.
  - `0x08000aee` [nottaken-only] `cmp r2, #0xc` then `bne`: taken when r2 != constant 0xc. r2 = computed (ands r1). MISSING direction (nottaken-only) needs r2 != constant 0xc.
- **`rtc_init`** (clock-stm32f0.c, conf:approx) — 4 uncovered [4 nottaken-only]
  - `0x08000b52` [nottaken-only] `tst r0, r3` then `beq`: tests bits of r0 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - `0x08000b68` [nottaken-only] `tst r1, r3` then `bne`: tests bits of r1 (= word [r2+0] (a struct/buffer field)) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
- **`board_init`** (board.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800046e` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds #4). MISSING direction (taken-only) needs r0 != constant 0.
- **`gpio_pre_init`** (gpio.c, conf:approx) — 2 uncovered [1 taken-only, 1 nottaken-only]
- **`crc32_init`** (crc_hw.h, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08009c50` [nottaken-only] `tst r1, r2` then `bne`: tests bits of r1 (= word [r3+0] (a struct/buffer field)) against mask r2. MISSING (nottaken-only) needs the masked bits nonzero.
- **`tcpm_init`** (stub.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800b73c` [nottaken-only] flags from `subs r1, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way

## R5 — Flash fault / protect precondition  (85 branches, 15 functions)
**Why not reached:** Flash program/erase/protect paths: the dark arms are the WRPRT/PGERR error returns, the option-byte write-protect-asserted gates, and the already-equal fast paths. Normal clean ops only walk the success ladder; the protect gates need specific WRP/OPTB register state.

**What would be required:** Pre-arm the matching fault (GaleFlash InjectProgErr/InjectWriteProtErr/StuckBusy) or option-byte / WRP register state at the exact call site. Some sites already covered by cov_flashfault; the rest need a fault the current knobs can't place at that step, or a specific WRP precondition.

- **`write_optb`** (flash-f.c, conf:approx) — 16 uncovered [2 unreached, 14 nottaken-only]
  - `0x08000f50` [nottaken-only] flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - `0x08000f8e` [nottaken-only] flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
- **`flash_set_protect`** (flash.c, conf:approx) — 13 uncovered [2 unreached, 3 taken-only, 8 nottaken-only]
  - `0x080047f8` [nottaken-only] `tst r0, r3` then `beq`: tests bits of r0 (= function argument r0) against mask r3. MISSING (nottaken-only) needs the masked bits nonzero.
  - `0x08004828` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #2). MISSING direction (taken-only) needs r0 != constant 0.
- **`flash_get_protect`** (flash.c, conf:approx) — 12 uncovered [4 unreached, 4 taken-only, 4 nottaken-only]
  - `0x080044ac` [taken-only] `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = function argument r0. MISSING direction (taken-only) needs r0 == constant 2.
  - `0x080044d6` [taken-only] `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r0 == constant …
- **`flash_physical_erase`** (flash-f.c, conf:approx) — 10 uncovered [4 taken-only, 6 nottaken-only]
  - `0x080010f4` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r0, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
  - `0x0800111e` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`flash_physical_write`** (flash-f.c, conf:approx) — 7 uncovered [1 unreached, 4 taken-only, 2 nottaken-only]
  - `0x080010b8` [taken-only] `tst r7, r6` then `beq`: tests bits of r7 (= word [r6+0] (a struct/buffer field)) against mask r6. MISSING (taken-only) needs the masked bits zero.
- **`flash_command_region_info`** (flash.c, conf:high) — 6 uncovered [2 unreached, 2 taken-only, 2 nottaken-only]
  - `0x080042fa` [nottaken-only] `cmp r2, #1` then `beq`: taken when r2 == constant 1. r2 = computed (orrs r1). MISSING direction (nottaken-only) needs r2 == constant 1.
  - `0x080042fe` [taken-only] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = computed (orrs r1). MISSING direction (taken-only) needs r2 != constant 0.
- **`flash_set_protect`** (flash.c, conf:approx) — 4 uncovered [3 taken-only, 1 nottaken-only]
  - `0x08004538` [taken-only] `cmp r0, #2` then `bne`: taken when r0 != constant 2. r0 = computed (movs #8). MISSING direction (taken-only) needs r0 == constant 2.
  - `0x08004572` [taken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = computed (mov sp). MISSING direction (taken-only) needs r3 != constant 0.
- **`command_flash_info`** (flash.c, conf:approx) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x080045f6` [nottaken-only] `lsls r3, r4, #0x1f` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r4, #0x1c). MISSING (nottaken-only) needs the tested bit cl…
  - `0x08004626` [taken-only] `lsls r3, r4, #0x1b` sets flags from a shifted value (bit test) then `bpl`. operand = computed (lsls r4, #0x1d). MISSING (taken-only) needs the tested bit set.
- **`flash_command_get_info`** (flash.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x080042b2` [taken-only] `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = computed (subs #8). MISSING direction (taken-only) needs r2 == constant 0.
- **`flash_range_ok`** (flash.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x08004346` [nottaken-only] `cmp r1, r0` then `blt`: taken when r1 < r0 (= computed (movs #0)). r1 = function argument r1. MISSING direction (nottaken-only) needs r1 < r0 (= computed (movs…
- **`flash_is_erased`** (flash.c, conf:high) — 2 uncovered [2 taken-only]
  - `0x080043a2` [taken-only] flags from `adds r1, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
- **`flash_command_read`** (flash.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800440a` [nottaken-only] `cmp r1, r3` then `bhi`: taken when r1 >u r3 (= halfword [r0+0x14] (a struct/buffer field)). r1 = computed (orrs r3). MISSING direction (nottaken-only) needs r1…
- **`flash_command_write`** (flash.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x080046fc` [taken-only] `lsls r3, r0, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r2). MISSING (taken-only) needs the tested bit set.
- **`flash_command_erase`** (flash.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800477c` [taken-only] `lsls r3, r0, #0x1d` sets flags from a shifted value (bit test) then `bpl`. operand = computed (orrs r2). MISSING (taken-only) needs the tested bit set.
- **`flash_write`** (flash.c, conf:approx) — 1 uncovered [1 taken-only]

## R6 — System / image-copy / jump-tag  (114 branches, 19 functions)
**Why not reached:** Branches gated on jump-data magic+version, image layout (RO/RW/loader), reset/jump reason, or sysjump tag presence. The single cold-boot + a couple of sysjumps exercise one layout.

**What would be required:** Crafted sysjump/reboot scenarios: jump WITH tags present, version/magic mismatch, overwrite-protect checks, alternate active-image copy. Partly drivable via the console `sysjump`/`reboot` with prepared jump data; some need specific flash/RAM layout the model fixes.

- **`system_run_image_copy`** (system.c, conf:approx) — 16 uncovered [6 unreached, 3 taken-only, 7 nottaken-only]
  - `0x08006886` [taken-only] `cmp r3, r1` then `bls`: taken when r3 <=u r1 (= a global/constant (pc-relative load)). r3 = computed (adds r2, r3). MISSING direction (taken-only) needs r3 >u …
  - `0x080068a0` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
- **`system_pre_init`** (system.c, conf:approx) — 13 uncovered [7 taken-only, 6 nottaken-only]
  - `0x08001db4` [nottaken-only] `tst r0, r1` then `beq`: tests bits of r0 (= word [r3+0] (a struct/buffer field)) against mask r1. MISSING (nottaken-only) needs the masked bits nonzero.
  - `0x08001e0c` [nottaken-only] `lsls r2, r3, #0x14` sets flags from a shifted value (bit test) then `bmi`. operand = function argument r2. MISSING (nottaken-only) needs the tested bit set.
- **`system_common_pre_init`** (system.c, conf:high) — 10 uncovered [6 unreached, 1 taken-only, 3 nottaken-only]
  - `0x08006d12` [nottaken-only] `cmp r3, #0` then `ble`: taken when r3 <= constant 0. r3 = word [r0+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 <= constant 0.
  - `0x08006d40` [nottaken-only] `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r0+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r6 == constant 0.
- **`system_get_jump_tag`** (system.c, conf:approx) — 9 uncovered [5 unreached, 2 taken-only, 2 nottaken-only]
  - `0x08006694` [nottaken-only] flags from `subs r4, r3, #0` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - `0x080066be` [taken-only] `cmp r3, r7` then `bne`: taken when r3 != r7 (= register r7). r3 = halfword [r0+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == r7 (= reg…
- **`host_command_vbnvcontext`** (system.c, conf:high) — 8 uncovered [4 unreached, 2 taken-only, 2 nottaken-only]
  - `0x08006542` [taken-only] flags from `orrs r3, r2` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - `0x08006546` [unreached] `cmp r3, #1` then `beq`: taken when r3 == constant 1. r3 = computed (orrs r2). MISSING direction (unreached) needs r3 == constant 1.
- **`system_get_version`** (system.c, conf:approx) — 8 uncovered [1 taken-only, 7 nottaken-only]
  - `0x08006a8c` [taken-only] `cmp r2, r3` then `bls`: taken when r2 <=u r3 (= a global/constant (pc-relative load)). r2 = computed (adds r5, r3). MISSING direction (taken-only) needs r2 >u …
  - `0x08006aa4` [nottaken-only] `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = computed (lsls r4, #1). MISSING direction (nottaken-only) needs r4 == constant 0.
- **`system_unsafe_to_overwrite`** (system.c, conf:approx) — 7 uncovered [2 unreached, 3 taken-only, 2 nottaken-only]
  - `0x0800671c` [taken-only] `cmp r0, r4` then `bls`: taken when r0 <=u r4 (= a global/constant (pc-relative load)). r0 = computed (adds r3, r0). MISSING direction (taken-only) needs r0 >u …
  - `0x08006726` [unreached] `cmp r3, r4` then `bhi`: taken when r3 >u r4 (= a global/constant (pc-relative load)). r3 = computed (adds r3, r0). MISSING direction (unreached) needs r3 >u r4…
- **`command_sysinfo`** (system.c, conf:high) — 7 uncovered [2 unreached, 3 taken-only, 2 nottaken-only]
  - `0x080067c0` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r4+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - `0x080067de` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 != constant 0.
- **`host_command_reboot`** (system.c, conf:approx) — 7 uncovered [1 unreached, 3 taken-only, 3 nottaken-only]
  - `0x08006996` [taken-only] `cmp r2, #1` then `bls`: taken when r2 <=u constant 1. r2 = computed (subs r0, #1). MISSING direction (taken-only) needs r2 >u constant 1.
  - `0x0800699c` [unreached] `cmp r0, #4` then `bne`: taken when r0 != constant 4. r0 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r0 != constant 4…
- **`system_add_jump_tag`** (system.c, conf:approx) — 6 uncovered [6 nottaken-only]
  - `0x08006646` [nottaken-only] `cmp r2, #0` then `beq`: taken when r2 == constant 0. r2 = word [r3+4] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 == constant 0.
  - `0x08006654` [nottaken-only] `cmp r4, #0xff` then `bgt`: taken when r4 > constant 0xff. r4 = computed (adds r2, #0). MISSING direction (nottaken-only) needs r4 > constant 0xff.
- **`command_reboot`** (system.c, conf:high) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x08006454` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [r5+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r0 == constant 0.
  - `0x08006460` [taken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r5+0] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
- **`host_command_get_version`** (system.c, conf:approx) — 4 uncovered [1 unreached, 1 taken-only, 2 nottaken-only]
  - `0x08006bb2` [taken-only] `cmp ip, r7` then `bls`: taken when ip <=u r7 (= a global/constant (pc-relative load)). ip = computed (mov r3). MISSING direction (taken-only) needs ip >u r7 (=…
  - `0x08006bbc` [unreached] `cmp r2, r7` then `bhi`: taken when r2 >u r7 (= a global/constant (pc-relative load)). r2 = computed (adds r2, r7). MISSING direction (unreached) needs r2 >u r7…
- **`command_sysinfo`** (system.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x08006c4a` [taken-only] `cmp r0, #0x31` then `bgt`: taken when r0 > constant 0x31. r0 = computed (movs #0). MISSING direction (taken-only) needs r0 <= constant 0x31.
  - `0x08006c7c` [taken-only] `cmp r3, #0x76` then `bne`: taken when r3 != constant 0x76. r3 = byte [r4+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 == constant 0x76.
- **`system_set_vbnvcontext`** (system.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08001f1e` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r4, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`system_get_image_copy`** (system.c, conf:exact) — 2 uncovered [1 taken-only, 1 nottaken-only]
  - `0x080063aa` [taken-only] `cmp r1, r2` then `bls`: taken when r1 <=u r2 (= a global/constant (pc-relative load)). r1 = computed (adds r3, r2). MISSING direction (taken-only) needs r1 >u …
- **`get_size`** (system.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x080066f8` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a global/constant (pc-relative load). MISSING direction (nottaken-only) needs r0 == constant 0.
- **`system_get_image_copy`** (system.c, conf:exact) — 2 uncovered [1 taken-only, 1 nottaken-only]
  - `0x0800676a` [taken-only] `cmp r0, r1` then `bls`: taken when r0 <=u r1 (= a global/constant (pc-relative load)). r0 = computed (adds r2, r3). MISSING direction (taken-only) needs r0 >u …
- **`command_sysjump`** (system.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08006a2e` [nottaken-only] flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
- **`system_print_reset_flags`** (system.c, conf:approx) — 1 uncovered [1 taken-only]

## R6b — Panic / fault-dump formatting  (20 branches, 8 functions)
**Why not reached:** panic.c register-dump and fault-print arms: dark arms depend on WHICH fault (HardFault vs usage vs the exception frame contents) and on flags only set on a real CPU exception.

**What would be required:** Trigger the specific CPU exception class (or stage the panic-data RAM block) so the dump formatter walks the untaken register/format arms. Some need a real fault the emulator must raise.

- **`command_crash`** (panic_output.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x0800583e` [taken-only] flags from `subs r6, r0, #0` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
  - `0x0800588a` [taken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = word [r4+4] (a struct/buffer field). MISSING direction (taken-only) needs r0 == constant 0.
- **`panic_get_reason`** (panic.c, conf:exact) — 4 uncovered [2 unreached, 2 taken-only]
  - `0x0800b156` [taken-only] `cmp r5, r4` then `bne`: taken when r5 != r4 (= a global/constant (pc-relative load)). r5 = word [r3+0x70] (a struct/buffer field). MISSING direction (taken-onl…
  - `0x0800b15c` [unreached] `cmp r3, #2` then `bne`: taken when r3 != constant 2. r3 = byte [r3+1] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 2.
- **`panic_txchar`** (panic_output.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x080057f6` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (nottaken-only) needs r0 == constant 0.
- **`command_panicinfo`** (panic_output.c, conf:exact) — 2 uncovered [2 nottaken-only]
  - `0x080058c8` [nottaken-only] `lsls r3, r3, #0x1e` sets flags from a shifted value (bit test) then `bmi`. operand = byte [r4+2] (a struct/buffer field). MISSING (nottaken-only) needs the tes…
- **`panic_printf`** (panic_output.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x08005916` [taken-only] `cmp r2, r3` then `bne`: taken when r2 != r3 (= a global/constant (pc-relative load)). r2 = word [r4+0x70] (a struct/buffer field). MISSING direction (taken-onl…
- **`panic_data_print`** (panic.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800afd2` [taken-only] `cmp r7, #0` then `beq`: taken when r7 == constant 0. r7 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r7 != constant …
- **`report_panic`** (panic.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800b086` [nottaken-only] flags from `ands r3, r1` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
- **`bus_fault_handler`** (panic.c, conf:exact) — 2 uncovered [2 nottaken-only]
  - `0x0800b194` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.

## R7 — Console / host-command argument  (124 branches, 31 functions)
**Why not reached:** Command handlers whose dark arms are specific argv shapes, sub-commands, parameter structs, version fields, or an error-return the current invocations didn't hit. Often gated on a precondition (a connected port, a populated buffer).

**What would be required:** Feed the missing console line / host-command params — mostly cheap and drivable. The residue needs a precondition (e.g. a live PD contract, a non-empty console buffer) set up first.

- **`host_command_vboot_hash`** (vboot_hash.c, conf:approx) — 14 uncovered [4 unreached, 6 taken-only, 4 nottaken-only]
  - `0x0800ada2` [nottaken-only] `cmp r3, #0x40` then `bhi`: taken when r3 >u constant 0x40. r3 = byte [r4+2] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 >u constant 0x4…
  - `0x0800ada6` [taken-only] flags from `adds r3, r0, #2` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
- **`console_handle_char`** (console.c, conf:approx) — 8 uncovered [2 taken-only, 6 nottaken-only]
  - `0x08003ca2` [nottaken-only] `cmp r5, #0x7e` then `bne`: taken when r5 != constant 0x7e. r5 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r5 != …
  - `0x08003d08` [taken-only] `cmp r5, #0xc` then `beq`: taken when r5 == constant 0xc. r5 = a value carried in from a preceding basic block. MISSING direction (taken-only) needs r5 != const…
- **`vboot_hash_start`** (vboot_hash.c, conf:approx) — 8 uncovered [2 taken-only, 6 nottaken-only]
  - `0x0800aa50` [nottaken-only] `cmp r0, r6` then `bhi`: taken when r0 >u r6 (= computed (lsls r6, #0xa)). r0 = function argument r0. MISSING direction (nottaken-only) needs r0 >u r6 (= comput…
  - `0x0800aa5a` [nottaken-only] `cmp r7, r6` then `bhi`: taken when r7 >u r6 (= computed (lsls r6, #0xa)). r7 = computed (adds r0, r1). MISSING direction (nottaken-only) needs r7 >u r6 (= comp…
- **`command_hash`** (vboot_hash.c, conf:approx) — 8 uncovered [2 unreached, 4 taken-only, 2 nottaken-only]
  - `0x0800ac14` [taken-only] `cmp r6, #0` then `beq`: taken when r6 == constant 0. r6 = word [r5+0x14] (a struct/buffer field). MISSING direction (taken-only) needs r6 != constant 0.
  - `0x0800acc0` [nottaken-only] `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = byte [r3+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
- **`usb_mux_get`** (usb_mux.c, conf:approx) — 8 uncovered [4 taken-only, 4 nottaken-only]
  - `0x0800b8d6` [taken-only] flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - `0x0800b8ea` [nottaken-only] `lsls r3, r2, #0x1d` sets flags from a shifted value (bit test) then `bmi`. operand = a value carried in from a preceding basic block. MISSING (nottaken-only) n…
- **`host_command_task`** (host_command.c, conf:approx) — 6 uncovered [6 nottaken-only]
  - `0x0800549a` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 != constant 0.
  - `0x080054c2` [nottaken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r3 != constant 0.
- **`fill_response`** (vboot_hash.c, conf:high) — 6 uncovered [6 nottaken-only]
  - `0x0800aad4` [nottaken-only] flags from `adds r2, r1, #2` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
  - `0x0800aad8` [nottaken-only] flags from `adds r3, r1, #3` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
- **`vboot_hash_invalidate`** (vboot_hash.c, conf:approx) — 6 uncovered [6 nottaken-only]
  - `0x0800ae3c` [nottaken-only] flags from `adds r5, r2, r1` then `bmi`; MISSING direction (nottaken-only) needs the result to make `bmi` go the other way
  - `0x0800ae4a` [nottaken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+8] (a struct/buffer field). MISSING direction (nottaken-only) needs r3 == constant 0.
- **`command_typec`** (usb_mux.c, conf:approx) — 6 uncovered [2 unreached, 2 taken-only, 2 nottaken-only]
  - `0x0800b9ae` [nottaken-only] `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = word [sp+0x10] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - `0x0800b9b8` [unreached] `cmp r1, #0` then `beq`: taken when r1 == constant 0. r1 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r1 == constant 0…
- **`cprints`** (console_output.c, conf:approx) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x08004226` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = word [sp+0x1c] (a struct/buffer field). MISSING direction (taken-only) needs r0 != constant 0.
  - `0x08004244` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r4, #0). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`print_gpio_info`** (gpio_commands.c, conf:approx) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x08004a30` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
  - `0x08004a4e` [taken-only] flags from `ands r3, r4` then `bpl`; MISSING direction (taken-only) needs the result to make `bpl` go the other way
- **`set`** (gpio_commands.c, conf:approx) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x08004b26` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r0 == consta…
  - `0x08004b30` [taken-only] `lsls r3, r0, #0x1a` sets flags from a shifted value (bit test) then `bpl`. operand = a value carried in from a preceding basic block. MISSING (taken-only) need…
- **`gpio_command_set`** (gpio_commands.c, conf:high) — 4 uncovered [4 nottaken-only]
  - `0x08004b48` [nottaken-only] flags from `subs r4, r0, #0` then `bne`; MISSING direction (nottaken-only) needs the result to make `bne` go the other way
  - `0x08004b56` [nottaken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = computed (adds r5, #0). MISSING direction (nottaken-only) needs r0 == constant 0.
- **`host_command_process`** (host_command.c, conf:approx) — 4 uncovered [2 taken-only, 2 nottaken-only]
  - `0x080051fe` [nottaken-only] `cmp r1, #0` then `bne`: taken when r1 != constant 0. r1 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-only) needs r1 != constant 0.
  - `0x08005260` [taken-only] `cmp r3, #0` then `bne`: taken when r3 != constant 0. r3 = a global/constant (pc-relative load). MISSING direction (taken-only) needs r3 == constant 0.
- **`command_mem_dump`** (memory_commands.c, conf:approx) — 4 uncovered [4 nottaken-only]
  - `0x080055d0` [nottaken-only] `cmp r7, #1` then `beq`: taken when r7 == constant 1. r7 = computed (subs #1). MISSING direction (nottaken-only) needs r7 == constant 1.
  - `0x08005606` [nottaken-only] `cmp r4, #3` then `bhi`: taken when r4 >u constant 3. r4 = register r4. MISSING direction (nottaken-only) needs r4 >u constant 3.
- **`__gnu_thumb1_case_uhi`** (thumb_case.S, conf:approx) — 4 uncovered [4 nottaken-only]
  - `0x0800b806` [nottaken-only] `cmp r2, #0` then `bne`: taken when r2 != constant 0. r2 = byte [r2+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r2 != constant 0.
  - `0x0800b814` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #3). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`command_rec`** (board.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800034a` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0x10). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`command_dev`** (board.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x080003ae` [nottaken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (movs #0x12). MISSING direction (nottaken-only) needs r0 != constant 0.
- **`console_putc`** (console.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x08003a42` [taken-only] `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = computed (adds r0, #0). MISSING direction (taken-only) needs r4 != constant 0.
- **`command_help`** (console.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x08003adc` [nottaken-only] flags from `subs r4, r2, #0` then `beq`; MISSING direction (nottaken-only) needs the result to make `beq` go the other way
- **`console_task`** (console.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x080040ca` [taken-only] flags from `adds r3, r0, #1` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
- **`host_command_read_test`** (host_command.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x08004f7e` [nottaken-only] `cmp r3, #0x20` then `bhi`: taken when r3 >u constant 0x20. r3 = computed (lsrs r3, #2). MISSING direction (nottaken-only) needs r3 >u constant 0x20.
- **`host_command_read_memmap`** (host_command.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800501c` [nottaken-only] `cmp r2, #0xff` then `bgt`: taken when r2 > constant 0xff. r2 = computed (adds r3, r5). MISSING direction (nottaken-only) needs r2 > constant 0xff.
- **`host_command_test_protocol`** (host_command.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x08005054` [taken-only] `cmp r5, #0x20` then `bls`: taken when r5 <=u constant 0x20. r5 = computed (orrs r3). MISSING direction (taken-only) needs r5 >u constant 0x20.
- **`host_command_get_cmd_versions`** (host_command.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x0800513a` [nottaken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r3 == consta…
- **`vboot_hash_next_chunk`** (vboot_hash.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800abc4` [taken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+0x14] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
- **`usb_mux_set`** (usb_mux.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800b880` [taken-only] flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
- **`board_no_charger`** (board.c, conf:exact) — 1 uncovered [1 nottaken-only]
- **`cputs`** (console_output.c, conf:approx) — 1 uncovered [1 taken-only]
  - `0x08004104` [taken-only] `cmp r5, #0` then `beq`: taken when r5 == constant 0. r5 = computed (adds r0, #0). MISSING direction (taken-only) needs r5 != constant 0.
- **`host_command_test_protocol`** (host_command.c, conf:approx) — 1 uncovered [1 nottaken-only]
- **`main`** (main.c, conf:approx) — 1 uncovered [1 taken-only]

## R8 — printf / arithmetic operand-value  (29 branches, 6 functions)
**Why not reached:** vfnprintf format-specifier arms and uint64divmod operand-magnitude arms. A direction flips only for a specific format spec (width/precision/sign/base/length-modifier) or a specific divisor/dividend size.

**What would be required:** Drive a print/divide with the exact operand: a CPRINTF using that specifier, or a 64-bit divide with that magnitude. Some specifiers have NO caller in this firmware → genuine dead code (needs a proof, e.g. the already-proven 'T' specifier at 0x08005b82).

- **`vfnprintf`** (printf.c, conf:approx) — 16 uncovered [8 taken-only, 8 nottaken-only]
  - `0x080059fa` [nottaken-only] `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == consta…
  - `0x08005b82` [nottaken-only] `cmp r4, #0x54` then `beq`: taken when r4 == constant 0x54. r4 = a value carried in from a preceding basic block. MISSING direction (nottaken-only) needs r4 == …
- **`uint64divmod`** (util.c, conf:approx) — 6 uncovered [2 unreached, 2 taken-only, 2 nottaken-only]
  - `0x0800a5ac` [taken-only] `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = byte [r3+3] (a struct/buffer field). MISSING direction (taken-only) needs r2 == constant 1.
  - `0x0800a5b2` [unreached] `cmp r0, r2` then `bgt`: taken when r0 > r2 (= a global/constant (pc-relative load)). r0 = computed (uxtb r4). MISSING direction (unreached) needs r0 > r2 (= a …
- **`strncasecmp`** (util.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800a6a0` [nottaken-only] `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = byte [r6+0] (a struct/buffer field). MISSING direction (nottaken-only) needs r4 == constant 0.
- **`strcasecmp`** (util.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800a6e2` [taken-only] `cmp r5, #0` then `bne`: taken when r5 != constant 0. r5 = byte [r6+0] (a struct/buffer field). MISSING direction (taken-only) needs r5 == constant 0.
- **`memmove`** (util.c, conf:high) — 2 uncovered [2 nottaken-only]
  - `0x0800a8f4` [nottaken-only] `cmp r0, r1` then `bhi`: taken when r0 >u r1 (= computed (adds r2, #0)). r0 = a value carried in from a preceding basic block. MISSING direction (nottaken-only)…
- **`memcpy`** (util.c, conf:approx) — 1 uncovered [1 nottaken-only]
  - `0x0800a85c` [nottaken-only] `cmp r2, r3` then `blo`: taken when r2 <u r3 (= computed (adds r0, r6)). r2 = computed (adds r0, r2). MISSING direction (nottaken-only) needs r2 <u r3 (= comput…

## R9 — RTOS / hooks / timer / queue scheduling  (76 branches, 21 functions)
**Why not reached:** Branches gated on multi-task scheduling, deferred-hook deadlines, timer wrap, mutex contention, or queue full/empty/wrap that a deterministic single-stimulus run does not reach.

**What would be required:** Manufacture the timing/contention: multiple simultaneously-pending deferred hooks, a wrapped/full queue, a contended mutex, a timer at the 32-bit wrap. Some are schedule-deterministic and may be structurally hard without a second runnable task.

- **`hook_task`** (hooks.c, conf:approx) — 13 uncovered [1 taken-only, 12 nottaken-only]
  - `0x08004d74` [nottaken-only] `cmp r7, r2` then `bhi`: taken when r7 >u r2 (= word [r3+4] (a struct/buffer field)). r7 = word [sp+0xc] (a struct/buffer field). MISSING direction (nottaken-on…
  - `0x08004dee` [nottaken-only] `cmp r5, r3` then `bhi`: taken when r5 >u r3 (= word [sp+0xc] (a struct/buffer field)). r5 = a global/constant (pc-relative load). MISSING direction (nottaken-o…
- **`process_timers`** (timer.c, conf:approx) — 12 uncovered [1 taken-only, 11 nottaken-only]
  - `0x08006f0e` [nottaken-only] `cmp r2, r0` then `bhi`: taken when r2 >u r0 (= word [sp+4] (a struct/buffer field)). r2 = word [r2+0xc] (a struct/buffer field). MISSING direction (nottaken-on…
  - `0x08006f42` [nottaken-only] `cmp ip, r0` then `bne`: taken when ip != r0 (= word [sp+4] (a struct/buffer field)). ip = computed (mov r0). MISSING direction (nottaken-only) needs ip != r0 (…
- **`timer_init`** (timer.c, conf:approx) — 6 uncovered [4 unreached, 2 taken-only]
  - `0x08006fe8` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = a global/constant (pc-relative load). MISSING direction (taken-only) needs r0 != constant 0.
  - `0x08006fee` [unreached] `cmp r3, #1` then `bne`: taken when r3 != constant 1. r3 = word [sp+4] (a struct/buffer field). MISSING direction (unreached) needs r3 != constant 1.
- **`queue_read_safe`** (queue.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x08005db8` [taken-only] `cmp r5, r3` then `bls`: taken when r5 <=u r3 (= computed (subs r3, r2)). r5 = computed (subs r4, #0). MISSING direction (taken-only) needs r5 >u r3 (= computed…
  - `0x08005dd0` [taken-only] `cmp r5, r4` then `bhs`: taken when r5 >=u r4 (= register r4). r5 = computed (adds r3, #0). MISSING direction (taken-only) needs r5 <u r4 (= register r4).
- **`queue_read_safe`** (queue.c, conf:approx) — 4 uncovered [2 unreached, 2 taken-only]
  - `0x08005e34` [taken-only] `cmp r0, #0` then `bne`: taken when r0 != constant 0. r0 = computed (adds r1, #0). MISSING direction (taken-only) needs r0 == constant 0.
  - `0x08005e3c` [unreached] `cmp r4, r3` then `blo`: taken when r4 <u r3 (= computed (ands r7)). r4 = computed (ands r7). MISSING direction (unreached) needs r4 <u r3 (= computed (ands r7)…
- **`queue_add_unit`** (queue.c, conf:approx) — 4 uncovered [2 unreached, 2 taken-only]
  - `0x08005eb4` [taken-only] `cmp r0, #0` then `beq`: taken when r0 == constant 0. r0 = function argument r0. MISSING direction (taken-only) needs r0 != constant 0.
  - `0x08005ec0` [unreached] `cmp r2, #1` then `bne`: taken when r2 != constant 1. r2 = word [r5+0xc] (a struct/buffer field). MISSING direction (unreached) needs r2 != constant 1.
- **`queue_add_memcpy`** (queue.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x08005f02` [taken-only] `cmp r6, r3` then `bls`: taken when r6 <=u r3 (= computed (subs r3, r0)). r6 = computed (subs r5, #0). MISSING direction (taken-only) needs r6 >u r3 (= computed…
  - `0x08005f18` [taken-only] `cmp r6, r5` then `bhs`: taken when r6 >=u r5 (= register r5). r6 = computed (adds r3, #0). MISSING direction (taken-only) needs r6 <u r5 (= register r5).
- **`usleep`** (timer.c, conf:approx) — 4 uncovered [2 unreached, 2 nottaken-only]
  - `0x08006e54` [nottaken-only] `cmp r0, r5` then `bhs`: taken when r0 >=u r5 (= a value carried in from a preceding basic block). r0 = computed (subs r0, r6). MISSING direction (nottaken-only…
  - `0x08006e7a` [unreached] `cmp r4, #0` then `bne`: taken when r4 != constant 0. r4 = a value carried in from a preceding basic block. MISSING direction (unreached) needs r4 != constant 0…
- **`mutex_unlock`** (task.c, conf:approx) — 4 uncovered [4 taken-only]
  - `0x0800b838` [taken-only] flags from `subs r3, r0, #0` then `beq`; MISSING direction (taken-only) needs the result to make `beq` go the other way
  - `0x0800b84a` [taken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r4+8] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
- **`hook_call_deferred`** (hooks.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x08004cd8` [taken-only] flags from `adds r3, r1, #1` then `bne`; MISSING direction (taken-only) needs the result to make `bne` go the other way
- **`queue_advance_head`** (queue.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x08005e64` [taken-only] `cmp r4, r6` then `bls`: taken when r4 <=u r6 (= computed (adds r1, #0)). r4 = computed (subs r0, #0). MISSING direction (taken-only) needs r4 >u r6 (= computed…
- **`queue_add_unit`** (queue.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x08005f4a` [taken-only] `cmp r5, r6` then `bls`: taken when r5 <=u r6 (= computed (adds r2, #0)). r5 = computed (subs r0, #0). MISSING direction (taken-only) needs r5 >u r6 (= computed…
- **`queue_add_direct`** (queue_policies.c, conf:high) — 2 uncovered [2 taken-only]
  - `0x08005f7e` [taken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
- **`queue_add_direct`** (queue_policies.c, conf:exact) — 2 uncovered [2 taken-only]
  - `0x08005f92` [taken-only] `cmp r3, #0` then `beq`: taken when r3 == constant 0. r3 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r3 != constant 0.
- **`get_time`** (timer.c, conf:high) — 2 uncovered [2 taken-only]
  - `0x08006e90` [taken-only] `cmp r7, r5` then `beq`: taken when r7 == r5 (= word [r6+0x30] (a struct/buffer field)). r7 = word [r6+0x30] (a struct/buffer field). MISSING direction (taken-o…
- **`task_wait_event_mask`** (task.c, conf:approx) — 2 uncovered [2 nottaken-only]
  - `0x0800b46c` [nottaken-only] `cmp r6, #0` then `ble`: taken when r6 <= constant 0. r6 = register r6. MISSING direction (nottaken-only) needs r6 <= constant 0.
- **`mutex_unlock`** (task.c, conf:high) — 2 uncovered [2 taken-only]
  - `0x0800b530` [taken-only] `cmp r4, #0` then `beq`: taken when r4 == constant 0. r4 = word [r3+0] (a struct/buffer field). MISSING direction (taken-only) needs r4 != constant 0.
- **`task_pre_init`** (task.c, conf:approx) — 2 uncovered [2 taken-only]
  - `0x0800b6a0` [taken-only] `cmp r7, #3` then `bls`: taken when r7 <=u constant 3. r7 = byte [r2+1] (a struct/buffer field). MISSING direction (taken-only) needs r7 >u constant 3.
- **`__svc_handler`** (task.c, conf:approx) — 1 uncovered [1 nottaken-only]
- **`svc_handler`** (task.c, conf:high) — 1 uncovered [1 taken-only]
- **`task_set_event`** (task.c, conf:approx) — 1 uncovered [1 nottaken-only]

**Total: 1072 branches across 191 functions.**
