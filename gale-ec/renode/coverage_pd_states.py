#!/usr/bin/env python3
"""Stateful-campaign lever #4 — drive PD-policy/console paths the main campaign never stimulates,
to reach the dual-role-config + PD-info branch cluster around 0x8007f8e/0x8017f8e that direct
function invocation structurally cannot cover (those functions block / are state-gated).

Concretely: the main campaign only ever issues `pd dualrole source`. The dispatch at 0x8007f8e is
`pd_set_dual_role` keyed on PD_DRP_* (TOGGLE_ON=0, TOGGLE_OFF=1, FORCE_SINK=2, FORCE_SOURCE=3), so
the on/off/sink/toggle cases are never reached. This driver sweeps every dual-role mode plus the PD
console-info / try-source / comm / ping paths, on BOTH the RO image and after `sysjump rw`.

Accumulating + independent: writes tmp/pdstate_edges.pkl, unioned by combine_coverage.py alongside
the campaign/sweep/fuzz pkls. Genuine execution of the real captured firmware via the console — no
faked branches. Serial + memory-capped (reuses coverage_captured.run_scenario).
"""
import os
import pickle

import coverage_captured as C

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin")
TMP = os.path.join(HERE, "tmp")


def _cc(line):
    """Type a console command (chars + CR) over usart1, then let it run briefly."""
    return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (line + "\r")] + \
           ['emulation RunFor "0.03"']


def _pd_console_post():
    """Sweep dual-role modes (all 4 PD_DRP_* cases) + PD info/try-src/comm/ping console paths."""
    c = []
    for line in ("pd dualrole on", "pd dualrole off", "pd dualrole sink",
                 "pd dualrole toggle", "pd dualrole source", "pd dualrole",
                 "pd 0 state", "pd 0 flags", "pd 0 dump 1", "pd 0 dump 0",
                 "pd trysrc 1", "pd trysrc 0", "pd 0 tx", "pd 0 charger",
                 "pd 0 comm on", "pd 0 comm off", "pd 0 ping on", "pd 0 ping off",
                 "pd 0 vdm 1", "pd 0 vdm 2", "pd 0 bist", "pd version"):
        c += _cc(line)
    return c


def _pd_bist_post():
    """Reach contract, then in SNK_READY inject message types the main campaign never sends: BIST
    (data type 3, Carrier-Mode-2 and Test-Data) -> BIST_RX/BIST_TX states; unexpected data messages
    (Request/Source_Cap variants) -> the 'unexpected message in state' branches; then several
    hard-reset -> recover cycles to flip HARD_RESET_SEND/EXECUTE/RECOVER both directions."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pd_encode.ACCEPT(i)))]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    def fire(t):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c += fire("0.2") + fire("0.3")
    mid = 6
    msgs = []
    # BIST data message (type 3): one data object, mode in bits[31:28]. Carrier Mode 2 = 5, Test Data = 8.
    for mode in (5, 8):
        msgs.append((pd_encode.header(3, 1, mid), [mode << 28])); mid += 1
    # Unexpected-in-state data messages: a sink Request and a second Source_Cap arriving at a SINK.
    msgs.append(pd_encode.REQUEST(mid)); mid += 1
    msgs.append((pd_encode.header(1, 1, mid), [0x2201912C, 0x0002D12C])); mid += 1   # 2-PDO Source_Cap
    # Unstructured VDM (bit15=0) + a wrong-SVID structured VDM -> svdm reject/null paths.
    msgs.append((pd_encode.header(15, 1, mid), [0x12340000])); mid += 1
    msgs.append((pd_encode.header(15, 1, mid), [(0x1234 << 16) | (1 << 15) | 1])); mid += 1
    for m in msgs:
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire("0.1")
    # hard-reset -> recover cycles
    def cc(line):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (line + "\r")]
    for _ in range(3):
        c += cc("pd 0 hard") + ['emulation RunFor "0.25"'] + fire("0.2")
    return c


def _attach_cycle_post():
    """Toggle CC attach/detach repeatedly. Every existing scenario sets ONE CC state and HOLDS it,
    so the connection-detection branches (SNK_DISCONNECTED <-> _DEBOUNCE <-> connect; SRC likewise;
    accessory attach/detach) only ever see one direction. Cycling attach->detach->reattach across
    sink-attach / source-partner / debug-accessory flips those transition guards both ways."""
    c = []
    def settle(t="0.18"):
        return ['emulation RunFor "%s"' % t]
    for knob in ("ForceSourceCc", "PartnerSink", "ForceAccessory"):
        for _ in range(3):
            c += ['sysbus.adc %s true' % knob] + settle()
            c += ['sysbus.adc %s false' % knob] + settle()
        # one extra short on/off to catch the mid-debounce abort (detach before cc_debounce expires)
        c += ['sysbus.adc %s true' % knob, 'emulation RunFor "0.02"',
              'sysbus.adc %s false' % knob] + settle("0.12")
    return c


def _hostcmd_sweep_post():
    """Drive host_command_process for EVERY command number across the EC_CMD range. Hits the
    never-entered DECLARE_HOST_COMMAND handlers (each unique cmd number routes to its handler) AND
    both directions of the command-lookup guard (valid -> handler, invalid -> EC_RES_INVALID_COMMAND).
    A few common commands also get a small data payload + alt versions to flip in-handler arg guards."""
    import hostcmd
    c = []
    # broad enumeration: every command id 0x00..0x9F, empty data, default version
    for cmd in range(0x00, 0xA0):
        c += ['sysbus.i2c1 HostCmd "%s"' % hostcmd._pkt(cmd, 0, 3, []), 'emulation RunFor "0.02"']
    # a handful with payloads / alt versions to exercise in-handler branches
    le = hostcmd._le32
    extras = [
        (0x0001, 0, le(0x11223344)),     # HELLO with data
        (0x0008, 0, []),                 # GET_VERSION
        (0x000b, 0, [1]),                # GET_CHIP_INFO / proto-info variants
        (0x0040, 0, le(0)),             # USB_PD_CONTROL-ish range
        (0x0101, 0, le(0)),             # extended range
    ]
    for cmd, ver, data in extras:
        c += ['sysbus.i2c1 HostCmd "%s"' % hostcmd._pkt(cmd, ver, 3, data), 'emulation RunFor "0.03"']
    return c


def _hook_post():
    """Fire periodic + event hooks the short scenarios never reach. Most never-entered functions are
    DECLARE_HOOK handlers: HOOK_TICK/HOOK_SECOND fire on a timer, so a long idle run executes their
    deferred routines; interleave console pokes so SECOND-aligned handlers (battery/charge/PD keepalive)
    run several times and flip their periodic guards both directions."""
    c = []
    for _ in range(8):                       # ~8 'seconds' of run -> many HOOK_SECOND/TICK cycles
        c += ['emulation RunFor "1.0"',
              'sysbus.usart1 WriteChar 13']  # a bare CR each second (console keepalive path)
    return c


def _sysjump_both_post():
    """Fire HOOK_SYSJUMP in BOTH directions (RO->RW and RW->RO) so the sysjump-save/restore handlers
    and the jumped-from/jumped-to branches both execute. The main campaign only does RO->RW."""
    def cc(line):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (line + "\r")] + \
               ['emulation RunFor "0.3"']
    return cc("sysjump rw") + cc("sysjump ro") + cc("sysjump rw") + cc("reboot ap-off") + \
           ['emulation RunFor "0.5"']


def _vdm_sweep_post():
    """Sweep the VDM-dispatch fields the 0x8007f8e PD-policy block decodes from a received VDO:
    bit15 = structured/unstructured, bits[7:6] = command type (REQ/ACK/NAK/BUSY), bits[4:0] = command.
    The main campaign only sends structured REQ VDMs, so the unstructured + ACK/NAK/BUSY branches
    (0x8008016/24/28/30/32 ...) stay unreached. Establish a contract, then deliver every combination
    in SNK_READY so pd_svdm / handle_vdm walk each dispatch arm."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    def fire(t="0.08"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c += fire("0.2") + fire("0.3")
    mid = 6
    for svid in (0xFF00, 0x1234):                  # gale SVID + a foreign SVID (reject path)
        for struct in (1, 0):                      # structured / unstructured
            for ctype in (0, 1, 2, 3):             # REQ / ACK / NAK / BUSY
                for cmd in (1, 2, 3, 4, 5, 6, 7):  # Disc Id/SVIDs/Modes/Enter/Exit/Attention/...
                    vdo = (svid << 16) | (struct << 15) | (ctype << 6) | cmd
                    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg((pd_encode.header(15, 1, mid), [vdo]))]
                    c += fire("0.04"); mid = (mid + 1) & 7 or 1
    return c


def _dfp_vdm_post():
    """Drive gale's DFP VDM discovery: as SOURCE (=DFP) it initiates Disc-Identity; the (now
    VDM-aware) partner ACKs each query from slots 9..12, walking gale through Disc-Identity ->
    Disc-SVIDs -> Disc-Modes -> Enter-Mode, exercising the pd_dfp_*/svdm response-processing arms in
    the 0x8007f8e PD-policy block (the structured-ACK branches the REQ-only sweep can't reach)."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(line):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (line + "\r")]
    def fire(t="0.1"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    # VDM ACK replies (slot 9..12): structured ACK (bit15=1, bits7:6=01), echoing the cmd gale sent.
    def ack(cmd, svid, extra):
        vdm = (svid << 16) | (1 << 15) | (1 << 6) | cmd
        return (pd_encode.header(15, 1 + len(extra), 0), [vdm] + extra)
    c += ['sysbus.dma1 SetReply 9 "%s"'  % hexmsg(ack(1, 0xFF00, [0x00000000, 0, 0]))]   # Disc Id
    c += ['sysbus.dma1 SetReply 10 "%s"' % hexmsg(ack(2, 0xFF00, [0xFF010000]))]          # Disc SVIDs
    c += ['sysbus.dma1 SetReply 11 "%s"' % hexmsg(ack(3, 0xFF01, [0x00000001]))]          # Disc Modes
    c += ['sysbus.dma1 SetReply 12 "%s"' % hexmsg(ack(4, 0xFF01, []))]                    # Enter Mode
    # gale as source = DFP; staged sink Request completes the source contract, then it discovers.
    c += cc("pd dualrole source") + ['emulation RunFor "1.2"']
    for m in (pd_encode.REQUEST(2), pd_encode.REQUEST(3)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)] + fire("0.3")
    # explicit VDM kicks too (in case auto-discovery is gated off), each ACK'd by the partner
    for line in ("pd 0 vdm version", "pd 0 vdm info", "pd 0 vdm 2", "pd 0 vdm 3"):
        c += cc(line) + fire("0.15") + fire("0.15")
    return c


def _fault_extreme_post():
    """Drive the error/protection edges of validation checks whose success edge the normal campaign
    already covers: sweep the ADC VBUS/CURRENT raw value across extremes (0, mid, full-scale) while
    the firmware runs (so charge_manager / pd_is_vbus_present / OVP-OCP polling reads them), and
    interleave the CC partner states so vbus-present is evaluated under attach. Each value held for a
    few SECOND/TICK cycles so the periodic readers latch it both ways."""
    c = []
    for raw in (0, 1, 100, 800, 1500, 2048, 3000, 4095):
        c += ['sysbus.adc ForceRaw %d' % raw, 'sysbus.adc PartnerSink true',
              'emulation RunFor "0.4"',
              'sysbus.adc PartnerSink false', 'sysbus.adc ForceSourceCc true',
              'emulation RunFor "0.4"', 'sysbus.adc ForceSourceCc false']
    c += ['sysbus.adc ForceRaw -1']
    return c


def _pd_inject_post():
    """Live PD-state injection: pd[0] is at 0x20001150 (task_state at offset 0). The dispatcher
    pd_task can't be direct-called (it blocks), but writing task_state=N then letting the periodic
    pd_task run makes it execute state N's case -> covers each state's dispatcher branch. Sweep all
    states 0..40, with a CC partner attached so state handlers that read CC proceed. Re-arm the PD
    task event each step (write the event-pending bit) so the task wakes and processes the state."""
    c = ['sysbus.adc PartnerSink true', 'emulation RunFor "1.0"']
    for st in range(0, 41):
        c += ['sysbus WriteByte 0x20001150 %d' % st,        # pd[0].task_state = st
              'emulation RunFor "0.04"']
    # again under ForceSourceCc (sink-attach) so source-side states see a partner
    c += ['sysbus.adc PartnerSink false', 'sysbus.adc ForceSourceCc true', 'emulation RunFor "0.3"']
    for st in range(0, 41):
        c += ['sysbus WriteByte 0x20001150 %d' % st, 'emulation RunFor "0.04"']
    return c


def _vdm_busy_post():
    """Cover pd_vdm's VDM_STATE_BUSY(2) + timeout branches: establish a contract (so VDM TX succeeds
    via auto-GoodCRC), then trigger a gale DFP VDM (`pd 0 vdm ...`) but give NO VDM response, so
    vdm_state goes READY->BUSY and pd_vdm runs the BUSY case across several pd_task ticks until the
    VDM timeout (-> ERR_TMOUT). The reactive partner GoodCRCs gale's TX but does NOT answer the VDM."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(line):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (line + "\r")]
    def fire(t="0.1"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):                                   # GoodCRC gale's TX (so VDM send succeeds)
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    # ACCEPT gale's auto-initiated DR/PR/VCONN swaps so it STAYS in SNK_READY (else it DR_SWAPs from
    # READY (st27), the partner never answers -> hard-reset cycle (st33/34) and the VDM can't sit BUSY).
    for i in range(8):
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pd_encode.ACCEPT(i)))]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    c += fire("0.2") + fire("0.2") + fire("0.2")         # -> SNK_READY, swaps auto-accepted -> stable
    # trigger gale DFP VDMs; NO VDM reply staged -> each sits BUSY then times out
    for line in ("pd 0 vdm version", "pd 0 vdm info", "pd 0 vdm 12345678", "pd 0 vdm deadbeef"):
        c += cc(line) + fire("0.05")
        c += ['emulation RunFor "0.6"']                  # > PD_T_VDM (let BUSY run + time out)
    return c


