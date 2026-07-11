# SPDX-License-Identifier: Apache-2.0
"""Runtime state store: armed flags + phone-home records per MAC.

State transitions (spec section 5.4):
- phone-home success / already-current  -> disarm + record installed image
- phone-home failed                     -> record only, stays armed
- unknown MACs are recorded too (flagged by `status`, never a crash)

Writes are atomic (tmp + rename) so a crash never leaves a partial file.
Keyed by eth0 (label) MAC, lowercase.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HISTORY_LIMIT = 20
DISARMING_RESULTS = frozenset({"success", "already-current"})


class StateStore:
    """Persistent per-MAC runtime state backed by a JSON file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict = {"version": 1, "pucks": {}}
        if self.path.exists():
            self._data = json.loads(self.path.read_text())

    # -- queries ----------------------------------------------------------

    def armed_macs(self) -> set[str]:
        return {mac for mac, st in self._data["pucks"].items()
                if st.get("armed")}

    def puck_state(self, mac: str) -> dict:
        return self._data["pucks"].get(mac.lower(), {})

    def all_states(self) -> dict[str, dict]:
        return dict(self._data["pucks"])

    # -- mutations (each persists atomically) ------------------------------

    def arm(self, macs: list[str]) -> None:
        for mac in macs:
            self._entry(mac)["armed"] = True
        self._save()

    def disarm(self, macs: list[str]) -> None:
        for mac in macs:
            self._entry(mac)["armed"] = False
        self._save()

    def record_phone_home(self, mac: str, *, result: str, image_id: str,
                          serial: str, detail: str) -> None:
        entry = self._entry(mac)
        event = {
            "time": datetime.now(timezone.utc).isoformat(),
            "result": result,
            "image_id": image_id,
            "serial": serial,
            "detail": detail,
        }
        entry["last_phone_home"] = event
        entry.setdefault("history", []).append(event)
        entry["history"] = entry["history"][-HISTORY_LIMIT:]
        if result in DISARMING_RESULTS:
            entry["armed"] = False
            entry["installed_image_id"] = image_id
        self._save()

    # -- internals ---------------------------------------------------------

    def _entry(self, mac: str) -> dict:
        return self._data["pucks"].setdefault(mac.lower(), {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent,
                                   prefix=f".{self.path.name}.")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(self._data, fh, indent=2)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise
