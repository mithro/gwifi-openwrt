"""Offline unit tests for gserial.py - mock pyusb device, NO hardware.

Run:  uv run --no-project --with pyusb --with pytest -m pytest gserial_test.py

The mocks emulate the pyusb object model faithfully enough that gserial's real
code paths run unchanged:

  * endpoint descriptors expose bEndpointAddress / bmAttributes /
    wMaxPacketSize and are iterated from interface descriptors;
  * ``usb.util.claim_interface`` / ``release_interface`` /
    ``dispose_resources`` are the REAL pyusb functions - they dispatch to
    ``device._ctx.managed_claim_interface`` etc., which the FakeCtx records;
  * bulk IN reads return ``array('B', ...)`` (as pyusb does) and raise real
    ``usb.core.USBTimeoutError`` / ``usb.core.USBError`` instances.
"""

import array
import errno
import os
import sys
import time

import pytest
import usb.core
import usb.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gserial
from gserial import (
    AP_INTERFACE,
    EC_INTERFACE,
    GaleConsole,
    GaleConsoleTimeout,
    GaleError,
    PRODUCT_ID,
    VENDOR_ID,
)

BULK = usb.util.ENDPOINT_TYPE_BULK      # 0x02
INTERRUPT = usb.util.ENDPOINT_TYPE_INTR  # 0x03


def timeout_error():
    return usb.core.USBTimeoutError('Operation timed out', -7, errno.ETIMEDOUT)


def stall_error():
    return usb.core.USBError('Pipe error', -9, errno.EPIPE)


# --------------------------------------------------------------------- mocks


class FakeEndpoint:
    def __init__(self, address, attributes=BULK, max_packet=64):
        self.bEndpointAddress = address
        self.bmAttributes = attributes
        self.wMaxPacketSize = max_packet


class FakeBulkInEndpoint(FakeEndpoint):
    """Bulk IN endpoint driven by a script.

    Script items:
      * bytes             -> returned (as array('B'), split to *size*)
      * Exception         -> raised
      * (delay_s, bytes)  -> data arrives after delay_s; if the read's timeout
                             expires first, a real timeout is raised and the
                             remaining delay is kept for the next read.
    Empty script -> sleep out the requested timeout, then raise timeout
    (exactly what libusb does on an idle console).
    """

    def __init__(self, address=0x83, script=None):
        super().__init__(address, BULK)
        self.script = list(script or [])
        self.reads = []  # (size, timeout_ms) of every read call

    def read(self, size, timeout=None):
        self.reads.append((size, timeout))
        timeout_s = (timeout if timeout else 1000) / 1000.0
        if not self.script:
            time.sleep(timeout_s)
            raise timeout_error()
        item = self.script[0]
        if isinstance(item, Exception):
            self.script.pop(0)
            raise item
        if isinstance(item, tuple):
            delay_s, payload = item
            if delay_s > timeout_s:
                time.sleep(timeout_s)
                self.script[0] = (delay_s - timeout_s, payload)
                raise timeout_error()
            time.sleep(delay_s)
            item = payload
        self.script.pop(0)
        data, rest = item[:size], item[size:]
        if rest:
            self.script.insert(0, rest)
        return array.array('B', data)


class FakeBulkOutEndpoint(FakeEndpoint):
    def __init__(self, address=0x03, on_write=None, error=None):
        super().__init__(address, BULK)
        self.writes = []
        self.on_write = on_write
        self.error = error

    def write(self, data, timeout=None):
        if self.error is not None:
            raise self.error
        data = bytes(data)
        self.writes.append(data)
        if self.on_write is not None:
            self.on_write(data)
        return len(data)


class FakeInterface:
    def __init__(self, number, endpoints, iclass=0xFF, alt=0):
        self.bInterfaceNumber = number
        self.bAlternateSetting = alt
        self.bInterfaceClass = iclass
        self._endpoints = list(endpoints)

    def __iter__(self):
        return iter(self._endpoints)


class FakeConfiguration:
    def __init__(self, interfaces):
        self._interfaces = list(interfaces)

    def __iter__(self):
        return iter(self._interfaces)


class FakeCtx:
    """Stands in for pyusb's _ResourceManager; the REAL usb.util helpers
    dispatch to these methods."""

    def __init__(self, device):
        self._device = device

    def managed_claim_interface(self, device, interface):
        self._device.calls.append(('claim', interface))
        self._device.claimed.add(interface)

    def managed_release_interface(self, device, interface):
        self._device.calls.append(('release', interface))
        self._device.claimed.discard(interface)

    def dispose(self, device):
        self._device.calls.append(('dispose',))


