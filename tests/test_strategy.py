"""Phase 6 unit tests. Regression protection for signal filters."""
import numpy as np
import pandas as pd
from strategy import compute_signal, Params

def _mk_df(closes, volumes=None, start_ts="2026-01-15 09:30"):
    n = len(closes)
    ts = pd.date_range(start_ts, periods=n, freq="1min")
    if volumes is None:
        volumes = [1000] * n
    return pd.DataFrame({
        "open":   closes,
        "high":   [c + 5 for c in closes],
        "low":    [c - 5 for c in closes],
        "close":  closes,
        "volume": volumes,
    }, index=ts)

def test_short_window_returns_none():
    df = _mk_df([56000.0] * 10)
    assert compute_signal(df, Params()) is None

def test_zero_volume_returns_none():
    df = _mk_df([56000.0 + i*2 for i in range(50)], volumes=[0]*50)
    assert compute_signal(df, Params()) is None

def test_declining_volume_returns_none():
    closes = [56000.0 + float(np.sin(i/5.0))*50 for i in range(50)]
    vols = [1000]*45 + [50]*5
    df = _mk_df(closes, vols)
    assert compute_signal(df, Params()) is None

def test_flat_series_returns_none():
    df = _mk_df([56000.0] * 50)
    assert compute_signal(df, Params()) is None

def test_signal_shape_when_valid():
    rng = np.random.default_rng(7)
    mu = 56000.0
    x = [mu]
    for _ in range(60):
        x.append(mu + 0.6 * (x[-1] - mu) + rng.normal(0, 40))
    df = _mk_df(x)
    sig = compute_signal(df, Params())
    if sig is not None:
        assert sig.z is not None
        assert sig.half_life > 0
        assert sig.sigma_eq > 0
        assert sig.r2 >= 0
        assert sig.price > 0
        assert sig.side in (None, "BUY", "SELL")
