#!/usr/bin/env python3
"""Branch-coverage measurement of the CAPTURED DEVICE firmware (the reference).

The captured firmware is a raw flash dump with no ELF/symbols, so branches are enumerated by
DISASSEMBLING THE RAW BINARY (objdump -b binary, Thumb) — RO at 0x08000000, RW at 0x08010000.
A PC execution trace is captured while the firmware runs the test suite, then mapped against
that disassembly to compute instruction + both-directions branch coverage.

Per the project goal: the captured firmware is the reference; every branch in it must be
reachable and executed by the emulation test suite. The test scenarios here are
address-INDEPENDENT (console commands, sysjump, deliberate crashes, AP host commands via the
GaleI2c injector — the firmware fills its own buffers), so they run identically on the captured
and rebuilt firmwares.

Usage: uv run python coverage_captured.py [--bin <captured>] [--boot 2.0]
"""
import argparse
import os
import re
import subprocess

import coverage_full   # reuse the address-independent scenario helpers (console-edit, faults, cmd args)

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
TC = "/home/tim/local/gwifi/ec-rebuild/gcc-arm-none-eabi-5_4-2016q3/bin"
OBJDUMP = os.path.join(TC, "arm-none-eabi-objdump")
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")
COND = re.compile(r'\b(b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)|cbz|cbnz)(\.[nw])?\b')

RO_CMDS = ["version", "sysinfo", "gettime", "taskinfo", "timerinfo", "gpioget", "adc",
           "panicinfo", "chan", "flashinfo", "shmem", "history", "hcdebug", "hostevent",
           "pd 0 state", "pd 0 srccaps", "pd dump 3", "tcpc", "typec", "syslock", "waitms 1",
           "gpioget LID_OPEN", "md 0x20000000", "flashwp", "gale"]
CRASH = ["crash unaligned", "crash divzero", "crash udf", "crash assert", "crash watchdog"]
# Console commands with VALID + ERROR args (address-independent) -> command_* parsing + vfnprintf
CMD_ARGS = [
    "help", "help pd", "help gpioget", "help xyzzy", "version foo",
    "gpioget EC_INT_L", "gpioget NOPE", "gpioset EC_INT_L 1", "gpioset BADPIN 1",
    "md 0x20000000 4", "md .b 0x08000000", "md badaddr", "rw 0x20000000", "rw badaddr",
    "spixfer rlen 0 0x9f 3", "spixfer 0", "spixfer badarg",
    "pd 0", "pd 9 state", "pd 0 bogus", "pd 0 dump 9", "pd 0 trysrc 1", "pd 0 dualrole source",
    "pd 0 dualrole sink", "pd 0 dualrole toggle-off", "pd 0 dualrole freeze",
    "tcpc 0", "typec 0", "flashwp bogus", "flashwp enable", "flashwp now", "flashwp disable",
    "chan 0", "chan save", "chan restore", "hcdebug params", "gale power on ap", "gale power off ap",
    "reboot ro", "hibernate 1"]


def _hc_packet(cmd, ver, sver, dlen, data, bad_csum=False):
    """Build an I2C host-command write payload: 0xda + ec_host_request + data + checksum."""
    req = [sver & 0xFF, 0x00, cmd & 0xFF, (cmd >> 8) & 0xFF, ver & 0xFF, 0x00,
           dlen & 0xFF, (dlen >> 8) & 0xFF] + list(data)
    req[1] = ((-sum(req)) & 0xFF) ^ (0xA5 if bad_csum else 0)
    return "da" + "".join("%02x" % b for b in req)


