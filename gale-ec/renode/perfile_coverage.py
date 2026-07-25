#!/usr/bin/env python3
"""Per-source-file branch coverage for the captured gale EC firmware.

Rolls the combined coverage up to the source-file level. Every conditional branch in the
rda denominator (tmp/_combined.pkl: cond/executed/edges) is attributed to its function
(map_funcs fingerprint match captured->rebuilt) and then to its **source file** via
`addr2line` on the DWARF-carrying vendored rebuilt ELF, using the rebuilt function-relative
address (reb_start + (branch - cap_start)) so the file is exact, not shift-approximated.
RW-half branches (>=0x08010000) mirror their RO twin (subtract 0x10000 for attribution;
the RW total is folded into the same source file).

A branch is "both-dirs" when both its taken edge and its fall-through edge were executed
in some scenario (identical definition to combine_coverage.py / verify_named_report.py).

Usage: uv run --python .venv python perfile_coverage.py [--csv]
"""
import bisect
import os
import pickle
import subprocess
import sys

import map_funcs as MF

HERE = os.path.dirname(os.path.abspath(__file__))
ELF = MF.ELF

# Pinned upstream base for platform/ec source links (build-firmware.sh EC_REV).
EC_REV = "7c97ab049ffb0ce8c22bb93bc7aac6e404d9cbcb"
UPSTREAM = "https://chromium.googlesource.com/chromiumos/platform/ec/+/" + EC_REV + "/"

