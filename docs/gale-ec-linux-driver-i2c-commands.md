# gale EC ↔ Linux `cros_ec` drivers — I2C host-command requirements

**Driver-centric** companion to the EC-centric
[`I2C-HOST-COMMANDS.md`](../../renode-equiv/gale-ec/I2C-HOST-COMMANDS.md) (branch
`gale-ec-renode-equivalence`). That document answers *"what does the gale EC
answer?"*. **This** document answers the inverse, practical question:

> *Which I2C host commands do the mainline Linux **`cros_ec` drivers** need or
> use, which are **required** vs **optional**, and which does gale's current EC
> actually **implement** — so which driver features work, which are dead, and
> what it would take to light the rest up.*

The gale puck's AP (IPQ4019, OpenWrt, kernel **6.12**) reaches the EC in-band
over **I2C at 7-bit address `0x1e`** on `/dev/i2c-1`, host-command **protocol v3
only**. Enabling the `cros_ec` driver family (kmod-cros-ec — see
[`openwrt-patches/0002‑0004`](../openwrt-patches/)) brings up `/dev/cros_ec` and
lets the kernel talk to the EC through the standard ChromeOS stack instead of a
raw-I2C tool. This document maps that stack against gale's real command set.

> **Address footnote.** The EC firmware sets `CONFIG_HOSTCMD_I2C_SLAVE_ADDR
> 0x3C` (`STM32_I2C_OAR1 = 0x803C`). STM32 OAR1 holds the 7-bit address in bits
> **[7:1]**, so `0x3C >> 1 = 0x1E` is the true 7-bit address — which is exactly
> what the kernel binds (`cros-ec-i2c 1-001e`) and what the device-tree node
> uses (`reg = <0x1e>`). The `0x3C` you see in the EC config is the address
> already shifted left by one.

---

## 1. Summary table

**Required** = a `cros_ec` driver's `probe()` (or the core bring-up) returns an
error / the interface is unusable if the command is missing or errors.
**Optional** = failure is tolerated (best-effort, has a fallback, or only
affects one attribute).

**gale EC status:**
- **✅ impl** — one of the 31 commands gale's EC answers today.
- **⚠️ addable** — the command *exists* in gale's EC codebase (ChromiumOS
  `platform/ec` @ `firmware-gale-8281.B`, 2016) but is **not compiled** on gale
  (guarded by an undefined `CONFIG_*`). Reachable by enabling that config + its
  board glue and reflashing the EC RW image.
- **❌ absent** — the command **does not exist** in gale's 2016 EC codebase at
  all; it was invented in a much newer EC tree. Requires a fundamentally newer
  EC, not a config flip. (The renode-equivalence reconstruction shares the same
  2016 base, so ⚠️/❌ are identical there.)

