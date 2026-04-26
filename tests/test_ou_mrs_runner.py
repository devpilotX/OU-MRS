"""Phase 8g.2.a: tests for OuMrsRunner state container."""
from ou_mrs_runner import OuMrsRunner


BNF_CFG = {"symbol": "BANKNIFTY26MAY26FUT", "token": "66068", "lot_size": 30, "margin_per_lot": 75000, "atr_mult": 1.5, "exchange": "NFO"}
NF_CFG  = {"symbol": "NIFTY26MAY26FUT",     "token": "66071", "lot_size": 65, "margin_per_lot": 50000, "atr_mult": 1.5, "exchange": "NFO"}


def test_init_state_defaults():
    r = OuMrsRunner("BNF", BNF_CFG)
    assert r.symbol == "BNF"
    assert r.position is None
    assert r.trades_today == 0
    assert r.pnl_today == 0.0
    assert r.kill is False
    assert r.soft_halt is False
    assert r.reasons_log == []


def test_cfg_accessors():
    r = OuMrsRunner("BNF", BNF_CFG)
    assert r.lot_size == 30
    assert r.token == "66068"
    assert r.exchange == "NFO"
    assert r.symbol_full == "BANKNIFTY26MAY26FUT"
    assert r.margin_per_lot == 75000
    assert r.atr_mult == 1.5


def test_lot_size_default_when_cfg_missing_keys():
    r = OuMrsRunner("XYZ", {})
    assert r.lot_size == 15
    assert r.exchange == "NFO"
    assert r.token is None


def test_none_cfg_uses_all_defaults():
    r = OuMrsRunner("BNF", None)
    assert r.lot_size == 15
    assert r.cfg == {}


def test_status_no_position():
    r = OuMrsRunner("NF", NF_CFG)
    s = r.status()
    assert s["symbol"] == "NF"
    assert s["in_trade"] is False
    assert s["side"] is None
    assert s["qty_lots"] == 0
    assert s["entry_px"] is None
    assert s["pnl_today"] == 0.0


def test_status_with_position():
    r = OuMrsRunner("BNF", BNF_CFG)
    r.position = {"side": "BUY", "qty": 2, "entry_px": 51234.5, "bars_held": 3, "half_life": 8}
    r.trades_today = 1
    r.pnl_today = 423.75
    s = r.status()
    assert s["in_trade"] is True
    assert s["side"] == "BUY"
    assert s["qty_lots"] == 2
    assert s["entry_px"] == 51234.5
    assert s["trades_today"] == 1
    assert s["pnl_today"] == 423.75


def test_reset_for_new_day_clears_all_state():
    r = OuMrsRunner("BNF", BNF_CFG)
    r.position = {"side": "SELL", "qty": 1, "entry_px": 50000}
    r.trades_today = 5
    r.pnl_today = -1234.0
    r.kill = True
    r.soft_halt = True
    r.reasons_log = ["STOP", "STOP", "STOP"]
    r.reset_for_new_day()
    assert r.position is None
    assert r.trades_today == 0
    assert r.pnl_today == 0.0
    assert r.kill is False
    assert r.soft_halt is False
    assert r.reasons_log == []
