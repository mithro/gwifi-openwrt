"""Parse the (verified) UNCOVERED-BY-FUNCTION.md and produce a data-driven categorization of the
1083 uncovered branches: by source file (subsystem), by function, by coverage-state, and by the
disassembled 'missing direction need'. Output drives the why-uncovered analysis."""
import os
import re
from collections import defaultdict, Counter

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
        cur = dict(fs=mh.group(1), name=mh.group(2), conf=mh.group(3), src=None,
                   decl=None, branches=[])
        continue
    if cur is None:
        continue
    ms = src_re.match(line)
    if ms:
        cur["src"] = ms.group(1)
        mc = cnt_re.search(line)
        if mc:
            cur["decl"] = tuple(int(mc.group(i)) for i in range(1, 5))
        continue
    mb = bul_re.match(line)
    if mb:
        cur["branches"].append(dict(addr=mb.group(1), rw=bool(mb.group(2)),
                                    state=mb.group(3), cause=mb.group(4)))
if cur:
    funcs.append(cur)


def subsystem(src, name):
    f = (src or "").split("/")[-1]
    table = {
        "usb_pd_protocol.c": "PD protocol state machine",
        "usb_pd_policy.c": "PD policy (VDM/DFP/cap)",
        "usb_pd_tcpc.c": "PD TCPC (phy/rx/tx)",
        "board.c": "board/gale glue",
        "flash.c": "flash common",
        "flash-f0.c": "flash STM32F0 driver",
        "stm32-flash.c": "flash STM32F0 driver",
        "spi.c": "SPI peripheral",
        "usb_spi.c": "USB-SPI bridge",
        "i2c.c": "I2C peripheral",
        "i2c-stm32f0.c": "I2C peripheral",
        "usb.c": "USB core/ep0",
        "console.c": "console",
        "console_output.c": "console",
        "vfnprintf.c": "printf/format",
        "printf.c": "printf/format",
        "host_command.c": "host-command dispatch",
        "system.c": "system/image",
        "system_chip.c": "system/image",
        "hooks.c": "hooks/deferred",
        "task.c": "RTOS/task",
        "gpio.c": "GPIO",
        "util.c": "libutil",
        "timer.c": "timer",
        "charge_manager.c": "charge manager",
    }
    if f in table:
        return table[f]
    n = name.lower()
    if n.startswith("pd_") or "pd_task" in n or "vdm" in n:
        return "PD protocol state machine"
    if "flash" in n or "optb" in n:
        return "flash"
    if "i2c" in n:
        return "I2C peripheral"
    if "spi" in n:
        return "SPI peripheral"
    if "console" in n or "command_" in n:
        return "console"
    if "div" in n or "mod" in n or "printf" in n or n.startswith("__"):
        return "lib/arith/printf"
    return "other: %s" % f


sub_tot = Counter()
sub_funcs = defaultdict(set)
for fn in funcs:
    s = subsystem(fn["src"], fn["name"])
    sub_tot[s] += len(fn["branches"])
    sub_funcs[s].add(fn["name"])

print("=== uncovered branches by subsystem (source file) ===")
for s, n in sub_tot.most_common():
    print("  %5d  %-32s  (%d functions)" % (n, s, len(sub_funcs[s])))
print("  -----")
print("  %5d  TOTAL" % sum(sub_tot.values()))

st = Counter()
for fn in funcs:
    for b in fn["branches"]:
        st[b["state"]] += 1
print("\n=== by coverage-state ===")
for k, v in st.most_common():
    print("  %5d  %s" % (v, k))

print("\n=== functions with >=5 uncovered (sorted) ===")
rows = sorted(funcs, key=lambda f: -len(f["branches"]))
for fn in rows:
    if len(fn["branches"]) < 5:
        continue
    states = Counter(b["state"] for b in fn["branches"])
    print("  %-26s %-28s u=%3d  unr=%d tk1=%d nt1=%d  [%s]"
          % (fn["name"], subsystem(fn["src"], fn["name"]), len(fn["branches"]),
             states.get("unreached", 0), states.get("taken-only", 0),
             states.get("nottaken-only", 0), fn["conf"]))

print("\n=== long tail: functions with <5 uncovered, grouped by subsystem ===")
tail = defaultdict(list)
for fn in rows:
    if len(fn["branches"]) < 5:
        tail[subsystem(fn["src"], fn["name"])].append((fn["name"], len(fn["branches"])))
for s in sorted(tail, key=lambda k: -sum(n for _, n in tail[k])):
    tot = sum(n for _, n in tail[s])
    print("  %-30s  %d branches across %d funcs" % (s, tot, len(tail[s])))
