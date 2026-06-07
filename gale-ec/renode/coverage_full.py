#!/usr/bin/env python3
"""CUMULATIVE branch-coverage campaign for the gale EC firmware under Renode.

Branch coverage is the UNION over many test scenarios: a conditional branch counts as
fully covered when its taken direction is seen in SOME scenario and its not-taken
direction in SOME (possibly different) scenario. A single boot only walks one path
through each defensive branch; driving both directions needs varied inputs AND
deliberate fault injection (the `crash` command, flash/SPI error injection, etc.).

This harness runs a battery of scenarios on BOTH images (RO and, via `sysjump rw`, RW),
captures a PC execution trace per scenario, and unions:
  * executed instructions  (instruction coverage)
  * per-branch taken / not-taken directions  (branch coverage, both-directions)
across all scenarios, then reports cumulative coverage per image.

It also writes the per-image set of branches still uncovered (addr + containing symbol)
to cov_uncovered_{RO,RW}.txt for the exclusion-justification analysis (classify.py).

Usage: uv run python coverage_full.py [--boot 1.5]
"""
import argparse
import os
import re
import subprocess

import pd_encode
import pd_inject
import usb_host
import hostcmd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
TC = "/home/tim/local/gwifi/ec-rebuild/gcc-arm-none-eabi-5_4-2016q3/bin"
OBJDUMP = os.path.join(TC, "arm-none-eabi-objdump")
RW_ELF = "/home/tim/local/gwifi/ec-rebuild/ec/build/gale/RW/ec.RW.elf"
RO_ELF = "/home/tim/local/gwifi/ec-rebuild/ec/build/gale/RO/ec.RO.elf"
REBUILT = os.path.join(HERE, "ec-rebuilt.bin")
TMP = os.path.join(HERE, "tmp")

COND = re.compile(r'\b(b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)|cbz|cbnz)(\.[nw])?\b')

# Read-only console commands safe to run in either image.
RO_CMDS = ["version", "sysinfo", "gettime", "taskinfo", "timerinfo", "gpioget", "adc",
           "panicinfo", "chan", "flashinfo", "shmem", "history", "hcdebug", "hostevent",
           "pd 0 state", "pd 0 srccaps", "pd dump", "tcpc", "typec", "syslock",
           "gpioget LID_OPEN", "md 0x20000000", "waitms 1",
           # hash command (command_hash, 13 unreached): no-arg status + recompute RO/RW + abort
           "hash", "hash ro", "hash rw", "hash 0x10000 0x100", "hash abort", "hash bogus"]
# Deliberate fault / state-changing commands (drive defensive + handler branches).
CRASH_CMDS = ["crash unaligned", "crash divzero", "crash udf", "crash assert", "crash watchdog"]


def _edit_bytes():
    """Monitor WriteChar commands exercising console line-editing in console_handle_char:
    populate history, then arrows (history/cursor), home/end, left/right, backspace, DEL,
    kill-to-end, mid-line insert, bad escape sequences, and an over-long line."""
    ESC = 27
    UP, DOWN, RIGHT, LEFT = [ESC, 91, 65], [ESC, 91, 66], [ESC, 91, 67], [ESC, 91, 68]
    HOME, DEL = [ESC, 91, 49, 126], [ESC, 91, 51, 126]
    seq = []
    seq += list(b"gpioget\r")                 # a real command -> saved to history
    seq += list(b"version\r")                 # another history entry
    seq += UP + UP + DOWN                      # history prev/prev/next
    seq += list(b"abcdef")                     # type
    seq += [1] + [5]                           # CTRL-A (home) / CTRL-E (end)
    seq += LEFT + LEFT + RIGHT                 # cursor moves
    seq += [2] + [6]                           # CTRL-B (left) / CTRL-F (right)
    seq += list(b"XY")                         # insert mid-line
    seq += [8] + [0x7f]                        # backspace x2 (two encodings)
    seq += HOME + DEL                          # home then delete-forward
    seq += [11]                                # CTRL-K kill-to-end
    seq += [ESC, 79, 88]                       # ESC O X (alt escape path)
    seq += [ESC, 90]                           # ESC Z (bad escape)
    seq += list(b"x" * 90)                     # over-long line (> input buffer)
    seq += [9]                                 # tab
    seq += [3]                                 # CTRL-C
    seq += [0x0d]                              # enter
    cmds = []
    for i, b in enumerate(seq):
        cmds.append('sysbus.usart1 WriteChar %d' % b)
        if i % 12 == 11:
            cmds.append('emulation RunFor "0.01"')
    cmds.append('emulation RunFor "0.05"')
    return cmds


