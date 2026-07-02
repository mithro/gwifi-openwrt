#!/usr/bin/env python3
"""Faithful CHUNKED read of the gale AP SPI flash through the EC raiden bridge.

Why chunks: the EC USB-SPI (raiden) bridge only returns reliable data for reads
< ~84 KiB, and flashrom hands the SPI bus back to the AP (auto power-on) after
every read. So a single 8 MiB read degrades to zeros past the first piece -- which
is exactly why earlier full-chip reads looked "99% 0x00 / bricked". This reads the
flash in 64 KiB pieces, RE-PARKING the AP (EC 'gale power off') before EACH piece,
and stitches them into a faithful image.

Why double-read: even inside the reliable window the bridge can return short
bursts of 0x00 in place of real data with flashrom still exiting 0, so every
chunk is read in two independent sessions and accepted only when both agree
byte-for-byte (see read_chunk).

READ-ONLY. The only state change is 'gale power off' (park AP + grant EC the SPI
bus) -- the approved park+read operation. No erase, no program, no gpioset, no
reliance on EC-reported gpio values (which may be stale).

Usage:
  chunk_read.py test                  # 3 scattered 64K chunks vs stock (method check)
  chunk_read.py all  <out.bin>        # full 8 MiB stitched -> out.bin, compared to stock
  chunk_read.py 0x300000 0x400000     # specific offsets vs stock
"""
import hashlib
import os
import subprocess
import sys
import time

import serial  # python3-serial, system dist-packages on the Pi

BYID = "/dev/serial/by-id/usb-Google_Inc._Gale_debug-if00-port0"
EC_PORT = os.path.realpath(BYID) if os.path.exists(BYID) else "/dev/ttyUSB0"
# Rig paths overridable via env (see README); defaults = the original dev rig.
FLASHROM = os.environ.get("GALE_FLASHROM", "/home/tim/local/gwifi/flashrom-cros/build/flashrom")
CHIP = os.environ.get("GALE_CHIP", "W25Q64BV/W25Q64CV/W25Q64FV")
STOCK = os.environ.get("GALE_STOCK", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "gale-spi-stock-2026-05-28.bin"))  # repo-shipped reference for the vs-stock diff
SIZE = 8 * 1024 * 1024
CHUNK = 64 * 1024          # 0x10000, comfortably under the ~84 KiB reliable limit
TMP = os.environ.get("GALE_WORK", os.path.dirname(os.path.abspath(__file__)))
LAY = f"{TMP}/_chunk_layout.txt"
THROW = f"{TMP}/_chunk_throwaway.bin"


def ec_park():
    """Send 'gale power off' to the EC: parks the AP and grants the EC the SPI bus.
    Opens and CLOSES the EC console before flashrom touches the raiden interface."""
    with serial.Serial(EC_PORT, 115200, timeout=0.2) as s:
        time.sleep(0.2)
        s.reset_input_buffer()
        s.write(b"gale power off\r\n")
        s.flush()
        time.sleep(0.8)
        if s.in_waiting:
            s.read(s.in_waiting)
    time.sleep(0.3)


def build_layout(off, size):
    """Whole-chip layout with [off,off+size) named 'chunk' (avoids gap warnings)."""
    lines = []
    if off > 0:
        lines.append(f"0x000000:0x{off - 1:06x} lo")
    lines.append(f"0x{off:06x}:0x{off + size - 1:06x} chunk")
    if off + size < SIZE:
        lines.append(f"0x{off + size:06x}:0x{SIZE - 1:06x} hi")
    with open(LAY, "w") as f:
        f.write("\n".join(lines) + "\n")


