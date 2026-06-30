# galeflash — Gale Fleet Firmware Flash Toolkit

Python tooling for flashing and validating firmware across a fleet of Gale (IPQ4019) devices.

## Setup

```
cd tools/fleet
uv run pytest
```

## Structure

- `galeflash/` — Package source
  - `const.py` — Verified constants: paths, FMAP regions, allowed-change sets
- `tests/` — pytest test suite
  - `conftest.py` — Fixtures (skip gracefully when binary fixtures are absent)
  - `test_smoke.py` — Basic import and constant sanity checks

## Notes

- Run tests with `uv run pytest -q` from `tools/fleet/`.
- Binary fixtures (`.bin` files) live under `UMBRELLA` (defined in `galeflash/const.py`)
  and are optional; tests that need them skip automatically when absent.
