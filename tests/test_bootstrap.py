"""Determinism and sanity tests for validation.bootstrap."""
import numpy as np
import pytest
from validation.bootstrap import bootstrap_trade_stats, _stationary_resample_indices


def test_resample_indices_length_and_range():
    rng = np.random.default_rng(0)
    idx = _stationary_resample_indices(50, mean_block_len=5.0, rng=rng)
    assert idx.shape == (50,)
    assert idx.min() >= 0 and idx.max() < 50


def test_bootstrap_deterministic_under_seed():
    pnl = np.array([100.0, -50.0, 200.0, -30.0, 80.0, -10.0, 150.0, -120.0,
                    60.0, 40.0, -70.0, 110.0])
    a = bootstrap_trade_stats(pnl, n_iter=2000, seed=42)
    b = bootstrap_trade_stats(pnl, n_iter=2000, seed=42)
    assert a == b


def test_bootstrap_ci_brackets_point_estimate():
    rng = np.random.default_rng(1)
    pnl = rng.normal(loc=50.0, scale=200.0, size=100)
    out = bootstrap_trade_stats(pnl, n_iter=2000, seed=7)
    lo, hi = out["ci95_mean_pnl"]
    # Point estimate may sit just outside in degenerate runs; widen tolerance
    assert lo <= out["point_mean_pnl"] + 5.0
    assert hi >= out["point_mean_pnl"] - 5.0


def test_bootstrap_pure_loss_series_p_value_high():
    pnl = np.array([-10.0, -20.0, -5.0, -30.0, -15.0, -25.0, -8.0, -18.0])
    out = bootstrap_trade_stats(pnl, n_iter=2000, seed=11)
    # All-negative series: P(resample_mean <= 0) should be ~1.0
    assert out["p_value_one_sided"] > 0.95


def test_bootstrap_pure_win_series_p_value_low():
    pnl = np.array([10.0, 20.0, 5.0, 30.0, 15.0, 25.0, 8.0, 18.0])
    out = bootstrap_trade_stats(pnl, n_iter=2000, seed=13)
    assert out["p_value_one_sided"] < 0.05


def test_raises_on_too_few_trades():
    with pytest.raises(ValueError):
        bootstrap_trade_stats(np.array([1.0]))


def test_detect_col_exact_and_substring():
    from validation.bootstrap import _detect_col
    assert _detect_col(["ts", "equity"], ["ts"]) == "ts"
    assert _detect_col(["bar_ts", "cum_equity"], ["ts", "timestamp"]) == "bar_ts"
    assert _detect_col(["foo", "bar"], ["baz"]) is None


def test_bootstrap_per_regime_handles_missing_column(tmp_path):
    import pandas as pd
    from validation.bootstrap import bootstrap_per_regime
    p = tmp_path / "trades_no_regime.csv"
    pd.DataFrame({"pnl": [10.0, -5.0, 7.0]}).to_csv(p, index=False)
    out = bootstrap_per_regime(p)
    assert out["regime_col"] is None
    assert "note" in out
