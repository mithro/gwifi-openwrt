"""Dump FMAP regions from a flashrom image (no hardware dependencies)."""
import struct
import sys


def main(path):
    buf = open(path, "rb").read()
    HDR = "<8sBBQI32sH"
    HSZ = struct.calcsize(HDR)
    ASZ = struct.calcsize("<II32sH")
    start = 0
    while True:
        i = buf.find(b"__FMAP__", start)
        if i < 0:
            print("no FMAP found")
            return 2
        start = i + 1
        sig, vmaj, vmin, base, size, name, nareas = struct.unpack_from(HDR, buf, i)
        if vmaj == 1 and 1 <= nareas <= 64 and size == len(buf):
            break
    name_s = name.split(b"\x00", 1)[0].decode("latin1")
    print(f"FMAP at file offset 0x{i:06x}, v{vmaj}.{vmin}, base=0x{base:x}, "
          f"size=0x{size:x} ({size/1024/1024:.1f} MiB), name={name_s!r}, "
          f"nareas={nareas}")
    print()
    print(f"  {'NAME':24s}  {'OFFSET':>10s}  {'SIZE':>10s}  {'SIZE_KiB':>10s}  END")
    rows = []
    for a in range(nareas):
        o = i + HSZ + a * ASZ
        ao, asz, an, fl = struct.unpack_from("<II32sH", buf, o)
        nm = an.split(b"\x00", 1)[0].decode("latin1")
        rows.append((ao, asz, nm))
    for ao, asz, nm in sorted(rows):
        print(f"  {nm:24s}  0x{ao:08x}  0x{asz:08x}  {asz/1024:>10.1f}  "
              f"0x{ao+asz:08x}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
