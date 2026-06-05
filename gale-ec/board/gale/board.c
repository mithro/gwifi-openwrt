/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
/* Google Wifi (gale) board configuration */

#include "adc.h"
#include "adc_chip.h"
#include "common.h"
#include "console.h"
#include "ec_version.h"
#include "gpio.h"
#include "hooks.h"
#include "i2c.h"
#include "queue_policies.h"
#include "registers.h"
#include "spi.h"
#include "system.h"
#include "task.h"
#include "timer.h"
#include "usart-stm32f0.h"
#include "usart_tx_dma.h"
#include "usart_rx_dma.h"
#include "tcpm.h"
#include "usb_descriptor.h"
#include "usb_mux.h"
#include "usb_pd.h"
#include "usb_pd_config.h"
#include "usb_pd_tcpm.h"
#include "usb_spi.h"
#include "usb-stream.h"
#include "util.h"

/******************************************************************************
 * Build GPIO tables.
 */
#include "gpio_list.h"

/******************************************************************************
 * Forward the EC console over USB, and forward USART2 (AP console) as a USB
 * serial interface.
 */

#define USB_STREAM_RX_SIZE	16
#define USB_STREAM_TX_SIZE	16

/*
 * Define AP console forwarding queue and associated USART and USB
 * stream endpoints.
 */
static struct usart_config const ap_usart;
struct usb_stream_config const ap_usb;

static struct queue const ap_usart_to_usb = QUEUE_DIRECT(64, uint8_t,
	ap_usart.producer, ap_usb.consumer);
static struct queue const ap_usb_to_usart = QUEUE_DIRECT(64, uint8_t,
	ap_usb.producer, ap_usart.consumer);

static struct usart_config const ap_usart =
	USART_CONFIG(usart2_hw,
		usart_rx_interrupt,
		usart_tx_interrupt,
		115200,
		ap_usart_to_usb,
		ap_usb_to_usart);

USB_STREAM_CONFIG(ap_usb,
	USB_IFACE_AP_STREAM,
	USB_STR_AP_STREAM_NAME,
	USB_EP_AP_STREAM,
	USB_STREAM_RX_SIZE,
	USB_STREAM_TX_SIZE,
	ap_usb_to_usart,
	ap_usart_to_usb)

/******************************************************************************
 * Define the strings used in our USB descriptors.
 */
const void *const usb_strings[] = {
	[USB_STR_DESC]           = usb_string_desc,
	[USB_STR_VENDOR]         = USB_STRING_DESC("Google Inc."),
	[USB_STR_PRODUCT]        = USB_STRING_DESC("Gale debug"),
	[USB_STR_VERSION]        = USB_STRING_DESC(CROS_EC_VERSION32),
	[USB_STR_CONSOLE_NAME]   = USB_STRING_DESC("EC_PD"),
	[USB_STR_AP_STREAM_NAME] = USB_STRING_DESC("AP"),
};

BUILD_ASSERT(ARRAY_SIZE(usb_strings) == USB_STR_COUNT);

/******************************************************************************
 * AP power state, exposed by the "gale power" command.
 */
static int ap_is_on;

/* AP power rails, in power-on order (decoded from the firmware). */
static void set_ap_power_on(void)
{
	ccputs("power on ap\n");
	gpio_set_level(GPIO_SYS_PWR_EN, 1);
	gpio_set_level(GPIO_VDD_3P3_EN, 1);
	gpio_set_level(GPIO_VDD_3P3_2G_EN, 1);
	gpio_set_level(GPIO_VDD_1P8_EN, 1);
	gpio_set_level(GPIO_VDD_1P35_EN, 1);
	gpio_set_level(GPIO_VDD_1P1_CPU_EN, 1);
	ap_is_on = 1;
}
DECLARE_DEFERRED(set_ap_power_on);

static void set_ap_power_off(void)
{
	ccputs("power off ap\n");
	gpio_set_level(GPIO_MCU_INT_L, 0);
	gpio_set_level(GPIO_VDD_1P1_CPU_EN, 0);
	gpio_set_level(GPIO_VDD_1P35_EN, 0);
	gpio_set_level(GPIO_VDD_1P8_EN, 0);
	gpio_set_level(GPIO_VDD_3P3_2G_EN, 0);
	gpio_set_level(GPIO_VDD_3P3_EN, 0);
	gpio_set_level(GPIO_SYS_PWR_EN, 0);
	ap_is_on = 0;
}
DECLARE_DEFERRED(set_ap_power_off);

