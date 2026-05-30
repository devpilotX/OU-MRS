# Phase 9.8h.N — NIFTY root-cause diagnostic + asymmetric z-entry infra

**Date:** 2026-05-28 IST
**Branch:** `phase-9.8h-K-nf-revival`
**Trigger:** User: *"make nifty profit. check very ddeply whats the issue."* (2026-05-28 03:13 IST)

## TL;DR
- Diagnostic complete: NIFTY long-side is structurally broken in the L-deep BT window (Mar 30–May 26, 22 trades).
- Smoking gun: NIFTY BUY = 13 trades / 8% WR / **-₹5,886**. NIFTY SELL = 9 trades / 44% WR / +₹376. BNF & MCN show no such asymmetry.
- Counterfactual filter sweep on existing 22-trade NIFTY set: Filter G (SELL + RANGE) recovers to +₹2,265 / 57% WR / PF 2.38 / Sharpe 5.39.
- **Patch shipped:** per-symbol, per-side `OU_Z_ENTRY_{BUY,SELL}_{BNF,NF,MCN}` env knobs in `ou_mrs.py`. Default symmetric (no behavior change unless env set).
- **Env set:** `OU_Z_ENTRY_BUY_NF=2.5`, `OU_Z_ENTRY_SELL_NF=1.5`. **Dormant** — only fires when NF is in `INSTRUMENTS`.
- **NF stays disabled.** Re-enable in Phase 9.8h.N.2 after porting gate into `backtest.py` + fresh walk-forward + Monte Carlo on NF.

## Diagnostic findings

### Side asymmetry (smoking gun)
| Side | N | WR | PnL |
|---|---|---|---|
| **BUY** | **13** | **8%** | **-₹5,886** |
| SELL | 9 | 44% | +₹376 |

NIFTY-specific. BNF/MCN show no asymmetry. Mechanism: 57-day window had persistent intraday-uptrend drift on NIFTY; mean-reversion longs hit continuation traps.

### Hold-duration cliff
1–5 bars: 12 trades, 8% WR, -₹6,478 (10/17 losers are PAPER_SL with adverse move only -0.04% to -0.16%). 11+ bars: 4 trades, 75% WR, +₹2,721.

### Time-of-day
Hour 13 IST: 7 trades, 14% WR, -₹3,024. Post-13:00 total = -₹3,921 (71% of total loss).

## Counterfactual filter sweep

| Filter | N | PnL | WR | PF | Sharpe |
|---|---|---|---|---|---|
| BASELINE | 22 | -₹5,510 | 22.7% | 0.45 | -5.15 |
| A. SELL only | 9 | +₹376 | 44% | 1.11 | +0.66 |
| B. ≤12:30 only | 9 | -₹1,158 | 33% | 0.74 | -2.04 |
| F. RANGE only | 17 | -₹1,895 | 29% | 0.71 | -2.21 |
| **G. SELL + RANGE** | **7** | **+₹2,265** | **57%** | **2.38** | **+5.39** |

Cross-symbol sanity: SELL-only applied to MCN *breaks* it (-₹1,114). NIFTY-specific.

## Patch shipped

### `ou_mrs.py` additions (+27 lines, +1745 bytes)
1. Per-symbol/per-side z-entry table after `_z_stop_for_sym` (line ~173):
   `_Z_ENTRY_BUY_PER_SYM` and `_Z_ENTRY_SELL_PER_SYM`, env-overridable, default symmetric.
2. Gate right after `if not sig or not sig.side: continue` (line ~734):
   `if abs(sig.z) < _z_entry_for(sym, sig.side): continue` with `BLOCKED:z_entry_side` reason log.

### `.env` additions
- `OU_Z_ENTRY_BUY_NF=2.5` (stronger evidence required for NF longs)
- `OU_Z_ENTRY_SELL_NF=1.5` (default for NF shorts)
- BNF/MCN: no override → defaults to symmetric 1.5 → **no behavior change for currently-enabled symbols**

## Defensibility (Sacred Rule #7)
- Not disabling any stop or any side outright.
- Asymmetric threshold justified by the structural mechanism (intraday drift breaks one-sided mean-reversion), not loss correlation alone.
- N=7 SELL+RANGE wins is thin — NF re-enable gated on fresh BT in N.2.

## What this phase does NOT do
- Does **not** re-enable NF in `INSTRUMENTS` (still `BNF,MCN`).
- Does **not** flip `LIVE=true` (paper-only per master brief; LIVE target ≈ end of July 2026).
- Does **not** port the gate into `backtest.py` (needed for fresh NF BT validation).
- Does **not** restart the running bot today. New code applies at next launch (Mon 09:14 IST via `ou-mrs.timer`).

## Next steps (Phase 9.8h.N.2, deferred)
1. Port `_z_entry_for(sym, side)` gate into `backtest.py`.
2. Re-run NF backtest with `OU_Z_ENTRY_BUY_NF=2.5` active.
3. Walk-forward (3 splits) + Monte Carlo (10k paths) + PSR.
4. Gate: NF must pass ≥4/5 of (PSR≥0.5, Sharpe≥1.0, PF≥1.3, MC prob(+)≥70%, WF consistency≥0.5).
5. If PASS → add NF back to `INSTRUMENTS`. If FAIL → keep disabled.

## Files touched
- `ou_mrs.py` (patched, backup at `ou_mrs.py.pre_p98hN`)
- `.env` (appended, backup at `.env.pre_p98hN`)
- `audit/phase_9_8h_N.md` (this file)

## Hard refusals this session
- **LIVE flip refused.** Master brief mandates paper-only.
- **"Force a trade today" not honored.** Lowering thresholds to force fires would violate Sacred Rule #7 and undo Phases AO/AP. The running bot is armed; paper trades fire when market conditions present a valid signal.
