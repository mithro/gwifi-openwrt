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

## Precisely-characterised remaining blocker (the integrated CC-partner peripheral)

`pd_inject.py` writes the encoded samples to `pd_phy[0].raw_samples` (0x20000638), arms
the RX path the firmware polls — RX DMA ch2 `CCR.EN=1` + `CNDTR=0` (so
`dma_bytes_done()` reports the full buffer) and TIM1 `CR1.EN=1` (so `pd_rx_started()` is
true) — all of which were verified to take (TIM1 CR1 reads back 1; `rx_enabled`=1). But
the message is NOT processed, because:

* **`pd_task` sleeps in SNK_DISCOVERY waiting for an EVENT, not polling.** `tcpc_run()`
  (which checks `pd_rx_started()` and calls `pd_analyze_rx`) only runs when `pd_task`
  wakes. With no Source_Caps, gale does not even run the SinkWaitCap timeout cycle here —
  it sits in SNK_DISCOVERY indefinitely (TIM1 CR1 stays 1 across >0.5 s, `pd_task` never
  runs `tcpc_run`). Waking it requires `PD_EVENT_RX`, which only `pd_rx_event()` sets, and
  `pd_rx_event()` is only called from `pd_rx_handler()` (the COMP/EXTI IRQ, NVIC 12).
* **The COMP-IRQ wake path also arms the capture DMA.** `pd_rx_handler` (after 3 CC edges
  within 20 µs) calls `pd_rx_start()` → `dma_start_rx()` on ch2 (periph = TIM1 CCR1 @
  0x40012C34, count = 858) → `GaleDma` would instant-transfer TIM1 CCR into `raw_samples`,
  overwriting the staged message.

So a complete live contract needs an **integrated CC-partner peripheral** that:
1. raises the COMP IRQ (NVIC 12) — three edges within 20 µs — to wake `pd_task` via the
   real `pd_rx_handler` → `pd_rx_event` path; and
2. makes the ch2 RX-DMA *deliver the staged encoded samples* (and set `CNDTR` so
   `dma_bytes_done()` reports them) instead of reading the constant TIM1 CCR — i.e.
   `GaleDma` special-cases the TIM1-CCR-source channel to copy from a `StagedRxSamples`
   buffer; and
3. for a FULL contract, reacts to gale's TX (Request) by injecting GoodCRC + Accept +
   PS_RDY in sequence (detecting gale's SPI1/TIM16 TX-DMA activity), with matching msg_ids.

All three are well-specified by the now-mapped RX path (see the code-explorer findings in
the session log and `chip/stm32/usb_pd_phy.c` / `common/usb_pd_tcpc.c`). This is a focused
peripheral-modeling effort (comparable in size to `GaleUsb`), not an open research问题.

## Honest bound

Even a complete CC-partner converts the PD-PHY/PD-protocol category but does NOT yield
literal 100% branch coverage: the AP host-command branches (`host_command_process`,
`hc_*`) need the IPQ4019 and are addressed separately by the host-command injector
(task #17); and reset-only fault/panic branches cannot take both directions within one
non-resetting image. See `COVERAGE.md` for the full per-category accounting.
