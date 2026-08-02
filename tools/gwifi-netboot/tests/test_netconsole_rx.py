# SPDX-License-Identifier: Apache-2.0
"""Tests for the netconsole UDP receiver."""

import socket
import threading
import time

from gwifi_netboot.netconsole_rx import serve


def test_datagrams_land_in_per_source_files(tmp_path):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    t = threading.Thread(
        target=serve,
        kwargs={"bind": ("127.0.0.1", port), "log_dir": tmp_path,
                "max_datagrams": 200},
        daemon=True)
    t.start()

    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    log = tmp_path / "127.0.0.1.log"
    # the serve thread may not have bound yet — retry the first datagram
    # (UDP has no handshake to wait on)
    for _ in range(50):
        tx.sendto(b"[  12.3] ath10k boot\n[  12.4] second line",
                  ("127.0.0.1", port))
        if log.exists():
            break
        time.sleep(0.1)
    tx.sendto(b"Kernel panic - not syncing: test", ("127.0.0.1", port))

    deadline = time.time() + 5
    while time.time() < deadline:
        if log.exists() and "Kernel panic" in log.read_text():
            break
        time.sleep(0.1)

    text = log.read_text()
    assert "ath10k boot" in text
    assert "second line" in text
    assert "Kernel panic" in text
    assert all(line[:2] == "20" for line in text.splitlines())  # stamped


# --- --bind parsing ----------------------------------------------------------
# The receiver's bind address was the module constant DEFAULT_BIND =
# ("10.1.4.2", 6666) -- welland's wisp. The rendered unit now passes the site's
# address explicitly, so the entrypoint must accept one.


def test_parse_bind_accepts_host_and_port():
    from gwifi_netboot.netconsole_rx import parse_bind

    assert parse_bind(["--bind", "10.2.4.2:6666"]) == ("10.2.4.2", 6666)


def test_parse_bind_defaults_when_absent():
    from gwifi_netboot.netconsole_rx import DEFAULT_BIND, parse_bind

    assert parse_bind([]) == DEFAULT_BIND


def test_parse_bind_rejects_a_missing_port():
    import pytest

    from gwifi_netboot.netconsole_rx import parse_bind

    with pytest.raises(SystemExit):
        parse_bind(["--bind", "10.2.4.2"])


def test_parse_bind_rejects_a_non_numeric_port():
    import pytest

    from gwifi_netboot.netconsole_rx import parse_bind

    with pytest.raises(SystemExit):
        parse_bind(["--bind", "10.2.4.2:six"])