def _vdm_waitbusy_post():
    """Cover VDM_STATE_WAIT_RSP_BUSY(3): same as above but the partner answers gale's VDM with a
    CMDT_RSP_BUSY response (cmd-type bits[7:6]=01? no -> BUSY type) so handle_vdm_request sets
    WAIT_RSP_BUSY. CMDT_RSP_BUSY = 3 in bits[7:6] of the VDO."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(line):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (line + "\r")]
    def fire(t="0.1"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    c += fire("0.2") + fire("0.2")
    mid = 5
    for line in ("pd 0 vdm version", "pd 0 vdm info"):
        c += cc(line) + ['emulation RunFor "0.04"']
        # partner answers with a BUSY VDM (cmd-type=BUSY=3 in bits[7:6]); SVID Google, structured
        vdo = (0xFF00 << 16) | (1 << 15) | (3 << 6) | 1
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg((pd_encode.header(15, 1, mid), [vdo]))]
        c += fire("0.15") + ['emulation RunFor "0.3"']; mid += 1
    return c


def _state_inject_post():
    """Cover pd_task's per-state switch handlers the EC unit-test way: set pd[0].task_state
    (offset 6 = 0x20001156) and pd[0].vdm_state (offset 72 = 0x20001198) to each VALID protocol
    value, then run pd_task so the REAL handler for that state executes and branches on real data.
    This is state-SETUP (a valid input), not branch-outcome faking — the switch genuinely reads the
    injected value. Sweep every task_state 0..40 and vdm_state {1,2,3} so each case body runs."""
    TS, VDM = 0x20001156, 0x20001198
    c = []
    for st in range(0, 41):
        c += ['sysbus WriteByte 0x%X %d' % (TS, st), 'emulation RunFor "0.04"']
        for v in (2, 3, 1):                       # exercise vdm_state cases within this task_state
            c += ['sysbus WriteByte 0x%X %d' % (VDM, v),
                  'sysbus WriteByte 0x%X %d' % (TS, st), 'emulation RunFor "0.02"']
    return c


def _state_inject2_post():
    """Flip the per-state handlers' INTERNAL sub-branches: for each task_state, vary the fields the
    handler reads — cc_state (offset 40 = 0x20001178), flags (offset 2 = 0x20001152, u16) — so the
    in-handler if/else guards (cc checks, PD_FLAGS_* checks) flip both directions. EC unit-test style:
    valid struct inputs, real handler branches."""
    TS, CC, FL = 0x20001156, 0x20001178, 0x20001152
    def w16(addr, v):
        return ['sysbus WriteByte 0x%X %d' % (addr, v & 0xFF),
                'sysbus WriteByte 0x%X %d' % (addr + 1, (v >> 8) & 0xFF)]
    c = []
    combos = [(0, 0x0000), (1, 0x0000), (2, 0x0000), (3, 0x0000), (4, 0x0000),
              (0, 0xFFFF), (1, 0x0080), (2, 0x018e), (0, 0x0100), (1, 0x4000)]
    for st in range(0, 41):
        for cc, fl in combos:
            c += ['sysbus WriteByte 0x%X %d' % (CC, cc)]
            c += w16(FL, fl)
            c += ['sysbus WriteByte 0x%X %d' % (TS, st), 'emulation RunFor "0.015"']
    return c


def _state_inject3_post():
    """Flip the per-state handler sub-branches that read pd[0] struct offsets 0x50 (u32) and 0x58
    (u16, bit15 tested) — e.g. 0x08008016 (bpl on bit15 of +0x58), 0x08008072/0x080080ae (cmp +0x50)
    — which the cc_state/flags sweep (_state_inject2) never sets. pd[0]=0x20001150 so +0x50=0x200011a0,
    +0x58=0x200011a8. Pair with flags so the contract-flag guards also flip. EC unit-test style: real
    handler branches on valid injected struct data."""
    TS, FL = 0x20001156, 0x20001152
    O50, O58 = 0x200011a0, 0x200011a8
    def w16(addr, v):
        return ['sysbus WriteByte 0x%X %d' % (addr, v & 0xFF),
                'sysbus WriteByte 0x%X %d' % (addr + 1, (v >> 8) & 0xFF)]
    def w32(addr, v):
        return ['sysbus WriteDoubleWord 0x%X 0x%X' % (addr, v & 0xFFFFFFFF)]
    # (o50, o58, flags): span the +0x50 compare, +0x58 bit15, and contract/role flags
    combos = [(0x00000000, 0x0000, 0x0000), (0xFFFFFFFF, 0x8000, 0x0040),
              (0x00010000, 0xFFFF, 0x0440), (0x00000001, 0x4000, 0x1000),
              (0x7FFFFFFF, 0x0001, 0x0200), (0x00000000, 0x0080, 0x004a)]
    c = []
    for st in range(0, 41):
        for o50, o58, fl in combos:
            c += w32(O50, o50) + w16(O58, o58) + w16(FL, fl)
            c += ['sysbus WriteByte 0x%X %d' % (TS, st), 'emulation RunFor "0.015"']
    return c


def _msg_battery_post():
    """Drive the pd_task message-type DISPATCH branches (cmp on control type 6/7/0xa/0xc/0xd ... and
    data-msg handling) by delivering EVERY PD message type to gale in a live SNK contract, one at a
    time through the reactive partner so the firmware's REAL RX path parses each (populating the
    sp+0x4c/sp+0x30 locals the uncovered sub-branches read). Genuine protocol execution — the partner
    delivers a validly-encoded message and gale's handler branches on it. Modeled on the proven
    _vdm_sweep delivery (ExpectContractMsg + FireComp x3 + RunFor keeps partner FIFO sync)."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
    # establish a contract so gale sits in SNK_READY and accepts unsolicited messages
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    def fire(t="0.06"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    c += fire("0.2") + fire("0.3")
    mid = 3
    # every CONTROL message type (PD spec 1..21): GoodCRC/Accept/Reject/Ping/PS_RDY/Get_Source_Cap/
    # Get_Sink_Cap/DR_Swap/PR_Swap/VCONN_Swap/Wait/Soft_Reset/.../Not_Supported/Get_Status/FR_Swap...
    for ct in range(1, 22):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.ctrl(ct, mid))]
        c += fire("0.05"); mid = (mid + 1) & 7 or 1
    # DATA messages: Source_Cap (multi-PDO), Request, BIST, Sink_Cap, Battery_Status, Alert, Vendor
    pdos = [0x22019096, 0x0002D12C, 0x0003C12C]    # 5V/1.5A, 9V/3A, 12V/3A fixed
    data_msgs = [(pd_encode.header(1, 3, mid), pdos),            # Source_Cap, 3 PDOs
                 pd_encode.REQUEST(mid, 2, 300),                 # Request PDO#2
                 (pd_encode.header(3, 1, mid), [0x00000000]),    # BIST
                 (pd_encode.header(4, 1, mid), [0x2701912C]),    # Sink_Cap
                 (pd_encode.header(5, 1, mid), [0x00000000]),    # Battery_Status
                 (pd_encode.header(6, 1, mid), [0x00000001]),    # Alert
                 (pd_encode.header(15, 1, mid), [0xFF008001])]   # Vendor/VDM
    for m in data_msgs:
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
        c += fire("0.05")
    # role-swap headers (prole/drole flipped) to hit the role-check branches
    for prole, drole in ((0, 0), (0, 1), (1, 0)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg((pd_encode.header(9, 0, mid, prole, drole), []))]
        c += fire("0.05")
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg((pd_encode.header(10, 0, mid, prole, drole), []))]
        c += fire("0.05")
    return c


def _pd_cmds():
    """Full PD console-command battery to drive the state machine through SRC / swap / hard-reset /
    BIST / try-source states that the passive SNK campaign never enters (the unreached pd_task arms,
    task_state ~0/1/3/5/26). The CAPTURED firmware handles these (only the rebuilt crashes on SRC,
    divergence #8 = emulation timing). Issued with a sink partner so role transitions actually fire."""
    return ['pd dualrole on', 'pd 0 state', 'pd dualrole source', 'pd 0 state',
            'pd 0 swap data', 'pd 0 state', 'pd 0 swap power', 'pd 0 swap vconn',
            'pd trysrc 1', 'pd 0 state', 'pd 0 tx', 'pd 0 bist', 'pd 0 ping',
            'pd 0 hardreset', 'pd 0 state', 'pd 0 softreset', 'pd 0 state',
            'pd dualrole toggle', 'pd dualrole sink', 'pd 0 state',
            'pd trysrc 0', 'pd dualrole off', 'pd 0 state']


def _pd_local_states_post():
    """Reach the LOCAL pd_task states needing NO partner handshake: DISABLED(0)/SUSPENDED(1) via
    pd disable/enable, and DEBOUNCE(3)/disconnect via CC attach<->detach cycling (debounce window).
    These transitions are gale-internal (CC level + console), so they're reliably reachable without
    the reactive-partner timing the swap/reset states need."""
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    c = []
    for _ in range(4):                                                  # attach->debounce->detach arms
        c += ['sysbus.adc ForceSourceCc true', 'emulation RunFor "0.02"']
        c += ['sysbus.adc ForceSourceCc false', 'emulation RunFor "0.004"']   # quick detach = debounce abort
        c += ['sysbus.adc ForceSourceCc true', 'emulation RunFor "0.15"']      # full attach
        c += ['sysbus.adc ForceSourceCc false', 'emulation RunFor "0.12"']     # detach
    for action in ("pd 0 disable", "pd 0 state", "pd 0 enable", "pd 0 state",
                   "pd 0 disable", "pd dualrole on", "pd 0 enable", "pd 0 state"):
        c += cc(action) + ['emulation RunFor "0.08"']
    c += ['sysbus.adc ForceSourceCc false', 'emulation RunFor "0.05"']
    c += cc("pd 0 disable") + ['emulation RunFor "0.05"']
    c += cc("pd 0 enable") + ['emulation RunFor "0.05"']
    c += ['sysbus.adc ForceSourceCc true', 'emulation RunFor "0.2"']
    return c


