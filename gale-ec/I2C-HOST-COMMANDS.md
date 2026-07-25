# gale EC — I2C host-command reference

Complete reference for the **31 host commands** the gale EC answers over its I2C slave interface.
The application processor (AP, an IPQ4019) is the I2C **master**; the EC is the **slave**. This is the
authoritative set, extracted from the `__hcmds` table in the firmware (each entry is registered with
`DECLARE_HOST_COMMAND`).

## Transport

- **Bus / addressing.** The EC is an I2C slave at 7-bit address **`0x3C`** (`STM32_I2C_OAR1 = 0x803C`;
  [`board/gale/board.h:104`](board/gale/board.h#L104) `#define CONFIG_HOSTCMD_I2C_SLAVE_ADDR 0x3C`).
  8-bit form: `0x78` write / `0x79` read.
- **Protocol.** EC host-command **protocol v3** (packet form). The AP writes a request packet, then
  reads a response packet. Query the exact capabilities at runtime with
  [`EC_CMD_GET_PROTOCOL_INFO` (0x0b)](#0x000b-ec_cmd_get_protocol_info).

**Request packet** = `struct ec_host_request` header (8 bytes) + command params:

| Off | Field | Type | Meaning |
|--:|---|---|---|
| 0 | `struct_version` | `uint8` | Header version, **=3**. Wrong value → `EC_RES_INVALID_HEADER`. |
| 1 | `checksum` | `uint8` | Byte-sum of the **entire** request (header+params) must equal 0 (mod 256). |
| 2 | `command` | `uint16` | The `EC_CMD_*` code (little-endian). |
| 4 | `command_version` | `uint8` | 0-based command version (must be in the command's `version_mask`). |
| 5 | `reserved` | `uint8` | =0. |
| 6 | `data_len` | `uint16` | Length of the params that follow the header. |

**Response packet** = `struct ec_host_response` header (8 bytes) + response data:

| Off | Field | Type | Meaning |
|--:|---|---|---|
| 0 | `struct_version` | `uint8` | =3. |
| 1 | `checksum` | `uint8` | Byte-sum of the entire response must equal 0 (mod 256). |
| 2 | `result` | `uint16` | `EC_RES_*` status (0 = success). |
| 4 | `data_len` | `uint16` | Length of the response data that follows. |
| 6 | `reserved` | `uint16` | =0. |

The per-command tables below document the **params** (request data) and **response data** — i.e. the
bytes *after* the 8-byte header on each side.

## Result codes (`result` field)

`0 EC_RES_SUCCESS` · `1 INVALID_COMMAND` · `2 ERROR` · `3 INVALID_PARAM` · `4 ACCESS_DENIED` ·
`5 INVALID_RESPONSE` · `6 INVALID_VERSION` · `7 INVALID_CHECKSUM` · `8 IN_PROGRESS` · `9 UNAVAILABLE` ·
`10 TIMEOUT` · `11 OVERFLOW` · `12 INVALID_HEADER` · `13 REQUEST_TRUNCATED` · `14 RESPONSE_TOO_BIG` ·
`15 BUS_ERROR` · `16 BUSY`. A command called with a `command_version` bit not set in its
`version_mask` is rejected by the dispatcher with `EC_RES_INVALID_VERSION` before the handler runs.

## Summary

Version-mask column: bit *N* set ⇒ command version *N* is accepted (`0x1`=v0 only, `0x3`=v0+v1, …).

| Cmd | Name | Ver | Source | Description |
|--:|---|--:|---|---|
| `0x00` | [`EC_CMD_PROTO_VERSION`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#427) | 0x1 | host_command.c | Highest supported legacy protocol version |
| `0x01` | [`EC_CMD_HELLO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#440) | 0x1 | host_command.c | Echo test: returns `in_data + 0x01020304` |
| `0x02` | [`EC_CMD_GET_VERSION`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1055) | 0x1 | system.c | RO/RW version strings + running image |
| `0x03` | [`EC_CMD_READ_TEST`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#455) | 0x1 | host_command.c | Return a computed pattern (comms read test) |
| `0x04` | [`EC_CMD_GET_BUILD_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1084) | 0x1 | system.c | Build-info string |
| `0x05` | [`EC_CMD_GET_CHIP_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1095) | 0x1 | system.c | Chip vendor / name / revision |
| `0x07` | [`EC_CMD_READ_MEMMAP`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#483) | 0x1 | host_command.c | Read the EC memory-map region |
| `0x08` | [`EC_CMD_GET_CMD_VERSIONS`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#505) | 0x3 | host_command.c | Version mask supported by a command |
| `0x0a` | [`EC_CMD_TEST_PROTOCOL`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#653) | 0x1 | host_command.c | Return caller-specified result+data (protocol test) |
| `0x0b` | [`EC_CMD_GET_PROTOCOL_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/chip/stm32/i2c-stm32f0.c#601) | 0x1 | i2c-stm32f0.c | Supported protocol versions + max sizes |
| `0x0d` | [`EC_CMD_GET_FEATURES`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#670) | 0x1 | host_command.c | 64-bit supported-feature bitmap |
| `0x17` | [`EC_CMD_VBNV_CONTEXT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1127) | 0x3 | system.c | Read/write verified-boot NV context |
| `0x2a` | [`EC_CMD_VBOOT_HASH`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/vboot_hash.c#407) | 0x1 | vboot_hash.c | Get / start / abort image hash |
| `0xb6` | [`EC_CMD_ENTERING_MODE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/host_command.c#641) | 0x1 | host_command.c | Notify EC of a mode transition |
| `0xd2` | [`EC_CMD_REBOOT_EC`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/system.c#1159) | 0x1 | system.c | Reboot the EC with flags |
| `0xd3` | [`EC_CMD_GET_PANIC_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/panic_output.c#220) | 0x1 | panic_output.c | Return the saved panic data block |
| `0x10` | [`EC_CMD_FLASH_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#738) | 0x3 | flash.c | Flash geometry (+ v1 sizes/flags) |
| `0x11` | [`EC_CMD_FLASH_READ`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#785) | 0x1 | flash.c | Read bytes from internal flash |
| `0x12` | [`EC_CMD_FLASH_WRITE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#810) | 0x3 | flash.c | Write bytes to internal flash |
| `0x13` | [`EC_CMD_FLASH_ERASE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#833) | 0x1 | flash.c | Erase a region of internal flash |
| `0x15` | [`EC_CMD_FLASH_PROTECT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#858) | 0x3 | flash.c | Get / set flash write-protect flags |
| `0x16` | [`EC_CMD_FLASH_REGION_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/flash.c#902) | 0x2 | flash.c | Offset+size of a named flash region |
| `0x92` | [`EC_CMD_GPIO_SET`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#262) | 0x1 | gpio_commands.c | Set an output GPIO by name |
| `0x93` | [`EC_CMD_GPIO_GET`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/gpio_commands.c#209) | 0x3 | gpio_commands.c | Get a GPIO value/flags by name (v1: +index) |
| `0x97` | [`EC_CMD_CONSOLE_SNAPSHOT`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#330) | 0x1 | uart_buffering.c | Snapshot the console buffer for reading |
| `0x98` | [`EC_CMD_CONSOLE_READ`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/uart_buffering.c#397) | 0x3 | uart_buffering.c | Read the snapshotted console buffer |
| `0x101` | [`EC_CMD_USB_PD_CONTROL`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3124) | 0x3 | usb_pd_protocol.c | Get (v1: set) a USB-PD port's role/mux/state |
| `0x102` | [`EC_CMD_USB_PD_PORTS`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3095) | 0x1 | usb_pd_protocol.c | Number of USB-PD ports |
| `0x110` | [`EC_CMD_USB_PD_FW_UPDATE`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3198) | 0x1 | usb_pd_protocol.c | Passthrough FW update to a PD device (VDM) |
| `0x111` | [`EC_CMD_USB_PD_RW_HASH_ENTRY`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3296) | 0x1 | usb_pd_protocol.c | Store a PD device's RW image hash |
| `0x112` | [`EC_CMD_USB_PD_DEV_INFO`](https://chromium.googlesource.com/chromiumos/platform/ec/+/7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb/common/usb_pd_protocol.c#3326) | 0x1 | usb_pd_protocol.c | Return a PD device's info + RW hash |

---

## Command details

Structs are quoted verbatim from `include/ec_commands.h` and are `__packed` (STM32 = little-endian, so
multi-byte fields are LE on the wire). Offsets are within the **payload** — i.e. the bytes *after* the
8-byte transport header on each side. The dispatcher rejects an unregistered command with
`EC_RES_INVALID_COMMAND` and a `command_version` not in the mask with `EC_RES_INVALID_VERSION` before
the handler runs, so handlers assume a valid version.

### `0x00` EC_CMD_PROTO_VERSION — legacy protocol version
- **Versions:** v0. Legacy/kernel-compat.
- **Request:** none.
- **Response** `struct ec_response_proto_version` (4 B): `version` u32 — the constant `EC_PROTO_VERSION = 0x00000002`.
- **Errors:** always `EC_RES_SUCCESS`.
- **Example:** request 0 B → response `02 00 00 00`.

### `0x01` EC_CMD_HELLO — liveness echo
- **Versions:** v0.
- **Request** `struct ec_params_hello` (4 B): `in_data` u32 — any value.
- **Response** `struct ec_response_hello` (4 B): `out_data` u32 = `in_data + 0x01020304` (proves the EC processed, not echoed).
- **Errors:** always `EC_RES_SUCCESS`.
- **Example:** `in_data=0xa0b0c0d0` (`d0 c0 b0 a0`) → `out_data=0xa1b2c3d4` (`d4 c3 b2 a1`).

### `0x02` EC_CMD_GET_VERSION — firmware versions
- **Versions:** v0.
- **Request:** none.
- **Response** `struct ec_response_get_version` (100 B):
  ```c
  char version_string_ro[32];   // @0  NUL-term RO version
  char version_string_rw[32];   // @32 NUL-term RW version
  char reserved[32];            // @64 legacy RW-B slot (never written)
  uint32_t current_image;       // @96 ec_current_image: 0=UNKNOWN,1=RO,2=RW
  ```
- **Errors:** always `EC_RES_SUCCESS`.
- **Example (running RO):** `"gale_v1.1.5337-0115719"\0…`(32) + RW(32) + reserved(32) + `01 00 00 00`.

### `0x03` EC_CMD_READ_TEST — transport read test
- **Versions:** v0.
- **Request** `struct ec_params_read_test` (8 B): `offset` u32 (start value), `size` u32 (bytes; internally `size/4` words).
- **Response** `struct ec_response_read_test` (128 B): `data[32]` u32 — first `size/4` words filled with `offset+i`; rest untouched. `response_size` is always 128.
- **Errors:** `EC_RES_ERROR` if `size/4 > 32`; else `EC_RES_SUCCESS`.
- **Example:** `offset=0x100, size=0x10` → `data[0..3]=0x100..0x103` → `00 01 00 00 01 01 00 00 02 01 00 00 03 01 00 00 …`.

### `0x04` EC_CMD_GET_BUILD_INFO — build string
- **Versions:** v0.
- **Request:** none. **Response:** raw NUL-terminated build-info string (no struct), length = `strlen+1`, capped at `response_max`.
- **Errors:** always `EC_RES_SUCCESS`.

### `0x05` EC_CMD_GET_CHIP_INFO — chip identity
- **Versions:** v0.
- **Request:** none.
- **Response** `struct ec_response_get_chip_info` (96 B): `vendor[32]`, `name[32]`, `revision[32]` (all NUL-term). On this STM32F0 e.g. `vendor="stm"`, `name="stm32f07x"`.
- **Errors:** always `EC_RES_SUCCESS`.

### `0x07` EC_CMD_READ_MEMMAP — read memory-map region
- **Versions:** v0. (Compiled because gale is not `CONFIG_LPC` — the I2C/SPI alternate to a directly-mapped region.)
- **Request** `struct ec_params_read_memmap` (2 B): `offset` u8, `size` u8 — into the `EC_MEMMAP_*` region.
- **Response:** `size` raw bytes from `host_get_memmap(offset)`.
- **Errors:** `EC_RES_INVALID_PARAM` if `size`/`offset`/`offset+size > EC_MEMMAP_SIZE (255)`; else `EC_RES_SUCCESS`.

### `0x08` EC_CMD_GET_CMD_VERSIONS — a command's supported versions
- **Versions:** v0+v1.
- **Request:** v0 `struct ec_params_get_cmd_versions` (1 B): `cmd` u8. v1 `…_v1` (2 B): `cmd` u16 (allows ids ≥256).
- **Response** `struct ec_response_get_cmd_versions` (4 B): `version_mask` u32 — bit N = version N supported by the queried command.
- **Errors:** `EC_RES_INVALID_PARAM` if the queried command isn't registered; else `EC_RES_SUCCESS`.
- **Example:** query `cmd=0x08` → `03 00 00 00` (this command supports v0+v1).

### `0x0a` EC_CMD_TEST_PROTOCOL — protocol conformance test
- **Versions:** v0. Testing tool that fabricates a response.
- **Request** `struct ec_params_test_protocol` (40 B): `ec_result` u32 (the code to return verbatim), `ret_len` u32 (response bytes; copy clamped to 32), `buf[32]`.
- **Response** `struct ec_response_test_protocol` (32 B): `buf[32]` — zero-filled then first `min(ret_len,32)` bytes copied from the request.
- **Errors:** returns whatever `ec_result` the caller supplied.
- **Example:** `ec_result=3, ret_len=4, buf="ABCD…"` → result `EC_RES_INVALID_PARAM`, response `41 42 43 44`.

### `0x0b` EC_CMD_GET_PROTOCOL_INFO — transport capabilities
- **Versions:** v0. Handler is `i2c_get_protocol_info` (I2C-specific), compiled because `CONFIG_HOSTCMD_I2C_SLAVE_ADDR` is set.
- **Request:** none.
- **Response** `struct ec_response_get_protocol_info` (12 B):
  ```c
  uint32_t protocol_versions;         // @0 bit N = version N. Gale = (1<<3) = 0x8 → v3 only
  uint16_t max_request_packet_size;   // @4 128 (I2C_MAX_HOST_PACKET_SIZE)
  uint16_t max_response_packet_size;  // @6 128
  uint32_t flags;                     // @8 0 (bit0 EC_PROTOCOL_INFO_IN_PROGRESS_SUPPORTED not advertised)
  ```
- **Errors:** always `EC_RES_SUCCESS`.
- **Example:** `08 00 00 00 | 80 00 | 80 00 | 00 00 00 00` — v3 only, 128/128, no flags. **Use this to discover the 128-byte packet cap before large transfers.**

### `0x0d` EC_CMD_GET_FEATURES — 64-bit feature bitmap
- **Versions:** v0.
- **Request:** none.
- **Response** `struct ec_response_get_features` (8 B): `flags[2]` u32 — 64-bit map; `flags[0]`=codes 0-31, `flags[1]`=codes ≥32. Each bit set only if the matching CONFIG is compiled. Notable codes: bit1 `FLASH`, bit9 `PORT80`(LPC), bit13 `HOST_EVENTS`, bit14 `GPIO`, bit15 `I2C`(master), bit22 `USB_PD`.
- **Errors:** always `EC_RES_SUCCESS`.
- **Example (gale):** compiles `FLASH`(1)+`GPIO`(14), no I2C-master/host-events/LPC → `flags = {0x00004002, 0}` → `02 40 00 00 00 00 00 00`.

### `0x10` EC_CMD_FLASH_INFO — flash geometry
- **Versions:** v0+v1.
- **Request:** none.
- **Response v0** `struct ec_response_flash_info` (16 B): `flash_size` u32 (`0x20000`=128 KB), `write_block_size` u32 (`0x2`), `erase_block_size` u32 (`0x800`=2 KB), `protect_block_size` u32 (`0x1000`=4 KB).
- **Response v1** `struct ec_response_flash_info_1` (24 B): same 4, plus `write_ideal_size` u32 (transport-dependent) and `flags` u32 — `EC_FLASH_INFO_ERASE_TO_0 (1<<0)` set only if flash erases to 0; **gale erases to 1 → flags = 0**.
- **Errors:** always `EC_RES_SUCCESS`.
- **Example (v1):** `00 00 02 00 | 02 00 00 00 | 00 08 00 00 | 00 10 00 00 | <ideal> | 00 00 00 00`.

### `0x11` EC_CMD_FLASH_READ — read internal flash
- **Versions:** v0.
- **Request** `struct ec_params_flash_read` (8 B): `offset` u32 (storage-relative; +0 on gale), `size` u32.
- **Response:** `size` raw flash bytes.
- **Errors:** `EC_RES_OVERFLOW` if `size > response_max`; `EC_RES_ERROR` if the range is invalid; else `EC_RES_SUCCESS`.
- **Example:** `offset=0, size=0x40` (`00 00 00 00 40 00 00 00`) → 64 bytes at offset 0.

### `0x12` EC_CMD_FLASH_WRITE — write internal flash
- **Versions:** v0+v1 (identical handler; `EC_FLASH_WRITE_VER0_SIZE=64` is only a host-side chunk hint).
- **Request** `struct ec_params_flash_write` (8 B header + data): `offset` u32, `size` u32, then `size` data bytes. Offset/size must be 2-byte aligned.
- **Response:** none.
- **Errors (in order):** `EC_RES_ACCESS_DENIED` if `ALL_NOW` protection set; `EC_RES_INVALID_PARAM` if payload truncated; `EC_RES_ACCESS_DENIED` if writing the running image (`system_unsafe_to_overwrite`); `EC_RES_ERROR` on a failed write; else `EC_RES_SUCCESS`.
- **Example:** write `AB CD` at RW `0x10000` → `00 00 01 00 | 02 00 00 00 | AB CD`.

### `0x13` EC_CMD_FLASH_ERASE — erase a flash region
- **Versions:** v0.
- **Request** `struct ec_params_flash_erase` (8 B): `offset` u32, `size` u32 — both 2 KB (`0x800`) aligned.
- **Response:** none. (The `EC_RES_IN_PROGRESS` streaming variant needs `CONFIG_HOST_COMMAND_STATUS`, which is **off** on gale — a single final status is returned.)
- **Errors:** `EC_RES_ACCESS_DENIED` if `ALL_NOW` set or erasing the running image; `EC_RES_ERROR` on a failed erase; else `EC_RES_SUCCESS`.
- **Example:** erase one page at RW `0x10000` → `00 00 01 00 | 00 08 00 00`.

### `0x15` EC_CMD_FLASH_PROTECT — get/set write-protect
- **Versions:** v0+v1 (identical; v0 is a driver-compat kludge).
- **`EC_FLASH_PROTECT_*` bits** (the `flags`/`mask` fields and the response `flags`):
  | Bit | Name | Meaning |
  |--:|---|---|
  | `1<<0` | `RO_AT_BOOT` | RO region protected at next boot |
  | `1<<1` | `RO_NOW` | RO protected now (locks at-boot changes) |
  | `1<<2` | `ALL_NOW` | Entire flash protected now, until reboot |
  | `1<<3` | `GPIO_ASSERTED` | WP GPIO asserted now (on gale = `!GPIO_WP_L`) |
  | `1<<4` | `ERROR_STUCK` | A bank is stuck locked (error) |
  | `1<<5` | `ERROR_INCONSISTENT` | Protection is in an inconsistent state (error) |
  | `1<<6` | `ALL_AT_BOOT` | Entire flash protected at next boot |
- **Request** `struct ec_params_flash_protect` (8 B): `mask` u32 (which bits to act on; `0` = read-only query), `flags` u32 (new values for masked bits). Only RO/ALL × AT_BOOT/NOW are actionable.
- **Response** `struct ec_response_flash_protect` (12 B): `flags` u32 (current, all bits above), `valid_flags` u32 (`0x7F` on STM32F0), `writable_flags` u32 (which can change now).
- **When usable / gale notes:** `RO_NOW`/`ALL_NOW` **cannot** be set immediately on STM32F0 (`flash_physical_protect_now` → `EC_ERROR_INVAL`, swallowed — the bit just won't appear in `flags`). Escalating AT_BOOT to ALL needs WP asserted + RO_AT_BOOT set.
- **Errors:** always `EC_RES_SUCCESS` — failures surface in the returned `flags`/`writable_flags`, not as a code.
- **Example:** `mask=0x1, flags=0x1` (`01 00 00 00 01 00 00 00`) → typical unlocked-WP reply `flags=0x0, valid=0x7F, writable=0x1`.

### `0x16` EC_CMD_FLASH_REGION_INFO — region offset/size
- **Versions:** v1 only (mask `0x2`).
- **Request** `struct ec_params_flash_region_info` (4 B): `region` u32 — `enum ec_flash_region`: `0=RO`, `1=RW`, `2=WP_RO`.
- **Response** `struct ec_response_flash_region_info` (8 B): `offset` u32, `size` u32 (storage-relative). Gale: RO @`0x0`, RW @`0x10000` size `0x10000`, WP_RO @`0x0` size `0x10000`.
- **Errors:** `EC_RES_INVALID_PARAM` for a region > 2; else `EC_RES_SUCCESS`.
- **Example:** `region=1` → `00 00 01 00 | 00 00 01 00`.

### `0x17` EC_CMD_VBNV_CONTEXT — vboot NV context read/write
- **Versions:** v0+v1 (identical; both bits set for driver compat).
- **Request** `struct ec_params_vbnvcontext` (20 B): `op` u32 (`0=READ`, `1=WRITE`), `block[16]` (context to store, WRITE only).
- **Response** `struct ec_response_vbnvcontext` (16 B on READ): `block[16]` = stored context. WRITE returns empty.
- **When usable / side effects:** WRITE **persists** the 16-byte block to NV storage.
- **Errors:** `EC_RES_ERROR` on get/set failure or an `op` other than 0/1; else `EC_RES_SUCCESS`.
- **Example:** READ → `op=00 00 00 00` + 16 don't-care → 16-byte context. WRITE → `op=01 00 00 00` + 16 bytes → empty, SUCCESS.

### `0x2a` EC_CMD_VBOOT_HASH — image hash get/start/abort
- **Versions:** v0. Present because gale defines `CONFIG_VBOOT_HASH`.
- **Request** `struct ec_params_vboot_hash` (76 B):
  ```c
  uint8_t cmd;            // 0=GET 1=ABORT 2=START 3=RECALC(start+block)
  uint8_t hash_type;      // 0=SHA256 (only)
  uint8_t nonce_size;     // nonce bytes prepended; may be 0
  uint8_t reserved0;      // 0
  uint32_t offset;        // flash offset; 0xfffffffe=RO region, 0xfffffffd=RW region
  uint32_t size;          // bytes to hash
  uint8_t nonce_data[64]; // ignored if nonce_size=0
  ```
- **Response** `struct ec_response_vboot_hash` (76 B):
  ```c
  uint8_t status;         // 0=NONE 1=DONE 2=BUSY
  uint8_t hash_type;      // 0=SHA256 when DONE
  uint8_t digest_size;    // 32 when DONE
  uint8_t reserved0;
  uint32_t offset;        // actual offset hashed
  uint32_t size;          // actual size hashed
  uint8_t hash_digest[64];// first 32 B = SHA-256 (DONE only)
  ```
- **When usable / side effects:** START/RECALC begin a background hash; **RECALC blocks the host-command task** until done. ABORT cancels an in-progress hash.
- **Errors:** `EC_RES_INVALID_PARAM` (non-SHA256 type, `nonce_size>64`, bad START params, or unknown `cmd`); `EC_RES_ERROR` on other start failure; else `EC_RES_SUCCESS`.
- **Example:** GET RW hash → `cmd=00 type=00 ns=00 rsvd=00`, `offset=0xfffffffd`, `size=0`, nonce 0 → if done: `status=01 type=00 digest_size=20 …` + offset + size + 32-byte digest + 32 zero bytes. (Matches the console `hash` digest, e.g. `5a2d7c5a…878b20`.)

### `0x92` EC_CMD_GPIO_SET — drive an output GPIO
- **Versions:** v0.
- **Request** `struct ec_params_gpio_set` (33 B): `name[32]` (NUL-term, case-insensitive), `val` u8 (0=low, non-zero=high).
- **Response:** none.
- **When usable:** header notes "only when write-protect disabled"; runtime gate `if (system_is_locked()) return EC_RES_ACCESS_DENIED`. **On gale `CONFIG_SYSTEM_UNLOCKED` makes `system_is_locked()` false, so SET is allowed** — unless `force_locked` was set (e.g. via console `syslock`). The signal must be an implemented output.
- **Errors:** `EC_RES_ACCESS_DENIED` if locked; `EC_RES_ERROR` if name not found / not an output; else `EC_RES_SUCCESS`.
- **Example:** `name="ERROR_LED"`(32) + `val=0x01`.

### `0x93` EC_CMD_GPIO_GET — read a GPIO
- **Versions:** v0+v1.
- **Request v0** `struct ec_params_gpio_get` (32 B): `name[32]`.
- **Request v1** `struct ec_params_gpio_get_v1` (33 B): `subcmd` u8 (`0=BY_NAME`, `1=COUNT`, `2=INFO`) + union (`name[32]` for BY_NAME, `index` u8 for INFO).
- **Response v0** (1 B): `val` u8 (level 0/1).
- **Response v1:** BY_NAME/COUNT → `val` u8 (1 B). INFO → `val` u8 + `name[32]` + `flags` u32 (37 B). **`flags` bits** (`gpio.h`): `1<<0` OPEN_DRAIN, `1<<1` PULL_UP, `1<<2` PULL_DOWN, `1<<3` ANALOG, `1<<4` INPUT, `1<<5` OUTPUT, `1<<6` LOW, `1<<7` HIGH, `1<<8` INT_RISING, `1<<9` INT_FALLING, `1<<11` INT_LOW, `1<<12` INT_HIGH, `1<<13` DEFAULT, `1<<17` ALTERNATE.
- **When usable:** read path, not lock-gated.
- **Errors:** `EC_RES_ERROR` (name not found / index out of range); v1 unknown subcmd → `EC_RES_INVALID_PARAM`; else `EC_RES_SUCCESS`.
- **Example:** v1 `subcmd=2, index=0` (`02 00`) → `val` + `"WP_L\0…"` + default-flags.

### `0x97` EC_CMD_CONSOLE_SNAPSHOT — latch the console buffer
- **Versions:** v0.
- **Request:** none. **Response:** none.
- **When usable / side effects:** latches a snapshot of the UART-TX ring buffer so a following `CONSOLE_READ` can return it. **Call this before `CONSOLE_READ`.** Header note: only when WP unlocked.
- **Errors:** always `EC_RES_SUCCESS`.

### `0x98` EC_CMD_CONSOLE_READ — read the snapshot
- **Versions:** v0+v1.
- **Request v0:** none (reads the whole snapshot). **Request v1** `struct ec_params_console_read_v1` (1 B): `subcmd` u8 (`0=NEXT` whole snapshot, `1=RECENT` only since the previous snapshot).
- **Response:** a NUL-terminated ASCII chunk of console output (empty string when drained). Read is incremental — call repeatedly to drain.
- **When usable:** run `CONSOLE_SNAPSHOT` first.
- **Errors:** v1 bad subcmd → `EC_RES_INVALID_PARAM`; else `EC_RES_SUCCESS`.

### `0x101` EC_CMD_USB_PD_CONTROL — get/set a PD port
- **Versions:** v0+v1.
- **Request** `struct ec_params_usb_pd_control` (4 B):
  ```c
  uint8_t port;   // <1 on gale (only 0)
  uint8_t role;   // 0=NO_CHANGE 1=TOGGLE_ON 2=TOGGLE_OFF 3=FORCE_SINK 4=FORCE_SOURCE
  uint8_t mux;    // 0=NO_CHANGE 1=NONE 2=USB 3=DP 4=DOCK 5=AUTO
  uint8_t swap;   // 0=NONE 1=DATA 2=POWER 3=VCONN
  ```
- **Response v0** `struct ec_response_usb_pd_control` (4 B): `enabled` u8, `role` u8, `polarity` u8, `state` u8 (numeric task-state).
- **Response v1** `struct …_v1` (35 B): `enabled` u8, `role` u8, `polarity` u8, `state[32]` (task-state name). **`enabled` bits:** `1<<0` COMMS, `1<<1` CONNECTED, `1<<2` PD_CAPABLE. **`role` bits:** `1<<0` POWER(0=SNK/1=SRC), `1<<1` DATA(0=UFP/1=DFP), `1<<2` VCONN, `1<<3` DR_POWER, `1<<4` DR_DATA, `1<<5` USB_COMM, `1<<6` EXT_POWERED.
- **Errors:** `EC_RES_INVALID_PARAM` if `port≥1`, `role≥5`, or `mux≥6`; else `EC_RES_SUCCESS`.
- **Example (v1 poll):** `00 00 00 00` → e.g. `enabled=0x01, role=0x00, polarity=0x00, state="SNK_DISCONNECTED\0…"`.

### `0x102` EC_CMD_USB_PD_PORTS — port count
- **Versions:** v0.
- **Request:** none. **Response** `struct ec_response_usb_pd_ports` (1 B): `num_ports` u8 = **1** on gale.
- **Errors:** always `EC_RES_SUCCESS`. **Example:** response `01`.

### `0x110` EC_CMD_USB_PD_FW_UPDATE — PD-device FW update (VDM passthrough)
- **Versions:** v0.
- **Request** `struct ec_params_usb_pd_fw_update` (8 B header + data):
  ```c
  uint16_t dev_id;  // target PD accessory
  uint8_t cmd;      // 0=REBOOT 1=FLASH_ERASE 2=FLASH_WRITE 3=ERASE_SIG
  uint8_t port;     // <1 on gale
  uint32_t size;    // data bytes following (FLASH_WRITE: multiple of 4)
  // + size bytes of data
  ```
  Each `cmd` maps to a Google-VID VDM. (The `EC_RES_UNAVAILABLE` battery guard is **not** compiled on gale — no battery config.)
- **Response:** none.
- **Errors:** `EC_RES_INVALID_PARAM` (`port≥1`, truncated payload, or `FLASH_WRITE` with `size==0`/not %4, or unknown cmd); `EC_RES_BUSY` if a VDM is already in flight; `EC_RES_TIMEOUT`/`EC_RES_ERROR` if the VDM engine times out/errors; `REBOOT`/`FLASH_ERASE` return `EC_RES_SUCCESS` immediately.
- **Example:** `dev_id=0x0001, cmd=1 (ERASE), port=0, size=0` → `01 00 | 01 | 00 | 00 00 00 00` → SUCCESS (VDM dispatched).

### `0x111` EC_CMD_USB_PD_RW_HASH_ENTRY — store a PD device's RW hash
- **Versions:** v0.
- **Request** `struct ec_params_usb_pd_rw_hash_entry` (27 B): `dev_id` u16 (non-zero), `dev_rw_hash[20]` (first 20 B of the device's RW SHA-256), `reserved` u8, `current_image` u32 (`0=UNKNOWN,1=RO,2=RW`). Stored into the EC's `rw_hash_table[]` (reuses the matching `dev_id` slot, else round-robin).
- **Response:** none.
- **Errors:** `EC_RES_INVALID_PARAM` if `dev_id==0`; else `EC_RES_SUCCESS`.

### `0x112` EC_CMD_USB_PD_DEV_INFO — get a PD device's info
- **Versions:** v0.
- **Request:** 1 byte — `port` u8 (`<1` on gale).
- **Response:** reuses `struct ec_params_usb_pd_rw_hash_entry` (27 B): `dev_id` u16 (0 if none discovered), `dev_rw_hash[20]` (only written if `dev_id≠0`), `reserved` u8, `current_image` u32.
- **Errors:** `EC_RES_INVALID_PARAM` if `port≥1`; else `EC_RES_SUCCESS`.
- **Example:** `port=0x00` → no peer: `dev_id=0x0000, current_image=0` → `00 00 | <20 B> | 00 | 00 00 00 00`.

### `0xb6` EC_CMD_ENTERING_MODE — notify vboot mode
- **Versions:** v0.
- **Request** `struct ec_params_entering_mode` (4 B): `vboot_mode` int — `0=NORMAL, 1=DEVELOPER, 2=RECOVERY`. Stored in global `g_vboot_mode`.
- **Response:** none. **Errors:** always `EC_RES_SUCCESS` (no validation).
- **Example:** `02 00 00 00` (recovery) → empty, SUCCESS.

### `0xd2` EC_CMD_REBOOT_EC — reboot with flags *(destructive)*
- **Versions:** v0.
- **Request** `struct ec_params_reboot_ec` (2 B):
  ```c
  uint8_t cmd;    // ec_reboot_cmd: 0=CANCEL 1=JUMP_RO 2=JUMP_RW 4=COLD 5=DISABLE_JUMP 6=HIBERNATE
  uint8_t flags;  // bit0 RESERVED0 (legacy); bit1 ON_AP_SHUTDOWN (defer until AP shutdown)
  ```
- **Response:** none. For the non-returning commands (`JUMP_*`/`COLD`/`HIBERNATE`) the EC **pre-sends** a success response before acting (gale has `HAS_TASK_HOSTCMD`).
- **Side effects — DESTRUCTIVE:** `CANCEL` clears a pending shutdown reboot; `ON_AP_SHUTDOWN` defers the command; `JUMP_RO/RW` switch image (no return); `COLD` → `system_reset(SYSTEM_RESET_HARD)` (hard reboot, no return); `DISABLE_JUMP` blocks further jumps; **`HIBERNATE` is not compiled on gale** (`CONFIG_HIBERNATE` undef) → falls through to `EC_ERROR_INVAL`.
- **Errors:** `EC_ERROR_INVAL`→`EC_RES_INVALID_PARAM` (unknown cmd / HIBERNATE on gale); `ACCESS_DENIED`→`EC_RES_ACCESS_DENIED`; else success/`EC_RES_ERROR`.
- **Example:** `cmd=0x04 (COLD), flags=0x02 (ON_AP_SHUTDOWN)` → returns `EC_RES_SUCCESS` now, cold reset at next AP shutdown.

### `0xd3` EC_CMD_GET_PANIC_INFO — saved panic block
- **Versions:** v0.
- **Request:** none.
- **Response:** the raw `struct panic_data` (variable, `response_size = struct_size`):
  ```c
  uint8_t arch;           // 1=CORTEX_M (gale)
  uint8_t struct_version; // 2
  uint8_t flags;          // 1<<0 FRAME_VALID, 1<<1 OLD_CONSOLE, 1<<2 OLD_HOSTCMD, 1<<3 OLD_HOSTEVENT
  uint8_t reserved;
  // union: cortex_panic_data { uint32 regs[12]; uint32 frame[8]; mmfs;bfar;mfar;shcsr;hfsr;dfsr; }
  uint32_t struct_size;
  uint32_t magic;         // 0x21636e50 ("Pnc!") when valid
  ```
- **Side effects:** reading sets `OLD_HOSTCMD` in the stored record (marks it consumed).
- **Errors:** always `EC_RES_SUCCESS`. If no valid panic (magic mismatch), the body is empty (0-byte response). (The register layout is the same one the console `panicinfo`/`crash` print.)

