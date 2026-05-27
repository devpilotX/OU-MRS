# OU-MRS

Ornstein-Uhlenbeck intraday mean-reversion bot for Indian index futures.
Symbols: BANKNIFTY, MIDCPNIFTY (NIFTY armed but insufficient validation data).
Built on Angel One SmartAPI.

    Branch:     phase-9.8f-bloomberg (active)
    Date:       27 May 2026 (end of phase 9.8h sprint)
    Mode:       PAPER ONLY — no live capital authorised
    Capital:    Rs 37,50,000 (paper)

## Where we are

Phase 9.8h shipped two parallel tracks:

- **B track (validation framework)** — PRs #10–#14, merged. Built a 6-test
  walk-forward validation suite (PSR, DSR_N20, holdout-stability, WF-consistency,
  WF-stability, Ljung-Box) at `tools/run_validation_suite.py`.
- **C track (cost realism)** — PRs #15–#19, merged. Cost model v2 (STT/GST/exchange
  fees), gap-risk surcharge on STOPs, INDEX-mode backtest, and a control experiment
  that **retracted** the INDEX result as basis-effect rather than regime overfit.

**Headline metric (post-C.3 cost stack, FUT backtest):**

    BANKNIFTY    38 sessions    16 trades   PSR 0.837   (positive edge, provisional)
    MIDCPNIFTY   37 sessions    15 trades   PSR 0.795   (positive edge, provisional)
    NIFTY        37 sessions    insufficient closed trades

**This is provisional only.** 15–16 closed trades cannot rule out luck at standard
confidence. See `docs/QUANT_GRADE_REVIEW.md` for the honest end-of-sprint synthesis.

## Phase 9.8h.C.4 retraction

C.4 attempted to expand the OOS sample by running the backtest on 137–150 sessions
of NSE INDEX prices. Result was catastrophic loss (BNF Sharpe −0.50, MCN −3.58).
C.4.b sliced those INDEX trades to the C.3 FUT calendar window and **still saw
negative Sharpe**. Conclusion: INDEX is not a valid OOS proxy for this FUT strategy.
The basis premium/discount drift between FUT and INDEX is load-bearing.

Older FUT contract data is **permanently unavailable** from Angel SmartAPI
(expired tokens are not indexed). Forward paper-trading is the only path to a
larger FUT sample.

Details:

- `audit/phase_9_8h_C_4_index_mode.md` — the INDEX-mode patch + result
- `audit/phase_9_8h_C_4b_basis_vs_regime.md` — the control retraction
- `docs/QUANT_GRADE_REVIEW.md` — full synthesis with forward path

## Risk armor (live since 21 May 2026, 14:21 IST)

    9.7AL.1   dual-cap (notional ceiling + lot ceiling per symbol)
    9.7AN     daily kill switch at -Rs 50,000
    9.7AO     tight stops (z >= 2.5, ATR x 1.2)
    9.7AP     paper-side STOP fires + breakeven ratchet at +1 ATR
    9.7AQ     NF lot reverted to 65, filter discipline restored
    9.8h.C.2  cost model v2 (STT/GST/exchange fees in backtest)
    9.8h.C.3  gap-risk surcharge on STOP exits (paper bot wiring pending)

## Live execution status

    `ou-mrs.timer`     auto-launches Mon-Fri 09:14 IST
    Bot internal EOD   15:30 IST (clean exit, state flushed)
    `ou-mrs-eod.timer` fires EOD report at 15:35 IST

    Dashboard at https://algo.devpilotx.com is owned by a separate operator (Opus 4.7).
    This repo contains the algo only.

## Quick start

    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env   # then fill Angel credentials
    ./run_bot.sh

Backtest the strategy with the post-C.3 cost stack:

    OU_COST_MODEL_V2=on OU_GAP_THRESHOLD_ATR=1.5 \
        ./venv/bin/python backtest.py --symbol BANKNIFTY

Run the validation suite over the latest backtest output:

    ./venv/bin/python tools/run_validation_suite.py --skip-backtest

## Documentation

    audit/                            phase-by-phase audit notes (B.1–C.4.b)
    docs/QUANT_GRADE_REVIEW.md        end-of-sprint synthesis + forward path
    .env.example                      all tunables documented

## What this codebase is NOT yet

It is not yet deployable to live capital. The 9.8h sprint built the validation
framework needed to make that judgement honestly, and the answer at 27 May 2026
is: not yet. See `docs/QUANT_GRADE_REVIEW.md` Section 6 for the 90-day plan.

## Disclaimer

Educational use only. Past performance does not predict future returns. Indian
F&O losses can exceed deposits. Paper trading only — do not flip LIVE=true
without (1) at least 100 closed trades per symbol in paper, (2) re-validation
showing PSR >= 0.95 with multiple-testing correction, and (3) independent risk
review.
