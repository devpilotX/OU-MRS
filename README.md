# OU-MRS

Ornstein-Uhlenbeck intraday mean-reversion bot for Indian index futures.
Symbols: BANKNIFTY, NIFTY, MIDCPNIFTY. Built on Angel One SmartAPI.

Branch:     phase-9.8f-bloomberg
Latest tag: phase-9.7AQ-revert-am
Date:       21 May 2026
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

Disclaimer: Educational use. Past performance does not predict future returns.
Indian F&O losses can exceed deposits. Paper only - do not flip LIVE=true
without walk-forward validation + 30 paper sessions post-armor + risk review.
without walk-forward validation, 30 paper sessions post-armor, and independent risk review.
