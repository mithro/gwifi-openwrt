# -*- makefile -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Board specific files build

# the IC is STmicro STM32F072CB
CHIP:=stm32
CHIP_FAMILY:=stm32f0
CHIP_VARIANT:=stm32f07x

board-y=board.o
# SPIKE-A forward-port: PDO tables split into usb_pd_pdo.o so the genvif host
# tool can link them under CONFIG_USB_PD_CUSTOM_PDO (see util/build.mk).
board-$(CONFIG_USB_POWER_DELIVERY)+=usb_pd_policy.o usb_pd_pdo.o
