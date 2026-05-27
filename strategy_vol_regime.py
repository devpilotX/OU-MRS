"""Phase 9.8h.C.1 - per-symbol vol-regime gates derived from B.5 findings.

B.5 walk-forward + vol-regime stratification (rv20 terciles, 39-day sample)
showed that BANKNIFTY has a mid-vol chop trap (LOW and HIGH buckets profitable,
MID losing) and MIDCPNIFTY has a clean LOW-vol concentration (5/5 wins, per-trade
Sharpe 3.13 when rv20 < 0.0074).

This module exposes:

  * compute_rv20(closes)          - 20-bar log-return realized vol (annualized
                                    by sqrt(375) intraday-minute convention)
  * passes_vol_filter(sym, rv20)  - True if rv20 is outside the excluded band
  * vol_size_multiplier(sym, rv20)- 1.0 default; >1 when in the accelerator zone

All bands and thresholds are env-tunable so we can A/B without code changes:

  OU_BNF_VOL_BAND_EXCLUDE = "0.0077,0.0092"   (skip entries inside this band)
  OU_NF_VOL_BAND_EXCLUDE  = ""                (no NF filter; NF is disabled
                                              entirely via INSTRUMENTS env)
  OU_MCN_VOL_BAND_EXCLUDE = ""                (no MCN filter)
  OU_MCN_LOW_VOL_THRESHOLD  = "0.0074"        (rv20 below this -> accelerator)
  OU_MCN_LOW_VOL_MULTIPLIER = "1.5"           (size multiplier in accelerator zone)

Setting OU_VOL_REGIME=off disables the entire module (returns pass/1.0 always).
This is the safe-rollback switch.
"""
from __future__ import annotations

import math
import os
from typing import Iterable, Optional, Tuple

# 375 minutes per regular session (9:15-15:30). Annualization factor for
# minute-bar realized vol over a 20-bar window. We do NOT multiply by sqrt(252)
# here; rv20 in this module is the *intraday-session* sigma scale used in B.5.
_RV_LOOKBACK = 20
_RV_SCALE = math.sqrt(375.0)


def compute_rv20(closes: Iterable[float], lookback: int = _RV_LOOKBACK) -> Optional[float]:
    """Return the rv20 figure used in the B.5 stratification.

    Definition: stdev of the last `lookback` 1-bar log returns, scaled by
    sqrt(375). Returns None when there aren't enough bars (caller should treat
    as "unknown regime" -> pass through with multiplier 1.0).
    """
    px = [float(c) for c in closes if c is not None]
    if len(px) < lookback + 1:
        return None
    rets = []
    for i in range(len(px) - lookback, len(px)):
        if px[i - 1] <= 0 or px[i] <= 0:
            return None
        rets.append(math.log(px[i] / px[i - 1]))
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * _RV_SCALE


def _is_enabled() -> bool:
    return os.environ.get("OU_VOL_REGIME", "on").strip().lower() != "off"


def _parse_band(env_name: str) -> Optional[Tuple[float, float]]:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != 2:
        return None
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


_SYM_KEYS = {
    "BNF": "OU_BNF_VOL_BAND_EXCLUDE",
    "BANKNIFTY": "OU_BNF_VOL_BAND_EXCLUDE",
    "NF": "OU_NF_VOL_BAND_EXCLUDE",
    "NIFTY": "OU_NF_VOL_BAND_EXCLUDE",
    "MCN": "OU_MCN_VOL_BAND_EXCLUDE",
    "MIDCPNIFTY": "OU_MCN_VOL_BAND_EXCLUDE",
}


def passes_vol_filter(symbol: str, rv20: Optional[float]) -> Tuple[bool, str]:
    """Return (allowed, reason). reason is empty string when allowed."""
    if not _is_enabled():
        return True, ""
    if rv20 is None:
        # unknown regime -> let the trade through, but tag so we can audit
        return True, ""
    env_key = _SYM_KEYS.get(symbol.upper())
    if not env_key:
        return True, ""
    band = _parse_band(env_key)
    if not band:
        return True, ""
    lo, hi = band
    if lo <= rv20 <= hi:
        return False, f"vol_band_excluded rv20={rv20:.4f} band=[{lo:.4f},{hi:.4f}]"
    return True, ""


def vol_size_multiplier(symbol: str, rv20: Optional[float]) -> float:
    """Return size multiplier (>=1.0). Only MCN has an accelerator zone by default."""
    if not _is_enabled() or rv20 is None:
        return 1.0
    sym = symbol.upper()
    if sym in ("MCN", "MIDCPNIFTY"):
        try:
            thresh = float(os.environ.get("OU_MCN_LOW_VOL_THRESHOLD", "0.0074"))
            mult = float(os.environ.get("OU_MCN_LOW_VOL_MULTIPLIER", "1.5"))
        except ValueError:
            return 1.0
        if rv20 < thresh and mult > 1.0:
            return mult
    return 1.0
