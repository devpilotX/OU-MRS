"""Phase 8f.5: signal_publisher tests."""
import json
import pytest

import signal_publisher


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_publish_entry_creates_valid_json(tmp_state):
    signal_publisher.publish_entry(
        side="BUY", qty_lots=2, lot_size=15,
        entry_price=50100.5, entry_time="2026-04-25T10:15:00",
        stop_loss=49850.0, account_id="test_a",
    )
    sp = signal_publisher.signals_path("test_a")
    assert sp.exists()
    data = json.loads(sp.read_text())
    assert data["signal"] == "LONG"
    assert data["qty"] == 30
    assert data["entry_price"] == 50100.5
    assert data["stop_loss"] == 49850.0
    assert data["instrument"] == "BANKNIFTY26MAY26FUT"
    assert data["strategy"] == "OU-MRS"
    assert data["account"] == "test_a"


def test_publish_exit_sets_flat(tmp_state):
    signal_publisher.publish_entry(
        side="SELL", qty_lots=1, lot_size=15,
        entry_price=50000.0, entry_time="2026-04-25T11:00:00",
        stop_loss=50250.0, account_id="test_b",
    )
    signal_publisher.publish_exit(realized_pnl=1234.5, account_id="test_b")
    data = json.loads(signal_publisher.signals_path("test_b").read_text())
    assert data["signal"] == "FLAT"
    assert data["qty"] == 0
    assert data["entry_price"] is None
    assert data["last_realized_pnl"] == 1234.5


def test_heartbeat_updates_pnl_when_active(tmp_state):
    signal_publisher.publish_entry(
        side="BUY", qty_lots=2, lot_size=15,
        entry_price=50000.0, entry_time="2026-04-25T10:30:00",
        stop_loss=49800.0, account_id="test_c",
    )
    signal_publisher.heartbeat(current_pnl=750.25, account_id="test_c")
    data = json.loads(signal_publisher.signals_path("test_c").read_text())
    assert data["signal"] == "LONG"
    assert data["current_pnl"] == 750.25


def test_account_isolation(tmp_state):
    signal_publisher.publish_entry(
        side="BUY", qty_lots=1, lot_size=15,
        entry_price=50000.0, entry_time="2026-04-25T10:30:00",
        stop_loss=49800.0, account_id="acct_one",
    )
    signal_publisher.publish_flat(account_id="acct_two")
    a = json.loads(signal_publisher.signals_path("acct_one").read_text())
    b = json.loads(signal_publisher.signals_path("acct_two").read_text())
    assert a["signal"] == "LONG"
    assert b["signal"] == "FLAT"
    assert a["account"] == "acct_one"
    assert b["account"] == "acct_two"


def test_read_signal_returns_flat_when_missing(tmp_state):
    data = signal_publisher.read_signal(account_id="never_existed")
    assert data["signal"] == "FLAT"
    assert data["strategy"] == "OU-MRS"