def _pd_swap_post():
    """Drive DR/PR/VCONN swap + soft-reset handshakes to COMPLETION so pd_task's swap/reset states
    run. KEY FIX vs prior scenarios: after a swap TX, fire COMPs WITHOUT ExpectContractMsg, so the
    RX delivery falls through to pendingGoodCrc (the GoodCRC gale awaits) then the reactive Accept
    in replyQueue — ExpectContractMsg would instead force a queued contract msg and break the
    handshake. GoodCrcMsgIdAddress = &pd[0].msg_id (0x20001154) so GoodCRC ids track gale exactly."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    sink_cap = (pd_encode.header(4, 1, 0), [0x2601912C])
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pd_encode.ACCEPT(i)))]
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg(sink_cap)]
    # establish contract (needs ExpectContractMsg so the staged SRC_CAP/Accept/PS_RDY deliver)
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    def fire_contract(t):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    def fire_swap(t):                                  # NO ExpectContractMsg -> GoodCRC then Accept
        f = []
        for _ in range(4):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]
    c += fire_contract("0.2") + fire_contract("0.3")
    # swap/reset actions from SNK_READY; each followed by GoodCRC+Accept delivery (no contract force)
    for action in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn", "pd 0 soft",
                   "pd 0 swap data", "pd 0 swap power"):
        c += cc(action) + ['emulation RunFor "0.03"'] + fire_swap("0.12") + fire_swap("0.12")
    c += cc("pd 0 hard") + ['emulation RunFor "0.3"']
    return c


def _soak_post(secs, contract=False):
    """Long emulated-time soak with execution tracing on, to fire the TIME-BASED branches a 2s boot
    never reaches: HOOK_SECOND / HOOK_TICK periodic hooks, watchdog pet, deferred-call timeouts, PD
    state timeouts (source-cap / sender-response / hard-reset, 100s of ms), retry backoffs. Idle time
    is cheap (CPU WFIs until the next interrupt), so a long soak is feasible AND fires these handlers.
    With contract=True, establish a SNK contract first so SNK_READY periodic maintenance runs."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = []
    if contract:
        c += ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
              'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
        for i in range(8):
            c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
            c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pd_encode.ACCEPT(i)))]
        for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
            c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
        for _ in range(2):
            c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.2"']
    # soak in chunks so periodic hooks at different phases all fire
    for _ in range(int(secs // 5)):
        c += ['emulation RunFor "5"']
    return c


def _partner_initiated_post():
    """Drive gale's RECEIVE-side PD handlers: the partner SENDS messages gale must RESPOND to (vs
    gale initiating). Each message is delivered (ExpectContractMsg+COMP), gale processes and TXs its
    response (Accept/Reject/Source_Cap/Sink_Cap/...) setting pendingGoodCrc, then a bare COMP delivers
    the GoodCRC for gale's response so the exchange completes -> the receive-handler + response-path +
    post-exchange state branches all run. This is the half of the PD protocol the gale-initiated
    scenarios never exercise."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    sink_cap = (pd_encode.header(4, 1, 0), [0x2601912C])
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pd_encode.ACCEPT(i)))]
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg(sink_cap)]
    for m in (pd_encode.SRC_CAP, pd_encode.ACCEPT(1), pd_encode.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]

    def deliver(t="0.05"):                              # contract-delivery of a partner msg
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]

    def goodcrc(t="0.05"):                              # deliver GoodCRC for gale's response (no contract-force)
        f = []
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]

    c += deliver("0.2") + deliver("0.3")                # establish contract first
    mid = 3
    # control messages the partner sends that gale must RESPOND to
    pdos = [0x22019096, 0x0002D12C, 0x0003C12C]
    msgs = [pd_encode.ctrl(7, mid), pd_encode.ctrl(8, mid + 1),       # Get_Source_Cap / Get_Sink_Cap
            pd_encode.ctrl(9, mid + 2), pd_encode.ctrl(10, mid + 3),  # DR_Swap / PR_Swap
            pd_encode.ctrl(11, mid + 4), pd_encode.ctrl(13, mid + 5), # VCONN_Swap / Soft_Reset
            pd_encode.ctrl(4, mid + 6), pd_encode.ctrl(12, mid + 7),  # Reject / Wait
            pd_encode.ctrl(5, mid),                                   # Ping
            (pd_encode.header(1, 3, mid + 1), pdos),                  # Source_Cap -> gale Requests
            (pd_encode.header(16, 0, mid + 2), []),                   # Not_Supported
            (pd_encode.header(15, 1, mid + 3), [0xFF008001])]         # Vendor/VDM
    # extended/status messages + BIST + repeated/role-varied + malformed
    for ct in (17, 18, 19, 20, 21, 14, 15, 6, 3):       # Get_Src_Cap_Ext/Get_Status/FR_Swap/...
        msgs.append(pd_encode.ctrl(ct, mid))
    msgs.append((pd_encode.header(3, 1, mid), [0x00000000]))   # BIST data msg
    msgs.append((pd_encode.header(4, 1, mid), [0x2701912C]))   # partner Sink_Cap
    msgs.append((pd_encode.header(5, 1, mid), [0x00000000]))   # Battery_Status
    # partner in the opposite power/data role (role-mismatch receive branches)
    for prole, drole in ((0, 0), (1, 1), (0, 1)):
        msgs.append((pd_encode.header(9, 0, mid, prole, drole), []))   # DR_Swap, varied roles
        msgs.append((pd_encode.header(10, 0, mid, prole, drole), []))  # PR_Swap, varied roles
    for m in msgs:
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
        c += deliver("0.05") + goodcrc("0.08")          # deliver msg, let gale respond, GoodCRC it
        mid = (mid + 1) & 7 or 1
    # second round: re-establish + repeated swaps (swap then swap-back) to drive role-toggle states
    for _ in range(2):
        for ct in (9, 10, 11, 9, 10, 11):
            c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.ctrl(ct, mid))]
            c += deliver("0.04") + goodcrc("0.06")
            mid = (mid + 1) & 7 or 1
    return c


def _partinit_src_post():
    """Same partner-initiated receive-handler drive, but with gale AS SOURCE (PartnerSink + `pd
    dualrole source`): exercises the SOURCE-side receive handlers (handle_*_request in SRC_READY,
    Get_Sink_Cap response, source-side DR/PR/VCONN swap, source Soft_Reset) — distinct code from the
    sink-side paths partinit covers."""
    import pd_encode
    def hexmsg(m):
        sm = pd_encode.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pd_encode.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pd_encode.ACCEPT(i)))]
    def deliver(t="0.05"):
        f = ['sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000005"']
        return f + ['emulation RunFor "%s"' % t]
    def goodcrc(t="0.06"):
        f = []
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]
    # gale sources; partner (sink) sends a Request so gale completes a SOURCE contract -> SRC_READY
    c += cc("pd dualrole source") + ['emulation RunFor "0.2"']
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pd_encode.REQUEST(0, 2, 300))]
    c += deliver("0.2") + goodcrc("0.2")
    mid = 2
    # partner sends messages gale-as-SOURCE must handle
    msgs = [pd_encode.ctrl(8, mid), pd_encode.ctrl(9, mid + 1), pd_encode.ctrl(10, mid + 2),
            pd_encode.ctrl(11, mid + 3), pd_encode.ctrl(13, mid + 4), pd_encode.ctrl(7, mid + 5),
            pd_encode.REQUEST(0, 1, 150), (pd_encode.header(15, 1, mid), [0xFF008001]),
            (pd_encode.header(16, 0, mid + 1), [])]
    for m in msgs:
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
        c += deliver("0.05") + goodcrc("0.08")
        mid = (mid + 1) & 7 or 1
    return c


def _pd_cmd_battery():
    """Exhaustively drive command_pd (0x0800971c, the `pd` console handler) — its 13 one-direction
    branches are subcommand-dispatch + argument-validation arms. Cover every subcommand AND the
    malformed/edge cases (bad port, missing/extra args, bad values) that flip the validation arms."""
    return ["pd", "pd 0", "pd 0 state", "pd 1 state", "pd 99 state", "pd badport state",
            "pd 0 tx", "pd 0 bist", "pd 0 charger", "pd 0 dev", "pd 0 dev 20", "pd 0 dev 5",
            "pd 0 disable", "pd 0 enable", "pd 0 hard", "pd 0 soft", "pd 0 flush", "pd 0 ping",
            "pd dualrole", "pd dualrole on", "pd dualrole off", "pd dualrole sink",
            "pd dualrole source", "pd dualrole toggle", "pd dualrole bogus",
            "pd 0 dump", "pd 0 dump 0", "pd 0 dump 3", "pd dump",
            "pd trysrc", "pd trysrc 0", "pd trysrc 1", "pd trysrc 2", "pd trysrc 9",
            "pd 0 swap", "pd 0 swap power", "pd 0 swap data", "pd 0 swap vconn", "pd 0 swap bogus",
            "pd 0 vdm", "pd 0 vdm version", "pd 0 vdm info", "pd 0 vdm 1 2 3",
            "pd 0 comm", "pd 0 comm enable", "pd 0 comm disable", "pd 0 boguscmd", "pd 0 1 2 3 4 5"]


def _console_battery():
    """Comprehensive console-command battery covering every recovered command's subcommands +
    argument-validation + edge/malformed cases — flips the dispatch + arg-check arms across
    command_md/rw/tcpc/flashinfo/spixfer/reboot/hash/adc/sysjump/sysinfo/gpio/chan/help/... (the
    same per-handler vein that gave command_pd +7). Realistic stimulus (a user at the EC console)."""
    c = [
        # memory dump / read-write (addr/count/width validation)
        "md", "md 0x20000000", "md 0x20000000 8", "md .b 0x20000000", "md .h 0x20000000",
        "md .w 0x20000000 4", "md 0x8000000 16", "md bogus", "md 0x20000000 0",
        "rw", "rw 0x20000000", "rw 0x20000000 0x1234", "rw .b 0x20000000", "rw .h 0x20000000 5",
        "rw bogus", "rw 0x20000000 notanum",
        # flash info / wp
        "flashinfo", "flashwp", "flashwp enable", "flashwp disable", "flashwp now", "flashwp bogus",
        # adc / spi / tcpc
        "adc", "adc bogus", "tcpc", "tcpc 0", "tcpc 1", "tcpc bogus",
        "spixfer", "spixfer 0", "spixfer 0 4 01020304", "spixfer bogus",
        # reboot variants (arg dispatch; cancel is safe)
        "reboot cancel", "reboot hard", "reboot soft", "reboot ap-off", "reboot bogus", "reboot",
        # hash (vboot hash: offset/size, abort, ro/rw)
        "hash", "hash abort", "hash ro", "hash rw", "hash 0 0x10000", "hash bogus",
        # sysjump / sysinfo / gettime / history / taskinfo / syslock / hcdebug / gale / chan / help
        "sysinfo", "sysjump", "sysjump ro", "sysjump rw", "sysjump bogus", "gettime", "history",
        "taskinfo", "syslock", "hcdebug", "hcdebug off", "hcdebug normal", "gale", "gale polarity",
        "chan", "chan 0", "chan 0xffffffff", "chan save", "chan restore", "chan bogus",
        "help", "help pd", "help bogus",
        "gpioget", "gpioget EC_INT_L", "gpioget bogus", "gpioset", "gpioset EC_INT_L 1",
        "panicinfo",
    ]
    return c


def _console_battery2():
    """Deeper console args targeting the SPECIFIC remaining arms: md ASCII-dump (region with
    printable bytes = flash strings @0x800c800) + alignment/width/count; spixfer VALID transfer
    formats (its error arms fire on malformed args — give well-formed ones); hash full compute;
    sysjump addresses; tcpc port/reg; flashinfo after wp; adc channels."""
    return [
        # md: flash region WITH ascii strings (printable-char dump branch) + widths/counts/alignment
        "md 0x800c800", "md 0x800c800 32", "md 0x800c800 64", "md .b 0x800c800 48",
        "md .h 0x800c801", "md .w 0x800c802", "md 0x800c803 16", "md 0x40021000 8",
        "md 0x20000000 1", "md 0x20000001 4", "md 0x20000002 4", "md 0x20000003 4",
        # rw with width + readback at flash/ram/peripheral
        "rw .b 0x800c800", "rw .h 0x800c800", "rw 0x20000004 0xdeadbeef", "rw .b 0x20000004 0x5a",
        # spixfer: well-formed variants (port, counts, hex) covering the success + count-limit arms
        "spixfer 0 1", "spixfer 0 4 0x9f", "spixfer 0 0 4", "spixfer 0 1 0x03 4",
        "spixfer 0 40 0x00", "spixfer 0 4 00112233",
        # hash: compute over valid ranges + status
        "hash", "hash 0 256", "hash 0x1000 0x1000", "hash status", "hash ro", "hash rw", "hash abort",
        # sysjump targets (addr forms)
        "sysjump 0x8010000", "sysjump 0x8000000", "sysjump disable",
        # tcpc port/register
        "tcpc 0 0", "tcpc 0 1", "tcpc 0 0x10", "tcpc 1 0",
        # adc named channels + flashinfo after protect
        "adc VBUS", "adc CC1", "adc CC2", "flashwp enable", "flashinfo", "flashwp disable", "flashinfo",
        # sysinfo / panicinfo / gpio specifics
        "sysinfo", "gpioget CC1_RD", "gpioset CC1_RD 0", "chan 0x1", "chan 0xff",
    ]


def _console_battery3():
    """CORRECT-SYNTAX console args (the prior batteries used wrong token counts for some commands).
    spixfer needs EXACTLY 5 tokens: `spixfer <rlen|w> <id> <offset> <value|len>` (id=0 is the SPI
    flash, so a valid read/write makes the transfer-result arm run). Plus correct-arity md/hash."""
    return [
        # spixfer: valid read (rlen id offset len) + write (w id offset value) + parse-error arms
        "spixfer 4 0 0 4", "spixfer 8 0 0 8", "spixfer 1 0 0 1", "spixfer 16 0 0 16",
        "spixfer w 0 0 0x9f", "spixfer w 0 1 0x05", "spixfer 4 0 0 0x40",
        "spixfer x 0 0 4", "spixfer 4 0 0", "spixfer 4 z 0 4", "spixfer 4 0 z 4", "spixfer 4 0 0 z",
        "spixfer 0 0 0 0", "spixfer w 0 0 z",
        # md correct arity (1-2 args) + width + ascii region
        "md 0x800c800 8", "md .b 0x800c810 40", "md 0x20000000",
        # hash: argc/sub-command variants
        "hash", "hash abort", "hash 0 0x100", "hash status",
        # flashinfo / flashwp protection then info
        "flashwp", "flashwp now", "flashinfo",
    ]


def _console_battery4():
    """command_hash (no args) prints STATUS — its arms depend on hash-engine state (idle/in-progress/
    done/aborted). Sequence start->status->abort->status, with a SMALL hash (completes fast = done
    arm) and a LARGE hash (still in-progress when polled = in-progress arm). command_md alignment +
    ASCII-region arms."""
    return [
        "hash",                                  # idle status
        "hash start 0x0 0x100", "hash",          # small -> completes -> done-status arms
        "hash start 0x0 0x40000", "hash",        # large -> in-progress-status arm
        "hash abort", "hash",                    # aborted-status arm
        "hash start 0x8000 0x200", "hash status", "hash done",
        # md alignment (low-addr bits) + ascii (flash strings) + width/count edges
        "md 0x800c800 64", "md .b 0x800c801 33", "md .h 0x800c802 17", "md 0x800c803 8",
        "md 0x20000000 0", "md 0x20000001 2", "md 0x20000003 5", "md .w 0x800c804 9",
    ]


def _console_battery5():
    """command_tcpc subcommands are dump/clock/state (not the `tcpc <port> <reg>` I guessed). Drive
    each + port/value variants + bad args, with a PD contract up so dump/state have real TCPC state."""
    return [
        "tcpc dump", "tcpc dump 0", "tcpc dump 1", "tcpc dump bad",
        "tcpc clock", "tcpc clock 2400000", "tcpc clock 0", "tcpc clock bad",
        "tcpc state", "tcpc state 0", "tcpc state 1",
        "tcpc", "tcpc bogus", "tcpc 0",
        # remaining hash/md variants
        "hash start 0x10000 0x80000", "hash", "hash abort", "hash recalc",
        "md .b 0x800c820 50", "md 0x800c830 30", "md .h 0x20000005 8",
    ]


def _pd_grammar_battery():
    """command_pd battery built from the EXACT source grammar (usb_pd_protocol.c command_pd): the
    top-level subcommands take NO port (pd dualrole/dump/enable/trysrc/rwhashtable); the per-port form
    is `pd <port> <sub>`. Earlier batteries used wrong forms. Sequence `pd dualrole source` then bare
    `pd dualrole` to display drp_state=FORCE_SOURCE(>3)."""
    return [
        "pd dualrole on", "pd dualrole", "pd dualrole off", "pd dualrole", "pd dualrole sink",
        "pd dualrole", "pd dualrole source", "pd dualrole", "pd dualrole bogus",
        "pd dump 0", "pd dump 1", "pd dump 2", "pd dump 3", "pd dump",
        "pd enable 0", "pd enable 1", "pd enable", "pd trysrc 0", "pd trysrc 1", "pd trysrc",
        "pd rwhashtable",
        "pd 0 tx", "pd 0 bist_rx", "pd 0 bist_tx", "pd 0 charger", "pd 0 dev", "pd 0 dev 20",
        "pd 0 hard", "pd 0 info", "pd 0 soft",
        "pd 0 swap", "pd 0 swap power", "pd 0 swap data", "pd 0 swap vconn", "pd 0 swap bogus",
        "pd 0 ping", "pd 0 ping 1", "pd 0 ping 0",
        "pd 0 vdm", "pd 0 vdm ping 1", "pd 0 vdm curr", "pd 0 vdm vers",
        "pd 0 flash", "pd 0 state", "pd 0 bogus", "pd 0",
    ]


def _src_precise_battery():
    """Source-precise args (from the rebuilt C conditions in UNCOVERED-BY-FUNCTION.md):
    md `.s`/`.x` width chars (switch argv[1][1]); sysjump RO/RW/A/disable/bad-addr/locked;
    reboot hard/soft/ap-off/preserve/cancel. Disruptive commands (reboot/sysjump/syslock) LAST."""
    return [
        # command_md: switch(argv[1][1]) width chars incl 's' + bad
        "md .s 0x800c800", "md .b 0x800c800 40", "md .h 0x800c802 8", "md .w 0x800c804 4",
        "md .x 0x800c800", "md .s 0x20000000",
        # command_reboot subcommands (these SCHEDULE a reboot flag; cancel clears it — safe order)
        "reboot ap-off", "reboot preserve", "reboot hard", "reboot soft", "reboot cancel",
        "reboot hard preserve", "reboot bogus",
        # command_pd remaining curr/vdm/ping forms
        "pd 0 vdm curr", "pd 0 vdm ping 1", "pd 0 vdm vers", "pd 0 ping 5",
        # command_tcpc remaining + command_hash remaining
        "tcpc clock 0", "tcpc state 1", "tcpc dump 1",
        "hash start 0x0 0x200", "hash", "hash abort", "hash status",
        # command_sysjump (jumps the image — keep at the very end) + syslock (locks console)
        "sysjump A", "sysjump disable", "sysjump 0xnotaddr", "sysjump RO",
    ]


def _flashinfo_protect_post():
    """command_flashinfo arms (flash.c:551-574) read flash_get_protect() flag bits + per-bank protect.
    AFTER boot (so flash_pre_init saw a clean 0xFFFFFFFF and didn't reset-loop), set FLASH_WRPR to
    partial-protection values + StuckBusy, and drive `flashinfo` so the RO_NOW/ALL_NOW/ERROR_STUCK
    flag arms and the per-bank Y/. arm run; also flashwp for RO_AT_BOOT/ALL_AT_BOOT pstate flags."""
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    c = []
    c += cc("flashinfo") + ['emulation RunFor "0.05"']                  # clean (unprotected) baseline
    for wrp in (0xFFFFFF00, 0xFFFF0000, 0x0000FFFF, 0x00000000, 0xFFFFFFFE):
        c += ['sysbus.flashif WrpValue 0x%08X' % wrp]
        c += cc("flashinfo") + ['emulation RunFor "0.05"']
    c += ['sysbus.flashif WrpValue 0xFFFFFFFF', 'sysbus.flashif StuckBusy true']
    c += cc("flashinfo") + ['emulation RunFor "0.05"']
    c += ['sysbus.flashif StuckBusy false']
    for sub in ("enable", "all", "now"):
        c += cc("flashwp " + sub) + ['emulation RunFor "0.05"'] + cc("flashinfo") + ['emulation RunFor "0.05"']
    return c


def _flash_protect_deep_post():
    """flash_set_protect (flash.c:456) DEEP arms — the 19-unreached cluster (RO 0x080047cc). They are
    gated behind the line-507 early-return `if ((~flash_get_protect()) & (GPIO_ASSERTED|RO_AT_BOOT)) return;`
    which ALWAYS fires in every prior scenario because base.resc leaves WP_L (PB11, active-low) HIGH, so
    flash_get_protect() never reports GPIO_ASSERTED. Here, POST-boot (flash_pre_init already ran with WP
    high, so no OBL_LAUNCH reset-loop), we assert WP_L LOW to set GPIO_ASSERTED, then `flashwp enable`
    writes the RO_AT_BOOT pstate, so flash_get_protect()==GPIO_ASSERTED|RO_AT_BOOT and the early-return is
    bypassed. Then the deep arms run: ALL_AT_BOOT-set (511), ALL_AT_BOOT-clear-with-RO-set (491+493 TRUE),
    ALL_NOW (525), and — only reachable via host cmd 0x15 with mask=RO_NOW since NO console command sends
    that mask — RO_NOW (517). Also varies WRP so flash_get_protect()'s per-bank scan yields RO_NOW/ALL_NOW/
    ERROR_INCONSISTENT and flash_physical_protect_now()'s arms execute."""
    import hostcmd
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "0.05"']
    def hc(mask, flags):  # EC_CMD_FLASH_PROTECT=0x15, params {u32 mask; u32 flags}
        data = hostcmd._le32(mask) + hostcmd._le32(flags)
        return ['sysbus.i2c1 HostCmd "%s"' % hostcmd._pkt(0x15, 0, 3, data), 'emulation RunFor "0.05"']
    c = []
    # --- baseline: WP_L still HIGH, RO_AT_BOOT pstate not set ---
    #   flashwp norw -> flash_set_protect(ALL_AT_BOOT,0): line 491 TRUE, line 493 FALSE (RO_AT_BOOT unset)
    #   then line 507 early-returns. host-cmd RO_NOW: line 517 guard true but 507 returns first.
    c += cc("flashwp norw")
    c += hc(0x02, 0x02)
    # --- assert WP_L LOW => GPIO_ASSERTED set in flash_get_protect() ---
    c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.02"']
    # --- establish RO_AT_BOOT pstate (RO_AT_BOOT,-1): line 486 arm, flash_protect_at_boot(FLASH_WP_RO) ---
    c += cc("flashwp enable")
    # now flash_get_protect()==GPIO_ASSERTED|RO_AT_BOOT -> line 507 does NOT return; deep arms reachable:
    c += cc("flashwp rw")     # (ALL_AT_BOOT,-1): line 511 TRUE -> flash_protect_at_boot(FLASH_WP_ALL)
    c += cc("flashwp norw")   # (ALL_AT_BOOT,0): line 491 TRUE, line 493 TRUE (RO_AT_BOOT now set) -> range=RO
    c += cc("flashwp enable") # restore RO_AT_BOOT pstate for the NOW arms below
    c += hc(0x02, 0x02)       # (RO_NOW,RO_NOW): line 517 -> flash_physical_protect_now(0)  [no console path]
    c += cc("flashwp now")    # (ALL_NOW,-1): line 525 -> flash_physical_protect_now(1)
    c += cc("flashwp disable")# (RO_AT_BOOT,0): range=NONE branch of line 487
    # host-cmd mask/flags matrix (only the host command can send arbitrary mask bits): exercise each
    # guard's (mask&BIT) && (flags&BIT) true/false combination with GPIO asserted + RO_AT_BOOT set.
    for mask in (0x01, 0x02, 0x04, 0x40, 0x46, 0x47):
        for flags in (0x00, mask, 0xFFFFFFFF):
            c += hc(mask, flags)
    # vary WRP option bytes so flash_get_protect()'s per-bank scan returns RO_NOW/ALL_NOW/INCONSISTENT
    for wrp in (0xFFFFFF00, 0x0000FFFF, 0x00000000):
        c += ['sysbus.flashif WrpValue 0x%08X' % wrp] + cc("flashinfo") + hc(0x04, 0x04) + hc(0x02, 0x02)
    return c


def _hostpkt_malformed_post():
    """host_packet_receive (host_command.c:239, RO 0x08005314) validation arms — unreached because the
    campaign's _pkt always builds a well-formed, correctly-checksummed packet, so every malformed-input
    `goto host_packet_bad` is skipped. Inject RAW malformed packets via the I2C slave injector (full
    byte control; leading 0xDA = EC protocol-v3 framing, stripped by the driver, so request_size = bytes
    after it). Cover: struct_version != EC_HOST_REQUEST_VERSION(3) -> EC_RES_INVALID_HEADER (289); bad
    checksum -> EC_RES_INVALID_CHECKSUM (326); < sizeof(header)=8 bytes -> EC_RES_REQUEST_TRUNCATED (256);
    data_len field overclaiming the bytes actually present -> EC_RES_REQUEST_TRUNCATED (300); reserved
    byte set (host_request_expected_size:234); oversized > slave buffer -> TRUNCATED/overflow (263)."""
    import hostcmd
    def hc(hexpkt):
        return ['sysbus.i2c1 HostCmd "%s"' % hexpkt, 'emulation RunFor "0.05"']
    def raw(sver, cmd, ver, rsvd, dlen, data, fixcsum=True):
        # ec_host_request: [struct_version, checksum, cmd_lo, cmd_hi, command_version, reserved, dlen_lo, dlen_hi] + data
        r = [sver & 0xFF, 0, cmd & 0xFF, (cmd >> 8) & 0xFF, ver & 0xFF, rsvd & 0xFF, dlen & 0xFF, (dlen >> 8) & 0xFF] + list(data)
        if fixcsum:
            r[1] = (-sum(r)) & 0xFF
        return "da" + "".join("%02x" % b for b in r)
    c = []
    c += hc(hostcmd._pkt(0x01, 0, 3, [0x44, 0x33, 0x22, 0x11]))   # valid baseline (success fall-through)
    c += hc(hostcmd._pkt(0x01, 0, 5, []))                         # struct_version=5 -> INVALID_HEADER (289)
    c += hc(hostcmd._pkt(0x01, 0, 0, []))                         # struct_version=0 -> INVALID_HEADER (289)
    c += hc(hostcmd._pkt(0x01, 0, 3, [0, 0, 0, 0], bad=True))     # corrupted checksum -> INVALID_CHECKSUM (326)
    c += hc("da0301")                                             # request_size=2 (<8) -> TRUNCATED (256)
    c += hc("da03")                                               # request_size=1 (<8) -> TRUNCATED (256)
    c += hc(raw(3, 0x01, 0, 0, 0xFF, []))                         # dlen=255 but 0 data -> TRUNCATED (300)
    c += hc(raw(3, 0x01, 0, 0, 0x40, [0, 0, 0, 0]))               # dlen=64 but 4 data -> TRUNCATED (300)
    c += hc(raw(3, 0x01, 0, 1, 0, []))                            # reserved=1 (expected_size:234)
    c += hc("da03" + "00" * 300)                                  # oversized > buffer -> TRUNCATED/overflow (263)
    return c


def _pd_fw_flash_post():
    """hc_remote_flash (EC_CMD_USB_PD_FW_UPDATE 0x110, RO 0x08007a60) VDM-loop arms — the 22-unreached
    cluster (usb_pd_protocol.c:3256-3288). Never reached because hostcmd.py's FW battery sends REBOOT/
    FLASH_ERASE/ERASE_SIG first, and queue_vdm() (usb_pd_protocol.c:466) UNCONDITIONALLY sets
    pd[0].vdm_state=VDM_STATE_READY(1); with no contract to clear it, every subsequent 0x110 hits the
    `if (pd[port].vdm_state > 0) return EC_RES_BUSY;` early-return (3227) BEFORE the switch/loop, so the
    valid-FLASH_WRITE path (3256 false), the per-VDO send loop (3260), and both VDM-wait loops
    (3266/3281) + their TIMEOUT arms (3270/3285) stay unreached. FIX: `pd 0 disable` (pd_task in
    PD_STATE_DISABLED won't run the vdm send machine, so it can't consume/clear the queued VDM) + clear
    vdm_state (0x20001198) = 0 immediately before each command. Then FLASH_WRITE(valid, size%4==0)
    passes 3256, pd_send_vdm sets READY, and the `while(vdm_state>0 && get_time()<timeout)` loop spins
    until the 500ms timeout (vdm_state stays >0) -> in-loop + post-loop TIMEOUT. ERASE_SIG breaks to the
    shared wait loop; multi-word size iterates the loop; cmd>3 hits the switch default; vdm_state>0 on
    entry hits BUSY. (The ERR_TMOUT(-1)/<0 ERROR post-loop arms need a NAKing reactive partner since
    pd_send_vdm overwrites any injected negative vdm_state with READY — deferred to a partner pass.)"""
    import hostcmd
    VDM = 0x20001198                                    # pd[0].vdm_state (offset 72)
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")] + ['emulation RunFor "0.05"']
    def fw(dev, cmd, port, size, data=None):
        return [dev & 0xFF, (dev >> 8) & 0xFF, cmd & 0xFF, port & 0xFF] + hostcmd._le32(size) + list(data or [])
    def hc(cmd, port, size, data=None, vdm=0, settle="0.7"):
        return ['sysbus WriteDoubleWord 0x%08X 0x%08X' % (VDM, vdm & 0xFFFFFFFF),   # clear/seed vdm_state
                'sysbus.i2c1 HostCmd "%s"' % hostcmd._pkt(0x110, 0, 3, fw(0, cmd, port, size, data)),
                'emulation RunFor "%s"' % settle]
    c = cc("pd 0 disable")
    c += hc(2, 0, 4, [0xDE, 0xAD, 0xBE, 0xEF])               # FLASH_WRITE 1 word -> loop body + TIMEOUT (3266/3270)
    c += hc(2, 0, 28, list(range(28)), settle="1.6")        # FLASH_WRITE 7 words (>VDO_MAX-1) -> multi-iter loop (3260)
    c += hc(3, 0, 0)                                         # ERASE_SIG -> break to wait loop (3281) + TIMEOUT (3284/3285)
    c += hc(99, 0, 0)                                        # cmd>3 -> switch default (0x7aa4)
    c += hc(0, 0, 0, vdm=2, settle="0.1")                   # vdm_state>0 on entry -> BUSY (3227)
    return c


def _tcpc_fixed_battery():
    """CORRECT command_tcpc grammar (usb_pd_tcpc.c:1330+): `tcpc <port> clock <freq>` / `tcpc <port>
    state` (argv[1]=port, argv[2]=subcmd) — earlier battery used `tcpc clock` (no port) and missed
    these arms. Cover: valid clock/state, bad port (1335), argc<4 (1341), bad freq *e (1345)."""
    return [
        "tcpc 0 clock 2400000", "tcpc 0 clock 1000000", "tcpc 0 state", "tcpc 0 dump",
        "tcpc 0 clock", "tcpc 0 clock notanum", "tcpc 9 clock 1", "tcpc 9 state",
        "tcpc x state", "tcpc 1 state", "tcpc dump", "tcpc",
        # also retry command_pd / md / reboot remaining with a contract present
        "pd 0 vdm curr", "pd 0 vdm vers", "pd 0 vdm ping 1", "pd dualrole source", "pd dualrole",
        "md .s 0x800c800 8", "md .x 0x20000000", "reboot ap-off", "reboot preserve",
    ]


def _reset_cause_scenarios():
    """Boot with each RCC_CSR reset cause so system_pre_init + other reset-flag-dependent branches run
    for every reset reason (POR/PIN/software/IWDG/WWDG/low-power/option-byte-loader). GaleRcc.ResetFlags
    is set BEFORE boot. Bits: POR=1<<27, PIN=1<<26, OBL=1<<25, SFT=1<<28, IWDG=1<<29, WWDG=1<<30, LPWR=1<<31."""
    causes = [("por", 0x08000000), ("pin", 0x04000000), ("sft", 0x10000000), ("iwdg", 0x20000000),
              ("wwdg", 0x40000000), ("lpwr", 0x80000000), ("obl", 0x02000000),
              ("porpin", 0x0C000000), ("all", 0xFE000000)]
    out = []
    for tag, bits in causes:
        out.append(("rst_%s" % tag, ['sysbus.rcc ResetFlags 0x%08X' % bits], [], "2.0", []))
        out.append(("rst_%s_rw" % tag, ['sysbus.rcc ResetFlags 0x%08X' % bits], ["sysjump rw"], "2.0", []))
    return out


def _jump_data_scenarios():
    """system_common_pre_init jump-data block (system.c:708-743, RO 0x08006ce4, 8 unreached + RW mirror)
    runs ONLY on a jump between images = boot reset_flags==0 AND a valid `struct jump_data` at
    jdata = CONFIG_RAM_BASE+CONFIG_RAM_SIZE - sizeof = 0x20004000 - 24 = 0x20003FE8, with
    magic==JUMP_DATA_MAGIC(0x706d754a) && version>=1. base.resc's default boot has reset_flags=POR|PIN
    (!=0) so the block is ALWAYS skipped. Plant jdata PRE-boot via monitor writes (initial SP=0x200004C0
    is far below jdata so the boot stack can't clobber it; jump_data lives above .bss so startup zeroing
    misses it) + zero the RCC reset cause. Struct (fields copied to END of RAM, magic last): reserved0@+0,
    struct_size@+4, jump_tag_total@+8, reset_flags@+0xc, version@+0x10, magic@+0x14. Different versions
    flip each discriminator: v1 (726 ==1 true, 739 <2 true; v1 has no tags), v2 (728 ==2 true; delta=
    sizeof(24)-JUMP_DATA_SIZE_V2(16)=8 != 0 AND tags!=0 -> 733 memmove; 743 <3 true), v3 (delta=24-
    struct_size(20)=4 != 0 -> 733; 743 <3 false), v3z (struct_size=24 -> delta==0 -> the 733 delta==0
    fall-through). Also bad-magic so 708 stays exercised both ways."""
    J = 0x20003FE8
    def plant(version, jump_tag_total, struct_size, restore_flags=0x00000002, magic=0x706d754a):
        return [
            'sysbus.rcc ResetFlags 0x0',                                       # boot reset_flags == 0 (a jump)
            'sysbus WriteByte 0x%08X 0' % J,                                   # reserved0
            'sysbus WriteDoubleWord 0x%08X %d' % (J + 4, struct_size),         # struct_size
            'sysbus WriteDoubleWord 0x%08X %d' % (J + 8, jump_tag_total),      # jump_tag_total
            'sysbus WriteDoubleWord 0x%08X 0x%08X' % (J + 0xc, restore_flags), # reset_flags to restore
            'sysbus WriteDoubleWord 0x%08X %d' % (J + 0x10, version),          # version
            'sysbus WriteDoubleWord 0x%08X 0x%08X' % (J + 0x14, magic),        # magic
        ]
    out = []
    for tag, (v, tot, sz) in (("v1", (1, 0, 24)), ("v2", (2, 8, 16)),
                              ("v3", (3, 4, 20)), ("v3z", (3, 0, 24))):
        out.append(("pdjump_%s" % tag, plant(v, tot, sz), [], "2.0", []))
    # bad magic: 708 magic-compare false arm (with reset_flags==0 so only magic differs)
    out.append(("pdjump_badmagic", plant(3, 0, 24, magic=0xDEADBEEF), [], "2.0", []))
    return out


def _pd_rx_malformed_post():
    """Drive pd_analyze_rx (the PHY RX decoder, usb_pd_tcpc.c:609) error/edge arms by delivering
    PHY-level message variants the normal traffic never produces: bad CRC (pcrc!=ccrc), truncated /
    no-EOP (bit<0 || eop!=PD_EOP), SOP'/SOP'' ordered sets (val==PD_SOP_PRIME/...), and HARD-RESET /
    CABLE-RESET signaling (bit==PD_RX_ERR_HARD_RESET/CABLE_RESET). Built at the symbol level with
    pd_encode.TxBits + the standard BMC K-codes."""
    import pd_encode as pe
    SYNC1, SYNC2, SYNC3, RST1, RST2, EOP = 0x18, 0x11, 0x06, 0x07, 0x19, 0x0D

    def msg(sop_syms, header=None, objs=(), crc=None, eop=True):
        tx = pe.TxBits()
        tx.preamble()
        for sym in sop_syms:
            tx.sym(pe.BMC(sym))
        if header is not None:
            tx.encode_short(header)
            for o in objs:
                tx.encode_word(o)
            tx.encode_word(pe.crc32_pd(header, objs) if crc is None else crc)
        if eop:
            tx.sym(pe.BMC(EOP))
        tx.last_edge()
        sm = pe.levels_to_samples(tx.level_bits())
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()

    SOP = [SYNC1, SYNC1, SYNC1, SYNC2]
    hdr = pe.header(1, 0, 0)
    variants = [
        msg(SOP, hdr, crc=0xDEADBEEF),                 # bad CRC -> pcrc != ccrc
        msg(SOP, hdr, eop=False),                      # no EOP -> eop != PD_EOP
        msg(SOP, pe.header(2, 1, 0), objs=[0x12345678]),   # 1-object data msg (decode_word path)
        msg([SYNC1, SYNC1, SYNC3, SYNC3], hdr),        # SOP'
        msg([SYNC1, RST2, RST2, SYNC3], hdr),          # SOP''
        msg([RST1, RST1, RST1, RST2]),                 # HARD RESET ordered set
        msg([RST1, SYNC1, RST1, SYNC3]),               # CABLE RESET ordered set
        msg(SOP, pe.header(2, 7, 0), objs=[0] * 7),    # max 7 objects
        "00" * 4,                                       # garbage / no preamble -> decode fail
    ]
    c = ['sysbus.adc ForceSourceCc true', 'sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true']
    for v in variants:
        c += ['sysbus.dma1 StageResponse "%s"' % v, 'sysbus.dma1 ExpectContractMsg']
        for _ in range(3):
            c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.00001"']
        c += ['emulation RunFor "0.05"']
    return c


def _flash_preinit_scenarios():
    """Boot with FLASH_WRPR showing various protection states (set BEFORE boot) so flash_pre_init's
    WRPR/RDP reconciliation check branches run. Its checks execute EARLY in boot (before any reset
    reconciliation loop), so even if a partial-protection value triggers reconciliation the branches
    are traced on the first pass."""
    out = []
    for tag, wrp in (("half", 0xFFFF0000), ("low8", 0xFFFFFF00), ("hi", 0x0000FFFF),
                     ("one", 0xFFFFFFFE), ("none", 0xFFFFFFFF)):
        out.append(("fpi_%s" % tag, ['sysbus.flashif WrpValue 0x%08X' % wrp], [], "2.5", []))
        out.append(("fpi_%s_rw" % tag, ['sysbus.flashif WrpValue 0x%08X' % wrp], ["sysjump rw"], "2.5", []))
    return out


def _flash_optb_scenarios():
    """Set flash OPTION BYTES (RAM-backed @0x1FFFF800; read_optb is a plain byte read) BEFORE boot to
    encode RDP level / WRP write-protect, so flash_pre_init's protect-at-boot reconciliation +
    flash_physical_get_protect_at_boot + flashinfo protect arms run. RDP@0x00 (0xAA=L0 else L1);
    WRP0..3 @0x08/0x0A/0x0C/0x0E (bit clear = protected). Checks run early in boot so they're traced
    even if reconciliation later resets."""
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    post = cc("flashinfo") + ['emulation RunFor "0.05"'] + cc("flashwp now") + ['emulation RunFor "0.05"'] + cc("flashinfo") + ['emulation RunFor "0.05"']
    sets = {
        "wrp0":   ['sysbus WriteByte 0x1FFFF808 0x00'],                       # RO group protected
        "allwrp": ['sysbus WriteByte 0x1FFFF808 0x00', 'sysbus WriteByte 0x1FFFF80A 0x00',
                   'sysbus WriteByte 0x1FFFF80C 0x00', 'sysbus WriteByte 0x1FFFF80E 0x00'],
        "rdp1":   ['sysbus WriteByte 0x1FFFF800 0x55'],                       # RDP level 1
        "rdp1wrp": ['sysbus WriteByte 0x1FFFF800 0x55', 'sysbus WriteByte 0x1FFFF808 0x00'],
        "halfwrp": ['sysbus WriteByte 0x1FFFF808 0xF0'],                      # some sectors of group 0
    }
    out = []
    for tag, mon in sets.items():
        out.append(("optb_%s" % tag, mon, [], "2.5", post))
        out.append(("optb_%s_rw" % tag, mon, ["sysjump rw"], "2.5", post))
    return out


def _usb_pd_control_post():
    """hc_usb_pd_control (cmd 0x101) arms: port>=COUNT (3130), role/mux>=COUNT (3133),
    swap==SWAP_POWER (3152), info-fill with PD state (3161). Struct {u8 port, role, mux, swap}.
    Sent via I2C host command with a contract up so the info-fill branches have real state."""
    import hostcmd, pd_encode as pe
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for m in (pe.SRC_CAP, pe.ACCEPT(1), pe.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    for _ in range(2):
        c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.2"']
    def hc(port, role, mux, swap):
        return ['sysbus.i2c1 HostCmd "%s"' % hostcmd._pkt(0x101, 0, 3, [port, role, mux, swap]),
                'emulation RunFor "0.05"']
    for role in range(0, 8):            # role 0..5 valid, 6/7 -> ROLE_COUNT exceeded
        c += hc(0, role, 0, 0)
    for mux in range(0, 8):             # mux range
        c += hc(0, 0, mux, 0)
    for swap in range(0, 4):            # swap incl SWAP_POWER
        c += hc(0, 0, 0, swap)
    c += hc(9, 0, 0, 0) + hc(1, 0, 0, 0) + hc(0, 99, 0, 0) + hc(0, 0, 99, 0)
    return c


def _pd_smallfns_post():
    """Drive the smaller PD functions over a multi-PDO contract: `pd 0 dev <mv>` ->
    pd_request_source_voltage (PDO select + re-negotiation set_state arms), `pd 0 vdm version/info`
    -> pd_send_vdm, `pd dualrole ...` -> pd_set_dual_role. Multi-PDO Source_Cap so voltage selection
    has 5/9/12/20V options."""
    import pd_encode as pe
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    pdos = [0x2201912C, 0x0002D12C, 0x0003C12C, 0x0004B12C]   # 5V/9V/12V/20V fixed
    src_cap = (pe.header(1, 4, 0), pdos)
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    for m in (src_cap, pe.ACCEPT(1), pe.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    for _ in range(2):
        c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.2"']
    def fire(t="0.08"):
        f = []
        for _ in range(3):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]
    for mv in ("5", "9", "12", "20", "3", "0", "100"):
        c += cc("pd 0 dev %s" % mv) + ['emulation RunFor "0.05"']
        # re-stage source cap so the re-negotiation has PDOs
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(src_cap)] + fire("0.1")
    for v in ("version", "info"):
        c += cc("pd 0 vdm %s" % v) + ['emulation RunFor "0.03"'] + fire("0.08")
    for d in ("on", "off", "sink", "source", "toggle"):
        c += cc("pd dualrole %s" % d) + ['emulation RunFor "0.05"']
    return c


def _pd_msgfuzz_post():
    """pd_task's 184 one-dir branches are message-FIELD tests (header bits via `lsls r,#0x10`=bit15,
    object/PDO/VDO field compares) in already-reached handler code — they need the OTHER direction, i.e.
    messages with DIFFERENT content delivered to gale-in-contract. Distinct from the state-focused levers.
    Establish a SNK contract (sustained Source_Cap firing), then deliver a wide battery of messages with
    varied headers (every type 0..15 x cnt 0..4 x both roles x msg_id) and varied object words (bit
    patterns exercising PDO type bits[31:30], VDO svid/cmd/bits, sign/range), firing COMP for each so the
    field-test branches flip both ways."""
    import pd_encode as pe
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    # establish contract
    for _ in range(40):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.SRC_CAP), 'sysbus.dma1 ExpectContractMsg',
              'sysbus.exti FireComp 21', 'emulation RunFor "0.006"']
    c += ['emulation RunFor "0.02"']
    # varied object words: PDO type bits[31:30]=0/1/2/3, big/small V/I, VDO svid/struct/cmd, sign bits
    objs = [0x2201912C, 0x0002D12C, 0x4001905A, 0x8001912C, 0xC0000000, 0xFF008001, 0xFF018040,
            0x12340000, 0x00000001, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0x00000000, 0x0000FFFF]
    mid = 3
    # data messages: type x cnt x role x object content
    for typ in (1, 2, 3, 4, 5, 6, 7, 15):           # Source_Cap/Request/BIST/Sink_Cap/.../VDM
        for cnt in (1, 2):
            for o in objs[:4]:
                hdr = pe.header(typ, cnt, mid & 7, prole=(mid & 1), drole=((mid >> 1) & 1))
                c += ['sysbus.dma1 StageResponse "%s"' % hexmsg((hdr, [o] * cnt)), 'sysbus.dma1 ExpectContractMsg',
                      'sysbus.exti FireComp 21', 'emulation RunFor "0.0008"']
                mid += 1
        c += ['emulation RunFor "0.004"']
    return c


def _ctrl_swap_held_post():
    """handle_ctrl_request swap-completion arms via STATE-HELD inject+deliver (fixes ctrlswap's flaw).
    Root cause ctrlswap +0: the swap-state pd_task cases re-send + set_state away `if (last_state !=
    task_state)`, so injecting only task_state(@6) let the switch transition before the delivered msg.
    FIX: inject BOTH task_state(0x20001156) AND last_state(0x20001157, DWARF offset 7) = swap_state, so
    `last_state == task_state` -> the case body is SKIPPED (no re-send/transition) and gale HOLDS the
    swap state; then deliver the matching PS_RDY/REJECT/WAIT/ACCEPT -> pd_task's handle_request (runs
    BEFORE the switch, on the held task_state) executes handle_ctrl_request's `if (task_state==<STATE>)`
    completion arm. Establish a SNK contract first so flags/roles are valid."""
    import pd_encode as pe
    TS, LS, PR, FL = 0x20001156, 0x20001157, 0x20001150, 0x20001152
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def w16(a, v):
        return ['sysbus WriteByte 0x%X %d' % (a, v & 0xFF), 'sysbus WriteByte 0x%X %d' % (a + 1, (v >> 8) & 0xFF)]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for m in (pe.SRC_CAP, pe.ACCEPT(1), pe.PS_RDY(2)):           # establish contract (valid flags/roles)
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    for _ in range(2):
        c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.2"']
    PS_RDY, REJECT, WAIT, ACCEPT = 6, 4, 12, 3
    EC, VC = 0x40, 0x40 | 0x1000
    pairs = [
        (PS_RDY, [(12, 0, EC), (31, 1, EC), (33, 1, VC), (6, 0, EC), (13, 0, EC)]),
        (REJECT, [(27, 1, EC), (32, 1, EC), (28, 1, EC), (10, 0, EC), (7, 0, EC)]),
        (WAIT,   [(27, 1, EC), (32, 1, EC), (28, 1, EC), (10, 0, EC), (7, 0, EC)]),
        (ACCEPT, [(35, 0, EC), (27, 1, EC), (32, 1, EC), (28, 1, EC), (10, 0, EC), (7, 0, EC)]),
    ]
    mid = 3
    for ctype, states in pairs:
        for st, pr, fl in states:
            c += ['sysbus WriteByte 0x%X %d' % (PR, pr)] + w16(FL, fl)   # role/flags once per pair
            # Re-assert TS=LS=st before EACH COMP (so pd_task's inter-tick recompute can't drift it off
            # target) + stage a fresh-msg_id ctrl msg, so whichever COMP lands while gale is RX-armed
            # processes it on the HELD swap state -> handle_ctrl_request's completion arm.
            for k in range(5):
                c += ['sysbus WriteByte 0x%X %d' % (TS, st), 'sysbus WriteByte 0x%X %d' % (LS, st),
                      'sysbus.dma1 StageResponse "%s"' % hexmsg(pe.ctrl(ctype, (mid + k) & 7)),
                      'sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.001"']
            c += ['emulation RunFor "0.006"']
            mid += 5
    return c


def _partner_swap_post():
    """RECEIVE-side swap/control handling: with a CONFIRMED-up SNK contract (gale reaches SNK_READY under
    sustained Source_Cap firing — verified), the PARTNER sends swap/control REQUESTS to gale-in-READY so
    handle_ctrl_request's request-processing cases run on a real contract (distinct from the transmit-side
    gale-initiated swaps). Establish contract via sustained Source_Cap+COMP, then deliver each partner msg
    (DR_Swap/PR_Swap/VCONN_Swap/Get_Source_Cap/Get_Sink_Cap/Soft_Reset/Reject/Wait/Ping/GotoMin) via
    StageResponse+ExpectContractMsg+COMP while continuing light Source_Cap firing to keep the contract."""
    import pd_encode as pe
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg((pe.header(4, 1, 0), [0x2601912C]))]
    # establish the contract: sustained Source_Cap + COMP
    for _ in range(50):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.SRC_CAP), 'sysbus.dma1 ExpectContractMsg',
              'sysbus.exti FireComp 21', 'emulation RunFor "0.006"']
    c += ['emulation RunFor "0.03"']
    # partner-initiated control requests to gale-in-READY (mid = continuing sequence); deliver each then
    # COMP a few times so gale processes + responds (its handle_ctrl_request case + response path run).
    mid = 4
    for ctype in (7, 8, 9, 10, 11, 13, 2, 5, 4, 12):     # Get_Src/Get_Snk/DR/PR/VCONN/Soft/GotoMin/Ping/Reject/Wait
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.ctrl(ctype, mid & 7)), 'sysbus.dma1 ExpectContractMsg']
        for _ in range(6):
            c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.003"']
        mid += 1
    return c