| # | Command | Used by (driver / interface) | Req? | gale | What it does |
|--:|---|---|:--:|:--:|---|
| `0x0b` | GET_PROTOCOL_INFO | core bring-up (`cros_ec_proto`) | **REQ** | ✅ | Negotiate protocol version + max packet sizes. **The one fatal bring-up command.** |
| `0x0b`+`0x400b` | GET_PROTOCOL_INFO (PD passthru) | core bring-up | opt | ✅/❌ | Probe a PD MCU behind the EC (index 1). gale has none → no `cros_pd` device. |
| `0x0d` | GET_FEATURES | MFD (`cros_ec_dev`) | opt* | ✅ | 64-bit feature bitmap. gale=`0x00004002` (FLASH+GPIO only). **Decides which consumer cells instantiate.** |
| `0x08` | GET_CMD_VERSIONS | core + several probes | opt | ✅ | Query a command's supported version mask (used to detect MKBP, host-sleep-v1, typec PD_CONTROL version). |
| `0x01` | HELLO | core bring-up (v2 fallback only) | opt | ✅ | Legacy liveness echo; only used if v3 proto probe fails (never on gale). |
| `0x67` | GET_NEXT_EVENT | core (MKBP), usbpd-notify | opt | ⚠️ | MKBP event/IRQ delivery. gale advertises no version → `mkbp_event_supported=0`, polled/absent. |
| `0x8d` | HOST_EVENT_GET_WAKE_MASK | core bring-up | opt | ⚠️ | Suspend wake-event mask; failure → hardcoded default (silent on `-EOPNOTSUPP`). |
| `0xa9` | HOST_SLEEP_EVENT | core bring-up | opt | ⚠️ | Clear stale S0ix sleep state at boot; "fails harmlessly". |
| `0x02` | GET_VERSION | sysfs `version`, `cros_ec_sysfs` | opt | ✅ | RO/RW firmware version strings + running image. |
| `0x04` | GET_BUILD_INFO | sysfs `version` | opt | ✅ | Build-info string. |
| `0x05` | GET_CHIP_INFO | sysfs `version` | opt | ✅ | Chip vendor / name / revision (`stm` / `stm32f07x`). |
| `0x06` | GET_BOARD_VERSION | sysfs `version` | opt | ⚠️ | Board hardware version. **Not compiled on gale → `version` shows `Board version: … EC ERROR -95`** (live proof of an unimplemented command). |
| `0x10` | FLASH_INFO | sysfs `flashinfo` | opt | ✅ | EC flash geometry. |
| `0xd2` | REBOOT_EC | sysfs `reboot` | opt | ✅ | Reboot the EC with flags. |
| `0x97`/`0x98` | CONSOLE_SNAPSHOT / CONSOLE_READ | debugfs `console` | opt | ✅ | Latch + drain the EC console ring buffer. |
| `0xd3` | GET_PANIC_INFO | debugfs `panicinfo` | opt | ✅ | Saved EC panic block. |
| `0x2a` | VBOOT_HASH | (`ectool`/diag via chardev) | opt | ✅ | Get/start/abort the RW image SHA-256. |
| `0x07` | READ_MEMMAP | debugfs / hwmon (legacy sensors) | opt | ✅ | Read the EC memory-map region (I2C transport does **not** wire `cmd_readmem`). |
| `0x92`/`0x93` | GPIO_SET / GPIO_GET | **gpio-cros-ec** | **REQ** | ✅ | Read/drive EC GPIOs. **The one consumer driver that fully works on gale** (EC_FEATURE_GPIO advertised). |
| `0x17` | VBNV_CONTEXT | cros-ec-vbc | REQ | ✅ | Read/write vboot NV context. Implemented, but the **vbc cell needs a DT `google,has-vbc-nvram` property** → not instantiated on gale. |
| `0x0101` | USB_PD_CONTROL | cros-ec-typec, extcon, debugfs `pdinfo` | REQ (typec) | ✅ (v1) | Per-port PD role/mux/state. gale offers **v0/v1**; cros-ec-typec **accepts v1** at probe (v2 only needed at runtime for DP/TBT altmode, non-fatal). |
| `0x0102` | USB_PD_PORTS | cros-ec-typec, extcon | REQ | ✅ | Number of PD ports (gale = 1). |
| `0x0103` | USB_PD_POWER_INFO | **extcon** (fatal), usbpd-charger | REQ | ⚠️ | Per-port voltage/current/type. **extcon bails on failure** (`if (power_type<0) return;`). Not compiled on gale. |
| `0x00a0` | CHARGE_STATE | usbpd-charger | opt | ⚠️ | Charger/battery state. Needs `CONFIG_CHARGE_MANAGER` (absent). |
| `0x0104` | PD_HOST_EVENT_STATUS | usbpd-notify (ACPI), logger | opt | ⚠️ | PD host-event status word. |
| `0x0115` | PD_GET_LOG_ENTRY | cros-usbpd-logger | opt | ⚠️ | Drain the EC's PD event log (runtime poll; probe issues nothing). |
| `0x011a` | USB_PD_MUX_INFO | cros-ec-typec, extcon | opt | ❌ | Type-C mux state (runtime; failure defaulted/warned). Absent from the 2016 EC. |
| `0x0132` | TYPEC_CONTROL | cros-ec-typec | opt | ❌ | Modern Type-C port control (runtime, feature-gated). Absent. |
| `0x0133` | TYPEC_STATUS | cros-ec-typec | opt | ❌ | Modern Type-C port status (runtime, feature-gated). Absent. |
| `0x0603` | USB_PD_MUX_ACK | cros-ec-typec | opt | ❌ | Ack an AP-driven mux set. Absent. |
| `0x0044`–`0x0047` | RTC_GET/SET_VALUE/ALARM | rtc-cros-ec | REQ | ⚠️ | EC real-time clock. Needs `CONFIG_HOSTCMD_RTC` (absent) **and** `EC_FEATURE_RTC` → no cell. |
| `0x009e` | I2C_PASSTHRU | i2c-cros-ec-tunnel | opt | ⚠️ | Tunnel I2C through the EC (runtime; probe issues nothing). Needs `CONFIG_I2C_PASSTHRU` + DT node. |
| `0x012c`–`0x0130` | REGULATOR_* | cros-ec-regulator | REQ | ❌ | EC-controlled regulators. Absent from the 2016 EC; DT-instantiated. |
| `0x0029` | LED_CONTROL | leds-cros_ec | REQ | ⚠️ | EC LED control. Needs `CONFIG_LED_COMMON` + `EC_FEATURE_LED` → no cell. |
| `0x0028` | LIGHTBAR_CMD | cros_ec_lightbar | REQ | ⚠️ | Pixel lightbar. gale has no lightbar → no `EC_FEATURE_LIGHTBAR` → no cell. |
| `0x002b` | MOTION_SENSE_CMD | cros_ec_sensorhub | REQ | ⚠️ | Motion-sensor hub. gale has no sensors → sensor count ≤0 → no cell. |
| `0x0134`/`0x0135` | PCHG_COUNT / PCHG | cros_peripheral_charger | REQ | ❌ | Peripheral (stylus) charger. Absent; `PCHG_COUNT` probe fails → no cell. |

