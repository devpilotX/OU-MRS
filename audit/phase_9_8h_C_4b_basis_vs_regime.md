# Phase 9.8h.C.4.b — Basis-vs-regime control experiment

**Date:** 2026-05-27
**Branch:** phase-9.8h.C.4b-control
**Predecessor:** C.4 (`c7381b7`)

## Question

C.4 ran the strategy on INDEX-mode (137-150 sessions) and saw catastrophic loss
(BNF Sharpe -0.50, MCN Sharpe -3.58). Was that loss caused by:
- **(A) Regime fragility** — strategy fails outside the Mar-May 2026 window, or
- **(B) Basis-effect** — INDEX is not a valid proxy for FUT and the strategy is
  calibrated to FUT-specific price microstructure?

We answer by slicing the C.4 INDEX trades to the same calendar window as the
C.3 FUT backtest and comparing.

## Method

1. Take the C.4 INDEX trades.csv outputs (96 BNF trades, 114 MCN trades).
2. Slice to the FUT calendar window:
   - BANKNIFTY FUT window: 2026-03-30 -> 2026-05-26 (38 sessions)
   - MIDCPNIFTY FUT window: 2026-03-27 -> 2026-05-22 (37 sessions)
3. Recompute Sharpe / PF / total PnL on the sliced subset.
4. Compare to:
   - C.4 full INDEX (no slice)
   - C.3 FUT (same window, FUT data)

Slicer: `tools/c4b_slice.py`. Output: `validation/c4b_basis_vs_regime.json` (gitignored).

## Results

### BANKNIFTY

| Run | Window | Sessions | Trades | Sharpe | PF | PnL (Rs) | PSR |
|---|---|---|---|---|---|---|---|
| C.3 FUT | 2026-03-30 -> 2026-05-26 | 38 | 16 | (positive) | -- | (positive) | 0.837 |
| C.4 INDEX full | 2025-10-01 -> 2026-04-24 | 137 | 96 | -0.524 | 0.919 | -4,449 | 0.376 |
| **C.4.b INDEX sliced to FUT window** | 2026-03-30 -> 2026-05-26 | 26* | **12** | **-2.124** | **0.729** | **-2,835** | n/a |

*INDEX data ends 2026-04-24, so the overlap is 26 sessions, not 38.

### MIDCPNIFTY

| Run | Window | Sessions | Trades | Sharpe | PF | PnL (Rs) | PSR |
|---|---|---|---|---|---|---|---|
| C.3 FUT | 2026-03-27 -> 2026-05-22 | 37 | 15 | (positive) | -- | (positive) | 0.795 |
| C.4 INDEX full | 2025-10-01 -> 2026-05-15 | 151 | 114 | -4.182 | 0.516 | -39,175 | 0.008 |
| **C.4.b INDEX sliced to FUT window** | 2026-03-27 -> 2026-05-22 | 37 | **22** | **-3.212** | **0.595** | **-7,723** | n/a |

## Verdict

**The basis-effect explanation dominates.** On the same calendar window:
- BNF FUT was edge-positive (PSR 0.837) but BNF INDEX over that same window
  is Sharpe -2.12 with a 0.73 profit factor.
- MCN FUT was edge-positive (PSR 0.795) but MCN INDEX over that same window
  is Sharpe -3.21 with a 0.60 profit factor.

Both symbols flip from clear winner to clear loser purely by swapping the
instrument (FUT -> INDEX), holding the calendar fixed. This is not a regime
story. INDEX-vs-FUT basis distorts:
- absolute price level (used by ATR and z-score calculations)
- intraday microstructure (FUT premium/discount drift creates additional
  mean-reverting signal that doesn't exist in INDEX)
- gap behavior at session boundaries

The strategy as currently parameterized is FUT-specific. The C.4 INDEX-mode
result is **not a valid out-of-sample test of strategy edge.**

## Implication for C.5

The C.5 plan must change.
- **Original C.5 plan:** regime-conditional sizing on the INDEX 137-150 day
  window.
- **Revised C.5 plan:** the only way to honestly test regime fragility is on
  **more FUT data**, not on INDEX as a proxy. We need to backfill older
  monthly expiries (Apr 2026, Mar 2026, Feb 2026, Jan 2026, Dec 2025, Nov 2025,
  Oct 2025) via Angel SmartAPI's historical candle endpoint, each with its
  own expiry-specific token.

Until we have 100+ FUT sessions, no PSR claim on this strategy is defensible.
The C.3 FUT PSR of 0.837/0.795 remains the headline result, but it is on a
sample size (16/15 trades) that cannot rule out luck.

## What we still don't know

- Whether the strategy survives the older 2025-Q4 / 2026-Q1 FUT regimes.
- Whether the C.4 INDEX losses would invert if we recalibrated the OU half-life
  and z-thresholds to INDEX-specific microstructure. (This is academic - we
  trade FUT, not INDEX, so we won't do this.)
- Whether NIFTY (no FUT data backfilled either) carries edge.

## Decision

1. C.4.b is a **negative result that retracts the C.4 conclusion**, not a fix.
2. The strategy remains in paper-trading hold.
3. C.5 pivots from "regime gating on INDEX" to "FUT backfill on older expiries".
4. If FUT backfill is feasible, re-run the full validation suite on the
   combined sample. Target PSR >= 0.95 on >100 FUT sessions.
5. If FUT backfill is infeasible (Angel API gates historical token lookups),
   we ship Phase E as "honest negative" and continue paper-trading until
   live conditions accumulate enough trades for a fair PSR test.
