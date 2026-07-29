"""Generate WHY-UNCOVERED.md: assign every uncovered-branch-bearing function to a reachability
REASON CLASS (derived from its source file + the disassembled missing-direction), and emit, per
class and per function: why the branches aren't reached + what would be required. 'Why/required'
are stated at the reason-CLASS level (defensible from subsystem+cause); function-specific notes are
added only where independently confirmed elsewhere in the campaign. Pure parse of the verified
UNCOVERED-BY-FUNCTION.md — no Renode."""
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RPT = os.path.join(HERE, "UNCOVERED-BY-FUNCTION.md")

hdr_re = re.compile(r"^## (0x[0-9a-fA-F]+)\s+`(.+?)`\s+\(conf:(\w+)\)\s*$")
src_re = re.compile(r"^\*\*Source:\*\*\s+(\S+)")
cnt_re = re.compile(r"\| (\d+) uncovered \((\d+) unreached, (\d+) one-dir; (\d+) in RW mirror\)")
bul_re = re.compile(r"^- \*\*(0x[0-9a-fA-F]+)\*\*(\s+\(RW mirror\))?\s+\[([a-z?-]+)\]\s+—\s+(.*)$")

funcs = []
cur = None
for line in open(RPT):
    line = line.rstrip("\n")
    mh = hdr_re.match(line)
    if mh:
        if cur:
            funcs.append(cur)
        cur = dict(fs=mh.group(1), name=mh.group(2), conf=mh.group(3), src="?", branches=[])
        continue
    if cur is None:
        continue
    ms = src_re.match(line)
    if ms:
        cur["src"] = re.sub(r":\d+$", "", ms.group(1))   # strip trailing ':<line>' so basename is clean
        continue
    mb = bul_re.match(line)
    if mb:
        cur["branches"].append(dict(addr=mb.group(1), rw=bool(mb.group(2)),
                                    state=mb.group(3), cause=mb.group(4)))
if cur:
    funcs.append(cur)