\* GET_FEATURES itself is best-effort (a failure yields an all-zero bitmap), but
its *result* gates almost every consumer cell.

**One-line conclusion.** Of the whole `cros_ec` consumer stack, exactly **one**
purpose-built driver works on gale today — **`gpio-cros-ec`**. Everything else
is reached only through the always-present **`/dev/cros_ec` (chardev)**,
**sysfs**, and **debugfs** diagnostic interfaces, and the PD/Type-C/charger/RTC/
regulator/sensor/LED drivers never even get a device to bind to. See §5 for the
live proof and §7 for the per-driver verdicts.

---

## 2. How to read this / link legend

Each detailed entry (§6) carries up to three source links:

- **Linux** — the driver source that issues the command. Paths are under the
  extracted kernel tree
  `…/build_dir/…/linux-ipq40xx_chromium/linux-6.12.87/drivers/…` and are
  **identical to mainline Linux v6.12**; cited as `file.c:line` + function.
- **EC (impl)** — the EC-side handler. For **✅ implemented** commands this is
  the anchor in [`I2C-HOST-COMMANDS.md`](../../renode-equiv/gale-ec/I2C-HOST-COMMANDS.md),
  which itself links the ChromiumOS `platform/ec` source at the pinned factory
  rev `7c97ab0`. For **⚠️ addable** commands it is the handler file in the EC
  tree that would need its `CONFIG` enabled.
- **EC (renode-equiv)** — the reconstruction on branch
  `gale-ec-renode-equivalence`: `gale-ec/board/gale/*` for board-specific
  behaviour, and the byte-level reference in `gale-ec/I2C-HOST-COMMANDS.md`.
  Because the reconstruction is proven functionally equivalent to the shipped
  firmware, its command surface is identical to gale's (same 31; same ⚠️/❌).

The wire format (request/response structs, byte-level examples, `EC_RES_*`
error semantics) for the **31 implemented** commands is **not repeated here** —
it is already exhaustively documented in `I2C-HOST-COMMANDS.md`. This document
gives the *driver-usage* layer and provides the wire format inline only for the
**gap** (⚠️/❌) commands, which that reference does not cover.

---

## 3. Transport & error model (recap)

- **Bus/addr:** `/dev/i2c-1` (78b8000.i2c QUP), 7-bit `0x1e`. Protocol **v3
  only** — the STM32F0 slave rejects `< EC_COMMAND_PROTOCOL_3 (0xda)`.
- **Framing:** request `[0xda][ec_host_request(8)][params]`; response
  `[result][packet_len][ec_host_response(8)][data]`; each 8-byte header+data
  sums to 0 (mod 256). Full byte layout: `I2C-HOST-COMMANDS.md` §Transport.
- **Result codes** (`result` u16, 0 = success): `1 INVALID_COMMAND`,
  `2 ERROR`, `3 INVALID_PARAM`, `4 ACCESS_DENIED`, `6 INVALID_VERSION`,
  `7 INVALID_CHECKSUM`, `8 IN_PROGRESS`, `9 UNAVAILABLE`, `10 TIMEOUT`,
  `11 OVERFLOW`, `12 INVALID_HEADER`. An unregistered command →
  `1 INVALID_COMMAND`; a bad `command_version` → `6 INVALID_VERSION`, both
  *before* the handler runs.
- **How Linux maps them** — `cros_ec_map_error()` via the `cros_ec_error_map[]`
  table (`cros_ec_proto.c:19‑40`): **`INVALID_COMMAND` (1) → `-EOPNOTSUPP`
  (‑95)**, `ERROR` (2) → `-EIO`, `INVALID_PARAM` (3) → `-EINVAL`,
  `ACCESS_DENIED` (4) → `-EACCES`, `INVALID_VERSION` (6) → `-ENOPROTOOPT`,
  `IN_PROGRESS` (8) → `-EINPROGRESS`, `UNAVAILABLE` (9) → `-ENODATA`,
  `TIMEOUT` (10) → `-ETIMEDOUT`, `BUSY` (16) → `-EBUSY`. So **an unimplemented
  command (`INVALID_COMMAND`) surfaces to userspace/driver as `-EOPNOTSUPP`
  (‑95)** — exactly the `-95` in the live `sysfs` `version` "Board version"
  line — while calling an implemented command at an unsupported *version* gives
  the distinct `-ENOPROTOOPT`.

---

## 4. What the EC returns decides everything: two data points

The entire behaviour of the stack on gale falls out of two values the EC
reports at bring-up:

1. **`GET_PROTOCOL_INFO` → v3** makes the base `cros_ec` device register (it is
   the *only* fatal bring-up command; see §6.1).
2. **`GET_FEATURES` → `flags = {0x00004002, 0x00000000}`** — i.e. only
   `EC_FEATURE_FLASH` (bit 1) and `EC_FEATURE_GPIO` (bit 14) — makes GPIO the
   sole feature-gated consumer that instantiates.

