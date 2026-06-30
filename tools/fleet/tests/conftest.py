import pytest
from pathlib import Path
UMBRELLA = Path("/home/tim/local/gwifi")
def _fx(p):
    p = UMBRELLA / p
    return p if p.exists() else None
@pytest.fixture
def stock_g4():
    p = _fx("gale-spi-stock-2026-05-28.bin")
    if not p: pytest.skip("G4 stock fixture absent")
    return p.read_bytes()
@pytest.fixture
def devkey_proto():
    p = _fx("tmp/gale-devkey-bringup.bin")
    if not p: pytest.skip("devkey prototype fixture absent")
    return p.read_bytes()
@pytest.fixture
def prerekey_live():
    p = _fx("tmp/gale-live-2026-06-08-pre-devkey.bin")
    if not p: pytest.skip("pre-devkey live fixture absent")
    return p.read_bytes()
@pytest.fixture
def tftpfirst_proto():
    p = _fx("tmp/gale-depthcharge-tftpfirst.bin")
    if not p: pytest.skip("tftp-first prototype fixture absent")
    return p.read_bytes()