def _hexmsg(msg):
    s = pd_encode.encode_message(*msg)
    pad = bytes([(s[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])
    return (s + pad).hex()


def _firecomp(settle):
    c = []
    for _ in range(3):
        c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
    c += ['emulation RunFor "%s"' % settle]
    return c


def _fire_contract(settle):
    c = ['sysbus.dma1 ExpectContractMsg']
    for _ in range(3):
        c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
    return c + ['emulation RunFor "%s"' % settle]


def _contract_post():
    """Live explicit PD contract to SNK_READY via the context-aware CC-partner: the GoodCRC
    gale waits for after its Request is auto-injected (msg_id read from RAM) by GaleDma on the
    synchronous pd_rx_start; the Source_Caps/Accept/PS_RDY are FireComp-driven contract msgs.
    Then exercise ready-state ops (Get_Sink_Cap, VDM Discover Identity, PR/DR swap requests) so
    pd_task's SNK_REQUESTED/TRANSITION/READY + handle_ctrl/data + pd_svdm + swap branches run."""
    c = ['sysbus.dma1 ClearResponses']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, _hexmsg(pd_encode.ctrl(1, i)))]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % _hexmsg(m)]
    c += _fire_contract("0.2") + _fire_contract("0.2") + _fire_contract("0.5")
    # SNK_READY now: inject ready-state messages the EC responds to (each FireComp-driven).
    for m in (pd_encode.ctrl(8, 3), pd_encode.vdm_discover_identity(4),
              pd_encode.ctrl(9, 5), pd_encode.ctrl(10, 6), pd_encode.ctrl(2, 7)):  # GetSnkCap/VDM/DR_Swap/PR_Swap/GotoMin
        c += ['sysbus.dma1 StageResponse "%s"' % _hexmsg(m)] + _fire_contract("0.15")
    return c


def _fault_post():
    """Flash fault injection -> EC_ERROR_* / WRPRTERR / PGERR / stuck-busy paths. Set a model
    error knob, then drive a flash op (flashwp protect = a pstate flash_physical_write)."""
    def cw(cmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (cmd + "\r")] + ['emulation RunFor "0.05"']
    c = ['sysbus.flashif InjectWriteProtErr true'] + cw("flashwp now")
    c += ['sysbus.flashif InjectProgErr true'] + cw("flashwp enable")
    c += ['sysbus.flashif StuckBusy true'] + cw("flashwp now") + ['sysbus.flashif StuckBusy false']
    c += cw("flashinfo")
    return c



def _hc_battery_post(prefix):
    """AP host-command battery via GaleI2c (address-independent): valid + error packets."""
    def pkt(cmd, ver, sver, dlen, data, bad=False):
        r=[sver&0xFF,0,cmd&0xFF,(cmd>>8)&0xFF,ver&0xFF,0,dlen&0xFF,(dlen>>8)&0xFF]+list(data)
        r[1]=((-sum(r))&0xFF)^(0xA5 if bad else 0)
        return "da"+"".join("%02x"%b for b in r)
    pl=[pkt(c,0,3,dl,d) for c,dl,d in [(1,4,[0x44,0x33,0x22,0x11]),(2,0,[]),(4,0,[]),(5,0,[]),
        (6,0,[]),(7,4,[0,0,0,0]),(8,2,[1,0]),(0xb,0,[]),(0x10,0,[]),(0xd,0,[]),(0xf,0,[])]]
    pl+=[pkt(0xff,0,3,0,[]),pkt(1,1,3,4,[0,0,0,0]),pkt(1,0,4,4,[0,0,0,0]),pkt(1,0,2,4,[0,0,0,0]),
         pkt(1,0,3,0xFFFF,[]),pkt(1,0,3,4,[0,0,0,0],bad=True)]
    c=list(prefix)
    for x in pl: c+=['sysbus.i2c1 HostCmd "%s"'%x,'emulation RunFor "0.05"']
    return c