### Feature bits relevant to the consumer drivers

| Bit | `EC_FEATURE_*` | Gates MFD cell | Set on gale? |
|--:|---|---|:--:|
| 1 | FLASH | (flash ops via chardev) | ✅ |
| 4 | LIGHTBAR | cros-ec-lightbar | ❌ |
| 5 | LED | cros-ec-led | ❌ |
| 6 | MOTION_SENSE | cros-ec-sensorhub | ❌ |
| 14 | **GPIO** | **cros-ec-gpio** | ✅ |
| 16 | CHARGER | cros-charge-control | ❌ |
| 19 | HANG_DETECT | cros-ec-wdt | ❌ |
| 22 | USB_PD | cros-usbpd-charger, cros-usbpd-logger, cros-usbpd-notify | ❌ |
| 23 | USB_MUX | (typec mux) | ❌ |
| 27 | RTC | cros-ec-rtc | ❌ |
| 35 | CEC | cros-ec-cec | ❌ |
| 41 | TYPEC_CMD | (modern typec) | ❌ |

`0x00004002 = BIT(1) | BIT(14)`. Everything gated on any other bit is dead on
gale. (`cros_ec_check_features()` indexes `flags[f/32] & BIT(f%32)`,
`cros_ec_proto.c:931`.)

---

## 5. Live ground truth (puck12, image `…060236`, 2026-07-18)

Enumerating the platform devices the MFD actually created and which drivers
bound — the empirical validation of §4 and §6:

```
platform devices:   cros-ec-dev.2  cros-ec-chardev.4  cros-ec-debugfs.5
                    cros-ec-gpio.3  cros-ec-hwmon.6   cros-ec-sysfs.7
bound drivers:      cros-ec-chardev ✔  cros-ec-debugfs ✔  cros-ec-gpio ✔  cros-ec-sysfs ✔
NO device / unbound: cros-ec-typec, cros-ec-rtc, cros-ec-sensorhub, cros-ec-regulator,
                     cros-ec-vbc, cros-ec-led, cros-ec-lightbar, cros-ec-pchg,
                     cros-ec-i2c-tunnel, cros-usbpd-charger/logger/notify, extcon-usbc-cros-ec
/dev/cros_ec:        crw------- 10,257     dmesg: "cros-ec-i2c 1-001e: Chrome EC device registered"
cat /sys/class/chromeos/cros_ec/version:
   RO/RW version: gale_v1.1.5337-0115719   Chip: stm / stm32f07x
   Board version: XFER / EC ERROR -95 / 1        ← GET_BOARD_VERSION unimplemented
```

Exactly the five cells §4 predicts (`gpio` + the four unconditional
`chardev`/`debugfs`/`hwmon`/`sysfs`) get a device; every feature/DT-gated
consumer gets nothing. `cros-ec-hwmon` is created unconditionally but we build
no hwmon driver (`SENSORS_CROS_EC=n`), so it sits idle and harmless.

---

## 6. Command details

Grouped by the role each command plays: §6.1 base bring-up, §6.2 the
always-available diagnostic surface, §6.3 the one working consumer (GPIO), §6.4
the USB-PD/Type-C/charger family, §6.5 the remaining function drivers. Byte-level
request/response for the ✅ implemented commands lives in
[`I2C-HOST-COMMANDS.md`](../../renode-equiv/gale-ec/I2C-HOST-COMMANDS.md); this section adds
the driver-usage and gap detail.

### 6.1 Base transport & bring-up

The base `cros_ec` device is brought up by
`cros_ec_i2c_probe()` → `cros_ec_register()` → `cros_ec_query_all()`. The command
sequence and its fatality:

| Order | Command | Issued by (Linux) | Req? | gale outcome |
|--:|---|---|:--:|---|
| 1 | **GET_PROTOCOL_INFO** `0x0b` (EC idx 0) | `cros_ec_get_proto_info()` `cros_ec_proto.c:305/308`, via `cros_ec_query_all:502` | **FATAL** | v3 → succeeds; sets max req/resp = 128. If it *and* the v2 HELLO fallback fail, `cros_ec_register` `cros_ec.c:207` bails and the device never appears. |
| 2 | GET_PROTOCOL_INFO `0x400b` (PD idx 1) | same fn, via `:504` | opt | `INVALID_COMMAND`, discarded → `max_passthru=0` → no `cros_pd` device (`cros_ec.c:237`). |
| — | HELLO `0x01` (v2 fallback) | `…_legacy()` `cros_ec_proto.c:382/389` via `:507` | (fatal on v2 path) | **Not reached** — step 1 already succeeded. |
| 3 | GET_CMD_VERSIONS `0x08` for `0x67` | `…_version_mask()` `:458/465` via `:537` | opt | `0x67` unknown → mask 0 → **`mkbp_event_supported=0`**, no IRQ notifier. |
| 4 | GET_CMD_VERSIONS `0x08` for `0xa9` | same, via `:547` | opt | unknown → `host_sleep_v1=false`. |
| 5 | HOST_EVENT_GET_WAKE_MASK `0x8d` | `…_wake_mask()` `:265/268` via `:551` | opt | `-EOPNOTSUPP` → hardcoded default mask, silent. |
| 6 | HOST_SLEEP_EVENT `0xa9` | `cros_ec_sleep_event()` `cros_ec.c:133/135` via `:270` | opt | "fails harmlessly", `dev_dbg` only. |