class FakeDevice:
    def __init__(self, interfaces, kernel_driver_on=(0, 1)):
        self._cfg = FakeConfiguration(interfaces)
        self.kernel_driver = set(kernel_driver_on)
        self.claimed = set()
        self.calls = []
        self._ctx = FakeCtx(self)

    def get_active_configuration(self):
        return self._cfg

    def is_kernel_driver_active(self, ifnum):
        self.calls.append(('is_kernel_driver_active', ifnum))
        return ifnum in self.kernel_driver

    def detach_kernel_driver(self, ifnum):
        self.calls.append(('detach_kernel_driver', ifnum))
        if ifnum not in self.kernel_driver:
            raise usb.core.USBError('Entity not found', -5, errno.ENOENT)
        self.kernel_driver.discard(ifnum)

    def attach_kernel_driver(self, ifnum):
        self.calls.append(('attach_kernel_driver', ifnum))
        self.kernel_driver.add(ifnum)


def make_device(ec_script=None, ap_script=None, cdc=False, on_ec_write=None,
                kernel_driver_on=(0, 1)):
    """A gale-shaped fake: EC on if0, AP on if1, SPI bridge on if3."""
    ec_in = FakeBulkInEndpoint(0x83, script=ec_script)
    ec_out = FakeBulkOutEndpoint(0x03, on_write=on_ec_write)
    ec_eps = [ec_out, ec_in]  # OUT listed first: order must not matter
    if cdc:
        # CDC-ACM style: an interrupt notification endpoint to be ignored.
        ec_eps = [FakeEndpoint(0x85, INTERRUPT, 16)] + ec_eps
    interfaces = [
        FakeInterface(EC_INTERFACE, ec_eps, iclass=0x0A if cdc else 0xFF),
        FakeInterface(AP_INTERFACE,
                      [FakeBulkInEndpoint(0x84, script=ap_script),
                       FakeBulkOutEndpoint(0x04)]),
        # Vendor SPI bridge (owned by another tool) - must never be chosen.
        FakeInterface(3, [FakeBulkInEndpoint(0x82),
                          FakeBulkOutEndpoint(0x02)]),
    ]
    return FakeDevice(interfaces, kernel_driver_on=kernel_driver_on)


def ec_in_ep(dev):
    for intf in dev.get_active_configuration():
        if intf.bInterfaceNumber == EC_INTERFACE:
            for ep in intf:
                if isinstance(ep, FakeBulkInEndpoint):
                    return ep
    raise AssertionError('no EC bulk IN in fake device')


# --------------------------------------------------- endpoint/iface discovery


def test_discovers_bulk_pair_vendor_interface():
    dev = make_device()
    with GaleConsole(dev, which='ec') as con:
        assert con.bulk_in_address == 0x83
        assert con.bulk_out_address == 0x03


def test_discovers_bulk_pair_cdc_interface_ignoring_interrupt_ep():
    dev = make_device(cdc=True)
    with GaleConsole(dev, which='ec') as con:
        # Interrupt EP 0x85 must have been skipped.
        assert con.bulk_in_address == 0x83
        assert con.bulk_out_address == 0x03


def test_selects_ap_interface():
    dev = make_device()
    with GaleConsole(dev, which='ap') as con:
        assert con.interface_number == AP_INTERFACE
        assert con.bulk_in_address == 0x84
        assert con.bulk_out_address == 0x04
    # Only interface 1 was ever claimed - never the SPI bridge (3).
    claims = [c for c in dev.calls if c[0] == 'claim']
    assert claims == [('claim', AP_INTERFACE)]


def test_missing_bulk_out_is_fatal():
    dev = FakeDevice([
        FakeInterface(EC_INTERFACE, [FakeBulkInEndpoint(0x83)]),
    ])
    with pytest.raises(GaleError, match='bulk'):
        GaleConsole(dev, which='ec').open()


def test_interrupt_only_interface_is_fatal():
    dev = FakeDevice([
        FakeInterface(EC_INTERFACE, [FakeEndpoint(0x85, INTERRUPT, 16)]),
    ])
    with pytest.raises(GaleError, match='bulk'):
        GaleConsole(dev, which='ec').open()