# One-line role per compiled source file (for the --md source-file table). Files reconstructed
# in-repo (board/gale/*) are local; everything else is upstream ChromeOS EC at the pinned rev.
DESC = {
    "board/gale/board.c": "Reconstructed gale board init, GPIO/ADC/SPI wiring, rails, `gale` cmd",
    "board/gale/usb_pd_policy.c": "Reconstructed gale USB-PD policy (sink-pref, CCD VDM, power supply)",
    "board/gale/usb_pd_config.h": "Reconstructed gale PD-PHY config (COMP refs, TX timing, CC pins)",
    "common/usb_pd_protocol.c": "USB-PD TCPMv1 state machine + `pd` console command",
    "common/usb_pd_tcpc.c": "Bit-banged TCPC (Type-C port controller) + `tcpc` command",
    "common/usb_pd_policy.c": "Shared PD policy helpers (request/VDM/DR checks)",
    "common/console.c": "Console core: line editing, dispatch, `help`/`history`",
    "common/console_output.c": "Console output channels + `chan` command",
    "common/system.c": "System/image state, reset, jump tags; `sysinfo`/`sysjump`/`syslock`/`reboot`/`version`",
    "common/printf.c": "Formatted-print core (vfnprintf)",
    "common/util.c": "libc-style string/mem utilities",
    "common/flash.c": "Flash abstraction, protection, `flashinfo`/`flashwp` commands",
    "common/vboot_hash.c": "Verified-boot SHA-256 image hashing + `hash` command",
    "common/host_command.c": "Host-command dispatch core + `hcdebug` command",
    "common/hooks.c": "Deferred-work + hook (init/tick/freq) dispatcher",
    "common/memory_commands.c": "`md` (mem dump) / `rw` (read-word) console commands",
    "common/gpio_commands.c": "`gpioget` / `gpioset` console commands",
    "common/gpio.c": "GPIO name table + common accessors",
    "common/adc.c": "ADC abstraction + `adc` console command",
    "common/timer.c": "Software timers, `gettime`/`waitms` commands",
    "common/panic_output.c": "Panic record formatting; `crash`/`panicinfo` commands",
    "common/spi_commands.c": "`spixfer` SPI-transfer console command",
    "common/case_closed_debug.c": "Closed-case-debug (CCD) USB endpoint mux",
    "common/queue.c": "Lock-free byte/word FIFO queue",
    "common/queue_policies.c": "Queue add/remove notification policies",
    "common/shared_mem.c": "Shared scratch-memory allocator",
    "common/sha256.c": "SHA-256 implementation (used by vboot_hash)",
    "common/clz.c": "Count-leading-zeros helper",
    "common/uart_buffering.c": "Buffered UART TX/RX + console snapshot",
    "common/main.c": "EC entry point / task bring-up",
    "common/fmap.c": "Flash-map descriptor (data table, no branches)",
    "common/version.c": "Version struct (data, no branches)",
    "chip/stm32/flash-f.c": "STM32F0 flash program/erase/option-byte driver",
    "chip/stm32/flash-stm32f0.c": "STM32F0 flash geometry glue",
    "chip/stm32/usb_pd_phy.c": "Bit-banged PD PHY: BMC edge decode, TX/RX DMA",
    "chip/stm32/usb.c": "STM32F0 USB device controller driver",
    "chip/stm32/usb_console.c": "USB serial console endpoint",
    "chip/stm32/usb_spi.c": "raiden USB↔SPI bridge (AP-flash access over USB)",
    "chip/stm32/usb-stream.c": "USB stream endpoint plumbing",
    "chip/stm32/usb-stm32f0.c": "STM32F0 USB device init/PMA glue",
    "chip/stm32/usb_endpoints.c": "USB endpoint table (data, no branches)",
    "chip/stm32/dma.c": "STM32F0 DMA driver (UART/SPI channels)",
    "chip/stm32/spi_master.c": "STM32F0 SPI master (AP-flash bridge transport)",
    "chip/stm32/system.c": "STM32F0 system/reset/backup-registers",
    "chip/stm32/i2c-stm32f0.c": "STM32F0 I2C master/slave (host-command transport)",
    "chip/stm32/gpio.c": "STM32F0 GPIO config/IRQ",
    "chip/stm32/gpio-f0-l.c": "STM32F0 GPIO alt-function/flags",
    "chip/stm32/gpio-stm32f0.c": "STM32F0 GPIO port tables (data, no branches)",
    "chip/stm32/adc-stm32f0.c": "STM32F0 12-bit ADC driver",
    "chip/stm32/clock-stm32f0.c": "STM32F0 RCC clock/PLL bring-up",
    "chip/stm32/hwtimer32.c": "32-bit hardware timer (scheduler tick)",
    "chip/stm32/uart.c": "STM32F0 UART low-level",
    "chip/stm32/usart.c": "USART baud/config",
    "chip/stm32/usart-stm32f0.c": "STM32F0 USART variant glue",
    "chip/stm32/usart_rx_interrupt-stm32f0.c": "USART RX-interrupt path",
    "chip/stm32/usart_tx_interrupt.c": "USART TX-interrupt path",
    "chip/stm32/usart_rx_dma.c": "USART RX DMA (data/config, no branches)",
    "chip/stm32/usart_tx_dma.c": "USART TX DMA (data/config, no branches)",
    "chip/stm32/watchdog.c": "STM32F0 IWDG watchdog (no branches)",
    "chip/stm32/jtag-stm32f0.c": "JTAG/SWD disable stub (no branches)",
    "chip/stm32/crc_hw.h": "Hardware CRC unit inline helpers",
    "core/cortex-m0/task.c": "Cooperative RTOS scheduler + `taskinfo` command",
    "core/cortex-m0/panic.c": "Cortex-M0 fault/panic handlers",
    "core/cortex-m0/init.S": "Reset vector + startup (asm)",
    "core/cortex-m0/div.S": "Software divide (asm)",
    "core/cortex-m0/thumb_case.S": "Switch-table thunks (asm)",
    "core/cortex-m0/atomic.h": "Atomic ops inline helpers",
    "driver/usb_mux.c": "USB SuperSpeed mux driver + `typec` command",
    "driver/tcpm/stub.c": "TCPM stub (gale IS the TCPC) + `tcpm_init`",
    "include/task.h": "Task API inline helpers",
}


