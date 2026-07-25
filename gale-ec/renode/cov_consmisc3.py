"""CONSOLE-MISC-3 lever — more bundled small clusters:
 command_spixfer (spi_commands.c:43 bad len / :48 result), command_sysjump (system.c:910 RO / :912 RW|A /
 :918 disable / :924 locked), command_adc (adc.c:21 no-name / :25 name match / :43 READ_ERROR / :45 print),
 command_panicinfo (panic_output.c:198 magic valid -> inject a valid panic_data at RAM top then panicinfo),
 flash_command_erase (flash.c:838 ALL_NOW protected). Genuine console/host execution. RO + RW.
Usage: uv run --python .venv python cov_consmisc3.py [rw]
"""
import os, pickle, struct, subprocess, sys
import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")
RAM_TOP = 0x20004000           # STM32F072CB: 16 KB SRAM
PANIC_MAGIC = 0x21636e50


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None; continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None; continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "consmisc3.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.2"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data), 'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trc3" @%s PC' % trace]

    # spixfer: valid read, bad length (:43 v<0 || v>sizeof), write, no-arg
    for s in ("spixfer rlen 0 0x1f 3", "spixfer rlen 0 0x1f 999", "spixfer rlen 0 0x1f 0",
              "spixfer w 0 0xab 0xcd", "spixfer", "spixfer rlen", "spixfer rlen 0 0x1f -1"):
        c += cc(s)
    # adc: all channels, specific name match (:25), not-found (no match -> nothing printed)
    for s in ("adc", "adc CC1", "adc CC2", "adc VBUS", "adc nonexistent", "adc "):
        c += cc(s)
    # command_panicinfo with VALID saved panic data: inject a panic_data struct at RAM top (magic at top-4)
    pdata = bytes([1, 2, 1, 0]) + struct.pack("<12I", *([0x11 * (i + 1) for i in range(12)])) \
        + struct.pack("<8I", *([0xA5] * 8)) + struct.pack("<II", 92, PANIC_MAGIC)
    base = RAM_TOP - len(pdata)
    for i in range(0, len(pdata), 4):
        w = struct.unpack_from("<I", pdata, i)[0]
        c += ['sysbus WriteDoubleWord 0x%X 0x%08X' % (base + i, w)]
    c += cc("panicinfo")
    # flash_command_erase when ALL_NOW protected (:838): set protect ALL_NOW then FLASH_ERASE host cmd
    c += hc(0x0015, [0x04, 0, 0, 0, 0x04, 0, 0, 0])            # FLASH_PROTECT mask=ALL_NOW flags=ALL_NOW
    c += hc(0x0013, [0, 0x80, 1, 0, 0, 0x08, 0, 0])            # FLASH_ERASE (protected -> error arm)
    c += cc("flasherase 0x18000 0x800")
    # sysjump arg arms (RO/RW/A/disable/bogus) + locked (after the protect above)
    for s in ("sysjump RO", "sysjump RW", "sysjump A", "sysjump disable", "sysjump bogus", "sysjump 0x8000000"):
        c += cc(s, "0.4")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "consmisc3.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "consmisc3_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/consmisc3_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
