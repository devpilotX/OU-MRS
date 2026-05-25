"""Phase 9.8g.12 (audit B2): tests for size_lots with runner-based signature."""
from types import SimpleNamespace
from ou_mrs import size_lots, _POLICY, CAPITAL


def _mk_runner(lot_size, max_lots, capital, atr_mult=1.5):
    return SimpleNamespace(
        lot_size=lot_size,
        max_lots=max_lots,
        capital=capital,
        atr_mult=atr_mult,
    )


def test_size_lots_basic():
    # HEDGE_FUND risk 0.5% of 150k = 750. atr=30, mult=1.5 -> stop=45, lot=30.
    # raw = 750/(45*30) = 0.555 -> int=0 -> floor to 1.
    runner = _mk_runner(lot_size=30, max_lots=2, capital=150_000)
    assert size_lots(runner, 30) == 1


def test_size_lots_caps_at_max_lots():
    # Huge capital -> raw above max_lots=3 -> capped at 3.
    runner = _mk_runner(lot_size=15, max_lots=3, capital=10_000_000)
    assert size_lots(runner, 20) == 3


def test_size_lots_floor_at_1():
    # Tiny capital, large stop -> raw=0 -> floor to 1.
    runner = _mk_runner(lot_size=30, max_lots=2, capital=1000)
    assert size_lots(runner, 100) == 1


def test_size_lots_honors_runner_atr_mult():
    # Doubling atr_mult doubles stop distance -> halves (or fewer) lots.
    r1 = _mk_runner(lot_size=30, max_lots=50, capital=3_750_000, atr_mult=1.5)
    r3 = _mk_runner(lot_size=30, max_lots=50, capital=3_750_000, atr_mult=3.0)
    assert size_lots(r3, 30) <= size_lots(r1, 30)


def test_size_lots_scales_with_capital():
    # 10x capital -> more lots (up to max_lots cap).
    r_small = _mk_runner(lot_size=30, max_lots=50, capital=1_000_000)
    r_big   = _mk_runner(lot_size=30, max_lots=50, capital=10_000_000)
    assert size_lots(r_big, 30) > size_lots(r_small, 30)


def test_policy_has_risk_per_trade_pct():
    # Confirms the policy key the implementation depends on.
    assert "risk_per_trade_pct" in _POLICY
    assert 0.001 <= _POLICY["risk_per_trade_pct"] <= 0.02


def test_size_lots_uses_capital_fallback():
    # Runner without .capital attr falls back to module CAPITAL.
    bare = SimpleNamespace(lot_size=30, max_lots=50, atr_mult=1.5)
    n = size_lots(bare, 30)
    assert n >= 1
