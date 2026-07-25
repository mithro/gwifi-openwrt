# Reconstruction divergence: gale was missing the AP host-command transport

## The divergence (found by comparing the captured device firmware to the recreation)

The **captured device firmware** (`gale-ec-gale_v1.1.5337-...`, sha `602a4614`) talks to the
AP (IPQ4019) over the I2C slave for **host commands**: at runtime it programs

```
STM32_I2C1_OAR1 = 0x803C   (OA1EN set, own slave address 0x3C)
STM32_I2C1_CR1  = 0x00BD   (PE + slave ADDR/RX/STOP/NACK/ERR interrupts)
```

i.e. `host_command_process` and all the `hc_*` handlers are **live** on the device — the AP
sends `EC_CMD_*` packets and the EC services them.

The **recreation** (`ec/` @ `firmware-gale-8281.B`) had `CONFIG_I2C_SLAVE` but **not**
`CONFIG_HOSTCMD_I2C_SLAVE_ADDR`, so the host-command transport was compiled out:
`host_packet_receive` / `host_command_received` / `i2c_event_handler` / `i2c_process_command`
were all garbage-collected from the binary, and `STM32_I2C1_OAR1` read `0x0000` (slave never
enabled). The `host_command_process`/`hc_*` code was linked but **unreachable** — a missing
feature, exactly like the earlier `CONFIG_CASE_CLOSED_DEBUG`/`usb_init` gap (see
`gale-ccd-enable.md`), NOT genuine dead code.

## The fix (faithful restoration, `board/gale/board.h`)

```c
/* Host-command transport: the AP talks to the EC over the I2C slave. */
#define CONFIG_HOSTCMD_I2C_SLAVE_ADDR 0x3C
```

The value 0x3C is read straight off the device firmware (`OAR1 = 0x8000 | ADDR`). Rebuild
`build/gale/ec.bin` with the 2016q3 toolchain. After the fix the recreation programs
`I2C1 OAR1 = 0x803C`, `CR1 = 0x00BD` — **byte-identical to the captured device** — and
`host_packet_receive`/`host_command_process` reappear in the binary. `battery.py` still
8 PASS / 2 XFAIL / 0 FAIL (equivalence preserved and improved).

## Emulation (`peripherals/GaleI2c.cs`)

`GaleI2c` replaces the stock STM32F7_I2C at I2C1 and adds `HostCmd("<hex>")`, which emulates
the AP master writing a host-command packet (then reading the response): it scripts the
STM32F0 slave-receive interrupt sequence (ADDR-write → RXNE per byte → ADDR-read → TXIS read
turnaround) and raises `IRQ -> nvic@23`, driving the *real* `i2c_event_handler` →
`i2c_process_command` → `host_packet_receive` → `host_command_process` → `hc_*`. Verified with
`EC_CMD_HELLO` (`da 03 f8 01 00 00 00 04 00000000`): the firmware returns `EC_RES_SUCCESS` with
a valid protocol-v3 `ec_host_response` (struct_version 3, 12-byte response). This makes the
host-command branches — live on the device — coverable in emulation on both firmwares.
