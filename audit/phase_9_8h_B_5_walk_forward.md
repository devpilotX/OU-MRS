# Phase 9.8h.B.5 — Walk-forward backtest, slippage sensitivity, vol-regime stratification

**Branch:** `phase-9.8h.B.5-walk-forward`  •  **Phase:** 9.8h.B.5  •  **Date:** 2026-05-27 IST

## Executive summary (the brutal truth)

Across a 39-trading-day sample (30 Mar – 26 May 2026) on minute-bar futures data, the current armor stack (Phase 9.7AQ live config: `OU_ADX=32`, `OU_Z_ENTRY=1.5`, `OU_Z_STOP=2.5`, `OU_VOL_CONFIRM=on`, `OU_ATR_PCT_FILTER=on`, `OU_HL=[0.5, 5.0]`, `OU_REGIME_FILTER=CHOP,RANGE`) **fails all six Phase 9.8h acceptance criteria on all three symbols**. Live P&L is statistically indistinguishable from noise at this sample size.

| Symbol | PSR@0 ≥0.95 | DSR_N20 ≥0.50 | WF cons ≥0.60 | WF stab ≤1.50 | Ljung-Box ≥0.05 | Holdout same-sign | Verdict |
|--------|-------------|---------------|----------------|----------------|------------------|---------------------|---------|
| BANKNIFTY  | 0.510 ✗ | 0.030 ✗ | 0.667 ✓ | **6.057 ✗** | 0.573 ✓ | False ✗ | **FAIL** |
| NIFTY      | **0.009 ✗** | 0.000 ✗ | **0.000 ✗** | 0.331 ✓ | 0.614 ✓ | True ✓ | **FAIL** |
| MIDCPNIFTY | 0.637 ✗ | 0.041 ✗ | 1.000 ✓ | 0.000 ✓ | 0.719 ✓ | False ✗ | **FAIL** |

Key reads:
- **NIFTY is structurally broken**: P(true Sharpe > 0) = **0.9%** with 0% walk-forward consistency. Should be disabled in production until re-tuned.
- **BANKNIFTY is unstable**: walk-forward stability (CV of SR) = 6.06 against a ≤1.50 floor — edge does not persist across rolling windows.
- **MIDCPNIFTY is the strongest**: 100% walk-forward consistency, but PSR 0.64 (below 0.95) and DSR 0.04 mean the sample is too small to claim significance after multiple-testing correction.

## 1. Slippage sensitivity sweep

Sweep ran 12 backtests = 4 slippage levels × 3 symbols. Slippage applied symmetrically on entry (NEXT bar open + N ticks) and exit (NEXT bar open − N ticks). 1 tick = ₹0.05.

| Symbol | 2 ticks (₹0.10) | 5 ticks (₹0.25) | 10 ticks (₹0.50) | 20 ticks (₹1.00) | Δ P&L (2→20) |
|--------|------------------|------------------|-------------------|-------------------|----------------|
| BANKNIFTY  | +₹19,802 / Sh 0.73 / PF 1.16 | +₹8,903 / Sh 0.31 / PF 1.07 | +₹6,488 / Sh 0.23 / PF 1.05 | +₹1,659 / Sh 0.06 / PF 1.01 | **−92%** |
| NIFTY      | −₹69,430 / Sh −5.36 / PF 0.42 | −₹72,004 / Sh −5.53 / PF 0.41 | −₹103,127 / Sh −6.37 / PF 0.21 | −₹112,370 / Sh −6.62 / PF 0.22 | **−62%** (worse) |
| MIDCPNIFTY | +₹38,699 / Sh 1.68 / PF 1.89 | +₹35,459 / Sh 1.54 / PF 1.79 | +₹30,995 / Sh 1.34 / PF 1.66 | +₹20,196 / Sh 0.88 / PF 1.39 | **−48%** |

Observations:
- Trade counts are invariant across slippage (23 / 22 / 15) because slippage doesn't change entry/exit logic, only fill price.
- **BANKNIFTY edge collapses fast under realistic Indian futures slippage** (10 ticks ≈ ₹0.50/side is a fair median for BNF FUT during the 09:15–15:30 IST window). PF drops to 1.05.
- **NIFTY is unprofitable at every level tested**, including the floor of 2 ticks. Slippage is not the problem — strategy structure is.
- **MIDCPNIFTY is the only symbol with material slippage cushion**: PF stays >1.39 even at ₹1.00/side, sharpe stays positive.

