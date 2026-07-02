#!/usr/bin/env python3
"""Park the gale AP through the shared, checked ec_park() in raiden.py.

This is the ONE approved way to park from an orchestrator: it queries the
EC's state first, checks the LOCKED state before attempting the set (a set
while locked is a silent no-op), requires the "OK" ack, and confirms the
parked state -- unlike a blind `ec_console.py "gale power off"`.

Exit 0 = AP confirmed parked; non-zero (RaidenError) = not parked, fail loud.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from raiden import ec_park  # noqa: E402

ec_park()
print("AP parked (state-confirmed, locked-state checked)")
