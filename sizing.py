"""Phase 9.5 Capital-Adaptive Sizing Engine DESIGN DOC PLUS STUBS.

Tier ladder plus fractional Kelly plus drawdown throttling plus cushion expansion.
Status: DESIGN ONLY. Not yet wired. ou_mrs.py still uses size_lots from strategy.py.
Activation gate: family money requires Phase 9.9 (6 months live plus 3 months profitable).

Author: Phase 9.5 designed Tue 5 May 2026 evening
"""
from dataclasses import dataclass
from typing import List

@dataclass
class TierPolicy:
    name: str
    capital_min: float
    capital_max: float
    max_lots_bnf: int
    risk_per_trade_pct: float
    daily_soft_halt_pct: float
    daily_hard_halt_pct: float
    atr_stop_mult: float

TIERS: List[TierPolicy] = [
    TierPolicy("TINY", 0.0, 200000.0, 1, 0.015, 0.020, 0.040, 1.5),
    TierPolicy("PAPER", 200000.0, 1500000.0, 5, 0.010, 0.015, 0.030, 1.5),
    TierPolicy("STARTER", 1500000.0, 2500000.0, 10, 0.007, 0.010, 0.040, 1.6),
    TierPolicy("PRO", 2500000.0, 5000000.0, 20, 0.006, 0.008, 0.050, 1.6),
    TierPolicy("HEDGE_FUND", 5000000.0, float("inf"), 50, 0.005, 0.008, 0.060, 1.7),
]

def get_tier(capital):
    for tier in TIERS:
        if tier.capital_min <= capital < tier.capital_max:
            return tier
    return TIERS[-1]

def adaptive_size_lots(atr, capital, symbol, drawdown_pct=0.0, cushion=0.0):
    raise NotImplementedError("Phase 9.5: adaptive sizing pending")

def compute_drawdown_pct(equity_history):
    raise NotImplementedError("Phase 9.5: helper pending")

def compute_cushion(current_equity, monthly_target):
    raise NotImplementedError("Phase 9.5: helper pending")

if __name__ == "__main__":
    print("Phase 9.5 sizing engine loaded. Status: DESIGN ONLY, not wired.")
    for t in TIERS:
        cm = "inf" if t.capital_max == float("inf") else f"{t.capital_max:>12,.0f}"
        print(f"  {t.name:12s}  cap={t.capital_min:>12,.0f} to {cm}  risk={t.risk_per_trade_pct:.1%}  max_bnf={t.max_lots_bnf}")
