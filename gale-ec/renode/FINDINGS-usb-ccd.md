# Finding: rebuilt gale firmware is missing `CONFIG_CASE_CLOSED_DEBUG` (USB/CCD)

Surfaced by the Renode differential-equivalence harness while trying to exercise
the USB device controller (USB UART consoles + raiden SPI bridge). This is a
genuine **functional** divergence between the original dump and the reconstruction
— recorded here rather than papered over.

## What was expected (and was wrong)

The earlier working assumption was that gale autonomously toggles SNK→SRC→
SRC_ACCESSORY and calls `usb_init()` via Case-Closed Debug during boot, so USB
would come up on its own. That premise is **false for the firmware as configured**:

* `board/gale/board.h` defines `CONFIG_USB_INHIBIT_INIT`, so the auto
  `DECLARE_HOOK(HOOK_INIT, usb_init, …)` in `chip/stm32/usb.c:317` is compiled out.
* The only in-tree STM32 caller of `usb_init()` is `common/case_closed_debug.c:55`
  (`chip/g/usb.c` is the Cr50 "g" chip; the third hit is a host-side test).
* The rebuilt `board/gale/board.h` does **not** define `CONFIG_CASE_CLOSED_DEBUG`
  (`include/config.h:304` `#undef`s it; `common/build.mk:29` gates the .o on it),
  so `case_closed_debug.c` is never compiled → nothing calls `usb_init()` →
  `--gc-sections` removes it.

## Proof (binary-level, both repos)

Symbol tables of the rebuilt ELFs (`arm-none-eabi-nm`):

```
RO usb_init symbols: 0
RW usb_init symbols: 0
build/gale/.../case_closed_debug.o : not present
```

Differential register-literal counts, original dump vs rebuilt `ec.bin`
(little-endian peripheral addresses; `usb_init` is the only writer of BTABLE):

```
                         original  rebuilt
USB_CNTR   0x40005c40        4        2     (orig: usb_init + usb_release; rebuilt: usb_release only)
USB_ISTR   0x40005c44        4        2
USB_BTABLE 0x40005c50        2        0     (BTABLE=0 is written ONLY by usb_init)
"USB init done" string      2        2     (orphaned .rodata survives GC in the rebuild — a red herring)
```

The string count matching (2/2) is why a casual check looked equivalent; only the
**register-write literals** expose that the rebuild contains no `usb_init` code at all.

Empirically, neither image prints `USB init done` during ~2.5 s of autonomous boot
— USB is dormant in both until a USB-PD debug accessory is detected. The divergence
is *callability*: the original retains `usb_init` (reachable via CCD); the rebuild
cannot reach it under any input.

## Consequence for the equivalence goal

* USB UART consoles (if00/if01) and the raiden SPI bridge (if03) cannot be
  exercised on the rebuilt firmware as-built — there is no code path to power the
  USB controller. So tasks #12–#14 (live USB) are blocked on a **firmware** fix,
  not a Renode-peripheral gap.
* The two images are different firmware *versions* (orig `v1.1.5337` 2016 vs
  reconstruction `v0.0.1`); their PD state-machine enum numbering already differs
  (orig progresses `st2→st16→st17`; rebuild holds at `st2`). Byte-/trace-identical
  execution between two different source versions is not attainable; the harness's
  standard is functional equivalence with documented deltas (see `battery.py`
  `DOCUMENTED_DELTAS`).

## Fix being attempted

Restore `CONFIG_CASE_CLOSED_DEBUG` (+ its dependencies) to `board/gale/board.h` so
the reconstruction matches the original's USB/CCD capability. Verification: `usb_init`
reappears in the rebuilt symbol table and the CNTR/ISTR/BTABLE literal counts match
the original. Once present, the SNK→SRC→SRC_ACCESSORY→`ccd_set_mode`→`usb_init` path
is compiled in, and the `GaleAdc.cs` faithful dynamic-CC model (added alongside this
finding) drives the debug-accessory detection that brings USB up.