Production implication: at the live default of 2 ticks the backtest overstates costs vs. paper-trading reality (where SLs fire on bar-close), but understates costs vs. live execution slippage in MCN (less liquid). The fair planning number is **slip=10 ticks**.

## 2. Vol-regime stratification

Realized vol = 20-bar log-return std × √375 (annualized to a 375-min trading day) of the underlying futures, sampled at each trade's entry timestamp. Trades bucketed by tercile of in-sample realized vol.

### BANKNIFTY — bimodal edge

| Bucket | rv20 range | n | Mean P&L | Win rate | Per-trade Sharpe |
|--------|------------|---|----------|----------|--------------------|
| LOW    | 0.0057–0.0075 | 8 | **+₹2,523** | 62.5% | +0.34 |
| MID    | 0.0077–0.0092 | 7 | **−₹3,642** | 28.6% | −0.27 |
| HIGH   | 0.0096–0.0142 | 8 | **+₹3,139** | 62.5% | +0.17 |

**Mid-vol = chop trap.** Edge works at vol extremes (low → clean mean-reversion, high → wide reversion targets) but fails in the middle band where price action is neither stable enough for clean Z reversion nor volatile enough for big targets. A vol-band filter `rv20 ∉ [0.0077, 0.0092]` is the highest-leverage filter improvement on BNF.

### NIFTY — broken across all vol regimes

| Bucket | rv20 range | n | Mean P&L | Win rate | Per-trade Sharpe |
|--------|------------|---|----------|----------|--------------------|
| LOW    | 0.0044–0.0062 | 8 | −₹3,556 | 37.5% | −0.43 |
| MID    | 0.0064–0.0076 | 7 | −₹4,068 | 14.3% | −0.41 |
| HIGH   | 0.0082–0.0096 | 7 | −₹1,787 | 42.9% | −0.16 |

All three buckets losing. NIFTY edge does not exist in this sample. The hypothesis that NIFTY is just "high-vol-only" or "low-vol-only" is rejected — every regime loses money.

### MIDCPNIFTY — low-vol concentration

| Bucket | rv20 range | n | Mean P&L | Win rate | Per-trade Sharpe |
|--------|------------|---|----------|----------|--------------------|
| LOW    | 0.0052–0.0074 | 5 | **+₹2,632** | **100%** | **+3.13** |
| MID    | 0.0074–0.0094 | 5 | −₹2,287 | 40% | −0.29 |
| HIGH   | 0.0096–0.0149 | 5 | +₹7,395 | 40% | +0.27 |

The LOW-vol bucket on MCN is **5/5 wins, per-trade Sharpe 3.13** — concentrated, clean edge. HIGH-vol is positive but driven by a single +₹37k outlier. MID-vol is a chop trap (mirroring BNF). Adding `rv20 < 0.0074` filter for MCN trims to 5 trades with a near-pristine Sharpe.

## 3. Walk-forward decomposition (slip=2, rolling W=15 windows)

- **BANKNIFTY**: 4/6 windows positive (consistency 0.667 ✓) but CV(SR) = 6.06 across windows (stab >> 1.50 ✗). Edge exists but is non-stationary.
- **NIFTY**: 0/6 windows positive (0% consistency ✗). Stable in its losing — sharpe is consistently bad, not chaotically bad.
- **MIDCPNIFTY**: 6/6 windows positive (100% consistency ✓) with stability 0.00 (deterministic SR sign). Best walk-forward profile.

## 4. PSR / DSR (Bailey–López de Prado)

PSR at threshold 0 = P(true annualized Sharpe > 0 | observed Sharpe, skew, kurtosis, n). DSR_N20 = PSR deflated for N=20 implicit trial Sharpes (Phase 9.7 sweep grid plus armor-stack tuning trials).

| Symbol | n trades | PSR@0 | DSR_N10 | DSR_N20 |
|--------|----------|-------|---------|---------|
| BANKNIFTY  | 23 | 0.510 | 0.097 | 0.030 |
| NIFTY      | 22 | 0.009 | 0.000 | 0.000 |
| MIDCPNIFTY | 15 | 0.637 | 0.130 | 0.041 |

Even MIDCPNIFTY — the strongest leg — has only a 4.1% chance of beating the deflated zero-Sharpe null after 20-trial correction. This is the multiple-testing tax: we have not run 1 strategy, we have run many config variants, and the in-sample winner shrinks accordingly.

## 5. Hold-out (24-day train / 13-day test split)

