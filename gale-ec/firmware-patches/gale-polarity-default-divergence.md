# Candidate divergence #9: `gale polarity` default differs (captured 0 vs rebuilt 1)

**Status:** CANDIDATE, found 2026-06-09 by systematic console-output diffing (captured vs rebuilt).
Likely an immaterial boot-default difference, but **not yet conclusively classified** — flagged per
the equivalence campaign's "surface every behavioral difference" rule.

## What was found
Diffing console output of identical commands on both firmwares, all lines matched (modulo expected
version-banner/timestamp/hash differences) EXCEPT:

```
gale polarity:   captured -> "polarity - 0"     rebuilt -> "polarity - 1"
```

Reproducible: stable across repeated reads, and unchanged whether a partner is attached
(`sysbus.adc ForceSourceCc true`) or not. So with no established contract it reflects the **initial
/ default `pd[0].polarity`**, which the two builds set differently (captured CC1=0, rebuilt CC2=1).

## Partial classification
- Under a **full reactive-partner contract** (CC1 active via ForceSourceCc), the **captured** reports
  `polarity - 0` / `CC1` / state `SNK_HARD_RESET_RECOVER` — i.e. it correctly tracks the active CC1.
- The **rebuilt's** post-contract polarity could not be cleanly read from the console in the test
  window (contract hard-reset-cycles; console readout timing) — so whether it **converges to 0/CC1
  under a real contract** (=> immaterial boot default) or **stays 1** (=> real CC-detection
  divergence) is UNCONFIRMED.

## Significance / next step
Most likely an immaterial difference in the **initial** `pd[0].polarity` value (overwritten on the
first real contract) — analogous to the struct-init differences EQUIVALENCE-REVIEW classified
immaterial. To classify definitively: read `pd[0].polarity` from RAM (pd[0]=0x20001150, find the
polarity field offset) after a contract on BOTH images; equal under contract => immaterial.
Distinct from the FIXED `pd_select_polarity` COMP-INSEL divergence (#1) — that was the comparator
reference constant; this is the runtime polarity *value*.

## Reproduce
```
cd gale-ec/renode
uv run --python .venv python capture_console.py --bin <fw> --boot 2.0 --cmd "gale polarity"
# captured -> polarity - 0 ; rebuilt -> polarity - 1
```

## CLASSIFICATION (2026-06-09): likely IMMATERIAL
- Under a real symmetric debug accessory (ForceAccessory: both CC Rd/Rd) the polarity tie-break is
  inherently arbitrary — either CC is valid — so a 0-vs-1 difference there is not a defect.
- Under the full reactive SNK contract the captured tracks CC1 (polarity 0) correctly.
- pd[0] struct diff (under ForceSourceCc) showed the rebuilt's pd[0] mostly ZERO vs captured
  populated, and task_state byte0=0 on both — i.e. the reported polarity is computed/stored outside
  the first 32 bytes; no clean polarity byte isolated. The 0-vs-1 difference appears only in the
  no-asymmetric-attachment default state.
- CONCLUSION: most consistent with an arbitrary boot/default polarity value (overwritten on a real
  asymmetric attachment), not a CC-detection bug. Definitive confirmation would need pd[0].polarity
  read from RAM (offset TBD) under a real asymmetric CC1 source contract on the rebuilt; deferred as
  low-value (the material divergences #1-7 are resolved).
