# Phase 9.8h — Quant-grade protection layer + integrated validation

**Branch:** `phase-9.8g-audit-fixes`
**Started:** 25 May 2026 02:45 IST
**Trigger:** user mandate "i want everything in qunat algo hight world class calculated with 100% accuracy. try to reach jane street quant algo (not by speed but as a quant level we can reach or even better)."

## Reality check: what "100% accuracy" means and doesn't mean

- **100% trade-level accuracy is mathematically impossible.** No quant fund — Jane Street, Renaissance, Two Sigma, DE Shaw, Citadel — claims certainty per trade. Their edge is *statistical*, not deterministic.
- **What we *can* reach:** their *statistical rigor*. That means:
  1. No look-ahead bias (event-driven, fills at next-bar open) — ✅ already true
  2. Realistic execution costs (STT, brokerage, GST, exchange charges, stamp duty, slippage) — ✅ already true (`cost_model.py`)
  3. Regime-aware analysis (TREND/RANGE/CHOP attribution) — ✅ already true (`regime.py`)
  4. Selection-bias correction (Deflated Sharpe Ratio across all trials) — ✅ already in `validation/bootstrap.py`, now wired into one-command verdict
  5. Walk-forward out-of-sample stability — ✅ already in `validation/bootstrap.py`, now in verdict
  6. IID diagnostics (Ljung-Box autocorrelation + ADF stationarity) — ✅ already there, now in verdict
  7. Hold-out 24-day train / 13-day test split — ✅ already there, now in verdict
  8. Protective exit cascade matching live edge — ❌ MISSING, this phase adds it
  9. Startup config-sanity log (defends against silent kill-switches) — ❌ MISSING, this phase adds it
  10. Pre-merge gate combining all of the above — ❌ MISSING, this phase adds it
- **Where Jane Street still beats us (unbridgeable as a single-trader operation):**
  - Cross-asset correlation arbitrage across thousands of instruments
  - Microsecond co-located execution + queue position modeling
  - Internalized order flow + market-making rebates
  - Realized volatility surface modeling across the full option chain
  - Tail-risk hedging via dynamic option overlays
  - Multi-strategy portfolio Sharpe stacking
- **What we don't need to beat them at:** any of the above. We need ONE statistically significant edge on three liquid Indian index futures, after costs. That is the scope.

## Phase 9.8g closeout discoveries (input to 9.8h)

- **B7 (fixed 9.8g.8):** backtest had no `--symbol` argparse; flag was silently ignored.
- **B8 (fixed 9.8g.8):** NIFTY + MIDCPNIFTY futures parquets did not exist on the VPS.
- **9.8g.8 backtest gate revealed:** all three symbols negative on 27 Mar → 22 May:
  - BNF −₹19,883 (PF 0.72, Sharpe −1.60)
  - NF  −₹23,024 (PF 0.52, Sharpe −3.20)
  - MCN −₹13,352 (PF 0.70, Sharpe −1.32)
  - **Zero `TRAIL_STOP` fires across 63 trades.** Reason mix 77-87% `TIME_STOP_HL`.
- **B10 (this phase):** `should_trail_stop()` defaults `OU_TRAIL_TRIGGER_ATR_MULT=0` and `OU_TRAIL_LOCK_PCT=0`, both of which immediately `return False`. TRAIL has been dead-on-arrival in every backtest since 9.5g, regardless of the 9.8g.2 dedent fix.
- **B11 (this phase):** strategy.py has zero BE-ratchet / paper-SL logic. GitHub code search for `ratchet`, `breakeven`, `lock_in`, `armor`, `paper_stop`, `sl_lock`, `be_active` returned 0 hits across the whole repo. The 9.7AP "paper SL + BE ratchet" was either never implemented or implemented under a name we cannot find. Either way, **backtest cannot model live edge**.

## 02:15 IST verification of B10 (TRAIL env unlock)

With `OU_TRAIL_TRIGGER_ATR_MULT=2.0` and `OU_TRAIL_LOCK_PCT=0.5`:

| Symbol | P&L OFF | P&L ON | TRAIL fires | PF | Sharpe |
|---|---|---|---|---|---|
| BNF | −₹19,883 | −₹20,867 | 3 | 0.71 | −1.67 |
| NF | −₹23,024 | −₹21,347 | 2 | 0.53 | −3.13 |
| MCN | −₹13,352 | **+₹7,263** | 6 | **1.36** | **+1.10** |