def _swap_reject_post():
    """handle_ctrl_request REJECT/WAIT swap-completion arms (usb_pd_protocol.c:907-924): a REJECT or WAIT
    received while in DR_SWAP/SRC_SWAP_INIT/SNK_SWAP_INIT/VCONN_SWAP_SEND/SNK_REQUESTED. CONFIRMED gale
    reaches a real SNK contract under sustained reactive firing (see memory: pd_request_vconn_swap requires
    SNK_READY, and gale reaches VCONN_SWAP_SEND); the swap ACCEPT arms are already covered (gale auto-swaps).
    What's missing: the partner only ever ACCEPTs. Here the reactive replyBank (consumed by ReactToTx on
    gale's swap TX, type 9/10/11/13) is loaded with REJECT then WAIT, so gale's initiated swaps are
    REJECTed/WAITed -> the REJECT/WAIT case + each swap-state arm runs. Establish the contract with sustained
    blanket firing (Source_Cap each round so gale catches it in DISCOVERY), then per reply-kind issue the
    swaps with continued firing to keep the contract + deliver the reactive REJECT/WAIT while gale holds the
    swap state."""
    import pd_encode as pe
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    def blanket(reps, gap="0.0015", src=False):
        f = []
        for _ in range(reps):
            if src:
                f += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.SRC_CAP), 'sysbus.dma1 ExpectContractMsg']
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "%s"' % gap]
        return f
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    # establish the contract: sustained Source_Cap + COMP so gale (transiently in DISCOVERY) catches it
    c += blanket(60, src=True) + ['emulation RunFor "0.05"']
    # now load the reactive swap-reply bank with REJECT, then WAIT, and drive gale-initiated swaps
    for kind, mk in (("reject", lambda i: pe.ctrl(4, i)), ("wait", lambda i: pe.ctrl(12, i))):
        for i in range(8):
            c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(mk(i)))]
        for action in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn", "pd 0 soft"):
            c += cc(action) + ['emulation RunFor "0.003"'] + blanket(40) + ['emulation RunFor "0.03"']
    return c