def test_missing_interface_is_fatal():
    dev = FakeDevice([FakeInterface(7, [FakeBulkInEndpoint(0x83),
                                        FakeBulkOutEndpoint(0x03)])])
    with pytest.raises(GaleError, match='interface 0'):
        GaleConsole(dev, which='ec').open()


def test_invalid_which_rejected_early():
    with pytest.raises(ValueError):
        GaleConsole(None, which='spi')


# -------------------------------------------------------------- device find


def test_find_device_by_vid_pid(monkeypatch):
    dev = make_device()
    seen = {}

    def fake_find(**kwargs):
        seen.update(kwargs)
        return dev

    monkeypatch.setattr(usb.core, 'find', fake_find)
    with GaleConsole(None, which='ec') as con:
        assert con.is_open
    assert seen == {'idVendor': VENDOR_ID, 'idProduct': PRODUCT_ID}
    assert seen == {'idVendor': 0x18D1, 'idProduct': 0x500F}
    # Library found the device itself -> it disposes it on close.
    assert ('dispose',) in dev.calls


def test_device_not_found(monkeypatch):
    monkeypatch.setattr(usb.core, 'find', lambda **kw: None)
    with pytest.raises(GaleError, match='not found'):
        GaleConsole(None, which='ec').open()


def test_passed_in_device_is_not_disposed():
    dev = make_device()
    with GaleConsole(dev, which='ec'):
        pass
    assert ('dispose',) not in dev.calls


# ------------------------------------------------------- claim/detach/release


def test_detach_claim_release_sequence_with_kernel_driver():
    dev = make_device(kernel_driver_on=(0, 1))
    con = GaleConsole(dev, which='ec')
    with con:
        pass
    relevant = [c for c in dev.calls
                if c[0] in ('is_kernel_driver_active', 'detach_kernel_driver',
                            'claim', 'release', 'attach_kernel_driver')]
    assert relevant == [
        ('is_kernel_driver_active', EC_INTERFACE),
        ('detach_kernel_driver', EC_INTERFACE),
        ('claim', EC_INTERFACE),
        ('release', EC_INTERFACE),
    ]
    # Default: kernel driver NOT reattached.
    assert EC_INTERFACE not in dev.kernel_driver


def test_reattach_kernel_driver_on_close_when_requested():
    dev = make_device(kernel_driver_on=(0,))
    with GaleConsole(dev, which='ec', reattach_kernel_driver=True):
        pass
    assert dev.calls[-1] == ('attach_kernel_driver', EC_INTERFACE)
    assert EC_INTERFACE in dev.kernel_driver


def test_no_detach_and_no_reattach_when_no_kernel_driver():
    dev = make_device(kernel_driver_on=())
    with GaleConsole(dev, which='ec', reattach_kernel_driver=True):
        pass
    kinds = [c[0] for c in dev.calls]
    assert 'detach_kernel_driver' not in kinds
    assert 'attach_kernel_driver' not in kinds
    assert kinds.count('claim') == 1
    assert kinds.count('release') == 1


def test_release_happens_even_on_exception_in_body():
    dev = make_device()
    with pytest.raises(RuntimeError, match='boom'):
        with GaleConsole(dev, which='ec') as con:
            raise RuntimeError('boom')
    assert ('release', EC_INTERFACE) in dev.calls
    assert not dev.claimed
    assert not con.is_open


def test_close_is_idempotent():
    dev = make_device()
    con = GaleConsole(dev, which='ec').open()
    con.close()
    con.close()
    assert [c for c in dev.calls if c[0] == 'release'] == \
        [('release', EC_INTERFACE)]


def test_double_open_rejected():
    dev = make_device()
    con = GaleConsole(dev, which='ec').open()
    try:
        with pytest.raises(GaleError, match='already open'):
            con.open()
    finally:
        con.close()


# --------------------------------------------------------------------- read


def test_read_returns_data_as_bytes():
    dev = make_device(ec_script=[b'hello'])
    with GaleConsole(dev, which='ec') as con:
        data = con.read(50)
        assert data == b'hello'
        assert isinstance(data, bytes)


def test_read_timeout_returns_empty_bytes():
    dev = make_device(ec_script=[])  # idle console
    with GaleConsole(dev, which='ec') as con:
        assert con.read(20) == b''


def test_read_stall_raises():
    dev = make_device(ec_script=[stall_error()])
    with GaleConsole(dev, which='ec') as con:
        with pytest.raises(usb.core.USBError) as excinfo:
            con.read(50)
        assert excinfo.value.errno == errno.EPIPE