def scenarios(boot):
    """List of (name, monitor-prelude-cmds, console-cmds). All run on ec-rebuilt.bin."""
    s = []
    s.append(("ro_readonly", [], RO_CMDS))
    s.append(("rw_readonly", [], ["sysjump rw"] + RO_CMDS))
    # debug accessory: brings up SRC_ACCESSORY -> ccd_set_mode -> usb_init -> usb_spi
    s.append(("ccd_usb", ['sysbus.adc ForceAccessory true'],
              ["spixfer rlen 0 0x1f 3", "spixfer 500 0x9f", "pd 0 state", "typec"]))
    s.append(("ccd_usb_rw", ['sysbus.adc ForceAccessory true'],
              ["sysjump rw", "spixfer rlen 0 0x1f 3", "pd 0 state"]))
    # SINK attach to a SOURCE partner (GaleAdc PartnerSource): drives SNK_DISCONNECTED ->
    # DEBOUNCE -> SNK_DISCOVERY and the SinkWaitCap/soft-reset/hard-reset cycling branches.
    s.append(("pd_sink", ['sysbus.adc ForceSourceCc true'],
              ["pd 0 state", "pd dump 3", "pd 0 state", "typec", "tcpc"]))
    # SPI flash exercise (raiden target) — multiple lengths/offsets
    s.append(("spi", [], ["spixfer rlen 0 0x9f 3", "spixfer rlen 0 0x03000000 8",
                          "spixfer 2000 0x9f", "flashinfo"]))
    # write-protect / lock state machine
    s.append(("wp", [], ["flashwp", "flashwp enable", "flashwp now", "syslock", "flashinfo"]))
    # PD subcommands across ports/roles
    s.append(("pd", [], ["pd 0 dualrole", "pd 0 dualrole sink", "pd 0 dualrole source",
                         "pd 0 dualrole toggle-off", "pd 0 dualrole freeze", "pd 0 state",
                         "pd 0 tx", "pd dump 4", "tcpc", "typec"]))
    # deliberate crashes -> fault/panic/assert/hardfault handlers (RO)
    for c in CRASH_CMDS:
        s.append(("crash_ro_%s" % c.split()[1], [], [c]))
    # deliberate crashes in RW
    for c in CRASH_CMDS:
        s.append(("crash_rw_%s" % c.split()[1], [], ["sysjump rw", c]))
    # reboot/hibernate handler paths
    s.append(("reboot", [], ["reboot hard", "version"]))
    s.append(("hibernate", [], ["hibernate 1", "version"]))
    s.append(("gale", [], ["gale", "gale power on ap", "gale power off ap"]))
    # Many console commands with VALID + ERROR args -> command_* arg parsing + vfnprintf
    cmd_args_list = [
        "help", "help pd", "help gpioget", "help xyzzy", "version", "version foo",
        "gpioget", "gpioget EC_INT_L", "gpioget NOPE", "gpioset EC_INT_L 1", "gpioset BADPIN 1",
        "md", "md 0x20000000", "md 0x20000000 4", "md .b 0x08000000", "md badaddr",
        "rw 0x20000000", "rw", "rw badaddr", "rw 0x20000000 0x1234",
        "spixfer", "spixfer rlen 0 0x9f 3", "spixfer 0", "spixfer badarg",
        "pd", "pd 0", "pd 9 state", "pd 0 bogus", "pd 0 dump", "pd 0 dump 9", "pd 0 trysrc 1",
        "tcpc", "tcpc 0", "typec", "typec 0", "flashinfo", "flashwp", "flashwp bogus",
        "gettime", "timerinfo", "taskinfo", "sysinfo", "panicinfo", "chan", "chan 0",
        "chan save", "chan restore", "shmem", "hcdebug", "hcdebug params", "hostevent",
        "sysjump ro", "waitms 0", "adc", "syslock"]
    s.append(("cmd_args", [], cmd_args_list))
    s.append(("cmd_args_rw", [], ["sysjump rw"] + cmd_args_list))   # same battery, in RW
    # flash protect / option-byte paths
    s.append(("flash_ops", [], ["flashwp", "flashwp enable", "flashwp disable", "flashwp now",
                                 "flashwp noprotect", "syslock", "flashinfo", "reboot ro"]))
    out = [(n, m, cc, boot, []) for (n, m, cc) in s]

    def _ccd_bringup():
        # Force the source role so the force-sink board policy doesn't block SRC_ACCESSORY; with
        # ForceAccessory's both-CC-Rd this drives SRC_ACCESSORY -> ccd_set_mode(ENABLED) ->
        # usb_console_enable + usb_spi_enable + usb_init (VERIFIED reaches ccd_set_mode/usb_init/
        # ep0_rx). The 1.2s RunFor lets the DRP debounce/toggle complete before EP0 enumeration.
        return ['sysbus.usart1 WriteChar %d' % ord(c) for c in "pd 0 dualrole source\r"] + \
               ['emulation RunFor "1.2"']
    # Console line editing: raw control chars + escape sequences (post-boot monitor WriteChars)
    # -> console_handle_char branches (history/arrows/home/end/kill/backspace/DEL/bad-escape).
    out.append(("console_edit", [], [], boot, _edit_bytes()))
    # LIVE USB host-bridge in the trace: forced debug accessory brings up usb_init, then EP0
    # enumeration + SET_CONFIG + USB_SPI enable + raiden RDID -> ep_0_rx / usb_spi_* / usb_stream
    # branches. Short boot stays in the rebuilt's pre-panic / early usb_spi window.
    ep0_rx = 0x40006088                     # rebuilt EP0 rx buffer
    # Bring up usb_init FIRST (force source -> SRC_ACCESSORY -> ccd_set_mode -> usb_init), THEN
    # drive EP0 enumeration: without the bringup, SignalReset/setup_ep0 fire into an
    # uninitialised USB controller and cover nothing.
    usbq = _ccd_bringup() + ['sysbus.usb SignalReset', 'emulation RunFor "0.1"']
    usbq += usb_host.setup_ep0(ep0_rx, usb_host.GET_DEV)
    usbq += usb_host.setup_ep0(ep0_rx, usb_host.GET_CFG)
    usbq += usb_host.setup_ep0(ep0_rx, usb_host.SET_CFG)
    usbq += usb_host.setup_ep0(ep0_rx, usb_host.SPI_EN)
    usbq += usb_host.raiden_cmds(4, 0x40006188, 0x40006148, usb_host.BT + 0x26)
    out.append(("usb_live", ['sysbus.adc ForceAccessory true'], [], "1.0", usbq))
    # LIVE USB-PD: attach as sink, then inject a battery of PD messages over the modeled
    # CC-partner PD-PHY (GaleExti COMP-IRQ wake + GaleDma RX-sample feed). Each message is
    # decoded by the real pd_analyze_rx and dispatched by handle_request -> covers the
    # PD-PHY decode chain + protocol dispatch (the largest uncovered category).
    pd_pre = ['sysbus.adc ForceSourceCc true']
    pd_post = []
    for _name, msg in pd_encode.battery():
        pd_post += pd_inject.stage(msg)
    out.append(("pd_live", pd_pre, [], "2.0", _contract_post()))
    # RW variants of the heavy post-driven scenarios (sysjump rw first) -> RW coverage, which
    # otherwise lags badly (most scenarios run in RO). Addresses are identical in RO/RW.
    out.append(("console_edit_rw", [], ["sysjump rw"], boot, _edit_bytes()))
    out.append(("usb_live_rw", ['sysbus.adc ForceAccessory true'], ["sysjump rw"], "0.6", usbq))
    out.append(("pd_live_rw", pd_pre, ["sysjump rw"], "2.0", _contract_post()))
    # Flash FAULT injection -> EC_ERROR_* / WRPRTERR / PGERR / stuck-busy error paths.
    out.append(("flash_fault", [], [], boot, _fault_post()))
    out.append(("flash_fault_rw", [], ["sysjump rw"], boot, _fault_post()))
    # LIVE explicit PD contract to SNK_READY + ready-state ops (RO and RW).
    out.append(("pd_contract", pd_pre, [], "2.0", _contract_post()))
    out.append(("pd_contract_rw", pd_pre, ["sysjump rw"], "2.0", _contract_post()))
    out.append(("hostcmd", [], [], boot, hostcmd.post([])))
    out.append(("hostcmd_rw", [], ["sysjump rw"], boot, hostcmd.post([])))
    return out