def _swap_blanket_post():
    """REAL swap-handshake completion for handle_ctrl_request's swap arms (the pd_task plateau). Unlike
    ctrlswap (inject+deliver — fails: swap states are transient, set_state's away before the RX), this
    drives gale to GENUINELY initiate each swap and lets the reactive partner complete it. Root cause of
    prior fire_swap +0: PD_STATE_DR_SWAP's `send_control(DR_SWAP)` SYNCHRONOUSLY waits for the partner's
    GoodCRC (res<0 -> leaves DR_SWAP to SOFT_RESET/READY before the Accept), and fire_swap's 4 COMPs at
    8us gaps are too fast for gale to TX the request and re-enable RX between them. FIX: BLANKET the whole
    command window with COMPs spaced ~1.5ms (GaleDma's TIM1_CCR1 RX pops GoodCRC then Accept as gale
    re-enables RX after TX; the spacing lets gale TX, get GoodCRC during send_control's wait -> STAY in
    the swap state -> then receive the Accept -> handle_ctrl_request's swap arm runs). gale is SOURCE
    (PartnerSink) with a contract; reactive partner auto-replies Accept to DR/PR/VCONN_Swap (ReactToTx)."""
    import pd_encode as pe
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg((pe.header(4, 1, 0), [0x2601912C]))]   # Sink_Cap
    def blanket(reps=40, gap="0.0015"):
        f = []
        for _ in range(reps):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "%s"' % gap]
        return f
    # Establish the WORKING SNK contract (gale-as-source never stabilizes SRC_READY via the reactive
    # partner — a documented fragility; the SNK path is the one injdel proved reaches a contract).
    # Partner (SOURCE) sends Source_Cap -> gale Requests -> partner Accept -> PS_RDY -> SNK_READY.
    for m in (pe.SRC_CAP, pe.ACCEPT(1), pe.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    for _ in range(2):
        c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.2"']
    c += blanket(20) + ['emulation RunFor "0.1"']
    # gale-initiated swaps FROM SNK_READY (DR_SWAP role-agnostic; PR_Swap->SNK_SWAP_INIT; VCONN->VCONN_*;
    # soft->SOFT_RESET). Issue cmd, then BLANKET so the sync GoodCRC (during send_control) + the partner
    # Accept both land while gale holds the swap state -> handle_ctrl_request's swap-completion arms run.
    for action in ("pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn", "pd 0 soft",
                   "pd 0 swap data", "pd 0 swap power", "pd 0 swap vconn"):
        c += cc(action) + ['emulation RunFor "0.003"'] + blanket(40) + ['emulation RunFor "0.05"']
    # partner sends Get_Sink_Cap -> gale responds; and a Reject/Wait to a swap to hit those arms
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.ctrl(8, 4))] + blanket(20)
    return c


