"""TCPC-I2C lever — gale acts as a TCPC (CONFIG_USB_PD_TCPC, OAR2=0x9c). The i2c2_event_interrupt
ADDR_IS_TCPC arms (i2c-stm32f0.c:329 STOP-while-rx-pending offset-write, :389 register read) + the
tcpc_i2c_process path run only for transactions on the TCPC address. GaleI2c.TcpcCmd(hex, read) scripts
an AP<->TCPC register write/read with ADDCODE=0x9c. Drive register writes (set offset + STOP) and reads
across the TCPC register map. Genuine execution. RO + RW.
Usage: uv run --python .venv python cov_tcpc.py [rw]
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
    trace = os.path.join(TMP, "tcpc.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'sysbus.adc ForceSourceCc true', 'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trtc" @%s PC' % trace]

    # TCPC register reads + offset-writes across the TCPCI register map (00=vendor_id, 04=product_id,
    # 1C=cc_status, 1D=power_status, 1E=fault_status, 90/98=alert, etc.). write=offset-only -> STOP-rx
    # path (:329); read=offset+readback -> :389. (hex = the register-offset byte(s) the AP writes.)
    for reg in ("00", "02", "04", "08", "0c", "10", "18", "19", "1b", "1c", "1d", "1e", "1f",
                "23", "90", "92", "98", "9b", "9e", "a0", "ff"):
        c += ['sysbus.i2c1 TcpcCmd "%s" false' % reg, 'emulation RunFor "0.06"']   # offset-write + STOP
        c += ['sysbus.i2c1 TcpcCmd "%s" true' % reg,  'emulation RunFor "0.06"']   # offset-write + read
    # multi-byte register writes (e.g. set ROLE_CTRL / COMMAND)
    for w in ("1a01", "2301", "2302", "2303", "9001ff", "23aa"):
        c += ['sysbus.i2c1 TcpcCmd "%s" false' % w, 'emulation RunFor "0.06"']
    # interleave a real PD contract so the TCPC alert/status registers have live state to report
    c += cc("pd 0 state")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "tcpc.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "tcpc_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/tcpc_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