# ---- reason classes ----
CLASSES = {
 "R1": ("PD state machine — blocking dispatcher",
        "pd_task and the policy handlers it calls run inside the cooperative dispatcher at 0x8007f8e; "
        "the protocol state (`pd[port].task_state`) only advances when LIVE PD traffic arrives in the "
        "right order. Direct function-calls cannot drive them, and many SOURCE / swap / error states are "
        "entered only one-directionally by the campaign, so the compare against a state/flag/field has only "
        "ever gone one way.",
        "Deliver a specific message TYPE+FIELD while the firmware sits in the exact target state — which "
        "usually first requires DRIVING the firmware into that state (e.g. SRC_GET_SINK_CAP, a swap, a "
        "retry-exhaust, or the data-request handler 0x80083f0 which is only reached in SRC_DISCOVERY). "
        "Several targets need a state the partner model can't currently push the firmware into."),
 "R2": ("PD receive / phy bit-decode",
        "These decode the raw BMC/4b5b line: preamble search, bit dequeue, symbol/CRC checks. The campaign "
        "stages WELL-FORMED messages at the message layer (dma1 StageResponse), so the malformed-symbol, "
        "bad-preamble, truncated/over-long-frame, and bad-5b-code arms never execute.",
        "Inject raw RX BITSTREAMS one layer below the current message staging: short/long preambles, illegal "
        "5b codes, truncated frames, deliberate CRC/symbol errors — i.e. extend the phy model to feed the "
        "decoder arbitrary edge sequences rather than pre-validated frames."),
 "R3": ("Peripheral-model gap (SPI/DMA/I2C/ADC/USART/USB-ep)",
        "The branch is gated on a hardware status bit, completion event, or error flag that the Renode "
        "peripheral model does not generate: SPI DMA transfer-complete/busy timing, DMA half-transfer, I2C "
        "ARLO/BERR/AF in a specific phase, USART overrun, USB ep enumeration sub-states, ADC EOC timing.",
        "Extend the peripheral model to produce the missing status/event at the right moment (or inject the "
        "bus error in the exact phase). This is emulator work, not stimulus crafting."),
 "R4": ("Boot / init alternate-precondition",
        "*_init / *_pre_init run ONCE during a single boot, so only one hardware configuration is exercised. "
        "The dark arms depend on a different boot-time register value, clock/PLL state, option-byte state, "
        "reset cause, or RO-vs-RW jump context.",
        "Boot under the alternate precondition: RO vs RW (sysjump — partly done), plus a model that presents "
        "the specific RCC/FLASH/PWR/reset-flag register states the untaken arm checks for."),
 "R5": ("Flash fault / protect precondition",
        "Flash program/erase/protect paths: the dark arms are the WRPRT/PGERR error returns, the option-byte "
        "write-protect-asserted gates, and the already-equal fast paths. Normal clean ops only walk the "
        "success ladder; the protect gates need specific WRP/OPTB register state.",
        "Pre-arm the matching fault (GaleFlash InjectProgErr/InjectWriteProtErr/StuckBusy) or option-byte / "
        "WRP register state at the exact call site. Some sites already covered by cov_flashfault; the rest "
        "need a fault the current knobs can't place at that step, or a specific WRP precondition."),
 "R6": ("System / image-copy / jump-tag",
        "Branches gated on jump-data magic+version, image layout (RO/RW/loader), reset/jump reason, or "
        "sysjump tag presence. The single cold-boot + a couple of sysjumps exercise one layout.",
        "Crafted sysjump/reboot scenarios: jump WITH tags present, version/magic mismatch, overwrite-protect "
        "checks, alternate active-image copy. Partly drivable via the console `sysjump`/`reboot` with "
        "prepared jump data; some need specific flash/RAM layout the model fixes."),
 "R7": ("Console / host-command argument",
        "Command handlers whose dark arms are specific argv shapes, sub-commands, parameter structs, version "
        "fields, or an error-return the current invocations didn't hit. Often gated on a precondition (a "
        "connected port, a populated buffer).",
        "Feed the missing console line / host-command params — mostly cheap and drivable. The residue needs "
        "a precondition (e.g. a live PD contract, a non-empty console buffer) set up first."),
 "R8": ("printf / arithmetic operand-value",
        "vfnprintf format-specifier arms and uint64divmod operand-magnitude arms. A direction flips only for a "
        "specific format spec (width/precision/sign/base/length-modifier) or a specific divisor/dividend size.",
        "Drive a print/divide with the exact operand: a CPRINTF using that specifier, or a 64-bit divide with "
        "that magnitude. Some specifiers have NO caller in this firmware → genuine dead code (needs a proof, "
        "e.g. the already-proven 'T' specifier at 0x08005b82)."),
 "R9": ("RTOS / hooks / timer / queue scheduling",
        "Branches gated on multi-task scheduling, deferred-hook deadlines, timer wrap, mutex contention, or "
        "queue full/empty/wrap that a deterministic single-stimulus run does not reach.",
        "Manufacture the timing/contention: multiple simultaneously-pending deferred hooks, a wrapped/full "
        "queue, a contended mutex, a timer at the 32-bit wrap. Some are schedule-deterministic and may be "
        "structurally hard without a second runnable task."),
 "R6b": ("Panic / fault-dump formatting",
        "panic.c register-dump and fault-print arms: dark arms depend on WHICH fault (HardFault vs usage vs "
        "the exception frame contents) and on flags only set on a real CPU exception.",
        "Trigger the specific CPU exception class (or stage the panic-data RAM block) so the dump formatter "
        "walks the untaken register/format arms. Some need a real fault the emulator must raise."),
}