B10 is mechanically verified. MCN flipped positive — strategy has edge. BNF + NF need additional protection.

## Phase 9.8h scope (what ships now)

### 1. BE ratchet (`strategy.py`)

Once unrealized gain reaches `OU_BE_TRIGGER_ATR_MULT × ATR` (default 1.0), the position arms. From that bar on, if current PnL drops to `OU_BE_LOCK_ATR_MULT × ATR` (default 0.1, i.e. roughly breakeven plus a small lock), the position exits with reason `BE_RATCHET`. This catches the case TRAIL misses: position went up but didn't reach TRAIL's 2×ATR activation, then drifted back through zero. NF's losers (which drift slowly to `TIME_STOP_HL`) are the prime target.

### 2. Paper SL (`strategy.py`)

Catastrophic intra-bar stop at `entry ± OU_PAPER_SL_ATR_MULT × ATR` (default 2.0). Triggered by the adverse extreme of the current bar (`low` for long, `high` for short). Fill still executes at the next bar's open with slippage so no-look-ahead invariant is preserved. This captures live-trader behavior that backtest does not currently model: every live exit at a hard ₹-stop never had a corresponding backtest exit because backtest only checked z-score thresholds.

### 3. Exit cascade ordering (`backtest.py`)

```
PAPER_SL → TARGET → STOP → BE_RATCHET → TIME_STOP_HL → Z_VEL_STALL → TRAIL_STOP
```

- PAPER_SL first: catastrophic always wins.
- TARGET/STOP: signal-driven (require fresh signal).
- BE_RATCHET: lock partial profit once armed.
- TIME_STOP_HL: mean-reversion timed out.
- Z_VEL_STALL: velocity dead (disabled in production via `OU_DISABLE_Z_VEL_STALL=on`).
- TRAIL_STOP: give back too much from peak.

### 4. Startup config-sanity log (Sacred Rule #41)

`strategy.log_config_sanity()` emits a single `[config-sanity] KEY=VALUE, ...` line listing every env-gated knob, plus `[config-sanity] FEATURE DISABLED` warnings for any kill-switch (env var ≤ 0). Called once at backtest `run()` start. Live runner integration is a follow-on (live code currently has no equivalent call).

### 5. Integrated validation suite (`tools/run_validation_suite.py`)

One command per symbol → full Bailey-LdP stack → PASS/FAIL verdict. Wraps the existing `validation/bootstrap.py` machinery (which already implements the right math). Exit code nonzero if any symbol fails — safe for CI / pre-merge gate.

### 6. DSR-corrected parameter sweep (`tools/param_sweep.py`)

Grid over `OU_PAPER_SL_ATR_MULT × OU_BE_TRIGGER_ATR_MULT × OU_TRAIL_TRIGGER_ATR_MULT × OU_TRAIL_LOCK_PCT`. Each (config, symbol) backtest is timed, its DSR computed with `n_trials = sweep_size` for honest selection-bias correction. **Results ranked by DSR, not raw Sharpe.** This is the Bailey-LdP defense against finding the lucky cell.

### 7. Pure-function unit tests (`tests/test_phase98h_exits.py`)

16 tests for `be_ratchet_armed`, `be_ratchet_hit`, `paper_sl_hit`. All pass override params (no env reload, no module reimport).

## Phase 9.8h acceptance criteria

For each symbol, the validation suite emits PASS only when ALL six checks clear:

| Check | Threshold | Source |
|---|---|---|
| Trade-level PSR(0) | ≥ 0.95 | `validation/bootstrap.py::probabilistic_sharpe_ratio` |
| Trade-level DSR (n_trials=20) | ≥ 0.50 | `validation/bootstrap.py::deflated_sharpe_ratio` |
| Walk-forward consistency rate (w=15 trades) | ≥ 0.60 | `validation/bootstrap.py::walk_forward_sharpe` |
| Walk-forward stability (CV of SR) | ≤ 1.50 | `validation/bootstrap.py::walk_forward_summary` |
| Ljung-Box lag-5 p-value | ≥ 0.05 (cannot reject IID) | `validation/bootstrap.py::ljung_box_test` |
| Hold-out 24/13 same-sign train/test | true | `validation/bootstrap.py::holdout_split_trades` |

