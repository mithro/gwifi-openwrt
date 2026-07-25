# Building the reconstructed gale EC firmware

The build runs **in-repo** and is driven entirely by **tracked** inputs.

```sh
cd gale-ec
./build-firmware.sh
```

That produces `build/gale/ec.bin` inside the gitignored workspace `gale-ec/.build/` and refreshes the
vendored analysis references `renode/data/rebuilt-R{O,W}.elf`.

## What's tracked vs fetched

| Input | Where | Tracked? |
|-------|-------|----------|
| Board source of truth | `board/gale/*` | yes |
| Local platform/ec patches | `firmware-patches/*.patch` | yes |
| Build recipe + pinned upstream rev | `build-firmware.sh` | yes |
| upstream ChromeOS EC `@ firmware-gale-8281.B` (`7c97ab0…`) | `.build/ec` | fetched (pinned) |
| arm-none-eabi **2016q3** toolchain | `.build/gcc-arm-none-eabi-5_4-2016q3` | fetched (pinned URL) |
| Build output / vendored ELFs | `.build/…`, `renode/data/rebuilt-*.elf` | ELFs committed |

`.build/` is gitignored — it is fully reproducible from the pinned rev + patches + board files, so it
is never committed.

## Why the 2016q3 toolchain

The captured firmware was built with arm-none-eabi 2016q3 and the build pins it: the host gcc-14
mis-builds the 2016-era tree (a bare-C99 `inline` link failure) **and** would inject codegen
differences that pollute the captured-vs-rebuilt equivalence comparison. The script downloads it
(~89 MB, once) into `.build/`. To reuse an existing install instead:

```sh
GALE_EC_TOOLCHAIN=/path/to/gcc-arm-none-eabi-5_4-2016q3 ./build-firmware.sh
```

## The vendored ELFs

`renode/data/rebuilt-R{O,W}.elf` are committed so the coverage/equivalence tooling is self-contained
(see `renode/data/README.md`). `build-firmware.sh` regenerates them; the EC version string embeds a
build date, so a rebuild produces a byte-different ELF — re-commit them when the board sources actually
change, alongside any regenerated reports.
