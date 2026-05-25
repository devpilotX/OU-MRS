"""Phase 8g.2.a: tests for OuMrsRunner state container.

Phase 9.8g.9 (25 May 2026 audit Track 1): max_lots tests updated for
9.7AL.1 dual-cap (margin_cap x notional_cap @ 3x leverage). The old
hardcoded 50-lot cap is gone; max_lots is now min(margin_cap, notional_cap).

Also updated test_cfg_accessors: atr_mult assertion lowered from 1.5 to 1.2
(post-9.7AO tight-stops; the runner reads OU_ATR_MULT from the module-level
constant and ignores cfg['atr_mult']).
"""
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
    # Phase 9.7AO tight stops: runner reads OU_ATR_MULT from module-level
    # constant (1.2), not from cfg['atr_mult']. The cfg value is informational.
    assert r.atr_mult == 1.2


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


# ----- Phase 9.8g.9: 9.7AL.1 dual-cap regression suite -----
# max_lots = min(margin_cap, notional_cap @ NOTIONAL_LEVERAGE_MAX = 3.0x).
# BNF approx_spot = 53,500. NF approx_spot = 24,800. Fallback spot = 50,000.

def test_runner_max_lots_bnf_seed_tier():
    """Capital Rs 1.5L = SEED tier; notional cap binds before margin cap."""
    cfg = {"symbol": "BNFFUT", "token": "66068", "lot_size": 30, "margin_per_lot": 75_000, "atr_mult": 1.5, "exchange": "NFO"}
    r = OuMrsRunner("BNF", cfg, capital=150_000)
    # margin_cap = 150,000 // 75,000 = 2
    # notional_cap = floor((150,000 * 3) / (53,500 * 30)) = floor(450,000 / 1,605,000) = 0 -> max(1, 0) = 1
    # max_lots = min(2, 1) = 1
    assert r.max_lots == 1


def test_runner_max_lots_nf_seed_tier():
    cfg = {"symbol": "NFFUT", "token": "66071", "lot_size": 65, "margin_per_lot": 50_000, "atr_mult": 1.5, "exchange": "NFO"}
    r = OuMrsRunner("NF", cfg, capital=150_000)
    # margin_cap = 150,000 // 50,000 = 3
    # notional_cap = floor((150,000 * 3) / (24,800 * 65)) = floor(450,000 / 1,612,000) = 0 -> max(1, 0) = 1
    # max_lots = min(3, 1) = 1
    assert r.max_lots == 1


def test_runner_max_lots_bnf_hedge_fund_tier():
    """Capital Rs 37.5L = HEDGE_FUND tier; matches the live VPS config."""
    cfg = {"symbol": "BNFFUT", "token": "66068", "lot_size": 30, "margin_per_lot": 75_000, "atr_mult": 1.5, "exchange": "NFO"}
    r = OuMrsRunner("BNF", cfg, capital=3_750_000)
    # margin_cap = 3,750,000 // 75,000 = 50
    # notional_cap = floor((3,750,000 * 3) / (53,500 * 30)) = floor(11,250,000 / 1,605,000) = 7
    # max_lots = min(50, 7) = 7
    assert r.max_lots == 7


def test_runner_max_lots_floor_at_1():
    """Tiny capital still leaves max_lots >= 1."""
    cfg = {"margin_per_lot": 75_000}
    r = OuMrsRunner("X", cfg, capital=10_000)
    assert r.max_lots == 1


def test_runner_max_lots_notional_cap_dominant():
    """Phase 9.8g.9: with huge capital but tiny margin_per_lot, notional cap binds."""
    cfg = {"margin_per_lot": 1}
    r = OuMrsRunner("X", cfg, capital=10_000_000_000)
    # margin_cap = 10B; symbol 'X' uses fallback spot=50,000 and default lot_size=15
    # notional_cap = floor((10B * 3) / (50,000 * 15)) = floor(30B / 750,000) = 40,000
    # max_lots = min(10B, 40,000) = 40,000
    assert r.max_lots == 40_000