def flink(f):
    """Markdown link for a source file: local for reconstructed board files, upstream otherwise."""
    if f == "?":
        return "*(unattributed)*"
    if f.startswith("board/gale/"):
        return "[`%s`](%s)" % (f, f)
    return "[`%s`](%s%s)" % (f, UPSTREAM, f)


def norm(path):
    """Reduce a DWARF absolute path to an ec-tree-relative path (board/..., chip/..., common/...)."""
    if not path or path == "??":
        return "?"
    i = path.rfind("/ec/")
    if i >= 0:
        return path[i + 4:]
    # board files are symlinks; DWARF may record the worktree path
    j = path.rfind("/gale-ec/")
    if j >= 0:
        return path[j + 9:]
    return path


def main():
    csv = "--csv" in sys.argv
    with open(os.path.join(HERE, "tmp", "_combined.pkl"), "rb") as f:
        cond, executed, edges = pickle.load(f)

    mapping, cap_end = MF.build_map()          # cap_start -> (reb_start, name, conf)
    cap_starts = sorted(mapping)

    a2l = {}

    def reb_file(reb_addr):
        if reb_addr in a2l:
            return a2l[reb_addr]
        out = subprocess.run(["arm-none-eabi-addr2line", "-e", ELF, "%#x" % reb_addr],
                             capture_output=True, text=True).stdout.strip()
        f = norm(out.rsplit(":", 1)[0])
        a2l[reb_addr] = f
        return f

    per = {}   # file -> [total, both, reached]
    for a in cond:
        ro = a - 0x10000 if a >= 0x08010000 else a
        i = bisect.bisect_right(cap_starts, ro) - 1
        fs = cap_starts[i] if i >= 0 else None
        if fs is None or ro >= cap_end.get(fs, 0):
            file = "?"
        else:
            reb_start, _name, _conf = mapping[fs]
            file = reb_file(reb_start + (ro - fs))
        both = (a, cond[a][1]) in edges and (a, cond[a][0]) in edges
        e = per.setdefault(file, [0, 0, 0])
        e[0] += 1
        e[1] += 1 if both else 0
        e[2] += 1 if a in executed else 0

    rows = sorted(per.items(), key=lambda k: (-k[1][0], k[0]))
    md = "--md" in sys.argv
    if md:
        print("| Source file | Role | Branches | Both-dirs | Reached | Reconstructed? |")
        print("|---|---|--:|--:|--:|---|")
        for file, (t, b, r) in rows:
            desc = DESC.get(file, "—")
            recon = "in-repo" if file.startswith("board/gale/") else "upstream (pinned)"
            print("| %s | %s | %d | %d (%.0f%%) | %d (%.0f%%) | %s |"
                  % (flink(file), desc, t, b, 100.0 * b / t, r, 100.0 * r / t, recon))
    elif csv:
        print("file,total,both_dirs,reached,uncovered,pct_both")
        for file, (t, b, r) in rows:
            print("%s,%d,%d,%d,%d,%.1f" % (file, t, b, r, t - b, 100.0 * b / t))
    else:
        print("%-42s %5s %5s %5s %5s %6s" % ("file", "tot", "both", "rch", "unc", "%both"))
        print("-" * 72)
        for file, (t, b, r) in rows:
            print("%-42s %5d %5d %5d %5d %5.0f%%" % (file, t, b, r, t - b, 100.0 * b / t))
    tt = sum(v[0] for v in per.values())
    bb = sum(v[1] for v in per.values())
    rr = sum(v[2] for v in per.values())
    print("-" * 72)
    print("TOTAL  files=%d  branches=%d  both-dirs=%d (%.1f%%)  reached=%d (%.1f%%)"
          % (len(per), tt, bb, 100.0 * bb / tt, rr, 100.0 * rr / tt))


if __name__ == "__main__":
    main()
