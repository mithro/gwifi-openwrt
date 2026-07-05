"""gserial - direct libusb/pyusb transport for Google Wifi "gale" USB debug consoles.

The gale debug device enumerates as USB ``18d1:500f`` and exposes its two
consoles as plain USB bulk-endpoint pairs:

  * interface 0 - EC command console (interactive shell, prompt ``> ``)
  * interface 1 - AP console (mostly one-way boot/kernel log stream)

This module talks to those interfaces *directly* via libusb (pyusb), bypassing
the kernel ttyACM/ttyUSB path entirely.  There is no baud rate, parity, or
DTR/RTS on this side of the link - the consoles are raw byte streams over USB
bulk transfers - so none is configured.  Bulk IN/OUT endpoint addresses are
discovered dynamically by walking the interface's endpoint descriptors (works
for both CDC-ACM-style interfaces, whose interrupt notification endpoint is
ignored, and vendor-specific interfaces with just the bulk pair).

Dependencies: pyusb only (plus stdlib).  No other project files.

API summary
-----------

    from gserial import GaleConsole

    # EC console: interactive commands.
    with GaleConsole(which='ec', logger=print) as ec:
        out = ec.command('version')          # -> decoded str incl. echo+prompt
        out = ec.command('sysinfo')

    # AP console: streaming reader (caller supplies the thread/policy).
    with GaleConsole(which='ap') as ap:
        while True:
            b = ap.read(200)                 # b'' on quiet 200 ms - normal
            if b:
                handle(b)

Transport methods:

  * ``write(data)``                     - one bulk OUT transfer (all-or-error).
  * ``read(timeout_ms, size=None)``     - one bulk IN transfer; returns ``b''``
                                          on a libusb timeout with no data
                                          (normal for a console), raises any
                                          other USB error (STALL, ENODEV, ...).
  * ``read_until(marker, timeout_ms, quiet_ms)``
                                        - accumulate reads until *marker* has
                                          appeared AND the stream has been
                                          quiet for *quiet_ms* (catches
                                          trailing async lines).  Raises
                                          GaleConsoleTimeout (with ``.partial``)
                                          if the marker never appears within
                                          *timeout_ms*.
  * ``command(cmd, prompt=b'> ', ...)`` - EC helper: drain stale bytes, send
                                          ``cmd + '\\r\\n'``, read_until prompt,
                                          return decoded text.
  * ``drain()``                         - read+discard pending bytes.

Lifecycle: ``__enter__``/``open()`` finds the device (if one was not passed),
locates the interface + bulk endpoints, detaches the kernel driver if attached,
and claims the interface.  ``__exit__``/``close()`` releases the interface,
optionally reattaches the kernel driver, and disposes resources for devices the
library itself found.  The active configuration is never (re)set, so other
interfaces (e.g. the vendor SPI bridge on interface 3, owned by another tool)
are not disturbed.

Logging: pass ``logger=`` either a plain ``callable(str)`` or a
``logging.Logger``.  Every bulk IN and OUT (direction, length, full hex) and
every detach/claim/release/attach/dispose step is recorded with a timestamp.

PENDING LIVE HARDWARE VALIDATION
--------------------------------
This module has so far been validated ONLY against offline mocks
(``gserial_test.py``).  The live test to run once the device is healthy and
handed over:

  1. EC console round-trip: ``with GaleConsole(which='ec') as ec:`` then
     ``ec.command('version')`` and ``ec.command('sysinfo')`` - each must return
     text terminated by the ``> `` prompt; repeat a number of times to confirm
     reliability (no desync) across fresh bulk reads.
  2. AP console streaming: ``with GaleConsole(which='ap') as ap:`` loop
     ``ap.read(200)`` in a thread while the AP boots - confirm nonzero byte
     bursts (boot log lines) are observed.
  3. Confirm kernel-driver detach on open and (with
     ``reattach_kernel_driver=True``) reattach on close leaves the system tty
     usable again.
"""

import logging
import time

import usb.core
import usb.util

