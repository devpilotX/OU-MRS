"""Phase 9.8h.C.2: per-symbol + size-aware + vol-aware slippage tests.

The C.2 cost-model overhaul introduces estimate_slippage_ticks(). These tests
lock the behavioral contract:
  * v2-off (default) returns the legacy flat BT_SLIPPAGE_TICKS.
  * v2-on returns per-symbol base spreads, with size penalty and vol surcharge.
  * Symbol aliases (BNF/NF/MCN) resolve to canonical names.
  * Backtest module imports estimate_slippage_ticks and uses _slip_ticks_c2.
"""
import importlib
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cost_model  # noqa: E402


def _env_v2_on(monkeypatch, **extras):
    monkeypatch.setenv("OU_COST_MODEL_V2", "on")
    for k, v in extras.items():
        monkeypatch.setenv(k, v)


def test_1_default_v2_off_returns_legacy_flat(monkeypatch):
    """Default behavior must be byte-exact with the legacy flat 2-tick model."""
    monkeypatch.delenv("OU_COST_MODEL_V2", raising=False)
    monkeypatch.delenv("BT_SLIPPAGE_TICKS", raising=False)
    for sym in ("BANKNIFTY", "NIFTY", "MIDCPNIFTY", "BNF", "NF", "MCN", ""):
        for q in (1, 2, 3):
            assert cost_model.estimate_slippage_ticks(sym, q, rv20=0.020) == 2.0


def test_2_v2_off_honors_bt_slippage_ticks(monkeypatch):
    """Legacy override path: BT_SLIPPAGE_TICKS still controls v2-off ticks."""
    monkeypatch.delenv("OU_COST_MODEL_V2", raising=False)
    monkeypatch.setenv("BT_SLIPPAGE_TICKS", "7")
    assert cost_model.estimate_slippage_ticks("BANKNIFTY", 1) == 7.0
    assert cost_model.estimate_slippage_ticks("NIFTY", 5, rv20=0.030) == 7.0


def test_3_v2_on_per_symbol_base_ticks(monkeypatch):
    """Per-symbol base ticks must match the documented profile."""
    _env_v2_on(monkeypatch)
    assert cost_model.estimate_slippage_ticks("BANKNIFTY", 1, rv20=0.005) == 2.0
    assert cost_model.estimate_slippage_ticks("NIFTY", 1, rv20=0.005) == 3.0
    assert cost_model.estimate_slippage_ticks("MIDCPNIFTY", 1, rv20=0.005) == 2.0


def test_4_v2_on_symbol_aliases_resolve(monkeypatch):
    """Short aliases (BNF / NF / MCN) resolve to canonical profiles."""
    _env_v2_on(monkeypatch)
    assert cost_model.estimate_slippage_ticks("BNF", 1, rv20=0.005) == 2.0
    assert cost_model.estimate_slippage_ticks("NF", 1, rv20=0.005) == 3.0
    assert cost_model.estimate_slippage_ticks("MCN", 1, rv20=0.005) == 2.0


def test_5_v2_on_size_penalty_scales_with_lots(monkeypatch):
    """Each extra lot adds 0.5 ticks (default per_lot_extra)."""
    _env_v2_on(monkeypatch)
    assert cost_model.estimate_slippage_ticks("BNF", 1, rv20=0.005) == 2.0
    assert cost_model.estimate_slippage_ticks("BNF", 2, rv20=0.005) == 2.5
    assert cost_model.estimate_slippage_ticks("BNF", 3, rv20=0.005) == 3.0
    # NF: starts at 3, adds 0.5 per extra lot.
    assert cost_model.estimate_slippage_ticks("NF", 3, rv20=0.005) == 4.0


def test_6_v2_on_high_vol_surcharge(monkeypatch):
    """rv20 above the threshold adds high_vol_extra ticks."""
    _env_v2_on(monkeypatch)
    # rv20 = 0.015 > default threshold 0.012 -> +1 tick.
    assert cost_model.estimate_slippage_ticks("BNF", 1, rv20=0.015) == 3.0
    # rv20 = 0.011 <= threshold -> no surcharge.
    assert cost_model.estimate_slippage_ticks("BNF", 1, rv20=0.011) == 2.0
    # None rv20 -> no surcharge applied.
    assert cost_model.estimate_slippage_ticks("BNF", 1, rv20=None) == 2.0


def test_7_v2_on_combined_size_and_vol(monkeypatch):
    """MCN, 3 lots, high vol: base 2 + per_lot (0.5 * 2) + high_vol 1 = 4 ticks."""
    _env_v2_on(monkeypatch)
    assert cost_model.estimate_slippage_ticks("MCN", 3, rv20=0.020) == 4.0
    # Same composition for canonical name.
    assert cost_model.estimate_slippage_ticks("MIDCPNIFTY", 3, rv20=0.020) == 4.0


def test_8_v2_on_unknown_symbol_uses_default_profile(monkeypatch):
    """Unknown symbols fall through to DEFAULT_SLIPPAGE_PROFILE."""
    _env_v2_on(monkeypatch)
    assert cost_model.estimate_slippage_ticks("FINNIFTY", 1, rv20=0.005) == 2.0
    assert cost_model.estimate_slippage_ticks("", 1, rv20=0.005) == 2.0


def test_9_v2_on_threshold_is_env_configurable(monkeypatch):
    """OU_HIGH_VOL_THRESHOLD shifts the surcharge boundary."""
    _env_v2_on(monkeypatch, OU_HIGH_VOL_THRESHOLD="0.005")
    # rv20 = 0.006 > 0.005 -> surcharge fires now.
    assert cost_model.estimate_slippage_ticks("BNF", 1, rv20=0.006) == 3.0
    # rv20 = 0.004 <= 0.005 -> no surcharge.
    assert cost_model.estimate_slippage_ticks("BNF", 1, rv20=0.004) == 2.0


def test_10_compute_rt_cost_still_works_after_extension():
    """Pre-existing fee model must remain functional after C.2 extension."""
    cost = cost_model.compute_rt_cost(
        entry_price=52000.0,
        exit_price=52100.0,
        lot_size=15,
        qty_lots=1,
        side="BUY",
    )
    assert cost > 0.0
    assert isinstance(cost, float)


def test_11_backtest_imports_estimate_slippage_ticks():
    """Regression: backtest.py must keep wiring _slip_ticks_c2 at fill sites."""
    bt_path = ROOT / "backtest.py"
    src = bt_path.read_text()
    assert "estimate_slippage_ticks" in src, "backtest must import estimate_slippage_ticks"
    assert src.count("_slip_ticks_c2 =") == 2, (
        f"expected 2 fill sites (_close + entry); got {src.count('_slip_ticks_c2 =')}"
    )
    # Legacy SLIPPAGE_TICKS constant kept for v2-off compatibility.
    assert "SLIPPAGE_TICKS = int(" in src, "legacy SLIPPAGE_TICKS constant should remain for v2-off path"


def test_12_v2_returns_non_negative(monkeypatch):
    """Slippage in ticks must never go negative regardless of inputs."""
    _env_v2_on(monkeypatch)
    for q in (-3, 0, 1, 10):
        for rv in (None, -0.01, 0.0, 0.005, 0.05):
            assert cost_model.estimate_slippage_ticks("BNF", q, rv20=rv) >= 0.0
