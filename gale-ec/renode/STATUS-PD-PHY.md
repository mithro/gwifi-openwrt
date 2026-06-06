# USB-PD live-negotiation modeling — status

Goal: drive a live USB-PD contract against gale in Renode so the PD physical-layer /
protocol branches (`pd_task`, `pd_analyze_rx`, `pd_dequeue_bits`, `pd_find_preamble`,
`pd_build_request`, `pd_svdm`, `handle_request`, …) — the single largest uncovered
branch category (`pd_task` alone = 179 uncovered branches, see `COVERAGE.md`) — execute,
without real CC analog hardware.

## DONE + verified

1. **Sink attach (`GaleAdc.PartnerSource`).** A new, additive mode on the ADC model
   presents a *Source* attached to gale's sink: CC1 sits in the SNK_1_5 Rp band
   (~800 mV) while gale sinks (`cc_pull==RD`); VBUS need not be modeled because gale's
   `pd_snk_is_vbus_provided()` is hardwired to 1. With it, gale drives
   `SNK_DISCONNECTED → SNK_DISCONNECTED_DEBOUNCE → SNK_DISCOVERY` and sits with RX
   enabled, exactly where it awaits the partner's Source_Capabilities. Verified:
   `pd 0 state` → `Role: SNK-UFP State: SNK_DISCOVERY` on CC1. This is wired into the
   `pd_sink` scenario in `coverage_full.py` and covers the attach/debounce/discovery
   branches.

2. **PD message encoder (`pd_encode.py`) — correctness proven.** A faithful port of the
   firmware's OWN TX encoder (`prepare_message` + `pd_write_preamble`/`pd_write_sym`/
   `pd_write_last_edge` + `BMC()` + the 4b5b table + the PD CRC32) produces the half-UI
   line-level waveform, then converts each level transition to the TIM1 input-capture
   edge-timestamp byte form the EC's RX hardware records into `pd_phy[0].raw_samples`
   (Δ≤6 ticks='1', Δ>6='0'; PERIOD=4 ticks/half-UI). A built-in self-check re-implements
   the firmware decoder (`pd_find_preamble` magic `0x36db6db6` → SOP `0x8E318` → 4b5b
   header → PDOs → CRC32 → EOP) and asserts the generated samples round-trip back to the
   original header+objects+CRC — so we KNOW the firmware would decode them. Canonical
   Source_Capabilities / Accept / PS_RDY messages all round-trip OK.

## DONE — live PD message decode over a modeled CC-partner (the integrated peripheral)

Built and **verified**: a modeled CC partner now drives the firmware's genuine PD RX path
end-to-end. Two new model pieces:

* **`GaleExti`** (replaces stock `STM32F4_EXTI`) — models the EXTI registers faithfully and
  adds `FireComp(line)`, which sets `EXTI_PR[line]` and pulses the ADC_COMP IRQ (wired
  `IRQ -> nvic@12` in `gale.repl`), i.e. it plays the comparator seeing a CC edge.
* **`GaleDma.TimRxSampleCount`** — when the firmware arms the TIM1-CCR1-source RX channel
  (`pd_rx_start`), the model reports this many bytes as captured (sets `CNDTR = n - count`
  so `dma_bytes_done()` returns them) WITHOUT overwriting the buffer — the CC-partner has
  pre-staged the encoded samples there, and those samples ARE the captured CC waveform.

Flow (verified): stage `pd_encode` samples into `pd_phy.raw_samples` + set `TimRxSampleCount`
→ `FireComp 21` ×3 within 20 µs → real `pd_rx_handler` → `pd_rx_start` (TIM1 CR1←1) +
`pd_rx_event` (wakes `pd_task`) → `tcpc_run` → **`pd_analyze_rx` decodes the message**. Proof:
`pd 0 state` = SNK_DISCOVERY, inject Source_Capabilities, then `pd[0].rx_head[0]` reads
**0x1161** — exactly the encoded Source_Caps header — and gale reacts by **transmitting a
Request** (`raw_samples` overwritten with gale's own TX preamble `0xB4…`). So the full RX
chain — `pd_find_preamble`/`pd_dequeue_bits`/`decode_short`/`decode_word`/`pd_analyze_rx` +
`handle_request`/`handle_data_request(SOURCE_CAP)`/`pd_build_request`/TX — executes on the
real firmware. `pd_inject.py` runs it; the `pd_live` scenario in `coverage_full.py` injects a
battery of 14 message types (Source_Caps, the control messages, a structured VDM Discover
Identity) to cover the decode + protocol-dispatch branches broadly.

## Remaining (full explicit contract to SNK_READY — incremental)

Decoding + dispatch work (above). Reaching an explicit contract (SNK_READY) additionally
needs the partner to complete the GoodCRC handshake: after gale decodes Source_Caps it
transmits a Request and waits `PD_T_RECEIVE` (~1 ms) for a GoodCRC, retrying then
soft-resetting if none arrives. The partner must therefore (a) detect gale's TX (SPI1/TIM16
TX-DMA activity), (b) inject a GoodCRC with the matching msg_id inside that ~1 ms window,
then (c) inject Accept and PS_RDY (each itself GoodCRC-acknowledged by the EC). This is
TX-reactive timing on top of the now-working RX injection — a refinement of `pd_inject.py`,
not new peripheral modeling. The branch-coverage value of the contract-accepted paths
(`handle_ctrl_request` ACCEPT/PS_RDY, SNK_TRANSITION, SNK_READY) is incremental over the
decode+dispatch coverage the message battery already provides.

## Honest bound

Even a complete CC-partner converts the PD-PHY/PD-protocol category but does NOT yield
literal 100% branch coverage: the AP host-command branches (`host_command_process`,
`hc_*`) are **unreachable dead code in gale** — `board/gale` compiles no host-command
transport, so `host_packet_receive`/`host_command_received`/`i2c_event_handler` are GC'd
and nothing can invoke them (an injector is infeasible, not a TODO — see `COVERAGE.md`);
and reset-only fault/panic branches cannot take both directions within one non-resetting
image. See `COVERAGE.md` for the full per-category accounting.