**Why gale comes up:** only command 1 is fatal, and gale answers it at v3.
Every other bring-up command is explicitly best-effort. That is exactly why
dmesg reads `cros-ec-i2c 1-001e: Chrome EC device registered` (`cros_ec.c:287`).

- **Linux:** `drivers/platform/chrome/cros_ec.c`, `cros_ec_proto.c`, `cros_ec_i2c.c`.
- **EC (impl):** GET_PROTOCOL_INFO → [`I2C-HOST-COMMANDS.md`](../../renode-equiv/gale-ec/I2C-HOST-COMMANDS.md) (`0x0b`); handler `chip/stm32/i2c-stm32f0.c` `i2c_get_protocol_info`. GET_CMD_VERSIONS `0x08`, HELLO `0x01` → same reference. GET_NEXT_EVENT `0x67`, HOST_SLEEP_EVENT `0xa9`, wake-mask `0x8d` are **⚠️ addable** (MKBP/host-event code present in `common/mkbp_event.c`, `common/host_event_commands.c` but not compiled).
- **EC (renode-equiv):** `gale-ec/I2C-HOST-COMMANDS.md` (same 31); MKBP/host-event absent from the built set identically.

### 6.2 Always-available diagnostic surface (chardev / sysfs / debugfs)

These three MFD cells are registered **unconditionally** (`cros_ec_dev.c:157‑162`,
added at `:313`), so they bind on gale regardless of features. They expose the
EC's implemented commands to userspace; there is no auto-probing consumer.

`/dev/cros_ec` (**cros-ec-chardev**) is a raw passthrough — `ioctl(CROS_EC_DEV_IOCXCMD)`
sends any command verbatim, so **every one of gale's 31 commands is reachable
here** (this is how `ectool`-style tooling and the raw `ec_probe` work), and the
EC's own `INVALID_COMMAND` is faithfully relayed for the rest. Note the separate
`IOCRDMEM` ioctl (direct memory-map read) returns **`-ENOTTY`** on gale: it is
guarded by `if (!ec_dev->cmd_readmem)` (`cros_ec_chardev.c:325`), and
`cmd_readmem` is set **only by the LPC transport** — the I2C transport leaves it
NULL. So although gale *implements* `READ_MEMMAP` (0x07), there is no driver path
to it. The MKBP `read()` event path is inert (gale raises no MKBP events).

sysfs (**cros-ec-sysfs**, `drivers/platform/chrome/cros_ec_sysfs.c`) and debugfs
(**cros-ec-debugfs**) map fixed attributes to commands:

| Interface entry | Command | gale | Notes |
|---|---|:--:|---|
| sysfs `version` | GET_VERSION `0x02` + GET_BUILD_INFO `0x04` + GET_CHIP_INFO `0x05` + GET_BOARD_VERSION `0x06` | ✅ (board ⚠️) | Works except the board-version line → `EC ERROR -95` (`0x06` not compiled). |
| sysfs `flashinfo` | FLASH_INFO `0x10` | ✅ | EC flash geometry. |
| sysfs `reboot` | REBOOT_EC `0xd2` | ✅ | Write `ro`/`rw`/`cold` to reboot the EC. |
| sysfs `kb_wake_angle` | MOTION_SENSE_CMD `0x2b` | — | **Attribute hidden on gale** — `cros_ec_ctrl_visible()` drops it unless the sensorhub set `has_kb_wake_angle` (`cros_ec_sysfs.c:320`); no sensorhub → file never created → command never issued. |
| debugfs `console` (`console_log`) | GET_CMD_VERSIONS `0x08` → CONSOLE_SNAPSHOT `0x97` + CONSOLE_READ `0x98` (v1) | ✅ | Streams the EC UART ring buffer (background poll). |
| debugfs `panicinfo` | GET_PANIC_INFO `0xd3` | ✅* | Saved panic block. *File created only if real panic data exists; normally absent. |
| debugfs `pdinfo` | USB_PD_CONTROL `0x101` (v1) only | ✅ | Per-port PD role/state; port count found by looping `0x101` until the first error (does **not** use `USB_PD_PORTS`). |
| debugfs `uptime` | GET_UPTIME_INFO `0x121` | ❌ | Probe capability-check (`debugfs.c:266`) sees `INVALID_COMMAND` and **suppresses the file** (not created) rather than erroring. |

- **Linux:** `cros_ec_chardev.c`, `cros_ec_sysfs.c`, `cros_ec_debugfs.c`.
- **EC (impl):** each command's anchor in `I2C-HOST-COMMANDS.md`.

