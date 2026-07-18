# gale EC firmware — reconstructed source

Reverse-engineered reconstruction of the **`board/gale/`** source for the Google
Wifi (`gale`) ChromiumOS Embedded Controller firmware **`gale_v1.1.5337-0115719`**,
recovered from this unit's on-device dump
([`../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin`](../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin)).

> 📊 **For the full project status — equivalence verdict, per-command / per-file / per-peripheral
> coverage, the Renode harness, and all tooling — see [STATE-OF-THE-EC.md](STATE-OF-THE-EC.md)
> (the top-level overview).**

The board layer was **stripped from the public `firmware-gale-8281.B` branch** of
`chromiumos/platform/ec`; everything else the firmware is built from
(`common/`, `chip/stm32`, `core/cortex-m0`, `driver/`) is upstream and unchanged.
So only these board files needed reconstructing.

An **independent reviewer certified the recompiled firmware functionally
equivalent** to the dump — see [`EQUIVALENCE-REVIEW-2.md`](EQUIVALENCE-REVIEW-2.md)
(verdict: *FUNCTIONALLY EQUIVALENT*) and [`EQUIVALENCE-REVIEW-1.md`](EQUIVALENCE-REVIEW-1.md)
(the first pass that found 4 USB-PD divergences, since fixed). Details in
[`FIDELITY.md`](FIDELITY.md).

## Files (`board/gale/`)

`board.h`, `board.c`, `gpio.inc`, `build.mk`, `ec.tasklist`, `usb_pd_config.h`,
`usb_pd_policy.c` — reverse-engineered reconstructions, **BSD-3-Clause** (matching
`platform/ec`). (`board/gale/Makefile` is just a symlink to the tree's top-level
`Makefile`, created during the overlay step below.)

## Reproduce

**Canonical build:** [`./build-firmware.sh`](build-firmware.sh) does all of the below from tracked
inputs (pinned upstream + the tracked `firmware-patches/` + this `board/gale/` overlay + the 2016q3
toolchain) into the gitignored `.build/` workspace, and refreshes the vendored analysis ELFs. See
[BUILD.md](BUILD.md). The manual steps below document what it does:

```sh
# 1. The public EC tree at the exact revision the firmware was built from
git clone --branch firmware-gale-8281.B --single-branch \
    https://chromium.googlesource.com/chromiumos/platform/ec ec

# 2. Overlay the reconstructed board
mkdir -p ec/board/gale
cp gale-ec/board/gale/* ec/board/gale/
ln -sf ../../Makefile ec/board/gale/Makefile

# 3. Period toolchain: gcc-arm-none-eabi 5.4 (2016q3) — contemporaneous with the
#    firmware's 2016-10-03 build. (The tree pins only the arm-none-eabi tuple, no
#    version, so any reasonably-period arm-none-eabi works. gcc 14 will NOT build
#    this 2016 code without patching the public tree, so a period toolchain is
#    strongly preferred.)
#    https://launchpad.net/gcc-arm-embedded/5.0/5-2016-q3-update

# 4. Build
make -C ec BOARD=gale \
    CROSS_COMPILE=/path/to/gcc-arm-none-eabi-5_4-2016q3/bin/arm-none-eabi- \
    -j4 build/gale/ec.bin
```

This produces `ec/build/gale/ec.bin` (128 KB = 64 KB RO + 64 KB RW) whose reset
vectors are **byte-identical** to the dump and whose FMAP geometry matches it.