__all__ = [
    'GaleConsole',
    'GaleError',
    'GaleConsoleTimeout',
    'VENDOR_ID',
    'PRODUCT_ID',
    'EC_INTERFACE',
    'AP_INTERFACE',
    'CONSOLE_INTERFACES',
]

#: USB identity of the gale debug device.
VENDOR_ID = 0x18D1
PRODUCT_ID = 0x500F

#: bInterfaceNumber of the EC command console (interactive shell, prompt '> ').
EC_INTERFACE = 0
#: bInterfaceNumber of the AP console (log stream).
AP_INTERFACE = 1
#: NOTE: interface 3 is the vendor SPI bridge - owned by another tool, never
#: touched here.

CONSOLE_INTERFACES = {
    'ec': EC_INTERFACE,
    'ap': AP_INTERFACE,
}

#: EC shell prompt.
EC_PROMPT = b'> '

#: libusb backend error code for a transfer timeout (LIBUSB_ERROR_TIMEOUT).
_LIBUSB_ERROR_TIMEOUT = -7
#: errno for a timeout, as some pyusb/libusb combinations report it.
_ETIMEDOUT = 110


class GaleError(Exception):
    """A genuine gserial error (device missing, bad descriptors, misuse)."""


class GaleConsoleTimeout(GaleError, TimeoutError):
    """read_until() overall timeout elapsed without the marker appearing.

    ``partial`` holds whatever bytes were accumulated before the deadline.
    """

    def __init__(self, message, partial=b''):
        super().__init__(message)
        self.partial = bytes(partial)


def _is_timeout(exc):
    """True if *exc* is a libusb 'transfer timed out' error (normal, no data).

    Handles both modern pyusb (USBTimeoutError) and older pyusb where a plain
    USBError carries the libusb/backend timeout code.
    """
    timeout_cls = getattr(usb.core, 'USBTimeoutError', None)
    if timeout_cls is not None and isinstance(exc, timeout_cls):
        return True
    if isinstance(exc, usb.core.USBError):
        if getattr(exc, 'backend_error_code', None) == _LIBUSB_ERROR_TIMEOUT:
            return True
        if exc.errno == _ETIMEDOUT:
            return True
    return False


def _find_bulk_endpoints(intf):
    """Walk *intf*'s endpoint descriptors; return (bulk_in, bulk_out).

    Non-bulk endpoints (e.g. a CDC-ACM interrupt notification endpoint) are
    ignored.  Returns (None, None)-ish partial results if a side is missing;
    the caller decides whether that is fatal.
    """
    ep_in = None
    ep_out = None
    for ep in intf:
        if usb.util.endpoint_type(ep.bmAttributes) != usb.util.ENDPOINT_TYPE_BULK:
            continue
        direction = usb.util.endpoint_direction(ep.bEndpointAddress)
        if direction == usb.util.ENDPOINT_IN:
            if ep_in is None:
                ep_in = ep
        else:
            if ep_out is None:
                ep_out = ep
    return ep_in, ep_out


