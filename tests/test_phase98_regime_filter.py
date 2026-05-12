"""Phase 9.8 tests: regime allow-list filter."""
import os
import pandas as pd
import numpy as np
import pytest

os.environ.pop("OU_REGIME_FILTER", None)
os.environ.pop("BT_REGIME_FILTER", None)

from strategy import compute_signal, Params


def _mr_df(n=200, seed=42):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-04-01 09:30", periods=n, freq="1min")
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.7 * x[i-1] + rng.normal(0, 0.5)
    close = 100.0 + x
    high = close + np.abs(rng.normal(0, 0.2, n))
    low = close - np.abs(rng.normal(0, 0.2, n))
    open_ = np.r_[close[0], close[:-1]]
    vol = rng.integers(100, 1000, n).astype(float)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": vol
    }, index=ts)


def test_regime_allow_default_is_empty_tuple():
    p = Params()
    assert p.regime_allow == ()


def test_regime_allow_can_be_set():
    p = Params(regime_allow=("CHOP",))
    assert p.regime_allow == ("CHOP",)
    p2 = Params(regime_allow=("CHOP", "RANGE"))
    assert p2.regime_allow == ("CHOP", "RANGE")


def test_compute_signal_runs_with_empty_filter():
    df = _mr_df()
    p = Params()
    sig = compute_signal(df, p)
    assert sig is None or hasattr(sig, "z")


def test_compute_signal_runs_with_chop_filter():
    df = _mr_df()
    p = Params(regime_allow=("CHOP",))
    sig = compute_signal(df, p)
    assert sig is None or hasattr(sig, "z")


def test_compute_signal_runs_with_chop_range_filter():
    df = _mr_df()
    p = Params(regime_allow=("CHOP", "RANGE"))
    sig = compute_signal(df, p)
    assert sig is None or hasattr(sig, "z")


def test_filter_handles_uncommon_df_shapes():
    df = _mr_df(n=50)
    p = Params(regime_allow=("CHOP",))
    sig = compute_signal(df, p)
    assert sig is None or hasattr(sig, "z")


def test_strong_trend_is_filtered_by_chop_only():
    n = 200
    rng = np.random.default_rng(0)
    ts = pd.date_range("2026-04-01 09:30", periods=n, freq="1min")
    close = 100.0 + np.arange(n) * 0.5 + rng.normal(0, 0.05, n)
    high = close + 0.1
    low = close - 0.1
    open_ = np.r_[close[0], close[:-1]]
    vol = np.full(n, 500.0)
    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": vol
    }, index=ts)
    p = Params(regime_allow=("CHOP",))
    sig = compute_signal(df, p)
    assert sig is None
