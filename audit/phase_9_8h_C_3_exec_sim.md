# Phase 9.8h.C.3 — Execution simulator: intra-bar stop-fill gap risk

## TL;DR

C.3 adds an **intra-bar gap-risk surcharge** for STOP-class market exits.
When a stop bar's range exceeds N×ATR (default 1.5×), an extra tick penalty
proportional to the excess range is added on top of the C.2 slippage. TARGET
(limit) exits are exempt — limit orders do not cross the spread.

**Headline result on our validation dataset: essentially zero metric impact.**

| Symbol | C.2 PSR | C.3 PSR | Δ PSR | C.2 DSR_N20 | C.3 DSR_N20 |
|---|---|---|---|---|---|
| BANKNIFTY | 0.837 | 0.837 | 0.000 | 0.190 | 0.190 |
| NIFTY | 0.108 | 0.107 | −0.001 | 0.001 | 0.001 |
| MIDCPNIFTY | 0.795 | 0.795 | 0.000 | 0.069 | 0.069 |

This is a **valid honest null result**. The model fires only on genuinely
violent bars; almost no stop fills in this dataset crossed the threshold,
so C.3 surcharge ≈ 0 on virtually every trade. NIFTY's tiny PSR drop
(−0.001) confirms at least one stop bar did trigger the surcharge.

## Why ship it anyway

1. **Risk-model realism is a structural improvement**, not a tuning knob.
   Future regimes with wider intraday ranges (gap-up/down days, news
   events, expiry rolls) will expose strategies that don't price gap fills.
   Better to encode the cost now than discover it live.
2. **It composes cleanly with C.2.** Off (default `OU_COST_MODEL_V2=off`)
   ⇒ legacy flat ticks. On with no violent bars ⇒ exactly C.2. On with
   violent bars ⇒ C.2 + proportional gap penalty.
3. **It tells us what the bottleneck IS:** sample size, not cost model.
   The PSR-at-zero acceptance bar (≥0.95) is structurally unreachable at
   N=15–22 trades regardless of how we model costs. C.3 confirming this
   means C.4 should target sample size, not more cost refinements.

## Design

### Function

```python
def estimate_gap_slippage_ticks(bar_range, atr, reason, env=None) -> float
```

Returns non-negative tick surcharge to ADD to the C.2 base. Returns 0.0
when:
* `OU_COST_MODEL_V2` is off (legacy mode)
* `reason` is not in `STOP_CLASS_EXIT_REASONS`
* `atr` or `bar_range` is missing/non-positive
* `bar_range / atr ≤ OU_GAP_THRESHOLD_ATR`

Otherwise:
```
surcharge_ticks = OU_GAP_PENALTY_SLOPE × (bar_range/atr − OU_GAP_THRESHOLD_ATR)
```

### Reason taxonomy

Exported as frozen sets in `cost_model.py`:

* `STOP_CLASS_EXIT_REASONS`: `STOP`, `PAPER_SL`, `BE_RATCHET`,
  `TIME_STOP_HL`, `Z_VEL_STALL`, `TRAIL_STOP` — all market exits that
  cross the spread.
* `LIMIT_TP_EXIT_REASONS`: `TARGET` — limit-order take-profit exits that
  do NOT cross the spread.

### Env knobs

| Env var | Default | Effect |
|---|---|---|
| `OU_COST_MODEL_V2` | `off` | Master switch (shared with C.2). `off` ⇒ surcharge = 0. |
| `OU_GAP_THRESHOLD_ATR` | `1.5` | range/ATR ratio above which surcharge fires. |
| `OU_GAP_PENALTY_SLOPE` | `1.0` | Ticks per unit of excess range/ATR. |

## Wiring in backtest.py

`_close()` now computes:

```python
_slip_ticks_c2 = estimate_slippage_ticks(_BT_SYMBOL, pos["qty"], rv20=None)
_gap_ticks_c3 = estimate_gap_slippage_ticks(
    bar_range=(fill_bar["high"] - fill_bar["low"]),
    atr=pos.get("atr"),
    reason=reason,
)
_total_slip_ticks = _slip_ticks_c2 + _gap_ticks_c3
exit_px = fill_bar["open"] - (_total_slip_ticks * TICK) * (1 if pos["side"]=="BUY" else -1)
```

## Validation

* Unit tests: `tests/test_phase_9_8h_c3_gap_slippage.py` — **12 tests, all green**
* Full repo suite: **200 passed / 4 skipped** (was 188 / 4 at C.2 head)
* Validation suite (`OU_COST_MODEL_V2=on`) re-run end-to-end on all 3 symbols
* Smoke probe confirmed: narrow bar → 0, wide STOP → surcharge fires, wide TARGET → 0, v2-off → 0

## Rollback

* Soft: `OU_GAP_PENALTY_SLOPE=0` or `OU_GAP_THRESHOLD_ATR=999` ⇒ never fires
* Hard: `OU_COST_MODEL_V2=off` ⇒ both C.2 and C.3 disabled, legacy flat-tick behavior

## What's next (C.4)

The null result here makes the data plan obvious: **backfill our minute
dataset to N≈60 trades/symbol** so the PSR-at-zero acceptance gate becomes
statistically reachable. The acceptance math (per-trade Sharpe ≈ 0.4–0.6
on BNF/MCN, `PSR(0) → 1` requires N where `Sharpe × √(N−1)` clears the
bar at α=0.05) says we need roughly 4× the trade count we have now.
Currently we run on a fragment of available history; expanding the window
is the unblocking move.
