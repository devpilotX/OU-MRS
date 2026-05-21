"""Phase 8g.2.a: OuMrsRunner — per-symbol state container.

Owns per-symbol state for OU-MRS strategy. Step 2.b will integrate
process_bar() into main(); Step 4 instantiates one runner per active
symbol in INSTRUMENTS for multi-instrument orchestration.
"""


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
        # convenience accessors from cfg
        self.lot_size = self.cfg.get("lot_size", lot_size_default)
        self.token = self.cfg.get("token")
        self.exchange = self.cfg.get("exchange", "NFO")
        self.symbol_full = self.cfg.get("symbol")
        self.margin_per_lot = self.cfg.get("margin_per_lot", 75_000)
        # Phase 9.7AO: OU_ATR_MULT env override > cfg > default
        import os as _os_p97ao
        _atr_mult_env = _os_p97ao.environ.get("OU_ATR_MULT")
        self.atr_mult = float(_atr_mult_env) if _atr_mult_env else self.cfg.get("atr_mult", 1.5)
        # Phase 8g.4.a: per-symbol max lots from capital and margin_per_lot
        # Phase 9.7AL.1 (21 May 2026): dual-cap = min(margin_cap, notional_cap @ 3x leverage)
        import os as _os_p97al1
        _nlm = float(_os_p97al1.environ.get("NOTIONAL_LEVERAGE_MAX", 3.0))
        _approx_spot = {"BNF": 53_500.0, "NF": 24_800.0, "MCN": 14_300.0, "SENSEX": 80_000.0}
        _lot_nse     = {"BNF": 30,       "NF": 75,       "MCN": 120,      "SENSEX": 10}
        _spot  = _approx_spot.get(self.symbol, self.cfg.get("approx_spot", 50_000.0))
        _lsize = _lot_nse.get(self.symbol, self.lot_size)
        _margin_cap   = max(1, int(self.capital // self.margin_per_lot))
        _notional_cap = max(1, int((self.capital * _nlm) // (_spot * _lsize)))
        self.max_lots = min(_margin_cap, _notional_cap)

    def status(self):
        """Snapshot for dashboard + multi-symbol aggregation."""
        pos = self.position or {}
        return {
            "symbol": self.symbol,
            "in_trade": self.position is not None,
            "side": pos.get("side"),
            "qty_lots": pos.get("qty", 0),
            "entry_px": pos.get("entry_px"),
            "trades_today": self.trades_today,
            "pnl_today": round(self.pnl_today, 2),
            "kill": self.kill,
            "soft_halt": self.soft_halt,
            "max_lots": self.max_lots,
            "reasons": list(self.reasons_log[-10:]),
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
        return f"OuMrsRunner(symbol={self.symbol!r}, in_trade={self.position is not None}, pnl={self.pnl_today:.0f})"
