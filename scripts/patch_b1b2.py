#!/usr/bin/env python3
"""Phase 9.8g.12 audit fix B1+B2 — atomic in-place patch.

Run from repo root:
    python scripts/patch_b1b2.py

Edits applied atomically (all-or-nothing — asserts abort BEFORE writing
if any anchor fails to match uniquely):

  1. ou_mrs.py
     - B1a  delete `_LOT_SIZE_AL = {...}` dict line
     - B1b  rewrite `max_lots_for_capital()` reader to use INSTRUMENT_CFG
             (Sacred Rule #33: single source of truth for lot sizes)
     - B2a  replace `size_lots()` body — tier-aware risk-based sizing
             (risk_per_trade_pct from _POLICY, stop = runner.atr_mult * ATR)
     - B2b  update the L706 call site to new signature

  2. tests/test_size_lots.py
     - overwrite with 7 runner-signature tests (SimpleNamespace fakes)

Note: backtest.py has its OWN size_lots() — unaffected by this patch.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def patch_ou_mrs():
    ou = REPO / "ou_mrs.py"
    if not ou.exists():
        sys.exit("ERROR: ou_mrs.py not found; run from repo root")

    src = ou.read_text()
    orig_len = len(src)

    # ---- B1a: delete _LOT_SIZE_AL definition line entirely ----
    m = re.search(r'^_LOT_SIZE_AL\s*=\s*\{[^}]*\}\s*\n', src, re.MULTILINE)
    assert m, "B1a: _LOT_SIZE_AL def line not found"
    src = src[:m.start()] + src[m.end():]

    # ---- B1b: rewrite reader inside max_lots_for_capital() ----
    b1b_old = '    lot_size_sym   = _LOT_SIZE_AL[instrument]'
    b1b_new = (
        '    # Phase 9.8g.12 (audit B1): canonical lot size from INSTRUMENT_CFG (Sacred Rule #33).\n'
        '    lot_size_sym   = INSTRUMENT_CFG[instrument]["lot_size"] if instrument in INSTRUMENT_CFG else 10  # SENSEX fallback'
    )
    n = src.count(b1b_old)
    assert n == 1, f"B1b: expected 1 reader line, found {n}"
    src = src.replace(b1b_old, b1b_new)

    # ---- B2a: replace size_lots() body ----
    b2a_old = (
        'def size_lots(atr: float, lot_size: int, max_lots: int = 1, capital: int = None) -> int:\n'
        '    """Phase 8g.4.a: pure. Pass per-symbol lot_size/max_lots; capital defaults to module CAPITAL."""\n'
        '    if capital is None:\n'
        '        capital = CAPITAL\n'
        '    stop = max(atr * 1.5, 20)\n'
        '    budget = 0.25 * 0.05 * capital  # Phase 8b.5: Kelly halved from 0.10\n'
        '    return max(1, min(max_lots, int(budget / (stop * lot_size))))'
    )
    b2a_new = (
        'def size_lots(runner, atr: float) -> int:\n'
        '    """Phase 9.8g.12 (audit B2): tier-aware risk-based sizing.\n'
        '\n'
        '    risk_per_trade_pct from _POLICY (HEDGE_FUND=0.5%; was hardcoded 1.25%).\n'
        '    Stop distance from runner.atr_mult x ATR (was hardcoded 1.5x).\n'
        '    """\n'
        '    atr_mult = float(getattr(runner, "atr_mult", 1.5))\n'
        '    stop_rs  = max(atr * atr_mult, 20.0)\n'
        '    risk_pct = float(_POLICY.get("risk_per_trade_pct", 0.005))\n'
        '    capital  = getattr(runner, "capital", CAPITAL)\n'
        '    budget   = risk_pct * capital\n'
        '    raw      = budget / (stop_rs * runner.lot_size)\n'
        '    return max(1, min(runner.max_lots, int(raw)))'
    )
    n = src.count(b2a_old)
    assert n == 1, f"B2a: expected 1 size_lots body, found {n}"
    src = src.replace(b2a_old, b2a_new)

    # ---- B2b: L706 call site ----
    b2b_old = 'qty_lots = size_lots(sig.atr, lot_size=runner.lot_size, max_lots=runner.max_lots, capital=CAPITAL)'
    b2b_new = 'qty_lots = size_lots(runner, sig.atr)  # Phase 9.8g.12 (audit B2)'
    n = src.count(b2b_old)
    assert n == 1, f"B2b: expected 1 call site, found {n}"
    src = src.replace(b2b_old, b2b_new)

    ou.write_text(src)
    print(f"OK ou_mrs.py:           {orig_len:>6d} -> {len(src):>6d} bytes ({len(src)-orig_len:+d})")


NEW_TEST_FILE = '''"""Phase 9.8g.12 (audit B2): tests for size_lots with runner-based signature."""
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
'''


def overwrite_tests():
    tf = REPO / "tests" / "test_size_lots.py"
    old_len = len(tf.read_text()) if tf.exists() else 0
    tf.write_text(NEW_TEST_FILE)
    print(f"OK tests/test_size_lots.py: {old_len:>6d} -> {len(NEW_TEST_FILE):>6d} bytes")


if __name__ == "__main__":
    patch_ou_mrs()
    overwrite_tests()
    print("\nNext: python -m pytest tests/test_size_lots.py -v")
