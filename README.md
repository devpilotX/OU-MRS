# OU-MRS

Ornstein-Uhlenbeck intraday mean-reversion bot for Indian index futures.
Symbols: BANKNIFTY, NIFTY, MIDCPNIFTY. Built on Angel One SmartAPI.

Branch:     phase-9.8f-bloomberg (active) / phase-9.8g-audit-fixes (open PR)
Latest tag: phase-9.7AQ-revert-am
Date:       25 May 2026
Mode:       Paper
Capital:    Rs 37,50,000

Net P&L all-time: +Rs 1,77,428 over 19 trades (68% win rate).
Sharpe 1.32 / Sortino 1.41 / Calmar 7.86 (20d rolling).

Risk armor (May 2026): notional leverage cap 3x, daily loss kill -Rs 50k,
dual-cap max_lots (BNF 7 / NF 6 / MCN 6), paper-side STOP + breakeven ratchet,
filter discipline restored after 5/19 alpha-decay incident.

Dashboard at https://algo.devpilotx.com is a separate project owned by another engineer.
This repo contains the algo only.

Quick start:
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env   (then fill Angel credentials)
  ./run_bot.sh

## Phase 9.8g audit (25 May 2026)

Full A-to-Z code review of the active phase-9.8f-bloomberg branch.
Findings + which fixes shipped on phase-9.8g-audit-fixes vs which
require a manual VPS edit are documented in:

    audit/PHASE_9_8G_AUDIT.md

Shipped on phase-9.8g-audit-fixes:
  9.8g.1  ou_mrs_runner.py   single source of truth for lot_size (drop _lot_nse)
  9.8g.2  backtest.py        dedent TRAIL_STOP + env-tunable CAPITAL/LOT/MAX_LOTS
  9.8g.3  signal_publisher.py per-symbol signals.json routing
  9.8g.4  strategy.py        remove dead vols.sum<=0 check
  9.8g.5  README.md          dedupe disclaimer + audit pointer (this commit)
  9.8g.6  .env.example       FINNIFTY -> MIDCPNIFTY, add OU_ATR_MULT, etc.
  9.8g.7  audit doc          new file documenting everything

Manual-edit-required on VPS (ou_mrs.py is too large to round-trip
through the agent, see Sacred Rule #34 / audit doc):
  - drop module-level _LOT_SIZE_AL dict (had stale NF=75)
  - rewrite size_lots() to use _POLICY['risk_per_trade_pct'] and runner.atr_mult
  - pass symbol=runner.symbol on every signal_publisher call

Backtest gate (Sacred Rule #31): each shipped commit must be backtested
before merging the PR into phase-9.8f-bloomberg. Do NOT auto-merge.

Disclaimer: Educational use. Past performance does not predict future returns.
Indian F&O losses can exceed deposits. Paper only - do not flip LIVE=true
without walk-forward validation, 30 paper sessions post-armor, and independent risk review.
