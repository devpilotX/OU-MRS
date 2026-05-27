# Phase 9.8h.K — NF Revival Investigation

**Date:** 2026-05-27  
**Branch:** `phase-9.8h-K-nf-revival`  
**Trigger:** User belief — "in previous only nf performed great and idk i do something with quant algo and mistakely i broke everything. make nf profitable again."

## TL;DR

**NF is not robustly profitable with any tested OU-MRS parameter set on the B.5 NIFTY data window (2026-03-30 → 2026-05-22, 22 baseline trades).** The user's belief that "NF was previously profitable and I broke something" is **not supported by the committed configuration history**: `.env.pre-C1.bak` (the snapshot taken right before NF was disabled in Phase 9.8h.C.1) has the **exact same** strategy parameters (`OU_Z_ENTRY=1.5`, `OU_Z_STOP_NF=2.5`, regime filter `CHOP,RANGE`, vol/ATR filters on, HL 0.5–5.0) as the current `.env`. NF was disabled in C.1 *because* B.5 walk-forward showed it structurally broken with those exact settings (PSR 0.009, 0/6 WF windows positive, profit_factor 0.482, win_rate 22.7%).

A targeted 24-config param sweep was run. The single in-sample winner — **`BT_REGIME_FILTER=TREND` + `OU_PAPER_SL_ATR_MULT=2.5` + `OU_Z_STOP_NF=3.5`** — produced N=7, PnL +₹5,023, win_rate 71.4%, PF 2.33, Sharpe +2.54. However, **walk-forward inside that window already shows decay**: April made +₹6,477, May made -₹1,455. At N=7 the 95% binomial confidence interval on win rate is 29–96%, which is statistically meaningless. **Recommendation: keep NF disabled.** Re-evaluate after 3+ months of new market data with `INSTRUMENTS=BNF,MCN` continuing in paper.

## What the user asked

> "is everything is nf,mnf,bnf all of them?" → asked which symbols active.  
> "in previous only nf is perform great and idk i do something with quant algo and mistakely i broke everything. make nf profitable again." → asked to revive NF.  
> "lets do it." → authorized investigation.

## What we did

### Step 1: Confirmed current state
- `.env` `INSTRUMENTS=BNF,MCN` — NF disabled since Phase 9.8h.C.1.
- C.1 audit (`audit/phase_9_8h_C_1_apply_b5_findings.md`) explicitly says: NF "structurally broken, kept disabled live".
- Rollback path was always documented: set `INSTRUMENTS=BNF,NF,MCN`.

### Step 2: Trade-level forensics on B.5 NIFTY backtest

Loaded `validation/b5_slip{2,5,10,20}_NIFTY/trades.csv` (22 trades each across 4 slippage levels). Key signals:

| Metric | Value | Interpretation |
|---|---|---|
| BUY side n=13, pnl -₹66.5k | SELL side n=9, pnl -₹2.9k (at slip=2) | NF has asymmetric loss profile — BUYs catch falling knives |
| PAPER_SL fires 10–13 / 22 trades | avg -₹11.2k each | Stops are too tight — half of all trades stop out at large loss |
| TIME_STOP_HL exits avg **+₹6,261** | 6 trades | When trades survive their half-life, they're **profitable** |
| TRAIL_STOP: 4 trades, 100% wins | +₹6,704 | The profitable trades aren't being captured proportionally |
| Hour-13 entries: 7 trades, -₹42.7k, 0–14% wr | catastrophic | Afternoon doldrum kills mean-rev |
| Hour-11 entries: 5 trades, +₹15.4k, 60% wr | profitable | Morning trend-resolution-to-range works |
| Cost = 25–29% of gross | high | NIFTY tick 0.05 + slippage assumptions eat the edge |
| CHOP regime: 4 trades, 0% wr, -₹44k | worst | But filtering CHOP doesn't help (see Step 3) |

### Step 3: Param sweep — 24 configs over 3 batches

