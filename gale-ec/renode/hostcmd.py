#!/usr/bin/env python3
"""Comprehensive AP host-command battery (EC protocol v3) for the GaleI2c injector.

Each entry is the I2C write payload (0xda + ec_host_request header + params + checksum) for a
real EC_CMD_* the gale firmware implements, with the correct param size so the handler runs
(not just the truncation branch). Covers flash (info/read/write/erase/protect/region — drives
hc_remote_flash / flash_set_protect / flash_physical_erase / write_optb), USB-PD
(control/ports/power_info -> hc_usb_pd_control), reboot (host_command_reboot), console
snapshot/read, get-next-event, plus the error cases from test/host_command.c. Address-
independent: the firmware fills its own host_buffer, so it runs identically on both firmwares.
"""


def _pkt(cmd, ver, sver, data, bad=False):
    dlen = len(data)
    r = [sver & 0xFF, 0, cmd & 0xFF, (cmd >> 8) & 0xFF, ver & 0xFF, 0, dlen & 0xFF, (dlen >> 8) & 0xFF] + list(data)
    r[1] = ((-sum(r)) & 0xFF) ^ (0xA5 if bad else 0)
    return "da" + "".join("%02x" % b for b in r)


def _le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def battery():
    cmds = []
    # General/info commands
    cmds += [_pkt(0x01, 0, 3, [0x44, 0x33, 0x22, 0x11])]   # HELLO in_data=0x11223344
    for c in (0x02, 0x04, 0x05, 0x06, 0x0b, 0x0d, 0x0f):   # GET_VERSION/BUILD/CHIP/BOARD/PROTO/FEATURES...
        cmds += [_pkt(c, 0, 3, [])]
    cmds += [_pkt(0x07, 0, 3, _le32(0)),                   # READ_MEMMAP (offset/size in 1 word here)
             _pkt(0x08, 0, 3, [0x01, 0x00, 0x00, 0x00]),   # GET_CMD_VERSIONS (cmd=1)
             _pkt(0x67, 0, 3, []),                         # GET_NEXT_EVENT
             _pkt(0x97, 0, 3, []),                         # CONSOLE_SNAPSHOT
             _pkt(0x98, 0, 3, _le32(0))]                   # CONSOLE_READ
    # Flash host commands (drive hc_remote_flash / flash_set_protect / erase / write_optb)
    cmds += [_pkt(0x10, 0, 3, []),                                  # FLASH_INFO
             _pkt(0x11, 0, 3, _le32(0x10000) + _le32(8)),          # FLASH_READ off=RW size=8
             _pkt(0x13, 0, 3, _le32(0x18000) + _le32(0x800)),      # FLASH_ERASE off size=2K
             _pkt(0x12, 0, 3, _le32(0x18000) + _le32(4) + _le32(0xDEADBEEF)),  # FLASH_WRITE
             _pkt(0x15, 0, 3, _le32(0) + _le32(0)),                # FLASH_PROTECT (get)
             _pkt(0x15, 0, 3, _le32(1) + _le32(1)),                # FLASH_PROTECT set RO_AT_BOOT
             _pkt(0x16, 0, 3, _le32(0))]                            # FLASH_REGION_INFO
    # USB-PD host commands (drive hc_usb_pd_control + PD info)
    cmds += [_pkt(0x101, 0, 3, [0, 0, 0, 0]),              # USB_PD_CONTROL port0
             _pkt(0x101, 0, 3, [0, 1, 1, 1]),              # USB_PD_CONTROL with role/mux/swap
             _pkt(0x102, 0, 3, []),                        # USB_PD_PORTS
             _pkt(0x103, 0, 3, [0])]                       # USB_PD_POWER_INFO port0
    # EC_CMD_USB_PD_FW_UPDATE (0x110) -> hc_remote_flash. struct {u16 dev_id, u8 cmd, u8 port,
    # u32 size, data...}. Variants walk its branches: bad port, size-overflow, each switch case
    # (REBOOT/FLASH_ERASE/ERASE_SIG/FLASH_WRITE), write-size validation, and the default case.
    def _fw(dev, cmd, port, size, data=None):
        return [dev & 0xFF, (dev >> 8) & 0xFF, cmd & 0xFF, port & 0xFF] + _le32(size) + list(data or [])
    cmds += [_pkt(0x110, 0, 3, _fw(0, 0, 9, 0)),                       # port>=COUNT -> INVALID_PARAM
             _pkt(0x110, 0, 3, _fw(0, 0, 0, 0xFFFF)),                  # size+8>params_size -> INVALID_PARAM
             _pkt(0x110, 0, 3, _fw(0, 0, 0, 0)),                       # USB_PD_FW_REBOOT -> pd_send_vdm
             _pkt(0x110, 0, 3, _fw(0, 1, 0, 0)),                       # USB_PD_FW_FLASH_ERASE
             _pkt(0x110, 0, 3, _fw(0, 3, 0, 0)),                       # USB_PD_FW_ERASE_SIG -> timeout wait
             _pkt(0x110, 0, 3, _fw(0, 2, 0, 0)),                       # FLASH_WRITE size=0 -> INVALID_PARAM
             _pkt(0x110, 0, 3, _fw(0, 2, 0, 3, [1, 2, 3])),            # FLASH_WRITE size%4 -> INVALID_PARAM
             _pkt(0x110, 0, 3, _fw(0, 2, 0, 4, [0xDE, 0xAD, 0xBE, 0xEF])),  # FLASH_WRITE valid 4B
             _pkt(0x110, 0, 3, _fw(0, 99, 0, 0)),                      # default -> INVALID_PARAM
             _pkt(0x111, 0, 3, [0] * 24),                              # USB_PD_RW_HASH_ENTRY
             _pkt(0x112, 0, 3, [0, 0])]                                # USB_PD_DEV_INFO port0
    # Reboot (host_command_reboot) — cmd=0 (cancel, safe)
    cmds += [_pkt(0xd2, 0, 3, [0, 0])]
    # The remaining implemented EC_CMDs (from the captured __hcmds table) whose handlers were
    # otherwise NEVER ENTERED — sending each covers its handler entry + param-validation branches.
    gpio_name = list(b"EC_INT_L") + [0] * (32 - 8)
    cmds += [
        _pkt(0x00, 0, 3, []),                              # PROTO_VERSION
        _pkt(0x03, 0, 3, _le32(0) + _le32(0x20)),          # READ_TEST {offset,size}
        _pkt(0x09, 0, 3, []),                              # GET_COMMS_STATUS
        _pkt(0x0a, 0, 3, _le32(0) + _le32(4) + [0] * 32),  # TEST_PROTOCOL {ec_result,ret_len,buf[32]}
        _pkt(0x17, 0, 3, _le32(0) + [0] * 16),             # VBNV_CONTEXT {op=read, block[16]}
        _pkt(0x2a, 0, 3, [0, 0, 0, 0] + _le32(0) + _le32(0)),   # VBOOT_HASH {cmd=GET,...}
        _pkt(0x2a, 0, 3, [2, 1, 0, 0] + _le32(0) + _le32(0x10000)),  # VBOOT_HASH {cmd=START,SHA256}
        _pkt(0x92, 0, 3, gpio_name + _le32(1)),            # GPIO_SET {name[32],val}
        _pkt(0x93, 0, 3, gpio_name),                       # GPIO_GET {name[32]}
        _pkt(0xb6, 0, 3, _le32(0)),                        # ENTERING_MODE {vtm}
        _pkt(0xd3, 0, 3, []),                              # GET_PANIC_INFO
        _pkt(0xdb, 0, 3, []),                              # RESEND_RESPONSE
        # the 4 registered __hcmds whose handlers were still never driven (256/282/488/640)
        _pkt(0x100, 0, 3, []), _pkt(0x100, 0, 3, [0] * 8),
        _pkt(0x11a, 0, 3, []), _pkt(0x11a, 0, 3, [0] * 8),
        _pkt(0x1e8, 0, 3, []), _pkt(0x1e8, 0, 3, [0] * 8),
        _pkt(0x280, 0, 3, []), _pkt(0x280, 0, 3, [0] * 8),
    ]
    # DEEP PARAM VARIATIONS for the handlers with the most uncovered arms (dispatch + validation),
    # the host-command analog of the console battery: vary sub-command / flags / size / port so each
    # arm of the handler's switch + arg-checks runs.
    def _fw(dev, cmd, port, size, data=None):
        return [dev & 0xFF, (dev >> 8) & 0xFF, cmd & 0xFF, port & 0xFF] + _le32(size) + list(data or [])
    # 0x110 USB_PD_FW_UPDATE / hc_remote_flash: every switch case x port/size/data validation
    for dev in (0, 1):
        for cmd in (0, 1, 2, 3, 4, 5, 99):                 # REBOOT/FLASH_ERASE/WRITE/ERASE_SIG/.../default
            cmds += [_pkt(0x110, 0, 3, _fw(dev, cmd, 0, 0))]
    cmds += [_pkt(0x110, 0, 3, _fw(0, 2, 0, 4, [0xDE, 0xAD, 0xBE, 0xEF])),   # write 4B valid
             _pkt(0x110, 0, 3, _fw(0, 2, 0, 3, [1, 2, 3])),                  # write size%4 -> INVAL
             _pkt(0x110, 0, 3, _fw(0, 2, 9, 4, [0, 0, 0, 0])),               # bad port
             _pkt(0x110, 0, 3, _fw(0, 2, 0, 0x10000))]                       # size overflow
    # 0x2a VBOOT_HASH {u8 cmd, hash_type, nonce_size, rsvd, u32 offset, u32 size, nonce[]}
    for hcmd in (0, 1, 2, 3, 99):                          # GET/ABORT/START/RECALC/bad
        cmds += [_pkt(0x2a, 0, 3, [hcmd, 1, 0, 0] + _le32(0) + _le32(0x10000))]
    cmds += [_pkt(0x2a, 0, 3, [2, 0, 0, 0] + _le32(0) + _le32(0x1000)),      # bad hash_type
             _pkt(0x2a, 0, 3, [2, 1, 4, 0] + _le32(0) + _le32(0x1000) + [1, 2, 3, 4])]  # with nonce
    # 0xd2 REBOOT_EC {u8 cmd, u8 flags}
    for rcmd in (0, 1, 2, 3, 4, 5, 6, 99):                 # CANCEL/JUMP_RO/JUMP_RW/COLD/DISABLE/HIBERNATE/...
        for fl in (0, 1, 2):
            cmds += [_pkt(0xd2, 0, 3, [rcmd, fl])]
    # 0x101 USB_PD_CONTROL {u8 port, u8 role, u8 mux, u8 swap} (role/mux/swap dispatch)
    for role in (0, 1, 2, 3):
        for mux in (0, 1, 2):
            cmds += [_pkt(0x101, 0, 3, [0, role, mux, 0])]
    cmds += [_pkt(0x101, 0, 3, [9, 0, 0, 0])]              # bad port
    # 0x93 GPIO_GET sub-commands {u8 subcmd, ...}; 0x8 GET_CMD_VERSIONS for various cmds
    gpio_name = list(b"EC_INT_L") + [0] * 24
    for sub in (0, 1, 2):
        cmds += [_pkt(0x93, 1, 3, gpio_name + [sub])]
    for q in (0x01, 0x08, 0x2a, 0x110, 0xff):
        cmds += [_pkt(0x08, 0, 3, _le32(q))]
    # 0x17 VBNV_CONTEXT read+write ; 0x111 RW_HASH_ENTRY ; 0x16 FLASH_REGION_INFO regions
    cmds += [_pkt(0x17, 0, 3, _le32(0) + [0] * 16), _pkt(0x17, 0, 3, _le32(1) + [0xAA] * 16),
             _pkt(0x111, 0, 3, [0, 0] + [0] * 22), _pkt(0x111, 0, 3, [1, 0] + [0x11] * 22),
             _pkt(0x16, 0, 3, _le32(0)), _pkt(0x16, 0, 3, _le32(1)), _pkt(0x16, 0, 3, _le32(2)),
             _pkt(0x16, 0, 3, _le32(99))]                   # bad region
    # SEQUENCE: register PD devices (0x111 RW_HASH_ENTRY) so 0x110's device-iteration loop runs over
    # populated entries, then FW_UPDATE ops that walk them. {u16 dev_id, u8 hash[20], reserved}
    for dev in (1, 2, 3, 4):
        cmds += [_pkt(0x111, 0, 3, [dev, 0] + [(dev * 0x11 + i) & 0xFF for i in range(20)] + [0, 0])]
    cmds += [_pkt(0x112, 0, 3, [0, 0]), _pkt(0x112, 0, 3, [1, 0])]   # DEV_INFO per port
    for cmd in (0, 1, 2, 3):
        cmds += [_pkt(0x110, 0, 3, _fw(1, cmd, 0, 0)), _pkt(0x110, 0, 3, _fw(2, cmd, 0, 4, [1, 2, 3, 4]))]
    # 0x93 GPIO_GET sub-commands (BY_NAME=0 / COUNT=1 / INFO=2 with index)
    gname = list(b"EC_INT_L") + [0] * 24
    for sub, idx in ((0, 0), (1, 0), (2, 0), (2, 1), (2, 5)):
        cmds += [_pkt(0x93, 1, 3, gname + [sub] + _le32(idx))]
    # 0x101 USB_PD_CONTROL more combos (swap field too) {port, role, mux, swap}
    for sw in (0, 1, 2, 3, 4):
        cmds += [_pkt(0x101, 0, 3, [0, 1, 1, sw])]
    # Error cases (ported from test/host_command.c)
    cmds += [_pkt(0x1234, 0, 3, []),                       # invalid command -> INVALID_COMMAND
             _pkt(0x01, 1, 3, _le32(0)),                   # wrong cmd version -> INVALID_VERSION
             _pkt(0x01, 0, 4, _le32(0)),                   # struct_version 4 -> INVALID_HEADER
             _pkt(0x01, 0, 2, _le32(0)),                   # struct_version 2 -> INVALID_HEADER
             _pkt(0x01, 0, 3, _le32(0), bad=True)]         # bad checksum -> INVALID_CHECKSUM
    return cmds


def post(prefix=None):
    """Monitor commands: inject the whole battery via GaleI2c, settling between each."""
    c = list(prefix or [])
    for p in battery():
        c += ['sysbus.i2c1 HostCmd "%s"' % p, 'emulation RunFor "0.05"']
    return c
