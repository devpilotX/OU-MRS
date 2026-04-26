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
        self.atr_mult = self.cfg.get("atr_mult", 1.5)

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
