"""
Pure OU-MRS signal logic. No I/O, no broker calls. Unit-testable.
Shared between live bot and backtest so they produce identical signals.

Phase 8c: ADX-based regime filter added. Skips entries when market is
trending (ADX > threshold). Addresses walk-forward Fold1 weakness.

Phase 9.8g.4 (25 May 2026 audit B6): removed dead vols.sum<=0 check
after the TWAP fallback. The fallback assigns np.ones_like(vols), so
the subsequent sum is always > 0. Misleading 'Strict volume' comment
also removed.

Phase 9.8h (25 May 2026 02:45 IST): BE ratchet + paper SL added as the
9.7AP-equivalent protective layer. Both env-gated with non-zero defaults
(Sacred Rule #41). log_config_sanity() emits the effective env values at
startup so any future kill-switch regression surfaces immediately.

Phase 9.8h.3 (25 May 2026 03:20 IST): in-code defaults updated to the
sweep-winning config from the DSR-corrected coarse sweep (Sacred Rule
#43). paper=1.5, be=1.25, trail=3.0/0.3. Previous defaults (paper=2.0,
be=1.0, trail=0.0/0.0) were placeholders -- they are now the global
compromise that gives BNF its global optimum, MCN 83% of its optimum,
and NF its least-bad row on the 27 Mar -> 22 May sample.

Phase 9.8g.11 (25 May 2026 15:24 IST, Fix B): symbol-specific time-of-day
entry cutoff helper. Env-gated, default OFF for all symbols.
is_entry_blocked_by_tod(symbol, bar_time) returns True iff
OU_<SHORT>_AFTERNOON_CUTOFF_HHMM env var is set to a valid HHMM and the
bar's IST hh:mm is >= cutoff. Motivated by Phase 9.8g.10 baseline backtest:
NF afternoon bucket (13:30-14:45) carried 63% of NF's total backtest loss
over the 37-day FUT window; BNF/MCN afternoons are net positive.
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
    regime_allow: tuple = ()         # Phase 9.8: regime allow-list (empty = permissive)


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
    """ADX(n) via Wilder EMA smoothing. Returns most recent ADX or None if insufficient bars."""
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
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info(f'[skip] Phase 9.7Z window: have ' + str(len(df)) + ' need ' + str(p.window))
        return None
    w = df.iloc[-p.window:]
    closes = w["close"].to_numpy(dtype=float)
    highs  = w["high"].to_numpy(dtype=float)
    lows   = w["low"].to_numpy(dtype=float)
    vols   = w["volume"].to_numpy(dtype=float)

    # Phase 9.1: TWAP fallback when volume is unavailable (e.g. INDEX backfill).
    # Phase 9.8g.4: removed dead 'if vols.sum() <= 0: return None' below this
    # - unreachable because vols is now ones_like with sum == len(vols) > 0.
    if vols.sum() <= 0.0:
        vols = np.ones_like(vols, dtype=float)
    center = (closes * vols).sum() / vols.sum()
    center = max(center, 1e-6)
    x = np.log(closes) - math.log(center)

    est = estimate_ou(x)
    if est is None:
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info('[skip] Phase 9.7Z estimate_ou: returned None')
        return None
    theta, mu, sigma_eq, half_life, r2 = est

    _hl_min = float(__import__('os').environ.get('OU_HL_MIN', str(p.min_half_life)))
    _hl_max = float(__import__('os').environ.get('OU_HL_MAX', str(p.max_half_life)))
    if not (_hl_min <= half_life <= _hl_max):
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info(f'[skip] Phase 9.7Z half_life: ' + format(half_life, '.2f') + ' not in [' + str(_hl_min) + ', ' + str(_hl_max) + ']')
        return None
    if r2 < p.min_r2:
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info(f'[skip] Phase 9.7Z r2: ' + format(r2, '.3f') + ' < ' + str(p.min_r2))
        return None
    if __import__('os').environ.get('OU_VOL_CONFIRM', 'on').lower() != 'off' and vols[-5:].mean() < vols.mean():
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info(f'[skip] Phase 9.7Z vol_confirm: last5=' + format(float(vols[-5:].mean()), '.0f') + ' < mean=' + format(float(vols.mean()), '.0f'))
        return None

    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
    )
    atr = float(tr[-p.atr_lookback:].mean())
    atr_hist = pd.Series(tr).rolling(p.atr_lookback).mean().dropna()
    if atr_hist.empty:
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info('[skip] Phase 9.7Z atr_hist: empty')
        return None
    pct = float((atr_hist < atr).mean())
    if __import__('os').environ.get('OU_ATR_PCT_FILTER', 'on').lower() != 'off' and not (p.atr_pct_low <= pct <= p.atr_pct_high):
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info(f'[skip] Phase 9.7Z atr_pct: ' + format(pct, '.2f') + ' not in [' + str(p.atr_pct_low) + ', ' + str(p.atr_pct_high) + ']')
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
        import logging as _lg97z
        _lg97z.getLogger('ou_mrs').info('[skip] Phase 9.7Z adx_val: None')
        return None
    if adx_val > p.adx_threshold:
        import logging as _lg_p98h
        _lg_p98h.getLogger("ou_mrs").info(f"[regime] skip: adx={adx_val:.2f} > {p.adx_threshold} (TREND)")
        return None  # trending regime - skip entries

    # Phase 9.8: regime allow-list filter (CHOP-only, etc.)
    if getattr(p, "regime_allow", None):
        try:
            from regime import classify_regime
            _series_p98 = classify_regime(df)
            _bar_regime_p98 = str(_series_p98.iloc[-1]) if len(_series_p98) else "UNKNOWN"
        except Exception:
            _bar_regime_p98 = "UNKNOWN"
        if _bar_regime_p98 not in p.regime_allow:
            import logging as _lg_p98h2
            _lg_p98h2.getLogger("ou_mrs").info(f"[regime] skip: regime={_bar_regime_p98} not in allow={p.regime_allow}")
            return None

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
    # Phase 9.7AC: env-controlled disable (3/3 historical Z_VEL_STALL = loss)
    if _os_p95.environ.get('OU_DISABLE_Z_VEL_STALL', 'off').lower() == 'on':
        return False
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

# Phase 9.5g: trail stop helper
import os as _os_p95g

def _env_float_p95g(name, default):
    try:
        v = _os_p95g.environ.get(name)
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)

# Phase 9.8h.3: in-code defaults updated to sweep-winning config (Sacred Rule #43)
OU_TRAIL_TRIGGER_ATR_MULT = _env_float_p95g("OU_TRAIL_TRIGGER_ATR_MULT", 3.0)
OU_TRAIL_LOCK_PCT = _env_float_p95g("OU_TRAIL_LOCK_PCT", 0.30)

def should_trail_stop(current_pnl_pts, peak_pnl_pts, atr):
    if OU_TRAIL_TRIGGER_ATR_MULT <= 0 or OU_TRAIL_LOCK_PCT <= 0:
        return False
    if atr <= 0:
        return False
    activation_pts = OU_TRAIL_TRIGGER_ATR_MULT * atr
    if peak_pnl_pts < activation_pts:
        return False
    lock_floor = peak_pnl_pts * (1.0 - OU_TRAIL_LOCK_PCT)
    return current_pnl_pts <= lock_floor


# === Phase 9.8h: BE ratchet + paper SL + startup config sanity log ===
# Both env-gated with NON-ZERO defaults so the protective layer is never
# accidentally disabled at startup (Sacred Rule #41).
# All helpers expose pure override params so tests can pin values without
# needing to reload the module.
#
# Phase 9.8h.3: defaults updated from DSR-corrected sweep (Sacred Rule #43).
# Previous in-code defaults (be_trigger=1.0, paper=2.0) were placeholders.
# Sweep top configs across BNF + MCN converged on be_trigger=1.25 and
# paper=1.5; NF stays negative on backtest regardless (B11 live/backtest gap).

OU_BE_TRIGGER_ATR_MULT = _env_float_p95g("OU_BE_TRIGGER_ATR_MULT", 1.25)
OU_BE_LOCK_ATR_MULT    = _env_float_p95g("OU_BE_LOCK_ATR_MULT",    0.1)
OU_PAPER_SL_ATR_MULT   = _env_float_p95g("OU_PAPER_SL_ATR_MULT",   1.5)


def be_ratchet_armed(peak_pnl_pts, atr, trigger_mult=None):
    """Phase 9.8h: armed once peak unrealized gain >= trigger_mult * ATR.
    trigger_mult: pure override for tests. None -> use OU_BE_TRIGGER_ATR_MULT."""
    t = OU_BE_TRIGGER_ATR_MULT if trigger_mult is None else float(trigger_mult)
    if t <= 0 or atr <= 0:
        return False
    return peak_pnl_pts >= t * atr


def be_ratchet_hit(current_pnl_pts, peak_pnl_pts, atr,
                  trigger_mult=None, lock_mult=None):
    """Phase 9.8h: fires when armed AND current PnL drops to lock floor (~breakeven).
    lock_mult: pure override for tests. None -> use OU_BE_LOCK_ATR_MULT."""
    if not be_ratchet_armed(peak_pnl_pts, atr, trigger_mult):
        return False
    lk = OU_BE_LOCK_ATR_MULT if lock_mult is None else float(lock_mult)
    return current_pnl_pts <= lk * atr


def paper_sl_hit(adverse_px, entry_px, side, atr, sl_mult=None):
    """Phase 9.8h: catastrophic stop at entry +/- sl_mult * ATR.

    Caller supplies adverse_px (bar low for long, bar high for short) so the
    check fires on intra-bar trigger; the backtest fill still executes at the
    NEXT bar's open with slippage, preserving the no-look-ahead invariant.
    """
    m = OU_PAPER_SL_ATR_MULT if sl_mult is None else float(sl_mult)
    if m <= 0 or atr <= 0:
        return False
    distance = m * atr
    if side == "BUY":
        return adverse_px <= entry_px - distance
    if side == "SELL":
        return adverse_px >= entry_px + distance
    return False


def log_config_sanity():
    """Phase 9.8h (Sacred Rule #41): emit effective env-gated config + warn
    on any kill switch (env var <= 0) that disables a protective feature.
    Call once at startup from live runner and from backtest run().
    """
    import logging as _lg
    log = _lg.getLogger("ou_mrs")
    cfg = {
        "OU_HL_MULTIPLIER":          HL_MULTIPLIER,
        "OU_Z_VEL_STALL":            Z_VEL_STALL_THRESHOLD,
        "OU_VEL_STALL_BARS":         VEL_STALL_BARS,
        "OU_DISABLE_Z_VEL_STALL":    _os_p95.environ.get("OU_DISABLE_Z_VEL_STALL", "off"),
        "OU_TRAIL_TRIGGER_ATR_MULT": OU_TRAIL_TRIGGER_ATR_MULT,
        "OU_TRAIL_LOCK_PCT":         OU_TRAIL_LOCK_PCT,
        "OU_BE_TRIGGER_ATR_MULT":    OU_BE_TRIGGER_ATR_MULT,
        "OU_BE_LOCK_ATR_MULT":       OU_BE_LOCK_ATR_MULT,
        "OU_PAPER_SL_ATR_MULT":      OU_PAPER_SL_ATR_MULT,
        "OU_ATR_MULT":               _os_p95.environ.get("OU_ATR_MULT", "1.5"),
        # Phase 9.8g.11 (Fix B): per-symbol TOD entry cutoff. Default OFF (unset / "").
        "OU_BNF_AFTERNOON_CUTOFF_HHMM": _os_p95.environ.get("OU_BNF_AFTERNOON_CUTOFF_HHMM", ""),
        "OU_NF_AFTERNOON_CUTOFF_HHMM":  _os_p95.environ.get("OU_NF_AFTERNOON_CUTOFF_HHMM",  ""),
        "OU_MCN_AFTERNOON_CUTOFF_HHMM": _os_p95.environ.get("OU_MCN_AFTERNOON_CUTOFF_HHMM", ""),
    }
    log.info("[config-sanity] " + ", ".join(f"{k}={v}" for k, v in cfg.items()))
    if OU_TRAIL_TRIGGER_ATR_MULT <= 0 or OU_TRAIL_LOCK_PCT <= 0:
        log.warning("[config-sanity] TRAIL_STOP DISABLED (OU_TRAIL_TRIGGER_ATR_MULT and/or OU_TRAIL_LOCK_PCT <= 0)")
    if OU_BE_TRIGGER_ATR_MULT <= 0:
        log.warning("[config-sanity] BE_RATCHET DISABLED (OU_BE_TRIGGER_ATR_MULT <= 0)")
    if OU_PAPER_SL_ATR_MULT <= 0:
        log.warning("[config-sanity] PAPER_SL DISABLED (OU_PAPER_SL_ATR_MULT <= 0)")


# === Phase 9.8g.11 (25 May 2026 audit Fix B): symbol-specific TOD entry cutoff ===
# Per Phase 9.8g.10 baseline-backtest TOD analysis (validation/tod_NIFTY.json):
# NF afternoon bucket 13:30-14:45 IST accumulated 63% of NF's total loss
# (n=7, 14.3% WR, tSR -2.21, -Rs 8,306 over 37 days). BNF/MCN afternoons are
# net positive (tSR +0.42 / +0.41) so the cutoff is symbol-specific by design.
# Ships disabled by default; opt-in via OU_<SHORT>_AFTERNOON_CUTOFF_HHMM env var.

_TOD_SHORT_KEYS_P98G11 = {
    "BANKNIFTY":  "BNF", "BNF": "BNF",
    "MIDCPNIFTY": "MCN", "MCN": "MCN",
    "NIFTY":      "NF",  "NF":  "NF",
}


def is_entry_blocked_by_tod(symbol, bar_time) -> bool:
    """Phase 9.8g.11 (Fix B): symbol-specific time-of-day entry cutoff.

    Reads OU_<SHORT>_AFTERNOON_CUTOFF_HHMM env var (e.g. OU_NF_AFTERNOON_CUTOFF_HHMM=1330).
    Returns True iff the cutoff env var is set to a valid HHMM and the bar's IST hh:mm
    is >= cutoff (i.e. the new entry should be blocked).

    Disabled (returns False) when:
      - symbol or bar_time is None
      - symbol is not in {BANKNIFTY, BNF, NIFTY, NF, MIDCPNIFTY, MCN}
      - env var is unset, empty, "0000", or not a valid 4-digit HHMM

    bar_time: any object exposing integer .hour and .minute attributes
    (e.g. pd.Timestamp, datetime.datetime, datetime.time).

    Both short (BNF/NF/MCN) and long (BANKNIFTY/NIFTY/MIDCPNIFTY) symbol forms
    are accepted so the same helper works from backtest.py --symbol and from
    ou_mrs.py's runner.symbol.
    """
    if symbol is None or bar_time is None:
        return False
    short = _TOD_SHORT_KEYS_P98G11.get(str(symbol).upper())
    if short is None:
        return False
    raw = _os_p95.environ.get(f"OU_{short}_AFTERNOON_CUTOFF_HHMM", "").strip()
    if not raw or raw == "0000":
        return False
    try:
        hhmm = int(raw)
    except (ValueError, TypeError):
        return False
    cutoff_h, cutoff_m = divmod(hhmm, 100)
    if not (0 <= cutoff_h <= 23 and 0 <= cutoff_m <= 59):
        return False
    try:
        bt_h = int(bar_time.hour)
        bt_m = int(bar_time.minute)
    except (AttributeError, TypeError, ValueError):
        return False
    return (bt_h, bt_m) >= (cutoff_h, cutoff_m)
