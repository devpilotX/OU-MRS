# Phase 9.8h.I (OC-7' v0) — post-trade slippage reconciliation

**Generated:** 2026-05-27T12:49:42
**Sample size:** 22 trades

> **INSUFFICIENT_SAMPLE**: need n ≥ 30 for stable slippage estimates; current n = 22. Estimates below are provisional and should not yet drive cost-model changes.

## Summary stats (total slippage per round-trip, points)

- Mean: +0.0000 pts
- Median: +0.0000 pts
- Std dev: 0.0000 pts
- Best (most favorable): -0.0000 pts
- Worst (most adverse): -0.0000 pts

## Per-trade detail

| Entry IST | Sym | Side | Qty | Entry | Exit | P&L ₹ | Reason | Slip→ entry | Slip→ exit | Slip→ total |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-28 14:42:00+05:30 | BNF | SELL | 28 | 55912.0 | 55716.2 | +164432 | EOD | +0.000 | -0.000 | **-0.000** |
| 2026-04-29 11:24:00+05:30 | BNF | SELL | 36 | 56299.8 | 56250.0 | +53744 | Z_VEL_STALL | +0.000 | +0.000 | **+0.000** |
| 2026-04-29 11:03:00+05:30 | NF | SELL | 34 | 24403.0 | 24441.0 | -84020 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-04-29 12:13:00+05:30 | BNF | SELL | 37 | 56299.2 | 56479.4 | -200062 | KILL | +0.000 | +0.000 | **+0.000** |
| 2026-04-30 11:36:00+05:30 | BNF | SELL | 32 | 54843.6 | 54830.0 | +13016 | Z_VEL_STALL | +0.000 | +0.000 | **+0.000** |
| 2026-04-30 14:40:00+05:30 | NF | SELL | 27 | 24125.7 | 24092.7 | +57875 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-04 13:22:00+05:30 | NF | BUY | 29 | 24161.9 | 24170.0 | +15228 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-05 14:10:00+05:30 | BNF | BUY | 27 | 54910.2 | 55038.0 | +103478 | TARGET | -0.000 | +0.000 | **-0.000** |
| 2026-05-08 13:28:00+05:30 | NF | SELL | 36 | 24220.0 | 24200.0 | +46760 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-11 10:20:00+05:30 | NF | BUY | 30 | 23881.4 | 23927.0 | +79909 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-11 12:32:00+05:30 | NF | BUY | 36 | 23941.0 | 23968.6 | +53760 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-11 12:33:00+05:30 | BNF | BUY | 38 | 54849.0 | 54988.0 | +146371 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-12 11:57:00+05:30 | NF | SELL | 34 | 23649.6 | 23628.0 | +37645 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-12 12:29:00+05:30 | BNF | BUY | 29 | 53979.4 | 53760.2 | -199749 | Z_VEL_STALL | +0.000 | +0.000 | **+0.000** |
| 2026-05-12 13:19:00+05:30 | NF | SELL | 36 | 23597.3 | 23579.0 | +32164 | Z_VEL_STALL | +0.000 | +0.000 | **+0.000** |
| 2026-05-14 13:03:00+05:30 | NF | SELL | 28 | 23748.9 | 23753.5 | -16727 | Z_VEL_STALL | +0.000 | +0.000 | **+0.000** |
| 2026-05-19 12:46:00+05:30 | BNF | BUY | 48 | 53718.0 | 53706.8 | -31040 | Z_VEL_STALL | +0.000 | +0.000 | **+0.000** |
| 2026-05-20 10:26:00+05:30 | MCN | BUY | 16 | 14196.1 | 14242.0 | +82829 | TARGET | +0.000 | +0.000 | **+0.000** |
| 2026-05-20 14:03:00+05:30 | MCN | SELL | 16 | 14321.2 | 14398.0 | -152794 | EOD | +0.000 | +0.000 | **+0.000** |
| 2026-05-21 12:15:00+05:30 | NF | BUY | 28 | 23681.7 | 23690.0 | +6773 | TIME_STOP_HL | +0.000 | +0.000 | **+0.000** |
| 2026-05-22 12:51:00+05:30 | MCN | SELL | 6 | 14404.05 | 14398.55 | +1920 | Z_VEL_STALL | +0.000 | -0.000 | **+0.000** |
| 2026-05-25 14:28:00+05:30 | NF | SELL | 6 | 23993.5 | 24058.6 | -27236 | EOD | +0.000 | -0.000 | **-0.000** |

## Methodology

- Tick size assumed: 0.05 points (Nifty/BankNifty/MidCpNifty futures).
- Mid proxy: `round(price / tick) * tick`. This is a coarse approximation when no depth snapshot was recorded at fill time; the true mid would require the L1 bid/ask at the fill millisecond.
- Signed convention: positive slip = trade got a BETTER fill than the proxy mid; negative = worse.
- This v0 does NOT yet reconcile against the C.2/C.3 estimator (`estimate_slippage_ticks`, `estimate_gap_slippage_ticks`) because those are backtest-only and gated by OU_COST_MODEL_V2. A v1 will add that comparison once n >= 30.

## Next milestone

- Re-run after each new trade close.
- Promote to v1 (estimator-vs-actual delta) at n ≥ 30.
