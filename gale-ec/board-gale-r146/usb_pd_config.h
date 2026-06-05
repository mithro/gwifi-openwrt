/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/* USB Power delivery board configuration */

#ifndef __CROS_EC_USB_PD_CONFIG_H
#define __CROS_EC_USB_PD_CONFIG_H

/*
 * Reconstructed from the gale firmware. The CC TX path is the discrete
 * STM32F072 PHY: SPI1 (SCK PB3) shifts the BMC-encoded data out onto the
 * TX_DATA pins (CC1 = PB4, CC2 = PA6), clocked by TIM16_CH1 (PB8). RX uses
 * the internal comparators triggering TIM1 input capture, as on twinkie.
 */

/* Timer selection for baseband PD communication */
#define TIM_CLOCK_PD_TX_C0 16
#define TIM_CLOCK_PD_RX_C0 1

#define TIM_CLOCK_PD_TX(p) TIM_CLOCK_PD_TX_C0
#define TIM_CLOCK_PD_RX(p) TIM_CLOCK_PD_RX_C0

/* TX and RX timer register */
#define TIM_REG_TX_C0 (STM32_TIM_BASE(TIM_CLOCK_PD_TX_C0))
#define TIM_REG_RX_C0 (STM32_TIM_BASE(TIM_CLOCK_PD_RX_C0))
#define TIM_REG_TX(p) TIM_REG_TX_C0
#define TIM_REG_RX(p) TIM_REG_RX_C0

/* Timer channel */
#define TIM_RX_CCR_C0 1
#define TIM_TX_CCR_C0 1

/* RX timer capture/compare register */
#define TIM_CCR_C0 (&STM32_TIM_CCRx(TIM_CLOCK_PD_RX_C0, TIM_RX_CCR_C0))
#define TIM_RX_CCR_REG(p) TIM_CCR_C0

/* use the hardware accelerator for CRC */
#define CONFIG_HW_CRC

/* TX is using SPI1 on PA6/PB4 */
#define SPI_REGS(p) STM32_SPI1_REGS
#define DMAC_SPI_TX(p) STM32_DMAC_CH3

static inline void spi_enable_clock(int port)
{
	STM32_RCC_APB2ENR |= STM32_RCC_PB2_SPI1;
}

/* RX is using COMP1 or COMP2 triggering TIM1 CH1 */
#define CMP1OUTSEL STM32_COMP_CMP1OUTSEL_TIM1_IC1
#define CMP2OUTSEL STM32_COMP_CMP2OUTSEL_TIM1_IC1

#define DMAC_TIM_RX(p) STM32_DMAC_CH2
#define TIM_RX_CCR_IDX(p) TIM_RX_CCR_C0
#define TIM_TX_CCR_IDX(p) TIM_TX_CCR_C0
#define TIM_CCR_CS  1
#define EXTI_COMP_MASK(p) ((1 << 21) | (1 << 22))
#define IRQ_COMP STM32_IRQ_COMP
/* triggers packet detection on comparator falling edge */
#define EXTI_XTSR STM32_EXTI_FTSR

/* the pins used for communication need to be hi-speed */
static inline void pd_set_pins_speed(int port)
{
	/* 40 MHz pin speed on SPI TX PB4 and SPI SCK PB3 */
	STM32_GPIO_OSPEEDR(GPIO_B) |= 0x000003C0;
	/* 40 MHz pin speed on TIM16_CH1 (PB8) */
	STM32_GPIO_OSPEEDR(GPIO_B) |= 0x00030000;
}

/* Reset SPI peripheral used for TX */
static inline void pd_tx_spi_reset(int port)
{
	/* Reset SPI1 */
	STM32_RCC_APB2RSTR |= (1 << 12);
	STM32_RCC_APB2RSTR &= ~(1 << 12);
}

/*
 * Drive the active CC line from the TX block.  Unlike twinkie (which drives
 * both CC lines), gale routes the SPI1 TX output onto a single CC line
 * selected by the detected plug polarity: CC2 (PA6) when inverted, otherwise
 * CC1 (PB4).
 */
static inline void pd_tx_enable(int port, int polarity)
{
	if (polarity) {
		/* TX_DATA on PA6 (CC2) is now connected to SPI1 */
		gpio_set_alternate_function(GPIO_A, 0x0040, 0);
		/*
		 * Force the active CC line's analog sense pin PA3 (USB_CC2_PD)
		 * to GPIO output low for the duration of the transmit.
		 */
		STM32_GPIO_MODER(GPIO_A) =
			(STM32_GPIO_MODER(GPIO_A) & ~(3 << (2*3)))
					 |  (1 << (2*3)); /* PA3 output */
		gpio_set_level(GPIO_USB_CC2_PD, 0);
	} else {
		/* TX_DATA on PB4 (CC1) is now connected to SPI1 */
		gpio_set_alternate_function(GPIO_B, 0x0010, 0);
		/*
		 * Force the active CC line's analog sense pin PA1 (USB_CC1_PD)
		 * to GPIO output low for the duration of the transmit.
		 */
		STM32_GPIO_MODER(GPIO_A) =
			(STM32_GPIO_MODER(GPIO_A) & ~(3 << (2*1)))
					 |  (1 << (2*1)); /* PA1 output */
		gpio_set_level(GPIO_USB_CC1_PD, 0);
	}
}

/* Put the TX driver in Hi-Z state */
static inline void pd_tx_disable(int port, int polarity)
{
	/* TX_DATA on PB4 is an output low GPIO to disable the FET */
	STM32_GPIO_MODER(GPIO_B) = (STM32_GPIO_MODER(GPIO_B) & ~(3 << (2*4)))
							 |  (1 << (2*4));
	/* TX_DATA on PA6 is an output low GPIO to disable the FET */
	STM32_GPIO_MODER(GPIO_A) = (STM32_GPIO_MODER(GPIO_A) & ~(3 << (2*6)))
							 |  (1 << (2*6));
}

/* we know the plug polarity, do the right configuration */
static inline void pd_select_polarity(int port, int polarity)
{
	/*
	 * Set the comparator inverting input to 1/2 VREFINT (~0.6V) and enable
	 * the right comparator (CC1 -> COMP1, CC2 -> COMP2).  This matches the
	 * original gale firmware (COMP_CSR INSEL = VREF1/2, not INM4).
	 */
	STM32_COMP_CSR = (STM32_COMP_CSR
		& ~(STM32_COMP_CMP1INSEL_MASK | STM32_COMP_CMP2INSEL_MASK
		  | STM32_COMP_CMP1EN | STM32_COMP_CMP2EN))
		| STM32_COMP_CMP1INSEL_VREF12 | STM32_COMP_CMP2INSEL_VREF12
		| (polarity ? STM32_COMP_CMP2EN : STM32_COMP_CMP1EN);
}

/* Initialize pins used for TX and put them in Hi-Z */
static inline void pd_tx_init(void)
{
	gpio_config_module(MODULE_USB_PD, 1);
}

static inline void pd_set_host_mode(int port, int enable)
{
	/* Gale is a sink; Rp/Rd are set in hardware. */
}

static inline void pd_config_init(int port, uint8_t power_role)
{
	/* Initialize TX pins and put them in Hi-Z */
	pd_tx_init();
}

static inline int pd_adc_read(int port, int cc)
{
	if (cc == 0)
		return adc_read_channel(ADC_USB_CC1_PD);
	else
		return adc_read_channel(ADC_USB_CC2_PD);
}

#endif /* __CROS_EC_USB_PD_CONFIG_H */
