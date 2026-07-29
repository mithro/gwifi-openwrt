#!/usr/bin/env python3
"""FLASH-WRITE-PROTECT lever — asserts the hardware write-protect pin (GPIO_WP_L = PB11, active-low)
and then runs flash-protect operations, so the GPIO_ASSERTED-dependent arms the campaign (which always
boots with WP de-asserted) never reaches finally execute:
  flash.c:404-409 `if (!gpio_get_level(GPIO_WP_L)) flags |= EC_FLASH_PROTECT_GPIO_ASSERTED;` (taken arm),
  flash.c:507 `if ((~flash_get_protect()) & (GPIO_ASSERTED | ...))`, flash_set_protect RO_AT_BOOT/
  ALL_AT_BOOT now-locked arms (a protect-at-boot request with WP asserted -> RO_NOW/ALL_NOW), and
  system_is_locked()==true (which gates sysjump/reboot/reset rejection) since locked = RO_NOW & WP.
Drives the pin via Renode's GPIO model (`gpioPortB OnGPIO 11 false` = real low input level — NOT register
forcing), then exercises flashinfo / flashwp / FLASH_PROTECT host cmd / sysjump / reboot. RO + RW.
Accumulates tmp/flashwp_edges.pkl. Usage: uv run --python .venv python cov_flashwp.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def le32(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "flashwp.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.15"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data),
                'emulation RunFor "%s"' % t]

    RO_AT_BOOT, RO_NOW, ALL_NOW, ALL_AT_BOOT = 0x01, 0x02, 0x04, 0x40

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    # sysjump to RW FIRST (with WP de-asserted so the jump is not locked-rejected), THEN assert WP.
    if RW:
        c += cc("sysjump rw", "0.5")
    # Assert the hardware write-protect pin (PB11 = WP_L, active-low): drive it LOW.
    c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"']
    c += ['cpu CreateExecutionTracing "trwp" @%s PC' % trace]

    # (1) flash_get_protect read-back with WP asserted -> GPIO_ASSERTED arm (flash.c:404)
    c += cc("flashinfo") + cc("flashwp") + cc("flashwp now")

    # (2) FLASH_PROTECT host cmd with WP asserted: a RO_AT_BOOT / ALL_AT_BOOT request is honoured and
    # becomes RO_NOW / ALL_NOW (locked); clear requests are DENIED -> the WP-gated arms in
    # flash_set_protect / flash_get_protect.
    for m, fl in ((RO_AT_BOOT, RO_AT_BOOT), (ALL_AT_BOOT, ALL_AT_BOOT), (RO_AT_BOOT, 0),
                  (ALL_AT_BOOT, 0), (RO_NOW, RO_NOW), (ALL_NOW, ALL_NOW), (0xFFFFFFFF, 0)):
        c += hc(0x0015, le32(m) + le32(fl))
        c += cc("flashinfo")

    # (3) WrpValue RO-protected pattern + WP asserted -> system_is_locked() true -> sysjump/reboot
    # rejection arms (system_run_image_copy / command_sysjump locked).
    c += ['sysbus.flashif WrpValue 0xFFFF0000', 'gpioPortB OnGPIO 11 false']
    c += cc("reboot ro", "0.7")
    c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"']
    c += cc("flashinfo") + cc("sysinfo")
    c += cc("sysjump rw", "0.4") + cc("sysjump ro", "0.4") + cc("sysjump a", "0.4")
    # FLASH_PROTECT clear attempt while locked (denied path)
    c += hc(0x0015, le32(0xFFFFFFFF) + le32(0))
    c += cc("flasherase 0x18000 0x800")           # erase while protected+locked
    c += ['sysbus.flashif WrpValue 0xFFFFFFFF', 'emulation RunFor "0.2"']

    # (4) de-assert WP mid-run then re-read (the GPIO_ASSERTED clear edge in a now-locked image)
    c += ['gpioPortB OnGPIO 11 true', 'emulation RunFor "0.1"'] + cc("flashinfo")
    c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"'] + cc("flashinfo")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "flashwp.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "flashwp_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/flashwp_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