def disasm_branches(elf):
    out = subprocess.run([OBJDUMP, "-d", elf], stdout=subprocess.PIPE,
                         universal_newlines=True).stdout
    insns, cond, sym = {}, {}, {}
    cur = "?"
    for ln in out.splitlines():
        fm = re.match(r'^[0-9a-f]+\s+<([^>]+)>:', ln)
        if fm:
            cur = fm.group(1); continue
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f ]+?)\s+(\S.*)$', ln)
        if not m:
            continue
        addr = int(m.group(1), 16)
        nb = len(m.group(2).replace(" ", "")) // 2
        insns[addr] = nb
        sym[addr] = cur
        cm = COND.search(m.group(3))
        if cm:
            tm = re.search(r'([0-9a-f]+)\s+<', m.group(3))
            if tm:
                cond[addr] = (addr + nb, int(tm.group(1), 16))
    return set(insns), cond, sym


def run_scenario(name, mon, cmds, boot, post=None):
    trace = os.path.join(TMP, "cov_%s.txt" % name)
    c = ['$h=@%s' % HERE, '$bin=@%s' % REBUILT, '$name="cov"', 'include @%s' % BASE] + mon
    c += ['cpu CreateExecutionTracing "tr_%s" @%s PC' % (name, trace),
          'emulation RunFor "%s"' % boot]
    for cmd in cmds:
        c += ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (cmd + "\r")]
        c.append('emulation RunFor "0.08"')
    c += (post or [])              # post-boot monitor commands (e.g. PD message injection)
    c += ['cpu DisableExecutionTracing', 'quit']
    subprocess.run(["renode", "--disable-gui", "--console", "-e", "; ".join(c)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)
    return trace


def fold_trace(path, cond, executed, taken, nottaken):
    """Stream a trace file; update executed set + per-branch taken/nottaken sets."""
    prev = None
    if not os.path.exists(path):
        return
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None; continue
            pc = int(ln, 16)
            executed.add(pc)
            if prev is not None and prev in cond:
                fall, tgt = cond[prev]
                if pc == tgt:
                    taken.add(prev)
                elif pc == fall:
                    nottaken.add(prev)
            prev = pc
    os.remove(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", default="1.5")
    args = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)

    scns = scenarios(args.boot)
    print("Running %d scenarios (each a separate traced renode run)..." % len(scns))
    traces = []
    for name, mon, cmds, boot, post in scns:
        print("  scenario: %-18s (%d cmds)" % (name, len(cmds)))
        traces.append((name, run_scenario(name, mon, cmds, boot, post)))

    executed, taken, nottaken = set(), set(), set()
    for name, elf in []:  # placeholder
        pass
    # We need cond maps per image, but executed/taken/nottaken are address sets shared
    # across images (RO 0x0800xxxx vs RW 0x0801xxxx don't overlap), so fold once with the
    # union of both cond maps.
    ro_insn, ro_cond, ro_sym = disasm_branches(RO_ELF)
    rw_insn, rw_cond, rw_sym = disasm_branches(RW_ELF)
    allcond = dict(ro_cond); allcond.update(rw_cond)
    for name, path in traces:
        fold_trace(path, allcond, executed, taken, nottaken)

    for label, all_insn, cond, sym, elf in [("RO", ro_insn, ro_cond, ro_sym, RO_ELF),
                                             ("RW", rw_insn, rw_cond, rw_sym, RW_ELF)]:
        ex = executed & all_insn
        icov = 100.0 * len(ex) / max(len(all_insn), 1)
        reached = [a for a in cond if a in executed]
        both = [a for a in cond if a in taken and a in nottaken]
        only = [a for a in reached if a not in (set(taken) & set(nottaken))]
        bcov_tot = 100.0 * len(both) / max(len(cond), 1)
        bcov_reached = 100.0 * len(both) / max(len(reached), 1)
        print("\n=== %s image (cumulative over %d scenarios) ===" % (label, len(scns)))
        print("  instructions:  %d/%d = %.1f%%" % (len(ex), len(all_insn), icov))
        print("  cond branches: %d total, %d reached, %d both-dirs covered" %
              (len(cond), len(reached), len(both)))
        print("  branch coverage: %.1f%% of total, %.1f%% of reached" % (bcov_tot, bcov_reached))
        # dump uncovered (not both-dirs) branches with containing symbol for classify.py
        uncov = sorted(a for a in cond if a not in both)
        outp = os.path.join(HERE, "cov_uncovered_%s.txt" % label)
        with open(outp, "w") as f:
            for a in uncov:
                state = ("reached-one-dir" if a in executed else "unreached")
                f.write("0x%08x %-30s %s\n" % (a, sym.get(a, "?"), state))
        print("  wrote %d uncovered branches -> %s" % (len(uncov), os.path.basename(outp)))


if __name__ == "__main__":
    main()
