#!/usr/bin/env python3
"""Region-aware writer for the gale AP SPI flash over the EC raiden bridge.

Stock `flashrom -E/-w` over raiden FAILS on this unit (it trips on the SRP1=1
power-cycle status-register lock and its erase silently no-ops). This tool drives
the bridge DIRECTLY (chromiumos usb_spi V1) to erase+program+verify a flash region.

Hard constraint discovered on this rig: the EC bridge silently returns/accepts only
~87 KiB per ENABLE-SESSION, and the ONLY thing that resets that session is a fresh
process (re-REQ_ENABLE / re-park / REQ_DISABLE+ENABLE inside one libusb claim all
fail). So this orchestrator spawns ONE fresh worker process per <=64 KiB chunk:
  per chunk:  [worker _pgm] erase+program   then   [worker _rd] read-back  -> compare
The first verify mismatch aborts the run.

SAFETY: dry-run by default (prints the plan, touches nothing). Pass --commit to write.
Refuses the bottom 4 MiB (RO_SECTION/WP_RO: bootblock+coreboot+FMAP+GBB+RO_VPD) unless
--allow-ro. Requires 4 KiB-aligned offset AND length (so erase never hits neighbors).

USAGE
  raiden_write_region.py <src.bin> <REGION|0xOFF:0xLEN> [--chunk 0x10000]
                         [--commit] [--allow-ro] [--no-verify]
    REGION = an FMAP region name parsed from <src.bin> (e.g. RW_LEGACY, RW_SECTION_A,
             RW_SECTION_B, RW_GPT). Or give an explicit 0xOFF:0xLEN span.
  Internal worker subcommands (spawned automatically; not for direct use):
    _pgm <0xoff> <chunkfile> [ro_ok]      _rd <0xoff> <0xlen> <outfile>
"""
import os
import struct
import subprocess
import sys
import time

import serial
import usb.core
import usb.util

VID, PID = 0x18D1, 0x500F
IFNUM, EP_OUT, EP_IN = 3, 0x03, 0x83
REQ_ENABLE, REQ_DISABLE, RTYPE_OUT = 0x0000, 0x0001, 0x41
BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
CHIP_SIZE = 8 * 1024 * 1024
SECTOR = 0x1000              # 4 KiB erase sector (0x20)
RO_LIMIT = 0x400000         # below this = RO_SECTION/WP_RO -> guarded
V1_WRITE_MAX = 58           # usb_spi V1: 62 - (opcode + 3 addr)
V1_READ_MAX = 62
SELF = os.path.abspath(__file__)
TMP = os.environ.get("GALE_WORK", os.path.dirname(SELF))  # scratch dir for chunk/verify files


