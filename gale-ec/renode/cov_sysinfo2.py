"""COMMAND-SYSINFO-2 lever — drives command_sysinfo (system.c:815-829) through its STATE-dependent arms:
 :815 jumped (run sysinfo AFTER a sysjump -> system_jumped_to_this_image() yes), :819 locked
 (system_is_locked() -> RO_NOW protect via WrpValue + WP asserted), :821 (forced) reset flags,
 :823 jump-disabled, :829 reboot_at_shutdown (EC_CMD_REBOOT_EC 0xd2 with ON_AP_SHUTDOWN flag).
Each state set up, then `sysinfo` printed so the arm runs. Genuine console/host-command execution. RO + RW.
Usage: uv run --python .venv python cov_sysinfo2.py [rw]
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


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "sysinfo2.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.08"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.15"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data),
                'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trs2" @%s PC' % trace]

    # (1) baseline sysinfo (not jumped if RO; jumped if RW) + reset-flags arms
    c += cc("sysinfo")
    # (2) jumped: sysjump to the OTHER image then sysinfo -> system_jumped_to_this_image() yes (:815)
    c += cc("sysjump rw", "0.4") + cc("sysinfo")
    c += cc("sysjump ro", "0.4") + cc("sysinfo")
    c += cc("sysjump a", "0.4") + cc("sysinfo")
    # (3) reboot_at_shutdown (:829): EC_CMD_REBOOT_EC(0xd2){cmd, flags=ON_AP_SHUTDOWN(2)} then sysinfo
    c += hc(0x00d2, [4, 0x02]) + cc("sysinfo")            # cmd=COLD(4) flags=ON_AP_SHUTDOWN
    c += hc(0x00d2, [3, 0x02]) + cc("sysinfo")            # cmd=HARD(3) flags=ON_AP_SHUTDOWN
    c += hc(0x00d2, [2, 0x02]) + cc("sysinfo")
    # (4) locked (:819): RO_NOW protect (WrpValue RO sectors) + WP asserted -> system_is_locked() true
    c += ['sysbus.flashif WrpValue 0xFFFF0000', 'gpioPortB OnGPIO 11 false']
    c += cc("reboot ro", "0.7")
    if RW:
        c += cc("sysjump rw", "0.4")
    c += ['gpioPortB OnGPIO 11 false', 'emulation RunFor "0.1"'] + cc("sysinfo")
    # also FLASH_PROTECT RO_NOW host cmd then sysinfo (locked)
    c += hc(0x0015, [0x02, 0, 0, 0, 0x02, 0, 0, 0]) + cc("sysinfo")
    c += ['sysbus.flashif WrpValue 0xFFFFFFFF', 'gpioPortB OnGPIO 11 true', 'emulation RunFor "0.2"'] + cc("sysinfo")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "sysinfo2.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "sysinfo2_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/sysinfo2_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