def _src_swap_post():
    """Drive gale AS SOURCE through SRC_* + swap pd_task states (the bulk of pd_task's uncovered:
    SRC_DISCOVERY/SRC_GET_SINK_CAP/DR_SWAP/SRC_SWAP_*/VCONN_SWAP_*/HARD_RESET). gale sources
    (PartnerSink + `pd dualrole source`), partner sends a Request to complete the source contract ->
    SRC_READY, then gale-initiated swaps with the partner auto-Accepting (fire_swap = COMPs WITHOUT
    ExpectContractMsg so GoodCRC+Accept deliver) drive the swap states."""
    import pd_encode as pe
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    sink_cap = (pe.header(4, 1, 0), [0x2601912C])
    c += ['sysbus.dma1 SetReply 8 "%s"' % hexmsg(sink_cap)]
    def fire_swap(t="0.12"):
        f = []
        for _ in range(4):
            f += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
        return f + ['emulation RunFor "%s"' % t]
    # gale sources; deliver a sink Request so gale completes the source contract -> SRC_READY
    c += cc("pd dualrole source") + ['emulation RunFor "0.25"']
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.REQUEST(0, 1, 150))]
    c += fire_swap("0.2") + fire_swap("0.2")
    # gale-initiated swaps + get-sink-cap + hard reset from the source role -> SRC swap states
    for action in ("pd 0 swap vconn", "pd 0 swap data", "pd 0 swap power", "pd 0 vdm version",
                   "pd 0 swap vconn", "pd 0 soft"):
        c += cc(action) + ['emulation RunFor "0.04"'] + fire_swap("0.12") + fire_swap("0.12")
    # partner sends Get_Sink_Cap to gale-as-source -> SRC_GET_SINK_CAP response
    c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.ctrl(8, 4))] + fire_swap("0.12")
    c += cc("pd 0 hard") + ['emulation RunFor "0.3"']
    return c


def _src_state_inject_post():
    """Inject pd[0] into each SRC-side task_state with SOURCE power_role + contract flags, then RunFor
    long enough for pd_task's timeout-wake to re-run the loop and execute that case (driving the SRC
    states the handshake-based scenarios can't reach). pd[0]=0x20001150: power_role@0, data_role@1,
    flags@2(u16), task_state@6, cc_state@40(0x20001178). EC unit-test-style injection (real handler
    branches on valid injected struct)."""
    PR, DR, FL, TS, CC = 0x20001150, 0x20001151, 0x20001152, 0x20001156, 0x20001178
    def w16(a, v): return ['sysbus WriteByte 0x%X %d' % (a, v & 0xFF), 'sysbus WriteByte 0x%X %d' % (a + 1, (v >> 8) & 0xFF)]
    c = []
    # SRC states 15..39 (SRC_DISCONNECTED..BIST_TX) with source role + EXPLICIT_CONTRACT|VCONN_ON flags
    for st in range(15, 40):
        for fl in (0x0040, 0x1040, 0x0440, 0x0000):     # EXPLICIT_CONTRACT / +VCONN / +DATA_SWAPPED
            c += ['sysbus WriteByte 0x%X 1' % PR, 'sysbus WriteByte 0x%X 1' % DR,
                  'sysbus WriteByte 0x%X 1' % CC]
            c += w16(FL, fl)
            c += ['sysbus WriteByte 0x%X %d' % (TS, st), 'emulation RunFor "0.06"']
    return c


def _snk_state_inject_post():
    """Complement srcinj: inject the SNK + swap/reset task_states (2..14, 35..39) with SINK role +
    contract flags + cc_state, RunFor to wake pd_task and run each case. Sweep data_role and a richer
    flag set so the in-case role/flag branches flip. pd[0]=0x20001150."""
    PR, DR, FL, TS, CC, MID, POL = 0x20001150, 0x20001151, 0x20001152, 0x20001156, 0x20001178, 0x20001154, 0x20001155
    def w16(a, v): return ['sysbus WriteByte 0x%X %d' % (a, v & 0xFF), 'sysbus WriteByte 0x%X %d' % (a + 1, (v >> 8) & 0xFF)]
    c = []
    states = list(range(2, 15)) + list(range(35, 40))   # SNK_* + swap/reset + BIST
    for st in states:
        for dr, fl, cc in ((0, 0x0040, 1), (1, 0x0440, 1), (0, 0x1040, 2), (1, 0x004a, 0), (0, 0x0000, 1)):
            c += ['sysbus WriteByte 0x%X 0' % PR, 'sysbus WriteByte 0x%X %d' % (DR, dr),
                  'sysbus WriteByte 0x%X %d' % (CC, cc), 'sysbus WriteByte 0x%X 2' % MID,
                  'sysbus WriteByte 0x%X %d' % (POL, st & 1)]
            c += w16(FL, fl)
            c += ['sysbus WriteByte 0x%X %d' % (TS, st), 'emulation RunFor "0.05"']
    return c


def _inject_deliver_post():
    """Synthesis: pd_task's remaining branches mostly read the RECEIVED MESSAGE (sp+0x4c/0x30), so
    injection alone can't flip them. Establish a contract, then for each target state inject
    task_state and DELIVER a crafted message + fire COMP so gale's pd_rx fills the message buffer and
    the injected-state case processes it (the message-processing branches run on real delivered data)."""
    import pd_encode as pe
    TS = 0x20001156
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
        c += ['sysbus.dma1 SetReply %d "%s"' % (i, hexmsg(pe.ACCEPT(i)))]
    for m in (pe.SRC_CAP, pe.ACCEPT(1), pe.PS_RDY(2)):
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    for _ in range(2):
        c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.2"']
    # messages to feed: Source_Cap, Request, Accept, PS_RDY, Reject, Wait, swaps, VDM, BIST, Get_*
    pdos = [0x2201912C, 0x0002D12C]
    msgs = [(pe.header(1, 2, 3), pdos), pe.REQUEST(3, 1, 150), pe.ctrl(3, 3), pe.ctrl(6, 3),
            pe.ctrl(4, 3), pe.ctrl(12, 3), pe.ctrl(9, 3), pe.ctrl(10, 3), pe.ctrl(11, 3),
            pe.ctrl(7, 3), pe.ctrl(8, 3), (pe.header(15, 1, 3), [0xFF008001]), (pe.header(3, 1, 3), [0])]
    # state x message x FLAGS matrix: also set pd[0] flags/role so message-processing branches that
    # gate on contract flags (EXPLICIT_CONTRACT/DATA_SWAPPED/VCONN_ON/CHECK_*_ROLE) flip too.
    FL, PR, DR = 0x20001152, 0x20001150, 0x20001151
    def w16(a, v): return ['sysbus WriteByte 0x%X %d' % (a, v & 0xFF), 'sysbus WriteByte 0x%X %d' % (a + 1, (v >> 8) & 0xFF)]
    flagsets = [(0, 0x0040), (1, 0x0440), (0, 0x1240), (1, 0x0640)]   # (drole, flags) combos
    for st in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
               29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39):
        for dr, fl in flagsets:
            for m in msgs[:7]:
                c += ['sysbus WriteByte 0x%X %d' % (DR, dr)] + w16(FL, fl)
                c += ['sysbus WriteByte 0x%X %d' % (TS, st)]
                c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m), 'sysbus.dma1 ExpectContractMsg']
                for _ in range(2):
                    c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
                c += ['emulation RunFor "0.015"']
    return c


