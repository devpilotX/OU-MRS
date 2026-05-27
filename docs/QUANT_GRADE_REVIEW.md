# OU-MRS Quant-Grade Review

**Phase 9.8h Phase E synthesis** · Author: agent · Date: 2026-05-27

This document is the honest end-of-9.8h synthesis: what we built, what we verified, what we falsified, and what "world-grade" actually requires from this codebase next. It supersedes any prior PSR/Sharpe claims made before 2026-05-27.

---

## 1. Executive summary

The OU-MRS strategy on **BANKNIFTY and MIDCPNIFTY monthly index futures** showed a **provisionally positive edge** on the 37-38 session Mar-May 2026 FUT backtest after the C.1-C.3 cost-model hardening (PSR 0.837 / 0.795 respectively). On 2026-05-27 we ran a longer 137-150 session backtest using NSE INDEX prices as a proxy for FUT (phase 9.8h.C.4) and saw catastrophic loss (Sharpe -0.50 / -3.58). The follow-up control experiment (9.8h.C.4.b) **slicing the INDEX trades to the same calendar window as the FUT backtest** still produced loss (Sharpe -2.12 / -3.21), which proves the catastrophic INDEX result is **basis-effect, not regime-overfit**. INDEX is therefore not a valid out-of-sample proxy for this strategy. NIFTY has insufficient data to evaluate.

**Honest current state:**
- Strategy edge is **provisional only** — demonstrated on 37-38 FUT sessions / 16-15 closed trades per symbol. PSR > 0.8 on this sample size cannot rule out luck at standard confidence.
- The strategy is **FUT-microstructure-specific** — basis premium/discount drift between FUT and INDEX appears to be load-bearing.
- **No live capital is deployed.** Paper trading only.
- **Older FUT data is not available** via Angel SmartAPI (expired contract tokens are not indexed). This blocks the natural OOS test for several months.

**Headline metric (FUT backtest, post-C.3 cost stack):**

| Symbol | Sessions | Trades | Sharpe | PSR | Holdout train Sharpe → test Sharpe |
|---|---|---|---|---|---|
| BANKNIFTY | 38 | 16 | positive | 0.837 | positive → positive |
| MIDCPNIFTY | 37 | 15 | positive | 0.795 | positive → positive |
| NIFTY | 37 | (insufficient) | n/a | n/a | n/a |

---

## 2. What was built (Phase 9.8h.B track — validation framework)

The B track produced an institutional-grade validation rig from a paper-trading log that had no validation discipline.

| Phase | Deliverable | Status |
|---|---|---|
| **B.1** | `trades.jsonl` rebuild: symbol field added, canonical reconciliation | merged |
| **B.2** | Trades-vs-state ledger desync audit, `tools/verify_pnl_reconciliation.py` | merged |
| **B.3** | PnL reconciliation: trades.jsonl is the source of truth (canonical) | merged |
| **B.4** | Walk-forward validation suite (`tools/run_validation_suite.py`) | merged |
| **B.5** | 6-test validation report: PSR, DSR_N20, holdout-stability, WF-consistency, WF-stability, Ljung-Box, breakeven probability | merged |

Validation suite outputs:
- `validation/phase_9_8h_<SYM>.json` per symbol
- `validation/phase_9_8h_master_report.json` aggregated PASS/FAIL
- Each test has a documented threshold derived from quant-finance literature (Bailey & Lopez de Prado 2014 PSR, Harvey & Liu 2015 DSR, etc.).

This is the most important thing the 9.8h sprint produced. Without it the strategy would still be claimed-but-unverified.

---

## 3. What was built (Phase 9.8h.C track — cost realism)

The C track hardened the backtest cost model to remove sources of bias.

| Phase | Change | BNF PSR | MCN PSR |
|---|---|---|---|
| Post-B.5 baseline | Bid-ask slippage only | 0.510 | 0.637 |
| **C.1** | Apply B.5 findings (tighter SL semantics, no entries near close) | 0.798 | 0.744 |
| **C.2** | Cost model v2: STT, exchange/SEBI fees, GST on brokerage, stamp duty | 0.837 | 0.795 |
| **C.3** | Exec-sim gap-risk surcharge on STOP-class exits (`OU_GAP_THRESHOLD_ATR`, `OU_GAP_PENALTY_BPS`) | 0.837 | 0.795 |
| **C.4** | INDEX-mode backtest (137-150 sessions) — **retracted** by C.4.b | 0.376 | 0.008 |
| **C.4.b** | Basis-vs-regime control — proves C.4 was basis-effect, not edge failure | n/a | n/a |

The C.1→C.2→C.3 PSR climb on the FUT backtest is the cost-realism story. The C.4→C.4.b detour is the data-validity story.

