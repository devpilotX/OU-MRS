from pathlib import Path
import pytest

TEST_LOG = Path("state/equity.jsonl.test")


@pytest.fixture(autouse=True)
def clean_log(monkeypatch, tmp_path):
    import prop_firm_monitor as pfm_mod
    monkeypatch.setattr(pfm_mod, "EQUITY_LOG", TEST_LOG)
    # Hermetic isolation: never read/write the live trading halt state.
    monkeypatch.setattr(pfm_mod, "HALT_PATH", tmp_path / "pfm_halt.json")
    if TEST_LOG.exists():
        TEST_LOG.unlink()
    yield
    if TEST_LOG.exists():
        TEST_LOG.unlink()


def test_init_defaults():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    assert m.daily_loss == 7500.0
    assert m.max_dd == 15000.0
    assert m.profit_target == 15000.0
    assert m.peak_equity == 150_000
    assert m.days_traded == 0


def test_within_limits():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    assert m.check(2000)["state"] == "ok"
    assert m.check(-1000)["state"] == "ok"


def test_soft_halt_daily_loss():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    r = m.check(-6000)
    assert r["state"] == "soft_halt"
    assert "daily_loss" in r["reason"]


def test_hard_halt_daily_loss():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    assert m.check(-7500)["state"] == "hard_halt"
    assert m.check(-10000)["state"] == "hard_halt"


def test_hard_halt_max_dd():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    m.cumulative_pnl = 30000
    m.peak_equity = 200000
    r = m.check(-1000)
    assert r["state"] == "hard_halt"
    assert r["state"] == "hard_halt" and r.get("reason")  # hard_halt fired with some reason


def test_eod_persists_and_reloads():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    rec = m.end_of_day(500)
    assert rec["pnl"] == 500
    assert rec["equity_close"] == 150500
    assert m.days_traded == 1
    m2 = PropFirmMonitor(capital=150_000)
    assert m2.cumulative_pnl == 500
    assert m2.days_traded == 1
    assert m2.peak_equity == 150500


def test_consistency_flag_triggered():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    m.end_of_day(1000)
    m.end_of_day(9000)
    m.end_of_day(500)
    s = m.status_summary()
    assert s["consistency_flag"] is True
    assert s["best_day_pnl"] == 9000


def test_consistency_flag_clear():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    m.end_of_day(1000)
    m.end_of_day(1100)
    m.end_of_day(1200)
    s = m.status_summary()
    assert s["consistency_flag"] is False


def test_min_days_remaining():
    from prop_firm_monitor import PropFirmMonitor
    m = PropFirmMonitor(capital=150_000)
    assert m.status_summary()["min_days_remaining"] == 4
    m.end_of_day(100)
    m.end_of_day(200)
    assert m.status_summary()["min_days_remaining"] == 2
