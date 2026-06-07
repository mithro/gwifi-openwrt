#!/usr/bin/env python3
"""Recover function names from the CAPTURED dump with no ELF, by parsing the firmware's own tables.

The EC keeps self-describing tables in rodata that pair a NAME STRING with a HANDLER POINTER:
  * struct console_command {const char *name; int (*handler)(); const char *argdesc, *shorthelp;}
    (DECLARE_CONSOLE_COMMAND) — 16 bytes, name is a printable string, handler is a Thumb code ptr.
These let us label dozens of real functions (command_adc, command_flash_wp, ...) in the captured
binary directly, so the uncovered-branch report is human-readable even though the dump has no symtab.

Used by analyze_uncov.py to group uncovered branches by enclosing function (rda entry points) and
annotate each with its recovered name where known.
"""
import rda

RO_BASE = 0x08000000


def _w(d, a):
    o = a - RO_BASE
    if o < 0 or o + 4 > len(d):
        return None
    return d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)


def _cstr(d, a, maxlen=48):
    o = a - RO_BASE
    s = b""
    while 0 <= o < len(d) and d[o] != 0 and len(s) < maxlen:
        s += bytes([d[o]])
        o += 1
    return s


def _is_code_ptr(v):
    return v is not None and (v & 1) and rda._in_text(v & ~1)


def _is_str_ptr(d, v):
    # name/argdesc/shorthelp are char* into rodata — any byte alignment (odd OR even), and they
    # live ABOVE the .text region (handlers live below). Must point at a printable C string.
    if v is None or not (RO_BASE <= v < RO_BASE + len(d)) or rda._in_text(v):
        return False
    s = _cstr(d, v, 4)
    return len(s) >= 1 and all(32 <= c < 127 for c in s)


def _is_str_or_null(d, v):
    # argdesc / shorthelp are often NULL for commands without help text.
    return v == 0 or _is_str_ptr(d, v)


def _entry_ok(d, a):
    """True if the 16 bytes at `a` look like a console_command struct; returns name or None."""
    w0, w1, w2, w3 = _w(d, a), _w(d, a + 4), _w(d, a + 8), _w(d, a + 12)
    if not (_is_code_ptr(w1) and _is_str_ptr(d, w0)
            and _is_str_or_null(d, w2) and _is_str_or_null(d, w3)):
        return None
    nm = _cstr(d, w0)
    if nm and all(32 <= c < 127 for c in nm) and 1 <= len(nm) <= 20:
        return nm.decode("latin1")
    return None


def recover_console_cmds(binpath):
    """Find the console_command table(s) as the longest CONTIGUOUS runs of valid 16-byte structs
    (robust against isolated false-positive matches elsewhere). Returns {handler_addr: name}."""
    d = open(binpath, "rb").read()
    end = RO_BASE + len(d)
    names = {}
    a = RO_BASE
    while a + 16 <= end:
        nm = _entry_ok(d, a)
        if nm is None:
            a += 4
            continue
        # Found a candidate entry; extend the run forward and only keep runs of >= 4 entries
        # (a real DECLARE_CONSOLE_COMMAND table), which filters coincidental single matches.
        run = []
        b = a
        while b + 16 <= end:
            n = _entry_ok(d, b)
            if n is None:
                break
            run.append((b, n))
            b += 16
        if len(run) >= 4:
            for off, n in run:
                names[_w(d, off + 4) & ~1] = "command_" + n
            a = b
        else:
            a += 4
    return names


def symbol_map(binpath):
    """All recovered handler-addr -> name mappings (currently console commands)."""
    return recover_console_cmds(binpath)


if __name__ == "__main__":
    import sys
    b = sys.argv[1] if len(sys.argv) > 1 else \
        "../../gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"
    m = symbol_map(b)
    print("recovered %d console-command handlers from %s:" % (len(m), b))
    for a in sorted(m):
        print("  0x%08x %s" % (a, m[a]))
