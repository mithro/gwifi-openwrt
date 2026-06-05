/* -*- mode:c -*-
 *
 * Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Reconstructed from the gale_v1.1.5337-0115719 firmware dump.
 * Ports/pins/flags decoded from the on-flash gpio_list[] and
 * gpio_alt_funcs[] tables; signal order matches the live `gpioget`.
 */

/*
 * USB Power Delivery CC sensing (analog inputs to the discrete PD PHY).
 *  USB_CC1_PD = PA1 (AIN1), USB_CC2_PD = PA3 (AIN3).
 */
GPIO(USB_CC1_PD,       PIN(A, 1),  GPIO_ANALOG)
GPIO(USB_CC2_PD,       PIN(A, 3),  GPIO_ANALOG)

/* CC transmit data lines (driven by SPI1 / TIM for BMC encoding) */
GPIO(USB_CC1_TX_DATA,  PIN(B, 4),  GPIO_INPUT)
GPIO(USB_CC2_TX_DATA,  PIN(A, 6),  GPIO_INPUT)

/* Type-C / SuperSpeed mux control */
GPIO(USB_CC_POLARITY,  PIN(B, 2),  GPIO_OUT_LOW)
GPIO(USB_SS_MUX_EN_L,  PIN(C, 15), GPIO_OUT_LOW)

/* VBUS and input current sensing (analog) */
GPIO(USB_VBUS_DETECT,  PIN(B, 0),  GPIO_ANALOG)
GPIO(IN_CURRENT_SENSE, PIN(B, 1),  GPIO_ANALOG)

/* Write protect (active low input) */
GPIO(WP_L,             PIN(B, 11), GPIO_INPUT)

/* AP power sequencing rails (driven by the `gale power` command) */
GPIO(VDD_3P3_EN,       PIN(A, 0),  GPIO_OUT_LOW)
GPIO(VDD_3P3_2G_EN,    PIN(A, 2),  GPIO_OUT_LOW)
GPIO(VDD_1P35_EN,      PIN(A, 5),  GPIO_OUT_LOW)
GPIO(VDD_1P1_CPU_EN,   PIN(F, 0),  GPIO_OUT_LOW)
GPIO(VDD_1P8_EN,       PIN(A, 8),  GPIO_OUT_LOW)
GPIO(SYS_PWR_EN,       PIN(B, 10), GPIO_OUT_HIGH)

/* Misc board control / status */
GPIO(ERROR_LED,        PIN(B, 5),  GPIO_OUT_LOW)
GPIO(ENTERING_REC,     PIN(C, 13), GPIO_INPUT)
GPIO(MCU_INT_L,        PIN(C, 14), GPIO_OUT_HIGH)
GPIO(ENTERING_DEV,     PIN(F, 1),  GPIO_INPUT)

/* SPI master to the AP boot flash (W25Q64), bridged via raiden usb_spi */
GPIO(SPI_FLASH_NSS,    PIN(B, 12), GPIO_INPUT)
GPIO(SPI_FLASH_SCK,    PIN(B, 13), GPIO_INPUT)
GPIO(SPI_FLASH_MISO,   PIN(B, 14), GPIO_INPUT)
GPIO(SPI_FLASH_MOSI,   PIN(B, 15), GPIO_INPUT)

/* USB D-/D+ (analog: peripheral controls the pads) */
GPIO(USB_DM,           PIN(A, 11), GPIO_ANALOG)
GPIO(USB_DP,           PIN(A, 12), GPIO_ANALOG)

/* I2C slave to the AP */
GPIO(SLAVE_I2C_SCL,    PIN(B, 6),  GPIO_INPUT)
GPIO(SLAVE_I2C_SDA,    PIN(B, 7),  GPIO_INPUT)

/* Signals expected by common code but not wired on gale */
UNIMPLEMENTED(ENTERING_RW)
UNIMPLEMENTED(PD_DISABLE_DEBUG)

/* Alternate functions (decoded from gpio_alt_funcs[]) */
ALTERNATE(PIN_MASK(B, 0x0008), 0, MODULE_USB_PD, 0)   /* SPI1_SCK:  PB3  (CC TX clock)   */
ALTERNATE(PIN_MASK(B, 0x0100), 2, MODULE_USB_PD, 0)   /* TIM16_CH1: PB8  (CC TX timer)   */
ALTERNATE(PIN_MASK(A, 0x0600), 1, MODULE_UART, 0)     /* USART1:    PA9/PA10 EC console  */
ALTERNATE(PIN_MASK(B, 0x00C0), 1, MODULE_I2C, 0)      /* I2C1:      PB6/PB7 (AP slave)   */
ALTERNATE(PIN_MASK(B, 0xE000), 0, MODULE_SPI_FLASH, GPIO_PULL_DOWN) /* SPI2: PB13/14/15 flash */
ALTERNATE(PIN_MASK(A, 0x1800), 6, MODULE_USB, 0)      /* USB:       PA11/PA12 DM/DP      */
ALTERNATE(PIN_MASK(A, 0xC000), 1, MODULE_USART, 0)    /* USART2:    PA14/PA15 AP stream  */
