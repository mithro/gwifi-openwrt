#!/usr/bin/env python3
"""Region-aware writer for the gale AP SPI flash over the EC raiden bridge.

Stock `flashrom -E/-w` over raiden FAILS on this unit (it trips on the SRP1=1
power-cycle status-register lock and its erase silently no-ops). This tool drives
the bridge DIRECTLY (chromiumos usb_spi V1, via the shared raiden.py transport) to
erase+program+verify a flash region.

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
import argparse
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find raiden.py beside us
from raiden import (Raiden, RaidenError, a3, V1_MAX,            # noqa: E402
                    OP_WREN, OP_SE4K, OP_PP)

CHIP_SIZE = 8 * 1024 * 1024
SECTOR = 0x1000                  # 4 KiB erase sector (0x20)
RO_LIMIT = 0x400000             # below this = RO_SECTION/WP_RO -> guarded
V1_WRITE_MAX = V1_MAX - 4        # usb_spi V1 payload minus (opcode + 3 addr) = 58
SELF = os.path.abspath(__file__)
TMP = os.environ.get("GALE_WORK", os.path.dirname(SELF))  # scratch dir for chunk/verify files


# ---------- workers (each is its own fresh process == cliff reset) ----------

def worker_pgm(off, chunkfile, ro_ok):
    data = open(chunkfile, "rb").read()
    n = len(data)
    if n == 0:
        raise SystemExit("_pgm: empty chunk file (0 bytes) -- nothing to program; "
                         "refusing a silent no-op that would 'verify' against b''")
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
        raise SystemExit(f"_pgm: chunk 0x{n:x} ~={est_txn} transactions risks the "
                         f"~1444/session cliff (programs would silently no-op); "
                         f"use --chunk <= 0x4000")
    with Raiden() as r:
        # erase every 4 KiB sector covering the chunk
        for s in range(off, off + n, SECTOR):
            try:
                r.xfer([OP_WREN], 0)
                r.xfer([OP_SE4K] + a3(s), 0)
                r.wait_wip()
            except RaidenError as e:
                raise SystemExit(f"_pgm: erase failed @0x{s:06x}: {e}")
        # page-program in <=58 B slices, never crossing a 256 B page
        i = 0
        while i < n:
            addr = off + i
            page_remain = 256 - (addr & 0xFF)
            k = min(V1_WRITE_MAX, page_remain, n - i)
            try:
                r.xfer([OP_WREN], 0)
                r.xfer([OP_PP] + a3(addr) + list(data[i:i + k]), 0)
                r.wait_wip()
            except RaidenError as e:
                raise SystemExit(f"_pgm: program failed @0x{addr:06x}: {e}")
            i += k
        print(f"_pgm OK off=0x{off:06x} len=0x{n:x}")


def worker_rd(off, length, outfile):
    # read_data() goes through the shared xfer, which RAISES on a short/garbled read
    # (never silently zero-fills) -- so a cliff hit or USB error aborts here, loud.
    with Raiden() as r:
        buf = bytearray()
        i = 0
        while i < length:
            k = min(V1_MAX, length - i)
            buf += r.read_data(off + i, k)
            i += k
        if len(buf) != length:
            raise SystemExit(f"_rd: assembled {len(buf)} B != requested 0x{length:x} "
                             f"-- refusing to write a short read-back")
        open(outfile, "wb").write(buf)
        print(f"_rd OK off=0x{off:06x} len=0x{length:x}")


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

def orchestrate(args):
    src = args.src
    spec = args.region
    chunk = args.chunk
    commit = args.commit
    allow_ro = args.allow_ro
    do_verify = not args.no_verify

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
    cf = f"{TMP}/_wr_chunk.bin"        # scratch: per-chunk source slice
    vf = f"{TMP}/_wr_verify.bin"       # scratch: per-chunk read-back
    try:
        for idx, (a, clen) in enumerate(chunks):
            open(cf, "wb").write(image[a:a + clen])
            print(f"\n[{idx+1}/{len(chunks)}] writing 0x{a:06x} len 0x{clen:x} ...")
            p = subprocess.run([sys.executable, SELF, "_pgm", hex(a), cf] + ro_ok,
                               capture_output=True, text=True)
            print("   " + (p.stdout + p.stderr).strip().replace("\n", "\n   "))
            if p.returncode != 0:
                raise SystemExit(f"ABORT: program worker failed at 0x{a:06x}")
            if do_verify:
                p = subprocess.run([sys.executable, SELF, "_rd", hex(a), hex(clen), vf],
                                   capture_output=True, text=True)
                print("   " + (p.stdout + p.stderr).strip().replace("\n", "\n   "))
                if p.returncode != 0:
                    raise SystemExit(f"ABORT: read-back worker failed at 0x{a:06x}")
                if not os.path.exists(vf):
                    raise SystemExit(f"ABORT: read-back worker exited 0 but wrote no "
                                     f"verify file at 0x{a:06x}")
                got = open(vf, "rb").read()
                want = image[a:a + clen]
                if len(got) != clen:
                    raise SystemExit(f"ABORT: read-back at 0x{a:06x} is {len(got)} B, "
                                     f"expected 0x{clen:x}")
                if got != want:
                    diff = sum(1 for x, y in zip(got, want) if x != y)
                    first = next(j for j in range(len(want)) if got[j] != want[j])
                    raise SystemExit(f"ABORT: verify MISMATCH at 0x{a:06x} "
                                     f"({diff} bytes, first +0x{first:x})")
                print(f"   verify OK (0x{clen:x} bytes match source)")
        print(f"\n== DONE: {region} written and verified ({len(chunks)} chunks).")
    finally:
        for tmpf in (cf, vf):
            if os.path.exists(tmpf):
                os.remove(tmpf)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "_pgm":
        worker_pgm(int(sys.argv[2], 16), sys.argv[3],
                   len(sys.argv) > 4 and sys.argv[4] == "ro_ok")
    elif len(sys.argv) >= 2 and sys.argv[1] == "_rd":
        worker_rd(int(sys.argv[2], 16), int(sys.argv[3], 16), sys.argv[4])
    else:
        ap = argparse.ArgumentParser(
            prog="raiden_write_region.py",
            description="Region-aware erase+program+verify writer for gale's AP SPI "
                        "flash over the EC raiden bridge. Dry-run by default.")
        ap.add_argument("src", help="8 MiB source image (must contain a valid FMAP)")
        ap.add_argument("region", help="FMAP region name (e.g. RW_LEGACY) or 0xOFF:0xLEN")
        ap.add_argument("--chunk", type=lambda x: int(x, 0), default=0x4000, metavar="N",
                        help="bytes per fresh-session chunk (default 0x4000; larger "
                             "risks the per-session cliff)")
        ap.add_argument("--commit", action="store_true",
                        help="actually erase+program (default: dry-run only)")
        ap.add_argument("--allow-ro", action="store_true",
                        help="permit writes below 0x400000 (RO/bootblock; bricking risk)")
        ap.add_argument("--no-verify", action="store_true",
                        help="skip per-chunk read-back verify (DANGEROUS)")
        orchestrate(ap.parse_args())


if __name__ == "__main__":
    main()
