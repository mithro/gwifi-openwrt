#!/usr/bin/env python3
"""Diff the live gale AP SPI flash against a provided image file.

Reads the hardware over the EC raiden bridge (fail-loud; reads are faithful at
every flash address) and reports which 4 KiB sectors differ from <image>,
grouped by FMAP region. READ-ONLY -- the only device state change is parking the
AP before each read.

The EC bridge reads reliably only < ~84 KiB per enable-session, so each chunk is
read in a FRESH worker process (the only thing that resets the per-session
cliff) -- the same orchestrator/worker model as raiden_write_region.py.

Exit status (like cmp): 0 = identical, 1 = differences found, 2 = error.

USAGE
  flash_diff.py <image.bin>                    # diff the whole 8 MiB chip
  flash_diff.py <image.bin> RW_SECTION_A       # diff one FMAP region (named in <image>)
  flash_diff.py <image.bin> 0x400000:0x160000  # diff an explicit 0xOFF:0xLEN span
    [--chunk 0x10000] [--quiet]
  Internal worker (spawned automatically; not for direct use):
    _rd <0xoff> <0xlen> <outfile>
"""
import argparse
import hashlib
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find raiden.py beside us
from raiden import Raiden, V1_MAX  # noqa: E402

CHIP_SIZE = 8 * 1024 * 1024
SECTOR = 0x1000
RO_LIMIT = 0x400000                # below this = RO_SECTION/WP_RO (bricking-risk to write)
SELF = os.path.abspath(__file__)
TMP = os.environ.get("GALE_WORK", os.path.dirname(SELF))  # scratch dir for the read worker
# big FMAP container regions to omit from the per-span name list (noise)
CONTAINERS = {"WP_RO", "RO_SECTION", "RW_SECTION_A", "RW_SECTION_B", "RW_GPT", "RW_MISC"}


# ---------- read worker (each is its own fresh process == session-cliff reset) ----------

def worker_rd(off, length, outfile):
    """Read [off,off+length) over raiden and write it to outfile. read_data goes
    through the shared fail-loud xfer (raises on any short/garbled read), so a
    cliff hit or USB error aborts loudly here, never returns silent zeros."""
    with Raiden() as r:
        buf = bytearray()
        i = 0
        while i < length:
            k = min(V1_MAX, length - i)
            buf += r.read_data(off + i, k)
            i += k
        if len(buf) != length:
            raise SystemExit(f"_rd: assembled {len(buf)} != requested 0x{length:x}")
        open(outfile, "wb").write(buf)


# ---------- FMAP (parsed from the reference image) ----------

def parse_fmap(buf):
    HDR = "<8sBBQI32sH"; HSZ = struct.calcsize(HDR); ASZ = struct.calcsize("<II32sH")
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
        areas, ok = {}, True
        for a in range(nareas):
            o = i + HSZ + a * ASZ
            if o + ASZ > len(buf):
                ok = False; break
            ao, asz, an, fl = struct.unpack_from("<II32sH", buf, o)
            areas[an.split(b"\0")[0].decode("latin1")] = (ao, asz)
        if ok and areas:
            return areas


def regions_for(off, length, fmap):
    hits = [(o, nm) for nm, (o, s) in fmap.items()
            if o < off + length and o + s > off and nm not in CONTAINERS]
    return ",".join(nm for _, nm in sorted(hits)) or "(unnamed)"


def resolve_target(spec, fmap):
    """(off, length, label) for None=whole chip, a 0xOFF:0xLEN span, or FMAP name."""
    if spec is None:
        return 0, CHIP_SIZE, "whole chip"
    if ":" in spec and spec.lower().startswith("0x"):
        o_str, l_str = spec.split(":")
        return int(o_str, 16), int(l_str, 16), spec
    if spec not in fmap:
        raise SystemExit(f"region {spec!r} not in <image> FMAP. Known: {sorted(fmap)}")
    off, length = fmap[spec]
    return off, length, spec


# ---------- orchestrator ----------

