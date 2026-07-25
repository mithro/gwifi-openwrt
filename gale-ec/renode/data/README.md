# renode/data — vendored binary references

These committed binaries let the Renode equivalence + coverage harness run **self-contained**
inside this repository: the analysis tooling never reaches outside `gwifi-openwrt` for an input.

| File | What it is | Used by |
|------|------------|---------|
| `gale-optionbytes.bin` | The dev unit's EC option bytes (copy of the published dump). | Renode harness boot |
| `rebuilt-RO.elf` | Snapshot of the **reconstructed** gale EC firmware, RO image. | `map_funcs.py`, `compare_cmds.py`, `build_named_report.py`, `rda_validate.py`, … |
| `rebuilt-RW.elf` | Same, RW image. | `rda_validate.py`, `coverage*.py` |

## About the rebuilt ELFs

They are a **build output**, not source. Source of truth = `gale-ec/board/gale/` (in this repo) overlaid
on `platform/ec @ firmware-gale-8281.B`, built with `arm-none-eabi` 2016q3 (that build tree + toolchain
live outside this repo and are not needed to *use* the harness — only to *regenerate* the ELFs).

The tooling only needs these committed snapshots for: rebuilt symbol names / DWARF source lines
(fingerprint-mapped onto the captured dump) and the rebuilt `__cmds` console-command table
(equivalence comparison). The **captured** firmware coverage numbers do not depend on them at all.

### Regenerating after a board change

```sh
# build (outside this repo) then refresh the vendored snapshots:
cp <ec-tree>/build/gale/RO/ec.RO.elf data/rebuilt-RO.elf
cp <ec-tree>/build/gale/RW/ec.RW.elf data/rebuilt-RW.elf
# then re-run the analysis and commit the ELFs + regenerated reports together.
```

Every tool also accepts an override env var (`GALE_REBUILT_RO_ELF`, `GALE_REBUILT_RW_ELF`) if you want
to point at a fresh out-of-tree build without touching these files. Source-line context additionally
needs the `platform/ec` tree via `GALE_EC_SRCROOT` — optional; reports generate fine without it.