---

## 4. The C.4 retraction — why it matters

C.4 was intended as a sample-size expansion: 38 FUT sessions is small (16 closed trades is even smaller). We hypothesized that running the strategy on the longer INDEX series would either confirm or refute the C.3 PSR. The result (Sharpe -0.50 / -3.58) initially looked like regime fragility — i.e., the strategy works in Mar-May 2026 but fails in Oct-Apr 2025-26.

C.4.b retracted that interpretation. **On the same calendar window** (the 26-37 days where FUT and INDEX overlap):
- BNF FUT (C.3): 16 trades, PSR 0.837, **positive edge**
- BNF INDEX (C.4.b sliced): 12 trades, Sharpe -2.12, **negative**
- MCN FUT (C.3): 15 trades, PSR 0.795, **positive edge**
- MCN INDEX (C.4.b sliced): 22 trades, Sharpe -3.21, **negative**

Both symbols flip from clear winner to clear loser purely by swapping the price series (FUT → INDEX), holding calendar fixed. **This is a basis-effect signature.** Plausible mechanisms:
- INDEX is a weighted average of constituent stocks; FUT carries a premium/discount that itself mean-reverts (cost-of-carry).
- ATR and z-score thresholds calibrated on FUT do not translate to INDEX price scale.
- Intraday microstructure differs: FUT has its own tick-by-tick liquidity profile distinct from INDEX.

**Therefore: INDEX cannot stand in for FUT in this strategy's OOS validation.** Any future longer-horizon OOS test must use actual FUT data, which is what Section 5 addresses.

---

## 5. The data wall — why C.5 stops here

To properly OOS-test this strategy we need 100+ FUT sessions. We have 37-38. The natural source of older FUT data is the Angel SmartAPI `getCandleData` endpoint, the same endpoint that fed the FUT parquet for Mar-May 2026.

**Constraint discovered (already documented in `backfill_historical.py` header):**

> *"Phase 8g v6 — Abandons FUT chain lookup (Angel doesn't index expired contracts)."*

Angel's scripmaster only includes active contracts. After a monthly FUT expires, its token is removed. Without a token we cannot call `getCandleData`. The team already encountered this wall before phase 8g and pivoted to INDEX-mode backfill at that time. The C.4/C.4.b sequence completed the loop and demonstrated INDEX is not a valid substitute.

**Options to break the data wall (all out-of-scope for this PR):**
1. **NSE bhavcopy archives** — contain daily OHLC for all historical FUT contracts. No intraday. Would allow daily-resolution backtesting only.
2. **NSE eod archives + 1-minute reconstructed via TBT replay** — commercial vendor only.
3. **Alternate intraday vendor** — Bloomberg, GlobalDataFeeds, TrueData, etc. Commercial, cost-bound.
4. **Forward accumulation** — keep paper-trading. At ~1 trade/symbol/2 sessions we accumulate ~125 BNF trades / year. Adequate sample size in 6-12 months of live paper.

The defensible choice given the existing constraints is **option 4**: continue paper-trading, gather more live evidence, and re-run the validation suite quarterly. This is what we will do.

---

## 6. What "world-grade" actually requires from here

For this codebase to be defensibly world-grade (meaning: a portfolio manager could deploy non-trivial capital on it with documented evidence rather than narrative), the following work items are required, ranked:

### 6.1 Sample size (highest priority, slow)
- Accumulate ≥ 100 closed FUT trades per symbol in live paper trading.
- Re-run `tools/run_validation_suite.py` quarterly.
- Publish each quarter's report in `validation/` with date suffix.
- **Estimated time:** 6-12 months of paper trading.

### 6.2 Regime tagging on live trades (low effort, ongoing)
- Already have `regime.py` classifier (TREND / RANGE / CHOP). Verify it tags every live trade.
- After 50+ trades, decompose PnL by regime tag. If one regime carries the edge, implement regime-gated entries.
- Add a `--regime-breakdown` flag to the validation suite to surface this without a code change.

### 6.3 Adversarial cost-stack stress test (medium effort)
- The C.2/C.3 cost stack assumes published exchange fees, GST 18%, STT futures sell-side 0.0125%, etc. These are correct as of 2026 but tariffs change.
- Add a `OU_COST_STRESS_MULTIPLIER` env that scales the entire variable-cost stack by 1.5x. Re-validate. The strategy should survive a 50% adverse cost shock if the edge is real.

### 6.4 Microstructure drift monitor (low effort, ongoing)
- The basis spread (FUT minus INDEX) is itself a tradeable signal in some regimes.
- Log spot-vs-future basis at every tick in `state/heartbeat.jsonl` (currently the heartbeat does not capture this).
- Use it as a feature in a future model layer (not the current OU strategy).