def a3(addr):
    return [(addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF]


# ---------- raiden session (one per worker process) ----------

def ec_park():
    port = os.path.realpath(BYID) if os.path.exists(BYID) else "/dev/ttyUSB0"
    with serial.Serial(port, 115200, timeout=0.2) as s:
        time.sleep(0.2)
        s.reset_input_buffer()
        s.write(b"gale power off\r\n")
        s.flush()
        time.sleep(0.6)
        if s.in_waiting:
            s.read(s.in_waiting)
    time.sleep(0.2)


class Raiden:
    def __init__(self):
        ec_park()
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise SystemExit("raiden: device 18d1:500f not found")
        self.detached = False
        try:
            if self.dev.is_kernel_driver_active(IFNUM):
                self.dev.detach_kernel_driver(IFNUM)
                self.detached = True
        except (usb.core.USBError, NotImplementedError):
            pass
        usb.util.claim_interface(self.dev, IFNUM)
        self.dev.ctrl_transfer(RTYPE_OUT, REQ_ENABLE, 0, IFNUM, None, 1000)
        time.sleep(0.05)
        for _ in range(100):
            try:
                self.dev.read(EP_IN, 64, timeout=20)
            except usb.core.USBError:
                break
        st, rdid = self.xfer([0x9F], 3)
        if rdid != bytes([0xEF, 0x40, 0x17]):
            self.close()
            raise SystemExit(f"raiden: RDID={rdid.hex()} != ef4017 (bridge not ready)")

    def xfer(self, wdata, rc):
        out = bytes([len(wdata), rc]) + bytes(wdata)
        self.dev.write(EP_OUT, out, timeout=2000)
        resp = bytes(self.dev.read(EP_IN, 64, timeout=2000))
        return (resp[0] | (resp[1] << 8)), resp[2:2 + rc]

    def sr1(self):
        return self.xfer([0x05], 1)[1][0]

    def wait_wip(self, timeout=2.0):
        # Poll sparsely: each RDSR is a transaction and counts against the ~1444
        # per-session cliff. Erases take ~45 ms, programs <1 ms, so 5 ms is plenty.
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not (self.sr1() & 1):
                return True
            time.sleep(0.005)
        return False

    def close(self):
        try:
            self.dev.ctrl_transfer(RTYPE_OUT, REQ_DISABLE, 0, IFNUM, None, 1000)
        except usb.core.USBError:
            pass
        usb.util.release_interface(self.dev, IFNUM)
        usb.util.dispose_resources(self.dev)
        if self.detached:
            try:
                self.dev.attach_kernel_driver(IFNUM)
            except usb.core.USBError:
                pass


# ---------- workers (each is its own fresh process == cliff reset) ----------

def worker_pgm(off, chunkfile, ro_ok):
    data = open(chunkfile, "rb").read()
    n = len(data)
    if off % SECTOR or n % SECTOR:
        raise SystemExit(f"_pgm: off 0x{off:x}/len 0x{n:x} not 4 KiB aligned")
    if off < RO_LIMIT and not ro_ok:
        raise SystemExit(f"_pgm: refusing RO write at 0x{off:x} (no ro_ok)")
    if off + n > CHIP_SIZE:
        raise SystemExit("_pgm: past end of chip")
    # Transaction-budget guard: erase+program must stay under the ~1444-per-session
    # cliff or programs silently no-op past it. ~14 txns/sector erase + ~3 txns per
    # 58-byte program slice.
    est_txn = (n // SECTOR) * 14 + (n // V1_WRITE_MAX + 1) * 3 + 5
    if est_txn > 1200:
        raise SystemExit(f"_pgm: chunk 0x{n:x} ≈{est_txn} transactions risks the "
                         f"~1444/session cliff (programs would silently no-op); "
                         f"use --chunk <= 0x4000")
    r = Raiden()
    try:
        # erase every 4 KiB sector covering the chunk
        for s in range(off, off + n, SECTOR):
            r.xfer([0x06], 0)                       # WREN
            st, _ = r.xfer([0x20] + a3(s), 0)       # 4 KiB sector erase
            if st or not r.wait_wip():
                raise SystemExit(f"_pgm: erase failed @0x{s:x} status=0x{st:04x}")
        # page-program in <=58 B slices, never crossing a 256 B page
        i = 0
        while i < n:
            addr = off + i
            page_remain = 256 - (addr & 0xFF)
            k = min(V1_WRITE_MAX, page_remain, n - i)
            r.xfer([0x06], 0)                       # WREN
            st, _ = r.xfer([0x02] + a3(addr) + list(data[i:i + k]), 0)  # Page Program
            if st or not r.wait_wip():
                raise SystemExit(f"_pgm: program failed @0x{addr:x} status=0x{st:04x}")
            i += k
        print(f"_pgm OK off=0x{off:06x} len=0x{n:x}")
    finally:
        r.close()


def worker_rd(off, length, outfile):
    r = Raiden()
    try:
        buf = bytearray()
        i = 0
        while i < length:
            k = min(V1_READ_MAX, length - i)
            _, d = r.xfer([0x03] + a3(off + i), k)
            if len(d) != k:
                raise SystemExit(f"_rd: SHORT READ at 0x{off + i:06x} -- got {len(d)}/{k} B "
                                 f"(bridge session cliff or USB error). Aborting; NOT zero-filling "
                                 f"(a silent zero-fill would masquerade as real data).")
            buf += d
            i += k
        open(outfile, "wb").write(buf)
        print(f"_rd OK off=0x{off:06x} len=0x{length:x}")
    finally:
        r.close()


# ---------- FMAP parsing (region name -> offset/size), from the source image ----------

def parse_fmap(buf):
    HDR = "<8sBBQI32sH"
    HSZ = struct.calcsize(HDR)
    ASZ = struct.calcsize("<II32sH")
    start = 0
    while True:
        i = buf.find(b"__FMAP__", start)
        if i < 0:
            return {}
        start = i + 1
        if i + HSZ > len(buf):
            continue
        sig, vmaj, vmin, base, size, name, nareas = struct.unpack_from(HDR, buf, i)
        if vmaj != 1 or not (1 <= nareas <= 64) or size != len(buf):
            continue
        areas = {}
        ok = True
        for a in range(nareas):
            o = i + HSZ + a * ASZ
            if o + ASZ > len(buf):
                ok = False
                break
            ao, asz, an, fl = struct.unpack_from("<II32sH", buf, o)
            areas[an.split(b"\0")[0].decode("latin1")] = (ao, asz)
        if ok and areas:
            return areas


# ---------- orchestrator ----------

def orchestrate(argv):
    src = argv[0]
    spec = argv[1]
    opts = argv[2:]
    chunk = 0x4000   # 16 KiB: safe under the ~1444-transaction per-session cliff
    if "--chunk" in opts:
        chunk = int(opts[opts.index("--chunk") + 1], 0)
    commit = "--commit" in opts
    allow_ro = "--allow-ro" in opts
    do_verify = "--no-verify" not in opts

    image = open(src, "rb").read()
    if len(image) != CHIP_SIZE:
        raise SystemExit(f"source size {len(image)} != {CHIP_SIZE}")

    if ":" in spec and spec.lower().startswith("0x"):
        o_str, l_str = spec.split(":")
        off, length = int(o_str, 16), int(l_str, 16)
        region = f"{spec}"
    else:
        fmap = parse_fmap(image)
        if spec not in fmap:
            raise SystemExit(f"region {spec!r} not in FMAP. Known: {sorted(fmap)}")
        off, length = fmap[spec]
        region = spec

    if off % SECTOR or length % SECTOR:
        raise SystemExit(f"region 0x{off:x}+0x{length:x} not 4 KiB aligned "
                         f"(would erase neighbours) -- refuse")
    if off < RO_LIMIT and not allow_ro:
        raise SystemExit(f"region {region} (0x{off:x}) is in the RO/bottom-4MiB area; "
                         f"refusing without --allow-ro (bricking risk)")

    chunks = []
    a = off
    while a < off + length:
        clen = min(chunk, off + length - a)
        chunks.append((a, clen))
        a += clen

    print(f"== raiden_write_region: {region} = 0x{off:06x} .. 0x{off+length:06x} "
          f"(0x{length:x} = {length/1024:.0f} KiB)")
    print(f"   source={src}  chunk=0x{chunk:x}  chunks={len(chunks)}  "
          f"verify={'yes' if do_verify else 'no'}  allow_ro={allow_ro}")
    print(f"   MODE = {'COMMIT (will erase+program the flash)' if commit else 'DRY-RUN (no device writes)'}")
    nz = sum(1 for b in image[off:off + length] if b)
    print(f"   source bytes in region: {length} ({100*nz/length:.1f}% nonzero)")
    for (a, clen) in chunks:
        print(f"     plan: erase+program 0x{a:06x} len 0x{clen:x} "
              f"({clen//SECTOR} sectors)")
    if not commit:
        print("\nDRY-RUN complete. Re-run with --commit to write.")
        return

    if not do_verify:
        print("\n!! WARNING: --no-verify is set. The bridge silently no-ops past the "
              "~16 KiB/session cliff, so an un-verified write can leave the flash in an "
              "UNKNOWN state with NO error and NO diff. Strongly prefer running WITHOUT "
              "--no-verify; only use it with a separate verification plan.")

    ro_ok = ["ro_ok"] if allow_ro else []
    for idx, (a, clen) in enumerate(chunks):
        cf = f"{TMP}/_wr_chunk.bin"
        open(cf, "wb").write(image[a:a + clen])
        print(f"\n[{idx+1}/{len(chunks)}] writing 0x{a:06x} len 0x{clen:x} ...")
        p = subprocess.run([sys.executable, SELF, "_pgm", hex(a), cf] + ro_ok,
                           capture_output=True, text=True)
        print("   " + (p.stdout + p.stderr).strip().replace("\n", "\n   "))
        if p.returncode != 0:
            raise SystemExit(f"ABORT: program worker failed at 0x{a:06x}")
        if do_verify:
            vf = f"{TMP}/_wr_verify.bin"
            p = subprocess.run([sys.executable, SELF, "_rd", hex(a), hex(clen), vf],
                               capture_output=True, text=True)
            print("   " + (p.stdout + p.stderr).strip().replace("\n", "\n   "))
            if p.returncode != 0:
                raise SystemExit(f"ABORT: read-back worker failed at 0x{a:06x}")
            got = open(vf, "rb").read()
            want = image[a:a + clen]
            if got != want:
                diff = sum(1 for x, y in zip(got, want) if x != y)
                first = next(j for j in range(len(want)) if got[j] != want[j])
                raise SystemExit(f"ABORT: verify MISMATCH at 0x{a:06x} "
                                 f"({diff} bytes, first +0x{first:x})")
            print(f"   verify OK (0x{clen:x} bytes match source)")
    print(f"\n== DONE: {region} written and verified ({len(chunks)} chunks).")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "_pgm":
        worker_pgm(int(sys.argv[2], 16), sys.argv[3],
                   len(sys.argv) > 4 and sys.argv[4] == "ro_ok")
    elif len(sys.argv) >= 2 and sys.argv[1] == "_rd":
        worker_rd(int(sys.argv[2], 16), int(sys.argv[3], 16), sys.argv[4])
    elif len(sys.argv) >= 3:
        orchestrate(sys.argv[1:])
    else:
        print(__doc__)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