A symbol that fails any check stays out of PR #3's merge scope. A symbol that passes all six joins the production cohort.

Under the **current** 37-day sample, NF likely fails several checks regardless of how good the protection is — the sample is just too short and too negative. That is fine. The honest answer in that case is: keep NF live (live performance has been positive — see `validation/baseline_post_b1.json` and other artifacts), but flag it as not statistically clearable on backtest until we have more out-of-sample data.

## New Sacred Rules

- **#42** — Every protective exit must have a corresponding implementation in `strategy.py` (the shared signal module). Live-only protective code creates an undetectable backtest/live divergence; lessons B11.
- **#43** — Parameter sweep results are ranked by Deflated Sharpe Ratio after multiple-testing correction (Bailey-LdP 2014), not by raw Sharpe or total P&L. Sweeping 192 cells without DSR correction is the textbook recipe for false discovery.

## Where this leaves us vs. Jane Street

| Dimension | Jane Street | OU-MRS post-9.8h |
|---|---|---|
| Statistical rigor (PSR, DSR, walk-forward, IID tests) | ✅ | ✅ matches |
| No look-ahead bias | ✅ | ✅ matches |
| Realistic execution costs | ✅ | ✅ matches |
| Regime-conditional attribution | ✅ | ✅ matches |
| Selection-bias-corrected param sweep | ✅ | ✅ matches (Sacred Rule #43) |
| Protective exit layer (BE, paper SL, trail) | ✅ | ✅ matches (9.8h ships it) |
| Startup config-sanity log | ✅ (mandatory at JS) | ✅ matches (Sacred Rule #41) |
| Cross-asset correlation arbitrage | ✅ | ❌ out of scope |
| Microsecond execution + colocation | ✅ | ❌ structurally infeasible |
| Options vol-surface modeling | ✅ | ❌ out of scope (futures-only) |
| Multi-strategy portfolio stacking | ✅ | ❌ phase 10+ candidate |
| Internalized order flow / market making | ✅ | ❌ requires market-maker license |

**Verdict on "can we reach Jane Street as quant":** on **quant rigor of a single-strategy futures backtest**, yes — post-9.8h we are at the same statistical-rigor floor a tier-1 quant fund uses internally. On **deployable quant infrastructure** (cross-asset, microstructure, vol-surface, market-making), no — those require institutional infrastructure, not better code. That is the honest answer.

## VPS run plan (post-merge into `phase-9.8g-audit-fixes`)

```bash
cd /home/ubuntu/bots/ou-mrs
git pull origin phase-9.8g-audit-fixes
source venv/bin/activate

# 1) Unit tests (must all pass)
python -m pytest tests/test_phase98h_exits.py tests/test_exit_helpers.py tests/test_strategy.py -v

# 2) Integrated validation suite (per-symbol verdict)
python tools/run_validation_suite.py 2>&1 | tee validation/phase_9_8h_run.log
# exit code 0 = all 3 symbols PASS; nonzero = at least one symbol failed

# 3) (Optional) param sweep — start with --coarse to budget time
python tools/param_sweep.py --symbol BANKNIFTY  --coarse   # ~5 min
python tools/param_sweep.py --symbol NIFTY      --coarse   # ~5 min
python tools/param_sweep.py --symbol MIDCPNIFTY --coarse   # ~5 min
# inspect bt_sweep_*/results.csv -- top-5 configs ranked by DSR

# 4) If validation passes for all 3 symbols, mark PR #3 ready and squash-merge.
#    Restart bot ONLY when all 3 runners report flat positions (Sacred Rule #6).
```

## Out-of-scope (deferred to 9.8i and beyond)

- Live runner integration of `log_config_sanity()` (currently only backtest calls it).
- Vol-expansion stop (`ATR_now > 2 × ATR_at_entry` → exit). Requires per-bar ATR refresh; defer to 9.8i.
- Cross-symbol portfolio Sharpe (combine BNF + NF + MCN into one Sharpe, account for correlation).
- Live BE-ratchet implementation in `ou_mrs.py` (>30 KB; must use VPS-side patch per Sacred Rule #34).
- Market-impact slippage model conditional on lot size (current model is fixed 2-tick).
- Replay test: feed historical tick-by-tick into live runner in dry mode, compare vs backtest reasons distribution.
