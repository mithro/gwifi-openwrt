"""COMMAND_SYSINFO lever — system.c:815-829 sysinfo arms: Jumped (815 system_jumped_to_this_image ->
run sysinfo after a sysjump), locked (819 system_is_locked -> flash-protect first), (forced) reset
(821 reset flags), jump-disabled (823 system_is_jump_disabled -> syslock), reboot_at_shutdown
(829 -> EC_CMD_REBOOT_EC with ON_AP_SHUTDOWN). Genuine console execution. RO + RW.
Usage: uv run --python .venv python cov_sysinfo.py [rw]
"""
import os, pickle, subprocess, sys
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
    trace = os.path.join(TMP, "sysinfo.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, data, t="0.1"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, 0, 3, len(data), data), 'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trsy" @%s PC' % trace]

    # baseline (cold boot or already-jumped if RW): the not-jumped/unlocked arms
    c += cc("sysinfo")
    # (815) Jumped=yes: sysjump (RO->RW or RW->RO), then sysinfo reports jumped
    c += cc("sysjump rw", "0.4") + cc("sysinfo")
    c += cc("sysjump ro", "0.4") + cc("sysinfo")
    c += cc("sysjump a", "0.4") + cc("sysinfo")
    # (829) reboot_at_shutdown: EC_CMD_REBOOT_EC(0xd2) {cmd, flags=EC_REBOOT_FLAG_ON_AP_SHUTDOWN(2)}
    c += hc(0x00d2, [3, 0x02]) + cc("sysinfo")            # cmd=COLD(3?) flags=ON_AP_SHUTDOWN
    c += hc(0x00d2, [2, 0x02]) + cc("sysinfo")            # different reboot cmd + at-shutdown
    c += cc("reboot ap-off-in-x") + cc("sysinfo")
    # (819) locked: protect flash so system_is_locked() may report locked, then sysinfo
    c += ['sysbus.flashif WrpValue 0xFFFF0000'] + cc("reboot ro", "0.6") + cc("sysinfo")
    # (823) jump-disabled: syslock disables jumping (destructive last); then sysinfo
    c += hc(0x00d2, [0, 0x01])                            # reboot flags (reserve/cancel)
    c += cc("sysinfo") + cc("syslock", "0.2") + cc("sysinfo")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "sysinfo.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "sysinfo_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/sysinfo_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