class GaleConsole:
    """One gale USB debug console (EC or AP) over raw libusb bulk transfers.

    Parameters
    ----------
    dev : usb.core.Device or None
        The device to use.  If None, the device is located with
        ``usb.core.find(idVendor=0x18d1, idProduct=0x500f)`` at open time (and
        its libusb resources are disposed at close, since we own it).
    which : 'ec' or 'ap'
        Which console interface to bind (EC_INTERFACE / AP_INTERFACE).
    logger : callable or logging.Logger or None
        Sink for the (verbose, timestamped) transfer/lifecycle log.  A callable
        receives one preformatted string per event; a Logger gets ``.debug()``
        calls.  None uses ``logging.getLogger('gserial')``.
    reattach_kernel_driver : bool
        If True and a kernel driver was detached at open, reattach it at close.
        Default False: for debug-console work, leaving the interface unbound
        avoids getty/ModemManager immediately re-grabbing it.
    write_timeout_ms : int
        Timeout for bulk OUT transfers.

    Use as a context manager; on exit the interface is released even if the
    body raised.
    """

    #: Default size of one bulk IN request, when the endpoint's
    #: wMaxPacketSize is unavailable.  Requesting exactly one max-packet per
    #: transfer means a libusb timeout can never discard partially transferred
    #: data (packets are delivered whole or not at all).
    _DEFAULT_READ_SIZE = 64

    def __init__(self, dev=None, which='ec', logger=None,
                 reattach_kernel_driver=False, write_timeout_ms=1000):
        if which not in CONSOLE_INTERFACES:
            raise ValueError(
                'which must be one of %r, got %r'
                % (sorted(CONSOLE_INTERFACES), which))
        self._dev = dev
        self._which = which
        self._ifnum = CONSOLE_INTERFACES[which]
        self._reattach = bool(reattach_kernel_driver)
        self._write_timeout_ms = int(write_timeout_ms)

        if logger is None:
            self._emit = logging.getLogger('gserial').debug
        elif isinstance(logger, logging.Logger):
            self._emit = logger.debug
        elif callable(logger):
            self._emit = logger
        else:
            raise TypeError('logger must be a callable, logging.Logger or None')

        self._owns_device = False
        self._claimed = False
        self._detached_kernel_driver = False
        self._intf = None
        self._ep_in = None
        self._ep_out = None

    # ----------------------------------------------------------------- log

    def _log(self, fmt, *args):
        ts = time.strftime('%H:%M:%S', time.localtime())
        frac = '%06d' % int((time.time() % 1.0) * 1e6)
        self._emit('%s.%s gserial[%s/if%d] %s'
                   % (ts, frac, self._which, self._ifnum,
                      (fmt % args) if args else fmt))

    # ----------------------------------------------------------- lifecycle

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def open(self):
        """Find device (if needed), locate bulk endpoints, detach + claim."""
        if self._claimed:
            raise GaleError('console already open')

        dev = self._dev
        if dev is None:
            self._log('finding device %04x:%04x', VENDOR_ID, PRODUCT_ID)
            dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
            if dev is None:
                raise GaleError(
                    'gale debug device %04x:%04x not found'
                    % (VENDOR_ID, PRODUCT_ID))
            self._dev = dev
            self._owns_device = True

        # Never set_configuration() here: the device is already configured by
        # the kernel and interface 3 (SPI bridge) may be in use by another
        # tool; reconfiguring would yank it out from under them.
        try:
            cfg = dev.get_active_configuration()
        except usb.core.USBError as exc:
            raise GaleError(
                'cannot read active configuration of %04x:%04x '
                '(device unconfigured or inaccessible): %s'
                % (VENDOR_ID, PRODUCT_ID, exc)) from exc

        intf, ep_in, ep_out = self._locate_interface(cfg)

        detached = False
        try:
            try:
                active = dev.is_kernel_driver_active(self._ifnum)
            except NotImplementedError:
                # Platform backend cannot tell (e.g. Windows); assume none.
                self._log('is_kernel_driver_active unsupported; assuming none')
                active = False
            if active:
                self._log('detaching kernel driver from interface %d',
                          self._ifnum)
                dev.detach_kernel_driver(self._ifnum)
                detached = True
            else:
                self._log('no kernel driver attached to interface %d',
                          self._ifnum)
            self._log('claiming interface %d', self._ifnum)
            usb.util.claim_interface(dev, self._ifnum)
        except Exception:
            if detached and self._reattach:
                try:
                    dev.attach_kernel_driver(self._ifnum)
                except (usb.core.USBError, NotImplementedError) as exc:
                    self._log('reattach after failed claim failed: %s', exc)
            raise

        self._detached_kernel_driver = detached
        self._intf = intf
        self._ep_in = ep_in
        self._ep_out = ep_out
        self._claimed = True
        self._log('open: bulk IN 0x%02x, bulk OUT 0x%02x',
                  ep_in.bEndpointAddress, ep_out.bEndpointAddress)
        return self

    def _locate_interface(self, cfg):
        """Find our bInterfaceNumber in *cfg* and its bulk endpoint pair."""
        candidates = [i for i in cfg
                      if getattr(i, 'bInterfaceNumber', None) == self._ifnum]
        if not candidates:
            raise GaleError(
                'interface %d (%s console) not present on device - '
                'wrong device or configuration?' % (self._ifnum, self._which))
        # An interface may have several alternate settings; use the first one
        # exposing a bulk IN + bulk OUT pair (any interrupt/other endpoints,
        # e.g. a CDC-ACM notification endpoint, are ignored).
        for intf in candidates:
            ep_in, ep_out = _find_bulk_endpoints(intf)
            if ep_in is not None and ep_out is not None:
                self._log(
                    'interface %d (class 0x%02x): bulk IN 0x%02x, '
                    'bulk OUT 0x%02x',
                    self._ifnum, getattr(intf, 'bInterfaceClass', 0),
                    ep_in.bEndpointAddress, ep_out.bEndpointAddress)
                return intf, ep_in, ep_out
        raise GaleError(
            'interface %d (%s console) has no bulk IN + bulk OUT endpoint '
            'pair - not a console interface' % (self._ifnum, self._which))

    def close(self):
        """Release the interface (+ optional kernel-driver reattach).

        Idempotent.  Cleanup errors are logged, not raised, so close() never
        masks an in-flight exception.
        """
        if not self._claimed:
            return
        self._claimed = False
        dev = self._dev
        try:
            self._log('releasing interface %d', self._ifnum)
            usb.util.release_interface(dev, self._ifnum)
        except usb.core.USBError as exc:
            self._log('release_interface failed (continuing): %s', exc)
        if self._detached_kernel_driver and self._reattach:
            try:
                self._log('reattaching kernel driver to interface %d',
                          self._ifnum)
                dev.attach_kernel_driver(self._ifnum)
            except (usb.core.USBError, NotImplementedError) as exc:
                self._log('attach_kernel_driver failed (continuing): %s', exc)
        if self._owns_device:
            try:
                self._log('disposing device resources')
                usb.util.dispose_resources(dev)
            except usb.core.USBError as exc:
                self._log('dispose_resources failed (continuing): %s', exc)
        self._detached_kernel_driver = False
        self._intf = None
        self._ep_in = None
        self._ep_out = None

    # ---------------------------------------------------------- properties

    @property
    def is_open(self):
        return self._claimed

    @property
    def which(self):
        return self._which

    @property
    def interface_number(self):
        return self._ifnum

    @property
    def bulk_in_address(self):
        """bEndpointAddress of the discovered bulk IN endpoint (open only)."""
        self._require_open()
        return self._ep_in.bEndpointAddress

    @property
    def bulk_out_address(self):
        """bEndpointAddress of the discovered bulk OUT endpoint (open only)."""
        self._require_open()
        return self._ep_out.bEndpointAddress

    def _require_open(self):
        if not self._claimed:
            raise GaleError('console is not open')

    # ----------------------------------------------------------- transport

    def write(self, data):
        """One bulk OUT transfer of *data*.  Raises on any USB error or a
        short write."""
        self._require_open()
        data = bytes(data)
        try:
            n = self._ep_out.write(data, timeout=self._write_timeout_ms)
        except usb.core.USBError as exc:
            self._log('OUT ERROR (len=%d hex=%s): %s', len(data), data.hex(),
                      exc)
            raise
        self._log('OUT len=%d hex=%s ascii=%r', len(data), data.hex(), data)
        if n != len(data):
            raise GaleError(
                'short bulk OUT write: %d of %d bytes' % (n, len(data)))
        return n

    def read(self, timeout_ms=100, size=None):
        """One bulk IN transfer; returns b'' if nothing arrived in time.

        A libusb transfer timeout with no data is NORMAL for an idle console
        and yields ``b''``.  Any other USB error (STALL/pipe error, device
        gone, overflow, ...) is raised as-is.

        *size* defaults to the endpoint's wMaxPacketSize: requesting exactly
        one max-packet per transfer guarantees a timeout can never discard a
        partially-filled multi-packet transfer.

        This is also the streaming primitive: a caller's reader thread can
        simply loop ``b = con.read(200); if b: handle(b)``.
        """
        self._require_open()
        timeout_ms = max(1, int(timeout_ms))  # 0 means 'infinite' to libusb
        if size is None:
            size = getattr(self._ep_in, 'wMaxPacketSize', 0) \
                or self._DEFAULT_READ_SIZE
        try:
            data = self._ep_in.read(size, timeout=timeout_ms)
        except usb.core.USBError as exc:
            if _is_timeout(exc):
                self._log('IN  timeout(%dms) len=0', timeout_ms)
                return b''
            self._log('IN  ERROR: %s', exc)
            raise
        data = bytes(data)
        self._log('IN  len=%d hex=%s ascii=%r', len(data), data.hex(), data)
        return data

    def read_until(self, marker, timeout_ms=3000, quiet_ms=100):
        """Accumulate bulk IN data until *marker* seen AND stream quiet.

        Returns once *marker* (searched across chunk boundaries in the whole
        accumulated buffer) has appeared and no further data has arrived for
        *quiet_ms* - so asynchronous lines trailing just after a prompt are
        still captured.  If the overall *timeout_ms* elapses first:

          * marker was seen  -> the buffer so far is returned (stream just
            never went quiet);
          * marker never seen -> GaleConsoleTimeout is raised, with the
            partial buffer attached as ``.partial``.
        """
        self._require_open()
        marker = bytes(marker)
        if not marker:
            raise ValueError('marker must be non-empty')
        buf = bytearray()
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            marker_seen = marker in buf
            remaining_s = deadline - time.monotonic()
            if marker_seen:
                if remaining_s <= 0:
                    return bytes(buf)
                per_read_s = min(quiet_ms / 1000.0, remaining_s)
            else:
                if remaining_s <= 0:
                    raise GaleConsoleTimeout(
                        'marker %r not seen within %d ms (%d bytes buffered)'
                        % (marker, timeout_ms, len(buf)),
                        partial=buf)
                per_read_s = remaining_s
            chunk = self.read(per_read_s * 1000.0)
            if chunk:
                buf += chunk
            elif marker_seen:
                # Quiet window elapsed with the marker present: done.
                return bytes(buf)

    def drain(self, idle_ms=30, max_ms=1000):
        """Read and discard pending bytes until the stream is idle.

        Used to resynchronise before sending a command (stale output from a
        previous command / async EC chatter would otherwise pollute the next
        response).  Returns the discarded bytes (they are also logged).
        """
        self._require_open()
        discarded = bytearray()
        deadline = time.monotonic() + max_ms / 1000.0
        while time.monotonic() < deadline:
            chunk = self.read(idle_ms)
            if not chunk:
                break
            discarded += chunk
        if discarded:
            self._log('drain: discarded %d stale bytes', len(discarded))
        return bytes(discarded)

    def command(self, cmd, prompt=EC_PROMPT, timeout_ms=3000, quiet_ms=100,
                drain_first=True):
        """EC console helper: send *cmd*, wait for *prompt*, return the text.

        Writes ``cmd + '\\r\\n'`` as one bulk OUT, then ``read_until(prompt)``.
        With *drain_first* (default) any stale, desynced bytes still queued
        from earlier output are read off and discarded before the command is
        sent, so the returned text corresponds to THIS command.  Returns the
        full decoded response (including the echoed command and the trailing
        prompt); raises GaleConsoleTimeout if the prompt never appears.
        """
        self._require_open()
        if drain_first:
            self.drain()
        self.write(cmd.encode('utf-8') + b'\r\n')
        raw = self.read_until(prompt, timeout_ms=timeout_ms, quiet_ms=quiet_ms)
        return raw.decode('utf-8', errors='replace')
