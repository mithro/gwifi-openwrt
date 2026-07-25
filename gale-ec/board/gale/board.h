/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/* Google Wifi (gale) board configuration */

#ifndef __CROS_EC_BOARD_H
#define __CROS_EC_BOARD_H

/* 48 MHz SYSCLK clock frequency */
#define CPU_CLOCK 48000000

/* the UART console is on USART1 (PA9/PA10) */
#undef  CONFIG_UART_CONSOLE
#define CONFIG_UART_CONSOLE 1

/* Optional features */
#define CONFIG_ADC
#undef  CONFIG_ADC_WATCHDOG
#define CONFIG_BOARD_PRE_INIT
#define CONFIG_HW_CRC
#define CONFIG_STM_HWTIMER32

/* This is not actually an EC, so disable some features. */
#undef  CONFIG_WATCHDOG_HELP
#undef  CONFIG_LID_SWITCH
/* The factory gale image was built without task profiling (its `taskinfo` prints
 * only the task table, no IRQ/exception/switch stats). Match it. Found via the
 * Renode trace-equivalence battery (renode/battery.py). */
#undef  CONFIG_TASK_PROFILING

/* USB Configuration */
#define CONFIG_USB
#define CONFIG_USB_PID 0x500f
#define CONFIG_USB_CONSOLE

/* Prevent the USB driver from initializing at boot */
#define CONFIG_USB_INHIBIT_INIT

/*
 * Case Closed Debugging — the original gale firmware compiles
 * common/case_closed_debug.c (proven: the original dump retains usb_init —
 * USB_CNTR/ISTR x4, USB_BTABLE x2 — which the CCD-less reconstruction GC'd). CCD
 * powers the USB device controller (EC/AP consoles + the raiden SPI bridge, which
 * IS case_closed_debug.c's ccd_usb_spi) on Type-C debug-accessory detection.
 *
 * gale is sink-only with no battery and no charger IC (its 4-task list has no
 * charger task), so CONFIG_CHARGE_MANAGER is NOT enabled — that would change the
 * validated input-current/AP-power flow and pull in a charge subsystem absent from
 * this design. The two charge_manager-era calls the CCD SRC_ACCESSORY path makes
 * (typec_set_input_current_limit, charge_manager_update_dualrole) are satisfied by
 * sink-only board stubs in usb_pd_policy.c, keeping all CCD changes confined to
 * board/gale and leaving common/ and gale's validated behavior untouched.
 */
#define CONFIG_CASE_CLOSED_DEBUG

/* USB interface indexes (use define rather than enum to expand them) */
#define USB_IFACE_CONSOLE   0
#define USB_IFACE_AP_STREAM 1
#define USB_IFACE_UNUSED    2 /* reserved */
#define USB_IFACE_SPI       3
#define USB_IFACE_COUNT     4

/* USB endpoint indexes (use define rather than enum to expand them) */
#define USB_EP_CONTROL   0
#define USB_EP_CONSOLE   1
#define USB_EP_AP_STREAM 2
#define USB_EP_SPI       3
#define USB_EP_COUNT     4

/* Enable USART1 (EC console) and USART2 (AP) streams over USB */
#define CONFIG_STREAM_USART
#define CONFIG_STREAM_USART2
#define CONFIG_STREAM_USB

/* Enable control of SPI over USB (raiden bridge to the AP boot flash) */
#define CONFIG_SPI_MASTER
#define CONFIG_SPI_FLASH_PORT    0  /* First SPI master port */
#define CONFIG_USB_SPI

/* USB Power Delivery (single sink-capable port C0) */
#define CONFIG_USB_POWER_DELIVERY
#define CONFIG_USB_PD_ALT_MODE
#define CONFIG_USB_PD_CUSTOM_VDM
#define CONFIG_USB_PD_DUAL_ROLE
#define CONFIG_USB_PD_INTERNAL_COMP
#define CONFIG_USB_PD_PORT_COUNT 1
#define CONFIG_USB_PD_TCPC
#define CONFIG_USB_PD_TCPM_STUB
#define CONFIG_USBC_SS_MUX