def _ctrl_swap_post():
    """handle_ctrl_request (usb_pd_protocol.c:843-955) per-control-type x task_state arms — the swap/
    reset COMPLETION branches: a PS_RDY/REJECT/WAIT/ACCEPT control msg received WHILE pd[port] is in a
    specific swap/reset state runs a chain of `if (pd[port].task_state == <STATE>) set_state(...)`. These
    are the bulk of pd_task's unreached state-dispatch arms (cmp [r5+6] vs 0x0c/0x0d/0x1b/0x1c/0x1f/0x20/
    0x21/0x23). injdel swept states x msgs but missed these exact (type,state) pairs/flags. Mechanism =
    the proven inject+deliver: pd_task's loop runs handle_request(incoming) BEFORE the main switch using
    the CURRENT task_state, so injecting task_state then delivering the matching ctrl msg makes
    handle_ctrl_request take the injected-state arm. Establish a SNK contract first (valid roles/flags),
    then per pair STAGE the ctrl msg + inject task_state(+power_role+flags) + fire COMP so pd_rx delivers
    it. State enum (verified vs disasm immediates): SNK_DISCOVERY=6, SNK_REQUESTED=7, SNK_SWAP_INIT=10,
    SNK_SWAP_SRC_DISABLE=12, SNK_SWAP_STANDBY=13, DR_SWAP=27, SRC_SWAP_INIT=28, SRC_SWAP_STANDBY=31,
    VCONN_SWAP_SEND=32, VCONN_SWAP_INIT=33, SOFT_RESET=35. Flags: EXPLICIT_CONTRACT=0x40, VCONN_ON=0x1000."""
    import pd_encode as pe
    TS, PR, DR, FL = 0x20001156, 0x20001150, 0x20001151, 0x20001152
    def hexmsg(m):
        sm = pe.encode_message(*m)
        return (sm + bytes([(sm[-1] + 8 * (i + 1)) & 0xFF for i in range(8)])).hex()
    def w16(a, v):
        return ['sysbus WriteByte 0x%X %d' % (a, v & 0xFF), 'sysbus WriteByte 0x%X %d' % (a + 1, (v >> 8) & 0xFF)]
    c = ['sysbus.dma1 ClearResponses', 'sysbus.dma1 ReactiveEnabled true',
         'sysbus.dma1 GoodCrcMsgIdAddress 0x20001154']
    for i in range(8):
        c += ['sysbus.dma1 SetGoodCrc %d "%s"' % (i, hexmsg(pe.ctrl(1, i)))]
    for m in (pe.SRC_CAP, pe.ACCEPT(1), pe.PS_RDY(2)):       # establish a SNK contract
        c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(m)]
    for _ in range(2):
        c += ['sysbus.dma1 ExpectContractMsg', 'sysbus.exti FireComp 21', 'emulation RunFor "0.2"']
    PS_RDY, REJECT, WAIT, ACCEPT = 6, 4, 12, 3
    EC, VC = 0x40, 0x40 | 0x1000
    # (ctrl_type, [(task_state, power_role, flags)...]) straight from the handle_ctrl_request source chains
    pairs = [
        (PS_RDY, [(12, 0, EC), (31, 1, EC), (33, 1, VC), (6, 0, EC), (13, 0, EC)]),
        (REJECT, [(27, 1, EC), (32, 1, EC), (28, 1, EC), (10, 0, EC), (7, 0, EC)]),
        (WAIT,   [(27, 1, EC), (32, 1, EC), (28, 1, EC), (10, 0, EC), (7, 0, EC)]),
        (ACCEPT, [(35, 0, EC), (27, 1, EC), (32, 1, EC), (28, 1, EC), (10, 0, EC), (7, 0, EC)]),
    ]
    for ctype, states in pairs:
        for st, pr, fl in states:
            c += ['sysbus.dma1 StageResponse "%s"' % hexmsg(pe.ctrl(ctype, 3))]
            c += ['sysbus WriteByte 0x%X %d' % (PR, pr), 'sysbus WriteByte 0x%X 0' % DR]
            c += w16(FL, fl)
            c += ['sysbus WriteByte 0x%X %d' % (TS, st), 'sysbus.dma1 ExpectContractMsg']
            for _ in range(2):
                c += ['sysbus.exti FireComp 21', 'emulation RunFor "0.000008"']
            c += ['emulation RunFor "0.02"']
    return c


def _hcdebug_post():
    """host_command_process (host_command.c:563) debug/dedup arms: set hcdebug to each level
    (off/normal/params/event) then send host commands (with params, and REPEATED same command for
    the hc_prev_cmd dedup branch) so the `if (hcdebug)` / `== NORMAL` / `>= PARAMS && params_size` /
    `command == hc_prev_cmd` / response-size arms all run."""
    import hostcmd
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    def hcp(cmd, data):
        return ['sysbus.i2c1 HostCmd "%s"' % hostcmd._pkt(cmd, 0, 3, data), 'emulation RunFor "0.05"']
    c = []
    for lvl in ("off", "normal", "params", "event"):
        c += cc("hcdebug " + lvl) + ['emulation RunFor "0.05"']
        c += hcp(0x01, [0x44, 0x33, 0x22, 0x11])    # HELLO with params + response
        c += hcp(0x01, [0x44, 0x33, 0x22, 0x11])    # REPEAT same cmd -> hc_prev_cmd dedup
        c += hcp(0x02, [])                          # GET_VERSION (no params, has response)
        c += hcp(0x02, [])                          # repeat
        c += hcp(0x00, [])                          # PROTO_VERSION
        c += hcp(0xff, [])                          # invalid cmd
    return c


def _hook_inject_post():
    """hook_task (hooks.c) processes __deferred_until[] (captured @0x20001ea8, 6 x uint64 deadlines).
    Its arms (deadline && < t; find soonest future) need a MIX of due/unscheduled/future deferred
    deadlines simultaneously — rarely all present in normal operation. Inject a mix then RunFor so the
    idle task runs hook_task over it."""
    DU = 0x20001ea8
    mixes = [
        [1, 0, 0xFFFFFFFFFFFF, 2, 0x7FFFFFFF, 0],          # due / unsched / far / due / future / unsched
        [0, 5, 3, 0xFFFFFFFFFFFF, 0, 7],
        [0xFFFFFFFFFFFF, 0xFFFFFFFFFFFE, 0, 1, 0, 0x100000000],
        [0, 0, 0, 0, 0, 0],                                # all unscheduled
        [1, 2, 3, 4, 5, 6],                                # all due (small)
    ]
    c = []
    for mix in mixes:
        for i, v in enumerate(mix):
            c += ['sysbus WriteDoubleWord 0x%X 0x%08X' % (DU + i * 8, v & 0xFFFFFFFF),
                  'sysbus WriteDoubleWord 0x%X 0x%08X' % (DU + i * 8 + 4, (v >> 32) & 0xFFFFFFFF)]
        c += ['emulation RunFor "0.3"']                    # let the idle task run hook_task
    return c


def _flash_ops_post():
    """Drive flash_physical_erase / flash_physical_write / flashread validation + error arms via the
    console flash commands with various offsets/sizes (valid RW-region, invalid, unaligned) + the
    GaleFlash error knobs (StuckBusy timeout, InjectProgErr, InjectWriteProtErr). Invalid offsets hit
    the validation arms without any actual erase/write; the error knobs make the op fail (no real
    corruption — GaleFlash latches the error and returns)."""
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    c = []
    # validation arms (bad/unaligned offset/size -> early return, no op)
    for cmd in ("flasherase 0x1 0x800", "flasherase 0x40000 0x7", "flasherase 0xFFFFFFFF 0x800",
                "flashwrite 0x3 0x100", "flashwrite 0x40000 0xFFFF", "flashread 0x40000 0x40",
                "flashread 0x0 0x20", "flasherase", "flashwrite", "flashread"):
        c += cc(cmd) + ['emulation RunFor "0.05"']
    # error-injected ops (op fails -> EC_ERROR_* arms)
    c += ['sysbus.flashif InjectProgErr true'] + cc("flashwrite 0x40000 0x100") + ['emulation RunFor "0.1"']
    c += ['sysbus.flashif InjectWriteProtErr true'] + cc("flasherase 0x40000 0x800") + ['emulation RunFor "0.1"']
    c += ['sysbus.flashif StuckBusy true'] + cc("flasherase 0x41000 0x800") + ['emulation RunFor "0.2"']
    c += ['sysbus.flashif StuckBusy false']
    return c


def _sysjump_arms_post():
    """system_run_image_copy / command_sysjump arms (system.c): system_is_locked (:544), switch(copy)
    RO/RW/unknown (:105), init_addr validation (:588). Lock the system first (syslock) so sysjump is
    REJECTED (no actual jump that would disrupt the trace) -> the is-locked + switch + validation arms
    run safely. Also bad-addr forms hit the validation arm without jumping."""
    def cc(scmd):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (scmd + "\r")]
    c = []
    # before lock: bad-addr / disable forms (validation arms, no jump)
    for cmd in ("sysjump 0xdeadbeef", "sysjump 0", "sysjump 0x20000000", "sysjump disable",
                "sysjump bogus"):
        c += cc(cmd) + ['emulation RunFor "0.05"']
    # lock, then RO/RW/A -> system_is_locked() true -> rejected (no jump) -> locked arm
    c += cc("syslock") + ['emulation RunFor "0.1"']
    for cmd in ("sysjump RO", "sysjump RW", "sysjump A", "sysjump disable", "sysjump 0x8010000"):
        c += cc(cmd) + ['emulation RunFor "0.05"']
    return c


