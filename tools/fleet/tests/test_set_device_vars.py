# SPDX-License-Identifier: Apache-2.0
"""Tests for set_device_vars pure helpers (no ssh)."""
import ast
import json

import pytest

from set_device_vars import (
    build_django_script,
    partition_puck_names,
    redact,
    scrub_hex,
    validate_logins,
)


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


def test_scrub_hex_redacts_long_hex_but_leaves_short_tokens():
    digest = "a1b2c3" * 10 + "abcd"  # 64-char sha256-shaped hex digest
    assert len(digest) == 64
    text = f"connect failed: password=hash:{digest} rc=1"
    scrubbed = scrub_hex(text)
    assert digest not in scrubbed
    assert "<REDACTED-HEX>" in scrubbed
    # ordinary short hex-ish tokens must survive untouched
    assert scrub_hex("commit abc123 failed") == "commit abc123 failed"


def test_partition_puck_names():
    pucks, skipped = partition_puck_names(
        ["puck06", "puck12", "tenwrt", "puck1", "ansells-aps-mesh"])
    assert pucks == ["puck06", "puck12"]
    assert skipped == ["ansells-aps-mesh", "puck1", "tenwrt"]


def test_build_django_script_handles_nasty_password_injection_safe():
    # quotes, a backslash, and a newline -- exactly the characters that would
    # break a naive (non-repr()) string-embedding scheme.
    tricky = {"puck06": {"username": "wifi-puck06", "password": "s3'cr\"et\\\n x"}}
    script = build_django_script(tricky)
    ast.parse(script)  # must not raise SyntaxError
