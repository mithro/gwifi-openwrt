#!/usr/bin/env python3
"""Direct function-invocation harness via Renode's GDB stub (raw RSP, no gdb binary needed).

This is the systematic lever for branch coverage + functional equivalence: CALL each firmware
function directly with crafted arguments (exactly what the EC's own unit tests do), on the REAL
firmware running in Renode — genuine execution, never faking a branch outcome. Inputs that exercise
both sides of a conditional cover it both directions; running the IDENTICAL call on the captured and
the rebuilt and comparing the return value (and memory effects) is per-function equivalence.

Mechanism (validated): boot the firmware (so globals are initialised), plant a 2-byte `b .` spin at
a scratch RAM address as the return trap, start Renode's GDB server, then over the GDB remote
protocol set r0..r3 = args, lr = spin|1, pc = func, plant a breakpoint at the spin, `continue`; the
function runs to completion and traps at the spin; read r0 for the return value. Hundreds of calls
run in ONE renode session (fast). With execution tracing enabled in the -e script, every call's PCs
are captured for branch coverage.

GDB register numbers (Cortex-M): r0..r12 = 0..12, sp = 13, lr = 14, pc = 15.
"""
import os
import socket
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.resc")
SPIN = 0x20003000          # scratch RAM: a `b .` (0xE7FE) return trap


class Rsp:
    def __init__(self, host="127.0.0.1", port=3333, timeout=5):
        self.sk = socket.create_connection((host, port), timeout=timeout)
        self.sk.settimeout(timeout)

    def _send(self, d):
        pkt = "$%s#%02x" % (d, sum(d.encode()) & 0xff)
        self.sk.sendall(pkt.encode())
        while self.sk.recv(1) != b'+':
            pass

    def _recv(self):
        buf = b''
        while not buf.endswith(b'#'):
            buf += self.sk.recv(1)
        buf += self.sk.recv(2)
        self.sk.sendall(b'+')
        return buf[1:buf.index(b'#')].decode()

    def cmd(self, d):
        self._send(d)
        return self._recv()

    @staticmethod
    def _le(v):
        return ''.join('%02x' % ((v >> (8 * i)) & 0xff) for i in range(4))

    def setreg(self, n, v):
        self.cmd("P%x=%s" % (n, self._le(v)))

    def readreg(self, n):
        return int.from_bytes(bytes.fromhex(self.cmd("p%x" % n)), 'little')

    def writemem(self, addr, data):
        self.cmd("M%x,%x:%s" % (addr, len(data), data.hex()))

    def readmem(self, addr, n):
        return bytes.fromhex(self.cmd("m%x,%x" % (addr, n)))

    def call(self, func, args=(), timeout_continue=10):
        """Invoke func(args...) and return r0. args -> r0..r3 (max 4 here)."""
        for i, a in enumerate(args[:4]):
            self.setreg(i, a & 0xFFFFFFFF)
        self.setreg(14, SPIN | 1)         # lr -> spin
        self.setreg(15, func & ~1)        # pc -> func
        self.cmd("Z0,%x,2" % SPIN)        # breakpoint at the spin
        old = self.sk.gettimeout(); self.sk.settimeout(timeout_continue)
        self.cmd("c")                     # continue until the breakpoint (function returns)
        self.sk.settimeout(old)
        self.cmd("z0,%x,2" % SPIN)
        return self.readreg(0)


class Session:
    """A booted firmware + GDB stub; supports many calls, optionally with execution tracing."""
    def __init__(self, binpath, boot="1.5", mon=None, trace=None):
        self.trace = trace
        c = ['$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(binpath), '$name="fc"',
             'include @%s' % BASE] + list(mon or [])
        c += ['emulation RunFor "%s"' % boot, 'sysbus WriteWord 0x%X 0xE7FE' % SPIN]
        if trace:
            c += ['cpu CreateExecutionTracing "t" @%s PC' % trace]
        c += ['machine StartGdbServer 3333']
        self.p = subprocess.Popen(["renode", "--disable-gui", "--console", "-e", "; ".join(c)],
                                  stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT)
        self.rsp = None
        for _ in range(60):
            try:
                self.rsp = Rsp(); break
            except OSError:
                time.sleep(0.5)
        if self.rsp is None:
            self.close(); raise RuntimeError("GDB server never came up")

    def call(self, func, args=()):
        return self.rsp.call(func, args)

    def close(self):
        try:
            self.rsp.sk.close()
        except Exception:
            pass
        try:
            self.p.stdin.close()
        except Exception:
            pass
        self.p.terminate()


if __name__ == "__main__":
    # self-test: __clzsi2 on the rebuilt
    s = Session("ec-rebuilt.bin")
    for a, want in ((0, 32), (0xFFFFFFFF, 0), (0x00010000, 15), (1, 31)):
        got = s.call(0x08003a78, (a,))
        print("clz(0x%08x) = %d %s" % (a, got, "OK" if got == want else "FAIL want %d" % want))
    s.close()