def scenarios(boot):
    s = []
    # system_run_image_copy / sysjump arms via locked-system rejection + bad-addr validation (no jump)
    s.append(("sysjarms", [], [], "2.0", _sysjump_arms_post()))
    s.append(("sysjarms_rw", [], ["sysjump rw"], "2.0", _sysjump_arms_post()))
    # flash_physical_erase/write/read validation + error arms via console flash commands + error inject
    s.append(("flashops", [], [], "2.0", _flash_ops_post()))
    s.append(("flashops_rw", [], ["sysjump rw"], "2.0", _flash_ops_post()))
    # hook_task deferred-deadline injection (mix of due/unsched/future) -> deferred-processing arms
    s.append(("hookinj", [], [], "2.0", _hook_inject_post()))
    s.append(("hookinj_rw", [], ["sysjump rw"], "2.0", _hook_inject_post()))
    # host_command_process debug-level + dedup arms (hcdebug levels x repeated host commands)
    s.append(("hcdbg", [], [], "2.0", _hcdebug_post()))
    s.append(("hcdbg_rw", [], ["sysjump rw"], "2.0", _hcdebug_post()))
    # inject task_state + DELIVER message -> pd_task message-processing branches (sp+0x4c reads)
    s.append(("injdel", ['sysbus.adc ForceSourceCc true'], [], "2.0", _inject_deliver_post()))
    s.append(("injdel_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _inject_deliver_post()))
    # handle_ctrl_request swap/reset completion arms (the pd_task state-dispatch cluster): inject each
    # swap state + deliver the matching PS_RDY/REJECT/WAIT/ACCEPT ctrl msg
    s.append(("ctrlswap", ['sysbus.adc ForceSourceCc true'], [], "2.0", _ctrl_swap_post()))
    s.append(("ctrlswap_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _ctrl_swap_post()))
    # REAL swap-handshake completion: gale-initiated swaps + blanket-COMP so the sync GoodCRC + Accept
    # both land while gale holds the swap state -> handle_ctrl_request swap arms (the pd_task plateau)
    s.append(("swapblanket", ['sysbus.adc ForceSourceCc true'], [], "2.5", _swap_blanket_post()))
    s.append(("swapblanket_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.5", _swap_blanket_post()))
    # REJECT/WAIT swap-completion arms: contract via sustained firing, then partner REJECTs/WAITs gale's swaps
    s.append(("swapreject", ['sysbus.adc ForceSourceCc true'], [], "3.0", _swap_reject_post()))
    s.append(("swapreject_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "3.0", _swap_reject_post()))
    # receive-side: partner sends swap/control REQUESTS to gale-in-READY (confirmed contract)
    s.append(("partswap", ['sysbus.adc ForceSourceCc true'], [], "2.5", _partner_swap_post()))
    s.append(("partswap_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.5", _partner_swap_post()))
    # STATE-HELD inject+deliver (last_state==task_state so the swap case is skipped, holding the state)
    s.append(("ctrlswaph", ['sysbus.adc ForceSourceCc true'], [], "2.0", _ctrl_swap_held_post()))
    s.append(("ctrlswaph_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _ctrl_swap_held_post()))
    # message-content fuzz: varied headers/objects to gale-in-contract -> the 184 one-dir field tests
    s.append(("pdmsgfuzz", ['sysbus.adc ForceSourceCc true'], [], "2.5", _pd_msgfuzz_post()))
    s.append(("pdmsgfuzz_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.5", _pd_msgfuzz_post()))
    # SNK + swap/reset/BIST state injection (sink role + flags + wake), RO + RW
    s.append(("snkinj", ['sysbus.adc ForceSourceCc true'], [], "1.8", _snk_state_inject_post()))
    s.append(("snkinj_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "1.8", _snk_state_inject_post()))
    # targeted SRC-state injection (source role + each SRC task_state + wake) — RO + RW, PartnerSink
    s.append(("srcinj", ['sysbus.adc PartnerSink true'], [], "1.8", _src_state_inject_post()))
    s.append(("srcinj_rw", ['sysbus.adc PartnerSink true'], ["sysjump rw"], "1.8", _src_state_inject_post()))
    # gale-as-SOURCE through SRC_*/swap/vconn/hard-reset pd_task states (PartnerSink + source contract)
    s.append(("srcswap", ['sysbus.adc PartnerSink true'], [], "2.0", _src_swap_post()))
    s.append(("srcswap_rw", ['sysbus.adc PartnerSink true'], ["sysjump rw"], "2.0", _src_swap_post()))
    # smaller PD functions: dev-voltage requests / vdm / dualrole over a multi-PDO contract
    s.append(("pdsmall", ['sysbus.adc ForceSourceCc true'], [], "2.0", _pd_smallfns_post()))
    s.append(("pdsmall_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _pd_smallfns_post()))
    # hc_usb_pd_control (0x101) param matrix with a live contract (info-fill arms)
    s.append(("pdctrl", ['sysbus.adc ForceSourceCc true'], [], "2.0", _usb_pd_control_post()))
    s.append(("pdctrl_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _usb_pd_control_post()))
    s += _flash_optb_scenarios()
    s += _flash_preinit_scenarios()
    # PHY-level malformed/special RX messages -> pd_analyze_rx decode error/SOP'/reset arms
    s.append(("pdrxmal", ['sysbus.adc ForceSourceCc true'], [], "2.0", _pd_rx_malformed_post()))
    s.append(("pdrxmal_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _pd_rx_malformed_post()))
    s += _reset_cause_scenarios()
    # system_common_pre_init jump-data block (0x6ce4): plant crafted struct jump_data + reset_flags==0
    s += _jump_data_scenarios()
    # corrected command_tcpc grammar (`tcpc <port> clock/state`) + pd/md/reboot retries, with contract
    s.append(("tcpcfix", ['sysbus.adc ForceSourceCc true'], _tcpc_fixed_battery(), "2.0", []))
    s.append(("tcpcfix_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _tcpc_fixed_battery(), "2.0", []))
    # command_flashinfo protect-state arms via the GaleFlash WRPR/StuckBusy knobs (set post-boot)
    s.append(("flashinfo_prot", [], [], "2.0", _flashinfo_protect_post()))
    s.append(("flashinfo_prot_rw", [], ["sysjump rw"], "2.0", _flashinfo_protect_post()))
    # flash_set_protect DEEP arms (0x47cc, 19 unreached): assert WP_L low post-boot + RO_AT_BOOT pstate
    # to bypass the line-507 early-return, then drive ALL_NOW/ALL_AT_BOOT/RO_NOW arms (RO_NOW via hostcmd)
    s.append(("flashprot_deep", [], [], "2.0", _flash_protect_deep_post()))
    s.append(("flashprot_deep_rw", [], ["sysjump rw"], "2.0", _flash_protect_deep_post()))
    # host_packet_receive (0x5314, 12 unreached): inject RAW malformed packets (bad version/checksum,
    # truncated, data_len-overclaim, oversized) -> the EC_RES_INVALID_*/REQUEST_TRUNCATED goto arms
    s.append(("hostpkt_malformed", [], [], "2.0", _hostpkt_malformed_post()))
    s.append(("hostpkt_malformed_rw", [], ["sysjump rw"], "2.0", _hostpkt_malformed_post()))
    # hc_remote_flash (0x7a60, EC_CMD_USB_PD_FW_UPDATE 0x110, 22 unreached): pd-disable + vdm_state clear
    # so FLASH_WRITE/ERASE_SIG enter the VDM send/wait loops -> the loop + TIMEOUT arms (3256-3288)
    s.append(("pdfwflash", [], [], "2.0", _pd_fw_flash_post()))
    s.append(("pdfwflash_rw", [], ["sysjump rw"], "2.0", _pd_fw_flash_post()))
    # source-precise battery for md/reboot/sysjump/tcpc/hash remaining arms (from the C conditions)
    s.append(("srcprec", ['sysbus.adc ForceSourceCc true'], _src_precise_battery(), "2.0", []))
    s.append(("srcprec_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _src_precise_battery(), "2.0", []))
    # grammar-correct command_pd battery (from source) — RO + RW, with a contract for state-display arms
    s.append(("pdgram", ['sysbus.adc ForceSourceCc true'], _pd_grammar_battery(), "2.0", []))
    s.append(("pdgram_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _pd_grammar_battery(), "2.0", []))
    # command_tcpc dump/clock/state subcommands (correct syntax) + remaining hash/md
    s.append(("console_bat5", ['sysbus.adc ForceSourceCc true'], _console_battery5(), "2.0", []))
    s.append(("console_bat5_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _console_battery5(), "2.0", []))
    # hash-state sequence + md alignment/ascii arms
    s.append(("console_bat4", ['sysbus.adc ForceSourceCc true'], _console_battery4(), "2.0", []))
    s.append(("console_bat4_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _console_battery4(), "2.0", []))
    # correct-syntax console args (spixfer 5-token, etc.) -> the parse/transfer arms prior batteries missed
    s.append(("console_bat3", ['sysbus.adc ForceSourceCc true'], _console_battery3(), "2.0", []))
    s.append(("console_bat3_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _console_battery3(), "2.0", []))
    # deeper console args for the specific remaining handler arms (md ascii / spixfer valid / hash / ...)
    s.append(("console_bat2", ['sysbus.adc ForceSourceCc true'], _console_battery2(), "2.0", []))
    s.append(("console_bat2_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _console_battery2(), "2.0", []))
    # comprehensive console-command battery -> per-handler dispatch/validation arms (RO + RW)
    s.append(("console_bat", ['sysbus.adc ForceSourceCc true'], _console_battery(), "2.0", []))
    s.append(("console_bat_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _console_battery(), "2.0", []))
    # exhaustive `pd` console subcommand + malformed-arg battery -> command_pd dispatch/validation arms
    s.append(("pdcmd", ['sysbus.adc ForceSourceCc true'], _pd_cmd_battery(), "2.0", []))
    s.append(("pdcmd_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"] + _pd_cmd_battery(), "2.0", []))
    # partner-initiated receive handlers in SOURCE role (gale sourcing)
    s.append(("partinit_src", ['sysbus.adc PartnerSink true'], [], "2.0", _partinit_src_post()))
    s.append(("partinit_src_rw", ['sysbus.adc PartnerSink true'], ["sysjump rw"], "2.0", _partinit_src_post()))
    # partner-INITIATED messages -> gale's receive-side handlers + response paths (the other half)
    s.append(("partinit", ['sysbus.adc ForceSourceCc true'], [], "2.0", _partner_initiated_post()))
    s.append(("partinit_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _partner_initiated_post()))
    # LONG emulated-time soaks -> time-based branches (periodic hooks, watchdog, timeouts, retries)
    s.append(("soak_idle", [], [], "2.0", _soak_post(30)))
    s.append(("soak_acc", ['sysbus.adc ForceAccessory true'], [], "2.0", _soak_post(30)))
    s.append(("soak_contract", ['sysbus.adc ForceSourceCc true'], [], "2.0", _soak_post(30, contract=True)))
    s.append(("soak_idle_rw", [], ["sysjump rw"], "2.0", _soak_post(30)))
    # swap/reset handshake completion (GoodCRC+Accept delivery without contract-force), RO + RW
    s.append(("pdswap", ['sysbus.adc ForceSourceCc true'], [], "2.0", _pd_swap_post()))
    s.append(("pdswap_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _pd_swap_post()))
    # local (no-partner) pd_task states: DISABLED/SUSPENDED/DEBOUNCE via disable/enable + CC cycling
    s.append(("pdlocal", [], [], "2.0", _pd_local_states_post()))
    s.append(("pdlocal_rw", [], ["sysjump rw"], "2.0", _pd_local_states_post()))
    # drive PD state machine through SRC/swap/reset/BIST states via the full pd command set, 2 partners
    s.append(("pddrive_sink", ['sysbus.adc PartnerSink true'], _pd_cmds(), "2.0", []))
    s.append(("pddrive_src", ['sysbus.adc ForceSourceCc true'], _pd_cmds(), "2.0", []))
    s.append(("pddrive_rw", ['sysbus.adc PartnerSink true'], ["sysjump rw"] + _pd_cmds(), "2.0", []))
    # FLASH error-path coverage (option-byte/WP programming, the 0x8000f00/f44 cluster): inject
    # PGERR / WRPRTERR / stuck-BSY (GaleFlash knobs) then drive flashwp so the firmware's
    # EC_ERROR_* / timeout branches execute (success paths already covered by boot flash_pre_init).
    s.append(("flasherr_pg", ['sysbus.flashif InjectProgErr true'],
              ['flashwp now', 'flashwp enable', 'flashinfo'], "2.0", []))
    s.append(("flasherr_wp", ['sysbus.flashif InjectWriteProtErr true'],
              ['flashwp enable', 'flashwp now', 'flashwp rw'], "2.0", []))
    s.append(("flasherr_busy", ['sysbus.flashif StuckBusy true'],
              ['flashwp now', 'flashwp enable'], "2.0", []))
    s.append(("flashok", [], ['flashwp now', 'flashwp enable', 'flashwp disable',
                              'flashwp rw', 'flashwp norw', 'flashinfo'], "2.0", []))
    # internal-sub-branch coverage via cc_state/flags injection per task_state
    s.append(("stinj2", [], [], "1.5", _state_inject2_post()))
    # full PD message-type battery (control 1..21 + data + role-swaps), RO and RW, in live contract
    s.append(("msgbat", ['sysbus.adc ForceSourceCc true'], [], "2.0", _msg_battery_post()))
    s.append(("msgbat_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _msg_battery_post()))
    # deeper sub-branch coverage via struct +0x50/+0x58 injection per task_state, 2 CC contexts
    s.append(("stinj3", [], [], "1.5", _state_inject3_post()))
    s.append(("stinj3_src", ['sysbus.adc ForceSourceCc true'], [], "1.5", _state_inject3_post()))
    s.append(("stinj2_src", ['sysbus.adc ForceSourceCc true'], [], "1.5", _state_inject2_post()))
    # per-state handler coverage via task_state/vdm_state injection (EC unit-test style), 3 CC contexts
    s.append(("stinj", [], [], "1.5", _state_inject_post()))
    s.append(("stinj_src", ['sysbus.adc ForceSourceCc true'], [], "1.5", _state_inject_post()))
    s.append(("stinj_acc", ['sysbus.adc ForceAccessory true'], [], "2.0", _state_inject_post()))
    s.append(("stinj_rw", [], ["sysjump rw"], "1.5", _state_inject_post()))
    # VDM state-machine BUSY/WAIT_RSP_BUSY coverage (RE-targeted), RO + RW
    s.append(("vdmbusy", ['sysbus.adc ForceSourceCc true'], [], "2.0", _vdm_busy_post()))
    s.append(("vdmbusy_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _vdm_busy_post()))
    s.append(("vdmwait", ['sysbus.adc ForceSourceCc true'], [], "2.0", _vdm_waitbusy_post()))
    # live PD-state injection (drive each pd_task state's dispatcher branch), RO and RW
    s.append(("pdinject", [], [], "1.5", _pd_inject_post()))
    s.append(("pdinject_rw", [], ["sysjump rw"], "1.5", _pd_inject_post()))
    # ADC extreme-value sweep (OVP/OCP/vbus-present error edges), RO and RW
    s.append(("fextreme", [], [], "1.5", _fault_extreme_post()))
    s.append(("fextreme_rw", [], ["sysjump rw"], "1.5", _fault_extreme_post()))
    # DFP VDM discovery handshake (partner now VDM-aware), PartnerSink so gale can source/DFP
    s.append(("dfpvdm", ['sysbus.adc PartnerSink true'], [], "1.5", _dfp_vdm_post()))
    s.append(("dfpvdm_rw", ['sysbus.adc PartnerSink true'], ["sysjump rw"], "1.5", _dfp_vdm_post()))
    # VDM field sweep (structured/unstructured x cmd-type x cmd), RO and RW
    s.append(("pdvdm", ['sysbus.adc ForceSourceCc true'], [], "2.0", _vdm_sweep_post()))
    s.append(("pdvdm_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _vdm_sweep_post()))
    # hook firing: long idle (TICK/SECOND/deferred) + sysjump both directions
    s.append(("pdhooks", [], [], "1.5", _hook_post()))
    s.append(("pdhooks_rw", [], ["sysjump rw"], "1.5", _hook_post()))
    s.append(("sysjmp", [], [], "1.5", _sysjump_both_post()))
    # host-command full-range sweep, RO and RW
    s.append(("hcsweep", [], [], boot, _hostcmd_sweep_post()))
    s.append(("hcsweep_rw", [], ["sysjump rw"], boot, _hostcmd_sweep_post()))
    # CC attach/detach cycles (disconnect/debounce both directions), RO and RW
    s.append(("pdattach", [], [], "1.5", _attach_cycle_post()))
    s.append(("pdattach_rw", [], ["sysjump rw"], "1.5", _attach_cycle_post()))
    # message-injection: BIST + unexpected-message + reset-recover, RO and RW
    s.append(("pdbist", ['sysbus.adc ForceSourceCc true'], [], "2.0", _pd_bist_post()))
    s.append(("pdbist_rw", ['sysbus.adc ForceSourceCc true'], ["sysjump rw"], "2.0", _pd_bist_post()))
    # dual-role / PD-console sweep, RO and RW images
    s.append(("pdcon", [], [], boot, _pd_console_post()))
    s.append(("pdcon_rw", [], ["sysjump rw"], boot, _pd_console_post()))
    # dual-role sweep WHILE a sink partner is attached (so FORCE_SOURCE actually enters SRC states
    # and the mode flips interact with a live CC) — drives the role-change branches with side effects.
    s.append(("pdcon_sink", ['sysbus.adc PartnerSink true'], [], "1.5", _pd_console_post()))
    s.append(("pdcon_acc", ['sysbus.adc ForceAccessory true'], [], "2.0", _pd_console_post()))
    return s


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=CAPTURED)
    ap.add_argument("--only", default=None, help="comma-separated scenario names to run")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    binpath = os.path.abspath(args.bin)
    os.makedirs(TMP, exist_ok=True)
    # bin-specific pkl so a rebuilt run can't clobber the captured pdstate cache
    out = os.path.join(TMP, "rebuilt_pdstate_edges.pkl" if "rebuilt" in os.path.basename(binpath)
                       else "pdstate_edges.pkl")
    executed, edges = set(), set()
    if os.path.exists(out):                       # accumulate across runs
        try:
            with open(out, "rb") as f:
                pe, ped = pickle.load(f)
            executed |= set(pe); edges |= set(ped)
            print("loaded prior pdstate_edges.pkl: %d edges, %d PCs" % (len(edges), len(executed)))
        except Exception as e:
            print("could not load prior pkl (%s); fresh" % e)
    scns = scenarios("2.0")
    if only:
        scns = [t for t in scns if t[0] in only]
    print("PD-state lever: %d scenarios on %s" % (len(scns), os.path.basename(binpath)))
    for (n, m, c, b, p) in scns:
        print("  scenario: %-14s" % n)
        C.fold_edges(C.run_scenario(n, m, c, b, p, binpath), executed, edges)
        with open(out, "wb") as f:                # checkpoint after each scenario
            pickle.dump((executed, edges), f)
    print("saved %d edges, %d PCs -> tmp/pdstate_edges.pkl" % (len(edges), len(executed)))


if __name__ == "__main__":
    main()
