"""Phase 8h.2: ADX-based market regime classifier.

Hand-rolled Wilder ADX (no talib/pandas_ta dependency).
Returns regime label per bar: TREND (ADX>25) / RANGE (ADX<20) / CHOP (20-25).
Mean-reversion strategies expect edge in RANGE, neutral in CHOP, hostile in TREND.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def wilder_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Wilder ADX + DI+/DI-. Returns DataFrame with adx, plus_di, minus_di."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    return pd.DataFrame({"adx": adx, "plus_di": plus_di, "minus_di": minus_di})


def classify_regime(df: pd.DataFrame, period: int = 14, trend_threshold: float = 25.0, range_threshold: float = 20.0) -> pd.Series:
    """Returns Series of TREND/RANGE/CHOP labels indexed by df.index."""
    indi = wilder_adx(df, period=period)
    adx = indi["adx"]
    regime = pd.Series("CHOP", index=df.index, dtype=object)
    regime[adx > trend_threshold] = "TREND"
    regime[adx < range_threshold] = "RANGE"
    regime[adx.isna()] = "UNKNOWN"
    return regime
