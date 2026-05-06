"""
Phase 9.5: Adaptive sizing module.
Phase 9.5a: drawdown/cushion math + adaptive_size_lots IMPLEMENTED.
NOT WIRED to ou_mrs.py. Imported only by tests and tools/.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class TierPolicy:
    name: str
    capital_min: float
    capital_max: float
    max_lots_total: int
    max_risk_per_trade_pct: float
    max_daily_loss_pct: float
    hard_floor_pct: float

TIERS = [
    TierPolicy("Tier 0 paper",  0.0,           50_000.0,        50, 1.5,  2.0,  80.0),
    TierPolicy("Tier 1",        50_000.0,      2_00_000.0,      20, 1.0,  1.5,  85.0),
    TierPolicy("Tier 2",        2_00_000.0,    10_00_000.0,     35, 1.0,  1.5,  85.0),
    TierPolicy("Tier 3",        10_00_000.0,   50_00_000.0,     50, 0.75, 1.0,  88.0),
    TierPolicy("Tier 4",        50_00_000.0,   2_00_00_000.0,   75, 0.5,  0.75, 90.0),
    TierPolicy("Tier 5",        2_00_00_000.0, 1e12,           100, 0.4,  0.5,  92.0),
]

def get_tier(capital: float) -> TierPolicy:
    """Map capital amount to its policy tier."""
    for t in TIERS:
        if t.capital_min <= capital < t.capital_max:
            return t
    return TIERS[-1]

def compute_drawdown_pct(current_equity: float, peak_equity: float) -> float:
    """Current drawdown as positive percent of peak. 0.0 if at/above peak."""
    if peak_equity <= 0:
        return 0.0
    if current_equity >= peak_equity:
        return 0.0
    return ((peak_equity - current_equity) / peak_equity) * 100.0

def compute_cushion(current_equity: float, hard_floor: float) -> float:
    """Distance above hard floor as percent of floor. Negative if below."""
    if hard_floor <= 0:
        return 0.0
    return ((current_equity - hard_floor) / hard_floor) * 100.0

def adaptive_size_lots(
    base_lots: int,
    dd_pct: float,
    cushion_pct: float,
    regime: str = "RANGE",
    vol_percentile: float = 50.0,
) -> int:
    """
    Adjust base lot size by current risk environment.
    Multipliers (multiplied together):
      regime:      CHOP=1.0, RANGE=0.80, TREND=0.0 (defense in depth)
      drawdown:    linear taper, 1.0 at 0% DD, 0.0 at 10% DD
      cushion:     <5%=0.25, <10%=0.50, <20%=0.75, >=20%=1.0
      vol pct:     >=80=0.50, <=20=1.20, else 1.0
    Hard cuts:
      regime==TREND -> 0
      dd_pct >= 10  -> 0
    Returns int in [0, base_lots*2].
    """
    if regime == "TREND":
        return 0
    if dd_pct >= 10.0:
        return 0
    dd_mult = max(0.0, 1.0 - (dd_pct / 10.0))
    if cushion_pct < 5.0:
        cushion_mult = 0.25
    elif cushion_pct < 10.0:
        cushion_mult = 0.50
    elif cushion_pct < 20.0:
        cushion_mult = 0.75
    else:
        cushion_mult = 1.0
    regime_mult = {"CHOP": 1.0, "RANGE": 0.80, "TREND": 0.0}.get(regime, 0.50)
    if vol_percentile >= 80.0:
        vol_mult = 0.50
    elif vol_percentile <= 20.0:
        vol_mult = 1.20
    else:
        vol_mult = 1.0
    final = base_lots * dd_mult * cushion_mult * regime_mult * vol_mult
    return max(0, min(int(round(final)), base_lots * 2))

if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("TIER LADDER")
    print(bar)
    for t in TIERS:
        print(f"  {t.name:14s} cap=[{t.capital_min:>13,.0f}, {t.capital_max:>15,.0f})  "
              f"lots={t.max_lots_total:3d}  risk={t.max_risk_per_trade_pct}%  "
              f"DDL={t.max_daily_loss_pct}%  floor={t.hard_floor_pct}%")
    print(bar)
    print("SMOKE TESTS (Phase 9.5a)")
    print(bar)

    # compute_drawdown_pct
    assert compute_drawdown_pct(100.0, 100.0) == 0.0
    assert compute_drawdown_pct(110.0, 100.0) == 0.0
    assert abs(compute_drawdown_pct(95.0, 100.0) - 5.0) < 1e-9
    assert abs(compute_drawdown_pct(80.0, 100.0) - 20.0) < 1e-9
    assert compute_drawdown_pct(0.0, 0.0) == 0.0
    print("  compute_drawdown_pct .................. PASS (5 cases)")

    # compute_cushion
    assert abs(compute_cushion(100.0, 80.0) - 25.0) < 1e-9
    assert abs(compute_cushion(80.0, 80.0) - 0.0) < 1e-9
    assert compute_cushion(70.0, 80.0) < 0.0
    assert compute_cushion(100.0, 0.0) == 0.0
    print("  compute_cushion ....................... PASS (4 cases)")

    # adaptive_size_lots
    assert adaptive_size_lots(10, 0, 25, "CHOP", 50) == 10,  "full CHOP"
    assert adaptive_size_lots(10, 0, 25, "RANGE", 50) == 8,  "RANGE 80%"
    assert adaptive_size_lots(10, 0, 25, "TREND", 50) == 0,  "TREND blocked"
    assert adaptive_size_lots(10, 10, 25, "CHOP", 50) == 0,  "DD >= 10% zeroed"
    assert adaptive_size_lots(10, 5,  25, "CHOP", 50) == 5,  "DD 5% halves"
    assert adaptive_size_lots(10, 0,  3,  "CHOP", 50) == 2,  "cushion <5% to 25%"
    assert adaptive_size_lots(10, 0, 25, "CHOP", 90) == 5,   "high vol halves"
    assert adaptive_size_lots(10, 0, 25, "CHOP", 10) == 12,  "low vol +20%"
    assert adaptive_size_lots(10, 5, 15, "RANGE", 85) == 1,  "stacked penalties"
    print("  adaptive_size_lots .................... PASS (9 cases)")

    # Tier mapping spot checks
    assert get_tier(0).name == "Tier 0 paper"
    assert get_tier(75_000).name == "Tier 1"
    assert get_tier(5_00_000).name == "Tier 2"
    assert get_tier(25_00_000).name == "Tier 3"
    assert get_tier(1_00_00_000).name == "Tier 4"
    assert get_tier(3_00_00_000).name == "Tier 5"
    print("  get_tier .............................. PASS (6 cases)")

    print(bar)
    print("Phase 9.5a OK. 24 assertions passed. NOT WIRED to ou_mrs.py.")
    print(bar)