### 6.3 GPIO — `gpio-cros-ec` (the one working consumer)

`gpio-cros-ec` binds to the **cros-ec-gpio** MFD cell, which is created because
gale advertises `EC_FEATURE_GPIO` (bit 14). No DT node is needed — probe borrows
the EC's fwnode and asks the EC for the GPIO count/names. It uses only
`EC_CMD_GPIO_GET`/`GPIO_SET`, at two versions:

| Command | # | Ver | Req? | Linux | gale |
|---|--:|:--:|:--:|---|:--:|
| GPIO_GET — `GET_COUNT`/`GET_INFO` subcmds | `0x93` | **v1** | **REQ (probe)** | `cros_ec_gpio_ngpios()` `:154`, `cros_ec_gpio_init_names()` `:126`; probe checks `:175`,`:187` | ✅ |
| GPIO_GET — by name | `0x93` | v0 | runtime | `cros_ec_gpio_get()` `:60` | ✅ |
| GPIO_SET | `0x92` | v0 | runtime | `cros_ec_gpio_set()` `:41` (WP-gated on the EC) | ✅ |

The subtlety: probe uses **GPIO_GET version 1** (the `subcmd`-based
`GET_COUNT`/`GET_INFO` interface), not merely command `0x93`. gale's EC supports
this — its `GPIO_GET` version mask is **`0x3` (v0+v1)** and its v1 handler
implements the `COUNT`/`INFO` subcommands (see
[`I2C-HOST-COMMANDS.md`](../../renode-equiv/gale-ec/I2C-HOST-COMMANDS.md) `0x93`). **Confirmed
live:** `cros-ec-gpio.3.auto` is *bound* on puck12 (§5), which only happens if
`probe()` returned 0.

- **EC (impl):** [`I2C-HOST-COMMANDS.md`](../../renode-equiv/gale-ec/I2C-HOST-COMMANDS.md) (`0x92`/`0x93`); handler `common/gpio_commands.c`.
- **EC (renode-equiv):** `gale-ec/board/gale/gpio.inc` (named-GPIO table) + upstream `common/gpio_commands.c`.
- **Verdict:** ✅ **the one purpose-built consumer driver fully functional on
  gale** — enumerates and reads/drives the EC's named GPIOs. (`GPIO_SET` is
  additionally gated by the EC's write-protect state; a locked EC returns
  `ACCESS_DENIED`, non-fatal.)

### 6.4 USB-PD / Type-C / charger family (none instantiate on gale)

Four of these bind to **feature-gated MFD cells** (`EC_FEATURE_USB_PD`, bit 22 —
**clear** on gale) and two bind only to **DT/ACPI nodes gale doesn't declare**.
So on a stock gale none of them get a device (§5 confirms: all unbound). The
per-command detail is what would happen *if* each were reached — and why the
underlying commands are missing.

**cros-ec-typec** (`cros_ec_typec.c`) — binds to a `google,cros-ec-typec` DT /
`GOOG0014` ACPI node (not an MFD cell). Probe-fatal set: `GET_CMD_VERSIONS`
(0x08, `:1156`), `USB_PD_PORTS` (0x102, `:1248`), `USB_PD_CONTROL` (0x101,
`:1119`) — **all three are in gale's 31**. It does **not** require v2: it takes
the max available version (`:1161‑1166`) and on gale would settle at `pd_ctrl_ver
= 1`. v2 is demanded only at *runtime* for DP/TBT altmode, non-fatally (`"PD_CTRL
version too old"`, `:462`). Runtime commands `TYPEC_STATUS` (0x133),
`TYPEC_CONTROL` (0x132), `USB_PD_MUX_INFO` (0x11a), `USB_PD_MUX_ACK` (0x603) are
all **❌ absent** from the 2016 EC — but they are gated behind
`typec_cmd_supported`/`needs_mux_ack` (false, since no feature bits) or
warned-and-swallowed. **Verdict:** never instantiates (no DT node); *if* forced
on it would **attach at v1 and run mux-blind**, not fail probe.

**extcon-usbc-cros-ec** (`extcon-usbc-cros-ec.c`) — binds to a
`google,extcon-usbc-cros-ec` DT node (not an MFD cell). Probe calls
`extcon_cros_ec_detect_cable(force=true)` (`:469`), which calls
**`USB_PD_POWER_INFO` (0x103)** and treats failure as **fatal**:
```c
259  power_type = cros_ec_usb_get_power_type(info);
260  if (power_type < 0) {
261      dev_err(dev, "failed getting power type err = %d\n",
262              power_type);
263      return power_type;                 // → probe aborts at :470‑472
264  }
```
`USB_PD_POWER_INFO` is **⚠️ addable** (handler `common/charge_manager.c`, gated
`CONFIG_CHARGE_MANAGER` — absent). **Verdict:** never instantiates (no DT node);
*if* forced on it would **fail probe** (0x103 → `-EOPNOTSUPP` → `power_type<0`).