Used `backtest.py --symbol NIFTY --auto-lot` with env overrides.

**Batch 1 — OU_REGIME_FILTER (turned out to be wrong env var for backtest):**

| Config | N | PnL | Win% | PF | Sharpe |
|---|---|---|---|---|---|
| baseline | 22 | -10,727 | 22.7 | 0.49 | -4.38 |
| OU_PAPER_SL_ATR_MULT=2.5 + OU_Z_STOP_NF=3.5 | 21 | -7,605 | 33.3 | 0.58 | -3.18 |
| + OU_HL_MAX=10 | 23 | -10,523 | 34.8 | 0.55 | -3.29 |
| + OU_Z_ENTRY=2.0 | 21 | -7,605 | 33.3 | 0.58 | -3.18 |
| OU_PAPER_SL_ATR_MULT=3.0 + Z_STOP=4.0 + Z_ENTRY=2.0 + HL_MAX=10 | 23 | -8,937 | 34.8 | 0.59 | -2.91 |

Finding: wider stops cut losses by ~₹3k but all still lose. **Critical bug**: `OU_REGIME_FILTER` is the *live runner* env var; the *backtest* uses `BT_REGIME_FILTER`. So regime-filter configs in this batch were no-ops.

**Batch 2 — `BT_REGIME_FILTER=RANGE` (correct env var):**

| Config | N | PnL | Win% | PF | Sharpe |
|---|---|---|---|---|---|
| baseline | 22 | -10,727 | 22.7 | 0.49 | -4.38 |
| BT_REGIME_FILTER=RANGE | 13 | -12,612 | 7.7 | 0.07 | -5.97 |
| RANGE + wide SL | 12 | -12,883 | 8.3 | 0.07 | -5.93 |
| RANGE + wide SL + longHL | 13 | -17,761 | 7.7 | 0.05 | -6.21 |
| RANGE + huge SL | 13 | -19,315 | 7.7 | 0.04 | -6.19 |
| **BT_REGIME_FILTER=TREND** | **7** | **+2,266** | **57.1** | **1.58** | **+1.45** |

Finding: RANGE-only is **worse** than baseline. The "good" RANGE trades in baseline must be those entered at regime-transition (TREND→RANGE), not at established RANGE. **TREND-only is the only positive config.**

**Batch 3 — variations around TREND winner:**

| Config | N | PnL | Win% | PF | Sharpe |
|---|---|---|---|---|---|
| TREND_only | 7 | +2,266 | 57.1 | 1.58 | +1.45 |
| **TREND + wide SL (PAPER_SL=2.5, Z_STOP=3.5)** | **7** | **+5,023** | **71.4** | **2.33** | **+2.54** |
| TREND + huge SL (3.5 / 4.5) | 7 | +5,023 | 71.4 | 2.33 | +2.54 (identical) |
| TREND + Z_ENTRY=2.0 | 7 | +2,266 | 57.1 | 1.58 | +1.45 |
| TREND + Z_ENTRY=2.0 + wide SL | 7 | +5,023 | 71.4 | 2.33 | +2.54 |
| TREND,RANGE | 20 | -10,346 | 25.0 | 0.41 | -4.03 |
| TREND,RANGE + wide SL | 19 | -7,860 | 31.6 | 0.55 | -2.79 |
| TREND + longHL | 8 | +216 | 50.0 | 1.04 | +0.11 |
| TREND,RANGE + longHL + wideSL | 21 | -15,472 | 28.6 | 0.37 | -4.83 |

Best in-sample: **TREND + wide SL** — PnL +₹5,023, wr 71.4%, PF 2.33, Sharpe +2.54.

### Step 4: Walk-forward / robustness check on the winner

The 7 winning trades in config 22, by entry date:

