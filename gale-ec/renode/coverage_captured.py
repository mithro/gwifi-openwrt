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

import coverage_full
import hostcmd   # reuse the address-independent scenario helpers (console-edit, faults, cmd args)
import rda       # validated recursive-descent disassembler -> honest branch denominator

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
           "gpioget LID_OPEN", "md 0x20000000", "flashwp", "gale",
           # hash command (command_hash, 13 unreached): no-arg status + recompute RO/RW + abort
           "hash", "hash ro", "hash rw", "hash 0x10000 0x100", "hash abort", "hash bogus"]
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


def _src_contract_post():
    """Drive gale AS SOURCE through a full source contract (the previously-mis-excused SRC states).
    With GaleAdc.PartnerSink (CC1 in the source Rd band, CC2 open) and `pd dualrole source`, gale
    enters SRC_STARTUP -> SRC_DISCOVERY and TX's Source_Caps; we deliver a sink Request (FireComp
    contract msg), and the counter-based auto-GoodCRC acks gale's own TXs (Source_Caps/Accept/
    PS_RDY), driving SRC_NEGOCIATE -> SRC_ACCEPTED -> SRC_TRANSITION -> SRC_READY. Then exercise
    ready-state requests so the source ready-state handlers run."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    def fire(t):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c = ['sysbus.dma1 ClearResponses']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    c += cc("pd dualrole source") + ['emulation RunFor "1.2"']   # -> SRC_DISCOVERY (TX Source_Caps)
    # Deliver the sink Request, then Get_Sink_Cap-ack window; gale's Accept/PS_RDY auto-GoodCRC'd.
    for m in (pd_encode.REQUEST(2), pd_encode.REQUEST(3)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire("0.3")
    # SRC_READY: drive ready-state requests the source responds to (Get_Source_Cap / VDM / swaps).
    mid = 4
    for t in (7, 8, 9, 10, 11, 5, 2):    # GET_SRC_CAP GET_SNK_CAP DR_SWAP PR_SWAP VCONN_SWAP PING GOTO_MIN
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.ctrl(t, mid))] + fire("0.1"); mid += 1
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
    # SOURCE contract (gale forced source + sink partner) -> SRC_STARTUP..SRC_READY + source
    # ready-state handlers (the previously-mis-excused source-role states). RO + RW.
    s.append(("src", ['sysbus.adc PartnerSink true'], [], "1.5", _src_contract_post()))
    s.append(("src_rw", ['sysbus.adc PartnerSink true'], ["sysjump rw"], "1.5", _src_contract_post()))
    s.append(("rw", [], ["sysjump rw"] + RO_CMDS, boot, []))
    for c in CRASH:
        s.append(("crash_" + c.split()[1], [], [c], boot, []))
        s.append(("crashrw_" + c.split()[1], [], ["sysjump rw", c], boot, []))
    # AP host commands (address-independent injector) — RO and RW
    hc = hostcmd.post([])
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


# Hard per-process RSS ceiling for each renode (mono) instance via a transient systemd cgroup
# scope. RLIMIT_AS is unusable here — mono reserves tens of GB of *virtual* space, so an address-
# space cap kills it even at modest real usage; MemoryMax caps actual resident memory and the
# cgroup OOM-kills only if the run genuinely exceeds it. One gale machine + a file-streamed trace
# sits well under 2.5 GiB. Override with RENODE_MEM_MAX (systemd size, e.g. "3G").
RENODE_MEM_MAX = os.environ.get("RENODE_MEM_MAX", "2500M")


def _renode_cmd(monitor_script):
    base = ["renode", "--disable-gui", "--console", "-e", monitor_script]
    # Prefer a cgroup RSS cap; fall back to bare renode if systemd-run is unavailable.
    if _HAVE_SYSTEMD_RUN:
        return ["systemd-run", "--user", "--scope", "-q",
                "-p", "MemoryMax=%s" % RENODE_MEM_MAX, "-p", "MemorySwapMax=0"] + base
    return base


def _have_systemd_run():
    try:
        return subprocess.run(["systemd-run", "--user", "--scope", "-q", "true"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=20).returncode == 0
    except Exception:
        return False


_HAVE_SYSTEMD_RUN = _have_systemd_run()


def run_scenario(name, mon, cmds, boot, post, binpath):
    trace = os.path.join(TMP, "cap_%s.txt" % name)
    c = ['$h=@%s' % HERE, '$bin=@%s' % binpath, '$name="cap"', 'include @%s' % BASE] + mon
    c += ['cpu CreateExecutionTracing "tr_%s" @%s PC' % (name, trace), 'emulation RunFor "%s"' % boot]
    for cmd in cmds:
        c += ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (cmd + "\r")]
        c.append('emulation RunFor "0.06"')
    c += (post or [])
    c += ['cpu DisableExecutionTracing', 'quit']
    # Single renode at a time (no parallelism), RSS-capped via a transient systemd scope.
    subprocess.run(_renode_cmd("; ".join(c)),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=900)
    return trace


def fold_edges(path, executed, edges):
    """Pass 1: collect executed PCs and the set of directed control-flow edges (prev -> pc) from
    a trace. We do NOT need the branch map yet — the rda denominator is built afterward, seeded by
    `executed`, then taken/not-taken are derived from `edges`. Edges are deduplicated, so memory is
    bounded by the number of distinct transitions, not trace length."""
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
            if prev is not None:
                edges.add((prev, pc))
            prev = pc
    os.remove(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=CAPTURED)
    ap.add_argument("--boot", default="2.0")
    ap.add_argument("--reuse", action="store_true",
                    help="reuse cached executed/edges from the last run (skip renode) — for fast "
                         "re-analysis after denominator/reporting changes")
    args = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)
    binpath = os.path.abspath(args.bin)
    scns = scenarios(args.boot)
    cache = os.path.join(TMP, "cap_trace_cache.pkl")
    print("CAPTURED firmware coverage: %s (%d scenarios)" % (os.path.basename(binpath), len(scns)))

    # Pass 1: run every scenario, collecting executed PCs + control-flow edges (or reuse the cache).
    executed, edges = set(), set()
    if args.reuse and os.path.exists(cache):
        import pickle
        with open(cache, "rb") as f:
            executed, edges = pickle.load(f)
        print("  reusing cached trace: %d executed PCs, %d edges" % (len(executed), len(edges)))
    else:
        # SERIAL: one renode at a time (keeps peak memory low — no concurrent VM instances). Each
        # renode process is additionally memory-capped (see run_scenario).
        for (n, m, c, b, p) in scns:
            print("  scenario: %-16s" % n)
            fold_edges(run_scenario(n, m, c, b, p, binpath), executed, edges)
        import pickle
        with open(cache, "wb") as f:
            pickle.dump((executed, edges), f)

    # HONEST, FIXED denominator: recursive-descent disassembly (rda, validated 0-FP/0-FN vs the
    # rebuilt ELF) seeded by the vector table, EVERY function-pointer-table target, AND every
    # executed PC. Seeding with the pointer-table targets (DECLARE_HOST_COMMAND / CONSOLE / HOOK /
    # task list) makes the denominator COMPLETE and STABLE — it counts the branches inside
    # functions the suite has not yet entered, so the total does not grow as coverage improves.
    # No flat-disasm phantom branches.
    seeds = set(executed) | rda.ptr_targets(binpath)
    insns, cond, calls = rda.analyze(binpath, extra_seeds=seeds)
    taken = set(a for a in cond if (a, cond[a][1]) in edges)         # branch -> target edge seen
    nottaken = set(a for a in cond if (a, cond[a][0]) in edges)      # branch -> fall-through seen

    reached = [a for a in cond if a in executed]
    both = [a for a in cond if a in taken and a in nottaken]
    ex = executed & insns
    print("\n=== CAPTURED firmware (rda denominator) ===")
    print("  instructions: %d executed / %d in recursive-descent code" % (len(ex), len(insns)))
    print("  cond branches: %d total (rda), %d reached, %d both-dirs covered" %
          (len(cond), len(reached), len(both)))
    print("  branch coverage: %.1f%% of total, %.1f%% of reached both-dirs" %
          (100.0 * len(both) / max(len(cond), 1), 100.0 * len(both) / max(len(reached), 1)))

    # Every uncovered branch (unreached, or reached one-direction-only) with its state, for the
    # grind / exclusion-justification analysis.
    uncov = sorted(a for a in cond if a not in (taken & nottaken))
    with open(os.path.join(HERE, "cap_uncovered.txt"), "w") as f:
        for a in uncov:
            if a not in executed:
                st = "unreached"
            elif a in taken:
                st = "taken-only"
            elif a in nottaken:
                st = "nottaken-only"
            else:
                st = "reached-nofold"
            f.write("0x%08x %s\n" % (a, st))
    print("  wrote %d uncovered branches -> cap_uncovered.txt" % len(uncov))

    # Completeness pass: function-pointer-table targets the suite never entered (dead-code
    # candidates to drive or justify) — the union check the goal demands ("no dead code").
    ptrs = rda.ptr_targets(binpath)
    never = sorted(p for p in ptrs if p not in executed)
    with open(os.path.join(HERE, "cap_unentered_funcs.txt"), "w") as f:
        for p in never:
            f.write("0x%08x\n" % p)
    print("  pointer-table targets never entered: %d -> cap_unentered_funcs.txt" % len(never))


if __name__ == "__main__":
    main()
