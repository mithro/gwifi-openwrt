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
import signal
import socket
import subprocess
import time

RENODE_MEM_MAX = os.environ.get("RENODE_MEM_MAX", "2500M")


def _have_systemd_run():
    try:
        return subprocess.run(["systemd-run", "--user", "--scope", "-q", "true"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=20).returncode == 0
    except Exception:
        return False


_HAVE_SYSTEMD_RUN = _have_systemd_run()


def _renode_argv(monitor_script):
    base = ["renode", "--disable-gui", "--console", "-e", monitor_script]
    if _HAVE_SYSTEMD_RUN:
        return ["systemd-run", "--user", "--scope", "-q",
                "-p", "MemoryMax=%s" % RENODE_MEM_MAX, "-p", "MemorySwapMax=0"] + base
    return base

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

    def call_stepped(self, func, args=(), max_steps=200000, step_timeout=20):
        """Invoke func(args...) by SINGLE-STEPPING, returning the ordered list of executed PCs.
        Robust alternative to CreateExecutionTracing for sessions where a machine modification
        (LoadPlatformDescriptionFromString) disrupts the execution tracer. Stops when PC reaches the
        spin trap (function returned) or max_steps is hit."""
        for i, a in enumerate(args[:4]):
            self.setreg(i, a & 0xFFFFFFFF)
        self.setreg(14, SPIN | 1)
        self.setreg(15, func & ~1)
        pcs = []
        old = self.sk.gettimeout(); self.sk.settimeout(step_timeout)
        try:
            for _ in range(max_steps):
                pc = self.readreg(15)
                pcs.append(pc)
                if (pc & ~1) == (SPIN & ~1):
                    break
                self.cmd("s")             # single-step one instruction
        finally:
            self.sk.settimeout(old)
        return pcs


_next_port = [3333]


class Session:
    """A booted firmware + GDB stub; supports many calls, optionally with execution tracing.
    Each session uses a FRESH port so a torn-down session never collides with the next one."""
    def __init__(self, binpath, boot="1.5", mon=None, trace=None, port=None, post_mon=None):
        self.trace = trace
        if port is None:
            port = _next_port[0]
            _next_port[0] = 3334 + (_next_port[0] - 3333 + 1) % 200   # rotate 3334..3534
        self.port = port
        c = ['$h=@%s' % HERE, '$bin=@%s' % os.path.abspath(binpath), '$name="fc"',
             'include @%s' % BASE] + list(mon or [])
        c += ['emulation RunFor "%s"' % boot, 'sysbus WriteWord 0x%X 0xE7FE' % SPIN]
        # Create the execution tracer BEFORE post_mon so a post_mon machine modification
        # (e.g. LoadPlatformDescriptionFromString swapping a peripheral) does not prevent the tracer
        # from attaching to the CPU. post_mon then runs AFTER boot (so a non-bridging swapped peripheral
        # is absent during the firmware's boot-time init) but before the GDB server starts.
        if trace:
            c += ['cpu CreateExecutionTracing "t" @%s PC' % trace]
        c += list(post_mon or [])
        c += ['machine StartGdbServer %d' % port]
        # Own process group + memory-capped cgroup so close() can kill the WHOLE tree (the renode
        # bash wrapper AND its dotnet child) — orphaned dotnet children were the memory leak that
        # exhausted RAM and made later sessions fail to start.
        self.p = subprocess.Popen(_renode_argv("; ".join(c)),
                                  stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT, start_new_session=True)
        self.rsp = None
        for _ in range(80):
            try:
                self.rsp = Rsp(port=port); break
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
        # Kill the entire process group (systemd-run/scope + renode wrapper + dotnet child) so no
        # dotnet orphan survives to leak memory.
        try:
            os.killpg(os.getpgid(self.p.pid), signal.SIGKILL)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass
        try:
            self.p.wait(timeout=10)        # reap; release the port before the next session
        except Exception:
            pass


if __name__ == "__main__":
    # self-test: __clzsi2 on the rebuilt
    s = Session("ec-rebuilt.bin")
    for a, want in ((0, 32), (0xFFFFFFFF, 0), (0x00010000, 15), (1, 31)):
        got = s.call(0x08003a78, (a,))
        print("clz(0x%08x) = %d %s" % (a, got, "OK" if got == want else "FAIL want %d" % want))
    s.close()