def _read_chunk_session(off, size, outpath, retries=1):
    """Park, then flashrom-read ONLY [off,off+size) via -i chunk:outpath.

    A read counts as success only if the file is full-size AND flashrom exited 0.
    A full-size file with nonzero rc is retried (up to `retries` times) and, if it
    never returns rc==0, handed back WITH that nonzero rc so callers fail loud --
    so a persistent flashrom error costs `retries`+1 park+read device sessions.
    """
    for attempt in range(retries + 1):
        build_layout(off, size)
        for p in (outpath, THROW):
            if os.path.exists(p):
                os.remove(p)
        ec_park()
        cmd = [FLASHROM, "-p", "raiden_debug_spi", "-c", CHIP,
               "-l", LAY, "-i", f"chunk:{outpath}", "-r", THROW]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        data = open(outpath, "rb").read() if os.path.exists(outpath) else b""
        # A read is valid only if BOTH signals agree: full length AND flashrom
        # exited 0. A nonzero rc with a full-size file (e.g. a stale same-size
        # file from a prior failed attempt) must NOT be accepted as good data.
        if len(data) == size and proc.returncode == 0:
            return proc.returncode, data, proc.stdout + proc.stderr, attempt
        if attempt < retries:
            time.sleep(0.5)
    return proc.returncode, data, proc.stdout + proc.stderr, attempt


def read_chunk(off, size, outpath, sessions=6):
    """Double-read verified chunk read: accept data only when two CONSECUTIVE
    independent park+read sessions return byte-identical data.

    Why: the raiden bridge can return short bursts of 0x00 in place of real
    data with flashrom still exiting 0 (observed 2026-07-02: scattered 00s in
    the 0xff CBFS padding of a dump whose flash content was cryptographically
    verified good by verstage at boot).  A single read therefore cannot be
    trusted; a corruption burst repeating byte-identically in two separate
    sessions is not a plausible failure mode.

    Returns (rc, data, log, sessions_used); rc!=0 / empty data on failure so
    callers keep failing loud.
    """
    prev = None
    rc, log = 250, ""
    for used in range(1, sessions + 1):
        rc, data, log, _ = _read_chunk_session(off, size, outpath)
        if len(data) != size or rc != 0:
            prev = None   # a failed session breaks any pending agreement pair
            continue
        if prev == data:
            return 0, data, log, used
        prev = data
    return (rc if rc != 0 else 250), b"", \
        log + "\nno two consecutive sessions returned identical data", sessions


def hx(b, n=16):
    return " ".join(f"{x:02x}" for x in b[:n])


def printable(b, n=24):
    return "".join(chr(x) if 32 <= x < 127 else "." for x in b[:n])


