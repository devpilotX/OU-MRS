"""Phase 9.8h.I autouse fixture: redirect live_hook state paths to tmp_path.

Without this, any test that imports live_hook and calls tick / tick_symbol writes
to the REAL state/live*.json and APPENDS to state/heartbeat.jsonl, polluting the
running dashboard's data. _HEARTBEAT_PATH is computed at module load time, so a
per-test monkeypatch of _STATE alone is not enough.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_live_hook_state(tmp_path, monkeypatch):
    try:
        import live_hook
    except Exception:
        return
    state_dir = tmp_path / "_state_isolated"
    state_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(live_hook, "_STATE", state_dir / "live.json", raising=False)
    monkeypatch.setattr(live_hook, "_HEARTBEAT_PATH", state_dir / "heartbeat.jsonl", raising=False)
    # Reset the throttle dict so each test gets a clean heartbeat-emit cadence.
    monkeypatch.setattr(live_hook, "_LAST_HEARTBEAT_TS", {}, raising=False)
    yield
