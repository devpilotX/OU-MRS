# Phase 9.8h.C.4 — INDEX-mode backtest (sample-size expansion)

## TL;DR

C.3 left the strategy with passes 4/2/3 out of 6 acceptance checks on a ~37-day
FUT sample. The diagnosis was "sample-size limited." C.4 added an INDEX-mode
switch that expands the sample by ~4× using 1-min INDEX bars.

**The expanded sample is catastrophic:**

| Sym | Window | Trades | PnL | Sharpe | PSR | DSR_N20 | Holdout train→test | Passes |
|---|---|---:|---:|---:|---:|---:|---|---:|
| BNF FUT (C.3) | 38d | 16  | — | — | 0.837 | 0.190 | — | 4/6 |
| BNF **INDEX** | 137d | 96  | −₹4,448 | −0.504 | 0.376 | 0.014 | +0.571 → −0.060 (sign flip) | 1/6 |
| MCN FUT (C.3) | 37d | 15  | — | — | 0.795 | 0.069 | — | 3/6 |
| MCN **INDEX** | 150d | 114 | −₹39,175 | −3.579 | 0.008 | 0.000 | −0.521 → −0.233 (negative both) | 3/6 |

On ~4× the data, the strategy goes from "close to acceptance" to
"unambiguously losing money." BNF flips sign between train and test. MCN is
negative even in-sample. PSR collapses from 0.84 → 0.38 for BNF and from 0.80
→ 0.01 for MCN.

Ljung-Box still passes (residuals IID), so the metric machinery works. The
strategy itself does not generalize beyond the March–May 2026 window.

## What this means

The favorable PSR seen at C.1–C.3 is **regime-specific**, not strategy edge.
The Mar–May 2026 FUT sample over-represents whatever regime favors this
strategy (most likely high-volatility mean-reversion). The Oct 2025–May 2026
INDEX window contains broader regimes — trending, low-vol, gap-dominated —
and the strategy loses badly outside its preferred regime.

**This is exactly the finding good validation should surface.** Without the
expanded sample, the team would have rolled toward live capital on a
regime-overfit edge.

## Caveat: INDEX is not FUT

INDEX prices differ from FUT prices by the basis (typically <0.5% on these
indices). Cost layers (C.2 ticks, C.3 gap) operate on INDEX price scale, not
FUT scale. So this run is **not a perfect substitute** for a long FUT
backtest. It is a strong directional signal that the strategy is
regime-overfit, but the absolute PnL numbers shouldn't be quoted as if they
were FUT PnL.

A control experiment — run INDEX-mode on the *same* 37-day window the FUT
backtest covers — would isolate "basis noise" from "regime exposure."
Deferred to C.4.b.

## What changed

* `backtest.py`: added `BT_USE_INDEX` env switch + `_resolve_data_path()`
  function that swaps `data/<SYM>_FUT_1min.parquet` for the matching INDEX
  parquet. NIFTY fails fast in INDEX mode (no NIFTY_INDEX parquet on disk).
* `.env.example`: documents `BT_USE_INDEX` and `BT_INDEX_BASIS_PTS` (latter
  reserved for a future basis adjustment; default 0.0 / no adjustment).

## Rollback

* Hard: leave `BT_USE_INDEX=off` (default). FUT data path is unchanged.

## What's next (C.5)

Given the C.4 finding, the next phases need to *change* before chasing more
sample. Options ranked by expected leverage:

1. **Regime gating** — hard-gate entries on the regime tag the strategy is
   actually edge-positive in. If the strategy only works in a specific
   regime, only trade that regime.
2. **Filter audit** — the May FUT period passed at PSR 0.84; the broader
   INDEX period fails. Diff the filter-firing distribution between the two
   windows to find which filter discriminates.
3. **C.4.b control experiment** — run INDEX-mode on the same 37-day window
   to attribute the failure to basis vs regime.
4. **Paper-trading hold** — do **not** push toward live until at least one
   regime-aware variant clears PSR >= 0.95 on a >100-session out-of-sample
   slice.

C.5 is regime gating.