/* I2C slave to the AP */
#define CONFIG_I2C
#define CONFIG_I2C_SLAVE
#define I2C_PORT_SLAVE  0
#define I2C_PORT_EC I2C_PORT_SLAVE
/*
 * Host-command transport: the AP talks to the EC over the I2C slave. The original device
 * firmware (v1.1.5337) enables this — STM32_I2C_OAR1 = 0x803C (slave addr 0x3C) — so the
 * host_command_process / hc_* handlers are LIVE on the device. The reconstruction had dropped
 * it (OAR1=0, transport GC'd); restore it to match the device firmware (faithful equivalence).
 */
#define CONFIG_HOSTCMD_I2C_SLAVE_ADDR 0x3C

/* Console command support seen on the live EC */
#define CONFIG_CMD_SPI_XFER

/*
 * Console-command set: match the factory gale image (v1.1.5337) EXACTLY. The shipping firmware
 * was built from this same branch (firmware-gale-8281.B), so its __cmds table is reproduced by
 * these board overrides (verified against the captured dump via renode/compare_cmds.py — 27 cmds):
 *   + ENABLE vboot hash: the device runs verified boot and exposes the `hash` command
 *     (common/vboot_hash.c; CONFIG_VBOOT_HASH also pulls in sha256.o for the RW-hash compute).
 *   - DISABLE the shmem / timerinfo debug commands (default-on in include/config.h; gale ships
 *     without them).
 *   - DISABLE the hibernate capability (gale is an always-on AP companion with no battery; the
 *     `hibernate` command is gated solely by CONFIG_HIBERNATE and is absent on the device).
 *   - DISABLE host-event reporting: gale keeps the HOSTCMD task (AP<->EC host commands are live)
 *     but ships no host-event mechanism, so the `hostevent` command is absent. CONFIG_HOSTCMD_EVENTS
 *     is auto-enabled by HAS_TASK_HOSTCMD in include/config.h; override it back off here.
 */
#define CONFIG_VBOOT_HASH
#undef  CONFIG_CMD_SHMEM
#undef  CONFIG_CMD_TIMERINFO
#undef  CONFIG_HIBERNATE
#undef  CONFIG_HOSTCMD_EVENTS

/*
 * Use PSTATE embedded in the RO image (not in its own erase block), so the
 * RO region spans the full first half of flash (matches the shipping image).
 */
#undef  CONFIG_FLASH_PSTATE_BANK
#undef  CONFIG_FW_PSTATE_SIZE
#define CONFIG_FW_PSTATE_SIZE 0

/*
 * Allow dangerous commands.
 * TODO: Remove this config before production.
 */
#define CONFIG_SYSTEM_UNLOCKED

#ifndef __ASSEMBLER__

/* Timer selection */
#define TIM_CLOCK32 2

#include "gpio_signal.h"

/* ADC signal (must be ordered by AIN id for STM32F0) */
enum adc_channel {
	ADC_USB_CC1_PD = 0,	/* PA1 / AIN1 */
	ADC_USB_CC2_PD,		/* PA3 / AIN3 */
	ADC_VBUS,		/* PB0 / AIN8 */
	ADC_IN_CURRENT_SENSE,	/* PB1 / AIN9 */
	/* Number of ADC channels */
	ADC_CH_COUNT
};

/* USB string indexes */
enum usb_strings {
	USB_STR_DESC = 0,
	USB_STR_VENDOR,
	USB_STR_PRODUCT,
	USB_STR_VERSION,
	USB_STR_CONSOLE_NAME,
	USB_STR_AP_STREAM_NAME,

	USB_STR_COUNT
};

/* 1.5A Rp */
#define PD_SRC_VNC            PD_SRC_1_5_VNC_MV
#define PD_SRC_RD_THRESHOLD   PD_SRC_1_5_RD_THRESH_MV

/* start as a sink in case we have no other power supply/battery */
#define PD_DEFAULT_STATE PD_STATE_SNK_DISCONNECTED

/* delay for the voltage transition on the power supply */
#define PD_POWER_SUPPLY_TURN_ON_DELAY  30000 /* us */
#define PD_POWER_SUPPLY_TURN_OFF_DELAY 50000 /* us */

/* Define typical operating power and max power */
#define PD_OPERATING_POWER_MW 5000
#define PD_MAX_POWER_MW       15000
#define PD_MAX_CURRENT_MA     3000
#define PD_MAX_VOLTAGE_MV     5000

#endif /* !__ASSEMBLER__ */
#endif /* __CROS_EC_BOARD_H */
