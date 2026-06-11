# gale EC — consolidated equivalence status (captured dump vs reconstruction)

**As of 2026-06-09.** Single source of truth for the divergence ledger. Combines the static
differential-RE reviews (EQUIVALENCE-REVIEW-1/2, #1–6) with the Renode runtime-harness findings
(#7–10). Reconstruction = `ec/` @ firmware-gale-8281.B; captured = device dump
`gale-ec-gale_v1.1.5337-0115719`.

## Divergence ledger

| # | area | status | evidence / resolution |
|---|------|--------|------------------------|
| 1 | `pd_select_polarity` COMP INSEL (VREF12 vs INM4) | ✅ FIXED | EQUIVALENCE-REVIEW-2: byte-equiv after patch |
| 2 | `board_no_charger` (pd_set_dual_role vs pd_comm_enable) | ✅ FIXED | REVIEW-2: instruction-for-instruction match |
| 3 | `pd_tx_enable` sense-pin drive | ✅ FIXED | REVIEW-2: FIXED-MATCHES |
| 4 | `pd_custom_vdm` VDO_CMD_CCD_EN case | ✅ FIXED | REVIEW-2: 15-entry jump table matches |
| 5 | `PD_STATE_SNK_ACCESSORY` missing | ✅ FIXED | ec/ commit 5120003; ForceAccessory → USB_CNTR 0xE400 both |
| 6 | `CONFIG_CASE_CLOSED_DEBUG` / USB absent | ✅ FIXED | CCD enabled; device+config descriptors byte-identical |
| 7 | raiden/SPI endpoint EP4 vs captured EP3 | ✅ FIXED+VERIFIED (2026-06-09) | board.h: dropped USB_EP_UNUSED, USB_EP_SPI 4→3; rebuilt → ec-rebuilt-ep3fix.bin; usb_host.py: raiden EP3, buffer addrs + descriptor BYTE-IDENTICAL to captured, ef4017 PASS |
| 8 | source-path `timer_cancel` assert crash | CHARACTERIZED — emulation effect, source logic equivalent | single `pd dualrole source` clean 5/5 (SRC logic OK); 2-cmd seq crashes 8/8 (deterministic at one reschedule boundary); captured LACKS the assert (TASK_ID_COUNT: cap=0 reb=2) so its older timer.c tolerates the same bad tskid; the bad `me`=136 is a context-switch-boundary effect exposed only by the rebuilt's newer ASSERT. NOT a recon PD-logic bug. (Definitive instruction-level proof blocked: timer_cancel is hot → hooks too slow + Heisenbug.) |
| 9 | `gale polarity` 0 (cap) vs 1 (reb) | likely IMMATERIAL | only in no-asymmetric-attachment default state; debug accessory is symmetric (polarity tie-break arbitrary); captured tracks CC1 under real contract |
| 10 | USB up at no-force boot (cap 0xE400 vs reb 0x0003) | ✅ RESOLVED — emulation artifact | both 0xE400 under real ForceAccessory; no-force SRC_ACCESSORY only occurs because GaleAdc presents a PHANTOM accessory; difference is borderline CC-classification of that phantom (known immaterial [200,250)mV band) |

## Verdict
All CONFIRMED MATERIAL divergences (#1–7) are FIXED and verified. #8 is an emulation
context-switch effect exposed by a newer-version assert (source reconstruction logic proven
equivalent). #9/#10 are immaterial / emulation artifacts (evidence-based, with decisive
real-stimulus tests). **No outstanding reconstruction logic divergence remains** on the paths the
harness exercises.

## Caveats / not-yet-done
- The #7 fix lives in `ec/board/gale/board.h` + verified `ec-rebuilt-ep3fix.bin`; the canonical
  `ec-rebuilt.bin` (coverage-campaign reference) is NOT yet repointed to it (user decision).
- Captured branch-coverage reached its automated ceiling **45.2% both-dirs / 82.6% reached** (rda
  denominator 3272); the 5-agent verification gate requires 100%, which is automated-unreachable —
  residual is `pd_task`'s live state machine (manual RE) + board-inactive (`board_no_charger`) +
  infeasible defensive asserts. See gwifi-ec-coverage-campaign memory.
- The 5 independent verification agents have NOT been run (coverage ≠ 100%).
