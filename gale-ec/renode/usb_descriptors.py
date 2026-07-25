#!/usr/bin/env python3
"""USB-enumeration equivalence (static) — compare the USB descriptors that the two
firmware images would present to a host.

A full live `lsusb` enumeration needs an STM32 USB-FS device-controller model + a USB
host (future work). But the data enumeration returns — the device descriptor (VID/PID,
class), and the UTF-16 string descriptors ("Gale debug", interface names) — is static
data compiled into each image. If both images contain byte-identical descriptors, they
would enumerate identically. This compares them directly from the two binaries.

This is a STATIC equivalence check (descriptor data), complementing — not replacing —
the live USB-controller execution-trace coverage that the USB-FS device model will add.
"""
import argparse
import re


def device_descriptors(data):
    """Find USB device descriptors: 18 bytes, bLength=0x12, bDescriptorType=0x01,
    with idVendor 0x18d1 / idProduct 0x500f (LE) at offset 8..11."""
    out = []
    vidpid = bytes([0xD1, 0x18, 0x0F, 0x50])
    i = data.find(vidpid)
    while i != -1:
        start = i - 8
        if start >= 0 and data[start] == 0x12 and data[start + 1] == 0x01:
            out.append(data[start:start + 18])
        i = data.find(vidpid, i + 1)
    return out


def usb_strings(data):
    """Find USB string descriptors: bLength, bDescriptorType=0x03, then UTF-16LE text.
    Heuristic: ASCII char followed by 0x00 runs, preceded by a 0x03 type byte."""
    found = set()
    for m in re.finditer(rb"\x03((?:[\x20-\x7e]\x00){3,})", data):
        try:
            found.add(m.group(1).decode("utf-16-le"))
        except UnicodeDecodeError:
            pass
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", required=True)
    ap.add_argument("--rebuilt", required=True)
    args = ap.parse_args()
    o = open(args.orig, "rb").read()
    r = open(args.rebuilt, "rb").read()

    od, rd = device_descriptors(o), device_descriptors(r)
    print("=== USB DEVICE DESCRIPTOR (18d1:500f) ===")
    print("orig:    %s" % (od[0].hex() if od else "<none>"))
    print("rebuilt: %s" % (rd[0].hex() if rd else "<none>"))
    desc_match = bool(od) and bool(rd) and od[0] == rd[0]
    print("device descriptor identical: %s" % desc_match)

    # USB-relevant strings (the enumeration identity). Compare the set the firmware
    # presents over USB — restrict to plausible USB string descriptors.
    keys = ["Gale", "debug", "Shell", "EC", "AP", "Raiden", "Google"]
    os_ = {s for s in usb_strings(o) if any(k in s for k in keys)}
    rs_ = {s for s in usb_strings(r) if any(k in s for k in keys)}
    print("\n=== USB STRING DESCRIPTORS (enumeration identity) ===")
    print("orig:    %s" % sorted(os_))
    print("rebuilt: %s" % sorted(rs_))
    str_match = os_ == rs_
    print("string descriptors identical: %s" % str_match)

    ok = desc_match and str_match
    print("\n%s USB enumeration identity is %sIDENTICAL between the two images"
          % ("[PASS]" if ok else "[FAIL]", "" if ok else "NOT "))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