| # | Entry date | Side | PnL | Reason | Entry regime |
|---|---|---|---|---|---|
| 1 | 2026-04-01 11:34 | SELL | +₹2,644 | TIME_STOP_HL | TREND |
| 2 | 2026-04-16 13:12 | BUY | +₹1,049 | TIME_STOP_HL | TREND |
| 3 | 2026-04-20 12:18 | BUY | +₹1,558 | TARGET | TREND |
| 4 | 2026-04-24 11:54 | BUY | +₹1,227 | TRAIL_STOP | TREND |
| 5 | 2026-05-07 10:10 | BUY | +₹2,326 | TIME_STOP_HL | TREND |
| 6 | 2026-05-11 12:33 | BUY | -₹873 | BE_RATCHET | TREND |
| 7 | 2026-05-13 12:38 | BUY | -₹2,908 | PAPER_SL | TREND |

- **First-half (n=3, all April): +₹5,251, 100% wr**
- **Second-half (n=4, May): -₹228, 50% wr**
- April: +₹6,477. May: -₹1,455. **Edge already decaying within the test window.**
- 6 of 7 trades have exit_regime=CHOP — the regime classifier reclassifies during the trade. The "TREND" filter is filtering at entry-bar regime only.
- Statistical significance: N=7, observed wr 71.4%. Binomial 95% CI ≈ [29.0%, 96.3%]. Lower bound below break-even. **Not statistically distinguishable from noise.**

## Conclusions

1. **The user's premise is incorrect.** Pre-C1 `.env` = current `.env` (verbatim diff on every OU_ knob). Nothing was "broken" by a recent quant-algo change. NF was disabled because B.5 walk-forward showed it broken **with the same params the user remembers as profitable**.
2. **Probable source of user's recollection:** Phase 9.7AQ (Oct 2025) corrected NF lot size from `75→65` per Angel authoritative scrip-master. Before that fix, earlier backtests reporting NF profitability had **inflated PnL** by using a 15% wider lot size. The NF margin requirement also went 50K → 130K per lot in 9.8g.65a-fix1. NF "was profitable" in pre-fix backtest grids that no longer reflect reality.
3. **No robust profitable config exists on the current 2-month window.** The single positive config (TREND + wide SL) is in-sample-only, decays within May, and has CI [29%, 96%] on win rate.
4. **Filtering CHOP at entry does NOT help.** RANGE-only is worse than baseline. Counter-intuitively, what looks like a TREND filter pulls a small handful of trades that happen to be profitable in April but stop being profitable in May.
5. **Mean reversion on NIFTY 1-min bars has no edge in this market**, period. NF tracks 50 large-caps; lower idiosyncratic noise than BNF (12 banks) or MCN (mid-caps) means less mean-reverting wiggle to harvest.

## Recommendation

**Keep NF disabled.** `INSTRUMENTS=BNF,MCN` stays as configured.

**Re-evaluate gate** (Phase 9.8h.L or later):
- Wait 3 months for additional NIFTY data (until ~end Aug 2026).
- Re-run B.5-style walk-forward on the expanded window.
- Accept only if: PSR ≥ 0.50, profit_factor > 1.2, ≥4 of 6 WF windows positive, both train and test halves positive.
- Independent gate: **N ≥ 30 trades** before any live decision.

**If user insists on running NF live anyway** (Sacred Rule #14 override territory): only in **paper mode** (`LIVE=false`, current state), with `OU_NF_REGIME_FILTER=TREND` + `OU_NF_PAPER_SL_ATR_MULT=2.5` + `OU_Z_STOP_NF=3.5`. This needs new per-symbol env knobs in `ou_mrs.py` (the live runner currently has only global `OU_REGIME_FILTER` and `OU_PAPER_SL_ATR_MULT`).

## Not Applied

No `.env` or code changes were committed in this phase. This is a research-only audit.

## Files

- `/tmp/nf_sweep/`, `/tmp/nf_sweep3/`, `/tmp/nf_sweep4/` — 24 backtest output dirs (VPS-local, not committed).
- `/tmp/nf_sweep{2,3,4}.sh` — sweep driver scripts.
- `audit/phase_9_8h_K_nf_revival.md` — this document.
