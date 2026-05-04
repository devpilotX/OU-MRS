# OU-MRS — Ornstein-Uhlenbeck Mean-Reversion System

Intraday algorithmic trading bot for Indian index futures (BankNifty, Nifty, FinNifty)
using OU-process mean reversion on 1-minute bars, with institutional-grade risk
plumbing including auto-scaling capital tiers, multi-layer halt logic, sticky
PFM persistence, and crash-recovery for stop-loss orders.

**Status:** Paper trading on Angel One. Phase 9.8 (May 2026): regime allow-list filter active.

---

## Quickstart (development)

git clone git@github.com:devpilotX/OU-MRS.git
cd OU-MRS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit with your Angel + dashboard credentials
venv/bin/python3 backtest.py
strategy.py            signal compute + exit helpers (CORE)
regime.py              ADX-based TREND / RANGE / CHOP classifier
ou_mrs.py              live trading main loop
ou_mrs_runner.py       per-instrument state container
prop_firm_monitor.py   daily-loss + drawdown halt logic
cost_model.py          realistic fees (STT + brokerage + slippage)
angel_adapter.py       Angel SmartAPI wrapper
backtest.py            event-driven historical replay
walk_forward.py        sequential fold validation
monte_carlo.py         bootstrap simulation
tearsheet.py           4-page PDF report generator
dashboard/             FastAPI + uvicorn, ~25 endpoints
tests/                 pytest suite
sudo systemctl status ou-mrs.timer ou-mrs.service ou-mrs-dashboard.service
sudo journalctl -u ou-mrs.service -f -n 50
venv/bin/python3 walk_forward.py


For full ops cheatsheet, see Master Audit Part 7.

## Phase history

The codebase uses Phase tags in commit messages and inline comments for
git-blame archaeology. Recent phases:

- **9.5d-g** — NF stop-fix, PFM sticky halt, dashboard truth wire, trail-stop
- **9.6** — SSE live ticks, dashboard pump
- **9.7b** — Bug2 broker.symbol mutation, bug3 f-string fix, pre-market guard
- **9.8** — Regime allow-list filter (CHOP+RANGE deployed)

## Risk disclaimers

- Past performance does not guarantee future results.
- Even a high-rated system can have a 3-sigma month.
- Running an algo for your own account is fine. Outside capital triggers
  SEBI PMS / RA / IA registration requirements.
- Phase 9.8 backtest on 37-day FUT sample shows PF 1.363 with CHOP+RANGE
  filter, but 142-day INDEX walk-forward shows the strategy is near
  break-even on longer samples. Currently a thin-edge mean-reversion play.

## License

Proprietary. Not for redistribution.

## Contact

Owner: Dipanshu Kumar (DevPilotX / ALLplay HQ)
