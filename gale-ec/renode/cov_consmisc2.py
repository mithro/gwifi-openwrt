"""CONSOLE-MISC-2 lever — more small clusters bundled: command_mem_dump (md .b/.h/.w fmt :27, ".X" arg
:66, argc<2 :85), command_read_word (rw .b/.h :127/129), command_gpio_get (name-not-found :118),
command_gpio_set/gpio_command_set (invalid value :189, locked :266), host_command_get_cmd_versions
(v0/v1 found/not-found :366/367/512). Genuine console + host-command execution. RO + RW.
Usage: uv run --python .venv python cov_consmisc2.py [rw]
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
    trace = os.path.join(TMP, "consmisc2.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.06"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    def hc(cmd, ver, sver, data, t="0.1"):
        return ['sysbus.i2c1 HostCmd "%s"' % C._hc_packet(cmd, ver, sver, len(data), data), 'emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trc2" @%s PC' % trace]

    cmds = [
        # md: format variants (.b/.h/.w switch :27), bad ".X", missing arg (:85), bad addr
        "md", "md .b 0x20000000", "md .h 0x20000000", "md .w 0x20000000", "md .x 0x20000000",
        "md 0x20000000", "md 0x20000000 8", "md . 0x20000000", "md .bb 0x20000000", "md badaddr",
        "md 0x08000000 4", "md .h 0x08000000 16",
        # rw: format variants (:127/129) + write
        "rw", "rw .b 0x20000000", "rw .h 0x20000000", "rw 0x20000000", "rw 0x20000000 0x1234",
        "rw .b 0x20000000 0xaa", "rw .x 0x20000000", "rw badaddr",
        # gpioget: all, valid, not-found (:118)
        "gpioget", "gpioget WP_L", "gpioget WP", "gpioget EC_INT_L", "gpioget nonexistent_pin",
        # gpioset: invalid value (:189), valid, not-found, (locked handled below)
        "gpioset WP_L 1", "gpioset WP_L 0", "gpioset WP_L x", "gpioset nonexistent 1", "gpioset WP_L",
    ]
    for s in cmds:
        c += cc(s)
    # GET_CMD_VERSIONS (0x08): v0 found(0x01)/not-found(0xff); v1 (u16 cmd) found/not-found (:366/367/512/518)
    c += hc(0x0008, 0, 3, [0x01]) + hc(0x0008, 0, 3, [0xff]) + hc(0x0008, 0, 3, [0x10])
    c += hc(0x0008, 1, 3, [0x01, 0x00]) + hc(0x0008, 1, 3, [0x00, 0xff]) + hc(0x0008, 1, 3, [0x67, 0x00])
    # FLASH_READ valid + bad offset (:793 error), FLASH_WRITE (:824)
    c += hc(0x0011, 0, 3, [0, 0, 0, 0, 8, 0, 0, 0]) + hc(0x0011, 0, 3, [0xff, 0xff, 0xff, 0x7f, 8, 0, 0, 0])

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "consmisc2.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "consmisc2_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/consmisc2_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