def diff(args):
    image = open(args.image, "rb").read()
    if len(image) != CHIP_SIZE:
        raise SystemExit(f"image {args.image} is {len(image)} B (need {CHIP_SIZE})")
    fmap = parse_fmap(image) or {}
    off, length, label = resolve_target(args.region, fmap)
    if length <= 0 or off < 0 or off + length > CHIP_SIZE:
        raise SystemExit(f"target 0x{off:x}+0x{length:x} out of range (chip is {CHIP_SIZE} B)")

    if not args.quiet:
        print(f"== flash_diff: device  vs  {args.image}")
        print(f"   target = {label}  (0x{off:06x}..0x{off + length:06x}, "
              f"0x{length:x} = {length / 1024:.0f} KiB)")
        print(f"   chunk  = 0x{args.chunk:x}   READ-ONLY (parks AP before each chunk)")

    # read [off,off+length) one fresh worker process per chunk (cliff reset).
    # The EC bridge occasionally reports RDID=000000 ("not ready") on a fresh
    # ENABLE -- a transient bring-up glitch, NOT bad data. So retry the whole
    # fresh-process read a few times before giving up. Fail-loud is preserved:
    # data is accepted ONLY on rc==0 AND exact length; a mid-read framing error
    # still raises inside the worker; and once the retry budget is spent we
    # sys.exit(2). We never accept a short/zero read as flash content.
    READ_TRIES = 4
    cf = f"{TMP}/_diff_rd.bin"
    hw = bytearray()
    a = off
    while a < off + length:
        clen = min(args.chunk, off + length - a)
        data = None
        for attempt in range(1, READ_TRIES + 1):
            if os.path.exists(cf):
                os.remove(cf)
            p = subprocess.run([sys.executable, SELF, "_rd", hex(a), hex(clen), cf],
                               capture_output=True, text=True)
            got = open(cf, "rb").read() if os.path.exists(cf) else b""
            if p.returncode == 0 and len(got) == clen:
                data = got
                break
            err = (p.stdout + p.stderr).strip()
            if attempt < READ_TRIES:
                print(f"   [0x{a:06x}] read attempt {attempt}/{READ_TRIES} failed "
                      f"(rc={p.returncode}, got {len(got)}/{clen} B); re-parking + retrying",
                      file=sys.stderr)
            else:
                print(f"ERROR: read failed at 0x{a:06x} after {READ_TRIES} attempts "
                      f"(rc={p.returncode}, got {len(got)}/{clen} B):\n" + err, file=sys.stderr)
                if os.path.exists(cf):
                    os.remove(cf)
                sys.exit(2)
        nb = sum(1 for x, y in zip(data, image[a:a + clen]) if x != y)
        if not args.quiet and (nb or (a // args.chunk) % 8 == 0):
            print(f"   [0x{a:06x}] {clen // 1024:>3d} KiB  "
                  + (f"{nb} B differ" if nb else "match"))
        hw += data
        a += clen
    if os.path.exists(cf):
        os.remove(cf)

    hw = bytes(hw)
    img = image[off:off + length]
    diff_bytes = sum(1 for x, y in zip(hw, img) if x != y)

    # which absolute 4 KiB sectors overlapping the target actually differ?
    diff_sectors = []
    sec = off - (off % SECTOR)
    while sec < off + length:
        s0, s1 = max(sec, off), min(sec + SECTOR, off + length)
        if hw[s0 - off:s1 - off] != img[s0 - off:s1 - off]:
            diff_sectors.append(sec)
        sec += SECTOR

    spans = []
    for o in diff_sectors:
        if spans and spans[-1][0] + spans[-1][1] == o:
            spans[-1] = (spans[-1][0], spans[-1][1] + SECTOR)
        else:
            spans.append((o, SECTOR))

    print(f"\n=== DIFF: device vs {os.path.basename(args.image)} ===")
    print(f"   range            : 0x{off:06x}..0x{off + length:06x} ({length / 1024:.0f} KiB)")
    print(f"   differing bytes  : {diff_bytes}/{length} ({100 * diff_bytes / length:.3f}%)")
    if off == 0 and length == CHIP_SIZE:
        first = next((i for i in range(length) if hw[i] != img[i]), None)
        print(f"   device sha256    : {hashlib.sha256(hw).hexdigest()}")
        print(f"   image  sha256    : {hashlib.sha256(img).hexdigest()}")
        print(f"   first diff       : {('0x%06x' % first) if first is not None else 'NONE (identical)'}")
    if not spans:
        print("   => IDENTICAL")
        sys.exit(0)
    has_ro = any(o < RO_LIMIT for o, _ in spans)
    print(f"   differing sectors: {len(diff_sectors)} (4 KiB) in {len(spans)} spans"
          + ("  [includes RO]" if has_ro else "") + ":")
    for (o, ln) in spans:
        zone = "RO" if o < RO_LIMIT else "RW"
        flag = "  <== RO (needs --allow-ro to write)" if o < RO_LIMIT else ""
        print(f"     [{zone}] 0x{o:06x}:0x{ln:06x}  ({ln // 1024:>4d} KiB)  "
              f"{regions_for(o, ln, fmap)}{flag}")
    print("   => DIFFERENCES FOUND")
    sys.exit(1)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "_rd":
        worker_rd(int(sys.argv[2], 16), int(sys.argv[3], 16), sys.argv[4])
        return
    ap = argparse.ArgumentParser(
        prog="flash_diff.py",
        description="Diff the live gale AP SPI flash against an image file "
                    "(read-only; exit 0=identical, 1=differs, 2=error).")
    ap.add_argument("image", help="8 MiB reference image (must contain a valid FMAP)")
    ap.add_argument("region", nargs="?", default=None,
                    help="FMAP region name (e.g. RW_SECTION_A) or 0xOFF:0xLEN span; "
                         "default = whole chip")
    ap.add_argument("--chunk", type=lambda x: int(x, 0), default=0x10000, metavar="N",
                    help="bytes per fresh-session read chunk (default 0x10000; keep "
                         "under the ~84 KiB read cliff)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the header and per-chunk progress lines")
    diff(ap.parse_args())


if __name__ == "__main__":
    main()
