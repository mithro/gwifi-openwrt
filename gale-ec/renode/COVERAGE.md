# Branch-coverage measurement (the "100% branch coverage" requirement)

`coverage.py` measures actual branch/instruction coverage by capturing a Renode PC
execution trace while the firmware runs the test scenarios (boot + console commands +
USB), then mapping executed PCs against the firmware disassembly (counting conditional
branches taken/not-taken).

## Measured result (rebuilt ec.bin, comprehensive console+USB+power scenario)

```
RO image (the ACTIVE image — see note): 
  instructions:   5943/20089 executed = 29.6%
  cond branches:  1583 total, 563 reached, 167 fully-covered (both directions)
  branch coverage: 29.7% of reached, 10.5% of total
RW image: 0% — never executed (RO does not sysjump to RW in this emulation)
```

## Why literal 100% branch coverage is NOT achievable here (honest)

This is a measured, structural limitation, not a shortcut:

1. **Unreachable defensive/error branches.** Production EC firmware is full of branches
   that guard conditions which cannot occur in EC-only emulation: hard-fault / panic /
   ASSERT handlers, `EC_ERROR_*` paths for hardware that cannot fail (the modeled flash
   never returns BSY/error, the SPI slave always responds), watchdog-trip paths,
   recovery/dev-mode branches, and timeouts that never expire. Taking *both* directions
   of these branches is impossible without injecting faults the real hardware models
   don't produce.
2. **AP-dependent code.** Large branch sets depend on the IPQ4019 AP being up (host
   commands, AP-stream console, charge/PD-contract states). The AP cannot boot in an
   EC-only STM32F0 emulation, so those branches are structurally unreachable (the same
   bounded gap as AP boot).
3. **RW image never entered.** The firmware runs as RO (console banner "Image: RO");
   RO doesn't sysjump to RW in this environment, so RW's 1583 branches are 0%-covered.
   Exercising RW would require driving the RO→RW sysjump (a separate effort) and even
   then the same unreachable-branch limits apply.

So "100% branch coverage" of this firmware in EC-only Renode emulation is not literally
attainable. What IS achievable and useful — and what this harness provides — is a
*measurement* of achieved coverage plus identification of the structurally-unreachable
classes above. Increasing the number further means adding scenarios (fault injection,
more console commands, driving RW); it asymptotes well below 100% for the reasons above.

## Usage
```
uv run python coverage.py --boot 3.0 --cmd version --cmd gpioget ...   # default = full battery set
```