def test_read_no_device_raises():
    dev = make_device(
        ec_script=[usb.core.USBError('No such device', -4, errno.ENODEV)])
    with GaleConsole(dev, which='ec') as con:
        with pytest.raises(usb.core.USBError) as excinfo:
            con.read(50)
        assert excinfo.value.errno == errno.ENODEV


def test_read_requests_one_max_packet_and_clamps_zero_timeout():
    dev = make_device(ec_script=[b'x'])
    with GaleConsole(dev, which='ec') as con:
        con.read(0)  # 0 would mean 'infinite' to libusb; must be clamped
    size, timeout = ec_in_ep(dev).reads[0]
    assert size == 64  # the endpoint's wMaxPacketSize
    assert timeout >= 1


def test_read_when_closed_raises():
    dev = make_device()
    con = GaleConsole(dev, which='ec')
    with pytest.raises(GaleError, match='not open'):
        con.read(10)


# --------------------------------------------------------------------- write


def test_write_goes_to_bulk_out():
    dev = make_device()
    with GaleConsole(dev, which='ec') as con:
        n = con.write(b'help\r\n')
    assert n == 6
    ec_out = next(ep for intf in dev.get_active_configuration()
                  for ep in intf if isinstance(ep, FakeBulkOutEndpoint)
                  and ep.bEndpointAddress == 0x03)
    assert ec_out.writes == [b'help\r\n']


def test_write_error_propagates():
    dev = make_device()
    for intf in dev.get_active_configuration():
        for ep in intf:
            if isinstance(ep, FakeBulkOutEndpoint):
                ep.error = stall_error()
    with GaleConsole(dev, which='ec') as con:
        with pytest.raises(usb.core.USBError):
            con.write(b'x')


# ---------------------------------------------------------------- read_until


def test_read_until_assembles_multiple_chunks():
    dev = make_device(ec_script=[b'Chip: npcx\r\n', b'RO: v1.1.', b'5337\r\n',
                                 b'> '])
    with GaleConsole(dev, which='ec') as con:
        out = con.read_until(b'> ', timeout_ms=2000, quiet_ms=30)
    assert out == b'Chip: npcx\r\nRO: v1.1.5337\r\n> '


def test_read_until_marker_split_across_chunks():
    dev = make_device(ec_script=[b'ok\r\n>', b' '])
    with GaleConsole(dev, which='ec') as con:
        out = con.read_until(b'> ', timeout_ms=2000, quiet_ms=30)
    assert out.endswith(b'> ')


def test_read_until_captures_trailing_async_line_within_quiet_window():
    # A log line lands 40 ms AFTER the prompt: with quiet_ms=150 it must be
    # captured, and the call must still return well before the 3 s timeout.
    dev = make_device(ec_script=[b'done\r\n> ', (0.04, b'[async tick]\r\n')])
    with GaleConsole(dev, which='ec') as con:
        t0 = time.monotonic()
        out = con.read_until(b'> ', timeout_ms=3000, quiet_ms=150)
        elapsed = time.monotonic() - t0
    assert out == b'done\r\n> [async tick]\r\n'
    assert 0.15 <= elapsed < 1.5  # quiet window honoured, no full-timeout wait


def test_read_until_overall_timeout_raises_with_partial():
    dev = make_device(ec_script=[b'no prompt here'])  # marker never arrives
    with GaleConsole(dev, which='ec') as con:
        t0 = time.monotonic()
        with pytest.raises(GaleConsoleTimeout) as excinfo:
            con.read_until(b'> ', timeout_ms=150, quiet_ms=30)
        elapsed = time.monotonic() - t0
    assert excinfo.value.partial == b'no prompt here'
    assert 0.10 <= elapsed < 1.0  # deadline respected (with slack)


def test_read_until_is_a_timeout_error():
    dev = make_device()
    with GaleConsole(dev, which='ec') as con:
        with pytest.raises(TimeoutError):
            con.read_until(b'> ', timeout_ms=50, quiet_ms=10)


def test_read_until_returns_buffer_if_marker_seen_but_never_quiet():
    # Continuous chatter after the prompt: overall deadline ends the call and
    # the buffer (marker included) is returned rather than raising.
    script = [b'> '] + [(0.02, b'spam') for _ in range(50)]
    dev = make_device(ec_script=script)
    with GaleConsole(dev, which='ec') as con:
        out = con.read_until(b'> ', timeout_ms=150, quiet_ms=500)
    assert out.startswith(b'> ')
    assert b'spam' in out


