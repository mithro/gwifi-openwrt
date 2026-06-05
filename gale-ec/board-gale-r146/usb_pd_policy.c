/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include "adc.h"
#include "common.h"
#include "console.h"
#include "gpio.h"
#include "hooks.h"
#include "registers.h"
#include "system.h"
#include "task.h"
#include "timer.h"
#include "util.h"
#include "usb_pd.h"

#define CPRINTF(format, args...) cprintf(CC_USBPD, format, ## args)
#define CPRINTS(format, args...) cprints(CC_USBPD, format, ## args)

/* Turn the AP power rails on; implemented in board.c. */
void set_ap_power(int on);

/*
 * SPIKE-A forward-port: the PDO tables (pd_src_pdo/pd_snk_pdo + counts) moved to
 * board/gale/usb_pd_pdo.c so they can be shared with the genvif host tool when
 * CONFIG_USB_PD_CUSTOM_PDO is set (see util/build.mk and board/servo_v4).
 */

int pd_is_valid_input_voltage(int mv)
{
	/* Gale only ever runs off 5V. */
	return mv == 5000;
}

void pd_transition_voltage(int idx)
{
	/* No-operation: we are always 5V */
}

int pd_set_power_supply_ready(int port)
{
	/* Gale is a sink only; it does not source VBUS. */
	return EC_SUCCESS;
}

void pd_power_supply_reset(int port)
{
	/* Gale is a sink only; nothing to discharge. */
}

void pd_set_input_current_limit(int port, uint32_t max_ma,
				uint32_t supply_voltage)
{
	/*
	 * When the charger offers 5V at (more than) 2.5A, we have enough
	 * headroom to run the AP, so bring its rails up.
	 */
	if (supply_voltage == 5000 && max_ma > 2499)
		set_ap_power(1);
}

int pd_snk_is_vbus_provided(int port)
{
	/* VBUS is always assumed present on this design. */
	return 1;
}

int pd_board_checks(void)
{
	return EC_SUCCESS;
}

int pd_check_power_swap(int port)
{
	/* Gale never sources, so never accept a power role swap. */
	return 0;
}

/*
 * SPIKE-A forward-port: the PD policy callbacks are now declared
 * __override_proto with enum role types in include/usb_pd.h. Match those
 * signatures (int -> enum pd_data_role / enum pd_power_role) and mark
 * __override, as servo_v4 does.
 */
__override int pd_check_data_swap(int port, enum pd_data_role data_role)
{
	/* Always allow data swap: we can be DFP or UFP for USB */
	return 1;
}

__override void pd_execute_data_swap(int port, enum pd_data_role data_role)
{
}

__override void pd_check_pr_role(int port, enum pd_power_role pr_role, int flags)
{
}

__override void pd_check_dr_role(int port, enum pd_data_role dr_role, int flags)
{
	/* If the partner is dual-role data and we are UFP, request a swap. */
	if ((flags & PD_FLAGS_PARTNER_DR_DATA) && dr_role == PD_ROLE_UFP)
		pd_request_data_swap(port);
}

/* ----------------- Vendor Defined Messages ------------------ */
const struct svdm_response svdm_rsp = {
	.identity = NULL,
	.svids = NULL,
	.modes = NULL,
};

int pd_custom_vdm(int port, int cnt, uint32_t *payload,
		  uint32_t **rpayload)
{
	int cmd = PD_VDO_CMD(payload[0]);
	uint16_t dev_id = 0;
	int is_rw;

	/* make sure we have some payload */
	if (cnt == 0)
		return 0;

	switch (cmd) {
	case VDO_CMD_VERSION:
		/* guarantee last byte of payload is null character */
		*(payload + cnt - 1) = 0;
		CPRINTF("version: %s\n", (char *)(payload+1));
		break;
	case VDO_CMD_READ_INFO:
	case VDO_CMD_SEND_INFO:
		/* copy hash */
		if (cnt == 7) {
			dev_id = VDO_INFO_HW_DEV_ID(payload[6]);
			is_rw = VDO_INFO_IS_RW(payload[6]);

			CPRINTF("DevId:%d.%d SW:%d RW:%d\n",
				HW_DEV_ID_MAJ(dev_id),
				HW_DEV_ID_MIN(dev_id),
				VDO_INFO_SW_DBG_VER(payload[6]),
				is_rw);
		} else if (cnt == 6) {
			/* really old devices don't have last byte */
			/* SPIKE-A: SYSTEM_IMAGE_UNKNOWN -> EC_IMAGE_UNKNOWN. */
			pd_dev_store_rw_hash(port, dev_id, payload + 1,
					     EC_IMAGE_UNKNOWN);
		}
		break;
	case VDO_CMD_CURRENT:
		CPRINTF("Current: %dmA\n", payload[1]);
		break;
	case VDO_CMD_CCD_EN:
		/*
		 * Chrome OS "CCD enable" debug VDM: select the dual-role power
		 * policy (force sink when unlocked, stop toggling when locked).
		 */
		/* SPIKE-A: pd_set_dual_role() gained a leading port argument. */
		pd_set_dual_role(port, system_is_locked() ? PD_DRP_TOGGLE_OFF
							  : PD_DRP_FORCE_SINK);
		break;
	}

	return 0;
}