/* Shared with usb_pd_policy.c (pd_set_input_current_limit turns the AP on). */
void set_ap_power(int on)
{
	if (on)
		hook_call_deferred(&set_ap_power_on_data, 0);
	else
		hook_call_deferred(&set_ap_power_off_data, 0);
}

/******************************************************************************
 * Support SPI bridging over USB, this requires usb_spi_board_enable and
 * usb_spi_board_disable to be defined to enable and disable the SPI bridge.
 *
 * SPI master to the AP's W25Q64 boot flash.
 */

/* SPI devices */
const struct spi_device_t spi_devices[] = {
	{ CONFIG_SPI_FLASH_PORT, 0, GPIO_SPI_FLASH_NSS},
};
const unsigned int spi_devices_used = ARRAY_SIZE(spi_devices);

void usb_spi_board_enable(struct usb_spi_config const *config)
{
	/*
	 * Bring up just the rails needed to read the AP boot flash: keep the
	 * 3.3V (and SYS_PWR) up so the W25Q64 is powered, but hold the CPU
	 * core rails (1.35V / 1.8V) off so the AP stays in reset.
	 */
	gpio_set_level(GPIO_VDD_1P35_EN, 0);
	gpio_set_level(GPIO_VDD_1P8_EN, 0);
	if (!gpio_get_level(GPIO_SYS_PWR_EN)) {
		gpio_set_level(GPIO_SYS_PWR_EN, 1);
		gpio_set_level(GPIO_VDD_3P3_EN, 1);
		usleep(25);
	} else {
		while (!gpio_get_level(GPIO_VDD_3P3_EN)) {
			gpio_set_level(GPIO_SYS_PWR_EN, 1);
			gpio_set_level(GPIO_VDD_3P3_EN, 1);
			usleep(25);
		}
	}

	/* Configure SPI GPIOs */
	gpio_config_module(MODULE_SPI_FLASH, 1);
	gpio_set_flags(SPI_FLASH_DEVICE->gpio_cs, GPIO_OUT_HIGH);

	/* Set all four SPI pins to high speed */
	/* pins B12/B13/B14/B15 */
	STM32_GPIO_OSPEEDR(GPIO_B) |= 0xff000000;

	/* Enable clocks to SPI2 module */
	STM32_RCC_APB1ENR |= STM32_RCC_PB1_SPI2;

	/* Reset SPI2 */
	STM32_RCC_APB1RSTR |= STM32_RCC_PB1_SPI2;
	STM32_RCC_APB1RSTR &= ~STM32_RCC_PB1_SPI2;

	spi_enable(CONFIG_SPI_FLASH_PORT, 1);
}

void usb_spi_board_disable(struct usb_spi_config const *config)
{
	/* Disable clocks to SPI2 module */
	STM32_RCC_APB1ENR &= ~STM32_RCC_PB1_SPI2;

	/* Release SPI GPIOs */
	gpio_config_module(MODULE_SPI_FLASH, 0);
	gpio_set_flags(SPI_FLASH_DEVICE->gpio_cs, GPIO_INPUT);

	spi_enable(CONFIG_SPI_FLASH_PORT, 0);
}

USB_SPI_CONFIG(usb_spi, USB_IFACE_SPI, USB_EP_SPI);

/******************************************************************************
 * ADC channels (ordered by AIN id for STM32F0).
 */
const struct adc_t adc_channels[] = {
	/* USB PD CC lines sensing. Converted to mV (3300mV/4096). */
	[ADC_USB_CC1_PD] = {"CC1", 3300, 4096, 0, STM32_AIN(1)},
	[ADC_USB_CC2_PD] = {"CC2", 3300, 4096, 0, STM32_AIN(3)},
	/* VBUS voltage sensing, /2 divider. Converted to mV (6600mV/4096). */
	[ADC_VBUS] = {"VBUS", 6600, 4096, 0, STM32_AIN(8)},
	/* Input current sense. */
	[ADC_IN_CURRENT_SENSE] = {"CUR", 6600, 4096, 0, STM32_AIN(9)},
};
BUILD_ASSERT(ARRAY_SIZE(adc_channels) == ADC_CH_COUNT);

/******************************************************************************
 * I2C ports (slave to the AP).
 */