def test_read_until_empty_marker_rejected():
    dev = make_device()
    with GaleConsole(dev, which='ec') as con:
        with pytest.raises(ValueError):
            con.read_until(b'', timeout_ms=100)


# ------------------------------------------------------------------- command


def test_command_frames_crlf_and_returns_response():
    dev = make_device()
    ec_in = ec_in_ep(dev)

    def device_side(written):
        assert written == b'version\r\n'
        ec_in.script.extend([b'version\r\n', b'RO: gale_v1.1.5337-0115719\r\n',
                             b'> '])

    for intf in dev.get_active_configuration():
        for ep in intf:
            if isinstance(ep, FakeBulkOutEndpoint) \
                    and ep.bEndpointAddress == 0x03:
                ep.on_write = device_side
                ec_out = ep

    with GaleConsole(dev, which='ec') as con:
        out = con.command('version', timeout_ms=2000, quiet_ms=30)

    assert ec_out.writes == [b'version\r\n']  # cmd + CRLF, exactly once
    assert 'RO: gale_v1.1.5337-0115719' in out
    assert out.endswith('> ')


def test_command_drains_stale_bytes_first():
    # Desynced state: leftover bytes from a previous command sit in the pipe.
    dev = make_device(ec_script=[b'STALE old output\r\n> '])
    ec_in = ec_in_ep(dev)

    def device_side(written):
        ec_in.script.extend([b'sysinfo\r\n', b'Reset flags: 0x00000c02\r\n',
                             b'> '])

    for intf in dev.get_active_configuration():
        for ep in intf:
            if isinstance(ep, FakeBulkOutEndpoint) \
                    and ep.bEndpointAddress == 0x03:
                ep.on_write = device_side

    with GaleConsole(dev, which='ec') as con:
        out = con.command('sysinfo', timeout_ms=2000, quiet_ms=30)

    assert 'STALE' not in out
    assert 'Reset flags: 0x00000c02' in out
    assert out.endswith('> ')


def test_command_prompt_timeout_raises():
    dev = make_device()  # device never answers
    with GaleConsole(dev, which='ec') as con:
        with pytest.raises(GaleConsoleTimeout):
            con.command('version', timeout_ms=100, quiet_ms=20)


# ----------------------------------------------------------------- streaming


def test_ap_streaming_read_pattern():
    """The documented AP-watchdog reader loop: read(); b'' when idle."""
    dev = make_device(ap_script=[b'[    0.000000] Booting Linux',
                                 (0.03, b' on physical CPU 0x0\r\n')])
    got = bytearray()
    with GaleConsole(dev, which='ap') as ap:
        for _ in range(4):
            b = ap.read(60)
            if b:
                got += b
    assert bytes(got) == b'[    0.000000] Booting Linux on physical CPU 0x0\r\n'


# ------------------------------------------------------------------- logging


def test_logger_callback_records_all_traffic_and_lifecycle():
    dev = make_device(ec_script=[b'pong'])
    lines = []
    with GaleConsole(dev, which='ec', logger=lines.append) as con:
        con.write(b'ping')
        assert con.read(50) == b'pong'
        assert con.read(10) == b''  # timeout read is logged too
    text = '\n'.join(lines)
    assert 'claiming interface 0' in text
    assert 'detaching kernel driver' in text
    assert 'releasing interface 0' in text
    assert 'OUT len=4 hex=70696e67' in text  # 'ping'
    assert 'IN  len=4 hex=706f6e67' in text  # 'pong'
    assert 'IN  timeout' in text
    # Every line carries a HH:MM:SS.microsecond timestamp.
    import re
    assert all(re.match(r'^\d{2}:\d{2}:\d{2}\.\d{6} gserial\[', ln)
               for ln in lines), lines


def test_logging_logger_instance_accepted():
    import logging as _logging
    records = []

    class Handler(_logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    lg = _logging.getLogger('gserial-test')
    lg.setLevel(_logging.DEBUG)
    lg.addHandler(Handler())
    dev = make_device()
    with GaleConsole(dev, which='ec', logger=lg):
        pass
    assert any('claiming interface 0' in m for m in records)


def test_bad_logger_rejected():
    with pytest.raises(TypeError):
        GaleConsole(None, which='ec', logger=42)


if __name__ == '__main__':
    sys.exit(pytest.main([os.path.abspath(__file__), '-v']))
