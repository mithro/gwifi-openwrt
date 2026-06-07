# Reconstruction divergence #2: rebuilt crashes entering the PD SOURCE path

**Status:** CONFIRMED behavioral divergence, found 2026-06-07 (needs root-cause).
**Related:** likely the same gale-vintage PD customization gap as the missing
[`PD_STATE_SNK_ACCESSORY`](gale-snk-accessory-divergence.md).

## What was found

Forcing the source role (`pd dualrole source`) with a normal **sink partner** attached
(`sysbus.adc PartnerSink true` — CC1 in the source Rd band [400,1600)mV, CC2 open) — IDENTICAL
stimulus and IDENTICAL emulation for both firmwares:

| firmware | result |
|----------|--------|
| **captured** (device dump) | sources cleanly: `SRC_DISCONNECTED_DEBOUNCE -> ... -> SRC_DISCOVERY` (`Role: SRC-DFP`), sends Source_Caps, **no crash** |
| **rebuilt** (ec/ @ firmware-gale-8281.B) | reaches `SRC_DISCONNECTED`, then **`ASSERTION FAILURE 'tskid < TASK_ID_COUNT' in timer_cancel() at common/timer.c:136`** -> HANDLER EXCEPTION (pc=0x0001d685 invalid, r4=0xdead6663 poison) -> reboot |

Because the emulation is byte-identical for both runs, this is a firmware behavioral
difference, not an emulation gap: the captured device firmware supports the PD source
contract path; the reconstruction crashes on it.

## Significance

This is the second hard divergence the harness surfaced once the SOURCE-side PD states were
actually driven (they had been wrongly written off as "board-dead" — gale is force-sink by
policy, but its state machine reaches SRC states fine with `pd dualrole source` + a sink
partner). The captured device clearly exercises the source path (it is the documented gale
behaviour); the reconstruction diverges by asserting/crashing.

`timer_cancel(tskid)` asserts because `tskid >= TASK_ID_COUNT` — an out-of-range task id, with
poison (0xdead6663) in r4 and an invalid PC, i.e. corruption/bad scheduling on the source path.
Root cause not yet isolated; candidates: (a) a task-table / PD_PORT_TO_TASK_ID difference between
the gale-vintage source and firmware-gale-8281.B; (b) a downstream symptom of the missing
SNK_ACCESSORY state shifting the PD state enum; (c) a source-path timer/deferred call the
reconstruction handles differently.

## Reproduce

```
cd gale-ec/renode
uv run --python .venv python capture_console.py --bin <firmware> \
    --mon 'sysbus.adc PartnerSink true' --boot 1.0 --settle 1.0 \
    --cmd "pd dualrole source" --cmd "pd 0 state"
# captured -> SRC_DISCOVERY ; rebuilt -> ASSERTION FAILURE in timer_cancel
```

## Next

Isolate the failing call site (which timer_cancel / task id), determine whether it is
independent of or caused by the SNK_ACCESSORY gap, then restore the gale-vintage source-path
behaviour to the reconstruction. Until fixed, the rebuilt is NOT functionally equivalent on the
PD source / source-contract path, and SRC_STARTUP..SRC_READY coverage cannot be driven on the
rebuilt.
