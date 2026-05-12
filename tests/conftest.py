"""Shared pytest fixtures.

Autouse fixture ensures PFM state is clean before and after every test, so
test runs cannot pollute production state/pfm_halt.json, which would cause
the live bot to start halted on the next timer-triggered run.
"""
import pathlib
import pytest

_PFM_HALT_PATH = pathlib.Path("state/pfm_halt.json")


@pytest.fixture(autouse=True)
def _cleanup_pfm_halt_state():
    """Remove state/pfm_halt.json before and after each test.

    This prevents PFM tests (which intentionally trigger halt states)
    from leaking into the production state file. If that file exists
    when the live bot starts, the bot will auto-load it and refuse
    to trade.
    """
    if _PFM_HALT_PATH.exists():
        _PFM_HALT_PATH.unlink()
    yield
    if _PFM_HALT_PATH.exists():
        _PFM_HALT_PATH.unlink()