**cros-usbpd-charger** (`cros_usbpd-charger.c`), **cros-usbpd-logger**
(`cros_usbpd_logger.c`), **cros-usbpd-notify** (`cros_usbpd_notify.c`) — the
first two share the `EC_FEATURE_USB_PD`-gated cell array (`cros_ec_dev.c:89‑92`);
notify's OF variant is gated on `OF && EC_FEATURE_USB_PD` (`:282`). All three
have **command-free probes** (they only register notifiers / queue delayed work),
so their *runtime* commands — `USB_PD_POWER_INFO` (0x103) / `CHARGE_STATE` (0xa0)
for the charger, `PD_GET_LOG_ENTRY` (0x115) for the logger, `PD_HOST_EVENT_STATUS`
(0x104) for notify — never fire on gale. **Verdict:** all three **never
instantiate** (USB_PD feature clear); if forced on they attach but their reads
harmlessly return `-EOPNOTSUPP`. (`0xa0`/`0x103`/`0x104`/`0x115` are all ⚠️
addable — handlers `common/charge_state_v2.c`, `charge_manager.c`,
`host_command_pd.c`, `pd_log.c`.)

**cros-ec-pchg** (`cros_peripheral_charger.c`) — MFD gates this cell on a live
`EC_CMD_PCHG_COUNT` (0x0134) probe (`cros_ec_dev.c:298`). gale returns
`INVALID_COMMAND` → cell not added. `PCHG`/`PCHG_COUNT` are **❌ absent** from the
2016 EC. **Verdict:** never instantiates; if forced on, `probe()` fails at
`cros_pchg_port_count()` (`:286`, `-ENODEV`).

### 6.5 Non-instantiating function drivers (rtc / regulator / i2c-tunnel / led / lightbar / sensorhub / vbc)

| Driver | Instantiation gate | Probe-fatal cmd | gale | Verdict on gale |
|---|---|---|:--:|---|
| **rtc-cros-ec** | MFD cell, `EC_FEATURE_RTC` (bit 27) | `RTC_GET_VALUE` 0x44 (`rtc-cros-ec.c:334`) | ⚠️ | never instantiates (bit clear); if forced, probe fails on 0x44 |
| **cros-ec-regulator** | DT `google,cros-ec-regulator` | `REGULATOR_GET_INFO` 0x12c (`:187`) | ❌ | never instantiates (no DT node); if forced, probe fails on 0x12c |
| **i2c-cros-ec-tunnel** | DT `google,cros-ec-i2c-tunnel` | *(none — probe is command-free)* | ⚠️ | never instantiates (no DT node); if forced, probe OK but **every transfer** → `I2C_PASSTHRU` 0x9e `-EOPNOTSUPP` |
| **leds-cros_ec** | MFD cell, `EC_FEATURE_LED` (bit 5) | `LED_CONTROL` 0x29 query (`:186`, `-EOPNOTSUPP`→`-ENODEV`) | ⚠️ | never instantiates (bit clear); if forced, probe fails `-ENODEV` |
| **cros_ec_lightbar** | MFD cell, `EC_FEATURE_LIGHTBAR` (bit 4) or DMI "Link" | `LIGHTBAR_CMD` 0x28 version query (`:549`) | ⚠️ | never instantiates (bit clear, ARM/no DMI); if forced, probe `-ENODEV` |
| **cros_ec_sensorhub** | MFD cell, `cros_ec_get_sensor_count() > 0` | `MOTION_SENSE_CMD` 0x2b (gates the count) | ⚠️ | never instantiates (count ≤0: 0x2b unimpl **and** I2C sets no `cmd_readmem` fallback) |
| **cros_ec_vbc** | DT prop `google,has-vbc-nvram` on the EC node | *(none — probe is command-free)* | ✅ | never instantiates on gale (**no DT prop**), **but would fully work if added** — `VBNV_CONTEXT` (0x17) v1 is implemented; probe issues nothing |

The two rows worth noting: **i2c-cros-ec-tunnel** and **cros_ec_vbc** have
command-free probes, so they can't fail on a missing command — their fate is
purely whether a DT node/property exists. `cros_ec_vbc` is the one currently-dead
driver whose command gale *does* implement: declaring
`google,has-vbc-nvram` on the EC's DT node would light it up (read/write the
vboot NV context from userspace via sysfs). Every other driver here needs a
command gale doesn't compile.

- **Linux:** `rtc-cros-ec.c`, `cros-ec-regulator.c`, `i2c-cros-ec-tunnel.c`, `leds-cros_ec.c`, `cros_ec_lightbar.c`, `cros_ec_sensorhub.c`, `cros_ec_vbc.c`.
- **EC (impl / addable):** `VBNV_CONTEXT` → [`I2C-HOST-COMMANDS.md`](../../renode-equiv/gale-ec/I2C-HOST-COMMANDS.md) (`0x17`, ✅). ⚠️ addable handlers: `RTC_*` (needs `CONFIG_HOSTCMD_RTC`), `LED_CONTROL` → `common/led_common.c`, `LIGHTBAR_CMD` → `common/lightbar.c`, `MOTION_SENSE_CMD` → `common/motion_sense.c`, `I2C_PASSTHRU` → `common/i2c.c`. ❌ absent: `REGULATOR_*` (no handler in the 2016 tree).

