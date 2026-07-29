# gale EC — console command reference

Complete reference for the **27 console commands** exposed on the gale EC's serial/USB console
(`gale_v1.1.5337-0115719`). The console is reachable over the USART1 debug UART and the USB serial
interfaces (`if00`/`if01`). Each command is registered with `DECLARE_CONSOLE_COMMAND`; the set here is
the exact table shipped on the device (verified against the captured firmware's `__cmds`).

> **How the examples were produced.** Every example output in this document is **real output captured
> from the proprietary firmware** running in the Renode emulator
> ([`renode/capture_console.py`](renode/capture_console.py) against the captured dump), except where a
> command resets the CPU (`crash`, `reboot`, `sysjump`) — those are documented from the source. A few
> outputs reflect emulator state: the modeled CC partner makes the port read as attached
> (`SRC_ACCESSORY`) where a bare device would read `SNK_DISCONNECTED`; this is called out per command.

**Conventions:** `> ` is the console prompt. Arguments in `[ ]` are optional, `< >` required, `|`
separates alternatives. Most commands print `Wrong number of params` + a `Usage:` line on bad input.

## Summary

| Command | Source | Description |
|---|---|---|
| [`adc`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/adc.c#32) | common/adc.c | Print one or all ADC channels (CC1, CC2, VBUS, CUR) |
| [`chan`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console_output.c#111) | common/console_output.c | Show / set / save / restore the console output-channel mask |
| [`crash`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c#158) | common/panic_output.c | Deliberately crash the EC (assert/divzero/stack/unaligned/watchdog) — **resets** |
| [`flashinfo`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#538) | common/flash.c | Print internal-flash geometry + write-protect state |
| [`flashwp`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#699) | common/flash.c | Modify the internal-flash write-protect setting |
| [`gale`](board/gale/board.c#L421) | board/gale/board.c | gale board control: AP power rails, CC polarity, dev/rec mode, read CC/VBUS |
| [`gettime`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/timer.c#303) | common/timer.c | Print the current 64-bit EC timer value |
| [`gpioget`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#111) | common/gpio_commands.c | Read the level of one or all GPIO signals |
| [`gpioset`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#140) | common/gpio_commands.c | Drive an output GPIO high or low |
| [`hash`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/vboot_hash.c#266) | common/vboot_hash.c | Query or recompute the verified-boot image hash |
| [`hcdebug`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#872) | common/host_command.c | Set host-command debug logging verbosity |
| [`help`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console.c#685) | common/console.c | List commands, or print help for one command |
| [`history`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/console.c#768) | common/console.c | Print the console command history |
| [`md`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/memory_commands.c#59) | common/memory_commands.c | Dump memory (byte / half / word / string) |
| [`panicinfo`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c#196) | common/panic_output.c | Print details of the last saved panic |
| [`pd`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#2869) | common/usb_pd_protocol.c | USB Power Delivery control / introspection |
| [`reboot`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#942) | common/system.c | Reboot the EC (hard/soft, preserve, ap-off, cancel) — **resets** |
| [`rw`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/memory_commands.c#115) | common/memory_commands.c | Read or write a word (or byte/half) at a memory address |
| [`spixfer`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/spi_commands.c#15) | common/spi_commands.c | Read/write bytes over a board SPI device (AP-flash bridge) |
| [`sysinfo`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#809) | common/system.c | Print reset flags, active image copy, jump + lock state |
| [`sysjump`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#901) | common/system.c | Jump to RO/RW image or an address (or disable jumping) — **resets** |
| [`syslock`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#977) | common/system.c | Permanently lock the system this boot (even if WP is off) |
| [`taskinfo`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/core/cortex-m0/task.c#567) | core/cortex-m0/task.c | Print the RTOS task table (state, events, stack usage) |
| [`tcpc`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_tcpc.c#1309) | common/usb_pd_tcpc.c | Type-C Port Controller introspection |
| [`typec`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/driver/usb_mux.c#108) | driver/usb_mux.c | Read / set the Type-C connector mux (none/usb/dp/dock) |
| [`version`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#886) | common/system.c | Print RO / RW / build version strings |
| [`waitms`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/timer.c#254) | common/timer.c | Busy-wait for the given number of milliseconds |

---

## Command details

Examples are real captured output (`>` is the prompt). Line numbers cite the pinned upstream tree.

### `adc`
- **Usage:** `adc [name]` — print one ADC channel, or all of them.
- **Arguments:** optional channel `name` (case-insensitive: `CC1`, `CC2`, `VBUS`, `CUR`). No arg → all channels.
- **State:** read-only; no preconditions.
- **Example:**
  ```
  > adc
    CC1 = 0
    CC2 = 0
    VBUS = 0
    CUR = 0
  ```
  (All read 0 with nothing attached / in emulation.)
- **Errors:** `EC_ERROR_PARAM1` if the name is unknown; `EC_ERROR_UNKNOWN` on a read failure.

### `chan`
- **Usage:** `chan [ save | restore | <mask> ]` — show, set, save or restore the console output-channel mask.
- **Arguments:** `save`/`restore` snapshot or restore the mask; a numeric `<mask>` (base-0) sets it. The `command` channel bit is always forced on so console replies can never be silenced. No arg → list all channels.
- **Example:**
  ```
  > chan
   # Mask     E Channel
   0 00000001 * command
   1 00000002 * accel
   ...
  23 00800000 * usbpd
  24 01000000 * vboot
  25 02000000 * hook
  ```
- **Errors:** `EC_ERROR_PARAM1` if `<mask>` has trailing non-numeric characters.

### `crash`
- **Usage:** `crash <assert | divzero | stack | unaligned | watchdog> [options]` — deliberately crash the EC (test tool). **Resets the CPU.**
- **Arguments:** the fault type is required. `divzero` accepts an optional `unsigned` keyword.
- **State:** destructive — intentionally faults and reboots; control never returns. (In the Renode harness the machine halts after the fault rather than clean-rebooting.)
- **Example (the resulting exception dump — this is the `panic_data_print` format shared with `panicinfo`):**
  ```
  === HANDLER EXCEPTION: 00 ====== xPSR: 00000000 ===
  r0 :00000088 r1 :0800d5cc r2 :20001348 r3 :08006ecf
  r4 :dead6663 r5 :00000088 r6 :00000010 r7 :00000000
  r8 :00000000 r9 :00000000 r10:00000000 r11:00000000
  r12:20001348 sp :20001bf0 lr :0800af89 pc :0001da83
  Rebooting...
  ```
- **Errors:** `EC_ERROR_PARAM1` for a missing/unknown fault type.

### `flashinfo`
- **Usage:** `flashinfo` — print internal-flash geometry and protection state.
- **Arguments:** none.
- **State:** read-only.
- **Example:**
  ```
  > flashinfo
  Usable:   128 KB
  Write:      2 B (ideal 2 B)
  Erase:   2048 B (to 1-bits)
  Protect: 4096 B
  Flags:   ro_at_boot
  Protected now:
      ........ ........ ........ ........
  ```
  `Flags:` lists asserted protection flags (`wp_gpio_asserted`, `ro_at_boot`, `all_at_boot`, `ro_now`, `all_now`, `STUCK`, `INCONSISTENT`); the grid shows per-bank protection (`Y`=protected, `.`=not).

### `flashwp`
- **Usage:** `flashwp <enable | disable | now | rw | norw>` — change the internal-flash write-protect.
- **Arguments (each maps to `flash_set_protect(flag, mask)`):** `enable`→set RO-at-boot, `disable`→clear RO-at-boot, `now`→protect ALL now, `rw`→protect ALL at boot, `norw`→clear ALL-at-boot.
- **State:** `now`/`enable` set protection that typically clears only on a reboot with the WP pin de-asserted (semi-persistent). Succeeds silently (no output).
- **Example (bad/no argument — shows the usage line):**
  ```
  > flashwp
  Wrong number of params
  Usage: flashwp <BOOLEAN> | now | rw | norw
  ```
- **Errors:** `EC_ERROR_PARAM_COUNT` (no arg), `EC_ERROR_PARAM1` (unknown keyword).

### `gale`  *(board-specific)*
- **Usage:** `gale [power [on|off] | polarity [0|1] | dev [on|off] | rec [on|off] | cc | vbus]` — gale board controls. No sub-command → dump everything.
- **Arguments:** `power on/off` drives the AP power rails; `polarity 0/1` sets `USB_CC_POLARITY`; `dev`/`rec on/off` drive the ENTERING_DEV / ENTERING_REC strap GPIOs; `cc` reads both CC-line voltages; `vbus` reads VBUS mV + input current.
- **State — important:** the *mutating* subcommands (`power`/`polarity`/`dev`/`rec`) only act when **both** the system is unlocked **and** an argument is given: `if (!system_is_locked() && argc > 1)`. **When the system is locked they print status and make no change (no `OK` line).** `cc`/`vbus` are read-only and always work.
- **Examples:**
  ```
  > gale cc
        cc - 0mV, 0mV
  > gale vbus
      vbus - 0mv 0ma
  ```
  A successful mutating call prints `OK` first, e.g. `gale power on` → `OK` then ` power - on`.
- **Errors:** `EC_ERROR_PARAM1` if the subcommand is unrecognized.

### `gettime`
- **Usage:** `gettime` — print the current 64-bit microsecond timer.
- **Example:**
  ```
  > gettime
  Time: 0x00000000001ab382 = 1.749890 s
  ```

### `gpioget`
- **Usage:** `gpioget [name]` — read one GPIO, or all of them.
- **Arguments:** optional signal `name` (case-insensitive). No arg → every implemented GPIO.
- **Output format:** ` <value><changed> <name>`, where `*` marks a signal whose level differs from its configured default.
- **Examples:**
  ```
  > gpioget WP_L
    1* WP_L
  ```
  All signals (abridged — 26 signals total):
  ```
  > gpioget
    0  USB_CC1_PD
    0  USB_CC2_PD
    1* USB_CC_POLARITY
    ...
    1* WP_L
    1* SYS_PWR_EN
    ...
  ```
- **Errors:** `EC_ERROR_PARAM1` if the name is unknown.

### `gpioset`
- **Usage:** `gpioset name <0 | 1>` — drive an output GPIO. (This build is non-extended, so only `0`/`1`.)
- **Arguments:** GPIO `name` + numeric level. The signal must be an **implemented output**.
- **Example (set, then confirm with `gpioget`):**
  ```
  > gpioset ERROR_LED 1
  > gpioget ERROR_LED
    1* ERROR_LED
  ```
- **Errors:** `EC_ERROR_PARAM_COUNT` (<2 args), `EC_ERROR_PARAM1` (unknown name), `EC_ERROR_PARAM2` (bad value); `EC_ERROR_INVAL` from the setter if the signal isn't an output.

### `hash`
- **Usage:** `hash [abort | ro | rw] | [<offset> <size> [<nonce>]]` — query or recompute the verified-boot image hash.
- **Arguments:** no arg → status; `abort` cancels; `ro`/`rw` hash the RO/RW image region; `<offset> <size> [nonce]` hash an arbitrary region (all base-0), optional 32-bit nonce seed.
- **State:** starts an asynchronous recompute (`in progress` until done).
- **Examples:**
  ```
  > hash
  Offset: 0x00010000
  Size:   0x0000e2a8 (58024)
  Digest: 5a2d7c5ae02bb9aa35876b56de7dbc22413a61c41803a6abe5c93fdb99878b20
  > hash ro
  [2.000416 hash start 0x00000000 0x0000e43c]
  [2.069256 hash done 5e1a761306ab4031f82982f0cf9f273969fbb03b4a73d8e7d38ac51175071254]
  ```
- **Errors:** `EC_ERROR_PARAM1/2/3` for malformed offset/size/nonce.

### `hcdebug`
- **Usage:** `hcdebug [off | normal | every | params]` — set host-command debug verbosity; always prints the resulting mode.
- **Example:**
  ```
  > hcdebug
  Host command debug mode is normal
  ```
- **Errors:** `EC_ERROR_PARAM1` for an unknown mode name.

### `help`
- **Usage:** `help [ list | <name> ]` — command list, per-command help, or one command's usage.
- **Example:**
  ```
  > help
  Known commands:
    adc            gettime        history        spixfer        typec
    chan           gpioget        md             sysinfo        version
    crash          gpioset        panicinfo      sysjump        waitms
    flashinfo      hash           pd             syslock
    flashwp        hcdebug        reboot         taskinfo
    gale           help           rw             tcpc
  HELP LIST = more info; HELP CMD = help on CMD.
  ```
- **Errors:** `EC_ERROR_UNKNOWN` if a named command is not found/ambiguous.

### `history`
- **Usage:** `history` — print the console command history.
- **Example:**
  ```
  > history
  chan
  help
  history
  ```

### `md`
- **Usage:** `md [.b|.h|.s] addr [count]` — dump memory. Default format is 32-bit words; `.b`=bytes, `.h`=halfwords, `.s`=string. `count` defaults to 1.
- **State:** reads arbitrary memory — a bad address can fault.
- **Examples:**
  ```
  > md 0x08000000 4

  08000000: 200004c0 080000ed 0800013b 0800013b
  > md .b 0x08000000 16

  08000000: c0 04 00 20 ed 00 00 08 3b 01 00 08 3b 01 00 08
  > md .h 0x08000000 8

  08000000: 04c0 2000 00ed 0800 013b 0800 013b 0800
  ```
- **Errors:** `EC_ERROR_PARAM1` (bad format/address), `EC_ERROR_PARAM_COUNT` (no address).

### `panicinfo`
- **Usage:** `panicinfo` — print details of the last saved panic (registers + exception).
- **State:** requires a valid saved panic record (magic present); reading it marks it as "seen".
- **Example (no panic saved):**
  ```
  > panicinfo
  No saved panic data available.
  ```
  When a panic *is* saved, it prints the `=== ... EXCEPTION ===` register dump shown under [`crash`](#crash).

### `pd`
- **Usage:** `pd dualrole|dump|enable [0|1]|rwhashtable|trysrc [0|1]` and `pd <port> [tx|bist_rx|bist_tx|charger|clock|dev|soft|hash|hard|ping|state|swap [power|data]|vdm [ping|curr|vers]]` — USB-PD control/introspection. gale has one port (`0`).
- **Arguments:** global subcommands manage dual-role policy, dump verbosity (`dump [level]`), comms enable, the RW-hash table, and Try.SRC. Port subcommands drive the port's PD state machine and `state` prints its status.
- **State:** port must be `< CONFIG_USB_PD_PORT_COUNT` (i.e. `0`). Many subcommands change live PD behavior.
- **Examples:**
  ```
  > pd dump
  dump level: 0
  > pd 0 state
  Port C0 CC1, Ena - Role: SRC-DFP State: SRC_ACCESSORY, Flags: 0x0080
  ```
  *(In emulation the modeled CC partner makes the port read `SRC_ACCESSORY`; a bare device with nothing attached reads `SNK_DISCONNECTED`.)* Bad usage:
  ```
  > pd 0
  Wrong number of params
  Usage: pd dualrole|dump|enable [0|1]|rwhashtabletrysrc [0|1]
  <port> [tx|bist_rx|bist_tx|charger|clock|dev|soft|hash|hard|ping|state|swap [power|data]|vdm [ping | curr | vers]]
  ```
- **Errors:** `EC_ERROR_PARAM_COUNT` / `PARAM1..4` for missing/bad subcommand, port, or values.

### `reboot`
- **Usage:** `reboot [hard|soft] [preserve] [ap-off] [cancel]` — reboot the EC. **Resets the CPU.**
- **Arguments (order-independent):** `hard`/`cold`→hard reset; `soft`→soft; `ap-off`→leave the AP off after reset; `preserve`→keep reset flags; `cancel`→cancel a *pending* shutdown-reboot and return **without** resetting.
- **State:** destructive (except `cancel`). Prints a banner then calls `system_reset`, which does not return.
- **Example:** `reboot` prints `Rebooting!` (or `Hard-Rebooting!`) then resets.
- **Errors:** a positional `EC_ERROR_PARAM*` for an unrecognized word.

### `rw`
- **Usage:** `rw [.b|.h] addr [value]` — read (no value) or write (value given) a byte/half/word in memory. Default width is word.
- **State:** reads/writes arbitrary memory directly — a write can corrupt state or fault.
- **Example:**
  ```
  > rw 0x20000000
  read 0x20000000 = 0x200004c0
  ```
- **Errors:** `EC_ERROR_PARAM_COUNT` (no addr), `EC_ERROR_PARAM1[+n]` (bad size/addr), `EC_ERROR_PARAM2[+n]` (bad value).

### `spixfer`
- **Usage:** `spixfer rlen|w id offset [value|len]` — read/write a board SPI device. `id` indexes the `spi_devices[]` array (the AP-flash bridge is index `0`).
- **Arguments (exactly 4):** mode (`rlen` read / `w` write), device `id`, `offset`, and `len` (for read, ≤32) or `value` (for write).
- **Example (read JEDEC ID `0x9F` from the AP flash → Winbond W25Q64 `ef4017`):**
  ```
  > spixfer rlen 0 0x9f 3
  Data: ef4017
  ```
- **Errors:** `EC_ERROR_PARAM_COUNT` (argc≠5), `EC_ERROR_PARAM1` (bad mode), `EC_ERROR_PARAM2/3/4` (bad id/offset/value or length >32).

### `sysinfo`
- **Usage:** `sysinfo` — print reset flags, active image, jump and lock state.
- **Example (unlocked, then after `syslock`):**
  ```
  > sysinfo
  Reset flags: 0x0000000a (reset-pin power-on)
  Copy:   RO
  Jumped: no
  Flags:  unlocked
  > syslock
  > sysinfo
  Reset flags: 0x0000000a (reset-pin power-on)
  Copy:   RO
  Jumped: no
  Flags:  locked (forced)
  ```
  This is the clearest demonstration of a state-dependent command: after `syslock`, `Flags:` changes to `locked (forced)` and lock-gated operations (e.g. `gale power`, arbitrary `sysjump`) stop working.

### `sysjump`
- **Usage:** `sysjump [RO | RW | addr | disable]` — jump to an image or address, or disable jumping. **Transfers control / resets.**
- **Arguments:** `RO`/`RW` run that image copy; `disable` blocks further jumps; a numeric `addr` jumps there.
- **State:** an **arbitrary-address** jump requires an unlocked system — `if (system_is_locked()) return EC_ERROR_ACCESS_DENIED;`. `RO`/`RW`/`disable` are not lock-gated.
- **Errors:** `EC_ERROR_PARAM_COUNT` (no arg), `EC_ERROR_ACCESS_DENIED` (locked + address), `EC_ERROR_PARAM1` (bad address).

### `syslock`
- **Usage:** `syslock` — force the system into the locked state, even if the WP pin is de-asserted.
- **State — important:** sets `force_locked = 1`; there is **no console un-lock**, so it is effectively irreversible for the rest of the boot. After it, `system_is_locked()` returns true and lock-gated commands stop mutating (see the `sysinfo` example above). Produces no output.

### `taskinfo`
- **Usage:** `taskinfo` — print the RTOS task table.
- **Example:**
  ```
  > taskinfo
  Task Ready Name         Events      Time (s)  StkUsed
     0 R << idle >>       00000000    0.000000   64/256
     1   HOOKS            00000000    0.000000  504/640
     2   HOSTCMD          00000000    0.000000  152/488
     3 R CONSOLE          00000000    0.000000  356/488
     4   PD_C0            00000000    0.000000  444/640
  ```
  `R` marks a runnable task; `StkUsed` is peak/total stack bytes. (IRQ/exception statistics also print when `CONFIG_TASK_PROFILING` is built.)

### `tcpc`
- **Usage:** `tcpc dump [0|1]` and `tcpc <port> [clock <freq> | state]` — Type-C Port Controller introspection (gale *is* its own TCPC).
- **Arguments:** `dump [level]` reads/sets debug verbosity; per-port `clock <freq>` sets the TX bit-clock; `state` prints the port's CC/alert/power status.
- **Example (missing the required 2nd arg → usage):**
  ```
  > tcpc 0
  Wrong number of params
  Usage: tcpc dump [0|1]
  <port> [clock|state]
  ```
- **Errors:** `EC_ERROR_PARAM_COUNT`, `EC_ERROR_PARAM2` (bad level/port/freq).

### `typec`
- **Usage:** `typec [port|debug] [none|usb|dp|dock]` — read or set the Type-C connector mux.
- **Arguments:** `debug` enables mux debug prints; a `port` alone prints its polarity + SuperSpeed mux status; `port` + a mux mode sets it (`none` disconnects).
- **Examples:**
  ```
  > typec 0
  Port C0: polarity:CC1
  No Superspeed connection
  ```
  Missing the port → usage:
  ```
  > typec
  Wrong number of params
  Usage: typec [port|debug] [none|usb|dp|dock]
  ```
- **Errors:** `EC_ERROR_PARAM_COUNT` (no port), `EC_ERROR_PARAM1` (bad/out-of-range port).

### `version`
- **Usage:** `version` — print chip, board, RO/RW image, and build version strings.
- **Example:**
  ```
  > version
  Chip:    stm stm32f07x
  Board:   0
  RO:      gale_v1.1.5337-0115719
  RW:      gale_v1.1.5337-0115719
  Build:   gale_v1.1.5337-0115719
           2016-10-03 15:55:36 hywu@hywu-z620.tpe.corp.google.com
  ```

### `waitms`
- **Usage:** `waitms msec` — busy-wait (spin, not sleep) for `msec` milliseconds.
- **State:** blocks the console/task for the duration; large values can starve other work or trip the watchdog. No output.
- **Example:** `waitms 1` returns after ~1 ms with no output.
- **Errors:** `EC_ERROR_PARAM_COUNT` (no arg), `EC_ERROR_PARAM1` (non-numeric).

