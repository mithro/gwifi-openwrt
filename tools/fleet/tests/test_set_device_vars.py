# SPDX-License-Identifier: Apache-2.0
"""Tests for set_device_vars pure helpers (no ssh)."""
import json

import pytest

from set_device_vars import build_django_script, redact, validate_logins


LOGINS = {"puck06": {"username": "wifi-puck06", "password": "s3cret1"},
          "puck12": {"username": "wifi-puck12", "password": "s3cret2"}}


def test_validate_logins_passes():
    validate_logins(LOGINS)


@pytest.mark.parametrize("bad", [
    {},                                                      # empty
    {"puck06": {"username": "wifi-puck06"}},                 # missing password
    {"puck06": {"username": "tas-puck06", "password": "x"}}, # wrong prefix
    {"puck06": {"username": "wifi-puck06", "password": ""}}, # empty password
])
def test_validate_logins_fails_loud(bad):
    with pytest.raises(ValueError):
        validate_logins(bad)


def test_django_script_embeds_logins_and_updates_context():
    s = build_django_script(LOGINS)
    blob = json.dumps(LOGINS)
    assert blob in s                        # embedded (stdin transit only)
    assert "Config" in s and "context" in s
    assert "full_clean" in s
    # password VALUES appear only inside the embedded blob, never elsewhere
    rest = s.replace(blob, "")
    assert "s3cret1" not in rest and "s3cret2" not in rest


def test_redact_removes_every_password():
    out = "set puck06 s3cret1 ok; s3cret2 too"
    assert "s3cret" not in redact(out, LOGINS)