def host_cmd_battery():
    """EC host-command packets driving host_command_process + hc_* — valid commands AND the
    error cases ported from test/host_command.c (each flips a different host_command_process
    branch: SUCCESS / INVALID_COMMAND / INVALID_VERSION / INVALID_HEADER / REQUEST_TRUNCATED /
    INVALID_CHECKSUM)."""
    out = []
    # Valid commands (cover hc_* handlers)
    for cmd, dlen, data in [(0x0001, 4, [0x44, 0x33, 0x22, 0x11]),  # HELLO in_data=0x11223344
                            (0x0002, 0, []), (0x0003, 0, []), (0x0004, 0, []), (0x0005, 0, []),
                            (0x0006, 0, []), (0x0007, 4, [0, 0, 0, 0]), (0x0008, 2, [1, 0]),
                            (0x000b, 0, []), (0x0010, 0, []), (0x000d, 0, []), (0x000f, 0, [])]:
        out.append(_hc_packet(cmd, 0, 3, dlen, data))
    # Error cases (ported from test/host_command.c) -> host_command_process error branches
    out.append(_hc_packet(0x00ff, 0, 3, 0, []))                 # invalid command -> INVALID_COMMAND
    out.append(_hc_packet(0x0001, 1, 3, 4, [0, 0, 0, 0]))       # wrong cmd version -> INVALID_VERSION
    out.append(_hc_packet(0x0001, 0, 4, 4, [0, 0, 0, 0]))       # struct_version 4 -> INVALID_HEADER
    out.append(_hc_packet(0x0001, 0, 2, 4, [0, 0, 0, 0]))       # struct_version 2 -> INVALID_HEADER
    out.append(_hc_packet(0x0001, 0, 3, 0xFFFF, []))            # huge data_len -> REQUEST_TRUNCATED
    out.append(_hc_packet(0x0001, 0, 3, 4, [0, 0, 0, 0], bad_csum=True))  # bad checksum -> INVALID_CHECKSUM
    return out


