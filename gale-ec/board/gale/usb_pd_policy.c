/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include "adc.h"
#include "charge_manager.h"
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
 * Gale is sink only: it advertises a single 5V/3A dual-role sink PDO and
 * exposes no source PDOs (pd_src_pdo_cnt == 0).
 */
const uint32_t pd_src_pdo[] = {};
const int pd_src_pdo_cnt = 0;

const uint32_t pd_snk_pdo[] = {
		PDO_FIXED(5000, 3000, PDO_FIXED_DUAL_ROLE | PDO_FIXED_DATA_SWAP),
};
const int pd_snk_pdo_cnt = ARRAY_SIZE(pd_snk_pdo);

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

/*
 * Case-Closed-Debug glue. The CCD SRC_ACCESSORY path in usb_pd_protocol.c calls
 * these two charge_manager-era hooks unconditionally. gale runs no charge manager
 * (sink-only, no battery/charger IC), so they are sink-only board stubs:
 * typec_set_input_current_limit reuses the existing 5V/AP-power policy above;
 * charge_manager_update_dualrole has nothing to track (no multi-supplier charging).
 * Keeping them here confines the CCD reconstruction to board/gale.
 */
void typec_set_input_current_limit(int port, uint32_t max_ma,
				   uint32_t supply_voltage)
{
	pd_set_input_current_limit(port, max_ma, supply_voltage);
}

void charge_manager_update_dualrole(int port, enum dualrole_capabilities cap)
{
	/* No charge manager on gale; nothing to update. */
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

int pd_check_data_swap(int port, int data_role)
{
	/* Always allow data swap: we can be DFP or UFP for USB */
	return 1;
}

void pd_execute_data_swap(int port, int data_role)
{
}

void pd_check_pr_role(int port, int pr_role, int flags)
{
}

void pd_check_dr_role(int port, int dr_role, int flags)
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
			pd_dev_store_rw_hash(port, dev_id, payload + 1,
					     SYSTEM_IMAGE_UNKNOWN);
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
		pd_set_dual_role(system_is_locked() ? PD_DRP_TOGGLE_OFF
						    : PD_DRP_FORCE_SINK);
		break;
	}

	return 0;
}