def _run(stock, args, scratch):
    """Dispatch the requested read mode. Adds every scratch temp file it creates
    to `scratch` (removed by main's finally); never adds the user's output file."""
    if args[0] == "all":
        outbin = args[1] if len(args) > 1 else f"{TMP}/gale-chunked-full.bin"
        cur = f"{TMP}/_chunk_cur.bin"
        scratch.add(cur)
        image = bytearray(SIZE)
        bad = []
        t0 = time.time()
        n = SIZE // CHUNK
        for idx in range(n):
            off = idx * CHUNK
            rc, data, log, att = read_chunk(off, CHUNK, cur)
            if len(data) != CHUNK or rc != 0:
                bad.append(off)
                print(f"  [{idx + 1:3d}/{n}] 0x{off:06x}  FAILED rc={rc} got={len(data)}B")
                print("    " + log.strip().replace("\n", "\n    "))
                continue
            image[off:off + CHUNK] = data
            if stock is not None:
                same = sum(1 for a, b in zip(data, stock[off:off + CHUNK]) if a == b)
                if idx % 8 == 0 or same != CHUNK:
                    print(f"  [{idx + 1:3d}/{n}] 0x{off:06x}  rc={rc} att={att} "
                          f"vs-stock={100 * same / CHUNK:5.1f}%")
            elif idx % 8 == 0:
                print(f"  [{idx + 1:3d}/{n}] 0x{off:06x}  rc={rc} att={att}")
        with open(outbin, "wb") as f:
            f.write(image)
        dt = time.time() - t0
        live_sha = hashlib.sha256(image).hexdigest()
        print("\n=== FULL CHUNKED READ COMPLETE ===")
        print(f"  out          = {outbin}")
        print(f"  elapsed      = {dt:.0f}s   failed chunks = {len(bad)}")
        print(f"  live  sha256 = {live_sha}")
        if stock is not None:
            stock_sha = hashlib.sha256(stock).hexdigest()
            same = sum(1 for a, b in zip(image, stock) if a == b)
            first_diff = next((i for i in range(SIZE) if image[i] != stock[i]), None)
            print(f"  stock sha256 = {stock_sha}")
            print(f"  vs stock     = {same}/{SIZE} ({100 * same / SIZE:.2f}%) identical")
            print(f"  first diff   = {('0x%06x' % first_diff) if first_diff is not None else 'NONE (identical)'}")
        if bad:
            print(f"  FAILED offsets: {[hex(x) for x in bad]}")
            # Loud process-level failure: a zero-filled/partial image must never
            # exit 0, or a caller will treat the corrupt output as a faithful read.
            sys.exit(1)
        return

    if args[0] == "test":
        offs = [0x000000, 0x300000, 0x400000]
    else:
        offs = [int(x, 0) for x in args]

    failed = []
    for off in offs:
        cur = f"{TMP}/chunk_{off:06x}.bin"
        scratch.add(cur)
        rc, data, log, att = read_chunk(off, CHUNK, cur)
        print(f"\n===== chunk @ 0x{off:06x} (64 KiB) =====")
        print(f"  flashrom rc={rc}  got={len(data)}B  retries_used={att}")
        if len(data) != CHUNK or rc != 0:
            failed.append(off)
            print(f"  READ FAILED (rc={rc}, got {len(data)}B, want {CHUNK}) -- log:")
            print("    " + log.strip().replace("\n", "\n    "))
            continue
        live_nonzero = sum(1 for x in data if x != 0)
        print(f"  live non-zero: {live_nonzero}/{CHUNK} bytes")
        print(f"  live  [0:16] : {hx(data)}   |{printable(data)}|")
        if stock is not None:
            ref = stock[off:off + CHUNK]
            same = sum(1 for a, b in zip(data, ref) if a == b)
            print(f"  vs stock     : {same}/{CHUNK} ({100 * same / CHUNK:.2f}%) identical")
            print(f"  stock [0:16] : {hx(ref)}   |{printable(ref)}|")
            if off == 0x300000:
                print(f"  FMAP sig live : {data[0:8]!r}   (stock: {ref[0:8]!r})")
        if b"Google_Gale" in data:
            i = data.find(b"Google_Gale")
            print(f"  FOUND 'Google_Gale' @0x{off + i:06x}: {printable(data[i:], 28)!r}")

    if failed:
        sys.exit(f"FAILED chunks (short read or flashrom rc!=0): "
                 f"{[hex(x) for x in failed]}")


def main():
    if os.path.exists(STOCK):
        stock = open(STOCK, "rb").read()
        if len(stock) != SIZE:
            # A *wrong-size* reference is almost always a mistake (truncated file,
            # or GALE_STOCK pointing at the wrong thing). Silently skipping the
            # comparison would make a miscompare look identical to "no reference",
            # so fail loud. A deliberately-absent reference (else branch) is the
            # only tolerated no-comparison case.
            sys.exit(f"FATAL: reference {STOCK} is {len(stock)} B (!= {SIZE}); "
                     f"fix it or unset GALE_STOCK to run without a comparison")
    else:
        stock = None
        print(f"# no reference at {STOCK} (set GALE_STOCK); skipping vs-stock comparison")
    args = sys.argv[1:]
    if not args:
        args = ["test"]

    # Remove every scratch temp file on ANY exit (return, sys.exit, exception).
    # _run() registers the paths it creates; the user's output file is never added.
    scratch = {LAY, THROW}
    try:
        _run(stock, args, scratch)
    finally:
        for p in scratch:
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    main()
