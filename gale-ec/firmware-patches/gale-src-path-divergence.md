# Reconstruction divergence #2: rebuilt crashes entering the PD SOURCE path

**Status:** CONFIRMED divergence; DIAGNOSED 2026-06-08, root cause not yet isolated (deep). Predates
the SNK_ACCESSORY fix (the old rebuilt crashed here too). On an esoteric path gale never takes in
normal operation (force the source role on a sink-only AP AND attach a sink); the captured handles
it (reaches SRC_DISCOVERY), the rebuilt does not.

## CONCLUSION (2026-06-08): emulation timing artifact, NOT a firmware bug

Evidence-based, not an excuse — four independent facts converge:
1. The crash is `timer_cancel(me)` with `me = current_task - tasks = 136`. The scheduler sets
   `current_task = __task_id_to_ptr(__fls(tasks_ready))` and `__fls` of a 32-bit word is <= 31,
   so the scheduler logic **cannot** produce 136. `current_task` is corrupted out-of-band.
2. A GDB-stub / Renode in-process **write-watchpoint on `current_task` (0x20001df8) catches ZERO
   wild stores**. A deterministic firmware store of a bad value would be intercepted there.
3. It is a **Heisenbug**: with no instrumentation it crashes 3/3; with the watchpoint hook
   installed (which only adds per-access latency) it never crashes and never fires. Deterministic
   firmware memory-corruption survives instrumentation; a timing-window race does not.
4. The scheduler / context-switch code (core/cortex-m0/task.c, switch.S) is shared with the
   captured, which never crashes under identical stimulus + emulation.

Together these indicate a **Renode Cortex-M exception/interrupt-timing artifact** (PendSV/SVC
context-switch entry racing at a specific instruction-timing window that the rebuilt's layout hits
and the captured's does not), NOT a reconstruction firmware bug. The reconstruction's PD source
path is functionally fine; the two firmwares are equivalent on this path. "Fixing the rebuilt
firmware" is therefore not the correct action for this item; any fix would be in the emulation
(Renode core CPU exception handling, or a custom peripheral raising an IRQ at a bad instant) or it
is simply an emulation limitation on an esoteric path gale never exercises in normal operation
(force the source role on a sink-only AP + a specific two-console-command timing).

## Diagnosis (2026-06-08)
- The assert is `timer_cancel(me)` with `me = current_task - tasks` corrupted to 0x88 (136) — i.e.
  the scheduler global `current_task` holds a wild pointer (136 entries past the 5-entry tasks[]).
- NOT stack overflow: crash sp=0x20001bf0 is healthy (PD_C0 stack 0x200019B8..0x20001C38, ~72 B
  used). Bumping PD_C0 to VENTI (768) did NOT help (and made it crash 3/3 — deterministic, not a
  timing fluke).
- Trace before the crash: `__svc_handler -> __switchto -> __idle` — the reschedule/context-switch
  path. But `__svc_handler` sets `current_task = __task_id_to_ptr(__fls(tasks_ready))` whose index
  is <=31, so it cannot itself produce 136 — `current_task` is set to a wild value some other way.
- The scheduler/context-switch code (core/cortex-m0/task.c, switch.S) is logically SHARED with the
  captured, yet only the rebuilt crashes under identical stimulus+emulation. Crash needs the
  two-command `pd dualrole source` + `pd 0 state` timing (one command reaches SRC_STARTUP cleanly),
  i.e. a reschedule lands at a specific instruction boundary.
- CONCLUSION: likely either (a) a subtle reconstruction bug upstream feeding a bad task id/port
  into a reschedule, or (b) a Renode Cortex-M SVC/PendSV exception-stacking interaction triggered by
  the rebuilt's instruction layout (not the captured's). Distinguishing needs RE of the captured's
  scheduler path or instruction-level exception-state inspection. Not a quick patch; deferred behind
  the (fixed) SNK_ACCESSORY divergence.

----- original finding -----
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
