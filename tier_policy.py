"""Phase 8p.2: Tier-aware parameter regime for OU-MRS.

Auto-scales risk, sizing, and entry parameters by capital tier.
Institutional pattern: as capital grows, risk % per trade SHRINKS,
concurrency GROWS, stops WIDEN, and entry threshold LOWERS
(Law of Large Numbers smooths variance across more concurrent trades).
"""
from __future__ import annotations


def get_tier(capital: int) -> str:
    """Capital (Rs) -> tier name. Boundaries match ou_mrs.capital_tier exactly."""
    if capital < 200_000:    return "SEED"
    if capital < 1_500_000:  return "GROWTH"
    if capital < 2_500_000:  return "INSTITUTIONAL"
    if capital < 5_000_000:  return "HEDGE_FUND"
    return "QUANT_ELITE"


TIER_POLICY = {
    "SEED": {
        "max_lots_cap": 2,
        "risk_per_trade_pct": 0.010,
        "daily_loss_cap_pct": 0.015,
        "max_concurrent_positions": 1,
        "atr_mult": 1.5,
        "z_entry": 1.5,
        "z_stop": 3.5,
    },
    "GROWTH": {
        "max_lots_cap": 50,
        "risk_per_trade_pct": 0.008,
        "daily_loss_cap_pct": 0.015,
        "max_concurrent_positions": 2,
        "atr_mult": 1.5,
        "z_entry": 1.5,
        "z_stop": 3.5,
    },
    "INSTITUTIONAL": {
        "max_lots_cap": 50,
        "risk_per_trade_pct": 0.006,
        "daily_loss_cap_pct": 0.012,
        "max_concurrent_positions": 3,
        "atr_mult": 1.6,
        "z_entry": 1.4,
        "z_stop": 3.5,
    },
    "HEDGE_FUND": {
        "max_lots_cap": 50,
        "risk_per_trade_pct": 0.005,
        "daily_loss_cap_pct": 0.008,
        "max_concurrent_positions": 3,
        "atr_mult": 1.7,
        "z_entry": 1.4,
        "z_stop": 3.5,
    },
    "QUANT_ELITE": {
        "max_lots_cap": 50,
        "risk_per_trade_pct": 0.004,
        "daily_loss_cap_pct": 0.006,
        "max_concurrent_positions": 3,
        "atr_mult": 1.8,
        "z_entry": 1.3,
        "z_stop": 3.5,
    },
}


def get_policy(capital: int):
    """Returns (tier_name, policy_dict_copy)."""
    tier = get_tier(capital)
    return tier, TIER_POLICY[tier].copy()
