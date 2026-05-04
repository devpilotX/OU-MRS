"""Phase 8h.2 / 9.8 tests: regime classifier."""
import pandas as pd
import numpy as np
from regime import wilder_adx, classify_regime


def test_wilder_adx_returns_required_columns():
    n = 100
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "high": 100 + rng.normal(0, 1, n).cumsum(),
        "low": 99 + rng.normal(0, 1, n).cumsum(),
        "close": 99.5 + rng.normal(0, 1, n).cumsum(),
    })
    out = wilder_adx(df, period=14)
    assert "adx" in out.columns
    assert "plus_di" in out.columns
    assert "minus_di" in out.columns
    assert len(out) == n


def test_classify_regime_returns_known_labels():
    n = 100
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "high": 100 + rng.normal(0, 1, n).cumsum(),
        "low": 99 + rng.normal(0, 1, n).cumsum(),
        "close": 99.5 + rng.normal(0, 1, n).cumsum(),
    })
    series = classify_regime(df)
    assert len(series) == n
    valid_labels = {"TREND", "RANGE", "CHOP", "UNKNOWN"}
    assert set(series.unique()).issubset(valid_labels)


def test_classify_regime_strong_trend_yields_trend():
    n = 200
    close = pd.Series(100 + np.arange(n) * 0.5)
    df = pd.DataFrame({
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
    })
    series = classify_regime(df)
    last_50 = series.iloc[-50:]
    assert (last_50 == "TREND").mean() > 0.5


def test_classify_regime_handles_nan_adx_as_unknown():
    n = 30
    rng = np.random.default_rng(2)
    df = pd.DataFrame({
        "high": 100 + rng.normal(0, 1, n),
        "low": 99 + rng.normal(0, 1, n),
        "close": 99.5 + rng.normal(0, 1, n),
    })
    series = classify_regime(df, period=14)
    assert series.iloc[0] == "UNKNOWN"
