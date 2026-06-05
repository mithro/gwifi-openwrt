/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/* Google Wifi (gale) board configuration */

#ifndef __CROS_EC_BOARD_H
#define __CROS_EC_BOARD_H

/*
 * SPIKE-A forward-port: enable link-time optimization. The RW image built with
 * GCC 14 (newer/larger than the original 2016q3 GCC 5.4) overflows the 64 KiB
 * RW half by ~3.5 KiB without LTO. The comparable STM32F072 boards (servo_micro,
 * servo_v4) enable CONFIG_LTO for exactly this reason; gale almost certainly
 * shipped with it too.
 */
#define CONFIG_LTO

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
/*
 * SPIKE-A forward-port: CONFIG_STM_HWTIMER32 was removed from the EC tree
 * (32-bit hwtimer is now unconditional on stm32). Dropping the define.
 */

/* This is not actually an EC, so disable some features. */
#undef  CONFIG_WATCHDOG_HELP
#undef  CONFIG_LID_SWITCH

/* USB Configuration */
#define CONFIG_USB
#define CONFIG_USB_PID 0x500f
#define CONFIG_USB_CONSOLE

/* Prevent the USB driver from initializing at boot */
#define CONFIG_USB_INHIBIT_INIT

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
#define USB_EP_UNUSED    3 /* reserved */
#define USB_EP_SPI       4
#define USB_EP_COUNT     5

/* Enable USART1 (EC console) and USART2 (AP) streams over USB */
#define CONFIG_STREAM_USART
#define CONFIG_STREAM_USART2
#define CONFIG_STREAM_USB

/* Enable control of SPI over USB (raiden bridge to the AP boot flash) */
/* SPIKE-A forward-port: CONFIG_SPI_MASTER renamed to CONFIG_SPI_CONTROLLER. */
#define CONFIG_SPI_CONTROLLER
#define CONFIG_SPI_FLASH_PORT    0  /* First SPI master port */
#define CONFIG_USB_SPI

/* USB Power Delivery (single sink-capable port C0) */
#define CONFIG_USB_POWER_DELIVERY
/*
 * SPIKE-A forward-port: the EC tree now requires an explicit TCPM state-machine
 * version. Gale drives the STM32 built-in TCPC (TCPM_STUB), which is the legacy
 * TCPMv1 stack (common/usb_pd_protocol.c). servo_v4 uses the identical combo.
 */
#define CONFIG_USB_PD_TCPMV1
#define CONFIG_USB_PD_ALT_MODE
/*
 * SPIKE-A forward-port: the default PDO tables (pd_src_pdo/pd_snk_pdo) moved to
 * common/usb_pd_pdo.c, guarded by !CONFIG_USB_PD_CUSTOM_PDO. Gale supplies its
 * own sink-only PDO tables in usb_pd_policy.c, so declare them custom to avoid a
 * multiple-definition link error (and drop the unused default tables).
 */
#define CONFIG_USB_PD_CUSTOM_PDO
#define CONFIG_USB_PD_CUSTOM_VDM
#define CONFIG_USB_PD_DUAL_ROLE
#define CONFIG_USB_PD_INTERNAL_COMP
/* SPIKE-A forward-port: CONFIG_USB_PD_PORT_COUNT renamed to ..._PORT_MAX_COUNT. */
#define CONFIG_USB_PD_PORT_MAX_COUNT 1
#define CONFIG_USB_PD_TCPC
#define CONFIG_USB_PD_TCPM_STUB
#define CONFIG_USBC_SS_MUX

/* I2C peripheral to the AP */
#define CONFIG_I2C
/* SPIKE-A forward-port: CONFIG_I2C_SLAVE renamed to CONFIG_I2C_PERIPHERAL. */
#define CONFIG_I2C_PERIPHERAL
#define I2C_PORT_SLAVE  0
#define I2C_PORT_EC I2C_PORT_SLAVE

/* Console command support seen on the live EC */
#define CONFIG_CMD_SPI_XFER

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
	/*
	 * SPIKE-A forward-port: the refactored USB-SPI driver
	 * (chip/stm32/usb_spi.c) now references a board-provided string index
	 * USB_STR_SPI_NAME for the SPI interface's iInterface descriptor.
	 */
	USB_STR_SPI_NAME,

	USB_STR_COUNT
};

/* 1.5A Rp */
#define PD_SRC_VNC            PD_SRC_1_5_VNC_MV
#define PD_SRC_RD_THRESHOLD   PD_SRC_1_5_RD_THRESH_MV

/*
 * SPIKE-A forward-port: PD_DEFAULT_STATE became a function-like macro
 * PD_DEFAULT_STATE(port) in include/usb_pd.h. With CONFIG_USB_PD_DUAL_ROLE set
 * (gale has it), the header default already resolves to PD_STATE_SNK_DISCONNECTED
 * (start as a sink), matching the original board intent, so we drop the override.
 */

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
