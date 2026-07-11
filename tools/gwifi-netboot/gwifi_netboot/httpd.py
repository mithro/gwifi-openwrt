# SPDX-License-Identifier: Apache-2.0
"""HTTP API: GET /manifest, GET /status, POST /phone-home.

Wire-compat notes (the installer relies on these):
- /phone-home bodies are parsed as JSON regardless of Content-Type —
  uclient-fetch --post-data sends application/x-www-form-urlencoded.
- 200 for every *recorded* result, including unknown MACs (server-side
  bookkeeping, not an installer error). The installer treats non-200 as
  delivery failure and stays up rather than rebooting.
- 400 only for undecodable bodies / missing or invalid fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from gwifi_netboot.dnsmasqctl import install_fragment
from gwifi_netboot.identity import IdentityError, Puck, load_identity
from gwifi_netboot.render import render_dnsmasq
from gwifi_netboot.state import StateStore

VALID_RESULTS = frozenset({"success", "already-current", "failed"})
REQUIRED_FIELDS = ("serial", "mac", "result", "image_id", "detail")

Installer = Callable[[str, Path], None]


@dataclass
class App:
    """Shared service context: paths, state, and the dnsmasq installer."""

    identity_path: Path
    state: StateStore
    fragment_path: Path
    manifest_path: Path
    installer: Installer = field(default=install_fragment)

    def identity(self) -> list[Puck]:
        try:
            return load_identity(self.identity_path)
        except IdentityError:
            # No identity deployed yet — serve empty; status shows nothing.
            return []

    def regenerate(self) -> None:
        """Render the fragment from identity + state and activate it."""
        content = render_dnsmasq(self.identity(), self.state.armed_macs())
        self.installer(content, self.fragment_path)

    def status(self) -> dict:
        pucks = []
        known_macs: set[str] = set()
        armed = self.state.armed_macs()
        for p in self.identity():
            known_macs.update((p.eth0, p.eth1))
            st = self.state.puck_state(p.eth0)
            pucks.append({
                "name": p.name,
                "number": p.number,
                "serial": p.serial,
                "eth0": p.eth0,
                "eth1": p.eth1,
                "ip": p.ip,
                "armed": p.eth0 in armed or p.eth1 in armed,
                "installed_image_id": st.get("installed_image_id"),
                "last_phone_home": st.get("last_phone_home"),
            })
        unknown = {mac: st for mac, st in self.state.all_states().items()
                   if mac not in known_macs and st}
        return {"pucks": pucks, "unknown": unknown}

    def phone_home(self, doc: dict) -> dict:
        for f in REQUIRED_FIELDS:
            if f not in doc or not isinstance(doc[f], str):
                raise ValueError(f"missing or non-string field {f!r}")
        if doc["result"] not in VALID_RESULTS:
            raise ValueError(f"invalid result {doc['result']!r}")

        mac = doc["mac"].lower()
        known = any(mac in (p.eth0, p.eth1) for p in self.identity())
        self.state.record_phone_home(
            mac, result=doc["result"], image_id=doc["image_id"],
            serial=doc["serial"], detail=doc["detail"])
        self.regenerate()
        return {"ok": True, "known": known}


def make_server(app: App, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # journald gets stdout
            print(f"{self.client_address[0]} {fmt % args}", flush=True)

        def _send(self, code: int, body: bytes,
                  content_type: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, code: int, doc: dict) -> None:
            self._send(code, (json.dumps(doc) + "\n").encode())

        def do_GET(self):
            if self.path == "/manifest":
                try:
                    body = app.manifest_path.read_bytes()
                except OSError:
                    self._send_json(404, {"error": "no manifest published"})
                    return
                self._send(200, body)
            elif self.path == "/status":
                self._send_json(200, app.status())
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/phone-home":
                self._send_json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                doc = json.loads(raw)
                if not isinstance(doc, dict):
                    raise ValueError("body must be a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                self._send_json(400, {"error": f"bad JSON body: {e}"})
                return
            try:
                resp = app.phone_home(doc)
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
            self._send_json(200, resp)

    return ThreadingHTTPServer((host, port), Handler)