const struct i2c_port_t i2c_ports[] = {
	{"slave", I2C_PORT_SLAVE, 100, GPIO_SLAVE_I2C_SCL, GPIO_SLAVE_I2C_SDA},
};
const unsigned int i2c_ports_used = ARRAY_SIZE(i2c_ports);

/******************************************************************************
 * SuperSpeed mux: gale drives a discrete USB SS mux via GPIO
 * (USB_SS_MUX_EN_L enable, USB_CC_POLARITY orientation).
 */
static int board_ss_mux_set(int port_addr, mux_state_t mux_state)
{
	gpio_set_level(GPIO_USB_CC_POLARITY,
		       (mux_state & MUX_POLARITY_INVERTED) ? 0 : 1);
	gpio_set_level(GPIO_USB_SS_MUX_EN_L,
		       (mux_state & MUX_USB_ENABLED) ? 0 : 1);
	return EC_SUCCESS;
}

static int board_ss_mux_get(int port_addr, mux_state_t *mux_state)
{
	*mux_state = gpio_get_level(GPIO_USB_SS_MUX_EN_L) ? 0
							  : MUX_USB_ENABLED;
	return EC_SUCCESS;
}

static int board_ss_mux_init(int port_addr)
{
	gpio_set_level(GPIO_USB_SS_MUX_EN_L, 1);
	return EC_SUCCESS;
}

static const struct usb_mux_driver board_ss_mux_driver = {
	.init = board_ss_mux_init,
	.set  = board_ss_mux_set,
	.get  = board_ss_mux_get,
};

struct usb_mux usb_muxes[] = {
	{
		.port_addr = 0,
		.driver = &board_ss_mux_driver,
	},
};

/******************************************************************************
 * Send host event up to AP -- gale has no host-event path, no-op.
 */
void pd_send_host_event(int mask)
{
}

/******************************************************************************
 * Board level config / init.
 */
void board_config_pre_init(void)
{
	/* Enable SYSCFG clock. */
	STM32_RCC_APB2ENR |= 1 << 0;
	/*
	 * the DMA mapping is :
	 *  SPI2_RX -> DMA_CH6
	 *  SPI2_TX -> DMA_CH7
	 */
	STM32_SYSCFG_CFGR1 |= (1 << 24); /* SPI2_RX/TX DMA remap */
}

static void board_no_charger(void);
DECLARE_DEFERRED(board_no_charger);

/* Initialize board. */
static void board_init(void)
{
	/* USB to serial queues */
	queue_init(&ap_usart_to_usb);
	queue_init(&ap_usb_to_usart);

	/* UART init */
	usart_init(&ap_usart);

	/*
	 * Disable UART input when the write protect is enabled.  Otherwise,
	 * one second after boot, if no charger is detected on either CC line,
	 * kick the standalone USB device-mode bring-up.
	 */
	if (system_is_locked())
		ap_usb.state->rx_disabled = 1;
	else
		hook_call_deferred(&board_no_charger_data, SECOND);
}
DECLARE_HOOK(HOOK_INIT, board_init, HOOK_PRIO_DEFAULT);

/******************************************************************************
 * Console command: "gale" - Get and set gale controls.
 */
static int command_power(int argc, char **argv)
{
	int v;

	if (!system_is_locked() && argc > 1) {
		if (parse_bool(argv[1], &v)) {
			set_ap_power(v);
			ccputs("OK\n");
		}
	}
	ccprintf("%8s - %s\n", argv[0], ap_is_on ? "on" : "off");
	return EC_SUCCESS;
}

static int command_polarity(int argc, char **argv)
{
	if (!system_is_locked() && argc > 1) {
		gpio_set_level(GPIO_USB_CC_POLARITY,
			       strtoi(argv[1], NULL, 0) ? 1 : 0);
		ccputs("OK\n");
	}
	ccprintf("%8s - %d\n", argv[0], gpio_get_level(GPIO_USB_CC_POLARITY));
	return EC_SUCCESS;
}

/*
 * Map a CC line voltage (mV) to the host's advertised current.  In the
 * shipping firmware this read the internal pd[port].cc_status sink levels
 * (TYPEC_CC_VOLT_SNK_DEF/1_5/3_0); that state is private to the PD task's
 * translation unit, so reconstruct the same advertisement from the sampled
 * CC voltage using the Type-C sink thresholds.
 */
