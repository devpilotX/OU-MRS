"""Phase 8g.2.a: OuMrsRunner — per-symbol state container.

Owns per-symbol state for OU-MRS strategy. Step 2.b will integrate
process_bar() into main(); Step 4 instantiates one runner per active
symbol in INSTRUMENTS for multi-instrument orchestration.

Phase 9.8g.1 (25 May 2026 audit): single source of truth for lot_size.
Removed local _lot_nse dict (had stale NF=75 from reverted 9.7AM,
production is NF=65 per 9.7AQ). Lot size now read exclusively from
self.cfg['lot_size'] = INSTRUMENT_CFG[symbol]['lot_size'] in ou_mrs.py.
Approx-spot moved to module-level default; cfg.approx_spot wins if set.
Sacred Rule #33: INSTRUMENT_CFG is the single source of truth.
"""

import os as _os


# Phase 9.8g.1: approx-spot for notional-cap arithmetic only.
# Mirrors ou_mrs._APPROX_SPOT_AL; cfg.approx_spot overrides per symbol.
_APPROX_SPOT_DEFAULT = {
    "BNF":    53_500.0,
    "NF":     24_800.0,
    "MCN":    14_300.0,
    "SENSEX": 80_000.0,
}


class OuMrsRunner:
    """Per-symbol state container for OU-MRS strategy."""

    def __init__(self, symbol, cfg, broker=None, capital=150_000, params=None, pfm=None, lot_size_default=15):
        self.symbol = symbol
        self.cfg = cfg or {}
        self.broker = broker
        self.capital = capital
        self.params = params
        self.pfm = pfm
        # per-symbol mutable state
        self.position = None
        self.trades_today = 0
        self.pnl_today = 0.0
        self.kill = False
        self.soft_halt = False
        self.reasons_log = []
        # Phase 9.8g.1: convenience accessors from cfg (single source of truth)
        self.lot_size = int(self.cfg.get("lot_size", lot_size_default))
        self.token = self.cfg.get("token")
        self.exchange = self.cfg.get("exchange", "NFO")
        self.symbol_full = self.cfg.get("symbol")
        self.margin_per_lot = self.cfg.get("margin_per_lot", 75_000)
        # Phase 9.7AO: OU_ATR_MULT env override > cfg > default 1.5
        _atr_mult_env = _os.environ.get("OU_ATR_MULT")
        self.atr_mult = float(_atr_mult_env) if _atr_mult_env else float(self.cfg.get("atr_mult", 1.5))
        # Phase 8g.4.a: per-symbol max lots from capital and margin_per_lot
        # Phase 9.7AL.1 (21 May 2026): dual-cap = min(margin_cap, notional_cap @ 3x leverage)
        # Phase 9.8g.1 (25 May 2026): lot_size + approx_spot now read from self.cfg
        # exclusively — no local _lot_nse dict (had stale NF=75 from reverted 9.7AM).
        _nlm = float(_os.environ.get("NOTIONAL_LEVERAGE_MAX", 3.0))
        _spot = float(self.cfg.get("approx_spot") or _APPROX_SPOT_DEFAULT.get(self.symbol, 50_000.0))
        _lsize = int(self.lot_size)
        _margin_cap = max(1, int(self.capital // self.margin_per_lot))
        _notional_cap = max(1, int((self.capital * _nlm) // (_spot * _lsize)))
        self.max_lots = min(_margin_cap, _notional_cap)

    def status(self):
        """Snapshot for dashboard + multi-symbol aggregation."""
        pos = self.position or {}
        return {
            "symbol":       self.symbol,
            "in_trade":     self.position is not None,
            "side":         pos.get("side"),
            "qty_lots":     pos.get("qty", 0),
            "entry_px":     pos.get("entry_px"),
            "trades_today": self.trades_today,
            "pnl_today":    round(self.pnl_today, 2),
            "kill":         self.kill,
            "soft_halt":    self.soft_halt,
            "max_lots":     self.max_lots,
            "lot_size":     self.lot_size,
            "reasons":      list(self.reasons_log[-10:]),
        }

    def reset_for_new_day(self):
        """Clear daily state. Call at session start (or after EOD)."""
        self.position = None
        self.trades_today = 0
        self.pnl_today = 0.0
        self.kill = False
        self.soft_halt = False
        self.reasons_log = []

    def __repr__(self):
        return f"OuMrsRunner(symbol={self.symbol!r}, lot={self.lot_size}, in_trade={self.position is not None}, pnl={self.pnl_today:.0f})"