---

## 7. Per-driver verdict rollup

The practical answer to "which `cros_ec` drivers do anything on gale":

| Driver | Instantiates on gale? | Works? | Blocking gap |
|---|:--:|:--:|---|
| cros-ec-chardev (`/dev/cros_ec`) | ✅ (unconditional) | ✅ | — (raw passthrough to all 31 cmds) |
| cros-ec-sysfs | ✅ (unconditional) | ✅ | `version`/`flashinfo`/`reboot` work; board-version line shows `-95` |
| cros-ec-debugfs | ✅ (unconditional) | ✅ | `console_log`/`pdinfo` work; `uptime` absent, `panicinfo` only on panic |
| cros-ec-hwmon | ✅ (unconditional) | n/a | no hwmon driver built (`SENSORS_CROS_EC=n`); cell idle |
| **gpio-cros-ec** | ✅ (`EC_FEATURE_GPIO`) | ✅ | — (**only working purpose-built consumer**) |
| cros-ec-vbc | ❌ (no DT prop) | (would ✅) | needs `google,has-vbc-nvram` in DT — command implemented |
| cros-ec-typec | ❌ (no DT/ACPI node) | (would run degraded) | no mux/status cmds; needs a modern EC for full function |
| extcon-usbc-cros-ec | ❌ (no DT node) | (would fail probe) | `USB_PD_POWER_INFO` 0x103 |
| cros-usbpd-charger / logger / notify | ❌ (`EC_FEATURE_USB_PD` clear) | ✗ | USB_PD feature bit + 0x103/0xa0/0x115/0x104 |
| cros-ec-rtc | ❌ (`EC_FEATURE_RTC` clear) | ✗ | RTC feature + `RTC_*` |
| cros-ec-regulator | ❌ (no DT node) | ✗ | `REGULATOR_*` (absent) |
| i2c-cros-ec-tunnel | ❌ (no DT node) | ✗ | `I2C_PASSTHRU` |
| leds-cros_ec | ❌ (`EC_FEATURE_LED` clear) | ✗ | LED feature + `LED_CONTROL` |
| cros_ec_lightbar | ❌ (`EC_FEATURE_LIGHTBAR` clear) | ✗ | no lightbar hardware |
| cros_ec_sensorhub | ❌ (sensor count 0) | ✗ | no motion sensors |
| cros-ec-pchg | ❌ (`PCHG_COUNT` fails) | ✗ | `PCHG` (absent) |

## 8. What it would take to light up more (gap analysis)

The three tiers from §1 map directly to effort:

- **Free (DT only):** **`cros_ec_vbc`** — add `google,has-vbc-nvram` to the EC's
  device-tree node. The command (`VBNV_CONTEXT` 0x17) is already implemented; no
  EC change needed.
- **⚠️ EC config + reflash (command exists in gale's 2016 tree):** the
  power-monitoring goal — `USB_PD_POWER_INFO` (0x103) and `CHARGE_STATE` (0xa0) —
  needs `CONFIG_CHARGE_MANAGER` + board glue in the EC RW image, then either the
  `cros-usbpd-charger` path (also needs the EC to advertise `EC_FEATURE_USB_PD`)
  or a direct chardev query. `RTC_*`, `LED_CONTROL`, `I2C_PASSTHRU`,
  `GET_NEXT_EVENT`/MKBP, `GET_BOARD_VERSION` are likewise addable via their
  `CONFIG_*`. This is the realistic route since we already rebuild + reflash the
  EC ([`gale-ec/`](../../renode-equiv/gale-ec/) renode-equivalence build; RO is byte-identical,
  RW is what we flash).
- **❌ Needs a newer EC (command absent from the 2016 codebase):**
  `TYPEC_STATUS/CONTROL`, `USB_PD_MUX_INFO`, `REGULATOR_*`, `PCHG`,
  `GET_PD_PORT_CAPS`, `USB_PD_MUX_ACK`, `GET_UPTIME_INFO`. Reaching the modern
  `cros-ec-typec` mux/altmode stack or the EC regulator/peripheral-charger
  drivers would require forward-porting gale to a much newer `platform/ec`
  branch — a far larger effort than a config flip (see the R146 rebase spike in
  the renode-equivalence docs).

For the immediate **power-consumption** objective, the smallest step is a custom
RW host command returning gale's four ADC channels (VBUS/current/CC1/CC2 — the
values behind the EC console `gale vbus`/`gale cc`) read via `/dev/cros_ec`,
rather than trying to satisfy the full `cros-usbpd-charger` contract. `ectool
usbpdpower` (`USB_PD_POWER_INFO` 0x103) is the standard tool for this and is the
smallest ⚠️-tier addition; the ADC-channel command is the zero-dependency
alternative.
