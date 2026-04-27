"""Phase 8g.5: tests for correlation cap + aggregate trade cap."""
import os
from ou_mrs import _can_enter_new_position


class FakeRunner:
    def __init__(self, position=None, trades_today=0):
        self.position = position
        self.trades_today = trades_today


def test_corr_cap_allows_when_under_limit():
    """1 of 3 in trade, max=2 -> NF can enter."""
    runners = {
        "BNF": FakeRunner(position={"side": "BUY", "qty": 1}),
        "NF": FakeRunner(),
        "FNF": FakeRunner(),
    }
    can, reason = _can_enter_new_position(runners, runners["NF"], max_concurrent=2, max_agg_trades=8)
    assert can is True
    assert reason == "ok"


def test_corr_cap_blocks_at_limit():
    """2 of 3 in trade, max=2 -> FNF blocked."""
    runners = {
        "BNF": FakeRunner(position={"side": "BUY", "qty": 1}),
        "NF": FakeRunner(position={"side": "SELL", "qty": 1}),
        "FNF": FakeRunner(),
    }
    can, reason = _can_enter_new_position(runners, runners["FNF"], max_concurrent=2, max_agg_trades=8)
    assert can is False
    assert "corr_cap" in reason
    assert "2/2" in reason


def test_agg_trades_cap_blocks():
    """4 + 4 = 8 trades, max_agg=8 -> FNF blocked."""
    runners = {
        "BNF": FakeRunner(trades_today=4),
        "NF": FakeRunner(trades_today=4),
        "FNF": FakeRunner(trades_today=0),
    }
    can, reason = _can_enter_new_position(runners, runners["FNF"], max_concurrent=2, max_agg_trades=8)
    assert can is False
    assert "max_trades_agg" in reason
    assert "8/8" in reason


def test_max_concurrent_positions_module_const_default():
    """Module exposes MAX_CONCURRENT_POSITIONS, default 2."""
    import ou_mrs
    assert hasattr(ou_mrs, "MAX_CONCURRENT_POSITIONS")
    assert isinstance(ou_mrs.MAX_CONCURRENT_POSITIONS, int)
    assert ou_mrs.MAX_CONCURRENT_POSITIONS >= 1
    assert ou_mrs.MAX_CONCURRENT_POSITIONS <= 3