static void print_cc_current(int cc_mv)
{
	if (cc_mv >= 1230)
		ccprintf("(%dmA)", 3000);	/* TYPEC_CC_VOLT_SNK_3_0 */
	else if (cc_mv >= 660)
		ccprintf("(%dmA)", 1500);	/* TYPEC_CC_VOLT_SNK_1_5 */
	else if (cc_mv >= 200)
		ccprintf("(%dmA)", 900);	/* TYPEC_CC_VOLT_SNK_DEF */
}

static int command_cc(int argc, char **argv)
{
	int cc1_mv = pd_adc_read(0, 0);
	int cc2_mv = pd_adc_read(0, 1);

	ccprintf("%8s - %dmV", argv[0], cc1_mv);
	print_cc_current(cc1_mv);
	ccprintf(", %dmV", cc2_mv);
	print_cc_current(cc2_mv);
	ccputs("\n");
	return EC_SUCCESS;
}

static int command_vbus(int argc, char **argv)
{
	ccprintf("%8s - %dmv %dma\n", argv[0],
		 adc_read_channel(ADC_VBUS),
		 adc_read_channel(ADC_IN_CURRENT_SENSE));
	return EC_SUCCESS;
}

static int command_dev(int argc, char **argv)
{
	int v;

	if (!system_is_locked() && argc > 1) {
		if (parse_bool(argv[1], &v)) {
			gpio_set_flags(GPIO_ENTERING_DEV,
				       v ? GPIO_OUT_LOW : GPIO_INPUT);
			ccputs("OK\n");
		}
	}
	ccprintf("dev switch is %s\n",
		 gpio_get_level(GPIO_ENTERING_DEV) ? "OFF" : "ON");
	return EC_SUCCESS;
}

static int command_rec(int argc, char **argv)
{
	int v;

	if (!system_is_locked() && argc > 1) {
		if (parse_bool(argv[1], &v)) {
			gpio_set_flags(GPIO_ENTERING_REC,
				       v ? GPIO_OUT_LOW : GPIO_INPUT);
			ccputs("OK\n");
		}
	}
	ccprintf("rec switch is %s\n",
		 gpio_get_level(GPIO_ENTERING_REC) ? "OFF" : "ON");
	return EC_SUCCESS;
}

static const struct {
	const char *name;
	int (*handler)(int argc, char **argv);
} gale_subcommands[] = {
	{"power",    command_power},
	{"polarity", command_polarity},
	{"cc",       command_cc},
	{"vbus",     command_vbus},
	{"dev",      command_dev},
	{"rec",      command_rec},
};

static int command_gale(int argc, char **argv)
{
	int i;

	if (argc < 2) {
		/* No sub-command: dump the status of every control. */
		for (i = 0; i < ARRAY_SIZE(gale_subcommands); i++)
			gale_subcommands[i].handler(1,
				(char **)&gale_subcommands[i].name);
		return EC_SUCCESS;
	}

	for (i = 0; i < ARRAY_SIZE(gale_subcommands); i++) {
		if (!strncasecmp(argv[1], gale_subcommands[i].name,
				 strlen(gale_subcommands[i].name)))
			return gale_subcommands[i].handler(argc - 1, argv + 1);
	}

	return EC_ERROR_PARAM1;
}
DECLARE_CONSOLE_COMMAND(gale, command_gale,
	"[power [on|off]|polarity [0|1]|dev [on|off]|rec [on|off]|cc|vbus",
	"Get and set gale controls",
	NULL);

/******************************************************************************
 * One second after boot, if neither CC line is presenting an Rp (i.e. no
 * USB host / charger is attached), select the dual-role power policy so the
 * unit can be reached over the debug USB connector while standalone.
 */
static void board_no_charger(void)
{
	int cc1, cc2;

	tcpm_get_cc(0, &cc1, &cc2);

	/*
	 * A CC line presenting an Rp (sink default / 1.5A / 3.0A advertisement)
	 * means a host/charger is attached; in that case leave the policy alone.
	 */
	if (cc1 >= TYPEC_CC_VOLT_SNK_DEF && cc1 <= TYPEC_CC_VOLT_SNK_3_0)
		return;
	if (cc2 >= TYPEC_CC_VOLT_SNK_DEF && cc2 <= TYPEC_CC_VOLT_SNK_3_0)
		return;

	/*
	 * No charger: when unlocked force a sink role (DRP off, sink) so the
	 * debug connector can drive the port; when locked just stop toggling.
	 */
	pd_set_dual_role(system_is_locked() ? PD_DRP_TOGGLE_OFF
					    : PD_DRP_FORCE_SINK);
}
