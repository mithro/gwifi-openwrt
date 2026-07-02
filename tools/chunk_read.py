#!/usr/bin/env python3
"""Faithful CHUNKED read of the gale AP SPI flash through the EC raiden bridge.

Transport: the project's PURE-PYTHON raiden path only -- each session spawns
raiden_write_region.py's `_rd` worker in a fresh process (resets the bridge's
per-session transaction budget; the worker parks via the checked ec_park and
FAILS LOUD on any short/garbled transfer).  flashrom -- stock OR flashrom-cros
-- is NEVER used: its erase path silently no-ops against this chip's SR lock
and its raiden read path returned silent 0x00 bursts with exit code 0.

Why chunks: the bridge honours only a limited per-session transaction budget
(~1444 usb_spi transactions nominal, observed degrading well below that), so
the 8 MiB read goes in small pieces (CHUNK, currently 32 KiB), one fresh
worker per piece, stitched into a faithful image.

Why double-read: a single read cannot be trusted (silent 0x00 bursts, see
above), so every chunk is read in two independent sessions and accepted only
when both agree byte-for-byte (see read_chunk).

READ-ONLY. The only state change is the worker's AP park (checked `gale power
off`) -- the approved park+read operation. No erase, no program, no gpioset.

Usage:
  chunk_read.py test                  # 3 scattered chunks vs stock (method check)
  chunk_read.py all  <out.bin>        # full 8 MiB stitched -> out.bin, compared to stock
  chunk_read.py 0x300000 0x400000     # specific offsets vs stock
"""
import hashlib
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
RWR = os.path.join(_HERE, "raiden_write_region.py")   # `_rd` worker host

STOCK = os.environ.get("GALE_STOCK", os.path.join(
    os.path.dirname(_HERE),
    "gale-spi-stock-2026-05-28.bin"))  # repo-shipped reference for the vs-stock diff
SIZE = 8 * 1024 * 1024
# 32 KiB per park+read session.  The session budget is ~1444 usb_spi
# transactions (= ~87 KiB at 62-byte reads) but it is NOT always the nominal
# value: on 2026-07-02 sessions degraded and zero-filled the tails of 64 KiB
# reads.  32 KiB (~530 transactions + overhead) keeps >2.5x margin against a
# degraded budget; the double-read agreement in read_chunk() backstops the
# rest.
CHUNK = 32 * 1024          # 0x8000
TMP = os.environ.get("GALE_WORK", _HERE)


def _read_chunk_session(off, size, outpath, retries=1):
    """One park+read session of [off,off+size) via the pure-python `_rd` worker.

    The worker runs in a FRESH process (resets the per-session budget), parks
    the AP itself through the checked ec_park (locked-state aware), and raises
    on any short/garbled usb_spi transfer instead of zero-filling.  A read
    counts as success only if the worker exited 0 AND the file is full-size;
    anything else is retried up to `retries` times, then handed back with the
    non-zero rc so callers fail loud.
    """
    for attempt in range(retries + 1):
        if os.path.exists(outpath):
            os.remove(outpath)
        proc = subprocess.run(
            ["python3", RWR, "_rd", hex(off), hex(size), outpath],
            capture_output=True, text=True)
        data = open(outpath, "rb").read() if os.path.exists(outpath) else b""
        # A read is valid only if BOTH signals agree: full length AND worker
        # exit 0. A nonzero rc with a full-size file (e.g. a stale same-size
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
    data with the session still reporting success (observed 2026-07-02: 00s in
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
            # flush=True on every progress line: under nohup/log redirection
            # stdout is block-buffered and a silent multi-minute phase is
            # indistinguishable from a hang for whoever is watching the log.
            if len(data) != CHUNK or rc != 0:
                bad.append(off)
                print(f"  [{idx + 1:3d}/{n}] 0x{off:06x}  FAILED rc={rc} got={len(data)}B",
                      flush=True)
                print("    " + log.strip().replace("\n", "\n    "), flush=True)
                continue
            image[off:off + CHUNK] = data
            if stock is not None:
                same = sum(1 for a, b in zip(data, stock[off:off + CHUNK]) if a == b)
                if idx % 8 == 0 or same != CHUNK:
                    print(f"  [{idx + 1:3d}/{n}] 0x{off:06x}  rc={rc} att={att} "
                          f"vs-stock={100 * same / CHUNK:5.1f}%", flush=True)
            elif idx % 8 == 0:
                print(f"  [{idx + 1:3d}/{n}] 0x{off:06x}  rc={rc} att={att}", flush=True)
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
        print(f"\n===== chunk @ 0x{off:06x} (0x{CHUNK:x} B) =====")
        print(f"  worker rc={rc}  got={len(data)}B  sessions_used={att}")
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
        sys.exit(f"FAILED chunks (short read or worker rc!=0): "
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
    scratch = set()
    try:
        _run(stock, args, scratch)
    finally:
        for p in scratch:
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    main()
