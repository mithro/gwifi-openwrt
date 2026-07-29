"""Dump full per-branch detail for one reason class (default R7 console/host-cmd). Parses the
verified UNCOVERED-BY-FUNCTION.md, applies the same classifier as gen_why_uncovered.py, and prints
every branch (RO+RW) with state, disassembled cause, and rebuilt-C line — the actionable list for
crafting stimulus. Usage: uv run --python .venv python dump_class.py [R7]"""
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
RPT = os.path.join(HERE, "UNCOVERED-BY-FUNCTION.md")
WANT = sys.argv[1] if len(sys.argv) > 1 else "R7"

hdr_re = re.compile(r"^## (0x[0-9a-fA-F]+)\s+`(.+?)`\s+\(conf:(\w+)\)\s*$")
src_re = re.compile(r"^\*\*Source:\*\*\s+(\S+)")
bul_re = re.compile(r"^- \*\*(0x[0-9a-fA-F]+)\*\*(\s+\(RW mirror\))?\s+\[([a-z?-]+)\]\s+—\s+(.*)$")
cre_re = re.compile(r"^\s+- rebuilt C \((.+?)\): `(.*)`\s*$")


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
        return "R4" if "init" in n else "R3"
    if f in ("flash.c", "flash-f0.c", "stm32-flash.c") or "flash" in n or "optb" in n:
        return "R4" if "init" in n else "R5"
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
    if f in ("util.c", "crc_hw.h"):
        return "R8"
    return "R7"


funcs = []
cur = None
b = None
for line in open(RPT):
    line = line.rstrip("\n")
    mh = hdr_re.match(line)
    if mh:
        if cur:
            funcs.append(cur)
        cur = dict(name=mh.group(1), nm=mh.group(2), conf=mh.group(3), src="?", branches=[])
        b = None
        continue
    if cur is None:
        continue
    ms = src_re.match(line)
    if ms:
        cur["src"] = re.sub(r":\d+$", "", ms.group(1))
        continue
    mb = bul_re.match(line)
    if mb:
        b = dict(addr=mb.group(1), rw=bool(mb.group(2)), state=mb.group(3), cause=mb.group(4), cline="")
        cur["branches"].append(b)
        continue
    mc = cre_re.match(line)
    if mc and b is not None:
        b["cline"] = "%s :: %s" % (mc.group(1), mc.group(2))
if cur:
    funcs.append(cur)

sel = [f for f in funcs if classify(f["nm"], f["src"]) == WANT]
sel.sort(key=lambda f: -len(f["branches"]))
tot = sum(len(f["branches"]) for f in sel)
print("=== class %s : %d functions, %d branches ===\n" % (WANT, len(sel), tot))
for f in sel:
    st = Counter(x["state"] for x in f["branches"])
    sm = " ".join("%d-%s" % (st[k], k) for k in ("unreached", "taken-only", "nottaken-only") if st.get(k))
    print("### %s  [%s]  src=%s  (%d: %s)"
          % (f["nm"], f["conf"], f["src"].split("/")[-1], len(f["branches"]), sm))
    # collapse RO/RW: show RO entries, note if RW mirror exists
    ro = [x for x in f["branches"] if not x["rw"]]
    rw = set(x["addr"] for x in f["branches"] if x["rw"])
    shown = ro if ro else f["branches"]
    for x in shown:
        print("  %s [%s] %s" % (x["addr"], x["state"], x["cause"]))
        if x["cline"]:
            print("        C: %s" % x["cline"])
    print()
