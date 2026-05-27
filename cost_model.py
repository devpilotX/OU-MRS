# Phase 9.5c: realistic FnO round-trip cost model
# Phase 9.8h.C.2: per-symbol + size-aware + vol-aware slippage estimation.

import os
from typing import Optional

DEF_COSTS = {
    "brokerage_per_order": 20.0,
    "stt_pct_sell": 0.0125 / 100,
    "txn_pct": 0.0019 / 100,
    "sebi_pct": 0.0001 / 100,
    "gst_pct": 18.0 / 100,
    "stamp_pct_buy": 0.002 / 100,
}


def compute_rt_cost(entry_price, exit_price, lot_size, qty_lots=1, costs=None, side="BUY"):  # Phase A1.5
    if costs is None:
        costs = DEF_COSTS
    contracts = lot_size * qty_lots
    ne = entry_price * contracts
    nx = exit_price * contracts
    brokerage = costs["brokerage_per_order"] * 2
    # Phase A1.5: side-aware sell/buy notional (was max/min, mis-billed losers)
    _su = side.upper() if isinstance(side, str) else "BUY"
    if _su == "BUY":
        sell_notional = nx  # long: sold at exit
        buy_notional = ne   # long: bought at entry
    else:
        sell_notional = ne  # short: sold at entry
        buy_notional = nx   # short: bought at exit
    stt = sell_notional * costs["stt_pct_sell"]
    txn = (ne + nx) * costs["txn_pct"]
    sebi = (ne + nx) * costs["sebi_pct"]
    gst = (brokerage + txn + sebi) * costs["gst_pct"]
    stamp = buy_notional * costs["stamp_pct_buy"]
    return brokerage + stt + txn + sebi + gst + stamp


# =====================================================================
# Phase 9.8h.C.2: realistic per-symbol slippage estimation.
#
# The legacy backtester applies a flat SLIPPAGE_TICKS (default 2) on every
# fill, identical across symbols and regardless of lot count or volatility.
# B.5's slippage sweep proved this is too coarse: each symbol shows a
# different per-tick P&L slope (BNF ~-Rs193/tick/trade, NF ~-Rs244,
# MCN ~-Rs240 at the live lot size).
#
# This module exposes estimate_slippage_ticks(symbol, qty_lots, rv20) which
# returns a float number of ticks. The backtester multiplies by TICK (0.05)
# to get the rupee offset. The model is intentionally simple and tunable
# via env vars; it is NOT a market-impact model with depth-of-book - that
# is C.3's responsibility. Here we only encode:
#   * a per-symbol base spread (NF is less liquid than BNF in our window)
#   * a high-vol surcharge (wider spreads in stress)
#   * a size penalty (lifting more lots moves the book)
#
# Master switch: OU_COST_MODEL_V2=on enables this; default is the legacy
# flat BT_SLIPPAGE_TICKS behavior for byte-exact backwards compatibility.
# =====================================================================

# Per-symbol slippage profile.
#   base_ticks      - half-spread cost in ticks, per fill (one side)
#   high_vol_extra  - additional ticks when rv20 > high_vol_threshold
#   per_lot_extra   - additional ticks for each lot above the first
DEFAULT_SLIPPAGE_PROFILE = {"base_ticks": 2.0, "high_vol_extra": 1.0, "per_lot_extra": 0.5}
SLIPPAGE_PROFILES = {
    "BANKNIFTY":  {"base_ticks": 2.0, "high_vol_extra": 1.0, "per_lot_extra": 0.5},
    "NIFTY":      {"base_ticks": 3.0, "high_vol_extra": 1.0, "per_lot_extra": 0.5},
    "MIDCPNIFTY": {"base_ticks": 2.0, "high_vol_extra": 1.0, "per_lot_extra": 0.5},
}

# Short-name aliases that match the live INSTRUMENTS list.
_SYM_ALIASES = {
    "BNF": "BANKNIFTY", "BANKNIFTY": "BANKNIFTY",
    "NF":  "NIFTY",     "NIFTY":     "NIFTY",
    "MCN": "MIDCPNIFTY","MIDCPNIFTY":"MIDCPNIFTY",
}


def _resolve_symbol(symbol: str) -> str:
    if not symbol:
        return ""
    return _SYM_ALIASES.get(symbol.upper(), symbol.upper())


def _is_v2_enabled(env=None) -> bool:
    e = env if env is not None else os.environ
    val = (e.get("OU_COST_MODEL_V2") or "off").strip().lower()
    return val in ("on", "true", "1", "yes")


def _high_vol_threshold(env=None) -> float:
    e = env if env is not None else os.environ
    try:
        return float(e.get("OU_HIGH_VOL_THRESHOLD", "0.012"))
    except (TypeError, ValueError):
        return 0.012


def estimate_slippage_ticks(
    symbol: str,
    qty_lots: int = 1,
    rv20: Optional[float] = None,
    env=None,
) -> float:
    """Phase 9.8h.C.2: per-symbol + size-aware + vol-aware slippage in ticks.

    Returns a non-negative float number of ticks for ONE side of a fill.
    Multiply by TICK at the call site to convert to rupees of price offset.

    Behavior when ``OU_COST_MODEL_V2`` is off (default): returns the legacy
    ``BT_SLIPPAGE_TICKS`` integer (default 2). This preserves byte-exact
    backwards compatibility for unaltered backtests.
    """
    e = env if env is not None else os.environ
    if not _is_v2_enabled(e):
        # Legacy path - flat ticks, no per-symbol awareness.
        try:
            return float(int(e.get("BT_SLIPPAGE_TICKS", "2")))
        except (TypeError, ValueError):
            return 2.0
    prof = SLIPPAGE_PROFILES.get(_resolve_symbol(symbol), DEFAULT_SLIPPAGE_PROFILE)
    ticks = float(prof["base_ticks"])
    # Vol surcharge: stress regimes have wider spreads and more impact.
    if rv20 is not None and rv20 > _high_vol_threshold(e):
        ticks += float(prof["high_vol_extra"])
    # Size penalty: each lot above 1 nudges the book.
    try:
        q = int(qty_lots)
    except (TypeError, ValueError):
        q = 1
    if q > 1:
        ticks += float(prof["per_lot_extra"]) * (q - 1)
    if ticks < 0.0:
        ticks = 0.0
    return ticks
