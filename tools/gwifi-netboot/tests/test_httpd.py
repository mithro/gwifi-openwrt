# SPDX-License-Identifier: Apache-2.0
"""Tests for the manifest / status / phone-home HTTP API."""

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gwifi_netboot.httpd import App, make_server
from gwifi_netboot.state import StateStore

FIXTURE = Path(__file__).parent / "fixtures" / "pucks.json"
PUCK12_ETH0 = "44:07:0b:01:a2:21"


class FakeInstaller:
    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, content: str, target: Path) -> None:
        self.calls.append(content)


@pytest.fixture()
def app(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    shutil.copy(FIXTURE, etc / "pucks.json")
    a = App(
        identity_path=etc / "pucks.json",
        state=StateStore(tmp_path / "state.json"),
        fragment_path=tmp_path / "gwifi-generated" / "pucks.conf",
        manifest_path=tmp_path / "images" / "manifest.json",
        installer=FakeInstaller(),
    )
    return a


@pytest.fixture()
def server(app):
    srv = make_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url) as resp:
        return resp.status, resp.read()


def post(url, body: bytes, content_type="application/x-www-form-urlencoded"):
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": content_type})
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read()


def test_manifest_404_when_absent(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server + "/manifest")
    assert e.value.code == 404


def test_manifest_served_verbatim(server, app):
    app.manifest_path.parent.mkdir(parents=True)
    app.manifest_path.write_text('{"image_id": "gale-x"}\n')
    status, body = get(server + "/manifest")
    assert status == 200
    assert json.loads(body) == {"image_id": "gale-x"}


def test_status_merges_identity_and_state(server, app):
    app.state.arm([PUCK12_ETH0])
    status, body = get(server + "/status")
    doc = json.loads(body)
    by_name = {p["name"]: p for p in doc["pucks"]}
    assert by_name["puck12"]["armed"] is True
    assert by_name["puck04"]["armed"] is False
    assert doc["unknown"] == {}


def test_phone_home_success_disarms_and_regenerates(server, app):
    app.state.arm([PUCK12_ETH0])
    body = json.dumps({
        "serial": "2831HW00WGD", "mac": PUCK12_ETH0, "result": "success",
        "image_id": "gale-x", "detail": "flashed+verified",
    }).encode()
    # uclient-fetch sends urlencoded content-type; body must parse as JSON
    # regardless.
    status, resp = post(server + "/phone-home", body)
    assert status == 200
    assert app.state.armed_macs() == set()
    assert app.installer.calls, "dnsmasq fragment must be regenerated"
    assert "set:install" not in app.installer.calls[-1]


def test_phone_home_failed_stays_armed(server, app):
    app.state.arm([PUCK12_ETH0])
    body = json.dumps({"serial": "s", "mac": PUCK12_ETH0, "result": "failed",
                       "image_id": "gale-x", "detail": "sha"}).encode()
    status, _ = post(server + "/phone-home", body)
    assert status == 200
    assert app.state.armed_macs() == {PUCK12_ETH0}


def test_phone_home_unknown_mac_returns_200(server, app):
    # Unknown MAC is server-side bookkeeping, not an installer error — the
    # installer treats non-200 as delivery failure and would stay up.
    body = json.dumps({"serial": "s", "mac": "de:ad:be:ef:00:01",
                       "result": "success", "image_id": "x",
                       "detail": "d"}).encode()
    status, resp = post(server + "/phone-home", body)
    assert status == 200
    assert json.loads(resp)["known"] is False


def test_phone_home_malformed_json_400(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        post(server + "/phone-home", b"{nope")
    assert e.value.code == 400


def test_phone_home_missing_fields_400(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        post(server + "/phone-home", json.dumps({"mac": "x"}).encode())
    assert e.value.code == 400


def test_phone_home_bad_result_400(server):
    body = json.dumps({"serial": "s", "mac": PUCK12_ETH0,
                       "result": "exploded", "image_id": "x",
                       "detail": "d"}).encode()
    with pytest.raises(urllib.error.HTTPError) as e:
        post(server + "/phone-home", body)
    assert e.value.code == 400


def test_unknown_path_404(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server + "/nope")
    assert e.value.code == 404


def test_phone_home_chunked_body(server, app):
    # uclient-fetch (the installer's HTTP client) POSTs without
    # Content-Length using chunked transfer-encoding — verified live on
    # puck12 2026-07-12 (curl 200 vs uclient-fetch 400 differential).
    import http.client
    host, port = server.replace("http://", "").split(":")
    conn = http.client.HTTPConnection(host, int(port))
    body = json.dumps({
        "serial": "s", "mac": PUCK12_ETH0, "result": "failed",
        "image_id": "x", "detail": "chunked probe",
    }).encode()
    conn.putrequest("POST", "/phone-home")
    conn.putheader("Transfer-Encoding", "chunked")
    conn.endheaders()
    conn.send(b"%x\r\n%s\r\n0\r\n\r\n" % (len(body), body))
    resp = conn.getresponse()
    assert resp.status == 200
    assert app.state.puck_state(PUCK12_ETH0)["last_phone_home"][
        "detail"] == "chunked probe"


def test_status_flags_unknown_state_macs(server, app):
    app.state.record_phone_home("de:ad:be:ef:00:01", result="success",
                                image_id="x", serial="s", detail="d")
    _, body = get(server + "/status")
    assert "de:ad:be:ef:00:01" in json.loads(body)["unknown"]
