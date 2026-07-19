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

## 0. Sources & link conventions

Every code reference in this document is a hyperlink into one of four pinned
trees:

| Tag | Tree | Base URL |
|---|---|---|
| **[Linux]** | Linux **v6.12.87** (what the gale image runs; identical to the local build tree) | `https://elixir.bootlin.com/linux/v6.12.87/source/…#L<line>` |
| **[EC-2016]** | ChromiumOS `platform/ec` @ [`7c97ab0`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb) (branch `firmware-gale-8281.B` — **the codebase gale's shipped EC was built from**) | `https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab0…/…#<line>` |
| **[EC-main]** | ChromiumOS `platform/ec` @ [`37850ff4`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1) (**current upstream** main, 2026-06-04) | `https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4…/…#<line>` |
| **[renode]** | The gale EC **reconstruction** on branch [`gale-ec-renode-equivalence`](https://github.com/mithro/gwifi-openwrt/tree/gale-ec-renode-equivalence/gale-ec) (open-source `board/gale/` overlay + pinned [EC-2016] base; proven functionally equivalent to the shipped firmware) | `https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/…#L<line>` |

Because the [renode] reconstruction pins the same [EC-2016] base, **gale's
host-command surface is identical in both** — command handlers live in the
pinned upstream files, and only `board/gale/*` (GPIO table, ADC channels, PD
policy) is reconstruction-local.

**gale status legend**, used for every command below:

- ✅ **implemented** — one of the **31 commands** gale's EC answers today.
- ⚠️ **addable** — the command exists in the [EC-2016] codebase but is not
  compiled into gale (gated by a `CONFIG_*` gale doesn't set). Enabling it =
  config + board glue + EC RW reflash.
- ❌ **absent** — the command does not exist in the [EC-2016] codebase at all
  (invented later; present in [EC-main]). Needs a forward-ported EC, not a
  config flip.

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
drivers instantiate, §3.2):
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

Gate = what `cros_ec_dev` checks before creating the cell (§3.3). gale's
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

### 2.7 Added after 6.12 (current mainline)

| Driver | Since | Purpose / commands |
|---|---|---|
| `cros_typec_altmode.c` (platform/chrome) | v6.14 | AP-driven DP/TBT altmode for cros-ec-typec; uses `EC_CMD_TYPEC_CONTROL` |
| `cros_ec_ucsi.c` (usb/typec/ucsi) | v6.14 | UCSI OPM↔PPM transport; new `EC_CMD_UCSI_PPM_GET`/`EC_CMD_UCSI_PPM_SET`, gated on new `EC_FEATURE_UCSI_PPM`; the MFD now prefers a `cros_ec_ucsi` cell and suppresses the legacy usbpd-charger/logger cells on UCSI ECs |
| `chromeos_of_hw_prober.c` | v6.13 | DT hardware prober — issues no EC commands |

None are relevant to gale's 2016 EC (no UCSI/Type-C commands), but they matter
when reading current upstream driver code: the modern PD stack assumes
commands (`TYPEC_*`, `UCSI_PPM_*`) that post-date gale's firmware by ~5–9 years.

### 2.8 Master map — driver → commands (with gale outcome)

| Driver (§) | Commands issued | On gale |
|---|---|---|
| cros_ec core + proto (§3.2) | `0x0b` `0x08` `0x01` `0x67` `0x8d` `0xa9` (`0x09` on IN_PROGRESS, `0x07` helper) | ✅ registers — only `0x0b` is fatal |
| cros_ec_dev MFD (§3.3) | `0x0d` `0x2b` `0x134` (gating probes) | ✅ creates 5 cells |
| cros-ec-chardev (§4.1) | `0x02` + **any** (userspace passthrough) | ✅ works |
| cros-ec-sysfs (§4.2) | `0x02` `0x04` `0x05` `0x06` `0x10` `0xd2` (`0x2b` hidden) | ✅ works (board-version line errors) |
| cros-ec-debugfs (§4.3) | `0xd3` `0x08` `0x97` `0x98` `0x121` `0x101` | ✅ works (`uptime` suppressed) |
| gpio-cros-ec (§5) | `0x93` (v0+v1) `0x92` | ✅ **fully works** |
| cros-ec-typec (§6.1) | `0x08` `0x102` `0x101` `0x11a` `0x131` `0x132` `0x133` `0x13c` `0x603` | ❌ no DT node (would attach degraded) |
| extcon-usbc-cros-ec (§6.2) | `0x102` `0x103` `0x101` `0x11a` | ❌ no DT node (would fail probe on `0x103`) |
| cros-usbpd-charger (§6.3) | `0x102` `0x105` `0x103` `0x113` `0xa2` | ❌ no USB_PD feature |
| cros-usbpd-logger (§6.4) | `0x115` | ❌ no USB_PD feature |
| cros-usbpd-notify (§6.5) | `0x104` | ❌ no USB_PD feature |
| cros_peripheral_charger (§6.6) | `0x134` `0x08` `0x135` | ❌ PCHG_COUNT probe fails |
| cros-ec-vbc (§7.1) | `0x17` | ❌ DT prop absent (**would fully work**) |
| rtc-cros-ec (§7.2) | `0x44` `0x45` `0x46` `0x47` | ❌ no RTC feature |
| cros-ec-regulator (§7.3) | `0x12c` `0x12d` `0x12e` `0x12f` `0x130` | ❌ no DT node |
| i2c-cros-ec-tunnel (§7.4) | `0x9e` | ❌ no DT node |
| leds-cros_ec (§7.5) | `0x29` | ❌ no LED feature |
| cros_ec_lightbar (§7.6) | `0x28` | ❌ no LIGHTBAR feature |
| cros-ec-sensorhub + ring + IIO (§7.7) | `0x08` `0x2b` (many subcommands) | ❌ sensor count 0 |
| cros_ec_keyb (§8.1) | `0x61` | ❌ not shipped / no node |
| cros_ec_mkbp_proximity (§8.2) | `0x61` | ❌ not shipped / no node |
| hid-google-hammer cbas (§8.3) | `0x61` | ❌ not shipped / no node |
| cros-ec-cec (§8.4) | `0xc1` `0x08` `0xb8` `0xb9` `0xba` | ❌ not shipped / no CEC feature |
| pwm-cros-ec (§8.5) | `0x26` `0x25` | ❌ not shipped / no node |
| cros_kbd_led_backlight (§8.6) | `0x22` `0x23` | ❌ not shipped / no feature |
| cros_ec_codec (§8.7) | `0xbc` `0xbd` `0xbe` `0xbf` | ❌ not shipped / no node |
| cros_ec_wdt (§8.8) | `0x9f` | ❌ not shipped / no feature |
| cros_charge-control (§8.9) | `0x08` `0x96` | ❌ not shipped / no feature |
| cros_typec_switch (§8.10) | `0x132` `0x133` | ❌ ACPI-only |
| cros_ec_hwmon (§8.11) | `0x07` `0x70` | ❌ not shipped (cell exists) |

---

## 3. Core stack

### 3.1 Transport: `cros_ec_i2c` — and the EC side of the wire

- **Linux:** [`cros_ec_i2c_probe()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L289)
  binds the DT node, installs
  [`ec_dev->pkt_xfer = cros_ec_pkt_xfer_i2c`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L304)
  ([framing](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_i2c.c#L52), §1.1)
  and calls
  [`cros_ec_register()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec.c#L180).
  The transport issues no commands of its own; it frames all of them. It does
  **not** provide `cmd_readmem` (only [EC-2016-era LPC does](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lpc.c#L577)) —
  relevant to §4.1/§8.11.
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
- **EC-main:** `chip/stm32/` **no longer exists** — legacy transports were
  replaced by Zephyr `ec_host_cmd` backends
  ([`zephyr/shim/src/host_command.c`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/host_command.c)
  bridges `DECLARE_HOST_COMMAND` into Zephyr; per-transport
  `GET_PROTOCOL_INFO` shims live in e.g.
  [`zephyr/shim/src/espi.c#545`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/espi.c#545)).
  The wire protocol itself is unchanged — a modern EC still answers the exact
  framing in §1.1.
- **renode:** the reconstruction models this transport in
  [`GaleI2c.cs`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/renode/peripherals/GaleI2c.cs)
  (slave-RX ISR sequence + AP host-command injector).

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
- EC-main handler: per-transport shims, e.g. [`zephyr/shim/src/espi.c:545`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/espi.c#545)

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
(§6.1), debugfs (§4.3), CEC (§8.4), charge-control (§8.9), sensors core
(§7.7) all use it to pick command versions.

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
consumer: cros_ec_hwmon (§8.11). Note the chardev `IOCRDMEM` ioctl does **not**
use this fallback (§4.1).

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
- **`0x2b` MOTION_SENSE_CMD** via [`cros_ec_get_sensor_count()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L961) — gates the [sensorhub cell `:237`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L237) (detail §7.7). The legacy fallback needs [`cmd_readmem`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L981), absent on I2C.
- **`0x134` PCHG_COUNT** live probe at [`:298`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L298) — gates the pchg cell (detail §6.6).
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
document (§1.4, §2.4).

---

## 4. Always-available interfaces (unconditional MFD cells)

### 4.1 `cros-ec-chardev` — `/dev/cros_ec`

[`cros_ec_chardev_probe()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L378)
issues **no EC command** (it only registers the misc device) — it always
attaches. Entry points:

| Entry point | Command(s) | gale |
|---|---|:--:|
| `ioctl(CROS_EC_DEV_IOCXCMD)` — [raw passthrough `:305`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L305) | **any** — userspace supplies the command | ✅ all 31 work; others relay `INVALID_COMMAND` |
| `read()` legacy path — [`ec_get_version()` `:68`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L68) via [`:241`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L241) | `0x02` GET_VERSION | ✅ |
| `read()` MKBP path — [event queue `:211`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L211), filled by [notifier `:93`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L93) | (consumes `0x67` events from core) | inert — no MKBP on gale |
| `ioctl(CROS_EC_DEV_IOCRDMEM)` — [`:325`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L325) | *(direct window only)* | **`-ENOTTY`** — guarded by `if (!ec_dev->cmd_readmem)`, which only [LPC sets](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lpc.c#L577); it does **not** fall back to `0x07` |

This is how any of gale's 31 commands (incl. FLASH_*, VBOOT_HASH, USB_PD_*)
are reachable from userspace without a dedicated driver.

#### 0x02 EC_CMD_GET_VERSION — firmware versions · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:968`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L968); [`enum ec_current_image`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L970)
- Issued by: chardev [`:68`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_chardev.c#L68); sysfs `version` [`cros_ec_sysfs.c:129`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L129) (the only sub-command whose failure [aborts the attribute `:133`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L133))
- EC-2016 handler: [`host_command_get_version`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1080) (v0) → gale ✅
- EC-main handler: [`common/system.c:1731`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1731) (v0|v1 — v1 adds `cros_fwid`)

Request: none. Response
[`struct ec_response_get_version`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L983) (100 B):

```c
struct ec_response_get_version {
	char version_string_ro[32];   /* "gale_v1.1.5337-0115719" */
	char version_string_rw[32];
	char reserved[32];
	uint32_t current_image;       /* enum ec_current_image: 1=RO, 2=RW */
} __ec_align4;
```

### 4.2 `cros-ec-sysfs` — `/sys/class/chromeos/cros_ec/*`

[Probe](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L331)
only creates the attribute group — no EC command; always attaches. Commands
fire on attribute access:

| Attribute | Command(s) | gale |
|---|---|:--:|
| `version` (read) | `0x02` [`:129`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L129) + `0x04` [`:148`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L148) + `0x05` [`:161`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L161) + `0x06` [`:180`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L180) | ✅ except the `0x06` line → `Board version: XFER / EC ERROR -95` ([handled gracefully `:183`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L183)) |
| `flashinfo` (read) | `0x10` [`:214`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L214) | ✅ |
| `reboot` (write) | `0xd2` [`:100`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L100) | ✅ |
| `kb_wake_angle` | `0x2b` ([show `:248`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L248)) | **hidden** — [visibility gate `:320`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sysfs.c#L320) needs the sensorhub's `has_kb_wake_angle`; never created on gale, so `0x2b` is never issued |

#### 0x04 EC_CMD_GET_BUILD_INFO · gale ✅ (v0)

[Defined `:1016`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1016).
Request: none; response: raw NUL-terminated build string (no struct).
EC-2016: [`host_command_build_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1091) → gale ✅ ·
EC-main: [`common/system.c:1771`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1771).
gale returns `"gale_v1.1.5337-0115719 2016-10-03 15:55:36 hywu@…"`.

#### 0x05 EC_CMD_GET_CHIP_INFO · gale ✅ (v0)

[Defined `:1019`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1019).
Request: none; response
[`struct ec_response_get_chip_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1027):

```c
struct ec_response_get_chip_info {
	char vendor[32];    /* "stm" */
	char name[32];      /* "stm32f07x" */
	char revision[32];
} __ec_align4;
```

EC-2016: [`host_command_get_chip_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1107) → gale ✅ ·
EC-main: [`common/system.c:1787`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1787).

#### 0x06 EC_CMD_GET_BOARD_VERSION · gale ⚠️ addable

[Defined `:1034`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1034).
Request: none; response
[`struct ec_response_board_version`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1040)
`{ uint16_t board_version; }`.
EC-2016: [`host_command_get_board_version`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1122) gated
[`#ifdef CONFIG_BOARD_VERSION`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1111) → **off** on gale ·
EC-main: [`common/system.c:1807`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1807).
This is the source of the live `-95` in the sysfs `version` output — the one
place a gale user sees an unimplemented command today.

#### 0x10 EC_CMD_FLASH_INFO · gale ✅ (v0+v1)

[Defined `:1339`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1339).
Request: none. Response v0
[`struct ec_response_flash_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1354) /
v1 [`…_info_1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1405):

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

EC-2016: [`flash_command_get_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#781) (v0|v1) → gale ✅ ·
EC-main: [`common/flash.c:1598`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/flash.c#1598) (adds v2).
(The sysfs attribute uses v0 only. gale's other flash commands —
`0x11`/`0x12`/`0x13`/`0x15`/`0x16` — have **no kernel consumer**; they're
reachable via the chardev passthrough, e.g. for EC RW flashing from userspace.)

#### 0xd2 EC_CMD_REBOOT_EC · gale ✅ (v0) *(destructive)*

[Defined `:4890`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4890);
[`enum ec_reboot_cmd`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4893),
flags [`EC_REBOOT_FLAG_ON_AP_SHUTDOWN`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4907).
Request [`struct ec_params_reboot_ec`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4910):

```c
struct ec_params_reboot_ec {
	uint8_t cmd;    /* enum ec_reboot_cmd: 0=CANCEL 1=JUMP_RO 2=JUMP_RW 4=COLD 5=DISABLE_JUMP 6=HIBERNATE */
	uint8_t flags;  /* EC_REBOOT_FLAG_* */
} __ec_align1;
```

EC-2016: [`host_command_reboot`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1202) → gale ✅
(the EC pre-sends success before a non-returning reboot; `HIBERNATE` is not
compiled on gale → `EC_RES_INVALID_PARAM`) ·
EC-main: [`common/system.c:1871`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1871).

### 4.3 `cros-ec-debugfs` — `/sys/kernel/debug/cros_ec/*`

[Probe](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L488)
issues three commands but **tolerates every failure** (the only fatal paths
are ENOMEM/notifier registration): `0xd3` (panic-data fetch,
[failure forced to 0 `:450`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L450)),
`0x08` (probe CONSOLE_READ v1 support,
[failure = skip `console_log` `:364`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L364)),
`0x121` (uptime support check —
[`INVALID_COMMAND` explicitly suppresses the file `:266`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L266)).

| debugfs file | Command(s) | gale |
|---|---|:--:|
| `console_log` | `0x97` [`:75`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L75) + `0x98` v1 [`:380`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L380)/[`:102`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L102) (background poll) | ✅ streams the EC console |
| `pdinfo` | `0x101` **v1 only**, looped over ports [`:226`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L226)/[`:235`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L235) until first error (it does **not** use `0x102`) | ✅ |
| `panicinfo` | `0xd3` [`:424`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L424); blob file [created only if data exists `:459`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L459) | ✅ (absent when no panic) |
| `uptime` | `0x121` [`:262`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L262)/[read `:288`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L288) | file **not created** |
| `last_resume_result`, `suspend_timeout_ms` | none (cached variables, [`:518`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L518)/[`:521`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L521)) | ✅ |

#### 0x97 EC_CMD_CONSOLE_SNAPSHOT / 0x98 EC_CMD_CONSOLE_READ · gale ✅ (v0 / v0+v1)

[Defined `:3906`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3906) /
[`:3920`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3920).
`0x97` (no params/response) latches the EC's UART ring buffer; `0x98` drains
it. Request v1
[`struct ec_params_console_read_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3927):

```c
struct ec_params_console_read_v1 {
	uint8_t subcmd;   /* enum ec_console_read_subcmd: 0=NEXT, 1=RECENT */
} __ec_align1;
```

Response: NUL-terminated ASCII chunk (empty when drained; call repeatedly).
EC-2016: [`host_command_console_snapshot`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#357) /
[`host_command_console_read`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#419) → gale ✅ ·
EC-main: moved to [`common/uart_hostcmd.c:17`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#17)/[`:53`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#53).

#### 0xd3 EC_CMD_GET_PANIC_INFO · gale ✅ (v0)

[Defined `:4921`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4921).
Request: none; response: the raw EC `struct panic_data` (arch-specific,
variable length; empty if no valid panic). Reading marks the record consumed.
EC-2016: [`host_command_panic_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c#233) → gale ✅ ·
EC-main: [`common/panic_output.c:618`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/panic_output.c#618) (v0-v2).

#### 0x121 EC_CMD_GET_UPTIME_INFO · gale ❌ absent-in-2016

[Defined `:5519`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5519).
Request: none; response
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

EC-2016: **not in tree** · EC-main:
[`common/uptime.c:42`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uptime.c#42).

---

## 5. `gpio-cros-ec` — the one consumer that fully works on gale

Cell created because gale advertises `EC_FEATURE_GPIO`
([gate `cros_ec_dev.c:121`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L121));
no DT node needed
([probe borrows the EC's fwnode `:173`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L173)).
**Live-confirmed bound** on puck12 (`cros-ec-gpio.3.auto`).

| Use | Command | Ver | Issued at | Fatal? |
|---|---|:--:|---|:--:|
| count GPIOs (probe) | `0x93` GET_COUNT | v1 | [`cros_ec_gpio_ngpios()` `:154`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L154), checked [`:175`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L175) | **YES** |
| name each line (probe) | `0x93` GET_INFO | v1 | [`cros_ec_gpio_init_names()` `:126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L126), checked [`:187`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L187) | **YES** |
| read a line | `0x93` by-name | v0 | [`cros_ec_gpio_get()` `:60`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L60) | no |
| direction | `0x93` GET_INFO | v1 | [`cros_ec_gpio_get_direction()` `:84`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L84) | no |
| drive a line | `0x92` | v0 | [`cros_ec_gpio_set()` `:41`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/gpio/gpio-cros-ec.c#L41) | no |

Probe requires **GPIO_GET v1** — and gale provides it (version mask `0x3`),
which the live bound device proves.

#### 0x93 EC_CMD_GPIO_GET · gale ✅ (v0+v1)

- Defined: [`cros_ec_commands.h:3761`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3761); subcommands [`enum gpio_get_subcmd`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3798)
- EC-2016 handler: [`gpio_command_get`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#259) (v0|v1), gated [`CONFIG_COMMON_GPIO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#36) → gale ✅
- EC-main handler: [`common/gpio_commands.c:280`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#280) (v0|v1)
- renode: the named-GPIO table this command reads is the reconstructed [`board/gale/gpio.inc`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/gpio.inc)

Request v0
[`struct ec_params_gpio_get`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3764) /
v1 [`…_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3773):

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

Response v0
[`struct ec_response_gpio_get`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3768) /
v1 [`…_v1`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3785):

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

Errors: `EC_RES_ERROR` for an unknown name / out-of-range index;
`EC_RES_INVALID_PARAM` for a bad v1 subcommand.

#### 0x92 EC_CMD_GPIO_SET · gale ✅ (v0)

- Defined: [`cros_ec_commands.h:3753`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3753)
- EC-2016 handler: [`gpio_command_set`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#274) (v0) → gale ✅
- EC-main handler: [`common/gpio_commands.c:295`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#295)

Request [`struct ec_params_gpio_set`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3755):

```c
struct ec_params_gpio_set {
	char name[32];   /* case-insensitive GPIO name */
	uint8_t val;     /* 0 = low, non-zero = high */
} __ec_align1;
```

Response: none. Errors: `EC_RES_ACCESS_DENIED` if the EC is locked
(`system_is_locked()`; gale runs `CONFIG_SYSTEM_UNLOCKED` → normally allowed);
`EC_RES_ERROR` if the name is not an output.

---

## 6. USB-PD / Type-C / charger family

None of these instantiate on a stock gale: four are gated on
`EC_FEATURE_USB_PD` (bit 22, clear on gale), one on a live `PCHG_COUNT` probe,
and two bind only to DT/ACPI nodes gale doesn't declare. Verified live: all
unbound on puck12.

### 6.1 `cros-ec-typec` (+ `cros_typec_vdm`) — Type-C connector class

Binds to DT [`google,cros-ec-typec`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1206) /
ACPI `GOOG0014` ([`:1198`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1198)) — **not** an MFD cell.

| Use | Command | Issued at | Fatal? | gale |
|---|---|---|:--:|:--:|
| probe: PD_CONTROL version | `0x08` | [`:1156`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1156), fatal [`:1235`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1235) | **YES** | ✅ |
| probe: features | `0x0d` | [`:1245`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1245) → `typec_cmd_supported`/`needs_mux_ack` | no | ✅ (both false) |
| probe: port count | `0x102` | [`:1248`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1248), fatal [`:1250`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1250) | **YES** | ✅ |
| probe+runtime: port state | `0x101` | [`:1119`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1119), fatal [`:1272`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1272) | **YES** | ✅ v1 |
| runtime: mux state | `0x11a` | [`:624`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L624) — warned & [swallowed `:1126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1126) | no | ❌ |
| runtime: mux ack | `0x603` | [`:687`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L687), only if `needs_mux_ack` | no | ❌ (never sent) |
| runtime: PD status/events | `0x133` | [`:1024`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1024), only if `typec_cmd_supported` ([gate `:1142`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L1142)) | no | ❌ (never sent) |
| runtime: altmode discovery | `0x131` | [`:856`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L856)/[`:939`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L939) | no | ❌ (never sent) |
| runtime: control / VDM send | `0x132` | [`:972`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_typec.c#L972), [`cros_typec_vdm.c:116`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L116)/[`:141`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L141) | no | ❌ (never sent) |
| runtime: VDM replies | `0x13c` | [`cros_typec_vdm.c:32`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L32)/[`:70`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_vdm.c#L70) | no | ❌ (never sent) |

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
probe-fatal set (`0x08`, `0x102`, `0x101`-v1) is entirely within gale's 31 —
it would attach at `pd_ctrl_ver = 1` and run **mux-blind and event-blind**
(every `0x11a` warned, no `0x133`/`0x131`/`0x132` ever issued). Partner/cable
registration and role reporting would work at v1 fidelity.

#### 0x101 EC_CMD_USB_PD_CONTROL — port role/mux/state · gale ✅ (v0+v1)

- Defined: [`cros_ec_commands.h:5020`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5020); enums [`usb_pd_control_role`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5022), [`usb_pd_control_mux`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5032), [`usb_pd_control_swap`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5042); response flags [`PD_CTRL_RESP_ENABLED_*` `:5057`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5057), [`PD_CTRL_RESP_ROLE_*` `:5061`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5061)
- Issued by: cros-ec-typec (above), extcon ([`:155` v1](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L155)), debugfs `pdinfo` ([`:226` v1](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_debugfs.c#L226))
- EC-2016 handler: [`hc_usb_pd_control`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3159) (v0|v1), gated [`CONFIG_USB_POWER_DELIVERY`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#86) + `HAS_TASK_HOSTCMD` → gale ✅ (TCPMv1)
- EC-main handler: [`common/usb_pd_host_cmd_common.c:202`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#202) (v0|v1|**v2**) — the 2016 TCPMv1 file was deleted upstream
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

#### 0x102 EC_CMD_USB_PD_PORTS — port count · gale ✅ (v0)

[Defined `:5113`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5113).
Request: none; response
[`struct ec_response_usb_pd_ports`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5118)
`{ uint8_t num_ports; }` — gale: `1`.
EC-2016: [`hc_pd_ports`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3068) → gale ✅ ·
EC-main: [`common/usb_pd_host_cmd.c:41`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd.c#41).

#### 0x11a EC_CMD_USB_PD_MUX_INFO — SS-mux state · gale ❌ absent-in-2016

[Defined `:5385`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5385);
flags [`USB_PD_MUX_*` `:5392`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5392).
Request `{ uint8_t port; }`
([`:5387`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5387));
response
[`struct ec_response_usb_pd_mux_info`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5402)
`{ uint8_t flags; }` (USB_ENABLED / DP_ENABLED / POLARITY_INVERTED / HPD_IRQ /
HPD_LVL / SAFE_MODE / TBT / USB4).
EC-2016: **not in tree** · EC-main:
[`driver/usb_mux/usb_mux.c:912`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#912)
(the mux framework — hardware gale doesn't have; its USB SS lines are fixed).

#### 0x131 EC_CMD_TYPEC_DISCOVERY · 0x132 EC_CMD_TYPEC_CONTROL · 0x133 EC_CMD_TYPEC_STATUS · 0x13c EC_CMD_TYPEC_VDM_RESPONSE — the modern (TCPMv2) AP interface · all gale ❌ absent-in-2016

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

EC-2016: **none exist**. EC-main: TCPMv2 AP interface —
[`hc_typec_status` `usb_pd_host_cmd_common.c:312`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#312),
[`hc_typec_control` `:419`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#419),
[`hc_typec_discovery` `usbc/usb_pd_host.c:102`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usbc/usb_pd_host.c#102),
[`hc_typec_vdm_response` `usbc/ap_vdm_control.c:300`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usbc/ap_vdm_control.c#300).
These are backed by the TCPMv2 state machines (`common/usbc/*.c`) — porting
them to gale means forward-porting the whole PD stack, not adding a handler.

#### 0x603 EC_CMD_USB_PD_MUX_ACK · gale ❌ absent-in-2016

[Defined `:6448`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6448);
request [`{ uint8_t port; }` `:6450`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L6450), no response.
Only sent when the EC advertises `EC_FEATURE_TYPEC_MUX_REQUIRE_AP_ACK`
([bit 43](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1302)).
EC-main: [`driver/usb_mux/usb_mux.c:942`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#942).

### 6.2 `extcon-usbc-cros-ec` — USB-C cable-state extcon

Binds to DT [`google,extcon-usbc-cros-ec`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L519).

| Use | Command | Issued at | Fatal? | gale |
|---|---|---|:--:|:--:|
| probe: port sanity | `0x102` | [`:180`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L180), fatal [`:411`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L411) | **YES** | ✅ |
| probe+event: power type | `0x103` | [`:105`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L105) | **YES** (below) | ❌ |
| event: role/polarity | `0x101` v1 | [`:155`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L155) ([`-ENOTCONN` = disconnected `:266`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L266)) | no | ✅ |
| event: mux/HPD | `0x11a` | [`:126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L126) ([failure defaulted `:279`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/extcon/extcon-usbc-cros-ec.c#L279)) | no | ❌ |

**The famous fatal bail** — `USB_PD_POWER_INFO` failure kills the whole cable
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
on `0x103` → `-EOPNOTSUPP`. Making this driver work on gale = compile
`USB_PD_POWER_INFO` into the EC (⚠️ tier) *or* patch the driver to make
`power_type` best-effort like `mux_state` already is.

#### 0x103 EC_CMD_USB_PD_POWER_INFO — **the power-consumption command** · gale ⚠️ addable

The command that would expose gale's measured VBUS voltage/current in-band —
the original motivation for this whole investigation.

- Defined: [`cros_ec_commands.h:5122`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5122); enums [`usb_chg_type`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5129), [`usb_power_roles`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5142); [`PD_POWER_CHARGING_PORT` `:5124`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5124)
- Issued by: extcon (fatal, above); cros-usbpd-charger ([`:183`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L183), per-property reads)
- EC-2016 handler: [`hc_pd_power_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#878) (v0) — gated [`CONFIG_CHARGE_MANAGER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#30), which gale **doesn't set** → not compiled. The measurement sources exist on gale (ADC channels for VBUS/current in the reconstructed [`board/gale/board.c`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/board.c); EC console `gale vbus` prints them) — only this host-command plumbing is missing.
- EC-main handler: [`common/charge_manager.c:1801`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1801) (v0, unchanged)

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

### 6.3 `cros-usbpd-charger` — power_supply provider

MFD cell gated on `EC_FEATURE_USB_PD`
([`cros_ec_dev.c:131`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L131), cell [`:90`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L90)).

| Use | Command | Issued at | Fatal? | gale |
|---|---|---|:--:|:--:|
| probe: PD port count | `0x102` | [`:136`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L136) | no (logged) | ✅ |
| probe: total charge ports | `0x105` | [`:122`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L122) | no (fallback) | ❌ |
| property read: measurements | `0x103` | [`:183`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L183) | no ([`-EINVAL` per read `:381`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L381)) | ❌ |
| property read: partner VID/PID | `0x113` | [`:153`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L153) | no | ❌ |
| sysfs write: input limits | `0xa2` | [`:328`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L328) | no | ❌ |

Only structural failure is fatal: no ports at all →
[`-ENODEV` `:579`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_usbpd-charger.c#L579).
**gale verdict:** never instantiates (feature gate). Even with the feature bit
+ `0x103` added on the EC (⚠️ tier), this driver would then work — it is the
natural kernel surface for gale power telemetry (`POWER_SUPPLY_PROP_*` from
`meas`).

- `0x105` CHARGE_PORT_COUNT: [defined `:5171`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5171), response `{ uint8_t port_count; }`; EC-2016 **not in tree**; EC-main [`charge_manager.c:1813`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1813).
- `0x113` USB_PD_DISCOVERY: [defined `:5217`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5217), response [`{u16 vid; u16 pid; u8 ptype;}` `:5218`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5218); EC-2016 handler exists ([`hc_remote_pd_discovery`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_policy.c#821)) but gated `CONFIG_USB_PD_ALT_MODE_DFP` → **off** on gale (⚠️).
- `0xa2` EXTERNAL_POWER_LIMIT: [defined `:4189`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4189), params [`{u16 current_lim; u16 voltage_lim;}` (v1) `:4192`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4192); EC-2016 [`hc_external_power_limit`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#960) gated `CONFIG_CHARGE_MANAGER` → **off** on gale (⚠️).

### 6.4 `cros-usbpd-logger` — PD event log

Same feature-gated cell array as the charger
([`cros_ec_dev.c:91`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L91)).
[Probe is command-free](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c#L196)
(queues delayed work); every 60 s it drains the log.

#### 0x115 EC_CMD_PD_GET_LOG_ENTRY · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:5243`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5243); entry types [`PD_EVENT_*` `:5266`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5266)
- Issued by: [`ec_get_log_entry()` `:71`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c#L71), loop [breaks harmlessly on error `:182`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_logger.c#L182)
- EC-2016 handler: [`hc_pd_get_log_entry`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pd_log.c#192) (v0), gated [`CONFIG_USB_PD_LOGGING`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#87) → **off** on gale
- EC-main handler: [`common/pd_log.c:86`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pd_log.c#86)

Request: none. Response
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

(empty entry = end of log).

### 6.5 `cros-usbpd-notify` — PD event fan-out

OF cell gated on `EC_FEATURE_USB_PD`
([`cros_ec_dev.c:282`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L282));
ACPI variant `GOOG0003`. [Probe is command-free](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_notify.c#L184).
On a PD MKBP event it reads the status word — best-effort
([warn + notify with 0 `:77`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_usbpd_notify.c#L77)).

#### 0x104 EC_CMD_PD_HOST_EVENT_STATUS · gale ⚠️ addable

[Defined `:5008`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5008);
bits [`PD_EVENT_UPDATE_DEVICE`… `:5011`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5011).
Request: none; response
[`struct ec_response_host_event_status`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5015)
`{ uint32_t status; }`.
EC-2016: [`hc_pd_host_event_status`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command_pd.c#242) gated `HAS_TASK_PDCMD` — gale's
[task list](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/ec.tasklist)
(HOOKS/HOSTCMD/CONSOLE/PD_C0) has no PDCMD task → **off** ·
EC-main: [`usb_pd_host_cmd_common.c:346`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#346).

### 6.6 `cros_peripheral_charger` — Qi/stylus charger

Cell gated on a **live command probe**: the MFD calls `0x134` and only adds
the cell when `port_count > 0`
([`cros_ec_dev.c:298`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L298)) —
gale answers `INVALID_COMMAND`, cell never added.

| Command | Issued at | Fatal? |
|---|---|:--:|
| `0x134` PCHG_COUNT — [defined `:5622`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5622), response `{ uint8_t port_count; }` [`:5626`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5626) | MFD gate + probe [`:113`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L113), [`-ENODEV` `:286`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L286) | **YES** |
| `0x08` for `0x135` (require PCHG v1) | [`:96`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L96), [`-EOPNOTSUPP` `:297`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L297) | **YES** |
| `0x135` PCHG — [defined `:5633`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5633), response [`{u32 error; u8 state; u8 battery_percentage; …}` `:5639`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5639) | [`:135`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_peripheral_charger.c#L135) | no |

Both commands gale ❌ absent-in-2016; EC-main provider:
[`common/peripheral_charger.c:975`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#975)/[`:1021`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#1021).

---

## 7. Function drivers (shipped in the gale image, dormant)

### 7.1 `cros-ec-vbc` — vboot NV context

Cell gated **only** on the DT property `google,has-vbc-nvram` on the EC node
([`cros_ec_dev.c:322`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L322)) —
not on a feature bit.
[Probe is command-free](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c#L114)
(creates a sysfs group); the command fires on `vboot_context` read/write.

**The one dormant driver whose command gale fully implements** — adding the DT
property would light it up with no EC change.

#### 0x17 EC_CMD_VBNV_CONTEXT · gale ✅ (v0+v1)

- Defined: [`cros_ec_commands.h:1661`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1661); [`EC_VER_VBNV_CONTEXT`=1 `:1662`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1662), [`EC_VBNV_BLOCK_SIZE`=16 `:1663`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1663)
- Issued by: [`vboot_context_read()` `:43`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c#L43) / [`vboot_context_write()` `:86`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_vbc.c#L86), both at v1 — runtime only
- EC-2016 handler: [`host_command_vbnvcontext`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1155) (v0|v1) → gale ✅
- EC-main: **REMOVED** — handler and even the `EC_CMD` define are gone from current upstream (dead command)

Request [`struct ec_params_vbnvcontext`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1670) /
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

WRITE persists to the EC's NV storage. Errors: `EC_RES_ERROR` on storage
failure / unknown `op`.

### 7.2 `rtc-cros-ec` — EC real-time clock

Cell gated on `EC_FEATURE_RTC` (bit 27,
[`cros_ec_dev.c:126`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L126)) — clear on gale.

| Use | Command | Issued at | Fatal? |
|---|---|---|:--:|
| probe: initial time | `0x44` RTC_GET_VALUE | [`cros_ec_rtc_read_time()` `:85`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L85) via probe [`:334`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L334) | **YES** ([`return ret` `:333`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L333)) |
| set time | `0x46` RTC_SET_VALUE | [`:104`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L104) | no |
| read/set alarm | `0x45`/`0x47` | [`:132`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L132)/[`:184`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L184) (+probe window sizing [`:360`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/rtc/rtc-cros-ec.c#L360)) | no |

#### 0x44–0x47 EC_CMD_RTC_GET/SET_VALUE/ALARM · gale ⚠️ (2016: chip-specific, no STM32 support)

- Defined: [`:2893`-`:2898`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2893); [`EC_RTC_ALARM_CLEAR` `:2901`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2901)
- Shared structs [`ec_params_rtc`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2884) / [`ec_response_rtc`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2888): `{ uint32_t time; }` (seconds)
- EC-2016: `GET/SET_VALUE` handlers exist only in [`chip/lm4/system.c:702`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/lm4/system.c#702) and [`chip/npcx/system.c:750`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/npcx/system.c#750) — **no STM32 implementation**; the alarm pair has **no handler at all** in 2016. So "addable" here means writing an STM32F0 RTC driver, not flipping a config.
- EC-main: [`zephyr/shim/src/rtc.c:204`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/rtc.c#204)ff (all four).

### 7.3 `cros-ec-regulator` — EC-controlled regulators

DT-bound ([`google,cros-ec-regulator`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L208));
probe issues `0x12c` and
[fails on error `:187`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L187).
Runtime: `0x12d` enable ([`:33`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L33)),
`0x12e` is-enabled ([`:58`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L58)),
`0x12f` set-voltage ([`:111`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L111)),
`0x130` get-voltage ([`:85`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/regulator/cros-ec-regulator.c#L85)).

#### 0x12c–0x130 EC_CMD_REGULATOR_* · all gale ❌ absent-in-2016

Defined [`:5754`-`:5827`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L5754). Key structs:

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

EC-2016: none exist. EC-main:
[`common/regulator.c:32`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/regulator.c#32)ff
(thin wrappers over per-board `board_regulator_*`).

### 7.4 `i2c-cros-ec-tunnel` — I2C through the EC

DT-bound ([`google,cros-ec-i2c-tunnel`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c#L296));
[probe issues no command](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c#L242)
(reads the `google,remote-bus` property); every transfer is one `0x9e`.

#### 0x9e EC_CMD_I2C_PASSTHRU · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:4010`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4010); flags [`EC_I2C_FLAG_READ` `:4013`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4013), status [`EC_I2C_STATUS_*` `:4018`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4018)
- Issued by: [`ec_i2c_xfer()` `:211`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/i2c/busses/i2c-cros-ec-tunnel.c#L211) — runtime only
- EC-2016 handler: [`i2c_command_passthru`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/i2c.c#701) (v0), gated [`CONFIG_I2C_MASTER`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#49) — gale is I2C **slave**-only → **off** (and gale's EC has no downstream I2C bus to tunnel to, so this is permanently moot)
- EC-main handler: [`common/i2c_passthru.c:260`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/i2c_passthru.c#260)

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

### 7.5 `leds-cros_ec` — EC LEDs

Cell gated on `EC_FEATURE_LED` (bit 5,
[`cros_ec_dev.c:141`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L141)).
Probe queries each LED and treats `-EOPNOTSUPP` as
[`-ENODEV` `:189`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L189).

#### 0x29 EC_CMD_LED_CONTROL · gale ⚠️ addable

- Defined: [`cros_ec_commands.h:2110`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2110); [`enum ec_led_id`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2112), [`enum ec_led_colors`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2138), flags [`EC_LED_FLAGS_QUERY`/`_AUTO` `:2135`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2135)
- Issued by: [`cros_ec_led_send_cmd()` `:75`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L75) — QUERY at probe ([`:186`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L186), fatal), set/auto at runtime ([`:99`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L99)/[`:129`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/leds/leds-cros_ec.c#L129))
- EC-2016 handler: [`led_command_control`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/led_common.c#73) (v1), gated [`CONFIG_LED_COMMON`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/build.mk#55) → **off** on gale (gale drives its RGB ring via an AP-side lp5523, not the EC)
- EC-main handler: [`common/led_common.c:97`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/led_common.c#97)

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

### 7.6 `cros_ec_lightbar` — Pixel lightbar

Cell gated on `EC_FEATURE_LIGHTBAR` ∨ DMI "Link"
([`cros_ec_dev.c:267`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L267)).
Probe checks
[`get_lightbar_version()` `:549`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lightbar.c#L549)
(treats `INVALID_COMMAND` as ["no lightbar" `:150`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_lightbar.c#L150) → `-ENODEV`).

#### 0x28 EC_CMD_LIGHTBAR_CMD · gale ⚠️ addable (hardware absent)

[Defined `:1803`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1803);
subcommand-multiplexed via
[`struct ec_params_lightbar` `:1973`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1973) /
[`struct ec_response_lightbar` `:2022`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2022)
(unions over [`enum lightbar_command` `:2069`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2069):
dump/on/off/brightness/rgb/seq/program/…).
EC-2016: [`lpc_cmd_lightbar`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/lightbar.c#1895)
gated `HAS_TASK_LIGHTBAR` → **off** on gale (no lightbar hardware — moot) ·
EC-main: **REMOVED** (lightbar dropped upstream).

### 7.7 `cros-ec-sensorhub` (+ ring) and the IIO sensor family

Cell gated on
[`cros_ec_get_sensor_count() > 0`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L237):
the count comes from `0x2b` MOTIONSENSE_CMD_DUMP
([`cros_ec_proto.c:961`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L961)),
whose failure falls back to an
[LPC-memmap read requiring `cmd_readmem`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L981) —
absent on I2C. gale: count < 0 → **no cell, ever**; the entire family below is
structurally unreachable (double-locked: no `0x2b`, no MKBP events for the
FIFO).

Command usage across the family (all `0x2b`
[MOTION_SENSE_CMD](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2235)
subcommands from
[`enum motionsense_command` `:2238`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2238),
via [`struct ec_params_motion_sense` `:2523`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2523) /
[`struct ec_response_motion_sense` `:2690`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L2690)):

| Sub-command | Used by | Issued at | Fatal? |
|---|---|---|:--:|
| version probe (`0x08` for `0x2b`) | sensors core | [`cros_ec_sensors_core.c:44`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L44)/[`:268`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L268) | **YES** ([`:272`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L272)) |
| DUMP (0) | MFD gate; accel_legacy reads | [`cros_ec_proto.c:961`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L961); [`cros_ec_accel_legacy.c:54`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/accel/cros_ec_accel_legacy.c#L54) | gate |
| INFO (1) | sensors core probe | [`:285`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L285) | **YES** ([`:288`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors_core.c#L288)) |
| EC_RATE (2), ODR (3), RANGE (4), DATA (6), PERFORM_CALIB (10), OFFSET (11), SCALE (18), LID_ANGLE (14) | sensors / light_prox / baro / lid_angle sysfs+reads | e.g. [`cros_ec_sensors.c:58`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_sensors.c#L58), [`cros_ec_light_prox.c:82`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/light/cros_ec_light_prox.c#L82), [`cros_ec_baro.c:59`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/pressure/cros_ec_baro.c#L59), [`cros_ec_lid_angle.c:57`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/common/cros_ec_sensors/cros_ec_lid_angle.c#L57) | no |
| FIFO_INFO (7), FIFO_READ (8), FIFO_INT_ENABLE (9) | sensorhub ring | [`cros_ec_sensorhub_ring.c:1037`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L1037)/[`:846`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L846)/[`:120`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L120) | FIFO_INFO fatal in [`ring_add` `:1042`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_sensorhub_ring.c#L1042) |

EC-2016 handler: [`host_cmd_motion_sense`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/motion_sense.c#1194)
(v1|v2), gated `HAS_TASK_MOTIONSENSE` → **off** on gale (no sensors — moot) ·
EC-main: [`common/motion_sense.c:1646`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/motion_sense.c#1646) (v1-v4).

---

## 8. Other upstream consumers (not in the gale image)

Listed for completeness — every remaining kernel driver that can talk to a
ChromeOS EC, none of which is shipped (or instantiable) on gale.

### 8.1 `cros_ec_keyb` — matrix keyboard / buttons / switches

DT [`google,cros-ec-keyb(-switches)`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L767) / ACPI `GOOG0007`.
Key events arrive via MKBP (`0x67`, fetched by the core); the driver itself
issues only **`0x61` MKBP_INFO** (v1) —
[`cros_ec_keyb_info()` `:368`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L368),
querying supported/current buttons & switches
([`:476`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L476)).
Old-EC tolerance: [`-ENOPROTOOPT` → "return 0 for everything" `:377`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L377);
other errors are probe-fatal
([`:732`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/input/keyboard/cros_ec_keyb.c#L732)).

#### 0x61 EC_CMD_MKBP_INFO · gale ⚠️ addable

[Defined `:3166`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3166);
[`enum ec_mkbp_info_type` `:3180`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3180).

```c
struct ec_params_mkbp_info  { uint8_t info_type; uint8_t event_type; } __ec_align1;   /* v1 */
struct ec_response_mkbp_info { uint32_t rows; uint32_t cols; uint8_t reserved; } __ec_align_size1;  /* v0 */
```

EC-2016: [`keyboard_get_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/keyboard_mkbp.c#226)
(v0 only!), gated `CONFIG_KEYBOARD_PROTOCOL_MKBP` → **off** on gale ·
EC-main: [`common/mkbp_info.c:154`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/mkbp_info.c#154) (v0|v1).

### 8.2 `cros_ec_mkbp_proximity` / 8.3 `hid-google-hammer` (cbas)

Both consume `0x61` MKBP_INFO + MKBP events. Proximity: DT
[`google,cros-ec-mkbp-proximity`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c#L251),
[command-free probe](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c#L207),
reads the front-proximity switch bit at
[`:75`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/iio/proximity/cros_ec_mkbp_proximity.c#L75).
Hammer's `cbas_ec` half (DT
[`google,cros-cbas`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c#L280) /
ACPI `GOOG000B`) probes base-attached switch support at
[`:185`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c#L185)
(**probe-fatal**, [`-ENXIO` if unsupported `:189`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hid/hid-google-hammer.c#L189)).
Neither can exist on gale (no node, no MKBP).

### 8.4 `cros-ec-cec` — HDMI CEC

Cell gated on `EC_FEATURE_CEC`
([`cros_ec_dev.c:116`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L116)).
Commands: `0xc1` CEC_PORT_COUNT
([`:378`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L378),
[fallback to 1 port `:380`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L380));
`0x08` for CEC_WRITE_MSG version (**probe-fatal**
[`:416`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L416)/[`:514`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L514));
runtime `0xba` CEC_SET (logical addr
[`:181`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L181),
enable [`:236`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L236)),
`0xb8` CEC_WRITE_MSG
([v0 `:204` / v1 `:210`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L204)),
`0xb9` CEC_READ_MSG
([`:107`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/media/cec/platform/cros-ec/cros-ec-cec.c#L107),
on `EC_MKBP_CEC_HAVE_DATA`). Structures:
[`ec_params_cec_write` `:4531`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4531),
[`…_v1` `:4541`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4541),
[`ec_response_cec_read` `:4563`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4563),
[`ec_params_cec_set` `:4580`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4580),
[`ec_response_cec_port_count` `:4617`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4617).
All ❌ absent-in-2016 (CEC added 2018+); EC-main:
[`common/cec.c:278`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/cec.c#278)ff.

### 8.5 `pwm-cros-ec` / 8.6 `cros_kbd_led_backlight`

**pwm-cros-ec** (DT
[`google,cros-ec-pwm(-type)`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L269)):
`0x26` PWM_GET_DUTY
([`:101`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L101);
channel-count probing loop
[`:191`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L191),
**probe-fatal** [`:231`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L231)) and
`0x25` PWM_SET_DUTY
([`:63`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/pwm/pwm-cros-ec.c#L63)).
Structs: [`ec_params_pwm_set_duty` `:1779`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1779)
`{u16 duty; u8 pwm_type; u8 index}`
([`enum ec_pwm_type` `:1769`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1769),
[`EC_PWM_MAX_DUTY`=0xffff `:1767`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1767)),
[`ec_params_pwm_get_duty` `:1787`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1787),
[`ec_response_pwm_get_duty` `:1792`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1792).
**Both ❌ absent-in-2016** (generic PWM commands added later; EC-main
[`common/pwm.c:70`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#70)/[`:90`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#90)).

**cros_kbd_led_backlight** (cell on `EC_FEATURE_PWM_KEYB`, DT/ACPI variants):
`0x23` SET
([`:140`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_kbd_led_backlight.c#L140)) /
`0x22` GET
([`:162`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_kbd_led_backlight.c#L162));
structs [`:1738`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1738)/[`:1747`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L1747)
(`{u8 percent; u8 enabled}` / `{u8 percent}`). gale ⚠️
(EC-2016 [`common/pwm_kblight.c:60`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pwm_kblight.c#60)
gated `CONFIG_PWM_KBLIGHT` → off; no backlight hardware — moot).

### 8.7 `cros_ec_codec` — EC audio codec (DMIC/I2S/WoV)

DT [`google,cros-ec-codec`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L1040) / ACPI `GOOG0013`.
Probe-fatal: `0xbc` EC_CODEC GET_CAPABILITIES
([`:1007`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L1007),
[fatal `:1010`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L1010)).
Runtime: `0xbd` DMIC gain, `0xbe` I2S_RX config, `0xbf` WOV
(all via [`send_ec_host_command()` `:74`](https://elixir.bootlin.com/linux/v6.12.87/source/sound/soc/codecs/cros_ec_codec.c#L74);
struct spans [`:4642`-`:4881`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4642)).
❌ absent-in-2016 — and notably the **audio-codec subsystem has been deleted
from EC-main too** (defines remain, handlers gone): a command family that was
born and died entirely between gale's firmware and today.

### 8.8 `cros_ec_wdt` — EC watchdog

Cell gated on `EC_FEATURE_HANG_DETECT`
([`cros_ec_dev.c:136`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L136)).
Single command **`0x9f` HANG_DETECT**
([sent `:43`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c#L43)):
probe does GET_STATUS + CLEAR_STATUS (**both fatal**,
[`:138`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c#L138)/[`:152`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/watchdog/cros_ec_wdt.c#L152));
runtime RELOAD/SET_TIMEOUT/CANCEL.

```c
struct ec_params_hang_detect  { uint16_t command; uint16_t reboot_timeout_sec; } __ec_align2;
struct ec_response_hang_detect { uint8_t status; } __ec_align1;
```

([defined `:4044`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4044);
[`enum ec_hang_detect_cmds` `:4050`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L4050)).
gale ⚠️: EC-2016 has the **old flag-based** `0x9f`
([`common/ap_hang_detect.c:203`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/ap_hang_detect.c#203),
gated `CONFIG_AP_HANG_DETECT` → off), which is **wire-incompatible** with this
driver's cmd-based API — enabling the 2016 config would *not* make the 6.12
driver work. EC-main:
[`common/ap_hang_detect.c:132`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/ap_hang_detect.c#132).

### 8.9 `cros_charge-control` — charge behaviour / battery sustainer

Cell gated on `EC_FEATURE_CHARGER`
([`cros_ec_dev.c:151`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L151)).
Probe: `0x08` to pick CHARGE_CONTROL v1/v2/v3 (**fatal**,
[`:310`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_charge-control.c#L310)),
then a configuring `0x96` (**fatal**,
[`:347`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/power/supply/cros_charge-control.c#L347)).

#### 0x96 EC_CMD_CHARGE_CONTROL · gale ⚠️ addable (no battery — moot)

[Defined `:3845`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3845);
[`enum ec_charge_control_mode` `:3848`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3848).

```c
struct ec_params_charge_control {
	uint32_t mode;         /* NORMAL / IDLE / DISCHARGE */
	uint8_t cmd;           /* v2+: SET / GET */
	uint8_t flags;         /* v3+ */
	struct { int8_t lower; int8_t upper; } sustain_soc;
} __ec_align4;
```

EC-2016: [`charge_command_charge_control`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_state_v1.c#1004)
(v0|v1), gated `CONFIG_CHARGER_V1/V2` → off (gale has no battery/charger) ·
EC-main: [`common/charge_state.c:2033`](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_state.c#2033)
(**v2|v3 — v0/v1 dropped**; another silent wire-format generation gap).

### 8.10 `cros_typec_switch` — mode-switch/retimer control

ACPI-only (`GOOG001A`,
[`:308`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L308));
[command-free probe](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L283).
Runtime: `0x132` TYPEC_CONTROL USB_MUX_SET
([`:48`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L48)) /
CLEAR_EVENTS
([`:79`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L79)),
`0x133` TYPEC_STATUS poll
([`:90`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_typec_switch.c#L90)).
Structures in §6.1. Never on gale (ARM, no ACPI).

### 8.11 `cros_ec_hwmon` — temperature / fan monitoring

Cell is **unconditional** (created even on gale;
[`cros_ec_dev.c:160`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/mfd/cros_ec_dev.c#L160)),
but the module isn't shipped (`SENSORS_CROS_EC=n`). Reads the EC memory map
via [`cros_ec_cmd_readmem()`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/platform/chrome/cros_ec_proto.c#L1066)
(→ `0x07` on I2C): thermal version @
[`EC_MEMMAP_THERMAL_VERSION`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L82)
(**probe-fatal**: [error `:246` / version 0 → `-ENODEV` `:250`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L246)),
temps @ [`EC_MEMMAP_TEMP_SENSOR`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L77)
([`:49`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L49)),
fans @ [`EC_MEMMAP_FAN`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L78)
([`:31`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L31));
plus `0x70` TEMP_SENSOR_GET_INFO for labels
([`:210`](https://elixir.bootlin.com/linux/v6.12.87/source/drivers/hwmon/cros_ec_hwmon.c#L210),
non-fatal; [struct `:3575`](https://elixir.bootlin.com/linux/v6.12.87/source/include/linux/platform_data/cros_ec_commands.h#L3575),
EC-2016 handler [`temp_sensor_command_get_info`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/temp_sensor.c#160)
gated `CONFIG_TEMP_SENSOR` → off).
On gale: `0x07` works but the memory map has no thermal data → thermal version
reads 0 → clean `-ENODEV`. No point shipping it.

---

## 9. Command index — every command in this document

Cross-reference: command → gale status → where detailed → EC handler in both
trees. **[EC-main]-removed** rows are commands gale implements whose handlers
**no longer exist in current upstream** — the 2016↔now drift in one column.

| Cmd | Name | gale | § | EC-2016 handler | EC-main handler |
|--:|---|:--:|:--:|---|---|
| `0x00` | PROTO_VERSION | ✅ | 1.4 | [host_command.c:436](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#436) | [host_command.c:87](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#87) |
| `0x01` | HELLO | ✅ | 3.2 | [host_command.c:451](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#451) | [host_command.c:101](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#101) |
| `0x02` | GET_VERSION | ✅ | 4.1 | [system.c:1080](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1080) | [system.c:1731](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1731) (+v1) |
| `0x03` | READ_TEST | ✅ | — | [host_command.c:474](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#474) | **removed** |
| `0x04` | GET_BUILD_INFO | ✅ | 4.2 | [system.c:1091](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1091) | [system.c:1771](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1771) |
| `0x05` | GET_CHIP_INFO | ✅ | 4.2 | [system.c:1107](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1107) | [system.c:1787](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1787) |
| `0x06` | GET_BOARD_VERSION | ⚠️ | 4.2 | [system.c:1122](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1122) (`CONFIG_BOARD_VERSION`) | [system.c:1807](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1807) |
| `0x07` | READ_MEMMAP | ✅ | 3.2 | [host_command.c:500](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#500) | [host_command.c:131](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#131) |
| `0x08` | GET_CMD_VERSIONS | ✅ | 3.2 | [host_command.c:524](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#524) | [host_command.c:157](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#157) |
| `0x09` | GET_COMMS_STATUS | ⚠️ | 3.2 | [host_command.c:619](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#619) (`CONFIG_HOST_COMMAND_STATUS`) | [host_command.c:215](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#215) |
| `0x0b` | GET_PROTOCOL_INFO | ✅ | 3.2 | [i2c-stm32f0.c:615](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#615) | per-transport Zephyr shims |
| `0x0d` | GET_FEATURES | ✅ | 3.3 | [host_command.c:760](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#760) | [host_command.c:190](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_command.c#190) |
| `0x10` | FLASH_INFO | ✅ | 4.2 | [flash.c:781](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#781) | [flash.c:1598](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/flash.c#1598) (+v2) |
| `0x11`-`0x16` | FLASH_READ/WRITE/ERASE/PROTECT/REGION_INFO | ✅ | 4.2 note | [flash.c:800](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#800)ff | [flash.c:1629](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/flash.c#1629)ff (PROTECT dropped v0) |
| `0x17` | VBNV_CONTEXT | ✅ | 7.1 | [system.c:1155](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1155) | **removed** |
| `0x22`/`0x23` | PWM_GET/SET_KEYBOARD_BACKLIGHT | ⚠️ | 8.6 | [pwm_kblight.c:60](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pwm_kblight.c#60)/[:72](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pwm_kblight.c#72) | [keyboard_backlight.c:190](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/keyboard_backlight.c#190)/[:204](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/keyboard_backlight.c#204) |
| `0x25`/`0x26` | PWM_SET/GET_DUTY | ❌ | 8.5 | not in tree | [pwm.c:70](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#70)/[:90](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pwm.c#90) |
| `0x28` | LIGHTBAR_CMD | ⚠️ | 7.6 | [lightbar.c:1895](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/lightbar.c#1895) | **removed** |
| `0x29` | LED_CONTROL | ⚠️ | 7.5 | [led_common.c:73](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/led_common.c#73) | [led_common.c:97](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/led_common.c#97) |
| `0x2a` | VBOOT_HASH | ✅ | — | [vboot_hash.c:442](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/vboot_hash.c#442) | [vboot_hash.c:533](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/vboot_hash.c#533) |
| `0x2b` | MOTION_SENSE_CMD | ⚠️ | 7.7 | [motion_sense.c:1194](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/motion_sense.c#1194) | [motion_sense.c:1646](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/motion_sense.c#1646) |
| `0x44`-`0x47` | RTC_* | ⚠️ | 7.2 | [chip-specific only](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/lm4/system.c#702) (no stm32) | [zephyr/shim/src/rtc.c:204](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/zephyr/shim/src/rtc.c#204)ff |
| `0x60` | MKBP_STATE | ⚠️ | — | [keyboard_mkbp.c:210](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/keyboard_mkbp.c#210) | **removed** |
| `0x61` | MKBP_INFO | ⚠️ | 8.1 | [keyboard_mkbp.c:226](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/keyboard_mkbp.c#226) (v0 only) | [mkbp_info.c:154](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/mkbp_info.c#154) |
| `0x67` | GET_NEXT_EVENT | ⚠️ | 3.2 | [mkbp_event.c:111](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/mkbp_event.c#111) | [mkbp_event.c:529](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/mkbp_event.c#529) (v0-v3) |
| `0x70` | TEMP_SENSOR_GET_INFO | ⚠️ | 8.11 | [temp_sensor.c:160](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/temp_sensor.c#160) | [temp_sensor.c:175](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/temp_sensor.c#175) |
| `0x8d` | HOST_EVENT_GET_WAKE_MASK | ⚠️ | 3.2 | [host_event_commands.c:205](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_event_commands.c#205) | [host_event_commands.c:550](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/host_event_commands.c#550) |
| `0x92` | GPIO_SET | ✅ | 5 | [gpio_commands.c:274](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#274) | [gpio_commands.c:295](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#295) |
| `0x93` | GPIO_GET | ✅ | 5 | [gpio_commands.c:259](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#259) | [gpio_commands.c:280](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/gpio_commands.c#280) |
| `0x96` | CHARGE_CONTROL | ⚠️ | 8.9 | [charge_state_v1.c:1004](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_state_v1.c#1004) (v0/v1) | [charge_state.c:2033](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_state.c#2033) (v2/v3!) |
| `0x97`/`0x98` | CONSOLE_SNAPSHOT/READ | ✅ | 4.3 | [uart_buffering.c:357](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#357)/[:419](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#419) | [uart_hostcmd.c:17](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#17)/[:53](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uart_hostcmd.c#53) |
| `0x9e` | I2C_PASSTHRU | ⚠️ | 7.4 | [i2c.c:701](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/i2c.c#701) (`CONFIG_I2C_MASTER`) | [i2c_passthru.c:260](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/i2c_passthru.c#260) |
| `0x9f` | HANG_DETECT | ⚠️* | 8.8 | [ap_hang_detect.c:203](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/ap_hang_detect.c#203) (*old flag API — wire-incompatible*) | [ap_hang_detect.c:132](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/ap_hang_detect.c#132) |
| `0xa2` | EXTERNAL_POWER_LIMIT | ⚠️ | 6.3 | [charge_manager.c:960](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#960) | [charge_manager.c:1916](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1916) |
| `0xa9` | HOST_SLEEP_EVENT | ❌ | 3.2 | not in tree | [power/host_sleep.c:90](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/power/host_sleep.c#90) |
| `0xb6` | ENTERING_MODE | ✅ | — | [host_command.c:649](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#649) | **removed** |
| `0xb8`-`0xc1` | CEC_* | ❌ | 8.4 | not in tree | [cec.c:278](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/cec.c#278)ff |
| `0xbc`-`0xbf` | EC_CODEC_* | ❌ | 8.7 | not in tree | **removed** (defines only) |
| `0xd2` | REBOOT_EC | ✅ | 4.2 | [system.c:1202](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1202) | [system.c:1871](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/system.c#1871) |
| `0xd3` | GET_PANIC_INFO | ✅ | 4.3 | [panic_output.c:233](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c#233) | [panic_output.c:618](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/panic_output.c#618) (v0-v2) |
| `0x101` | USB_PD_CONTROL | ✅ v0/v1 | 6.1 | [usb_pd_protocol.c:3159](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3159) | [usb_pd_host_cmd_common.c:202](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#202) (+v2) |
| `0x102` | USB_PD_PORTS | ✅ | 6.1 | [usb_pd_protocol.c:3068](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3068) | [usb_pd_host_cmd.c:41](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd.c#41) |
| `0x103` | USB_PD_POWER_INFO | ⚠️ | 6.2 | [charge_manager.c:878](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/charge_manager.c#878) (`CONFIG_CHARGE_MANAGER`) | [charge_manager.c:1801](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1801) |
| `0x104` | PD_HOST_EVENT_STATUS | ⚠️ | 6.5 | [host_command_pd.c:242](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command_pd.c#242) (`HAS_TASK_PDCMD`) | [usb_pd_host_cmd_common.c:346](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#346) |
| `0x105` | CHARGE_PORT_COUNT | ❌ | 6.3 | not in tree | [charge_manager.c:1813](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/charge_manager.c#1813) |
| `0x110` | USB_PD_FW_UPDATE | ✅ | — | [usb_pd_protocol.c:3257](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3257) | **removed** |
| `0x111` | USB_PD_RW_HASH_ENTRY | ✅ | — | [usb_pd_protocol.c:3287](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3287) | [usb_pd_host_cmd.c:72](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd.c#72) |
| `0x112` | USB_PD_DEV_INFO | ✅ | — | [usb_pd_protocol.c:3312](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3312) | **removed** |
| `0x113` | USB_PD_DISCOVERY | ⚠️ | 6.3 | [usb_pd_policy.c:821](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_policy.c#821) (`…ALT_MODE_DFP`) | [usb_pd_host_cmd_common.c:442](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#442) |
| `0x115` | PD_GET_LOG_ENTRY | ⚠️ | 6.4 | [pd_log.c:192](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/pd_log.c#192) (`CONFIG_USB_PD_LOGGING`) | [pd_log.c:86](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/pd_log.c#86) |
| `0x11a` | USB_PD_MUX_INFO | ❌ | 6.1 | not in tree | [usb_mux.c:912](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#912) |
| `0x121` | GET_UPTIME_INFO | ❌ | 4.3 | not in tree | [uptime.c:42](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/uptime.c#42) |
| `0x12c`-`0x130` | REGULATOR_* | ❌ | 7.3 | not in tree | [regulator.c:32](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/regulator.c#32)ff |
| `0x131`-`0x133`, `0x13c` | TYPEC_* | ❌ | 6.1 | not in tree | [usb_pd_host_cmd_common.c:312](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usb_pd_host_cmd_common.c#312)ff, [usbc/](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/usbc/) |
| `0x134`/`0x135` | PCHG_COUNT / PCHG | ❌ | 6.6 | not in tree | [peripheral_charger.c:975](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#975)/[:1021](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/common/peripheral_charger.c#1021) |
| `0x603` | USB_PD_MUX_ACK | ❌ | 6.1 | not in tree | [usb_mux.c:942](https://chromium.googlesource.com/chromiumos/platform/ec/+/37850ff4dfdad2a8062702be5a3591d195f4c9c1/driver/usb_mux/usb_mux.c#942) |

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
   documents what a forward-port would take. Note also the reverse drift:
   current upstream has **deleted** five commands gale relies on
   (`READ_TEST`, `VBNV_CONTEXT`, `ENTERING_MODE`, `USB_PD_FW_UPDATE`,
   `USB_PD_DEV_INFO` — §9), so a forward-ported EC would *break* those unless
   re-added.

**For the power-consumption goal specifically**, the shortest paths, in
increasing effort:
(a) custom RW host command returning gale's four ADC channels
(VBUS mV / input mA / CC1 / CC2 — the values behind the EC console
[`gale vbus`](https://github.com/mithro/gwifi-openwrt/blob/gale-ec-renode-equivalence/gale-ec/board/gale/board.c)),
read via `/dev/cros_ec` — zero kernel changes, minimal EC change;
(b) `CONFIG_CHARGE_MANAGER` + `EC_FEATURE_USB_PD` → stock
`cros-usbpd-charger` works unmodified — the clean, upstream-shaped solution;
(c) full TCPMv2 forward-port — not justified by telemetry alone.
