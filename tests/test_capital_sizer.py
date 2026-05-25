"""Capital sizing tests.

Phase 9.8g.9 (25 May 2026 audit Track 1): updated for 9.7AL.1 dual-cap math.
The old hardcoded 50-lot cap is gone; max_lots is now:

    max_lots = min(margin_cap, notional_cap)

where notional_cap = floor(capital * NOTIONAL_LEVERAGE_MAX / (spot * lot_size)),
with NOTIONAL_LEVERAGE_MAX = 3.0x. BNF approx_spot = 53,500. NF = 24,800.
Result is floored at 1 lot regardless.

These tests pin the live VPS sizing math (HEDGE_FUND tier @ Rs 37.5L) plus a
few invariants that survive future spot drift.
"""


def test_capital_tiers():
    from ou_mrs import capital_tier
    assert capital_tier(150_000)    == "SEED"
    assert capital_tier(1_000_000)  == "GROWTH"
    assert capital_tier(2_000_000)  == "INSTITUTIONAL"
    assert capital_tier(3_000_000)  == "HEDGE_FUND"
    assert capital_tier(10_000_000) == "QUANT_ELITE"


def test_max_lots_floor_at_one():
    """max_lots must never drop below 1, even at tiny capital."""
    from ou_mrs import max_lots_for_capital
    assert max_lots_for_capital(50_000, "BNF") == 1
    assert max_lots_for_capital(150_000, "BNF") == 1
    assert max_lots_for_capital(150_000, "NF") == 1


def test_max_lots_scales_with_capital():
    """More capital -> more lots (monotone non-decreasing)."""
    from ou_mrs import max_lots_for_capital
    seed = max_lots_for_capital(150_000, "BNF")
    growth = max_lots_for_capital(1_000_000, "BNF")
    hedge = max_lots_for_capital(3_750_000, "BNF")  # live VPS HEDGE_FUND
    assert seed >= 1
    assert growth >= seed
    assert hedge >= growth
    # Live config (Rs 37.5L HEDGE_FUND BNF) must allow at least 5 lots.
    assert hedge >= 5


def test_max_lots_dual_cap_at_1_5L_capital():
    """Phase 9.7AL.1: at Rs 15L BNF the notional cap binds (not the margin cap).

    margin_cap   = 1,500,000 // 75,000      = 20
    notional_cap = floor((1.5M * 3) / (53,500 * 30))
                 = floor(4,500,000 / 1,605,000)
                 = 2
    max_lots     = min(20, 2)               = 2
    """
    from ou_mrs import max_lots_for_capital
    assert max_lots_for_capital(1_500_000, "BNF") == 2


def test_max_lots_live_vps_hedge_fund():
    """Pin the exact live VPS dual-cap result @ Rs 37.5L BNF.

    margin_cap   = 3,750,000 // 75,000     = 50
    notional_cap = floor((3.75M * 3) / (53,500 * 30))
                 = floor(11,250,000 / 1,605,000)
                 = 7
    max_lots     = min(50, 7)              = 7
    """
    from ou_mrs import max_lots_for_capital
    assert max_lots_for_capital(3_750_000, "BNF") == 7
