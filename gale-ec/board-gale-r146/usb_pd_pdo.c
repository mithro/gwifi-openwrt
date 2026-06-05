/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/*
 * SPIKE-A forward-port: with CONFIG_USB_PD_CUSTOM_PDO the default PDO tables in
 * common/usb_pd_pdo.c are compiled out, and the genvif host tool links the
 * board's PDO tables from board/<board>/usb_pd_pdo.c (see util/build.mk). The
 * tables previously lived in usb_pd_policy.c; move them here so they are shared
 * by both the firmware and genvif, matching the modern board layout
 * (e.g. board/servo_v4/usb_pd_pdo.c).
 *
 * Only usb_pd.h is included (not usb_pd_pdo.h) because usb_pd_pdo.h fixes the
 * array dimensions to pd_src_pdo[1]/pd_snk_pdo[3], whereas gale advertises an
 * empty source PDO list and a single sink PDO. usb_pd.h declares these arrays
 * unsized.
 */

#include "compile_time_macros.h"
#include "usb_pd.h"

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
