"""Phase 8p.2: tier-policy invariants."""
from tier_policy import get_tier, get_policy, TIER_POLICY


def test_tier_boundaries():
    assert get_tier(100_000)    == "SEED"
    assert get_tier(1_000_000)  == "GROWTH"
    assert get_tier(2_000_000)  == "INSTITUTIONAL"
    assert get_tier(3_750_000)  == "HEDGE_FUND"
    assert get_tier(10_000_000) == "QUANT_ELITE"
    assert get_tier(60_000_000) == "QUANT_ELITE"


def test_policy_keys_complete():
    required = {"max_lots_cap", "risk_per_trade_pct", "daily_loss_cap_pct",
                "max_concurrent_positions", "atr_mult", "z_entry", "z_stop"}
    for tier, pol in TIER_POLICY.items():
        assert required.issubset(pol.keys()), f"{tier} missing keys"


def test_risk_per_trade_decreases_with_capital():
    pcts = [TIER_POLICY[t]["risk_per_trade_pct"] for t in
            ["SEED", "GROWTH", "INSTITUTIONAL", "HEDGE_FUND", "QUANT_ELITE"]]
    assert pcts == sorted(pcts, reverse=True)


def test_daily_loss_cap_decreases_with_capital():
    caps = [TIER_POLICY[t]["daily_loss_cap_pct"] for t in
            ["SEED", "GROWTH", "INSTITUTIONAL", "HEDGE_FUND", "QUANT_ELITE"]]
    assert caps[-1] < caps[0]


def test_concurrency_grows_with_capital():
    assert TIER_POLICY["QUANT_ELITE"]["max_concurrent_positions"] > TIER_POLICY["SEED"]["max_concurrent_positions"]


def test_atr_mult_widens_with_capital():
    mults = [TIER_POLICY[t]["atr_mult"] for t in
             ["SEED", "GROWTH", "INSTITUTIONAL", "HEDGE_FUND", "QUANT_ELITE"]]
    assert mults == sorted(mults)


def test_z_entry_lowers_with_capital():
    assert TIER_POLICY["QUANT_ELITE"]["z_entry"] < TIER_POLICY["SEED"]["z_entry"]


def test_get_policy_returns_tier_and_dict():
    tier, pol = get_policy(3_750_000)
    assert tier == "HEDGE_FUND"
    assert pol["atr_mult"] == 1.7
    pol["atr_mult"] = 999
    _, pol2 = get_policy(3_750_000)
    assert pol2["atr_mult"] == 1.7