- **BANKNIFTY**: train SR > 0, test SR < 0 → same_sign = False. Train edge does not generalize.
- **NIFTY**: train SR < 0, test SR < 0 → same_sign = True (consistently losing).
- **MIDCPNIFTY**: train SR > 0, test SR < 0 → same_sign = False. Best-leg edge also does not generalize out-of-sample.

This is the most actionable warning: **all three symbols show train/test sign breakage** (NIFTY in the wrong direction, BNF and MCN can't carry the edge forward).

## 6. Ljung–Box (lag 5) — IID check on trade P&L

- BANKNIFTY: p=0.573 ✓ (can't reject IID)
- NIFTY:     p=0.614 ✓
- MIDCPNIFTY: p=0.719 ✓

All three pass — trade outcomes look serially uncorrelated, so no streak-driven structure to exploit (or to compensate for).

## 7. Root-cause: why does the sample fail?

Three contributing factors:

1. **Sample size**. 23 / 22 / 15 trades over 39 days is too thin to clear PSR ≥ 0.95. Even a Sharpe of 2.0 on n=15 yields a PSR around 0.85, not 0.95. The acceptance gate is doing its job: it refuses to certify a small sample.
2. **NIFTY structural break**. Edge does not exist in any vol regime on this sample. Either the chosen parameters are wrong for NF, or NF mean-reversion edge has actually decayed. Phase 9.7AQ reverted NF lot to 65, but the underlying signal quality is the problem, not sizing.
3. **BNF instability**. Walk-forward CV(SR) = 6.06 says: the average is fine, but the dispersion is huge. Per-window Sharpe oscillates between deeply positive and deeply negative depending on which 15-trade window you slice.

## 8. Recommended next-phase actions (Phase C inputs)

1. **Disable NIFTY in production** until a focused NF re-tune. Concrete proposal: drop NF from `OU_SYMBOLS` until backtest shows PSR ≥ 0.80 on a per-symbol pilot. Net live impact: NF contributed ~₹110k of loss in the backtest, the cumulative live P&L of ₹1.84L is therefore likely a BNF + MCN result that NF is dragging down.
2. **Add vol-band filter on BANKNIFTY**: skip new entries when `rv20 ∈ [0.0077, 0.0092]`. Re-run validation; expected: BNF moves from PSR 0.51 to 0.75+ on the same sample.
3. **Add `rv20 < tercile_break` accelerator on MIDCPNIFTY**: opportunistically scale up sizing in the LOW-vol bucket where the per-trade Sharpe is 3.13. Note: requires re-validating drawdown.
4. **Extend the data window**. Per PSR sample-size math, ~60 trades per symbol is the minimum for PSR @ Sh=2 to clear 0.95. Backfill another 30 trading days of minute data (Mar 2026 ←) and re-run.
5. **Regime-conflict force-exit experiment** (deferred to Phase C): test what happens if `_exit()` fires when regime transitions out of CHOP/RANGE mid-trade. Preliminary intuition from the LOW-vol concentration on MCN: regime conflict is already implicitly handled by the entry filter.

## 9. Permanent deliverables shipped with B.5

- `backtest.py`: SLIPPAGE_TICKS made env-driven (`BT_SLIPPAGE_TICKS`, default 2). Enables CI sensitivity sweeps without code edits.
- `tools/slippage_sweep.py`: orchestrates the 4×3 sensitivity matrix and the vol-regime stratification. Idempotent, reads `bt_out_<sym>/{trades,equity}.csv`, writes `validation/phase_9_8h_B_5_*.json`.
- `tests/test_phase_9_8h_b5_walk_forward.py`: 4 regression tests that lock the B.5 quantitative findings (slippage sensitivity sign, vol-regime tercile structure, NIFTY no-edge, run_validation_suite acceptance schema).
- `validation/phase_9_8h_B_5_slippage_sweep.json` and `validation/phase_9_8h_B_5_vol_regime.json`: raw matrices, regeneratable.
- This forensic doc.

## 10. Reproduction recipe

```bash
cd /home/ubuntu/bots/ou-mrs
set -a; . .env; set +a
./venv/bin/python tools/slippage_sweep.py
./venv/bin/python tools/run_validation_suite.py --skip-backtest
```

First command takes ~3 minutes (12 backtests). Second takes ~30 seconds (reuses bt_out_*).

Expected output: `0/3 symbols PASS all 6 acceptance checks` (the brutal truth).