### 6.5 Slippage realism check (medium effort)
- The current cost model assumes 1-tick adverse fill at MARKET. In low-liquidity bars (lunch hour, expiry day) this is optimistic.
- Cross-reference paper-fills with actual NBBO from `state/heartbeat.jsonl` and quantify the gap.
- Add `OU_LIQUIDITY_PENALTY_BPS` if the gap is material.

### 6.6 Statistical hygiene
- The current validation suite tests Ljung-Box on trade returns (passes). Add:
  - Reality check (Sullivan-Timmermann-White) once trade count > 50
  - SPA (Hansen 2005) multiple-testing correction for any sweep that tried > 1 parameter set
  - Documented data-snooping bias accounting for every backtest that informed C.1-C.3 parameter choices.

### 6.7 Drawdown discipline (already in place, verify firing)
- Sacred Rule #19 requires every armor layer to be observed firing in live conditions.
- The C.3 gap-risk surcharge has NOT yet been observed firing live (it fires only when a STOP exit coincides with a large gap, which is rare).
- Phase A.4 of this sprint will run live observation on 2026-05-27 with `OU_COST_MODEL_V2=on` and `OU_GAP_THRESHOLD_ATR=1.5` to provide the first such observation. Pending.

---

## 7. What is NOT in this codebase yet

Gap analysis vs a notional world-grade institutional setup:

| Capability | Status | Required for world-grade |
|---|---|---|
| Walk-forward validation suite | ✅ | ✅ |
| Multi-test PSR/DSR | ✅ | ✅ |
| Cost model with STT/GST/fees | ✅ (C.2) | ✅ |
| Gap-risk surcharge on STOPs | ✅ (C.3) | ✅ |
| Sample size > 100 trades/symbol | ❌ (15-16) | ✅ |
| Multi-instrument OOS | ❌ (INDEX is invalid; NIFTY has insufficient data) | ✅ |
| Portfolio-level risk model (correlation, factor exposure) | ❌ | ✅ |
| Live execution-vs-paper-fill audit | ⚠️ (partial via heartbeat) | ✅ |
| Regime-conditioned sizing | ❌ (classifier exists but not used for sizing) | ⚠️ (nice-to-have) |
| Adversarial stress tests | ❌ | ⚠️ (nice-to-have) |
| Reality check / SPA multiple-testing | ❌ | ✅ (once trade count permits) |
| Drawdown circuit breakers (daily kill, dual-cap) | ✅ (9.7AL/9.7AN) | ✅ |
| Independent dashboard handoff (Opus 4.7) | ✅ | ✅ |

---

## 8. Recommended forward path (next 90 days)

1. **Today (2026-05-27 09:14 IST):** Phase A.4 live observation. Verify `config-sanity` log line and that the C.3 cost stack is loaded. Capture in `audit/phase_9_8h_A_4_live_observation.md`.
2. **This week:** keep paper-trading. Document every armor firing in the EOD report.
3. **Quarterly (next: 2026-08-31):** re-run `tools/run_validation_suite.py`. Compare PSR to the 2026-05-21 baseline.
4. **When BNF trade count crosses 50:** decompose PnL by regime tag. Decide if regime gating is warranted based on data, not a priori.
5. **When BNF trade count crosses 100:** publish a formal v2 review document with full reality-check / SPA correction.
6. **Never:** deploy live capital based on the 37-session backtest alone. The PSR is encouraging but not deployable.

---

## 9. Open cases (carried forward)

| ID | Description | Source |
|---|---|---|
| OC-1 | 12 May 2026 -₹162,000 loss — standalone case, not bundled with filter-loosening era | Sacred Rule #20 |
| OC-2 | NIFTY no INDEX parquet available; no plan to fix until forward-accumulation produces FUT trades | C.4 audit |
| OC-3 | `tools/run_validation_suite.py:47` uses bare `python` instead of `./venv/bin/python` | B.5 carry-over |
| OC-4 | B.4 instructions-page write returns content_only_editor access denial | persistent |
| OC-5 | C.3 gap-risk surcharge has not yet fired live | Sacred Rule #19 |
| OC-6 | Older FUT data is permanently unavailable from Angel SmartAPI | C.5 wall |

---

## 10. Final verdict

The OU-MRS strategy in its current form is **a credible candidate for continued paper-trading with disciplined sample accumulation**. It is **not yet a candidate for live capital deployment**. The 9.8h sprint produced the validation framework needed to make that judgement honestly. The C.4/C.4.b detour was the most important experiment of the sprint because it prevented a costly wrong fix (regime gating against a basis-effect artifact). The next material progress requires time, not code.

This is the most honest report we can produce on this strategy today.
