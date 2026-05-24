# 📈 OU-MRS — Ornstein-Uhlenbeck Mean-Reversion Strategy

> Live intraday Indian-futures bot built on a calibrated OU mean-reversion model with an ADX regime filter, walk-forward validation, Monte Carlo risk sims, and a FastAPI ops dashboard.

🔗 **Dashboard:** [algo.devpilotx.com](https://algo.devpilotx.com)
🧪 **Status:** Active research + paper / live toggle. Runs on **BankNifty / Nifty / FinNifty** futures via Angel One SmartAPI.

---

## 🧭 What it does

Trades a mean-reverting OU process fitted on log-prices, generates **z-score** signals around an estimated equilibrium, sizes positions by capital tier, and routes orders through an Angel One adapter. Identical signal logic powers backtests and live execution — what you backtest is what trades.

**Key features:**
- 📐 OU model with volume-weighted centering, half-life + R² gating
- 🌪️ **ADX regime filter** (Phase 8c) — skips entries during trending markets
- 📊 **Walk-forward validation** + Monte Carlo equity simulation
- 🧮 Capital tier sizing (`TINY / PAPER / FTMO_STARTER / FTMO_PRO / FTMO_ELITE`)
- 🎯 Multi-symbol (BNF / NF / FNF) with per-symbol state isolation
- 📡 Live signal feed for **Tradetron-compatible** consumers (`/api/signals.json`)
- 🛡️ Prop-firm monitor for live drawdown / kill switches
- 📺 **FastAPI dashboard** with bcrypt auth, equity curve, drawdown, daily P&L, live state, market-status, system health
- 🔁 systemd-driven scheduling (`ou-mrs.service` + `ou-mrs.timer`)

## 🧱 Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Numerics | `numpy`, `pandas` |
| Broker | **Angel One SmartAPI** (`angel_adapter.py`) |
| Dashboard | **FastAPI** + static HTML/JS, `bcrypt` + signed cookies (`itsdangerous`) |
| Ops | systemd unit + timer, log rotation |
| Telemetry | JSONL trade log, equity CSV, `psutil` system health |
| Config | `python-dotenv` (env-driven) |

## 🚀 Quickstart

```bash
git clone https://github.com/devpilotX/OU-MRS.git
cd OU-MRS
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt          # numpy, pandas, fastapi, uvicorn, bcrypt, psutil, …
cp .env.example .env                     # ANGEL_*, CAPITAL, INSTRUMENTS, LIVE, DASHBOARD_*

# 1) Validate offline first
python backtest.py
python walk_forward.py
python monte_carlo.py
python tearsheet.py

# 2) Paper-trade locally
LIVE=false bash run_bot.sh

# 3) Dashboard
uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
```

## 🗂️ Module map

```
OU-MRS/
├── strategy.py             # Pure OU signal logic (unit-testable, no I/O)
├── ou_mrs.py               # Live bot main loop (broker calls, state, kill switches)
├── ou_mrs_runner.py        # systemd-friendly entrypoint
├── run_bot.sh              # Rotates logs and execs ou_mrs.py
├── account.py              # Per-account + per-symbol state path helpers
├── angel_adapter.py        # Angel SmartAPI session, login, order routing
├── fetch_history.py        # 1m / 5m bar history fetch
├── backfill_historical.py  # Bulk historical pull
├── backtest.py             # Vectorized backtest engine
├── walk_forward.py         # Rolling-window OOS validation
├── monte_carlo.py          # Equity-path Monte Carlo simulator
├── size_sensitivity.py     # Position-size grid search
├── tearsheet.py            # Performance report / metrics
├── signal_publisher.py     # Tradetron-compatible signal feed
├── live_hook.py            # Bot → dashboard state bridge (state/live.json)
├── prop_firm_monitor.py    # Live drawdown / kill-switch checks
├── test_login.py           # Quick broker-login sanity check
├── tests/                  # Unit tests for strategy + signal math
├── bt_out/                 # Backtest artifacts (metrics.json, equity.csv, trades.csv)
├── data/                   # Historical bar caches
└── dashboard/
    ├── app.py              # FastAPI app: auth + 15+ API endpoints
    └── static/             # login.html, index.html, JS, CSS
```

## 📐 Strategy detail

Core estimator (`strategy.estimate_ou`) fits an OU process:

> `x_{t+1} = a + b · x_t + ε`,  where  `x_t = log(close_t) − log(volume-weighted close)`

It derives **half-life** `ln(2)/θ`, equilibrium **σ**, and **R²**, then gates entries by:

- `min_half_life ≤ half-life ≤ max_half_life` (default 1–15 bars)
- `R² ≥ min_r2` (default 0.05)
- ATR percentile in `[atr_pct_low, atr_pct_high]` (vol-regime band, 0.20–0.80)
- **ADX(14) ≤ adx_threshold** (default 25 — no entries in trending regime)
- Recent volume above mean (avoid thin liquidity)
- Z-score crosses `±z_entry` (default 1.5) with reversal momentum

Stops trigger at `±z_stop` (default 3.5). The signal function in `strategy.py` is **pure** — no I/O, no broker calls — so `backtest.py` and live `ou_mrs.py` consume the exact same logic.

## 📊 Dashboard endpoints (`dashboard/app.py`)

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Auth-gated dashboard shell |
| `GET /api/status` | Bot service + timer state, heartbeat, capital, live mode |
| `GET /api/trades` | Last 200 trades with cumulative P&L + win rate |
| `GET /api/log` | Tail of most recent dated log |
| `GET /api/metrics` | Latest backtest metrics |
| `GET /api/equity` | Equity curve rows |
| `GET /api/drawdown` | Equity peak + drawdown % series |
| `GET /api/daily-pnl` | Per-day trade count + P&L + wins |
| `GET /api/portfolio` | Live Angel portfolio snapshot via `state/live.json` |
| `GET /api/health` | CPU / RAM / disk / uptime (`psutil`) |
| `GET /api/market-status` | IST-aware open / closed / pre-open |
| `GET /api/strategy` | Active symbols, capital tier, z-thresholds, lot sizes |
| `GET /api/symbols` | Per-symbol live state (BNF/NF/FNF) + aggregate |
| `GET /api/live/state` | Raw live-state push from bot |
| `GET /api/signals.json` | Token-gated, Tradetron-compatible signal feed |
| `GET /api/export/trades` | CSV download |

Auth is bcrypt-checked against `DASHBOARD_USER` / `DASHBOARD_PASS_HASH`, with signed 7-day session cookies via `itsdangerous`.

## 🛣️ Roadmap

- [ ] Options-leg variant (writing IV-rich strangles into OU regime)
- [ ] Multi-strategy router with per-strategy capital allocation
- [ ] Postgres-backed trade journal (replacing JSONL)
- [ ] Discord / Telegram alerts on kill-switch + first fill of day

## ⚠️ Risk disclaimer

This is research code for educational use. Trading futures involves substantial risk and can result in significant losses. Paper-trade first, validate on out-of-sample data, and never deploy live capital you cannot afford to lose. **Not financial advice.**

---

## 👤 Author

**Dipanshu Kumar** — independent AI engineer, shipping consumer + finance + quant tools solo.

- 📧 [connect.dipanshukumar@gmail.com](mailto:connect.dipanshukumar@gmail.com)
- 🌐 [paisareality.com](https://paisareality.com) · [value.codes](https://value.codes) · [algo.devpilotx.com](https://algo.devpilotx.com)
- 🐙 [@devpilotX](https://github.com/devpilotX)

## 📄 License

Proprietary — all rights reserved.
