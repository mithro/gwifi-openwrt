# gale EC ↔ Linux — per-driver I2C host-command reference

This document is the **driver-centric** reference for the in-band AP↔EC channel
on the Google WiFi puck ("gale"): **every Linux driver that can talk to a
ChromeOS EC**, grouped by driver, with **every I2C host command each driver
issues**, the **complete wire structure** of each command, whether the command
is **required or optional** for that driver, and whether gale's shipped EC
firmware **implements** it. It is self-contained: transport framing, error
codes and all structures are given inline with links to their definitions.

**System under discussion.** The gale AP (IPQ4019, OpenWrt, Linux **6.12.87**)
reaches its EC (STM32F072, ChromiumOS EC firmware `gale_v1.1.5337-0115719`,
2016) over **I2C bus 1** (`/dev/i2c-1`, QUP `78b8000.i2c`) at 7-bit address
**`0x1e`**, speaking EC host-command **protocol v3 only**. The kernel binds it
via the DT node
[`cros_ec: ec@1e { compatible = "google,cros-ec-i2c"; reg = <0x1e>; }`](https://github.com/mithro/gwifi-openwrt/blob/wisp-netboot-install/openwrt-patches/0002-ipq40xx-chromium-google_wifi-add-cros-ec-i2c-node.patch)
and the image ships the full `cros_ec` module family
([kmod-cros-ec](https://github.com/mithro/gwifi-openwrt/blob/wisp-netboot-install/openwrt-patches/0004-add-kmod-cros-ec-package.patch)).

> **Why 0x1e and not 0x3C?** The EC firmware sets
> [`CONFIG_HOSTCMD_I2C_SLAVE_ADDR 0x3C`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/board.h#L104)
> and loads it into `STM32_I2C_OAR1`. OAR1 keeps the 7-bit address in bits
> [7:1], so `0x3C >> 1 = 0x1E` is the true 7-bit address — matching the live
> kernel binding (`cros-ec-i2c 1-001e: Chrome EC device registered`).

## 0. Sources, link conventions and section template

### 0.1 The five pinned source trees

Every code reference in this document is a hyperlink into one of five pinned
trees:

| Tag | Tree | Base URL |
|---|---|---|
| **[Linux]** | Linux **v6.12.87** (what the gale image runs; identical to the local build tree) | `https://elixir.bootlin.com/linux/v6.12.87/source/…#L<line>` |
| **[Linux-7.1]** | Linux **v7.1.1** (current mainline at time of writing, 2026; used for "what changed since 6.12"; facts verified against a local v7.1.1 tree) | `https://github.com/torvalds/linux/blob/v7.1.1/…#L<line>` |
| **[EC-2016]** | ChromiumOS `platform/ec` @ [`7c97ab0`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb) (branch `firmware-gale-8281.B` — **the codebase gale's shipped EC was built from**) | `https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab0…/…#<line>` |
| **[EC-main]** | ChromiumOS `platform/ec` @ [`37850ff4`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1) (**current upstream** main, 2026-06-04). This one tree hosts **two build systems**: the **legacy Makefile build** (a.k.a. CrosEC/ECOS — the lineage gale's 2016 firmware belongs to) and the **Zephyr build** (`zephyr/`, where all current EC development happens). The per-module *EC firmware support* tables report both. | `https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4…/…#<line>` |
| **[renode]** | The gale EC **reconstruction** on branch [`gale-ec-renode-equivalence`](https://github.com/mithro/gwifi-openwrt/tree/gale-ec-renode-equivalence/gale-ec) (open-source `board/gale/` overlay + pinned [EC-2016] base; proven functionally equivalent to the shipped firmware) | `https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/…#L<line>` |

Because the [renode] reconstruction pins the same [EC-2016] base, **gale's
host-command surface is identical in both** — command handlers live in the
pinned upstream files, and only `board/gale/*` (GPIO table, ADC channels, PD
policy) is reconstruction-local.

### 0.2 Status legend

**gale status legend**, used for every command below:

- ✅ **implemented** — one of the **31 commands** gale's EC answers today.
- ⚠️ **addable** — the command exists in the [EC-2016] codebase but is not
  compiled into gale (gated by a `CONFIG_*` gale doesn't set). Enabling it =
  config + board glue + EC RW reflash.
- ❌ **absent** — the command does not exist in the [EC-2016] codebase at all
  (invented later; present in [EC-main]). Needs a forward-ported EC, not a
  config flip.

### 0.3 Per-module section template

Every Linux-driver ("module") section in §[§4](#4-always-available-interfaces-unconditional-mfd-cells)–8 is self-contained and follows
the same layout, so any section can be read on its own:

1. **Title** — links to the module's source file in [Linux].
2. **Functionality** — what the module provides (device nodes, sysfs paths,
   kernel services), how it instantiates, and the outcome on gale.
3. **Host commands used** — one table row per command the module issues:
   version used, purpose, exact call site, whether failure is probe-fatal,
   and gale's EC status.
4. **Command reference** — full wire structure of each command (verbatim
   structs with linked definitions, request/response layout, error cases).
   Commands owned by another section are summarised and linked instead of
   duplicated.
5. **EC firmware support** — one row per command across the three EC
   generations: gale's shipped 2016 firmware, the [EC-main] **legacy
   (Makefile) build**, and the [EC-main] **Zephyr build** (with the gating
   `CONFIG_*`/Kconfig symbol linked for each).
6. **Linux driver history** — kernel releases that introduced/changed the
   module, each with the mainline commit linked.

## 1. The wire protocol (standalone reference)

### 1.1 I2C framing

The transport is implemented on the Linux side by
[`cros_ec_pkt_xfer_i2c()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L52)
and on the EC side by the STM32F0 I2C-slave ISR in
[`chip/stm32/i2c-stm32f0.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c).

**Request** (I2C write to 0x1e):

```
[0xda] [struct ec_host_request (8 bytes)] [request data (data_len bytes)]
```

The leading byte is
[`EC_COMMAND_PROTOCOL_3` = 0xda](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L739);
the 2016 STM32 slave **rejects anything below it** with
`EC_RES_INVALID_HEADER` — protocol v3 is the only option on gale.

**Response** (I2C read from 0x1e):

```
[result (1)] [packet_length (1)] [struct ec_host_response (8 bytes)] [response data]
```

### 1.2 Packet headers

[`struct ec_host_request`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L755)
([`EC_HOST_REQUEST_VERSION` = 3](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L741)):

```c
struct ec_host_request {
	uint8_t struct_version;   /* = 3 */
	uint8_t checksum;         /* whole request sums to 0 mod 256 */
	uint16_t command;         /* EC_CMD_* (little-endian) */
	uint8_t command_version;  /* 0-based; must be in the command's version mask */
	uint8_t reserved;         /* = 0 */
	uint16_t data_len;        /* bytes of request data that follow */
} __ec_align4;
```

[`struct ec_host_response`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L775)
([`EC_HOST_RESPONSE_VERSION` = 3](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L764)):

```c
struct ec_host_response {
	uint8_t struct_version;   /* = 3 */
	uint8_t checksum;         /* whole response sums to 0 mod 256 */
	uint16_t result;          /* enum ec_status (0 = success) */
	uint16_t data_len;        /* bytes of response data that follow */
	uint16_t reserved;        /* = 0 */
} __ec_align4;
```

All multi-byte fields are little-endian on the wire (both ends are LE). Each
side's checksum makes header+data sum to 0 (mod 256). gale caps packets at
**128 bytes** each way (its `GET_PROTOCOL_INFO` reports
`max_request_packet_size = max_response_packet_size = 128`, from
[`I2C_MAX_HOST_PACKET_SIZE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c)).

Command versions: a command supporting version *N* has bit *N* set in its
version mask
([`EC_VER_MASK(v)`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L31));
the dispatcher rejects a `command_version` outside the mask with
`EC_RES_INVALID_VERSION` **before** the handler runs, and an unknown `command`
with `EC_RES_INVALID_COMMAND`
([EC-2016 `common/host_command.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c)).

### 1.3 Result codes and how Linux maps them to errno

[`enum ec_status`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L466)
→ mapped by
[`cros_ec_error_map[]`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L19)
in `cros_ec_map_error()`:

| # | `EC_RES_*` | Meaning | Linux errno |
|--:|---|---|---|
| 0 | `SUCCESS` | OK | 0 |
| 1 | `INVALID_COMMAND` | command not registered on the EC | **`-EOPNOTSUPP` (-95)** |
| 2 | `ERROR` | generic failure | `-EIO` |
| 3 | `INVALID_PARAM` | bad parameter in request | `-EINVAL` |
| 4 | `ACCESS_DENIED` | locked / not permitted | `-EACCES` |
| 5 | `INVALID_RESPONSE` | — | `-EPROTO` |
| 6 | `INVALID_VERSION` | `command_version` not in mask | `-ENOPROTOOPT` |
| 7 | `INVALID_CHECKSUM` | request checksum wrong | `-EBADMSG` |
| 8 | `IN_PROGRESS` | accepted, still running | `-EINPROGRESS` |
| 9 | `UNAVAILABLE` | no response available | `-ENODATA` |
| 10 | `TIMEOUT` | timeout during processing | `-ETIMEDOUT` |
| 11 | `OVERFLOW` | table/data overflow | `-EOVERFLOW` |
| 12 | `INVALID_HEADER` | bad request header (e.g. not v3) | `-EBADR` |
| 13 | `REQUEST_TRUNCATED` | request cut short | `-EBADR` |
| 14 | `RESPONSE_TOO_BIG` | response exceeds buffer | `-EFBIG` |
| 15 | `BUS_ERROR` | comms bus error | `-EFAULT` |
| 16 | `BUSY` | up but busy, retry | `-EBUSY` |

The practical consequence used throughout this document: **calling a command
gale's EC doesn't implement returns `EC_RES_INVALID_COMMAND`, which every
driver sees as `-EOPNOTSUPP` (-95)** — e.g. the live
`/sys/class/chromeos/cros_ec/version` shows `Board version: XFER / EC ERROR
-95 / 1` because `EC_CMD_GET_BOARD_VERSION` isn't compiled on gale. Calling an
implemented command at an unsupported *version* gives the distinct
`-ENOPROTOOPT`.

### 1.4 What gale's EC implements — the 31 commands

Extracted from the shipped firmware's `__hcmds` host-command table (each entry
registered via `DECLARE_HOST_COMMAND`; independently verified in the
[renode reconstruction](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/I2C-HOST-COMMANDS.md)).
"Ver mask": bit *N* set ⇒ version *N* accepted.

| Cmd | Name | Ver mask | Cmd | Name | Ver mask |
|--:|---|--:|--:|---|--:|
| `0x00` | PROTO_VERSION | 0x1 | `0x15` | FLASH_PROTECT | 0x3 |
| `0x01` | HELLO | 0x1 | `0x16` | FLASH_REGION_INFO | 0x2 |
| `0x02` | GET_VERSION | 0x1 | `0x17` | VBNV_CONTEXT | 0x3 |
| `0x03` | READ_TEST | 0x1 | `0x2a` | VBOOT_HASH | 0x1 |
| `0x04` | GET_BUILD_INFO | 0x1 | `0x92` | GPIO_SET | 0x1 |
| `0x05` | GET_CHIP_INFO | 0x1 | `0x93` | GPIO_GET | 0x3 |
| `0x07` | READ_MEMMAP | 0x1 | `0x97` | CONSOLE_SNAPSHOT | 0x1 |
| `0x08` | GET_CMD_VERSIONS | 0x3 | `0x98` | CONSOLE_READ | 0x3 |
| `0x0a` | TEST_PROTOCOL | 0x1 | `0xb6` | ENTERING_MODE | 0x1 |
| `0x0b` | GET_PROTOCOL_INFO | 0x1 | `0xd2` | REBOOT_EC | 0x1 |
| `0x0d` | GET_FEATURES | 0x1 | `0xd3` | GET_PANIC_INFO | 0x1 |
| `0x10` | FLASH_INFO | 0x3 | `0x101` | USB_PD_CONTROL | 0x3 |
| `0x11` | FLASH_READ | 0x1 | `0x102` | USB_PD_PORTS | 0x1 |
| `0x12` | FLASH_WRITE | 0x3 | `0x110` | USB_PD_FW_UPDATE | 0x1 |
| `0x13` | FLASH_ERASE | 0x1 | `0x111` | USB_PD_RW_HASH_ENTRY | 0x1 |
| — | | | `0x112` | USB_PD_DEV_INFO | 0x1 |

Every other command number → `EC_RES_INVALID_COMMAND` → `-EOPNOTSUPP`.

**gale's `GET_FEATURES` bitmap** (the single value that decides which consumer
drivers instantiate, [§3.2](#32-core-bring-up-cros_ec--cros_ec_proto)):
`flags = {0x00004002, 0x00000000}` =
[`EC_FEATURE_FLASH`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1195) (bit 1) |
[`EC_FEATURE_GPIO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1233) (bit 14),
and nothing else — no
[`EC_FEATURE_USB_PD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1252) (22),
[`EC_FEATURE_RTC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1262) (27),
[`EC_FEATURE_MOTION_SENSE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1214) (6),
[`EC_FEATURE_KEYB`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1216) (7), etc.

## 2. Driver inventory — every Linux driver that can talk to the EC

Complete inventory of Linux 6.12.87 sources that speak the EC host-command
protocol (enumerated by grepping the tree for `cros_ec_cmd`/`cros_ec_command`/
`cros_ec_device` users). **Image** = shipped in the gale OpenWrt image
(kmod-cros-ec). **Active** = gets a bound device on a running gale puck
(verified live on puck12, image `gale-openwrt-20260718060236-g6f0edc8`).

### 2.1 Transports (produce the `cros_ec_device`)

| Driver | Source | Bound via | Image | Active on gale |
|---|---|---|:--:|:--:|
| cros_ec_i2c | [`cros_ec_i2c.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c) | DT [`google,cros-ec-i2c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L348) | ✅ | ✅ **the gale transport** (`ec@1e` on i2c-1) |
| cros_ec_spi | [`cros_ec_spi.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_spi.c) | DT [`google,cros-ec-spi`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_spi.c#L815) | ✅ | idle (no DT node) |
| cros_ec_lpc | [`cros_ec_lpc.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lpc.c) | ACPI `GOOG0004` / DMI | ❌ | n/a (x86 LPC; the only transport that sets [`cmd_readmem`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lpc.c#L577)) |
| cros_ec_rpmsg | [`cros_ec_rpmsg.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_rpmsg.c) | DT [`google,cros-ec-rpmsg`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_rpmsg.c#L290) | ❌ | n/a (MediaTek SCP) |
| cros_ec_ishtp | [`cros_ec_ishtp.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_ishtp.c) | ISHTP GUID | ❌ | n/a (Intel ISH) |
| cros_ec_uart | [`cros_ec_uart.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_uart.c) | DT [`google,cros-ec-uart`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_uart.c#L331) / ACPI `GOOG0019` | ❌ | n/a (serdev/FPMCU) |

### 2.2 Core (always present once a transport binds)

| Driver | Source | Role | Image | Active |
|---|---|---|:--:|:--:|
| cros_ec (core) | [`cros_ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c) | bring-up, suspend/resume, MKBP IRQ plumbing | ✅ | ✅ |
| cros_ec_proto | [`cros_ec_proto.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c) | packet building, retries, errno mapping, helpers (built-in, `CONFIG_CROS_EC_PROTO=y`) | ✅ | ✅ |
| cros_ec_dev (MFD) | [`cros_ec_dev.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c) | creates every consumer cell below | ✅ | ✅ |

### 2.3 MFD cells created unconditionally

| Driver | Source | Image | Active | Notes |
|---|---|:--:|:--:|---|
| cros-ec-chardev | [`cros_ec_chardev.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c) | ✅ | ✅ | `/dev/cros_ec` raw passthrough |
| cros-ec-sysfs | [`cros_ec_sysfs.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c) | ✅ | ✅ | `version`/`flashinfo`/`reboot` attributes |
| cros-ec-debugfs | [`cros_ec_debugfs.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c) | ✅ | ✅ | `console_log`/`pdinfo`/`panicinfo`/`uptime` |
| cros-ec-hwmon | [`cros_ec_hwmon.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c) | ❌ (`SENSORS_CROS_EC=n`) | cell created, no driver | temp/fan via memmap |

### 2.4 MFD cells gated on the EC (feature bit / probe)

Gate = what `cros_ec_dev` checks before creating the cell ([§3.3](#33-mfd-cros_ec_dev--the-gatekeeper)). gale's
feature bitmap is `0x00004002` (FLASH+GPIO), so **only the GPIO cell exists**.

| Driver | Source | Gate | Image | Active |
|---|---|---|:--:|:--:|
| **gpio-cros-ec** | [`gpio-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c) | [`EC_FEATURE_GPIO`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L121) (14) | ✅ | ✅ **works** |
| rtc-cros-ec | [`rtc-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c) | [`EC_FEATURE_RTC`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L126) (27) | ✅ | ❌ |
| leds-cros_ec | [`leds-cros_ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c) | [`EC_FEATURE_LED`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L141) (5) | ✅ | ❌ |
| cros-ec-cec | [`cros-ec-cec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c) | [`EC_FEATURE_CEC`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L116) (35) | ❌ | ❌ |
| cros_ec_wdt | [`cros_ec_wdt.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c) | [`EC_FEATURE_HANG_DETECT`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L136) (19) | ❌ | ❌ |
| cros_kbd_led_backlight | [`cros_kbd_led_backlight.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_kbd_led_backlight.c) | [`EC_FEATURE_PWM_KEYB`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L146) (3), also DT/ACPI | ❌ | ❌ |
| cros_charge-control | [`cros_charge-control.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_charge-control.c) | [`EC_FEATURE_CHARGER`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L151) (16) | ❌ | ❌ |
| cros_usbpd-charger | [`cros_usbpd-charger.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c) | [`EC_FEATURE_USB_PD`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L131) (22) | ✅ | ❌ |
| cros_usbpd_logger | [`cros_usbpd_logger.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c) | same cell array ([`:91`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L91)) | ✅ | ❌ |
| cros_usbpd_notify | [`cros_usbpd_notify.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_notify.c) | OF && [`EC_FEATURE_USB_PD`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L282); ACPI `GOOG0003` | ✅ | ❌ |
| cros_peripheral_charger | [`cros_peripheral_charger.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c) | live [`EC_CMD_PCHG_COUNT` probe](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L298) | ✅ | ❌ |
| cros_ec_lightbar | [`cros_ec_lightbar.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lightbar.c) | [`EC_FEATURE_LIGHTBAR` ∨ DMI "Link"](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L267) | ✅ | ❌ |
| cros-ec-sensorhub | [`cros_ec_sensorhub.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub.c) | [`cros_ec_get_sensor_count() > 0`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L237) | ✅ | ❌ |
| cros-ec-vbc | [`cros_ec_vbc.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c) | DT prop [`google,has-vbc-nvram`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L322) | ✅ | ❌ (prop not set) |

### 2.5 Bound directly via DT / ACPI (not MFD cells)

| Driver | Source | Bound via | Image | Active |
|---|---|---|:--:|:--:|
| cros-ec-typec (+ vdm) | [`cros_ec_typec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c), [`cros_typec_vdm.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c) | DT [`google,cros-ec-typec`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1206) / ACPI `GOOG0014` | ✅ | ❌ (no node) |
| extcon-usbc-cros-ec | [`extcon-usbc-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c) | DT [`google,extcon-usbc-cros-ec`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L519) | ✅ | ❌ (no node) |
| cros-ec-regulator | [`cros-ec-regulator.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c) | DT [`google,cros-ec-regulator`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L208) | ✅ | ❌ (no node) |
| i2c-cros-ec-tunnel | [`i2c-cros-ec-tunnel.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c) | DT [`google,cros-ec-i2c-tunnel`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c#L296) | ✅ | ❌ (no node) |
| pwm-cros-ec | [`pwm-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c) | DT [`google,cros-ec-pwm(-type)`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L269) | ❌ | ❌ |
| cros_ec_keyb | [`cros_ec_keyb.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c) | DT [`google,cros-ec-keyb(-switches)`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L767) / ACPI `GOOG0007` | ❌ | ❌ |
| cros_ec_mkbp_proximity | [`cros_ec_mkbp_proximity.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c) | DT [`google,cros-ec-mkbp-proximity`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c#L251) | ❌ | ❌ |
| cros_ec_codec | [`cros_ec_codec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c) | DT [`google,cros-ec-codec`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L1040) / ACPI `GOOG0013` | ❌ | ❌ |
| cros_typec_switch | [`cros_typec_switch.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c) | ACPI [`GOOG001A`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L308) only | ❌ | n/a |
| hid-google-hammer (cbas) | [`hid-google-hammer.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c) | DT [`google,cros-cbas`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c#L280) / ACPI `GOOG000B` | ❌ | ❌ |

### 2.6 Sensor-stack children (instantiated by cros-ec-sensorhub)

All created by the sensorhub's EC sensor enumeration
([`cros_ec_sensorhub.c:92-110`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub.c#L92));
none can exist on gale (no sensorhub cell). All share
[`cros_ec_sensors_core.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c).

| Driver | Source | Platform name |
|---|---|---|
| cros_ec_sensors | [`cros_ec_sensors.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors.c) | `cros-ec-accel` / `cros-ec-gyro` / `cros-ec-mag` |
| cros_ec_lid_angle | [`cros_ec_lid_angle.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_lid_angle.c) | `cros-ec-lid-angle` |
| cros_ec_light_prox | [`cros_ec_light_prox.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/light/cros_ec_light_prox.c) | `cros-ec-light` / `cros-ec-prox` |
| cros_ec_baro | [`cros_ec_baro.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/pressure/cros_ec_baro.c) | `cros-ec-baro` |
| cros_ec_accel_legacy | [`cros_ec_accel_legacy.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/accel/cros_ec_accel_legacy.c) | `cros-ec-accel-legacy` (LPC-only path) |

### 2.7 Added after 6.12 (current mainline = v7.1.1)

New EC consumers (verified in a local v7.1.1 tree; nothing from §[§2.1](#21-transports-produce-the-cros_ec_device)–2.6 was
removed or renamed):

| Driver | Since | Binds via | Purpose / commands |
|---|---|---|---|
| [`cros_typec_altmode.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_typec_altmode.c) | v6.14 | not a separate module — [linked into `cros-ec-typec.o`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/Makefile#L21) | AP-driven DP/TBT altmode ops split out of cros-ec-typec; enter/exit send [`EC_CMD_TYPEC_CONTROL`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_typec_altmode.c#L74), DP/TBT VDMs emulated AP-side; enabled when the EC sets [`EC_FEATURE_TYPEC_REQUIRE_AP_MODE_ENTRY`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_typec.c#L1377) |
| [`cros_ec_ucsi.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/usb/typec/ucsi/cros_ec_ucsi.c) | v6.14 | MFD cell [`cros_ec_ucsi`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/mfd/cros_ec_dev.c#L135) gated on [`EC_FEATURE_UCSI_PPM`](https://github.com/torvalds/linux/blob/v7.1.1/include/linux/platform_data/cros_ec_commands.h#L1346) (bit 54) / ACPI [`GOOG0021`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/usb/typec/ucsi/cros_ec_ucsi.c#L360) / DT [`google,cros-ec-ucsi`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/usb/typec/ucsi/cros_ec_ucsi.c#L366) | UCSI OPM↔PPM transport over two **new commands** [`EC_CMD_UCSI_PPM_SET`](https://github.com/torvalds/linux/blob/v7.1.1/include/linux/platform_data/cros_ec_commands.h#L6198) (0x140) / [`EC_CMD_UCSI_PPM_GET`](https://github.com/torvalds/linux/blob/v7.1.1/include/linux/platform_data/cros_ec_commands.h#L6206) (0x141); on UCSI ECs the MFD [suppresses the legacy usbpd-charger/logger cells](https://github.com/torvalds/linux/blob/v7.1.1/drivers/mfd/cros_ec_dev.c#L267) |
| [`cros_ec_activity.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/iio/common/cros_ec_sensors/cros_ec_activity.c) | post-6.12 | platform device `cros-ec-activity`, [registered by the sensorhub since its introduction](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_sensorhub.c#L110) | IIO driver for body-detection / significant-motion events via [`MOTIONSENSE_CMD_{LIST,GET,SET}_ACTIVITY`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/iio/common/cros_ec_sensors/cros_ec_activity.c#L68) subcommands of `EC_CMD_MOTION_SENSE_CMD` |
| [`chromeos_of_hw_prober.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/chromeos_of_hw_prober.c) | v6.13 | [root DT machine compatible](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/chromeos_of_hw_prober.c#L93) | i2c-of-prober for second-source touchscreen/trackpad parts — **issues no EC commands** |

Behaviour changes in existing drivers worth knowing when reading current
code (all verified in the v7.1.1 tree):

- [`cros_ec_proto.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_proto.c) gained [`cros_ec_rwsig_continue()`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_proto.c#L292) (sends [`EC_CMD_RWSIG_ACTION`](https://github.com/torvalds/linux/blob/v7.1.1/include/linux/platform_data/cros_ec_commands.h#L5560) to jump the EC to RW; `INVALID_COMMAND` treated as "not supported/already RW"), and [`cros_ec.c` now calls it during registration](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec.c#L235) (non-fatal — harmless on a gale-class EC).
- [`cros_ec_chardev.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_chardev.c#L354) gained a `CROS_EC_DEV_IOCEVENTMASK` ioctl to filter which MKBP events reach a reader.
- [`cros_ec_sysfs.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_sysfs.c#L309) gained `usbpdmuxinfo` (loops `USB_PD_PORTS` + `USB_PD_MUX_INFO`) and `ap_mode_entry` attributes.
- [`cros_ec_hwmon.c`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/hwmon/cros_ec_hwmon.c#L486) grew PWM fan control (`PWM_GET/SET_FAN_DUTY` + `THERMAL_AUTO_FAN_CTRL` + `THERMAL_GET_THRESHOLD`) on top of the 6.12 read-only memmap interface; the [memmap thermal-version probe gate is unchanged](https://github.com/torvalds/linux/blob/v7.1.1/drivers/hwmon/cros_ec_hwmon.c#L555).
- Unchanged where it matters to gale: extcon's fatal `power_type < 0` bail ([v7.1.1 `:259`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/extcon/extcon-usbc-cros-ec.c#L259)), gpio-cros-ec's hard `GPIO_GET` v1 probe requirement ([`:145`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/gpio/gpio-cros-ec.c#L145)), debugfs `pdinfo`'s `USB_PD_CONTROL`-v1 port loop ([`:219`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_debugfs.c#L219)), and cros-ec-typec's acceptance of `USB_PD_CONTROL` v1 ([`:1294`](https://github.com/torvalds/linux/blob/v7.1.1/drivers/platform/chrome/cros_ec_typec.c#L1294)).

None of the new consumers are relevant to gale's 2016 EC (no UCSI/Type-C
commands), but they matter when reading current upstream driver code: the
modern PD stack assumes commands (`TYPEC_*`, `UCSI_PPM_*`) that post-date
gale's firmware by ~5–9 years.

### 2.8 Master map — driver → commands (with gale outcome)

Every command name links to its `EC_CMD_*` definition in the [Linux] header;
every driver links to its detailed section.

| Driver | Commands issued | On gale |
|---|---|---|
| [cros_ec core + proto (§3.2)](#32-core-bring-up-cros_ec--cros_ec_proto) | [`GET_PROTOCOL_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1132), [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065), [`HELLO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L949), [`GET_NEXT_EVENT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3355), [`HOST_EVENT_GET_WAKE_MASK`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3613), [`HOST_SLEEP_EVENT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4244) (+ [`GET_COMMS_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1100) on IN_PROGRESS, [`READ_MEMMAP`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1052) helper) | ✅ registers — only `GET_PROTOCOL_INFO` is fatal |
| [cros_ec_dev MFD (§3.3)](#33-mfd-cros_ec_dev--the-gatekeeper) | [`GET_FEATURES`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1182), [`MOTION_SENSE_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2235), [`PCHG_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5622) (gating probes) | ✅ creates 5 cells |
| [cros-ec-chardev (§4.1)](#41-cros_ec_chardevc--devcros_ec-raw-host-command-access) | [`GET_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L968) + **any** (userspace passthrough) | ✅ works |
| [cros-ec-sysfs (§4.2)](#42-cros_ec_sysfsc--sysclasschromeoscros_ec-attributes) | [`GET_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L968), [`GET_BUILD_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1016), [`GET_CHIP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1019), [`GET_BOARD_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1034), [`FLASH_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1339), [`REBOOT_EC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4890) ([`MOTION_SENSE_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2235) hidden) | ✅ works (board-version line errors) |
| [cros-ec-debugfs (§4.3)](#43-cros_ec_debugfsc--syskerneldebugcros_ec) | [`GET_PANIC_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4921), [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065), [`CONSOLE_SNAPSHOT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3906), [`CONSOLE_READ`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3920), [`GET_UPTIME_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5519), [`USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020) | ✅ works (`uptime` suppressed) |
| [gpio-cros-ec (§5)](#5-gpio-cros-ecc--ec-gpio-controller-the-one-gated-consumer-that-fully-works-on-gale) | [`GPIO_GET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761) (v0+v1), [`GPIO_SET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3753) | ✅ **fully works** |
| [cros-ec-typec (§6.1)](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc) | [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065), [`USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113), [`USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020), [`USB_PD_MUX_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385), [`TYPEC_DISCOVERY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5840), [`TYPEC_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5867), [`TYPEC_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5932), [`TYPEC_VDM_RESPONSE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6049), [`USB_PD_MUX_ACK`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6448) | ❌ no DT node (would attach degraded) |
| [extcon-usbc-cros-ec (§6.2)](#62-extcon-usbc-cros-ecc--usb-c-cable-state-extcon) | [`USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113), [`USB_PD_POWER_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122), [`USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020), [`USB_PD_MUX_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385) | ❌ no DT node (would fail probe on `USB_PD_POWER_INFO`) |
| [cros-usbpd-charger (§6.3)](#63-cros_usbpd-chargerc--usb-pd-power_supply-provider) | [`USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113), [`CHARGE_PORT_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5171), [`USB_PD_POWER_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122), [`USB_PD_DISCOVERY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5217), [`EXTERNAL_POWER_LIMIT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4189) | ❌ no USB_PD feature |
| [cros-usbpd-logger (§6.4)](#64-cros_usbpd_loggerc--pd-event-log) | [`PD_GET_LOG_ENTRY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5243) | ❌ no USB_PD feature |
| [cros-usbpd-notify (§6.5)](#65-cros_usbpd_notifyc--pd-event-fan-out) | [`PD_HOST_EVENT_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5008) | ❌ no USB_PD feature |
| [cros_peripheral_charger (§6.6)](#66-cros_peripheral_chargerc--qistylus-peripheral-charger) | [`PCHG_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5622), [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065), [`PCHG`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5633) | ❌ `PCHG_COUNT` probe fails |
| [cros-ec-vbc (§7.1)](#71-cros_ec_vbcc--vboot-nv-context) | [`VBNV_CONTEXT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1661) | ❌ DT prop absent (**would fully work**) |
| [rtc-cros-ec (§7.2)](#72-rtc-cros-ecc--ec-real-time-clock) | [`RTC_GET_VALUE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2893), [`RTC_GET_ALARM`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2894), [`RTC_SET_VALUE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2897), [`RTC_SET_ALARM`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2898) | ❌ no RTC feature |
| [cros-ec-regulator (§7.3)](#73-cros-ec-regulatorc--ec-controlled-voltage-regulators) | [`REGULATOR_GET_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5754), [`REGULATOR_ENABLE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5775), [`REGULATOR_IS_ENABLED`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5787), [`REGULATOR_SET_VOLTAGE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5805), [`REGULATOR_GET_VOLTAGE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5819) | ❌ no DT node |
| [i2c-cros-ec-tunnel (§7.4)](#74-i2c-cros-ec-tunnelc--i2c-bus-tunnelled-through-the-ec) | [`I2C_PASSTHRU`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4010) | ❌ no DT node |
| [leds-cros_ec (§7.5)](#75-leds-cros_ecc--ec-controlled-leds) | [`LED_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2110) | ❌ no LED feature |
| [cros_ec_lightbar (§7.6)](#76-cros_ec_lightbarc--google-pixel-2013-lightbar) | [`LIGHTBAR_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1803) | ❌ no LIGHTBAR feature |
| [cros-ec-sensorhub + ring + IIO (§7.7)](#77-cros_ec_sensorhubc--cros_ec_sensorhub_ringc-and-the-iio-sensor-family) | [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065), [`MOTION_SENSE_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2235) (many subcommands) | ❌ sensor count 0 |
| [cros_ec_keyb (§8.1)](#81-cros_ec_keybc--matrix-keyboard--buttons--switches) | [`MKBP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166) | ❌ not shipped / no node |
| [cros_ec_mkbp_proximity (§8.2)](#82-cros_ec_mkbp_proximityc--mkbp-proximity-sensor) | [`MKBP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166) | ❌ not shipped / no node |
| [hid-google-hammer cbas (§8.3)](#83-hid-google-hammerc--detachable-base-hid-hammer--base-attached-switch) | [`MKBP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166) | ❌ not shipped / no node |
| [cros-ec-cec (§8.4)](#84-cros-ec-cecc--hdmi-cec) | [`CEC_PORT_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4611), [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065), [`CEC_WRITE_MSG`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4525), [`CEC_READ_MSG`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4548), [`CEC_SET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4569) | ❌ not shipped / no CEC feature |
| [pwm-cros-ec (§8.5)](#85-pwm-cros-ecc--ec-pwm-channels) | [`PWM_GET_DUTY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1785), [`PWM_SET_DUTY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1765) | ❌ not shipped / no node |
| [cros_kbd_led_backlight (§8.6)](#86-cros_kbd_led_backlightc--keyboard-backlight) | [`PWM_GET_KEYBOARD_BACKLIGHT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1736), [`PWM_SET_KEYBOARD_BACKLIGHT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1745) | ❌ not shipped / no feature |
| [cros_ec_codec (§8.7)](#87-cros_ec_codecc--ec-audio-codec-dmici2swov) | [`EC_CODEC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4642), [`EC_CODEC_DMIC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4706), [`EC_CODEC_I2S_RX`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4762), [`EC_CODEC_WOV`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4824) | ❌ not shipped / no node |
| [cros_ec_wdt (§8.8)](#88-cros_ec_wdtc--ec-watchdog) | [`HANG_DETECT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4044) | ❌ not shipped / no feature |
| [cros_charge-control (§8.9)](#89-cros_charge-controlc--charge-behaviour--battery-sustainer) | [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065), [`CHARGE_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3845) | ❌ not shipped / no feature |
| [cros_typec_switch (§8.10)](#810-cros_typec_switchc--type-c-mode-switch--retimer-control) | [`TYPEC_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5867), [`TYPEC_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5932) | ❌ ACPI-only |
| [cros_ec_hwmon (§8.11)](#811-cros_ec_hwmonc--temperature--fan-monitoring) | [`READ_MEMMAP`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1052), [`TEMP_SENSOR_GET_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3573) | ❌ not shipped (cell exists) |

---

## 3. Core stack

### 3.1 Transport: `cros_ec_i2c` — and the EC side of the wire

- **Linux:** [`cros_ec_i2c_probe()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L289)
  binds the DT node, installs
  [`ec_dev->pkt_xfer = cros_ec_pkt_xfer_i2c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L304)
  ([framing](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L52), [§1.1](#11-i2c-framing))
  and calls
  [`cros_ec_register()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L180).
  The transport issues no commands of its own; it frames all of them. It does
  **not** provide `cmd_readmem` (only [EC-2016-era LPC does](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lpc.c#L577)) —
  relevant to [§4.1](#41-cros_ec_chardevc--devcros_ec-raw-host-command-access)/[§8.11](#811-cros_ec_hwmonc--temperature--fan-monitoring).
- **EC-2016 (the gale side):** the STM32F0 I2C-slave ISR
  [`i2c_event_handler()`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#272)
  collects the write, and on STOP
  [`i2c_process_command()`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#219)
  [rejects anything below `EC_COMMAND_PROTOCOL_3`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#245)
  and dispatches via
  [`host_packet_receive()`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#251);
  the reply goes out through
  [`i2c_send_response_packet()`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#193).
  All of this is compiled because
  [`CONFIG_HOSTCMD_I2C_SLAVE_ADDR`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/board.h#L104)
  is set.
- **EC-main:** `chip/stm32/` **no longer exists** — `chip/` retains only the
  host emulator, so the legacy Makefile build has lost every real transport.
  Zephyr builds use the upstream Zephyr `ec_host_cmd` subsystem with
  per-transport backends (SPI/UART/SHI/eSPI — e.g.
  [`CONFIG_EC_HOST_CMD_BACKEND_SPI` in the fpmcu program](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/program/fpmcu/bloonchipper/prj.conf#56));
  [`zephyr/shim/src/host_command.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/host_command.c)
  bridges `DECLARE_HOST_COMMAND` into it. **There is no I2C backend anywhere
  in current upstream** (no `EC_HOST_CMD_BACKEND_I2C` exists) — gale's
  I2C-slave host-command transport has **no successor**; a forward-ported
  gale EC would have to write one. The wire protocol itself is unchanged — a
  modern EC still answers the exact framing in [§1.1](#11-i2c-framing).
- **STM32F072 status:** dropped from both build systems — no `stm32f0`
  anywhere under `zephyr/`, and the only STM32 target left is the STM32F412
  fingerprint MCU
  ([`zephyr/program/fpmcu`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/program/fpmcu/)).
- **renode:** the reconstruction models this transport in
  [`GaleI2c.cs`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/renode/peripherals/GaleI2c.cs)
  (slave-RX ISR sequence + AP host-command injector).

**Linux driver history** (`cros_ec_i2c.c`):

| Version | Date | Change |
|---|---|---|
| v3.10 | 2013-04 | introduced as `drivers/mfd/cros_ec_i2c.c` ([`899690094854`](https://github.com/torvalds/linux/commit/89969009485fa9e62814afaa438c12c45d7d2def)) |
| v4.2 | 2015-06 | protocol-v3 framing added — the format gale speaks ([`d365407079d3`](https://github.com/torvalds/linux/commit/d365407079d33106f76bd486a863de05eb5ae95d)) |
| v4.19 | 2018 | moved to `drivers/platform/chrome/` ([`d00a8741fd8f`](https://github.com/torvalds/linux/commit/d00a8741fd8fab2dc82f1c44d4111a337d505e60)) |
| v6.14 | 2024-12 | registration now jumps the EC to RW first (RWSIG; harmless on gale) ([`5ffa0dbfdc9f`](https://github.com/torvalds/linux/commit/5ffa0dbfdc9fc05acae02d5b0dc766ec778569ac)) |

### 3.2 Core bring-up: `cros_ec` + `cros_ec_proto`

[`cros_ec_register()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L180)
→ [`cros_ec_query_all()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L495)
issues, in order:

| # | Command | Issued at | Fatal? | gale outcome |
|--:|---|---|:--:|---|
| 1 | `0x0b` GET_PROTOCOL_INFO (EC) | [`cros_ec_proto.c:305`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L305)/[`:308`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L308) via [`:502`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L502) | **YES** | v3 → OK; 128-byte caps |
| 2 | `0x400b` GET_PROTOCOL_INFO (PD idx 1, [`EC_CMD_PASSTHRU_OFFSET(1)`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6514)) | via [`:504`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L504) | no | INVALID_COMMAND → no [`cros_pd`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L237) device |
| — | `0x01` HELLO (v2 fallback) | [`:382`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L382)/[`:389`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L389) via [`:507`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L507) | (fatal on v2 path) | not reached (step 1 succeeded) |
| 3 | `0x08` GET_CMD_VERSIONS for `0x67` | [`:458`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L458)/[`:465`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L465) via [`:537`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L537) | no | `0x67` unknown → [`mkbp_event_supported = 0`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L538) → no MKBP thread ([`cros_ec.c:275`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L275)) |
| 4 | `0x08` GET_CMD_VERSIONS for `0xa9` | via [`:547`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L547) | no | `host_sleep_v1 = false` |
| 5 | `0x8d` HOST_EVENT_GET_WAKE_MASK | [`:265`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L265)/[`:268`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L268) via [`:551`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L551) | no | `-EOPNOTSUPP` → [default mask, silent](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L562) |
| 6 | `0xa9` HOST_SLEEP_EVENT (clear) | [`cros_ec.c:133`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L133) via [`:270`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L270) | no | "[fails harmlessly](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L271)" |

Only step 1 can prevent registration — which is why gale logs
[`Chrome EC device registered`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L287).
On `EC_RES_IN_PROGRESS` the proto layer polls `0x09` GET_COMMS_STATUS
([`cros_ec_wait_until_complete`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L138),
up to [50 retries](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L17)) —
never triggered by gale, whose EC (no
[`CONFIG_HOST_COMMAND_STATUS`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#607))
never returns IN_PROGRESS.

#### 0x0b EC_CMD_GET_PROTOCOL_INFO — protocol negotiation · gale ✅ (v0)

The **one command an EC must implement** for Linux to talk to it at all.

- Defined: [`cros_ec_commands.h:1132`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1132)
- Issued by: [`cros_ec_get_proto_info()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L305) — **REQUIRED**; total failure (incl. the HELLO fallback) aborts [`cros_ec_register` at `cros_ec.c:207`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L207)
- EC-2016 handler: [`i2c_get_protocol_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#615) (v0), inside [`#ifdef CONFIG_HOSTCMD_I2C_SLAVE_ADDR`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#597) — **on** for gale
- EC-main: **the legacy build has no provider left at all** (the chip
  transports that carried this handler were deleted with `chip/`); Zephyr
  builds get one handler per transport —
  [`zephyr/shim/src/espi.c:545`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/espi.c#545),
  [`zephyr/shim/chip/npcx/shi.c:144`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/chip/npcx/shi.c#144),
  [`zephyr/shim/chip/it8xxx2/shi.c:75`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/chip/it8xxx2/shi.c#75) —
  or from the upstream Zephyr `ec_host_cmd` subsystem on `CONFIG_EC_HOST_CMD`
  builds

Request: none. Response
[`struct ec_response_get_protocol_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1146) (12 B):

```c
struct ec_response_get_protocol_info {
	/* Fields which exist if at least protocol version 3 supported */
	uint32_t protocol_versions;         /* bit N = protocol version N; gale: 0x8 (v3 only) */
	uint16_t max_request_packet_size;   /* gale: 128 */
	uint16_t max_response_packet_size;  /* gale: 128 */
	uint32_t flags;                     /* gale: 0 (no EC_PROTOCOL_INFO_IN_PROGRESS_SUPPORTED) */
} __ec_align4;
```

Errors: always `EC_RES_SUCCESS` when implemented. gale reply:
`08 00 00 00 | 80 00 | 80 00 | 00 00 00 00`.

#### 0x08 EC_CMD_GET_CMD_VERSIONS — capability discovery · gale ✅ (v0+v1)

The stack's feature-detect primitive: core (steps 3-4 above), cros-ec-typec
([§6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc)), debugfs ([§4.3](#43-cros_ec_debugfsc--syskerneldebugcros_ec)), CEC ([§8.4](#84-cros-ec-cecc--hdmi-cec)), charge-control ([§8.9](#89-cros_charge-controlc--charge-behaviour--battery-sustainer)), sensors core
([§7.7](#77-cros_ec_sensorhubc--cros_ec_sensorhub_ringc-and-the-iio-sensor-family)) all use it to pick command versions.

- Defined: [`cros_ec_commands.h:1065`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065)
- Issued by: [`cros_ec_get_host_command_version_mask()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L458) and per-driver callers — optional everywhere in core, **probe-fatal** in cros-ec-typec/CEC/charge-control/sensors (see those sections)
- EC-2016 handler: [`host_command_get_cmd_versions`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#524) (v0|v1) — always compiled → gale ✅
- EC-main handler: [`common/host_command.c:157`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#157) (v0|v1)

Request v0 [`struct ec_params_get_cmd_versions`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1071) (1 B) /
v1 [`…_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1080) (2 B, for cmd ≥ 0x100):

```c
struct ec_params_get_cmd_versions     { uint8_t cmd;  } __ec_align1;
struct ec_params_get_cmd_versions_v1  { uint16_t cmd; } __ec_align2;
```

Response [`struct ec_response_get_cmd_versions`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1089) (4 B):

```c
struct ec_response_get_cmd_versions {
	uint32_t version_mask;  /* bit N set = version N supported (EC_VER_MASK) */
} __ec_align4;
```

Errors: `EC_RES_INVALID_PARAM` if the queried command is not registered — this
is how the kernel discovers gale lacks `0x67`/`0xa9` without ever calling them.

#### 0x01 EC_CMD_HELLO — liveness echo · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:949`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L949)
- Issued by: [`cros_ec_get_proto_info_legacy()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L382) — only if the v3 probe failed; **never reached on gale**
- EC-2016 handler: [`host_command_hello`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#451) (v0) → gale ✅
- EC-main handler: [`common/host_command.c:101`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#101)

Request [`struct ec_params_hello`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L955)
`{ uint32_t in_data; }` → response
[`struct ec_response_hello`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L963)
`{ uint32_t out_data; }` = `in_data + 0x01020304` (proves processing, not
echo). Live-validated on gale: `0xa0b0c0d0 → 0xa1b2c3d4`.

#### 0x67 EC_CMD_GET_NEXT_EVENT — MKBP event delivery · gale ⚠️ addable

The event backbone of the modern stack: keyboard, sensors FIFO, PD/typec
notifications and proximity all arrive as MKBP events fetched with this
command (typically from the EC interrupt). gale has neither the command nor an
EC→AP interrupt line.

- Defined: [`cros_ec_commands.h:3355`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3355); event types [`enum ec_mkbp_event`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3368)
- Issued by: [`get_next_event_xfer()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L694) from [`cros_ec_get_next_event()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L777), called from the EC IRQ thread ([`cros_ec.c:293`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L293)) — optional; gated off at bring-up when the version probe fails (step 3 above)
- EC-2016 handler: [`mkbp_get_next_event`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/mkbp_event.c#111) (v0), gated [`CONFIG_MKBP_EVENT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#62) → **off** on gale
- EC-main handler: [`common/mkbp_event.c:529`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/mkbp_event.c#529) (v0-v3)

Request: none. Response
[`struct ec_response_get_next_event`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3494)
(v0; [v1](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3500)/[v3](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3506) grow the data union):

```c
struct ec_response_get_next_event {
	uint8_t event_type;                    /* enum ec_mkbp_event (| EC_MKBP_HAS_MORE_EVENTS) */
	union ec_response_get_next_data data;  /* per-type payload */
} __ec_align1;
```

#### 0x8d EC_CMD_HOST_EVENT_GET_WAKE_MASK — suspend wake mask · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:3613`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3613)
- Issued by: [`cros_ec_get_host_event_wake_mask()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L265) — optional; on failure a [hardcoded default mask](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L562) is used ([silent on `-EOPNOTSUPP`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L574))
- EC-2016 handler: [`host_event_get_wake_mask`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_event_commands.c#205) (v0), gated `CONFIG_HOSTCMD_EVENTS` — gale [`#undef`s it](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/board.h#L127) → **off**
- EC-main handler: [`common/host_event_commands.c:550`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_event_commands.c#550)

Request: none. Response
[`struct ec_response_host_event_mask`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3605)
`{ uint32_t mask; }` — bitmap of host events that wake the AP.

#### 0xa9 EC_CMD_HOST_SLEEP_EVENT — S0ix/S3 sleep tracking · gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:4244`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4244); [`enum host_sleep_event`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4246)
- Issued by: [`cros_ec_sleep_event()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L133) at register/suspend/resume — optional ("[failing is not fatal](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L271)")
- EC-2016 handler: **not in the 2016 tree** (command added 2017+)
- EC-main handler: [`power/host_sleep.c:90`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/power/host_sleep.c#90) (v0|v1)

Request v0 [`struct ec_params_host_sleep_event`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4255)
`{ uint8_t sleep_event; }`; v1
[adds a suspend timeout and a transitions-count response](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4268).

#### 0x07 EC_CMD_READ_MEMMAP — shared-memory window · gale ✅ (v0)

Helper [`cros_ec_cmd_readmem()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L1066)
uses this command whenever the transport lacks a direct window (I2C/SPI do);
consumer: cros_ec_hwmon ([§8.11](#811-cros_ec_hwmonc--temperature--fan-monitoring)). Note the chardev `IOCRDMEM` ioctl does **not**
use this fallback ([§4.1](#41-cros_ec_chardevc--devcros_ec-raw-host-command-access)).

- Defined: [`cros_ec_commands.h:1052`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1052)
- EC-2016 handler: [`host_command_read_memmap`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#500) (v0), compiled [`#ifndef CONFIG_LPC`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#478) → gale ✅
- EC-main handler: [`common/host_command.c:131`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#131)

Request [`struct ec_params_read_memmap`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1059):

```c
struct ec_params_read_memmap {
	uint8_t offset;   /* EC_MEMMAP_* offset */
	uint8_t size;     /* bytes to read */
} __ec_align1;
```

Response: `size` raw bytes of the EC memory map. Errors:
`EC_RES_INVALID_PARAM` if `offset+size` exceeds the 255-byte map. (gale
implements the command, but its memory map carries none of the
battery/thermal/switch fields the consumers look for.)

### 3.3 MFD: `cros_ec_dev` — the gatekeeper

[`ec_device_probe()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L181)
decides which consumer cells exist. Gating commands:

- **`0x0d` GET_FEATURES** via [`cros_ec_check_features()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L920) (cached; bit test at [`:931`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L931)) — drives the [feature-gated cell loop `:250`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L250) (declarations [`:116-153`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L116)), the [MCU-rename loop `:207`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L207) (FP/ISH/SCP/TP identities), the [lightbar special case `:267`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L267) and the [usbpd-notify OF gate `:282`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L282).
- **`0x2b` MOTION_SENSE_CMD** via [`cros_ec_get_sensor_count()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L961) — gates the [sensorhub cell `:237`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L237) (detail [§7.7](#77-cros_ec_sensorhubc--cros_ec_sensorhub_ringc-and-the-iio-sensor-family)). The legacy fallback needs [`cmd_readmem`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L981), absent on I2C.
- **`0x134` PCHG_COUNT** live probe at [`:298`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L298) — gates the pchg cell (detail [§6.6](#66-cros_peripheral_chargerc--qistylus-peripheral-charger)).
- The four unconditional cells ([`cros_ec_platform_cells`, `:157`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L157), added [`:313`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L313)) and the [vbc DT-prop check `:322`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L322) issue no commands.

No command failure here is probe-fatal — cells are silently skipped.

#### 0x0d EC_CMD_GET_FEATURES — the feature bitmap · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:1182`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1182); bits: [`enum ec_feature_code`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1185); mask macros [`EC_FEATURE_MASK_0/1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1317)
- Issued by: [`cros_ec_get_features()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L920) — optional (failure ⇒ empty bitmap ⇒ no feature-gated cells)
- EC-2016 handler: [`host_command_get_features`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#760) (v0) — always compiled → gale ✅
- EC-main handler: [`common/host_command.c:190`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#190)

Request: none. Response
[`struct ec_response_get_features`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1320):

```c
struct ec_response_get_features {
	uint32_t flags[2];   /* flags[0] = bits 0-31, flags[1] = bits 32+ */
} __ec_align4;
```

Each bit is set only if the corresponding EC `CONFIG_*` was compiled. **gale
returns `{0x00004002, 0}`** — the single most consequential value in this
document ([§1.4](#14-what-gales-ec-implements--the-31-commands), [§2.4](#24-mfd-cells-gated-on-the-ec-feature-bit--probe)).

**Linux driver history** (core stack — `cros_ec.c` / `cros_ec_proto.c` /
`cros_ec_dev.c`):

| Version | Date | Change |
|---|---|---|
| v3.10 | 2013-04 | EC core born as `drivers/mfd/cros_ec.c` ([`4ab6174e8cdb`](https://github.com/torvalds/linux/commit/4ab6174e8cdb007cf500e484bdf454b8d14d524a)) |
| v4.1 | 2015-02 | userspace device interface (`cros_ec_dev.c`, then in platform/chrome) ([`e7c256fbfb15`](https://github.com/torvalds/linux/commit/e7c256fbfb157885d36ffcf03d981fa8b21e8fec)) |
| v4.2 | 2015-06 | protocol helpers split into `cros_ec_proto.c`; proto v3 added ([`062476f24aa7`](https://github.com/torvalds/linux/commit/062476f24aa7cf714169342cc50626fd9bbb93da), [`2c7589af3c4d`](https://github.com/torvalds/linux/commit/2c7589af3c4dee844e6a4174f2aa8996cf837604)) |
| v4.9 | 2016-08 | MKBP event support ([`6f1d912b687d`](https://github.com/torvalds/linux/commit/6f1d912b687d3d17c1731f5bda3b5d6703bce4a0)) — the mechanism gale's EC pre-dates |
| v4.10 | 2016-10 | `cros_ec_check_features()` — feature-bit gating begins ([`e4244ebddae2`](https://github.com/torvalds/linux/commit/e4244ebddae27e9200146bba897f12a3950ce722)) |
| v4.16 | 2017-12 | `cros_ec_dev` moved to `drivers/mfd/` and split ([`5e0115581bbc`](https://github.com/torvalds/linux/commit/5e0115581bbc367c7958bf5ab8c511b808558533), [`ea01a31b9058`](https://github.com/torvalds/linux/commit/ea01a31b90581a94cdeef7fda9e4522f15ef64f2)) |
| v5.4 | 2019-09 | core moved out of MFD to `drivers/platform/chrome/` ([`47f11e0b40e9`](https://github.com/torvalds/linux/commit/47f11e0b40e97f373da4efbacee0a9526c816ed5)) |
| v5.10 | 2020-08 | `EC_RES_*` → errno mapping introduced (the [§1.3](#13-result-codes-and-how-linux-maps-them-to-errno) table) ([`0d080459e813`](https://github.com/torvalds/linux/commit/0d080459e813ce8076f183cc73a4c9b64a39a4d8)) |
| v6.9 | 2024-02 | GPIO feature-gated cell added — the one that lights up on gale ([`8f49b623b934`](https://github.com/torvalds/linux/commit/8f49b623b9348e3374491df1a18ca2de285fc7da)) |
| v6.11 | 2024-06 | generic `cros_ec_cmd_readmem()` helper ([`a14a569a9918`](https://github.com/torvalds/linux/commit/a14a569a9918a0c7e340257a17dbc088bb27db72)) |
| v6.14 | 2024-12 | RWSIG "jump to RW before probing" ([`5ffa0dbfdc9f`](https://github.com/torvalds/linux/commit/5ffa0dbfdc9fc05acae02d5b0dc766ec778569ac)); UCSI cell + usbpd-cell suppression land in the MFD ([§2.7](#27-added-after-612-current-mainline--v711)) |

---

## 4. Always-available interfaces (unconditional MFD cells)

The three modules in this section are created by the MFD for **every**
registered EC — no feature bit, no DT property — and all three are shipped and
**live on gale today** (verified on puck12). They are the interfaces a gale
user actually touches.

### 4.1 [`cros_ec_chardev.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c) — `/dev/cros_ec` raw host-command access

**Functionality.** Exposes the EC to userspace as a misc device,
`/dev/cros_ec`. Its main job is the `CROS_EC_DEV_IOCXCMD` ioctl: a **raw
passthrough** that lets userspace send *any* host command (this is what
`ectool` uses, and how gale's flash/vboot/PD commands are reachable without
any dedicated kernel driver). It also offers a legacy `read()` that returns
the version string, and an MKBP-event stream. Instantiated as unconditional
MFD cell `cros-ec-chardev`
([cell array `cros_ec_dev.c:157`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L157));
[`cros_ec_chardev_probe()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L378)
issues no EC command, so it always attaches. **On gale: ✅ present and fully
functional** — all 31 implemented commands work through the passthrough;
unimplemented ones relay `EC_RES_INVALID_COMMAND` to the caller.

**Host commands used:**

| Entry point | Command | Purpose | Call site | Failure behaviour | gale EC |
|---|---|---|---|---|:--:|
| `ioctl(CROS_EC_DEV_IOCXCMD)` | **any** (userspace-chosen) | raw passthrough | [`cros_ec_chardev_ioctl_xcmd()` `:305`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L305) | EC result relayed to caller | ✅ all 31 |
| `read()` (legacy) | [`EC_CMD_GET_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L968) (0x02) | version string | [`ec_get_version()` `:68`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L68) via [`:241`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L241) | error string returned | ✅ |
| `read()` (MKBP events) | none (consumes [`EC_CMD_GET_NEXT_EVENT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3355) events fetched by the core) | event stream | [queue `:211`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L211), [notifier `:93`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L93) | — | inert (no MKBP on gale, see [§3.2](#32-core-bring-up-cros_ec--cros_ec_proto)) |
| `ioctl(CROS_EC_DEV_IOCRDMEM)` | none — direct memory window only | memmap read | [`:325`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L325) | **`-ENOTTY`** on gale: guarded by `if (!ec_dev->cmd_readmem)`, which only the [LPC transport sets](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lpc.c#L577); it does **not** fall back to [`EC_CMD_READ_MEMMAP`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1052) (0x07) | n/a |

**Command reference:**

#### `EC_CMD_GET_VERSION` (0x02) — firmware versions · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:968`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L968); image enum [`enum ec_current_image`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L970)
- Issued by: chardev [`:68`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L68); sysfs `version` attribute [`cros_ec_sysfs.c:129`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L129) (the only sub-command whose failure [aborts that attribute `:133`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L133))
- Request: none. Response
  [`struct ec_response_get_version`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L983) (100 B):

```c
struct ec_response_get_version {
	char version_string_ro[32];   /* "gale_v1.1.5337-0115719" */
	char version_string_rw[32];
	char reserved[32];
	uint32_t current_image;       /* enum ec_current_image: 1=RO, 2=RW */
} __ec_align4;
```

- Errors: none in practice (always succeeds when implemented).
- gale answers RO & RW = `gale_v1.1.5337-0115719` (live-verified via
  `/sys/class/chromeos/cros_ec/version`).

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`GET_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L968) (0x02) | ✅ v0 — [`host_command_get_version`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1080) | ✅ v0+v1 (v1 adds `cros_fwid`) — [`system.c:1731`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1731) | ✅ always — `common/system.c` is in the baseline [`CONFIG_PLATFORM_EC` source block](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#204) |

(The passthrough itself needs no per-command EC support — it forwards
whatever userspace builds.)

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.1 | 2015-02 | ancestor: `/dev/cros_ec` chardev+ioctl born inside `cros_ec_dev.c` ([`e7c256fbfb15`](https://github.com/torvalds/linux/commit/e7c256fbfb157885d36ffcf03d981fa8b21e8fec)) |
| v5.4 | 2019-09 | split into today's standalone `cros_ec_chardev.c` ([`eda2e30c6684`](https://github.com/torvalds/linux/commit/eda2e30c6684d67288edb841c6125d48c608a242)); MKBP poll handler added ([`96a0a8073846`](https://github.com/torvalds/linux/commit/96a0a80738461d6d2421ae64ee9990b702efd2a6)) |
| v5.19 | 2022-04 | ioctls switched back to `cros_ec_cmd_xfer` (EC errors relayed, not mapped) ([`57b888ca2541`](https://github.com/torvalds/linux/commit/57b888ca2541785de2fcb90575b378921919b6c0)) |
| v6.1 | 2022-08 | ioctl memory-corruption fix ([`8a07b45fd3c2`](https://github.com/torvalds/linux/commit/8a07b45fd3c2dda24fad43639be5335a4595196a)) |
| v7.1 (current) | 2026 | new `CROS_EC_DEV_IOCEVENTMASK` ioctl for filtering MKBP events ([§2.7](#27-added-after-612-current-mainline--v711)) |

### 4.2 [`cros_ec_sysfs.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c) — `/sys/class/chromeos/cros_ec/*` attributes

**Functionality.** Provides the human-readable sysfs attributes under
`/sys/class/chromeos/cros_ec/`: `version` (RO/RW firmware strings, build
info, chip, board version), `flashinfo` (EC flash geometry), a write-only
`reboot` control, and — on sensor-equipped machines only — `kb_wake_angle`.
Instantiated as unconditional MFD cell `cros-ec-sysfs`
([cell array `cros_ec_dev.c:157`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L157));
the [probe `:331`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L331)
only creates the attribute group and issues no EC command — commands fire on
attribute access. **On gale: ✅ present and working**; the only visible defect
is the `Board version: XFER / EC ERROR -95` line inside `version` (see
`EC_CMD_GET_BOARD_VERSION` below).

**Host commands used:**

| Attribute | Command | Purpose | Call site | Failure behaviour | gale EC |
|---|---|---|---|---|:--:|
| `version` (read) | [`EC_CMD_GET_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L968) (0x02) | RO/RW version strings | [`:129`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L129) | aborts the read ([`:133`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L133)) | ✅ |
| `version` (read) | [`EC_CMD_GET_BUILD_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1016) (0x04) | build string | [`:148`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L148) | error printed inline | ✅ |
| `version` (read) | [`EC_CMD_GET_CHIP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1019) (0x05) | chip vendor/name/rev | [`:161`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L161) | error printed inline | ✅ |
| `version` (read) | [`EC_CMD_GET_BOARD_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1034) (0x06) | board revision | [`:180`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L180) | error printed inline ([`:183`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L183)) — gale's live `-95` | ⚠️ |
| `flashinfo` (read) | [`EC_CMD_FLASH_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1339) (0x10) | flash geometry | [`:214`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L214) | read fails | ✅ |
| `reboot` (write) | [`EC_CMD_REBOOT_EC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4890) (0xd2) | reboot/jump image | [`:100`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L100) | write fails | ✅ |
| `kb_wake_angle` | [`EC_CMD_MOTION_SENSE_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2235) (0x2b) | tablet wake angle | [show `:248`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L248) | attribute **hidden** on gale — [visibility gate `:320`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L320) needs the sensorhub's `has_kb_wake_angle`, so the command is never issued | n/a |

**Command reference:**

#### `EC_CMD_GET_BUILD_INFO` (0x04) · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:1016`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1016)
- Request: none. Response: raw NUL-terminated build string (no struct).
- Errors: none in practice.
- gale returns `"gale_v1.1.5337-0115719 2016-10-03 15:55:36 hywu@…"`.

#### `EC_CMD_GET_CHIP_INFO` (0x05) · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:1019`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1019)
- Request: none. Response
  [`struct ec_response_get_chip_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1027):

```c
struct ec_response_get_chip_info {
	char vendor[32];    /* gale: "stm" */
	char name[32];      /* gale: "stm32f07x" */
	char revision[32];
} __ec_align4;
```

#### `EC_CMD_GET_BOARD_VERSION` (0x06) · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:1034`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1034)
- Request: none. Response
  [`struct ec_response_board_version`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1040)
  `{ uint16_t board_version; }`.
- On gale: not compiled (`EC_RES_INVALID_COMMAND` → `-EOPNOTSUPP`). This is
  the source of the live `-95` in the sysfs `version` output — the one place
  a stock gale user sees an unimplemented command today.

#### `EC_CMD_FLASH_INFO` (0x10) · gale ✅ (v0+v1)

- Defined: [`cros_ec_commands.h:1339`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1339)
- Request: none. Response v0
  [`struct ec_response_flash_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1354) /
  v1 [`struct ec_response_flash_info_1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1405):

```c
struct ec_response_flash_info_1 {
	uint32_t flash_size;         /* gale: 0x20000 (128 KiB) */
	uint32_t write_block_size;   /* gale: 2 */
	uint32_t erase_block_size;   /* gale: 0x800 (2 KiB) */
	uint32_t protect_block_size; /* gale: 0x1000 (4 KiB) */
	/* Version 1 adds: */
	uint32_t write_ideal_size;
	uint32_t flags;              /* gale: 0 (erases to 1, not EC_FLASH_INFO_ERASE_TO_0) */
} __ec_align4;
```

- The sysfs attribute uses v0 only. gale's five other flash commands
  ([`FLASH_READ`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1458) 0x11,
  [`FLASH_WRITE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1471) 0x12,
  [`FLASH_ERASE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1489) 0x13,
  [`FLASH_PROTECT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1548) 0x15,
  [`FLASH_REGION_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1614) 0x16)
  have **no kernel consumer** — they are reachable via the chardev
  passthrough ([§4.1](#41-cros_ec_chardevc--devcros_ec-raw-host-command-access)),
  which is how EC RW flashing from userspace works.

#### `EC_CMD_REBOOT_EC` (0xd2) · gale ✅ (v0) *(destructive)*

- Defined: [`cros_ec_commands.h:4890`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4890); subcommands [`enum ec_reboot_cmd`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4893); flags [`EC_REBOOT_FLAG_ON_AP_SHUTDOWN`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4907)
- Request [`struct ec_params_reboot_ec`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4910):

```c
struct ec_params_reboot_ec {
	uint8_t cmd;    /* enum ec_reboot_cmd: 0=CANCEL 1=JUMP_RO 2=JUMP_RW 4=COLD 5=DISABLE_JUMP 6=HIBERNATE */
	uint8_t flags;  /* EC_REBOOT_FLAG_* */
} __ec_align1;
```

- Response: none (the EC pre-sends success before a non-returning reboot).
- Errors: `EC_RES_INVALID_PARAM` for subcommands not compiled in (on gale,
  `HIBERNATE`).

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`GET_BUILD_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1016) (0x04) | ✅ v0 — [`host_command_build_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1091) | ✅ v0 — [`system.c:1771`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1771) | ✅ always — baseline [`CONFIG_PLATFORM_EC` block](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#204) |
| [`GET_CHIP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1019) (0x05) | ✅ v0 — [`host_command_get_chip_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1107) | ✅ v0 — [`system.c:1787`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1787) | ✅ always — baseline [`CONFIG_PLATFORM_EC` block](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#204) |
| [`GET_BOARD_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1034) (0x06) | ⚠️ off — [`host_command_get_board_version`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1122) gated [`CONFIG_BOARD_VERSION`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1111) | ✅ — [`system.c:1807`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1807) | ✅ always — baseline [`CONFIG_PLATFORM_EC` block](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#204) |
| [`FLASH_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1339) (0x10) | ✅ v0+v1 — [`flash_command_get_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#781) | ✅ v0-v2 — [`flash.c:1598`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/flash.c#1598) | ✅ — [`CONFIG_PLATFORM_EC_FLASH_CROS`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig#476) (selected by the `cros_flash` drivers), via [`CMakeLists.txt:381`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#381) |
| [`REBOOT_EC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4890) (0xd2) | ✅ v0 — [`host_command_reboot`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1202) | ✅ v0 — [`system.c:1871`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1871) | ✅ always — baseline [`CONFIG_PLATFORM_EC` block](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#204) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.1 | 2015-02 | attributes introduced ([`71af4b52cc22`](https://github.com/torvalds/linux/commit/71af4b52cc22a8d0f7b66a51427a804741a045b6)) |
| v4.17 | 2018-04 | `kb_wake_angle` added ([`c1d1e91aff3d`](https://github.com/torvalds/linux/commit/c1d1e91aff3d1183d6b16a282c2575e3e006cee4)) |
| v5.1 | 2019-02 | split into its own driver/MFD cell ([`6fd7f2bbd442`](https://github.com/torvalds/linux/commit/6fd7f2bbd4422e7635bc771cd1ec440378158cb1)) |
| v5.12 | 2021-01 | `cold-ap-off` reboot argument ([`4c2e9b3e1896`](https://github.com/torvalds/linux/commit/4c2e9b3e18962862281d2b2b82e5ef8aaba0442f)) |
| v6.15 | 2025-02 | `usbpdmuxinfo` attribute added ([`e6a3215f7871`](https://github.com/torvalds/linux/commit/e6a3215f78716d25ad60b002fd0585c04ffd5d01); see [§2.7](#27-added-after-612-current-mainline--v711)) |

### 4.3 [`cros_ec_debugfs.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c) — `/sys/kernel/debug/cros_ec/*`

**Functionality.** The debugging window into the EC: `console_log` (a
continuously-polled copy of the EC's UART console), `pdinfo` (USB-PD port
state), `panicinfo` (saved crash record), `uptime`, and two suspend-telemetry
files. Instantiated as unconditional MFD cell `cros-ec-debugfs`
([cell array `cros_ec_dev.c:157`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L157)).
The [probe `:488`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L488)
issues three commands but **tolerates every failure** (only ENOMEM/notifier
registration are fatal) — files whose command is unsupported are simply not
created. **On gale: ✅ present**; `console_log`, `pdinfo` and `panicinfo`
work, `uptime` is suppressed.

**Host commands used:**

| debugfs file | Command | Purpose | Call site | Failure behaviour | gale EC |
|---|---|---|---|---|:--:|
| `console_log` | [`EC_CMD_CONSOLE_SNAPSHOT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3906) (0x97) | latch console ring | [`:75`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L75) | poll iteration skipped | ✅ |
| `console_log` | [`EC_CMD_CONSOLE_READ`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3920) (0x98) v1 | drain console ring | [background poll `:102`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L102); v1-support probe via [`EC_CMD_GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065) at [`:364`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L364)/[`:380`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L380) | no v1 ⇒ file not created | ✅ |
| `pdinfo` | [`EC_CMD_USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020) (0x101) **v1 only** | port state lines | looped over ports [`:226`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L226)/[`:235`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L235) until first error — it does **not** use `USB_PD_PORTS` | read shows fewer ports | ✅ v1 |
| `panicinfo` | [`EC_CMD_GET_PANIC_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4921) (0xd3) | fetch crash record | probe [`:424`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L424); [failure forced to "no data" `:450`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L450); file [created only if data exists `:459`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L459) | file absent | ✅ |
| `uptime` | [`EC_CMD_GET_UPTIME_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5519) (0x121) | EC uptime/AP resets | support check [`:262`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L262) ([`INVALID_COMMAND` suppresses the file `:266`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L266)); read [`:288`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L288) | file **not created** (gale's case) | ❌ |
| `last_resume_result`, `suspend_timeout_ms` | none (cached core variables) | suspend telemetry | [`:518`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L518)/[`:521`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L521) | — | n/a |

**Command reference:**

#### `EC_CMD_CONSOLE_SNAPSHOT` (0x97) / `EC_CMD_CONSOLE_READ` (0x98) · gale ✅ (v0 / v0+v1)

- Defined: [`cros_ec_commands.h:3906`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3906) / [`:3920`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3920)
- Semantics: `CONSOLE_SNAPSHOT` (no request, no response) latches the EC's
  UART ring buffer; `CONSOLE_READ` drains the latched copy chunk by chunk.
- `CONSOLE_READ` v1 request
  [`struct ec_params_console_read_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3927):

```c
struct ec_params_console_read_v1 {
	uint8_t subcmd;   /* enum ec_console_read_subcmd: 0=NEXT, 1=RECENT */
} __ec_align1;
```

- Response: NUL-terminated ASCII chunk (empty when drained; call repeatedly).
- Errors: none beyond transport.

#### `EC_CMD_GET_PANIC_INFO` (0xd3) · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:4921`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4921)
- Request: none. Response: the raw EC `struct panic_data` (arch-specific,
  variable length; empty response if no valid panic saved). Reading marks
  the record consumed.

#### `EC_CMD_GET_UPTIME_INFO` (0x121) · gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:5519`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5519)
- Request: none. Response
  [`struct ec_response_uptime_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5521):

```c
struct ec_response_uptime_info {
	uint32_t time_since_ec_boot_ms;
	uint32_t ap_resets_since_ec_boot;
	uint32_t ec_reset_flags;
	struct ap_reset_log_entry {
		uint16_t reset_cause;
		uint16_t reserved;
		uint32_t reset_time_ms;
	} recent_ap_reset[4];
} __ec_align4;
```

(`USB_PD_CONTROL` (0x101) is detailed in
[§6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc);
`GET_CMD_VERSIONS` (0x08) in
[§3.2](#32-core-bring-up-cros_ec--cros_ec_proto).)

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`CONSOLE_SNAPSHOT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3906) (0x97) | ✅ v0 — [`host_command_console_snapshot`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#357) | ✅ v0 — moved to [`uart_hostcmd.c:17`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#17) | ✅ — [`CONFIG_PLATFORM_EC_HOSTCMD_CONSOLE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.console#38) (default y), via [`CMakeLists.txt:412`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#412) |
| [`CONSOLE_READ`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3920) (0x98) | ✅ v0+v1 — [`host_command_console_read`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#419) | ✅ v0+v1 — [`uart_hostcmd.c:53`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#53) | ✅ — same `CONFIG_PLATFORM_EC_HOSTCMD_CONSOLE` gate |
| [`GET_PANIC_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4921) (0xd3) | ✅ v0 — [`host_command_panic_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c#233) | ✅ v0-v2 — [`panic_output.c:618`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/panic_output.c#618) | ✅ — [`CONFIG_PLATFORM_EC_PANIC`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig#715) (default y), via [`CMakeLists.txt:520`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#520) |
| [`GET_UPTIME_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5519) (0x121) | ❌ not in tree | ✅ v0 — [`uptime.c:42`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uptime.c#42) | ✅ — [`CONFIG_PLATFORM_EC_HOSTCMD_GET_UPTIME_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig#531) (defaults to on whenever host commands are on), via [`CMakeLists.txt:414`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#414) |
| [`USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020) (0x101) v1 | ✅ v0+v1 (see [§6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc)) | ✅ v0-v2 | ✅ (see [§6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc)) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.13 | 2017-06 | introduced with `console_log` ([`e86264595225`](https://github.com/torvalds/linux/commit/e86264595225d2764a903965356ef59aeb7d1c47)) and `panicinfo` ([`6e4941067cef`](https://github.com/torvalds/linux/commit/6e4941067cef482c9ed254cf06cab70c32db05b2)) |
| v5.1 | 2019-02 | split into its own driver/MFD cell ([`6fce0a2cf5a0`](https://github.com/torvalds/linux/commit/6fce0a2cf5a050e8a3326556d7d293e69be303be)) |
| v5.3 | 2019-06 | `uptime` file added ([`e90716a66121`](https://github.com/torvalds/linux/commit/e90716a6612150218aaff1fd47ca6de954100a06)) |
| v6.3 | 2023-01 | console polled immediately on EC panic ([`d90fa2c64d59`](https://github.com/torvalds/linux/commit/d90fa2c64d59f5f151beeef5dbc599784b3391ca)) |

---

## 5. [`gpio-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c) — EC GPIO controller (the one gated consumer that fully works on gale)

**Functionality.** Exposes the EC's named GPIO lines as a Linux `gpiochip`
(`/sys/class/gpio` / libgpiod), reading levels, directions and names over
host commands. Instantiated as MFD cell `cros-ec-gpio`, gated on the EC
advertising [`EC_FEATURE_GPIO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1233)
(bit 14; [gate `cros_ec_dev.c:121`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L121));
no DT node is needed
([the probe borrows the EC's fwnode `:173`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L173)).
**On gale: ✅ bound and working** — gale is one of only two feature bits set
(see [§1.4](#14-what-gales-ec-implements--the-31-commands)), and the device
is live-confirmed on puck12 as `cros-ec-gpio.3.auto`. Writes are possible
because gale's EC runs unlocked (`CONFIG_SYSTEM_UNLOCKED`).

**Host commands used:**

| Use | Command (subcommand) | Ver | Call site | Probe-fatal? | gale EC |
|---|---|:--:|---|:--:|:--:|
| count GPIOs (probe) | [`EC_CMD_GPIO_GET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761) (0x93) `GET_COUNT` | v1 | [`cros_ec_gpio_ngpios()` `:154`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L154), checked [`:175`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L175) | **YES** | ✅ |
| name each line (probe) | [`EC_CMD_GPIO_GET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761) (0x93) `GET_INFO` | v1 | [`cros_ec_gpio_init_names()` `:126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L126), checked [`:187`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L187) | **YES** | ✅ |
| read a line | [`EC_CMD_GPIO_GET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761) (0x93) by-name | v0 | [`cros_ec_gpio_get()` `:60`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L60) | no | ✅ |
| line direction | [`EC_CMD_GPIO_GET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761) (0x93) `GET_INFO` | v1 | [`cros_ec_gpio_get_direction()` `:84`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L84) | no | ✅ |
| drive a line | [`EC_CMD_GPIO_SET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3753) (0x92) | v0 | [`cros_ec_gpio_set()` `:41`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L41) | no | ✅ |

The probe requires **`GPIO_GET` v1** — gale provides v0+v1 (version mask
`0x3`), which the live bound device proves.

**Command reference:**

#### `EC_CMD_GPIO_GET` (0x93) · gale ✅ (v0+v1)

- Defined: [`cros_ec_commands.h:3761`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761); subcommands [`enum gpio_get_subcmd`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3798)
- renode: the named-GPIO table this command reads is the reconstructed
  [`board/gale/gpio.inc`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/gpio.inc)
- Request v0
  [`struct ec_params_gpio_get`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3764) /
  v1 [`struct ec_params_gpio_get_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3773):

```c
struct ec_params_gpio_get { char name[32]; } __ec_align1;

struct ec_params_gpio_get_v1 {
	uint8_t subcmd;                       /* 0=BY_NAME, 1=COUNT, 2=INFO */
	union {
		struct __ec_align1 { char name[32]; } get_value_by_name;
		struct __ec_align1 { uint8_t index; } get_info;
	};
} __ec_align1;
```

- Response v0
  [`struct ec_response_gpio_get`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3768) /
  v1 [`struct ec_response_gpio_get_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3785):

```c
struct ec_response_gpio_get { uint8_t val; } __ec_align1;

struct ec_response_gpio_get_v1 {
	union {
		struct __ec_align1 { uint8_t val; } get_value_by_name, get_count;
		struct __ec_todo_unpacked {
			uint8_t val;
			char name[32];
			uint32_t flags;   /* GPIO_* flags: input/output/pullup/… */
		} get_info;
	};
} __ec_todo_packed;
```

- Errors: `EC_RES_ERROR` for an unknown name / out-of-range index;
  `EC_RES_INVALID_PARAM` for a bad v1 subcommand.

#### `EC_CMD_GPIO_SET` (0x92) · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:3753`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3753)
- Request [`struct ec_params_gpio_set`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3755):

```c
struct ec_params_gpio_set {
	char name[32];   /* case-insensitive GPIO name */
	uint8_t val;     /* 0 = low, non-zero = high */
} __ec_align1;
```

- Response: none.
- Errors: `EC_RES_ACCESS_DENIED` if the EC is locked (`system_is_locked()`;
  gale runs `CONFIG_SYSTEM_UNLOCKED` → normally allowed); `EC_RES_ERROR` if
  the named line is not an output.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`GPIO_GET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761) (0x93) | ✅ v0+v1 — [`gpio_command_get`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#259), compiled via [`CONFIG_COMMON_GPIO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#36) | ✅ v0+v1 — [`gpio_commands.c:280`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#280) | ✅ always — `common/gpio_commands.c` is in the baseline [`CONFIG_PLATFORM_EC` source block](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#200) |
| [`GPIO_SET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3753) (0x92) | ✅ v0 — [`gpio_command_set`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#274) | ✅ v0 — [`gpio_commands.c:295`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#295) | ✅ always — same baseline block |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v6.9 | 2024-02 | driver introduced ([`f837fe1bffe6`](https://github.com/torvalds/linux/commit/f837fe1bffe6976ed5e7198b1892ea248b75358b)), together with its MFD feature-gated cell ([`8f49b623b934`](https://github.com/torvalds/linux/commit/8f49b623b9348e3374491df1a18ca2de285fc7da)) — a *recent* driver that happens to fit gale's 2016 EC perfectly |
| v6.10 | 2024-04 | platform ID table added ([`782f4e47ffc1`](https://github.com/torvalds/linux/commit/782f4e47ffc19622bf80b3c0cf9cadd2b0b9a644)) |
| v6.15 | 2025-03 | new line-value setter callbacks ([`2661dc2de186`](https://github.com/torvalds/linux/commit/2661dc2de18617ac827aa9b50cb145bf5a185896)) |
| v7.1 (current) | 2026 | probe still hard-requires `GPIO_GET` v1 ([§2.7](#27-added-after-612-current-mainline--v711)) |

---

## 6. USB-PD / Type-C / charger family

None of these instantiate on a stock gale: four are gated on
[`EC_FEATURE_USB_PD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1252)
(bit 22, clear on gale), one on a live `PCHG_COUNT` probe, and two bind only
to DT/ACPI nodes gale doesn't declare. Verified live: all unbound on puck12.

### 6.1 [`cros_ec_typec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c) — USB Type-C connector class (+ [`cros_typec_vdm.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c))

**Functionality.** Registers each EC-managed USB-C port with the kernel's
Type-C connector class (`/sys/class/typec/portN`): power/data role, partner
and cable identity, alternate modes, and (on modern ECs) DP/TBT mode entry
and VDM exchange via the companion `cros_typec_vdm.c`. Binds to DT
[`google,cros-ec-typec`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1206)
or ACPI `GOOG0014`
([`:1198`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1198)) —
**not** an MFD cell. **On gale: ❌ never instantiates** (no DT node). If a
node were added it *would* attach — see the verdict below — but run
mux-blind and event-blind.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: pick `USB_PD_CONTROL` version | [`EC_CMD_GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065) (0x08) | [`:1156`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1156), fatal [`:1235`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1235) | **YES** | ✅ |
| probe: feature flags | [`EC_CMD_GET_FEATURES`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1182) (0x0d) | [`:1245`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1245) → sets `typec_cmd_supported`/`needs_mux_ack` | no | ✅ (both false) |
| probe: port count | [`EC_CMD_USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113) (0x102) | [`:1248`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1248), fatal [`:1250`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1250) | **YES** | ✅ |
| probe+runtime: port state | [`EC_CMD_USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020) (0x101) | [`:1119`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1119), fatal [`:1272`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1272) | **YES** | ✅ v1 |
| runtime: SS-mux state | [`EC_CMD_USB_PD_MUX_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385) (0x11a) | [`:624`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L624) — warned & [swallowed `:1126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1126) | no | ❌ |
| runtime: mux ack | [`EC_CMD_USB_PD_MUX_ACK`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6448) (0x603) | [`:687`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L687), only if `needs_mux_ack` | no | ❌ (never sent) |
| runtime: PD status/events | [`EC_CMD_TYPEC_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5932) (0x133) | [`:1024`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1024), only if `typec_cmd_supported` ([gate `:1142`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1142)) | no | ❌ (never sent) |
| runtime: altmode discovery | [`EC_CMD_TYPEC_DISCOVERY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5840) (0x131) | [`:856`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L856)/[`:939`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L939) | no | ❌ (never sent) |
| runtime: control / VDM send | [`EC_CMD_TYPEC_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5867) (0x132) | [`:972`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L972); [`cros_typec_vdm.c:116`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L116)/[`:141`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L141) | no | ❌ (never sent) |
| runtime: VDM replies | [`EC_CMD_TYPEC_VDM_RESPONSE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6049) (0x13c) | [`cros_typec_vdm.c:32`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L32)/[`:70`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L70) | no | ❌ (never sent) |

**The version question, settled from source:** the driver does **not** demand
`USB_PD_CONTROL` v2. It takes the best available —

```c
1161	if (resp.version_mask & EC_VER_MASK(2))
1162		typec->pd_ctrl_ver = 2;
1163	else if (resp.version_mask & EC_VER_MASK(1))
1164		typec->pd_ctrl_ver = 1;
1165	else
1166		typec->pd_ctrl_ver = 0;
```

([`cros_ec_typec.c:1161`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1161))
— and only the runtime DP/TBT altmode paths insist on v2, non-fatally
([`"PD_CTRL version too old"` `:462`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L462),
[`:519`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L519)).

**gale verdict:** never instantiates (no DT node). If a node were added, the
probe-fatal set (0x08, 0x102, 0x101-v1) is entirely within gale's 31 — it
would attach at `pd_ctrl_ver = 1` and run **mux-blind and event-blind**
(every 0x11a call warned, and 0x133/0x131/0x132 never issued). Partner/cable
registration and role reporting would work at v1 fidelity.

**Command reference:**

#### `EC_CMD_USB_PD_CONTROL` (0x101) — port role/mux/state · gale ✅ (v0+v1)

- Defined: [`cros_ec_commands.h:5020`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020); request enums [`usb_pd_control_role`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5022), [`usb_pd_control_mux`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5032), [`usb_pd_control_swap`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5042); response flags [`PD_CTRL_RESP_ENABLED_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5057), [`PD_CTRL_RESP_ROLE_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5061)
- Issued by: cros-ec-typec (above); extcon at v1 ([`extcon-usbc-cros-ec.c:155`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L155)); debugfs `pdinfo` at v1 ([`cros_ec_debugfs.c:226`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L226))
- renode: gale's sink-preferring PD policy behind this command is the reconstructed [`board/gale/usb_pd_policy.c`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/usb_pd_policy.c)

Request [`struct ec_params_usb_pd_control`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5050) (4 B, all versions):

```c
struct ec_params_usb_pd_control {
	uint8_t port;   /* gale: only 0 */
	uint8_t role;   /* enum usb_pd_control_role: 0=NO_CHANGE 1=TOGGLE_ON 2=TOGGLE_OFF 3=FORCE_SINK 4=FORCE_SOURCE */
	uint8_t mux;    /* enum usb_pd_control_mux:  0=NO_CHANGE 1=NONE 2=USB 3=DP 4=DOCK 5=AUTO */
	uint8_t swap;   /* enum usb_pd_control_swap: 0=NONE 1=DATA 2=POWER 3=VCONN */
} __ec_align1;
```

Response [v0 `:5069`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5069) /
[v1 `:5076`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5076) /
[v2 `:5100`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5100):

```c
struct ec_response_usb_pd_control    { uint8_t enabled, role, polarity, state; } __ec_align1;   /* v0 */

struct ec_response_usb_pd_control_v1 {          /* what gale answers */
	uint8_t enabled;    /* bit0 COMMS, bit1 CONNECTED, bit2 PD_CAPABLE */
	uint8_t role;       /* bit0 POWER(1=SRC), bit1 DATA(1=DFP), bit2 VCONN, … */
	uint8_t polarity;
	char state[32];     /* PD task-state name, e.g. "SNK_DISCONNECTED" */
} __ec_align1;

struct ec_response_usb_pd_control_v2 {          /* NOT available on gale */
	uint8_t enabled, role, polarity;
	char state[32];
	uint8_t cc_state, dp_mode, reserved, control_flags, cable_speed, cable_gen;
} __ec_align1;
```

Errors: `EC_RES_INVALID_PARAM` if `port ≥ 1`, `role ≥ 5`, or `mux ≥ 6`.

#### `EC_CMD_USB_PD_PORTS` (0x102) — port count · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:5113`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113)
- Request: none. Response
  [`struct ec_response_usb_pd_ports`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5118)
  `{ uint8_t num_ports; }` — gale answers `1`.
- Errors: none.

#### `EC_CMD_USB_PD_MUX_INFO` (0x11a) — SS-mux state · gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:5385`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385); response flags [`USB_PD_MUX_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5392) (USB_ENABLED / DP_ENABLED / POLARITY_INVERTED / HPD_IRQ / HPD_LVL / SAFE_MODE / TBT / USB4)
- Request [`{ uint8_t port; }`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5387); response
  [`struct ec_response_usb_pd_mux_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5402)
  `{ uint8_t flags; }`.
- Provided upstream by the USB-mux framework — hardware gale doesn't have
  (its USB SS lines are hard-wired).

#### `EC_CMD_TYPEC_DISCOVERY` (0x131) · `EC_CMD_TYPEC_CONTROL` (0x132) · `EC_CMD_TYPEC_STATUS` (0x133) · `EC_CMD_TYPEC_VDM_RESPONSE` (0x13c) — the modern (TCPMv2) AP interface · all gale ❌ absent-in-2016

Defined:
[`0x131` `:5840`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5840) ·
[`0x132` `:5867`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5867)
(subcommands [`enum typec_control_command`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5869)) ·
[`0x133` `:5932`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5932)
(enums [`pd_power_role`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5941), [`pd_data_role`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5953), [`tcpc_cc_polarity`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5968), events [`PD_STATUS_EVENT_*` `:5993`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5993)) ·
[`0x13c` `:6049`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6049).

Key structures:

```c
struct ec_params_typec_status { uint8_t port; } __ec_align1;

struct ec_response_typec_status {              /* 0x133 — the modern port snapshot */
	uint8_t pd_enabled, dev_connected, sop_connected, source_cap_count;
	uint8_t power_role, data_role, vconn_role, sink_cap_count;
	uint8_t polarity, cc_state, dp_pin, mux_state;
	char tc_state[32];
	uint32_t events;                           /* PD_STATUS_EVENT bitmask */
	uint16_t sop_revision, sop_prime_revision; /* BCD PD revision */
	uint32_t source_cap_pdos[7];
	uint32_t sink_cap_pdos[7];
} __ec_align1;

struct ec_params_typec_control {               /* 0x132 */
	uint8_t port;
	uint8_t command;                           /* enum typec_control_command */
	uint16_t reserved;
	union {
		uint32_t clear_events_mask;
		uint8_t mode_to_enter;
		uint8_t tbt_ufp_reply;
		struct typec_usb_mux_set mux_params;
		struct typec_vdm_req vdm_req_params;
		uint8_t placeholder[128];
	};
} __ec_align1;
```

([full struct definitions: `ec_params_typec_discovery` `:5847`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5847),
[`ec_response_typec_discovery` `:5858`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5858),
[`ec_params_typec_control` `:5901`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5901),
[`ec_response_typec_status` `:6007`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6007),
[`ec_response_typec_vdm_response` `:6055`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6055))

These commands do not exist in the 2016 codebase at all. Upstream they are
backed by the TCPMv2 state machines (`common/usbc/*.c`) — porting them to
gale means forward-porting the whole PD stack, not adding a handler.

#### `EC_CMD_USB_PD_MUX_ACK` (0x603) · gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:6448`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6448)
- Request [`{ uint8_t port; }`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6450); no response.
- Only sent when the EC advertises
  [`EC_FEATURE_TYPEC_MUX_REQUIRE_AP_ACK`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1302) (bit 43).

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113) (0x102) | ✅ v0 — [`hc_pd_ports`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3068) | ✅ — [`usb_pd_host_cmd.c:41`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd.c#41), gated [`CONFIG_USB_PD_HOST_CMD`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#180) | ✅ TCPMv2 builds via [`tcpmv2.cmake:35`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/tcpmv2.cmake#35); PDC builds via [`pdc_host_cmd.c:105`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/subsys/pd_controller/pdc_host_cmd.c#105) |
| [`USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020) (0x101) | ✅ v0+v1 — [`hc_usb_pd_control`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3159) (TCPMv1), gated [`CONFIG_USB_POWER_DELIVERY`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#86) | ✅ v0-v2 — [`usb_pd_host_cmd_common.c:202`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#202) (the 2016 TCPMv1 file was deleted upstream) | ✅ — [`CONFIG_PLATFORM_EC_USB_PD_HOST_CMD`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.pd_host_cmd#5) (default y on USB-C builds), via [`CMakeLists.txt:674`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#674) |
| [`USB_PD_MUX_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385) (0x11a) | ❌ not in tree | ✅ — [`usb_mux.c:912`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#912), gated [`CONFIG_USBC_SS_MUX`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/build.mk#212) | ✅ — [`CONFIG_PLATFORM_EC_USBC_SS_MUX`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.usbc_ss_mux#5) (default y); PDC builds via [`pdc_host_cmd.c:132`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/subsys/pd_controller/pdc_host_cmd.c#132) |
| [`USB_PD_MUX_ACK`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6448) (0x603) | ❌ not in tree | ✅ — [`usb_mux.c:942`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#942) | ✅ — same `CONFIG_PLATFORM_EC_USBC_SS_MUX` gate |
| [`TYPEC_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5932) (0x133) | ❌ not in tree | ✅ — [`hc_typec_status` `usb_pd_host_cmd_common.c:312`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#312) | ✅ — `CONFIG_PLATFORM_EC_USB_PD_HOST_CMD` |
| [`TYPEC_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5867) (0x132) | ❌ not in tree | ✅ — [`hc_typec_control` `:419`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#419) | ✅ — `CONFIG_PLATFORM_EC_USB_PD_HOST_CMD` |
| [`TYPEC_DISCOVERY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5840) (0x131) | ❌ not in tree | ✅ — [`hc_typec_discovery` `usbc/usb_pd_host.c:102`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usbc/usb_pd_host.c#102) | ✅ TCPMv2 builds only ([`tcpmv2.cmake:35`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/tcpmv2.cmake#35)) |
| [`TYPEC_VDM_RESPONSE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6049) (0x13c) | ❌ not in tree | ✅ — [`usbc/ap_vdm_control.c:300`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usbc/ap_vdm_control.c#300), gated `CONFIG_USB_PD_VDM_AP_CONTROL` | ✅ — [`CONFIG_PLATFORM_EC_USB_PD_VDM_AP_CONTROL`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.pd#218) |
| [`GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065) (0x08) / [`GET_FEATURES`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1182) (0x0d) | ✅ (see [§3.2](#32-core-bring-up-cros_ec--cros_ec_proto)/[§3.3](#33-mfd-cros_ec_dev--the-gatekeeper)) | ✅ | ✅ |

(Caveat that applies to every "[EC-main] legacy build" cell in this document:
at the [EC-main] pin the legacy Makefile build **retains the common-code
handlers but has lost all real chip/board targets** — `chip/` and `board/`
now only contain the host emulator and hyperdebug. The cells describe whether
the handler code is still compiled into legacy builds, but every shipping EC
today is a Zephyr build.)

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v5.7 | 2020-03 | driver introduced ([`fdc6b21e2444`](https://github.com/torvalds/linux/commit/fdc6b21e2444290b69ac9ffa936bf583830dc0de) "Add Type C connector class driver") |
| v5.9 | 2020-06 | Thunderbolt compat-mode support ([`5b30bd35aab4`](https://github.com/torvalds/linux/commit/5b30bd35aab4bcea6a06627a1e943659d82a71cb)) |
| v5.10 | 2020-08 | USB4 support ([`46c5bbd2df4a`](https://github.com/torvalds/linux/commit/46c5bbd2df4a8b7eed427db866a5bce7234744bf)) |
| v6.3 | 2023-01 | initial VDM support — `cros_typec_vdm.c` added ([`493e699b9934`](https://github.com/torvalds/linux/commit/493e699b9934d9cd6a46ecc7782540014b369267)) |
| v6.14 | 2024-12 | AP-driven DP altmode — the split that created `cros_typec_altmode.c` ([`dbb3fc0ffa95`](https://github.com/torvalds/linux/commit/dbb3fc0ffa95788e00e50ffc6501eb0085d48231)), plus Thunderbolt ([`3b00be26b16a`](https://github.com/torvalds/linux/commit/3b00be26b16ad72c85624ada08cbae2d2c57b6e9)) |
| v7.1 (current) | 2026 | actively maintained; probe still accepts `USB_PD_CONTROL` v1 (see [§2.7](#27-added-after-612-current-mainline--v711)) |

### 6.2 [`extcon-usbc-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c) — USB-C cable-state extcon

**Functionality.** Publishes each USB-C port's cable state (USB host/device,
DP, charger type, polarity, HPD) through the extcon subsystem, for consumers
like USB controllers and DRM bridges that need to react to cable events.
Binds to DT
[`google,extcon-usbc-cros-ec`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L519)
(one node per port) — not an MFD cell. Updates run on PD host events and at
probe. **On gale: ❌ never instantiates** (no DT node) — and even with a
node, **probe would fail** because its cable-state update fatally requires
`USB_PD_POWER_INFO`, which gale doesn't compile (details below).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: port sanity | [`EC_CMD_USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113) (0x102) | [`:180`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L180), fatal [`:411`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L411) | **YES** | ✅ |
| probe+event: power type | [`EC_CMD_USB_PD_POWER_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122) (0x103) | [`:105`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L105) | **YES** (quote below) | ❌ |
| event: role/polarity | [`EC_CMD_USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020) (0x101) v1 | [`:155`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L155) ([`-ENOTCONN` = disconnected `:266`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L266)) | no | ✅ |
| event: mux/HPD | [`EC_CMD_USB_PD_MUX_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385) (0x11a) | [`:126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L126) ([failure defaulted `:279`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L279)) | no | ❌ |

**The fatal bail** — `USB_PD_POWER_INFO` failure kills the whole cable
update, and probe runs it with `force=true`
([`:469`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L469)):

```c
259	power_type = cros_ec_usb_get_power_type(info);
260	if (power_type < 0) {
261		dev_err(dev, "failed getting power type err = %d\n",
262			power_type);
263		return power_type;
264	}
```

([`extcon-usbc-cros-ec.c:259`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L259))

**gale verdict:** never instantiates (no DT node); if forced, **probe fails**
on `USB_PD_POWER_INFO` → `-EOPNOTSUPP`. Making this driver work on gale =
compile `USB_PD_POWER_INFO` into the EC (⚠️ tier) *or* patch the driver to
make `power_type` best-effort like `mux_state` already is.

**Command reference:**

#### `EC_CMD_USB_PD_POWER_INFO` (0x103) — **the power-consumption command** · gale ⚠️ addable

The command that would expose gale's measured VBUS voltage/current in-band —
the original motivation for this whole investigation.

- Defined: [`cros_ec_commands.h:5122`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122); enums [`usb_chg_type`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5129), [`usb_power_roles`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5142); [`PD_POWER_CHARGING_PORT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5124)
- Issued by: extcon (fatal, above); cros-usbpd-charger ([`:183`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L183), per-property reads)
- On gale: the handler exists in the 2016 tree but is gated by
  [`CONFIG_CHARGE_MANAGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#30),
  which gale doesn't set → not compiled. The measurement sources exist on
  gale (ADC channels for VBUS/current in the reconstructed
  [`board/gale/board.c`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/board.c);
  EC console `gale vbus` prints them) — only this host-command plumbing is
  missing.

Request [`struct ec_params_usb_pd_power_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5125)
`{ uint8_t port; }` (or `PD_POWER_CHARGING_PORT` = 0xff for "the charging
port"). Response
[`struct ec_response_usb_pd_power_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5156):

```c
struct usb_chg_measures {
	uint16_t voltage_max;   /* mV */
	uint16_t voltage_now;   /* mV */
	uint16_t current_max;   /* mA */
	uint16_t current_lim;   /* mA */
} __ec_align2;

struct ec_response_usb_pd_power_info {
	uint8_t role;                 /* enum usb_power_roles */
	uint8_t type;                 /* enum usb_chg_type */
	uint8_t dualrole;
	uint8_t reserved1;
	struct usb_chg_measures meas;
	uint32_t max_power;           /* µW */
} __ec_align4;
```

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`USB_PD_POWER_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122) (0x103) | ⚠️ off — [`hc_pd_power_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#878) (v0) exists, gated [`CONFIG_CHARGE_MANAGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#30) which gale doesn't set | ✅ v0 — [`charge_manager.c:1801`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1801) | ✅ — [`CONFIG_PLATFORM_EC_CHARGE_MANAGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.charger#1186) (selected by `PLATFORM_EC_CHARGER`), via [`CMakeLists.txt:323`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#323) |
| [`USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113) (0x102) / [`USB_PD_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020) (0x101) / [`USB_PD_MUX_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385) (0x11a) | ✅ / ✅ / ❌ | ✅ | ✅ (all — see the table in [§6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc)) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.14 | 2017-07 | driver introduced, for USB-C display-out detection ([`c69831666109`](https://github.com/torvalds/linux/commit/c698316661096e036b54448039b35e1c2c5809f0)) |
| v4.16 | 2017-12 | USB host/device cable notification added ([`c7eb47f9e452`](https://github.com/torvalds/linux/commit/c7eb47f9e45226571be31212f6efd4b307d3b59d)) |
| v5.4 | 2019-09 | cros_ec MFD/platform include reorganisation ([`840d9f131f65`](https://github.com/torvalds/linux/commit/840d9f131f65b021e0a73f3371f3194897dba6ad)) |
| v7.1 (current) | 2026 | essentially unchanged — the fatal `power_type < 0` bail is still present ([§2.7](#27-added-after-612-current-mainline--v711)) |

### 6.3 [`cros_usbpd-charger.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c) — USB-PD power_supply provider

**Functionality.** Registers one `power_supply` class device per EC charge
port (`/sys/class/power_supply/CROS_USBPD_CHARGER0`, …) reporting charger
type, online state, and the measured/negotiated voltage and current — the
standard kernel surface for "what power is this machine drawing over USB-C".
Instantiated as MFD cell `cros-usbpd-charger`, gated on
[`EC_FEATURE_USB_PD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1252)
([gate `cros_ec_dev.c:131`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L131),
cell [`:90`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L90)).
**On gale: ❌ never instantiates** (feature bit clear). With the feature bit
+ `USB_PD_POWER_INFO` added on the EC (⚠️ tier), this stock driver would
work — it is the natural kernel surface for gale power telemetry.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: PD port count | [`EC_CMD_USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113) (0x102) | [`:136`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L136) | no (logged) | ✅ |
| probe: total charge-port count | [`EC_CMD_CHARGE_PORT_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5171) (0x105) | [`:122`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L122) | no (falls back to PD count) | ❌ |
| property read: measurements | [`EC_CMD_USB_PD_POWER_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122) (0x103) | [`:183`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L183) | no ([`-EINVAL` per read `:381`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L381)) | ❌ |
| property read: partner VID/PID | [`EC_CMD_USB_PD_DISCOVERY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5217) (0x113) | [`:153`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L153) | no | ❌ |
| sysfs write: input limits | [`EC_CMD_EXTERNAL_POWER_LIMIT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4189) (0xa2) | [`:328`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L328) | no | ❌ |

The only structural failure that is fatal: no ports at all →
[`-ENODEV` `:579`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L579).

**Command reference:**

#### `EC_CMD_CHARGE_PORT_COUNT` (0x105) · gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:5171`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5171)
- Request: none. Response
  [`struct ec_response_charge_port_count`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5172)
  `{ uint8_t port_count; }` (counts dedicated barrel-jack ports too, unlike
  `USB_PD_PORTS`).

#### `EC_CMD_USB_PD_DISCOVERY` (0x113) · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:5217`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5217)
- Request `{ uint8_t port; }`. Response
  [`struct ec_params_usb_pd_discovery_entry`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5218)
  `{ uint16_t vid; uint16_t pid; uint8_t ptype; }` — the PD partner's USB
  VID/PID from discovery.

#### `EC_CMD_EXTERNAL_POWER_LIMIT` (0xa2) · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:4189`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4189)
- Request (v1)
  [`struct ec_params_external_power_limit_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4192)
  `{ uint16_t current_lim; /* mA */ uint16_t voltage_lim; /* mV */ }`
  (`EC_POWER_LIMIT_NONE` = 0xffff clears). No response.

(`USB_PD_POWER_INFO` (0x103) is detailed in
[§6.2](#62-extcon-usbc-cros-ecc--usb-c-cable-state-extcon).)

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`CHARGE_PORT_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5171) (0x105) | ❌ not in tree | ✅ — [`charge_manager.c:1813`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1813) | ✅ — [`CONFIG_PLATFORM_EC_CHARGE_MANAGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.charger#1186) |
| [`USB_PD_DISCOVERY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5217) (0x113) | ⚠️ off — [`hc_remote_pd_discovery`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_policy.c#821), gated `CONFIG_USB_PD_ALT_MODE_DFP` (gale is sink/UFP-only) | ✅ — [`usb_pd_host_cmd_common.c:442`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#442) | ✅ — [`CONFIG_PLATFORM_EC_USB_PD_HOST_CMD`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.pd_host_cmd#5) |
| [`EXTERNAL_POWER_LIMIT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4189) (0xa2) | ⚠️ off — [`hc_external_power_limit`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#960), gated `CONFIG_CHARGE_MANAGER` | ✅ — [`charge_manager.c:1916`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1916) | ✅ — [`CONFIG_PLATFORM_EC_CHARGE_MANAGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.charger#1186) |
| [`USB_PD_PORTS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113) (0x102) / [`USB_PD_POWER_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122) (0x103) | ✅ / ⚠️ | ✅ | ✅ (see [§6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc)/[§6.2](#62-extcon-usbc-cros-ecc--usb-c-cable-state-extcon)) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.19 | 2018-07 | driver introduced ([`f68b883e8fad`](https://github.com/torvalds/linux/commit/f68b883e8fad23ed0ac4756d91594809d78678ed)) |
| v4.20 | 2018-09 | dedicated (barrel-jack) charge-port support — the `CHARGE_PORT_COUNT` path ([`3af15cfacd1e`](https://github.com/torvalds/linux/commit/3af15cfacd1eef7f223802d49a88cae23c509183)) |
| v5.3 | 2019-06 | writable input voltage/current limits — the `EXTERNAL_POWER_LIMIT` path ([`2ffb500d824b`](https://github.com/torvalds/linux/commit/2ffb500d824bbe6535c64d3e7e9971cca0db0a3e)) |
| v6.12 | 2024-09 | `usb_types` becomes a bitmask ([`364ea7ccaef9`](https://github.com/torvalds/linux/commit/364ea7ccaef917a3068236a19a4b31a0623b561a)) |
| v6.14+ | 2025 | on `EC_FEATURE_UCSI_PPM` ECs the MFD no longer instantiates this driver — `cros_ec_ucsi` supplies power data instead ([§2.7](#27-added-after-612-current-mainline--v711)) |

### 6.4 [`cros_usbpd_logger.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c) — PD event log

**Functionality.** Drains the EC's USB-PD event log every 60 s and prints
each entry (charger attach/detach, power negotiation, accessory events) to
the kernel log with charger details. Instantiated from the same
feature-gated cell array as the charger
([`cros_usbpd_charger_cells`, `cros_ec_dev.c:91`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L91),
gate `EC_FEATURE_USB_PD`).
[Probe is command-free](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c#L196)
(queues delayed work). **On gale: ❌ never instantiates** (feature bit
clear); even if forced it would log nothing (command not compiled).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| periodic log drain | [`EC_CMD_PD_GET_LOG_ENTRY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5243) (0x115) | [`ec_get_log_entry()` `:71`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c#L71); loop [breaks harmlessly on error `:182`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c#L182) | no | ⚠️ |

**Command reference:**

#### `EC_CMD_PD_GET_LOG_ENTRY` (0x115) · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:5243`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5243); entry types [`PD_EVENT_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5266)
- Request: none. Response
  [`struct ec_response_pd_log`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5245):

```c
struct ec_response_pd_log {
	uint32_t timestamp;  /* ms, relative */
	uint8_t type;        /* PD_EVENT_* */
	uint8_t size_port;   /* [7:5] port, [4:0] payload bytes */
	uint16_t data;
	uint8_t payload[];   /* 0-16 bytes */
} __ec_align4;
```

- An empty entry (`type == PD_EVENT_NO_ENTRY`) means end of log.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`PD_GET_LOG_ENTRY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5243) (0x115) | ⚠️ off — [`hc_pd_get_log_entry`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pd_log.c#192) (v0) exists, gated [`CONFIG_USB_PD_LOGGING`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#87) | ✅ — [`pd_log.c:86`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pd_log.c#86) | ✅ — [`CONFIG_PLATFORM_EC_USB_PD_LOGGING`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.pd_host_cmd#25) (default n), via [`CMakeLists.txt:667`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#667) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v5.2 | 2019-04 | driver introduced ([`a2679b647190`](https://github.com/torvalds/linux/commit/a2679b64719085196a8e1762a40e90e92b1f3cf5)) |
| v6.14+ | 2025 | suppressed by the MFD on `EC_FEATURE_UCSI_PPM` ECs, together with the charger cell ([§2.7](#27-added-after-612-current-mainline--v711)) |
| v7.1 | 2026-03 | devm simplification ([`168e4b208ca8`](https://github.com/torvalds/linux/commit/168e4b208ca8c2e04de20cc6cb7e2fb035dc1ec8)) |

### 6.5 [`cros_usbpd_notify.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_notify.c) — PD event fan-out

**Functionality.** The glue that turns EC "PD state changed" interrupts into
kernel notifications: it listens for the PD MKBP host event and calls every
registered consumer (cros-ec-typec, extcon, usbpd-charger all subscribe via
`cros_usbpd_register_notify()`). Instantiated as an OF cell gated on
`EC_FEATURE_USB_PD`
([`cros_ec_dev.c:282`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L282));
on ACPI platforms it binds `GOOG0003` instead.
[Probe is command-free](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_notify.c#L184).
**On gale: ❌ never instantiates** (feature bit clear — and gale has no MKBP
events to fan out anyway, see [§3.2](#32-core-bring-up-cros_ec--cros_ec_proto)).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| on PD MKBP event: read status word | [`EC_CMD_PD_HOST_EVENT_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5008) (0x104) | [`:64`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_notify.c#L64); best-effort ([warn + notify with 0 `:77`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_notify.c#L77)) | no | ⚠️ |

**Command reference:**

#### `EC_CMD_PD_HOST_EVENT_STATUS` (0x104) · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:5008`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5008); status bits [`PD_EVENT_UPDATE_DEVICE`, …](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5011)
- Request: none. Response
  [`struct ec_response_host_event_status`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5015)
  `{ uint32_t status; }` (read-and-clear).

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`PD_HOST_EVENT_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5008) (0x104) | ⚠️ off — [`hc_pd_host_event_status`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command_pd.c#242), gated `HAS_TASK_PDCMD`; gale's [task list](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/ec.tasklist) (HOOKS/HOSTCMD/CONSOLE/PD_C0) has no PDCMD task | ✅ — [`usb_pd_host_cmd_common.c:346`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#346) | ✅ — [`CONFIG_PLATFORM_EC_USB_PD_HOST_CMD`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.pd_host_cmd#5) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v5.7 | 2020-02 | driver introduced, centralising PD event delivery ([`ec2daf6e33f9`](https://github.com/torvalds/linux/commit/ec2daf6e33f9f9113ba085b6ff88592907b6f1ce)); `PD_HOST_EVENT_STATUS` polling added the same cycle ([`a88214089d67`](https://github.com/torvalds/linux/commit/a88214089d67b0f246cf6ae4fb0a7e0735ff3595)) |
| v5.13 | 2021-04 | also listens to the USB-mux host event ([`4423ee65f768`](https://github.com/torvalds/linux/commit/4423ee65f76818c8a8994e6f5821372661ea7f89)) |
| v6.19 | 2025-10 | defers probe until the parent EC driver is ready ([`e4ee0bb077cd`](https://github.com/torvalds/linux/commit/e4ee0bb077cd7d70207647a0106f6ea6a74c2636)) |

### 6.6 [`cros_peripheral_charger.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c) — Qi/stylus peripheral charger

**Functionality.** power_supply devices (`PCHG0`, …) for EC-managed
*peripheral* chargers — wireless (Qi) pads and garaged-stylus chargers —
reporting attach/charge state and battery percentage, with firmware-update
support for the charger chip. Instantiated via a **live command probe**: the
MFD calls `PCHG_COUNT` and only adds the `cros-pchg` cell when
`port_count > 0`
([`cros_ec_dev.c:298`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L298)).
**On gale: ❌ never instantiates** — gale answers `INVALID_COMMAND`, so the
cell is never added.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| MFD gate + probe: port count | [`EC_CMD_PCHG_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5622) (0x134) | MFD [`:298`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L298); driver [`:113`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L113), [`-ENODEV` `:286`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L286) | **YES** | ❌ |
| probe: require `PCHG` v1 | [`EC_CMD_GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065) (0x08) | [`:96`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L96), [`-EOPNOTSUPP` `:297`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L297) | **YES** | ✅ (but `PCHG` unknown) |
| property reads: port state | [`EC_CMD_PCHG`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5633) (0x135) | [`:135`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L135) | no | ❌ |

**Command reference:**

#### `EC_CMD_PCHG_COUNT` (0x134) / `EC_CMD_PCHG` (0x135) · gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:5622`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5622) / [`:5633`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5633)
- `PCHG_COUNT`: no request; response
  [`{ uint8_t port_count; }`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5626).
- `PCHG` (v1): request `{ uint8_t port; }`; response
  [`struct ec_response_pchg`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5639)
  `{ uint32_t error; uint8_t state; uint8_t battery_percentage; uint8_t unused; uint32_t fw_version; uint32_t dropped_event_count; }`.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`PCHG_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5622) (0x134) / [`PCHG`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5633) (0x135) | ❌ not in tree | ✅ — [`peripheral_charger.c:975`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#975)/[`:1021`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#1021), gated [`CONFIG_PERIPHERAL_CHARGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#135) | ✅ — [`CONFIG_PLATFORM_EC_PERIPHERAL_CHARGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.wireless_charger#5) (default n), via [`CMakeLists.txt:480`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#480) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v5.15 | 2021-07 | driver introduced ([`56d629af09b9`](https://github.com/torvalds/linux/commit/56d629af09b9d4db9792257165844287ecce0a98)) |
| v5.18 | 2022-02 | switched to MKBP for device events ([`845301001308`](https://github.com/torvalds/linux/commit/845301001308aab8fb7902548f6c3256d28b8c48)) |
| v6.5 | 2023-05 | port-status sync on resume ([`97dd69b1ade1`](https://github.com/torvalds/linux/commit/97dd69b1ade166f3200546e5fb7984986cafcf81)) |

---

## 7. Function drivers (shipped in the gale image, dormant)

### 7.1 [`cros_ec_vbc.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c) — vboot NV context

**Functionality.** Exposes the EC-stored verified-boot nonvolatile context
(the 16-byte VBNV block that firmware uses for recovery/dev-mode flags) as a
read/write sysfs binary attribute `vboot_context`. Instantiated as MFD cell
`cros-ec-vbc`, gated **only** on the DT property `google,has-vbc-nvram` on
the EC node
([`cros_ec_dev.c:322`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L322)) —
not on a feature bit.
[Probe is command-free](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c#L114).
**On gale: ❌ dormant (DT property not set) — but this is the one dormant
driver whose command gale fully implements.** Adding the property to the
`ec@1e` node would light it up with no EC change.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| `vboot_context` read | [`EC_CMD_VBNV_CONTEXT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1661) (0x17) v1, op READ | [`vboot_context_read()` `:43`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c#L43) | no (runtime only) | ✅ |
| `vboot_context` write | [`EC_CMD_VBNV_CONTEXT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1661) (0x17) v1, op WRITE | [`vboot_context_write()` `:86`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c#L86) | no (runtime only) | ✅ |

**Command reference:**

#### `EC_CMD_VBNV_CONTEXT` (0x17) · gale ✅ (v0+v1)

- Defined: [`cros_ec_commands.h:1661`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1661); [`EC_VER_VBNV_CONTEXT` = 1](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1662), [`EC_VBNV_BLOCK_SIZE` = 16](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1663)
- Request [`struct ec_params_vbnvcontext`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1670) /
  response [`struct ec_response_vbnvcontext`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1675):

```c
struct ec_params_vbnvcontext {
	uint32_t op;                          /* 0 = READ, 1 = WRITE */
	uint8_t block[EC_VBNV_BLOCK_SIZE];    /* 16 B; WRITE only */
} __ec_align4;

struct ec_response_vbnvcontext {
	uint8_t block[EC_VBNV_BLOCK_SIZE];    /* READ only */
} __ec_align4;
```

- WRITE persists to the EC's NV storage.
- Errors: `EC_RES_ERROR` on storage failure / unknown `op`.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`VBNV_CONTEXT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1661) (0x17) | ✅ v0+v1 — [`host_command_vbnvcontext`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1155) | ❌ **REMOVED** — handler *and* the `EC_CMD_VBNV_CONTEXT` wire define are gone from [EC-main]'s `include/ec_commands.h` (dead command; the kernel header keeps it) | ❌ removed |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.4 | 2015-10 | driver introduced ([`18800fc7a04e`](https://github.com/torvalds/linux/commit/18800fc7a04e7df8a345e7ef4fc3064368276f83)) |
| v5.1 | 2019-02 | split into its own MFD-cell driver ([`acb9900f9e80`](https://github.com/torvalds/linux/commit/acb9900f9e8074858738f48bee9a705138961258)); the `google,has-vbc-nvram` DT gate added ([`0545625baa59`](https://github.com/torvalds/linux/commit/0545625baa5981bb0a583e6a6045155936d3ea95)) |

### 7.2 [`rtc-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c) — EC real-time clock

**Functionality.** A standard RTC class device (`/dev/rtc*`) backed by the
EC's clock: read/set time, plus a wake alarm implemented with the EC's
relative alarm counter. Instantiated as MFD cell `cros-ec-rtc`, gated on
[`EC_FEATURE_RTC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1262)
(bit 27; [`cros_ec_dev.c:126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L126)).
**On gale: ❌ never instantiates** (feature bit clear) — and the 2016 EC tree
has no STM32 RTC host-command implementation at all, so enabling this means
*writing* an EC driver, not flipping a config.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe + `hwclock` read | [`EC_CMD_RTC_GET_VALUE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2893) (0x44) | [`cros_ec_rtc_read_time()` `:85`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L85) via probe [`:334`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L334) | **YES** ([`return ret` `:333`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L333)) | ❌ |
| set time | [`EC_CMD_RTC_SET_VALUE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2897) (0x46) | [`:104`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L104) | no | ❌ |
| read alarm | [`EC_CMD_RTC_GET_ALARM`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2894) (0x45) | [`:132`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L132) | no | ❌ |
| set alarm | [`EC_CMD_RTC_SET_ALARM`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2898) (0x47) | [`:184`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L184); probe window sizing [`:360`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L360) | no | ❌ |

**Command reference:**

#### `EC_CMD_RTC_GET_VALUE` (0x44) / `GET_ALARM` (0x45) / `SET_VALUE` (0x46) / `SET_ALARM` (0x47) · gale ❌ (no STM32 implementation in 2016)

- Defined: [`cros_ec_commands.h:2893`–`:2898`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2893); [`EC_RTC_ALARM_CLEAR`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2901)
- All four share
  [`struct ec_params_rtc`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2884) /
  [`struct ec_response_rtc`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2888)
  `{ uint32_t time; }` — absolute seconds for VALUE, relative seconds for
  ALARM (0 = cleared).

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`RTC_GET/SET_VALUE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2893) (0x44/0x46) | ❌ — handlers exist only in [`chip/lm4/system.c:702`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/lm4/system.c#702) and [`chip/npcx/system.c:750`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/npcx/system.c#750); **no STM32 implementation** | ❌ — no handlers left in the legacy build ([`common/rtc.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/rtc.c) is calendar helpers only) | ✅ — [`zephyr/shim/src/rtc.c:204`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/rtc.c#204)ff (all four), gated [`CONFIG_PLATFORM_EC_RTC`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig#843) (needs a DT `cros-rtc` chosen node) |
| [`RTC_GET/SET_ALARM`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2894) (0x45/0x47) | ❌ — **no handler at all** in the 2016 tree | ❌ | ✅ — same file/gate |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.16 | 2017-12 | driver introduced ([`6f2a71a31afd`](https://github.com/torvalds/linux/commit/6f2a71a31afd738af446c802e1ed40365afa55b8)) |
| v5.5 | 2019-11 | RTC range handling moved to the RTC core ([`0e8431379e3c`](https://github.com/torvalds/linux/commit/0e8431379e3c451067a49080c5ef619a0c633a8d)) |
| v6.2 | 2022-11 | alarm range limiting ([`f27efee66370`](https://github.com/torvalds/linux/commit/f27efee663701f0e93351cf052677214fed40a42)) |
| v6.6 | 2023-08 | supported-alarm-window detection ([`00c3092d881b`](https://github.com/torvalds/linux/commit/00c3092d881bc9d63dc36eecd140cdb38962c7ec)) |

### 7.3 [`cros-ec-regulator.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c) — EC-controlled voltage regulators

**Functionality.** Registers EC-managed voltage rails as standard Linux
regulators, so DT consumers (camera sensors etc. on MediaTek Chromebooks)
can enable/disable them and set voltages through the regulator framework.
Binds to DT
[`google,cros-ec-regulator`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L208)
(one node per rail). **On gale: ❌ never instantiates** (no DT node — and no
command support; the whole family post-dates gale's firmware).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: name + voltage list | [`EC_CMD_REGULATOR_GET_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5754) (0x12c) | [`:169`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L169), [fatal `:187`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L187) | **YES** | ❌ |
| enable/disable | [`EC_CMD_REGULATOR_ENABLE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5775) (0x12d) | [`:33`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L33) | no | ❌ |
| is-enabled | [`EC_CMD_REGULATOR_IS_ENABLED`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5787) (0x12e) | [`:58`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L58) | no | ❌ |
| set voltage | [`EC_CMD_REGULATOR_SET_VOLTAGE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5805) (0x12f) | [`:111`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L111) | no | ❌ |
| get voltage | [`EC_CMD_REGULATOR_GET_VOLTAGE`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5819) (0x130) | [`:85`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L85) | no | ❌ |

**Command reference:**

#### `EC_CMD_REGULATOR_*` (0x12c–0x130) · all gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:5754`–`:5827`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5754). Key structs:

```c
struct ec_params_regulator_get_info  { uint32_t index; } __ec_align4;
struct ec_response_regulator_get_info {
	char name[EC_REGULATOR_NAME_MAX_LEN];               /* 16 */
	uint16_t num_voltages;
	uint16_t voltages_mv[EC_REGULATOR_VOLTAGE_MAX_COUNT]; /* 16 */
} __ec_align2;
struct ec_params_regulator_enable      { uint32_t index; uint8_t enable; } __ec_align4;
struct ec_params_regulator_set_voltage { uint32_t index; uint32_t min_mv; uint32_t max_mv; } __ec_align4;
struct ec_response_regulator_get_voltage { uint32_t voltage_mv; } __ec_align4;
```

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`REGULATOR_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5754) (0x12c–0x130) | ❌ not in tree | ✅ — [`regulator.c:32`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/regulator.c#32)ff (thin wrappers over per-board `board_regulator_*`), gated [`CONFIG_HOSTCMD_REGULATOR`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#105) | ✅ — [`CONFIG_PLATFORM_EC_HOSTCMD_REGULATOR`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig#539) (default n), via [`CMakeLists.txt:416`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#416) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v5.9 | 2020-06 | driver introduced (for MediaTek Chromebooks) ([`8d9f8d57e023`](https://github.com/torvalds/linux/commit/8d9f8d57e023893bfa708d83e3a787e77766a378)) |
| v6.0 | 2022-06 | switched to the common `cros_ec_cmd()` helper ([`015cd0043503`](https://github.com/torvalds/linux/commit/015cd0043503a1691ba28529e21478fe0822f3ff)) |
| v7.1 | 2026-03 | regulator-supply support ([`411eb30f1382`](https://github.com/torvalds/linux/commit/411eb30f13823c37cd20d7c0fb7d5c8bdb1d844d)) |

### 7.4 [`i2c-cros-ec-tunnel.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c) — I2C bus tunnelled through the EC

**Functionality.** Registers a Linux I2C adapter whose transfers are relayed
by the EC onto one of *its* I2C buses — how Chromebooks reach devices that
hang off the EC (sensors, battery gas gauge) from the AP. Binds to DT
[`google,cros-ec-i2c-tunnel`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c#L296);
[probe issues no command](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c#L242)
(reads the `google,remote-bus` property). **On gale: ❌ never instantiates**
(no DT node) — and permanently moot: gale's EC is an I2C *slave* with no
downstream bus to tunnel to.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| every I2C transfer | [`EC_CMD_I2C_PASSTHRU`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4010) (0x9e) | [`ec_i2c_xfer()` `:211`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c#L211) | no (runtime only) | ⚠️ |

**Command reference:**

#### `EC_CMD_I2C_PASSTHRU` (0x9e) · gale ⚠️ addable (moot — no downstream bus)

- Defined: [`cros_ec_commands.h:4010`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4010); flags [`EC_I2C_FLAG_READ`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4013), status codes [`EC_I2C_STATUS_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4018)

```c
struct ec_params_i2c_passthru_msg {
	uint16_t addr_flags;   /* 7/10-bit addr | EC_I2C_FLAG_READ */
	uint16_t len;
} __ec_align2;
struct ec_params_i2c_passthru {
	uint8_t port;
	uint8_t num_msgs;
	struct ec_params_i2c_passthru_msg msg[];
	/* write data concatenated after */
} __ec_align2;
struct ec_response_i2c_passthru {
	uint8_t i2c_status;    /* EC_I2C_STATUS_NAK / _TIMEOUT */
	uint8_t num_msgs;
	uint8_t data[];        /* read data concatenated */
} __ec_align1;
```

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`I2C_PASSTHRU`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4010) (0x9e) | ⚠️ off — [`i2c_command_passthru`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/i2c.c#701) (v0) exists, gated [`CONFIG_I2C_MASTER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#49); gale is I2C slave-only | ✅ — [`i2c_passthru.c:260`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/i2c_passthru.c#260), gated [`CONFIG_I2C_CONTROLLER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#109) | ✅ — [`CONFIG_PLATFORM_EC_I2C`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.i2c#5) (default y when DT declares named I2C ports), via [`CMakeLists.txt:418`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#418) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v3.16 | 2014-06 | driver introduced ([`9d230c9e4f4e`](https://github.com/torvalds/linux/commit/9d230c9e4f4e67cb1c1cb9e0f6142da16b0f2796)) — one of the oldest EC consumers |
| v3.18 | 2014-09 | OF match table ([`6c97c9c1acfc`](https://github.com/torvalds/linux/commit/6c97c9c1acfce89cce2f239f0325786f95aea848)) |
| v5.5 | 2019-11 | ACPI binding ([`9af1563a5486`](https://github.com/torvalds/linux/commit/9af1563a54865a2973d4c0cbeaa95809cf4b14e0)) |
| 2025-04 | — | probe deferral when the parent EC isn't ready ([`424eafe65647`](https://github.com/torvalds/linux/commit/424eafe65647a8d6c690284536e711977153195a)) |

### 7.5 [`leds-cros_ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c) — EC-controlled LEDs

**Functionality.** Registers each EC-managed LED (battery/power/etc.) as a
multicolour LED class device, including the "automatic" EC-controlled mode
as an LED trigger. Instantiated as MFD cell `cros-ec-led`, gated on
[`EC_FEATURE_LED`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1209)
(bit 5; [`cros_ec_dev.c:141`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L141)).
Probe queries each LED and treats `-EOPNOTSUPP` as
[`-ENODEV` `:189`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L189).
**On gale: ❌ never instantiates** (feature bit clear — gale drives its RGB
ring from the AP via an lp5523 on i2c-1, not through the EC).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: query LED capabilities | [`EC_CMD_LED_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2110) (0x29) v1, `QUERY` flag | [`cros_ec_led_send_cmd()` `:75`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L75) from probe [`:186`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L186) | **YES** | ⚠️ |
| set brightness / auto mode | [`EC_CMD_LED_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2110) (0x29) v1 | [`:99`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L99)/[`:129`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L129) | no | ⚠️ |

**Command reference:**

#### `EC_CMD_LED_CONTROL` (0x29) · gale ⚠️ addable (no EC-driven LED hardware)

- Defined: [`cros_ec_commands.h:2110`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2110); [`enum ec_led_id`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2112), [`enum ec_led_colors`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2138), flags [`EC_LED_FLAGS_QUERY`/`_AUTO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2135)

```c
struct ec_params_led_control {
	uint8_t led_id;                          /* enum ec_led_id */
	uint8_t flags;                           /* EC_LED_FLAGS_QUERY / _AUTO */
	uint8_t brightness[EC_LED_COLOR_COUNT];  /* 6: R G B YELLOW WHITE AMBER */
} __ec_align1;
struct ec_response_led_control {
	uint8_t brightness_range[EC_LED_COLOR_COUNT];  /* 0=absent 1=on/off >1=PWM */
} __ec_align1;
```

- Errors: `EC_RES_INVALID_PARAM` for an unknown `led_id`.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`LED_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2110) (0x29) | ⚠️ off — [`led_command_control`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/led_common.c#73) (v1) exists, gated [`CONFIG_LED_COMMON`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#55) | ✅ — [`led_common.c:97`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/led_common.c#97) | ✅ — [`CONFIG_PLATFORM_EC_LED_COMMON`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.led#5) or the DT-based [`CONFIG_PLATFORM_EC_LED_DT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.led_dt#5) (default y with a `cros-ec-led-policy` DT node) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v6.11 | 2024-06 | driver introduced ([`8d6ce6f3ec9d`](https://github.com/torvalds/linux/commit/8d6ce6f3ec9d5f384e3eac92e43cfeac7a36e6b1)) — like gpio-cros-ec, a recent driver over an old command |
| v6.19 | 2025-11 | skips LEDs without colour components ([`4dbf066d965c`](https://github.com/torvalds/linux/commit/4dbf066d965cd3299fb396f1375d10423c9c625c)) |

### 7.6 [`cros_ec_lightbar.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lightbar.c) — Google Pixel (2013) lightbar

**Functionality.** sysfs interface (`brightness`, `led_rgb`, `sequence`,
`program`) for the four-LED lightbar of the 2013 Chromebook Pixel — a
single-device legacy feature. Instantiated as MFD cell `cros-ec-lightbar`,
gated on
[`EC_FEATURE_LIGHTBAR`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1207)
**or** DMI product "Link"
([`cros_ec_dev.c:267`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L267)).
The probe checks
[`get_lightbar_version()` `:549`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lightbar.c#L549)
and treats `INVALID_COMMAND` as
["no lightbar" `:150`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lightbar.c#L150)
→ `-ENODEV`. **On gale: ❌** (no feature bit, no hardware).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: version check; all attribute accesses | [`EC_CMD_LIGHTBAR_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1803) (0x28), subcommand-multiplexed | [`:549`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lightbar.c#L549) and per-attribute | **YES** (clean `-ENODEV`) | ⚠️ |

**Command reference:**

#### `EC_CMD_LIGHTBAR_CMD` (0x28) · gale ⚠️ addable (hardware absent — moot)

- Defined: [`cros_ec_commands.h:1803`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1803)
- Subcommand-multiplexed: request
  [`struct ec_params_lightbar`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1973) /
  response
  [`struct ec_response_lightbar`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2022) —
  unions selected by
  [`enum lightbar_command`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2069)
  (dump / on / off / brightness / rgb / seq / program / …).

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`LIGHTBAR_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1803) (0x28) | ⚠️ off — [`lpc_cmd_lightbar`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/lightbar.c#1895) exists, gated `HAS_TASK_LIGHTBAR` | ❌ **REMOVED** — `common/lightbar.c` deleted; [`build.mk:213`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#213) is a dangling reference | ❌ removed |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.1 | 2015-02 | sysfs interface introduced ([`f3f837e52b14`](https://github.com/torvalds/linux/commit/f3f837e52b14bf84c2db65f622b5c31cd261100c)) |
| v4.13 | 2017-06 | `program` upload ([`be3ebebf4377`](https://github.com/torvalds/linux/commit/be3ebebf4377fe924f0419f78fc82cf01a31e692)) and suspend/resume sequences ([`405c84308c43`](https://github.com/torvalds/linux/commit/405c84308c4335ee7cb58b9304b77b85e61f7129)) |
| v5.1 | 2019-02 | split into its own MFD-cell driver ([`ecf8a6cd949e`](https://github.com/torvalds/linux/commit/ecf8a6cd949ef236ce435ae488ceb6b3354e677e)) |
| v7.0 | 2026-01 | large-sequence support ([`9600b8bdbfe4`](https://github.com/torvalds/linux/commit/9600b8bdbfe48bb51865be743450160577d2bae2)) — still maintained despite the EC side being deleted upstream |

### 7.7 [`cros_ec_sensorhub.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub.c) (+ [`cros_ec_sensorhub_ring.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c)) and the IIO sensor family

**Functionality.** The sensor hub enumerates the EC's motion sensors and
spawns one IIO platform device per sensor (accelerometer, gyro, magnetometer,
light, barometer, lid angle — the drivers listed in
[§2.6](#26-sensor-stack-children-instantiated-by-cros-ec-sensorhub)), plus a
timestamp-synchronised FIFO ("ring") fed by MKBP events. Instantiated as MFD
cell `cros-ec-sensorhub`, gated on
[`cros_ec_get_sensor_count() > 0`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L237).
**On gale: ❌ structurally unreachable, twice over** — the sensor count
probe fails (no `MOTION_SENSE_CMD`; the fallback is an
[LPC-memmap read requiring `cmd_readmem`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L981),
absent on I2C) so the cell is never created, and even if it were, the FIFO
needs MKBP events which gale also lacks
([§3.2](#32-core-bring-up-cros_ec--cros_ec_proto)).

**Host commands used** — the whole family speaks one command,
[`EC_CMD_MOTION_SENSE_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2235)
(0x2b), multiplexed by
[`enum motionsense_command`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2238)
via [`struct ec_params_motion_sense`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2523) /
[`struct ec_response_motion_sense`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2690):

| Subcommand | Used by | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| version probe ([`EC_CMD_GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065) for 0x2b) | sensors core | [`cros_ec_sensors_core.c:44`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L44)/[`:268`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L268) | **YES** ([`:272`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L272)) | ✅ (but reports 0x2b unknown) |
| `DUMP` (0) | MFD gate; accel_legacy | [`cros_ec_proto.c:961`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L961); [`cros_ec_accel_legacy.c:54`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/accel/cros_ec_accel_legacy.c#L54) | gate | ❌ |
| `INFO` (1) | sensors core probe | [`:285`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L285) | **YES** ([`:288`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L288)) | ❌ |
| `EC_RATE` (2), `SENSOR_ODR` (3), `SENSOR_RANGE` (4), `DATA` (6), `PERFORM_CALIB` (10), `SENSOR_OFFSET` (11), `LID_ANGLE` (14), `SENSOR_SCALE` (18) | IIO drivers' sysfs + reads | e.g. [`cros_ec_sensors.c:58`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors.c#L58), [`cros_ec_light_prox.c:82`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/light/cros_ec_light_prox.c#L82), [`cros_ec_baro.c:59`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/pressure/cros_ec_baro.c#L59), [`cros_ec_lid_angle.c:57`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_lid_angle.c#L57) | no | ❌ |
| `FIFO_INFO` (7), `FIFO_READ` (8), `FIFO_INT_ENABLE` (9) | sensorhub ring | [`cros_ec_sensorhub_ring.c:1037`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L1037)/[`:846`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L846)/[`:120`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L120) | `FIFO_INFO` fatal in [`ring_add` `:1042`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L1042) | ❌ |

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`MOTION_SENSE_CMD`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2235) (0x2b) | ⚠️ off — [`host_cmd_motion_sense`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/motion_sense.c#1194) (v1|v2) exists, gated `HAS_TASK_MOTIONSENSE` (gale has no sensors — moot) | ✅ v1-v4 — [`motion_sense.c:1646`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/motion_sense.c#1646), gated [`HAS_TASK_MOTIONSENSE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#214) | ✅ — [`CONFIG_PLATFORM_EC_MOTIONSENSE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.motionsense#5) (default y with motionsense DT nodes), via [`CMakeLists.txt:476`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#476) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.10 | 2016-10 | IIO sensor family introduced (`cros_ec_sensors_core.c` [`974e6f02e27e`](https://github.com/torvalds/linux/commit/974e6f02e27e1b46c6c5e600e70ced25079f73eb), `cros_ec_sensors.c` [`c14dca07a31d`](https://github.com/torvalds/linux/commit/c14dca07a31dac8bd91aa818df62fb3bf1d846c5)) — originally enumerated by the MFD directly |
| v5.5 | 2019-11 | `cros_ec_sensorhub.c` created; sensor registration moved behind it ([`53067471188c`](https://github.com/torvalds/linux/commit/53067471188c4066fc393ab892d0a74482eac000), [`d60ac88a62df`](https://github.com/torvalds/linux/commit/d60ac88a62df71cb12b2d60d2dae5658fb4eab43)) |
| v5.7 | 2020-03 | FIFO/ring buffer with timestamp spreading ([`145d59baff59`](https://github.com/torvalds/linux/commit/145d59baff5944b71551ac518d7fd7d377a9c820)); IIO drivers register through the sensorhub FIFO ([`aa984f1ba4a4`](https://github.com/torvalds/linux/commit/aa984f1ba4a477c8ea39d2fa975a4f8de8a126e9)) |
| v6.17 | 2025-06 | retries for sensors that aren't ready at probe ([`981d7f91aeda`](https://github.com/torvalds/linux/commit/981d7f91aeda17424b29f033249f4fa7cd2a7556)) |
| post-6.12 | — | new `cros_ec_activity.c` IIO child for body-detection events ([§2.7](#27-added-after-612-current-mainline--v711)) |

---

## 8. Other upstream consumers (not in the gale image)

Listed for completeness — every remaining kernel driver that can talk to a
ChromeOS EC, none of which is shipped (or instantiable) on gale. Sections
here follow the same template but summarise runtime detail where a driver
can never apply to gale.

### 8.1 [`cros_ec_keyb.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c) — matrix keyboard / buttons / switches

**Functionality.** The Chromebook keyboard driver: an input device fed by
MKBP key-matrix events, plus buttons (power/volume) and switches (lid,
tablet mode). Binds to DT
[`google,cros-ec-keyb(-switches)`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L767)
/ ACPI `GOOG0007`. Key events arrive via
[`EC_CMD_GET_NEXT_EVENT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3355)
fetched by the core ([§3.2](#32-core-bring-up-cros_ec--cros_ec_proto)); the
driver itself issues only `MKBP_INFO`. **On gale: ❌** — not shipped, no DT
node, and no MKBP support in the EC.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: query supported/current buttons & switches | [`EC_CMD_MKBP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166) (0x61) v1 | [`cros_ec_keyb_info()` `:368`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L368), used at [`:476`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L476) | partly — [`-ENOPROTOOPT` → "0 buttons/switches" `:377`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L377) is tolerated (old-EC path); other errors fatal ([`:732`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L732)) | ⚠️ |

**Command reference:**

#### `EC_CMD_MKBP_INFO` (0x61) · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:3166`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166); [`enum ec_mkbp_info_type`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3180)

```c
struct ec_params_mkbp_info  { uint8_t info_type; uint8_t event_type; } __ec_align1;   /* v1 */
struct ec_response_mkbp_info { uint32_t rows; uint32_t cols; uint8_t reserved; } __ec_align_size1;  /* v0 */
```

- v1 responses vary by `info_type` (matrix size / supported masks / current
  state).

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`MKBP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166) (0x61) | ⚠️ off — [`keyboard_get_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/keyboard_mkbp.c#226) (**v0 only** — the v1 form this driver needs post-dates 2016), gated `CONFIG_KEYBOARD_PROTOCOL_MKBP` | ✅ v0+v1 — [`mkbp_info.c:154`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/mkbp_info.c#154) | ✅ — [`CONFIG_MKBP_PROTOCOL`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig#618) (selected by the MKBP keyboard/input configs), via [`CMakeLists.txt:446`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#446) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v3.10 | 2013-04 | driver introduced — the same release as the EC core itself ([`6af6dc2d2aa6`](https://github.com/torvalds/linux/commit/6af6dc2d2aa654e928ed0a64c28724d1cd2c36c1)) |
| v4.11 | 2017-02 | non-matrix buttons/switches ([`cdd7950e7aa4`](https://github.com/torvalds/linux/commit/cdd7950e7aa4a4d0d8ba71e3967aae6d25d09b03)) and tablet-mode switch ([`6ccc3a33810e`](https://github.com/torvalds/linux/commit/6ccc3a33810e8ec09936fa990c13370d9f61606f)) — the `MKBP_INFO` v1 machinery |
| v5.12 | 2021-02 | function-row physical map exposed ([`820c8727956d`](https://github.com/torvalds/linux/commit/820c8727956da82b7a841c299fabb2fdca9a37d4)) |
| v7.1 | 2026-02 | function-key support ([`d8df89904cb4`](https://github.com/torvalds/linux/commit/d8df89904cb46bd7995db1dda3405cbbe34247d7)) |

### 8.2 [`cros_ec_mkbp_proximity.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c) — MKBP proximity sensor

**Functionality.** An IIO proximity device backed by the EC's front
proximity sensor, delivered as an MKBP *switch* bit rather than a motion
sensor. Binds to DT
[`google,cros-ec-mkbp-proximity`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c#L251);
[command-free probe](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c#L207).
**On gale: ❌** (not shipped, no node, no MKBP).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| read the front-proximity switch bit | [`EC_CMD_MKBP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166) (0x61) v1 | [`:75`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c#L75) | no (read path) | ⚠️ |

**EC firmware support:** identical to
[§8.1](#81-cros_ec_keybc--matrix-keyboard--buttons--switches) (same single
command).

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v5.13 | 2021-03 | driver introduced ([`7792225b7b67`](https://github.com/torvalds/linux/commit/7792225b7b671800d1c9b562ace8e167a3d0e2e7)); no functional additions since — later commits are API modernisations |

### 8.3 [`hid-google-hammer.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c) — detachable-base HID ("hammer") + base-attached switch

**Functionality.** HID driver for Google detachable keyboards ("hammer"
family); its EC-facing half (`cbas_ec`) tracks the base-attached switch so
the OS knows whether the keyboard base is connected. Binds to DT
[`google,cros-cbas`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c#L280)
/ ACPI `GOOG000B`. **On gale: ❌** (not shipped, no node, no MKBP).

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: base-attached switch support | [`EC_CMD_MKBP_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166) (0x61) v1 | [`:185`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c#L185) | **YES** ([`-ENXIO` if unsupported `:189`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c#L189)) | ⚠️ |

**EC firmware support:** identical to
[§8.1](#81-cros_ec_keybc--matrix-keyboard--buttons--switches) (same single
command).

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.17 | 2018-03 | HID driver introduced ([`bc774b8c110f`](https://github.com/torvalds/linux/commit/bc774b8c110f7d90d13257b95b5a22f5bb7fd71b)) |
| v4.20 | 2018-10 | the `cbas_ec` base-attached/tablet-mode switch machinery — the EC-facing half ([`eb1aac4c8744`](https://github.com/torvalds/linux/commit/eb1aac4c8744f75460c34d71b0c73bebf3e8ee5c)) |
| v5.5 | 2019-10 | base-folded detection generalised beyond whiskers ([`20c55f250618`](https://github.com/torvalds/linux/commit/20c55f250618d4d110b27410a8ffd2c02a0e6911)) |
| v5.18 | 2022-03 | vivaldi keyboard-layout support ([`a9d672998a33`](https://github.com/torvalds/linux/commit/a9d672998a33e4bccdf62f6c2f8a47d51893b83f)) |

### 8.4 [`cros-ec-cec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c) — HDMI CEC

**Functionality.** Registers the EC's HDMI-CEC controller(s) with the kernel
CEC framework (`/dev/cecN`) so userspace can exchange CEC messages with a TV
(Chromebox-for-meetings hardware). Received messages arrive as MKBP CEC
events. Instantiated as MFD cell `cros-ec-cec`, gated on
[`EC_FEATURE_CEC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1278)
(bit 35; [`cros_ec_dev.c:116`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L116)).
**On gale: ❌** — not shipped, feature bit clear, and the whole CEC command
family post-dates 2016.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: port count | [`EC_CMD_CEC_PORT_COUNT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4611) (0xc1) | [`:378`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L378) | no ([fallback to 1 port `:380`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L380)) | ❌ |
| probe: pick `CEC_WRITE_MSG` version | [`EC_CMD_GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065) (0x08) | [`:416`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L416)/[`:514`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L514) | **YES** | ✅ (but `CEC_WRITE_MSG` unknown) |
| set logical address / enable | [`EC_CMD_CEC_SET`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4569) (0xba) | [`:181`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L181)/[`:236`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L236) | no | ❌ |
| transmit a message | [`EC_CMD_CEC_WRITE_MSG`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4525) (0xb8) | [v0 `:204` / v1 `:210`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L204) | no | ❌ |
| fetch a received message | [`EC_CMD_CEC_READ_MSG`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4548) (0xb9) | [`:107`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L107), on the `EC_MKBP_CEC_HAVE_DATA` event | no | ❌ |

**Command reference** — key structures:
[`struct ec_params_cec_write`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4531)
`{ uint8_t msg[16]; }` /
[v1](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4541)
adds `port` + `msg_len`;
[`struct ec_response_cec_read`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4563)
`{ uint8_t msg_len; uint8_t msg[16]; }`;
[`struct ec_params_cec_set`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4580)
`{ uint8_t cmd; uint8_t port; uint8_t val; }`;
[`struct ec_response_cec_port_count`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4617)
`{ uint8_t port_count; }`.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`CEC_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4525) (0xb8–0xc1) | ❌ not in tree (CEC added 2018+) | ✅ — [`cec.c:278`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/cec.c#278)ff, gated [`CONFIG_CEC`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#53) | ✅ — [`CONFIG_PLATFORM_EC_CEC`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.cec#5) (default n), via [`CMakeLists.txt:359`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#359) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.19 | 2018-07 | driver introduced as `drivers/media/platform/cros-ec-cec/` ([`cd70de2d356e`](https://github.com/torvalds/linux/commit/cd70de2d356ee692477276bd5d6bc88c71a48733)) |
| v5.8 | 2020 | moved to `drivers/media/cec/platform/cros-ec/` ([`4be5e8648b0c`](https://github.com/torvalds/linux/commit/4be5e8648b0c287aefc6ac3f3a0b12c696054f43)) |
| v6.7 | 2023-09 | multi-port rework — per-port array ([`4d0e179a4287`](https://github.com/torvalds/linux/commit/4d0e179a42879f7d76a5b95a2e7e7a5afa33954a)) + `CEC_PORT_COUNT` query ([`5d227f02ceb9`](https://github.com/torvalds/linux/commit/5d227f02ceb9cc120cf04efbd77e12da182a5f62)) |

### 8.5 [`pwm-cros-ec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c) — EC PWM channels

**Functionality.** A Linux PWM chip whose channels are EC-controlled PWMs
(display backlight on some Chromebooks); consumers reference it from DT like
any PWM provider. Binds to DT
[`google,cros-ec-pwm(-type)`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L269).
**On gale: ❌** — not shipped, no node, and the generic PWM commands don't
exist in 2016 firmware.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: count channels (loop until error); read duty | [`EC_CMD_PWM_GET_DUTY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1785) (0x26) | [`:101`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L101), probing loop [`:191`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L191) | **YES** ([`:231`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L231)) | ❌ |
| set duty | [`EC_CMD_PWM_SET_DUTY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1765) (0x25) | [`:63`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L63) | no | ❌ |

**Command reference:**

#### `EC_CMD_PWM_SET_DUTY` (0x25) / `EC_CMD_PWM_GET_DUTY` (0x26) · gale ❌ absent-in-2016

- Defined: [`cros_ec_commands.h:1765`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1765)/[`:1785`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1785); [`enum ec_pwm_type`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1769), [`EC_PWM_MAX_DUTY` = 0xffff](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1767)

```c
struct ec_params_pwm_set_duty { uint16_t duty; uint8_t pwm_type; uint8_t index; } __ec_align4;
struct ec_params_pwm_get_duty { uint8_t pwm_type; uint8_t index; } __ec_align1;
struct ec_response_pwm_get_duty { uint16_t duty; } __ec_align2;
```

([set](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1779) /
[get params](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1787) /
[get response](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1792))

- The probe loop relies on `EC_RES_INVALID_PARAM` for an out-of-range
  `index` to terminate channel counting.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`PWM_SET/GET_DUTY`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1765) (0x25/0x26) | ❌ not in tree (generic PWM commands added later; 2016 has only the fan/keyboard-specific ones) | ✅ — [`pwm.c:70`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#70)/[`:90`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#90), gated [`CONFIG_PWM`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#139) | ✅ — Zephyr-native reimplementation [`zephyr/shim/src/pwm_hc.c:82`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/pwm_hc.c#82)/[`:108`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/pwm_hc.c#108) under [`CONFIG_PLATFORM_EC_PWM_HC`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig#824) (`common/pwm.c` itself is **not** compiled under Zephyr) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.8 | 2016-07 | driver introduced ([`1f0d3bb02785`](https://github.com/torvalds/linux/commit/1f0d3bb02785f698dc273b9006a473194c32f874)) — contemporary with gale's firmware, but gale's EC never compiled the command |
| v5.6 | 2019-12 | duty-cycle caching ([`1db37f9561b2`](https://github.com/torvalds/linux/commit/1db37f9561b2b3f57d84b6253a9cd97f6289f8e1)) |
| v5.19 | 2022-05 | channel-type support (`google,cros-ec-pwm-type`) ([`3d593b6e80ad`](https://github.com/torvalds/linux/commit/3d593b6e80ad2c911b5645af28d83eabb96e7c1b)) |

### 8.6 [`cros_kbd_led_backlight.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_kbd_led_backlight.c) — keyboard backlight

**Functionality.** A LED-class device (`chromeos::kbd_backlight`) for the
keyboard backlight, with percent brightness set/get through the EC.
Instantiated as MFD cell `cros-keyboard-leds` gated on
[`EC_FEATURE_PWM_KEYB`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1203)
(bit 3; [`cros_ec_dev.c:146`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L146)),
with DT/ACPI binding variants. **On gale: ❌** — not shipped, feature bit
clear, no backlight hardware.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| set brightness | [`EC_CMD_PWM_SET_KEYBOARD_BACKLIGHT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1745) (0x23) | [`:140`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_kbd_led_backlight.c#L140) | no | ⚠️ |
| get brightness | [`EC_CMD_PWM_GET_KEYBOARD_BACKLIGHT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1736) (0x22) | [`:162`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_kbd_led_backlight.c#L162) | no | ⚠️ |

**Command reference:** request/response structs
[`ec_params_pwm_set_keyboard_backlight`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1747)
`{ uint8_t percent; }` and
[`ec_response_pwm_get_keyboard_backlight`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1738)
`{ uint8_t percent; uint8_t enabled; }`.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`PWM_GET/SET_KEYBOARD_BACKLIGHT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1736) (0x22/0x23) | ⚠️ off — [`pwm_kblight.c:60`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pwm_kblight.c#60), gated `CONFIG_PWM_KBLIGHT` (no backlight hardware — moot) | ✅ — [`keyboard_backlight.c:190`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/keyboard_backlight.c#190)/[`:204`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/keyboard_backlight.c#204), gated [`CONFIG_KEYBOARD_BACKLIGHT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#141) | ✅ — [`CONFIG_PLATFORM_EC_PWM_KBLIGHT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.keyboard#289) (default y with a kblight PWM DT node) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v4.7 | 2016-05 | driver introduced (ACPI-only) ([`492ef7829d2d`](https://github.com/torvalds/linux/commit/492ef7829d2d09428803bffb187d5781bbc12ca5)) |
| v6.0 | 2022-06 | EC-PWM backend ([`40f58143745e`](https://github.com/torvalds/linux/commit/40f58143745eaabc68ef44b068642ca3b38d23a6)) and OF match ([`fd1e8054ff69`](https://github.com/torvalds/linux/commit/fd1e8054ff6985cfcbdf66a6de88cf1c47a14f46)) |
| v6.11 | 2024-06 | MFD-cell binding (the `EC_FEATURE_PWM_KEYB` gate) ([`baa19b650794`](https://github.com/torvalds/linux/commit/baa19b650794d58d01ec3ea03c63eb4ae0fa9d84)) |

### 8.7 [`cros_ec_codec.c`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c) — EC audio codec (DMIC/I2S/WoV)

**Functionality.** An ASoC codec whose DMIC capture path and wake-on-voice
engine live on the EC; the AP configures gains and I2S routing over host
commands and even shares memory for voice data. Binds to DT
[`google,cros-ec-codec`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L1040)
/ ACPI `GOOG0013`. **On gale: ❌** — not shipped, no node, no commands. A
command family that was **born and died entirely between gale's firmware and
today**: absent in 2016, and the handlers have been deleted from [EC-main]
as well.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: capabilities | [`EC_CMD_EC_CODEC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4642) (0xbc) `GET_CAPABILITIES` | [`:1007`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L1007), [fatal `:1010`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L1010) | **YES** | ❌ |
| DMIC gain control | [`EC_CMD_EC_CODEC_DMIC`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4706) (0xbd) | via [`send_ec_host_command()` `:74`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L74) | no | ❌ |
| I2S RX config | [`EC_CMD_EC_CODEC_I2S_RX`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4762) (0xbe) | same helper | no | ❌ |
| wake-on-voice | [`EC_CMD_EC_CODEC_WOV`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4824) (0xbf) | same helper | no | ❌ |

(Structure definitions span
[`cros_ec_commands.h:4642`–`:4881`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4642) —
subcommand unions per family member.)

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`EC_CODEC_*`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4642) (0xbc–0xbf) | ❌ not in tree | ❌ **REMOVED** — defines remain in [EC-main]'s `ec_commands.h` but no handler exists anywhere | ❌ removed |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v5.1 | 2019-01 | codec driver introduced ([`b291f42a3718`](https://github.com/torvalds/linux/commit/b291f42a37187cbd78ff59a34f2751164baad8bf)) |
| v5.5 | 2019-10 | I2S RX refactor ([`727f1c71c780`](https://github.com/torvalds/linux/commit/727f1c71c780789aeb8f3da2596c65ae008d5d6c)), wake-on-voice ([`b6bc07d4360d`](https://github.com/torvalds/linux/commit/b6bc07d4360dbf766e551f18e43c67fff6784955)), ACPI binding ([`877167ef343d`](https://github.com/torvalds/linux/commit/877167ef343de2a9be3d31cdd5c41122e61190dd)) |

### 8.8 [`cros_ec_wdt.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c) — EC watchdog

**Functionality.** A standard watchdog device (`/dev/watchdog*`) backed by
the EC's AP-hang-detect timer: userspace pings it, and if the AP stops
pinging, the EC reboots it. Instantiated as MFD cell `cros-ec-wdt`, gated on
[`EC_FEATURE_HANG_DETECT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1246)
(bit 19; [`cros_ec_dev.c:136`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L136)).
**On gale: ❌ never instantiates** — and beware the trap below: gale's 2016
tree *has* a `HANG_DETECT` command, but a wire-incompatible one.

**Host commands used** — everything is one command,
[`EC_CMD_HANG_DETECT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4044)
(0x9f), subcommand-multiplexed
([sent from `cros_ec_wdt_send_cmd()` `:43`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c#L43)):

| Use | Subcommand | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: read boot status | `EC_HANG_DETECT_CMD_GET_STATUS` | [`:138`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c#L138) | **YES** | ❌ |
| probe: clear status | `EC_HANG_DETECT_CMD_CLEAR_STATUS` | [`:152`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c#L152) | **YES** | ❌ |
| runtime: arm / ping / stop | `SET_TIMEOUT` / `RELOAD` / `CANCEL` | [`:59`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c#L59)ff | no | ❌ |

**Command reference:**

#### `EC_CMD_HANG_DETECT` (0x9f) · gale ⚠️* (2016 has a wire-incompatible predecessor)

- Defined: [`cros_ec_commands.h:4044`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4044); subcommands [`enum ec_hang_detect_cmds`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4050)

```c
struct ec_params_hang_detect  { uint16_t command; uint16_t reboot_timeout_sec; } __ec_align2;
struct ec_response_hang_detect { uint8_t status; } __ec_align1;
```

- **The trap:** the 2016 tree's `0x9f`
  ([`ap_hang_detect.c:203`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/ap_hang_detect.c#203),
  gated `CONFIG_AP_HANG_DETECT`, off on gale) speaks the **old flag-based
  API** (`{u32 flags; u16 timeout; u16 warn}`) — same command number,
  different wire format. Enabling the 2016 config would *not* make this
  driver work; the modern cmd-based handler must be ported.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`HANG_DETECT`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4044) (0x9f) | ⚠️* off + **wire-incompatible** old flag API ([`ap_hang_detect.c:203`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/ap_hang_detect.c#203)) | ✅ modern cmd API — [`ap_hang_detect.c:132`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/ap_hang_detect.c#132), gated [`CONFIG_AP_HANG_DETECT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/build.mk#36) | ✅ — [`CONFIG_PLATFORM_EC_AP_HANG_DETECT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.ap_hang_detect#5) (default n), via [`CMakeLists.txt:761`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#761) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v6.9 | 2024-02 | driver introduced ([`843dac4d3687`](https://github.com/torvalds/linux/commit/843dac4d3687f7628ba4f76e1481ee3838b27a35)) — built for the modern cmd-based `HANG_DETECT` API only; minor fixes since |

### 8.9 [`cros_charge-control.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_charge-control.c) — charge behaviour / battery sustainer

**Functionality.** sysfs knobs (`charge_behaviour`,
`charge_control_start/end_threshold`) on the battery power_supply for
limiting or inhibiting charging — the "battery sustainer" on Chromebooks.
Instantiated as MFD cell `cros-charge-control`, gated on
[`EC_FEATURE_CHARGER`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1237)
(bit 16; [`cros_ec_dev.c:151`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L151)).
**On gale: ❌** — not shipped, feature bit clear, no battery.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: pick `CHARGE_CONTROL` version (v1/v2/v3) | [`EC_CMD_GET_CMD_VERSIONS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1065) (0x08) | [`:310`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_charge-control.c#L310) | **YES** | ✅ (but reports 0x96 unknown) |
| probe + sysfs writes: set mode/thresholds | [`EC_CMD_CHARGE_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3845) (0x96) | probe [`:347`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_charge-control.c#L347) | **YES** | ⚠️ |

**Command reference:**

#### `EC_CMD_CHARGE_CONTROL` (0x96) · gale ⚠️ addable (no battery — moot)

- Defined: [`cros_ec_commands.h:3845`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3845); [`enum ec_charge_control_mode`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3848)

```c
struct ec_params_charge_control {
	uint32_t mode;         /* NORMAL / IDLE / DISCHARGE */
	uint8_t cmd;           /* v2+: SET / GET */
	uint8_t flags;         /* v3+ */
	struct { int8_t lower; int8_t upper; } sustain_soc;
} __ec_align4;
```

- **Version drift warning:** the request layout *grew* across versions (v1 =
  `mode` only); a v0/v1-only EC and a v2/v3-only EC both answer command 0x96
  with different wire formats.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`CHARGE_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3845) (0x96) | ⚠️ off — [`charge_command_charge_control`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_state_v1.c#1004) (**v0/v1 only**), gated `CONFIG_CHARGER_V1/V2` | ✅ **v2/v3 only — v0/v1 dropped** ([`charge_state.c:2033`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_state.c#2033)); a silent wire-format generation gap | ✅ — [`CONFIG_PLATFORM_EC_CHARGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.charger#5) (default y on battery builds), via [`CMakeLists.txt:320`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/CMakeLists.txt#320) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v6.11 | 2024-07 | driver introduced ([`c6ed48ef5259`](https://github.com/torvalds/linux/commit/c6ed48ef52599098498a8442fd60bea5bd8cd309)) |
| v6.13 | 2024-12 | start-threshold hidden on v2-only ECs — the wire-format generations surface in the UI ([`c28dc9fc24f5`](https://github.com/torvalds/linux/commit/c28dc9fc24f5fa802d44ef7620a511035bdd803e)) |
| v6.14 | 2024-12 | reimplemented as a power-supply extension ([`bcfe7d6ba207`](https://github.com/torvalds/linux/commit/bcfe7d6ba20742bc166b293cc1a3986a0f4aaeb9)) |

### 8.10 [`cros_typec_switch.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c) — Type-C mode-switch / retimer control

**Functionality.** Registers the EC's Type-C mode switches and retimers with
the kernel's typec-mux framework, letting an AP-side Type-C stack drive
EC-owned muxes. Binds **ACPI-only**
([`GOOG001A` `:308`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L308));
[command-free probe](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L283).
**On gale: n/a** — ARM/DT platform, no ACPI, and no TCPMv2 commands.

**Host commands used:**

| Use | Command | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| set mux / clear events | [`EC_CMD_TYPEC_CONTROL`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5867) (0x132) | [`:48`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L48)/[`:79`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L79) | no | ❌ |
| poll status | [`EC_CMD_TYPEC_STATUS`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5932) (0x133) | [`:90`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L90) | no | ❌ |

**Command reference / EC firmware support:** both commands are detailed, with
their EC support, in
[§6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc).

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v6.1 | 2022-08 | driver introduced ([`affc804c44c8`](https://github.com/torvalds/linux/commit/affc804c44c8259ae53423aa3b5c20907e3a9a34)); EC retimer ([`d4536a216c3f`](https://github.com/torvalds/linux/commit/d4536a216c3f8ea0abcf90110750eb297ce48b45)) and mode-switch registration ([`9e6e05169980`](https://github.com/torvalds/linux/commit/9e6e05169980e83a870dd595012ec014a5fc440c)) in the same cycle |
| v6.5 | 2023-05 | DP pin-assignment D support ([`c9f9c6c875d1`](https://github.com/torvalds/linux/commit/c9f9c6c875d14a107dabcf4579fcab95ed30af31)) |

### 8.11 [`cros_ec_hwmon.c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c) — temperature / fan monitoring

**Functionality.** A hwmon device exposing the EC's temperature sensors and
fan tachometers (the `sensors` command output on Chromebooks). It reads the
EC's **memory map**, not regular per-reading commands — via
[`cros_ec_cmd_readmem()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L1066),
which on I2C transports falls back to
[`EC_CMD_READ_MEMMAP`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1052) (0x07).
Instantiated as **unconditional** MFD cell `cros-ec-hwmon`
([`cros_ec_dev.c:160`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L160)) —
the cell exists even on gale, but the gale image doesn't ship the module
(`SENSORS_CROS_EC=n`). **On gale: ❌ pointless anyway** — 0x07 works, but
the memory map carries no thermal data, so the thermal version reads 0 and
probe exits with a clean `-ENODEV`.

**Host commands used:**

| Use | Command / memmap offset | Call site | Probe-fatal? | gale EC |
|---|---|---|:--:|:--:|
| probe: thermal version | 0x07 read of [`EC_MEMMAP_THERMAL_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L82) | [error `:246`, version 0 → `-ENODEV` `:250`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L246) | **YES** | ✅ cmd, no data |
| temperature reads | 0x07 read of [`EC_MEMMAP_TEMP_SENSOR`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L77) | [`:49`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L49) | no | ✅ cmd, no data |
| fan speed reads | 0x07 read of [`EC_MEMMAP_FAN`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L78) | [`:31`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L31) | no | ✅ cmd, no data |
| sensor labels | [`EC_CMD_TEMP_SENSOR_GET_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3573) (0x70) | [`:210`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L210) | no | ⚠️ |

**Command reference:**

#### `EC_CMD_TEMP_SENSOR_GET_INFO` (0x70) · gale ⚠️ addable (no sensors — moot)

- Defined: [`cros_ec_commands.h:3573`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3573); structs [`:3575`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3575)
- Request `{ uint8_t id; }`; response
  `{ char sensor_name[32]; uint8_t sensor_type; }`.

**EC firmware support:**

| Command | gale EC (2016, shipped) | [EC-main] legacy build | [EC-main] Zephyr build |
|---|---|---|---|
| [`READ_MEMMAP`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1052) (0x07) | ✅ (see [§3.2](#32-core-bring-up-cros_ec--cros_ec_proto); map carries no thermal fields on gale) | ✅ | ✅ |
| [`TEMP_SENSOR_GET_INFO`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3573) (0x70) | ⚠️ off — [`temp_sensor_command_get_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/temp_sensor.c#160), gated `CONFIG_TEMP_SENSOR` | ✅ — [`temp_sensor.c:175`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/temp_sensor.c#175) | ✅ — [`CONFIG_PLATFORM_EC_TEMP_SENSOR`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/Kconfig.temperature#5) (default y with temp-sensor DT nodes) |

**Linux driver history:**

| Version | Date | Change |
|---|---|---|
| v6.11 | 2024-06 | driver introduced (read-only temps + fan RPM) ([`bc3e45258096`](https://github.com/torvalds/linux/commit/bc3e45258096f2ea2116302abefde4b1cb9bc3c1)) |
| v6.13 | 2024-11 | thermal-framework registration ([`c1fff92d808b`](https://github.com/torvalds/linux/commit/c1fff92d808bb41064b783a072dee834bcc29f33)) |
| v6.18 | 2025-09 | PWM fan control ([`fb8e659309f7`](https://github.com/torvalds/linux/commit/fb8e659309f72e54ed011c6bfe98597b9236805d)) + fans as cooling devices ([`5798b62867b4`](https://github.com/torvalds/linux/commit/5798b62867b47b6ace287d31172ce748ad70d869)) |
| v7.0 | 2026-02 | temperature thresholds via `THERMAL_GET_THRESHOLD` ([`afa7c56ec447`](https://github.com/torvalds/linux/commit/afa7c56ec447315ab38182bb9c185d8ea712c3ad); see [§2.7](#27-added-after-612-current-mainline--v711)) |

---

## 9. Command index — every command in this document

Cross-reference: command → gale status → where detailed → EC handler in both
trees. **[EC-main]-removed** rows are commands gale implements whose handlers
**no longer exist in current upstream** — the 2016↔now drift in one column.

| Cmd | Name | gale | § | EC-2016 handler | EC-main handler |
|--:|---|:--:|:--:|---|---|
| `0x00` | PROTO_VERSION | ✅ | [1.4](#14-what-gales-ec-implements--the-31-commands) | [host_command.c:436](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#436) | [host_command.c:87](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#87) |
| `0x01` | HELLO | ✅ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | [host_command.c:451](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#451) | [host_command.c:101](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#101) |
| `0x02` | GET_VERSION | ✅ | [4.1](#41-cros_ec_chardevc--devcros_ec-raw-host-command-access) | [system.c:1080](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1080) | [system.c:1731](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1731) (+v1) |
| `0x03` | READ_TEST | ✅ | — | [host_command.c:474](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#474) | **removed** |
| `0x04` | GET_BUILD_INFO | ✅ | [4.2](#42-cros_ec_sysfsc--sysclasschromeoscros_ec-attributes) | [system.c:1091](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1091) | [system.c:1771](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1771) |
| `0x05` | GET_CHIP_INFO | ✅ | [4.2](#42-cros_ec_sysfsc--sysclasschromeoscros_ec-attributes) | [system.c:1107](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1107) | [system.c:1787](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1787) |
| `0x06` | GET_BOARD_VERSION | ⚠️ | [4.2](#42-cros_ec_sysfsc--sysclasschromeoscros_ec-attributes) | [system.c:1122](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1122) (`CONFIG_BOARD_VERSION`) | [system.c:1807](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1807) |
| `0x07` | READ_MEMMAP | ✅ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | [host_command.c:500](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#500) | [host_command.c:131](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#131) |
| `0x08` | GET_CMD_VERSIONS | ✅ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | [host_command.c:524](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#524) | [host_command.c:157](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#157) |
| `0x09` | GET_COMMS_STATUS | ⚠️ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | [host_command.c:619](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#619) (`CONFIG_HOST_COMMAND_STATUS`) | [host_command.c:215](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#215) |
| `0x0b` | GET_PROTOCOL_INFO | ✅ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | [i2c-stm32f0.c:615](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#615) | per-transport Zephyr shims (e.g. [espi.c:545](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/espi.c#545)); legacy build: **none left** |
| `0x0d` | GET_FEATURES | ✅ | [3.3](#33-mfd-cros_ec_dev--the-gatekeeper) | [host_command.c:760](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#760) | [host_command.c:190](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#190) |
| `0x10` | FLASH_INFO | ✅ | [4.2](#42-cros_ec_sysfsc--sysclasschromeoscros_ec-attributes) | [flash.c:781](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#781) | [flash.c:1598](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/flash.c#1598) (+v2) |
| `0x11`-`0x16` | FLASH_READ/WRITE/ERASE/PROTECT/REGION_INFO | ✅ | [4.2](#42-cros_ec_sysfsc--sysclasschromeoscros_ec-attributes) note | [flash.c:800](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#800)ff | [flash.c:1629](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/flash.c#1629)ff (PROTECT dropped v0) |
| `0x17` | VBNV_CONTEXT | ✅ | [7.1](#71-cros_ec_vbcc--vboot-nv-context) | [system.c:1155](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1155) | **removed** |
| `0x22`/`0x23` | PWM_GET/SET_KEYBOARD_BACKLIGHT | ⚠️ | [8.6](#86-cros_kbd_led_backlightc--keyboard-backlight) | [pwm_kblight.c:60](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pwm_kblight.c#60)/[:72](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pwm_kblight.c#72) | [keyboard_backlight.c:190](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/keyboard_backlight.c#190)/[:204](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/keyboard_backlight.c#204) |
| `0x25`/`0x26` | PWM_SET/GET_DUTY | ❌ | [8.5](#85-pwm-cros-ecc--ec-pwm-channels) | not in tree | [pwm.c:70](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#70)/[:90](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#90) |
| `0x28` | LIGHTBAR_CMD | ⚠️ | [7.6](#76-cros_ec_lightbarc--google-pixel-2013-lightbar) | [lightbar.c:1895](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/lightbar.c#1895) | **removed** |
| `0x29` | LED_CONTROL | ⚠️ | [7.5](#75-leds-cros_ecc--ec-controlled-leds) | [led_common.c:73](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/led_common.c#73) | [led_common.c:97](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/led_common.c#97) |
| `0x2a` | VBOOT_HASH | ✅ | — | [vboot_hash.c:442](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/vboot_hash.c#442) | [vboot_hash.c:533](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/vboot_hash.c#533) |
| `0x2b` | MOTION_SENSE_CMD | ⚠️ | [7.7](#77-cros_ec_sensorhubc--cros_ec_sensorhub_ringc-and-the-iio-sensor-family) | [motion_sense.c:1194](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/motion_sense.c#1194) | [motion_sense.c:1646](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/motion_sense.c#1646) |
| `0x44`-`0x47` | RTC_* | ⚠️ | [7.2](#72-rtc-cros-ecc--ec-real-time-clock) | [chip-specific only](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/lm4/system.c#702) (no stm32) | [zephyr/shim/src/rtc.c:204](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/rtc.c#204)ff |
| `0x60` | MKBP_STATE | ⚠️ | — | [keyboard_mkbp.c:210](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/keyboard_mkbp.c#210) | **removed** |
| `0x61` | MKBP_INFO | ⚠️ | [8.1](#81-cros_ec_keybc--matrix-keyboard--buttons--switches) | [keyboard_mkbp.c:226](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/keyboard_mkbp.c#226) (v0 only) | [mkbp_info.c:154](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/mkbp_info.c#154) |
| `0x67` | GET_NEXT_EVENT | ⚠️ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | [mkbp_event.c:111](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/mkbp_event.c#111) | [mkbp_event.c:529](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/mkbp_event.c#529) (v0-v3) |
| `0x70` | TEMP_SENSOR_GET_INFO | ⚠️ | [8.11](#811-cros_ec_hwmonc--temperature--fan-monitoring) | [temp_sensor.c:160](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/temp_sensor.c#160) | [temp_sensor.c:175](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/temp_sensor.c#175) |
| `0x8d` | HOST_EVENT_GET_WAKE_MASK | ⚠️ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | [host_event_commands.c:205](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_event_commands.c#205) | [host_event_commands.c:550](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_event_commands.c#550) |
| `0x92` | GPIO_SET | ✅ | [5](#5-gpio-cros-ecc--ec-gpio-controller-the-one-gated-consumer-that-fully-works-on-gale) | [gpio_commands.c:274](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#274) | [gpio_commands.c:295](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#295) |
| `0x93` | GPIO_GET | ✅ | [5](#5-gpio-cros-ecc--ec-gpio-controller-the-one-gated-consumer-that-fully-works-on-gale) | [gpio_commands.c:259](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#259) | [gpio_commands.c:280](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#280) |
| `0x96` | CHARGE_CONTROL | ⚠️ | [8.9](#89-cros_charge-controlc--charge-behaviour--battery-sustainer) | [charge_state_v1.c:1004](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_state_v1.c#1004) (v0/v1) | [charge_state.c:2033](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_state.c#2033) (v2/v3!) |
| `0x97`/`0x98` | CONSOLE_SNAPSHOT/READ | ✅ | [4.3](#43-cros_ec_debugfsc--syskerneldebugcros_ec) | [uart_buffering.c:357](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#357)/[:419](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#419) | [uart_hostcmd.c:17](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#17)/[:53](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#53) |
| `0x9e` | I2C_PASSTHRU | ⚠️ | [7.4](#74-i2c-cros-ec-tunnelc--i2c-bus-tunnelled-through-the-ec) | [i2c.c:701](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/i2c.c#701) (`CONFIG_I2C_MASTER`) | [i2c_passthru.c:260](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/i2c_passthru.c#260) |
| `0x9f` | HANG_DETECT | ⚠️* | [8.8](#88-cros_ec_wdtc--ec-watchdog) | [ap_hang_detect.c:203](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/ap_hang_detect.c#203) (*old flag API — wire-incompatible*) | [ap_hang_detect.c:132](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/ap_hang_detect.c#132) |
| `0xa2` | EXTERNAL_POWER_LIMIT | ⚠️ | [6.3](#63-cros_usbpd-chargerc--usb-pd-power_supply-provider) | [charge_manager.c:960](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#960) | [charge_manager.c:1916](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1916) |
| `0xa9` | HOST_SLEEP_EVENT | ❌ | [3.2](#32-core-bring-up-cros_ec--cros_ec_proto) | not in tree | [power/host_sleep.c:90](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/power/host_sleep.c#90) |
| `0xb6` | ENTERING_MODE | ✅ | — | [host_command.c:649](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#649) | **removed** |
| `0xb8`-`0xc1` | CEC_* | ❌ | [8.4](#84-cros-ec-cecc--hdmi-cec) | not in tree | [cec.c:278](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/cec.c#278)ff |
| `0xbc`-`0xbf` | EC_CODEC_* | ❌ | [8.7](#87-cros_ec_codecc--ec-audio-codec-dmici2swov) | not in tree | **removed** (defines only) |
| `0xd2` | REBOOT_EC | ✅ | [4.2](#42-cros_ec_sysfsc--sysclasschromeoscros_ec-attributes) | [system.c:1202](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1202) | [system.c:1871](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1871) |
| `0xd3` | GET_PANIC_INFO | ✅ | [4.3](#43-cros_ec_debugfsc--syskerneldebugcros_ec) | [panic_output.c:233](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c#233) | [panic_output.c:618](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/panic_output.c#618) (v0-v2) |
| `0x101` | USB_PD_CONTROL | ✅ v0/v1 | [6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc) | [usb_pd_protocol.c:3159](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3159) | [usb_pd_host_cmd_common.c:202](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#202) (+v2) |
| `0x102` | USB_PD_PORTS | ✅ | [6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc) | [usb_pd_protocol.c:3068](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3068) | [usb_pd_host_cmd.c:41](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd.c#41) |
| `0x103` | USB_PD_POWER_INFO | ⚠️ | [6.2](#62-extcon-usbc-cros-ecc--usb-c-cable-state-extcon) | [charge_manager.c:878](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#878) (`CONFIG_CHARGE_MANAGER`) | [charge_manager.c:1801](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1801) |
| `0x104` | PD_HOST_EVENT_STATUS | ⚠️ | [6.5](#65-cros_usbpd_notifyc--pd-event-fan-out) | [host_command_pd.c:242](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command_pd.c#242) (`HAS_TASK_PDCMD`) | [usb_pd_host_cmd_common.c:346](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#346) |
| `0x105` | CHARGE_PORT_COUNT | ❌ | [6.3](#63-cros_usbpd-chargerc--usb-pd-power_supply-provider) | not in tree | [charge_manager.c:1813](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1813) |
| `0x110` | USB_PD_FW_UPDATE | ✅ | — | [usb_pd_protocol.c:3257](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3257) | **removed** |
| `0x111` | USB_PD_RW_HASH_ENTRY | ✅ | — | [usb_pd_protocol.c:3287](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3287) | [usb_pd_host_cmd.c:72](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd.c#72) |
| `0x112` | USB_PD_DEV_INFO | ✅ | — | [usb_pd_protocol.c:3312](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3312) | **removed** |
| `0x113` | USB_PD_DISCOVERY | ⚠️ | [6.3](#63-cros_usbpd-chargerc--usb-pd-power_supply-provider) | [usb_pd_policy.c:821](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_policy.c#821) (`…ALT_MODE_DFP`) | [usb_pd_host_cmd_common.c:442](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#442) |
| `0x115` | PD_GET_LOG_ENTRY | ⚠️ | [6.4](#64-cros_usbpd_loggerc--pd-event-log) | [pd_log.c:192](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pd_log.c#192) (`CONFIG_USB_PD_LOGGING`) | [pd_log.c:86](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pd_log.c#86) |
| `0x11a` | USB_PD_MUX_INFO | ❌ | [6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc) | not in tree | [usb_mux.c:912](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#912) |
| `0x121` | GET_UPTIME_INFO | ❌ | [4.3](#43-cros_ec_debugfsc--syskerneldebugcros_ec) | not in tree | [uptime.c:42](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uptime.c#42) |
| `0x12c`-`0x130` | REGULATOR_* | ❌ | [7.3](#73-cros-ec-regulatorc--ec-controlled-voltage-regulators) | not in tree | [regulator.c:32](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/regulator.c#32)ff |
| `0x131`-`0x133`, `0x13c` | TYPEC_* | ❌ | [6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc) | not in tree | [usb_pd_host_cmd_common.c:312](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#312)ff, [usbc/](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usbc/) |
| `0x134`/`0x135` | PCHG_COUNT / PCHG | ❌ | [6.6](#66-cros_peripheral_chargerc--qistylus-peripheral-charger) | not in tree | [peripheral_charger.c:975](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#975)/[:1021](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#1021) |
| `0x603` | USB_PD_MUX_ACK | ❌ | [6.1](#61-cros_ec_typecc--usb-type-c-connector-class--cros_typec_vdmc) | not in tree | [usb_mux.c:942](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#942) |

(`0x0a` TEST_PROTOCOL, `0x2a` VBOOT_HASH, `0x110`-`0x112` and `0x11`-`0x16`
have **no kernel-driver consumer** — they are reachable only via the chardev
passthrough, which is exactly how our EC-flashing tooling uses them.)

## 10. gale gap analysis — what it takes to light up each driver

Three effort tiers, from the EC's perspective:

1. **DT-only (no EC change).** `cros-ec-vbc` — add `google,has-vbc-nvram` to
   the `ec@1e` node; `VBNV_CONTEXT` (0x17) is already implemented.
   `cros-ec-typec` would also *attach* with just a DT node (its probe-fatal
   commands are all implemented at sufficient versions) but runs mux-blind —
   of limited value.
2. **⚠️ EC config + RW reflash (handler exists in the 2016 tree).** The
   headline: **`USB_PD_POWER_INFO` (0x103)** via `CONFIG_CHARGE_MANAGER` —
   with the `EC_FEATURE_USB_PD` feature bit, this lights up
   **`cros-usbpd-charger`** and gives in-band power telemetry through the
   standard power_supply class (and satisfies extcon's fatal probe call).
   Same tier: `GET_BOARD_VERSION` (fixes the `-95` in sysfs `version`),
   `MKBP`/`GET_NEXT_EVENT` (needs `CONFIG_MKBP_EVENT` + an EC→AP interrupt
   line gale doesn't wire — polling only), `LED_CONTROL`, `USB_PD_DISCOVERY`,
   `PD_GET_LOG_ENTRY`, `PD_HOST_EVENT_STATUS`. We already rebuild + reflash
   the EC RW image (see the [renode-equivalence build](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/BUILD.md)),
   so this tier is genuinely actionable.
3. **❌ Needs a newer EC (command doesn't exist in the 2016 codebase).**
   `TYPEC_STATUS`/`TYPEC_CONTROL`/`TYPEC_DISCOVERY`/`VDM_RESPONSE`,
   `USB_PD_MUX_INFO`/`MUX_ACK`, `REGULATOR_*`, `PCHG`, `GET_UPTIME_INFO`,
   `HOST_SLEEP_EVENT`, `CEC`, generic `PWM`, `CHARGE_PORT_COUNT` — these are
   provided by subsystems (TCPMv2, mux framework, Zephyr shims) that
   post-date gale's firmware by years. The
   [R146 rebase spike](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/REBASE-PLAN.md)
   documents what a forward-port would take. Two hard warnings for that
   path, both verified against the [EC-main] pin:
   - **Reverse drift:** current upstream has **deleted** five commands gale
     relies on (`READ_TEST`, `VBNV_CONTEXT` — wire define and all,
     `ENTERING_MODE`, `USB_PD_FW_UPDATE`, `USB_PD_DEV_INFO` —
     [§9](#9-command-index--every-command-in-this-document)), so a
     forward-ported EC would *break* those unless re-added.
   - **No transport to port to:** upstream has dropped `chip/stm32/`
     entirely (the STM32F072 is no longer a supported chip in either build
     system) and the Zephyr `ec_host_cmd` subsystem has **no I2C backend at
     all** ([§3.1](#31-transport-cros_ec_i2c--and-the-ec-side-of-the-wire)) —
     a forward-port must first write a new I2C-slave host-command transport
     before any command can answer.

**For the power-consumption goal specifically**, the shortest paths, in
increasing effort:
(a) custom RW host command returning gale's four ADC channels
(VBUS mV / input mA / CC1 / CC2 — the values behind the EC console
[`gale vbus`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/board.c)),
read via `/dev/cros_ec` — zero kernel changes, minimal EC change;
(b) `CONFIG_CHARGE_MANAGER` + `EC_FEATURE_USB_PD` → stock
`cros-usbpd-charger` works unmodified — the clean, upstream-shaped solution;
(c) full TCPMv2 forward-port — not justified by telemetry alone.