def classify(name, src):
    f = src.split("/")[-1]
    n = name.lower()
    if f == "usb_pd_protocol.c":
        if n == "pd_task":
            return "R1"
        if "analyze_rx" in n or "dequeue" in n or "preamble" in n or n.endswith("_rx") or "receive_message" in n:
            return "R2"
        return "R1"
    if f in ("usb_pd_phy.c", "usb_pd_tcpc.c"):
        return "R2"
    if f in ("usb_pd_policy.c",) or n.startswith("pd_") or "vdm" in n:
        return "R1"
    if f in ("spi.c", "usb_spi.c", "dma.c") or "spi" in n or n.startswith("dma"):
        return "R3"
    if f in ("i2c.c", "i2c-stm32f0.c") or "i2c" in n:
        return "R3"
    if ("adc" in f or "usart" in f or "uart" in f or "clock" in f or f == "gpio.c" or "gpio-f0" in f
            or f in ("usb.c", "usb-stream.c", "usb_console.c")):
        if "init" in n:
            return "R4"
        return "R3"
    if f in ("flash.c", "flash-f0.c", "stm32-flash.c") or "flash" in n or "optb" in n:
        if "init" in n:
            return "R4"
        return "R5"
    if f in ("vfnprintf.c", "printf.c") or n == "uint64divmod" or "divmod" in n:
        return "R8"
    if f in ("hooks.c", "task.c", "timer.c", "queue.c", "queue_policies.c"):
        return "R9"
    if f in ("panic.c", "panic_output.c"):
        return "R6b"
    if f == "system.c" or n.startswith("system_"):
        return "R6"
    if "init" in n or "pre_init" in n:
        return "R4"
    if n.startswith("command_") or n.startswith("host_command") or "console" in f or "console" in n:
        return "R7"
    if f in ("util.c", "crc_hw.h", "stub.c", "main.c", "queue_policies.c", "usb_mux.c"):
        return "R8" if f in ("util.c", "crc_hw.h") else "R7"
    return "R7"


by_class = defaultdict(list)
for fn in funcs:
    cls = classify(fn["name"], fn["src"])
    by_class[cls].append(fn)

order = ["R1", "R2", "R3", "R4", "R5", "R6", "R6b", "R7", "R8", "R9"]
out = ["# Why each uncovered branch is not reached — and what would reach it", "",
       "Generated from the verified `UNCOVERED-BY-FUNCTION.md`. Every uncovered-branch-bearing function "
       "is assigned a **reason class**; *why* and *what's required* are stated at the class level (derived "
       "from the source subsystem + the disassembled missing-direction), with function notes where "
       "independently confirmed.", "",
       "Coverage state legend: **unreached** = block never executed; **taken-only** / **nottaken-only** = "
       "reached but the compare only ever went one way.", ""]
grand = 0
for cls in order:
    fns = sorted(by_class.get(cls, []), key=lambda f: -len(f["branches"]))
    if not fns:
        continue
    n = sum(len(f["branches"]) for f in fns)
    grand += n
    title, why, req = CLASSES[cls]
    out.append("## %s — %s  (%d branches, %d functions)" % (cls, title, n, len(fns)))
    out.append("**Why not reached:** %s" % why)
    out.append("")
    out.append("**What would be required:** %s" % req)
    out.append("")
    for f in fns:
        states = Counter(b["state"] for b in f["branches"])
        sm = ", ".join("%d %s" % (states[k], k) for k in ("unreached", "taken-only", "nottaken-only") if states.get(k))
        out.append("- **`%s`** (%s, conf:%s) — %d uncovered [%s]"
                   % (f["name"], f["src"].split("/")[-1], f["conf"], len(f["branches"]), sm))
        # up to 2 representative RO-side example causes
        ex = [b for b in f["branches"] if not b["rw"]][:2]
        for b in ex:
            c = b["cause"]
            c = c[:160] + ("…" if len(c) > 160 else "")
            out.append("  - `%s` [%s] %s" % (b["addr"], b["state"], c))
    out.append("")
out.append("**Total: %d branches across %d functions.**" % (grand, sum(len(v) for v in by_class.values())))

open(os.path.join(HERE, "WHY-UNCOVERED.md"), "w").write("\n".join(out) + "\n")
print("wrote WHY-UNCOVERED.md")
print("class totals:")
for cls in order:
    fns = by_class.get(cls, [])
    if fns:
        print("  %-4s %-42s %4d branches  %3d funcs"
              % (cls, CLASSES[cls][0], sum(len(f["branches"]) for f in fns), len(fns)))
print("  TOTAL %d branches / %d funcs" % (grand, sum(len(v) for v in by_class.values())))
