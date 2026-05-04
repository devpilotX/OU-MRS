# OU-MRS -- Ornstein-Uhlenbeck Mean-Reversion System

Intraday algorithmic trading bot for Indian index futures (BankNifty, Nifty, FinNifty) using OU-process mean reversion on 1-minute bars, with institutional-grade risk plumbing including auto-scaling capital tiers, multi-layer halt logic, sticky PFM persistence, and crash-recovery for stop-loss orders.

*Status:** Paper trading on Angel One. Phase 9.8 (May 2026): regime allow-list filter active.

---

## Quickstart (development)

```bash
git clone git@github.com:devpilotX/OU-MRS.git
cd OU-MRS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit with your Angel + dashboard credentials
venv/bin/python3 backtest.py
```

## Architecture (high level)

Single source of truth: `strategy.py` is imported by both `backtest.py` and `ou_mrs.py`. Live and backtest share signal-generation logic exactly.

```
strategy.py            signal compute + exit helpers (CORE)
regime.py              ADX-based TREND / RANGE / CHOP classifier
ou_mrs.py              live trading main loop
ou_mrs_runner.py       per-instrument state container
prop_firm_monitor.py   daily-loss + drawdown halt logic
cost_model.py          realistic fees
angel_adapter.py       Angel SmartAPI wrapper
backtest.py            event-driven historical replay
walk_forward.py        sequential fold validation
monte_carlo.py         bootstrap simulation
dashboard/             FastAPI + uvicorn, about 25 endpoints
tests/                 pytest suite
```

For deeper detail (file structure, VPS layout, SSH, audit, roadmap, scoring):
see the OU-MRS Master Audit and Operations Manual in the project's Notion workspace.

## Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LIVE` | `false` | Set to `true` only for real-capital trading |
| `CAPITAL` | `150000` | Account size in INR |
| `INSTRUMENTS` | `BNF` | Comma-separated subset of BNF, NF, FNF |
| `OU_ADX_THRESHOLD` | `30` | Reject entries when ADX above this |
| `OU_Z_ENTRY` | `1.5` | Z-score threshold for entry |
| `OU_REGIME_FILTER` | (unset) | Phase 9.8: allow-list e.g. `CHOP,RANGE` |

## Operations

The bot starts via systemd timer at 09:14 IST every weekday. Exits 15:30 IST.

```bash
sudo systemctl status ou-mrs.timer ou-mrs.service ou-mrs-dashboard.service
sudo journalctl -u ou-mrs.service -f -n 50
venv/bin/python3 backtest.py
BT_REGIME_FILTER=CHOP,RANGE venv/bin/python3 backtest.py
venv/bin/python3 walk_forward.py
```

For full ops cheatsheet, see Master Audit Part 7.

## Phase history (recent)

- **9.5d-g** -- NF stop-fix, PFM sticky halt, dashboard truth wire, trail-stop
- **9.6** -- SSE live ticks, dashboard pump
- **9.7b** -- Bug2 broker.symbol mutation, bug3 f-string fix, pre-market guard
- **9.8** -- Regime allow-list filter (CHOP+RANGE deployed)

## Risk disclaimers

- Past performance does not guarantee future results.
- Running an algo for your own account is fine. Outside capital triggers SEBI PMS / RA / IA registration requirements.
- Phase 9.8 backtest on 37-day FUT sample shows PF 1.363 with CHOP+RANGE filter; 142-day INDEX walk-forward shows near break-even on longer samples. Currently a thin-edge mean-reversion play.

## Contact

Owner: Dipanshu Kumar (DevPilotX / ALLplay HQ)
