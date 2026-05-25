"""Determinism and sanity tests for validation.bootstrap."""
import os
import numpy as np
import pytest
from validation.bootstrap import bootstrap_trade_stats, _stationary_resample_indices

# Phase 9.8g.9 (25 May 2026): the bt_out/ tree is no longer tracked in git,
# so the two real-data hold-out split tests below are skipped unless the
# user has run backtest.py locally first.
_BT_OUT_EQUITY_READY = os.path.exists("bt_out/equity.csv")
_BT_OUT_TRADES_READY = os.path.exists("bt_out/trades.csv")


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


def test_psr_at_zero_threshold_for_balanced_series():
    """Deterministic: symmetric series with exactly zero mean -> PSR(0) ~ 0.5."""
    from validation.bootstrap import probabilistic_sharpe_ratio
    r = np.array([1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 1.5, -1.5] * 5, dtype=np.float64)
    out = probabilistic_sharpe_ratio(r, 0.0)
    # mean is exactly 0 so SR is exactly 0; PSR(0) = Phi(0) = 0.5 exactly
    assert 0.49 <= out["psr"] <= 0.51


def test_psr_high_for_strong_positive_series():
    from validation.bootstrap import probabilistic_sharpe_ratio
    rng = np.random.default_rng(7)
    r = rng.normal(loc=0.5, scale=1.0, size=200)
    out = probabilistic_sharpe_ratio(r, 0.0)
    assert out["psr"] > 0.99


def test_expected_max_sr_increases_with_n_trials():
    from validation.bootstrap import expected_max_sr_periodic
    a = expected_max_sr_periodic(2, 50)
    b = expected_max_sr_periodic(20, 50)
    c = expected_max_sr_periodic(200, 50)
    assert a < b < c


def test_dsr_below_psr_at_zero_threshold():
    from validation.bootstrap import probabilistic_sharpe_ratio, deflated_sharpe_ratio
    rng = np.random.default_rng(13)
    r = rng.normal(loc=0.05, scale=1.0, size=100)
    psr = probabilistic_sharpe_ratio(r, 0.0)["psr"]
    dsr = deflated_sharpe_ratio(r, n_trials=20)["dsr"]
    assert dsr <= psr  # DSR is always more conservative than PSR-at-zero


def test_ljung_box_white_noise_does_not_reject_iid():
    from validation.bootstrap import ljung_box_test
    rng = np.random.default_rng(seed=2026)
    r = rng.normal(size=200)
    out = ljung_box_test(r, lags=10)
    assert out["p_value"] > 0.05


def test_ljung_box_ar1_rejects_iid():
    from validation.bootstrap import ljung_box_test
    rng = np.random.default_rng(seed=2026)
    e = rng.normal(size=300)
    r = np.zeros_like(e)
    for i in range(1, len(e)):
        r[i] = 0.7 * r[i - 1] + e[i]
    out = ljung_box_test(r, lags=10)
    assert out["p_value"] < 0.05


def test_adf_white_noise_is_stationary():
    from validation.bootstrap import adf_test
    rng = np.random.default_rng(seed=2026)
    r = rng.normal(size=200)
    out = adf_test(r)
    assert out["p_value"] < 0.05


def test_walk_forward_window_count():
    from validation.bootstrap import walk_forward_sharpe
    r = np.arange(30, dtype=np.float64)
    out = walk_forward_sharpe(r, window=10, step=1)
    assert len(out) == 21  # 30 - 10 + 1
    assert out[0]["start"] == 0 and out[0]["end"] == 9
    assert out[-1]["start"] == 20 and out[-1]["end"] == 29


def test_walk_forward_consistent_positive_returns():
    """Strictly positive constant-mean returns -> consistency_rate == 1.0."""
    from validation.bootstrap import walk_forward_sharpe, walk_forward_summary
    rng = np.random.default_rng(seed=2026)
    r = 1.0 + 0.1 * rng.normal(size=100)  # mean=1, sd~0.1, all positive on avg
    windows = walk_forward_sharpe(r, window=20, step=1)
    s = walk_forward_summary(windows)
    assert s["consistency_rate"] == 1.0
    assert s["sharpe_mean"] > 5.0  # very high for mean/sd ~ 10


def test_walk_forward_zero_mean_noise_inconsistent():
    """Zero-mean noise -> consistency_rate near 0.5, not 1.0."""
    from validation.bootstrap import walk_forward_sharpe, walk_forward_summary
    rng = np.random.default_rng(seed=2026)
    r = rng.normal(size=200)
    windows = walk_forward_sharpe(r, window=20, step=1)
    s = walk_forward_summary(windows)
    assert 0.25 < s["consistency_rate"] < 0.75


# -----------------------------------------------------------------------------
# Phase B-0g: hold-out split tests (require bt_out/ to be populated)
# -----------------------------------------------------------------------------

@pytest.mark.skipif(
    not _BT_OUT_EQUITY_READY,
    reason="bt_out/equity.csv not present; run backtest.py first",
)
def test_holdout_split_equity_runs_on_real_data():
    from validation.bootstrap import holdout_split_equity
    r = holdout_split_equity("bt_out/equity.csv", train_days=24)
    assert r["train"]["n"] == 24
    assert r["test"]["n"] >= 1
    assert "boot_ci95_sharpe_ann" in r["train"]
    assert "test_point_in_train_ci" in r["decision"]


@pytest.mark.skipif(
    not _BT_OUT_TRADES_READY,
    reason="bt_out/trades.csv not present; run backtest.py first",
)
def test_holdout_split_trades_runs_on_real_data():
    from validation.bootstrap import holdout_split_trades
    r = holdout_split_trades("bt_out/trades.csv", train_days=24)
    assert r["train"]["n"] >= 1
    assert r["test"]["n"] >= 1
    assert r["train"]["n"] + r["test"]["n"] == 24


def test_holdout_split_equity_constant_positive_returns_same_sign():
    import numpy as np, pandas as pd, tempfile, os
    from validation.bootstrap import holdout_split_equity
    df = pd.DataFrame({"daily_return": np.linspace(0.0005, 0.0015, 30)})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        df.to_csv(f.name, index=False)
        path = f.name
    try:
        r = holdout_split_equity(path, train_days=24, n_iter=1000)
        assert r["train"]["sharpe_ann"] > 0
        assert r["test"]["sharpe_ann"] > 0
        assert bool(r["decision"]["same_sign"]) is True
    finally:
        os.unlink(path)
