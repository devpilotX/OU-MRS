"""Phase 8g.4.a: tests for size_lots pure function (post-refactor)."""
from ou_mrs import size_lots


def test_size_lots_basic():
    # atr=30, lot_size=30, max_lots=2, capital=150_000
    # stop=45, budget=1875, raw=1875/(45*30)=1.388 -> int=1, capped [1, 2] -> 1
    assert size_lots(30, lot_size=30, max_lots=2, capital=150_000) == 1


def test_size_lots_caps_at_max_lots():
    assert size_lots(20, lot_size=15, max_lots=3, capital=10_000_000) == 3


def test_size_lots_floor_at_1():
    assert size_lots(100, lot_size=30, max_lots=2, capital=1000) == 1


def test_size_lots_default_capital_uses_module():
    # Pass module CAPITAL explicitly so both calls use identical capital
    # (avoids fragility from .env-loaded CAPITAL differing from 150_000)
    import ou_mrs
    a = size_lots(30, lot_size=30, max_lots=2, capital=ou_mrs.CAPITAL)
    b = size_lots(30, lot_size=30, max_lots=2)
    assert a == b
