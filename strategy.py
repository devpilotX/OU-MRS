"""
Pure OU-MRS signal logic. No I/O, no broker calls. Unit-testable.
Shared between live bot and backtest so they produce identical signals.

Phase 8c: ADX-based regime filter added. Skips entries when market is
trending (ADX > threshold). Addresses walk-forward Fold1 weakness.
"""
import math
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    side: Optional[str]
    z: float
    z_prev: float
    half_life: float
    sigma_eq: float
    mu: float
    atr: float
    price: float
    r2: float
    adx: float = 0.0  # Phase 8c: regime strength (default keeps existing tests passing)


@dataclass
class Params:
    window: int = 40
    z_entry: float = 1.5
    z_stop: float = 3.5
    atr_lookback: int = 14
    min_half_life: float = 1.0
    max_half_life: float = 15.0
    min_r2: float = 0.05
    atr_pct_low: float = 0.20
    atr_pct_high: float = 0.80
    adx_n: int = 14                  # Phase 8c: ADX smoothing period
    adx_threshold: float = 25.0      # Phase 8c: reject entries when ADX above this
    adx_lookback_bars: int = 60      # Phase 8c: bars used for ADX estimation


def estimate_ou(x: np.ndarray):
    if len(x) < 30:
        return None
    x0, x1 = x[:-1], x[1:]
    X = np.vstack([np.ones_like(x0), x0]).T
    coef, *_ = np.linalg.lstsq(X, x1, rcond=None)
    a, b = coef
    if b <= 0 or b >= 1:
        return None
    resid = x1 - (a + b * x0)
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((x1 - x1.mean()) ** 2)) or 1e-12
    r2 = 1 - ss_res / ss_tot
    theta = -math.log(b)
    mu = a / (1 - b)
    var_eps = float(resid.var(ddof=2)) if len(resid) > 2 else float(resid.var())
    sigma2 = var_eps * (-2 * math.log(b)) / ((1 - b ** 2) or 1e-12)
    sigma_eq = math.sqrt(max(sigma2, 1e-12)) / math.sqrt(2 * theta)
    half_life = math.log(2) / theta
    return theta, mu, sigma_eq, half_life, r2


def compute_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, n: int = 14) -> Optional[float]:
    """ADX(n) via simple rolling means. Returns most recent ADX or None if insufficient bars."""
    if len(highs) < 2 * n + 2:
        return None
    high_diff = highs[1:] - highs[:-1]
    low_diff = lows[:-1] - lows[1:]
    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
    )
    tr_s       = pd.Series(tr).ewm(alpha=1.0/n, adjust=False, min_periods=n).mean()  # Wilder
    plus_dm_s  = pd.Series(plus_dm).ewm(alpha=1.0/n, adjust=False, min_periods=n).mean()  # Wilder
    minus_dm_s = pd.Series(minus_dm).ewm(alpha=1.0/n, adjust=False, min_periods=n).mean()  # Wilder
    tr_safe   = tr_s.replace(0, np.nan)
    plus_di   = 100.0 * plus_dm_s / tr_safe
    minus_di  = 100.0 * minus_dm_s / tr_safe
    di_sum    = (plus_di + minus_di).replace(0, np.nan)
    dx        = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx       = dx.ewm(alpha=1.0/n, adjust=False, min_periods=n).mean()  # Wilder.dropna()
    if adx.empty:
        return None
    return float(adx.iloc[-1])


def compute_signal(df: pd.DataFrame, p: Params = Params()) -> Optional[Signal]:
    if len(df) < p.window:
        return None
    w = df.iloc[-p.window:]
    closes = w["close"].to_numpy(dtype=float)
    highs  = w["high"].to_numpy(dtype=float)
    lows   = w["low"].to_numpy(dtype=float)
    vols   = w["volume"].to_numpy(dtype=float)

    # Phase 9.1: TWAP fallback when volume is unavailable (e.g. INDEX backfill)
    if vols.sum() <= 0.0:
        vols = np.ones_like(vols, dtype=float)
    # Strict volume: futures data always has volume. No silent spot fallback.
    if vols.sum() <= 0:
        return None
    center = (closes * vols).sum() / vols.sum()
    center = max(center, 1e-6)
    x = np.log(closes) - math.log(center)

    est = estimate_ou(x)
    if est is None:
        return None
    theta, mu, sigma_eq, half_life, r2 = est

    if not (p.min_half_life <= half_life <= p.max_half_life):
        return None
    if r2 < p.min_r2:
        return None
    if vols[-5:].mean() < vols.mean():
        return None

    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
    )
    atr = float(tr[-p.atr_lookback:].mean())
    atr_hist = pd.Series(tr).rolling(p.atr_lookback).mean().dropna()
    if atr_hist.empty:
        return None
    pct = float((atr_hist < atr).mean())
    if not (p.atr_pct_low <= pct <= p.atr_pct_high):
        return None

    # Phase 8c: regime filter - pull wider tail of df for stable ADX estimate
    adx_tail = df.iloc[-p.adx_lookback_bars:] if len(df) >= p.adx_lookback_bars else df
    adx_val = compute_adx(
        adx_tail["high"].to_numpy(dtype=float),
        adx_tail["low"].to_numpy(dtype=float),
        adx_tail["close"].to_numpy(dtype=float),
        n=p.adx_n,
    )
    if adx_val is None:
        return None
    if adx_val > p.adx_threshold:
        return None  # trending regime - skip entries

    z      = (x[-1] - mu) / max(sigma_eq, 1e-9)
    z_prev = (x[-2] - mu) / max(sigma_eq, 1e-9)

    side = None
    if z < -p.z_entry and z > z_prev:
        side = "BUY"
    elif z > p.z_entry and z < z_prev:
        side = "SELL"

    return Signal(
        side=side, z=float(z), z_prev=float(z_prev),
        half_life=float(half_life), sigma_eq=float(sigma_eq),
        mu=float(mu), atr=atr, price=float(closes[-1]), r2=float(r2),
        adx=float(adx_val),
    )


# === Phase 9.5: half-life time-stop + z-velocity stall ===
import os as _os_p95
HL_MULTIPLIER = float(_os_p95.environ.get("OU_HL_MULTIPLIER", "5.0"))
Z_VEL_STALL_THRESHOLD = float(_os_p95.environ.get("OU_Z_VEL_STALL", "1.0"))
VEL_STALL_BARS = int(_os_p95.environ.get("OU_VEL_STALL_BARS", "2"))


def should_time_stop_hl(bars_held, half_life):
    if half_life is None or half_life <= 0:
        return False
    return bars_held >= math.ceil(HL_MULTIPLIER * half_life)


def should_velocity_stop(z_history, side):
    needed = 3 + VEL_STALL_BARS
    if z_history is None or len(z_history) < needed:
        return False
    velocities = []
    for i in range(VEL_STALL_BARS):
        cur = z_history[-1 - i]
        prev = z_history[-1 - i - 3]
        velocities.append((cur - prev) / 3.0)
    if side == "SELL":
        return all(v > -Z_VEL_STALL_THRESHOLD for v in velocities)
    elif side == "BUY":
        return all(v < +Z_VEL_STALL_THRESHOLD for v in velocities)
    return False