def _pd_contract_post():
    """Address-independent live PD contract: ForceSourceCc sink-attach + queue-delivered
    Source_Caps/Accept/PS_RDY + counter-based auto-GoodCRC (no per-firmware RAM addresses)."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    def fire(t):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c += fire("0.2") + fire("0.2") + fire("0.4")
    # SNK_READY: inject a broad set of message TYPES the EC dispatches -> handle_ctrl_request /
    # handle_data_request / pd_svdm branches. ctrl types: GOTO_MIN2 ACCEPT3 REJECT4 PING5 PS_RDY6
    # GET_SRC_CAP7 GET_SNK_CAP8 DR_SWAP9 PR_SWAP10 VCONN_SWAP11 WAIT12 SOFT_RESET13.
    mid = 3
    msgs = []
    for t in (8, 7, 9, 10, 11, 12, 5, 2, 4, 13, 6, 3):
        msgs.append(pd_encode.ctrl(t, mid)); mid += 1
    # VDM commands: Discover Identity(1)/SVIDs(2)/Modes(3)/Enter(4)/Exit(5) + a data SOURCE_CAP.
    for vcmd in (1, 2, 3, 4, 5):
        vdm = (0xFF00 << 16) | (1 << 15) | (0 << 6) | vcmd
        msgs.append((pd_encode.header(15, 1, mid), [vdm])); mid += 1
    msgs.append(pd_encode.SRC_CAP)            # re-send Source_Caps in READY (re-request path)
    for m in msgs:
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire("0.1")
    return c


def scenarios(boot):
    s = [("ro", [], RO_CMDS, boot, [])]
    # Live USB-PD contract (ForceSourceCc = address-independent sink attach) — RO + RW
    s.append(("pd", ['sysbus.adc ForceSourceCc true'], [], "2.0", _pd_contract_post()))
    s.append(("pd_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _pd_contract_post()))
    # Debug accessory -> SRC_ACCESSORY -> ccd_set_mode -> usb_init/CCD + raiden over the bridge.
    s.append(("ccd", ['sysbus.adc ForceAccessory true'],
              ["spixfer rlen 0 0x1f 3", "spixfer 500 0x9f", "pd 0 state", "typec", "version"], "2.5", []))
    s.append(("ccd_rw", ['sysbus.adc ForceAccessory true'],
              ["sysjump rw", "spixfer rlen 0 0x1f 3", "pd 0 state"], "2.5", []))
    s.append(("rw", [], ["sysjump rw"] + RO_CMDS, boot, []))
    for c in CRASH:
        s.append(("crash_" + c.split()[1], [], [c], boot, []))
        s.append(("crashrw_" + c.split()[1], [], ["sysjump rw", c], boot, []))
    # AP host commands (address-independent injector) — RO and RW
    hc = []
    for p in host_cmd_battery():
        hc += ['sysbus.i2c1 HostCmd "%s"' % p, 'emulation RunFor "0.05"']
    s.append(("hostcmd", [], [], boot, hc))
    s.append(("hostcmd_rw", [], ["sysjump rw"], boot, hc))
    # address-independent high-yield scenarios (reused from coverage_full)
    s.append(("cmd_args", [], CMD_ARGS, boot, []))
    s.append(("cmd_args_rw", [], ["sysjump rw"] + CMD_ARGS, boot, []))
    s.append(("console_edit", [], [], boot, coverage_full._edit_bytes()))
    s.append(("console_edit_rw", [], ["sysjump rw"], boot, coverage_full._edit_bytes()))
    s.append(("flash_fault", [], [], boot, coverage_full._fault_post()))
    s.append(("flash_fault_rw", [], ["sysjump rw"], boot, coverage_full._fault_post()))
    return s


# .text (code) ranges — branches/instructions outside these are .rodata/.data mis-disassembled
# as Thumb and must NOT be counted. Bounds from the equivalent rebuilt ELF (.text size 0xb744,
# RO @0x08000000, RW @0x08010000); the captured firmware shares this layout (same source).
TEXT_RANGES = [(0x08000000, 0x0800b744), (0x08010000, 0x0801b744)]


def _in_text(addr):
    return any(lo <= addr < hi for lo, hi in TEXT_RANGES)


def disasm_branches(binpath):
    """Disassemble the raw binary (Thumb) at 0x08000000; return (insn addrs, cond branch map).
    Only .text-range instructions are counted (excludes .rodata/.data false branches)."""
    out = subprocess.run([OBJDUMP, "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                          "--adjust-vma=0x08000000", binpath],
                         stdout=subprocess.PIPE, universal_newlines=True).stdout
    insns, cond = {}, {}
    for ln in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f ]+?)\s+(\S.*)$', ln)
        if not m:
            continue
        addr = int(m.group(1), 16)
        if not _in_text(addr):
            continue
        nb = len(m.group(2).replace(" ", "")) // 2
        insns[addr] = nb
        cm = COND.search(m.group(3))
        if cm:
            tm = re.search(r'\b([0-9a-f]+)\s+<', m.group(3)) or re.search(r'#?(0x[0-9a-f]+)', m.group(3))
            if tm:
                cond[addr] = (addr + nb, int(tm.group(1), 16))
    return set(insns), cond


def run_scenario(name, mon, cmds, boot, post, binpath):
    trace = os.path.join(TMP, "cap_%s.txt" % name)
    c = ['$h=@%s' % HERE, '$bin=@%s' % binpath, '$name="cap"', 'include @%s' % BASE] + mon
    c += ['cpu CreateExecutionTracing "tr_%s" @%s PC' % (name, trace), 'emulation RunFor "%s"' % boot]
    for cmd in cmds:
        c += ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (cmd + "\r")]
        c.append('emulation RunFor "0.06"')
    c += (post or [])
    c += ['cpu DisableExecutionTracing', 'quit']
    subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(c)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)
    return trace


def fold(path, cond, executed, taken, nottaken):
    prev = None
    if not os.path.exists(path):
        return
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            pc = int(ln, 16)
            executed.add(pc)
            if prev is not None and prev in cond:
                fa, tg = cond[prev]
                if pc == tg:
                    taken.add(prev)
                elif pc == fa:
                    nottaken.add(prev)
            prev = pc
    os.remove(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=CAPTURED)
    ap.add_argument("--boot", default="2.0")
    args = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)
    binpath = os.path.abspath(args.bin)
    all_insn, cond = disasm_branches(binpath)
    scns = scenarios(args.boot)
    print("CAPTURED firmware coverage: %s (%d scenarios)" % (os.path.basename(binpath), len(scns)))
    executed, taken, nottaken = set(), set(), set()
    for name, mon, cmds, boot, post in scns:
        print("  scenario: %-16s" % name)
        fold(run_scenario(name, mon, cmds, boot, post, binpath), cond, executed, taken, nottaken)
    # Only count branches in EXECUTED code regions (raw disasm includes literal-pool data that
    # is never executed; a branch is "real code" if reached, or adjacent to reached instructions).
    reached = [a for a in cond if a in executed]
    both = [a for a in cond if a in taken and a in nottaken]
    ex = executed & all_insn
    print("\n=== CAPTURED firmware ===")
    print("  instructions executed: %d" % len(ex))
    print("  cond branches (raw disasm): %d total, %d reached, %d both-dirs covered" %
          (len(cond), len(reached), len(both)))
    print("  branch coverage: %.1f%% of reached both-dirs" % (100.0 * len(both) / max(len(reached), 1)))
    uncov = sorted(a for a in reached if a not in (set(taken) & set(nottaken)))
    with open(os.path.join(HERE, "cap_uncovered.txt"), "w") as f:
        for a in uncov:
            f.write("0x%08x %s\n" % (a, "taken-only" if a in taken else ("nottaken-only" if a in nottaken else "?")))
    print("  reached-but-one-direction branches -> cap_uncovered.txt (%d)" % len(uncov))


if __name__ == "__main__":
    main()
