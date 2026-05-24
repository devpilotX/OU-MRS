# 📈 OU-MRS — Ornstein-Uhlenbeck Mean-Reversion Strategy

> Live intraday Indian-futures bot built on a calibrated OU mean-reversion model, ADX regime filter, walk-forward + Monte Carlo validation, tier-aware sizing, and a hardened risk-armor stack.

🔗 **Public dashboard:** [algo.devpilotx.com](https://algo.devpilotx.com) *(separate project, owned by another engineer — this repo contains the algo only)*
🧪 **Mode:** Paper · 💰 **Capital:** ₹37,50,000 · 📊 **Net P&L all-time:** +₹1,77,428 over 19 trades (68% win rate) · Sharpe **1.32** / Sortino **1.41** / Calmar **7.86** (20d rolling)

---

## 🎯 Symbols & instruments

Indian index futures via **Angel One SmartAPI**:

| Code | Instrument | Notes |
|------|------------|-------|
| **BNF** | BANKNIFTY futures | Primary symbol, deepest backtest coverage |
| **NF**  | NIFTY futures     | Lot size **65** (Phase 9.7AQ — reverted AM's 75 after Angel scripmaster verification) |
| **MCN** | MIDCPNIFTY futures | Added Phase 8g multi-instrument |

## 🌳 Branches & phase progression

The project ships across multiple phase branches. **Production runs from `phase-9.8f-bloomberg`** — `main` is the stable Phase 8j baseline kept for reference.

| Branch | Phase | Status | What it adds |
|--------|-------|--------|--------------|
| `main` | 8j+8j.5 | 🟢 Stable baseline | Multi-symbol core, ADX regime filter, FastAPI state bridge |
| `phase-8f-capital-sizer` | 8f | 📦 Historical | Per-account capital sizer |
| `phase-8g-multi-instrument` | 8g | 📦 Historical | Multi-symbol orchestration (BNF / NF / MCN) |
| `phase-9.8d-dashboard-stabilization` | 9.8d | 🟡 Feature | Dashboard reliability fixes |
| `phase-9.8e-calendar-and-ui` | 9.8e | 🟡 Feature | NSE calendar awareness + UI polish |
| **`phase-9.8f-bloomberg`** | **9.8f** | 🔴 **Live** | Bloomberg-style quant terminal + full risk armor stack |

### Tag highlights (recent)

- **`phase-9.7AQ-revert-am`** (21 May 2026) — reverts NF lot_size 75→65 after Angel scripmaster verification
- **`phase-9.7AP-paper-sl-trail`** — paper-side STOP enforcement + breakeven ratchet at peak ≥ 1.0×ATR
- **`phase-9.7AO-tight-stops`** — `OU_Z_STOP_{BNF,NF,MCN}=2.5` (was 3.5), `OU_ATR_MULT=1.2` (was 1.5)
- **`phase-9.7AN-daily-loss-kill`** — `DAILY_LOSS_LIMIT=-50000` env kill switch on aggregate breach
- **`phase-9.7AL-notional-cap`** — fix for 20.6× BNF leverage blowup risk; dual-cap `max_lots = min(margin_cap, 3× notional_cap)`
- **`phase-9.7AK-restore`** — restored AF-dash original 7-tab layout (KPI cards, Z-score gauge, intraday chart, L2 depth)

## 🛡️ Risk armor stack (May 2026 hardening)

Following a 19 May audit that surfaced a 20.6× leverage anomaly and Z_VEL_STALL alpha-decay, the bot now ships with **5 layers of defense in depth**:

1. **Notional leverage cap** — `NOTIONAL_LEVERAGE_MAX=3.0`, reduces BNF max 50→7, NF 28→6, MCN 16→6
2. **Dual-cap max_lots** — `min(margin_cap, notional_cap)`, prevents OuMrsRunner inline bypass
3. **Daily loss kill** — `DAILY_LOSS_LIMIT=-50000`, kills all runners on aggregate breach
4. **Tight stops** — `Z_STOP=2.5`, `ATR_MULT=1.2` (was 3.5 / 1.5)
5. **Paper-side STOP enforcement** — breakeven ratchet at peak ≥ 1.0×ATR (paper broker previously never simulated SL fills)

## 🧭 What it does

Trades a mean-reverting OU process fitted on log-prices, generates **z-score** signals around an estimated equilibrium, sizes positions by capital tier under regime + drawdown constraints, and routes orders through Angel One. Identical signal logic powers backtests and live execution — **what you backtest is what trades**.

## 🧱 Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ (pinned via `.python-version`) |
| Numerics | `numpy`, `pandas` |
| Broker | **Angel One SmartAPI** (`angel_adapter.py`) |
| Ops | systemd unit + timer, log rotation, nginx SSE proxy |
| Telemetry | JSONL trade log, equity CSV, EOD markdown reports |
| Config | `python-dotenv`, `requirements.lock` for reproducible builds |
| Validation | Backtest grid (`tools/backtest_phase97aa.py`), walk-forward, Monte Carlo, tearsheet |

## 🚀 Quickstart

```bash
git clone https://github.com/devpilotX/OU-MRS.git
cd OU-MRS
git checkout phase-9.8f-bloomberg   # live branch
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # fill Angel credentials + instrument tokens

# 1) Validate offline first
python backtest.py && python walk_forward.py && python monte_carlo.py && python tearsheet.py

# 2) Paper-trade locally (LIVE=false in .env)
./run_bot.sh
```

**Required env** (see `.env.example`): `ANGEL_API_KEY`, `ANGEL_API_SECRET`, `ANGEL_CLIENT_CODE`, `ANGEL_MPIN`, `ANGEL_TOTP_SECRET`, per-symbol `*_FUT_SYMBOL` + `*_FUT_TOKEN` (rotate every expiry), `LIVE`, `CAPITAL`, `INSTRUMENTS`.

**Strategy knobs:** `OU_ADX_THRESHOLD=30`, `OU_Z_ENTRY=1.5`, `OU_HL_MULTIPLIER=5.0`, `OU_Z_VEL_STALL=1.0`, `OU_VEL_STALL_BARS=2`, `OU_REGIME_FILTER`, plus risk-armor overrides (`NOTIONAL_LEVERAGE_MAX`, `DAILY_LOSS_LIMIT`, `OU_Z_STOP_{BNF,NF,MCN}`, `OU_ATR_MULT`, `OU_TRAIL_TRIGGER_ATR_MULT`, `OU_TRAIL_LOCK_PCT`).

## 🗂️ Module map (live branch)

```
OU-MRS/
├── strategy.py             # Pure OU signal logic (no I/O, unit-testable)
├── strategy_trend.py       # Phase 9.12 trend companion (SCAFFOLD ONLY, NOT WIRED)
├── regime.py               # Phase 8h.2: Wilder ADX classifier → TREND/RANGE/CHOP
├── sizing.py               # Phase 9.5a: adaptive sizing (DD + cushion + regime + vol)
├── tier_policy.py          # Phase 8p.2: tier-aware params (SEED/GROWTH/INST/HF/QE)
├── cost_model.py           # Phase 9.5c: realistic FnO round-trip costs (STT, GST, stamp)
├── ou_mrs.py               # Live bot main loop (42KB; broker, state, kill switches)
├── ou_mrs_runner.py        # systemd-friendly entrypoint with dual-cap max_lots
├── run_bot.sh              # Rotates logs + execs ou_mrs.py
├── account.py              # Per-account + per-symbol state path helpers
├── angel_adapter.py        # Angel SmartAPI session, login, order routing
├── latency.py              # Order → fill latency tracking
├── tick_capture.py         # Live tick recorder for replay backtests
├── fetch_history.py        # 1m / 5m bar history fetch
├── backfill_historical.py  # Bulk historical pull
├── backtest.py             # Vectorized backtest engine (11KB)
├── walk_forward.py         # Rolling-window OOS validation
├── monte_carlo.py          # Equity-path Monte Carlo simulator
├── size_sensitivity.py     # Position-size grid search
├── tearsheet.py            # Performance metrics report
├── signal_publisher.py     # Tradetron-compatible signal feed
├── live_hook.py            # Bot → dashboard state bridge (state/live.json)
├── prop_firm_monitor.py    # Live drawdown / kill-switch checks
├── deploy_p97{k,L,M,N}.sh  # Phase-tagged deploy scripts
├── tools/                  # Ops + audit utilities
│   ├── backtest_phase97aa.py # 16-config grid harness (vc × ap × hl × zvel)
│   ├── eod_report.py         # Daily PnL + exit-reason markdown report
│   ├── filter_audit.py       # Filter-skip audit
│   ├── skip_audit.py         # Entry-skip distribution
│   ├── fut_token_sweep.py    # Expiry-rollover token sweep
│   ├── backfill_mcn_historical.py
│   ├── p97s_portfolio_oneshot.py
│   └── watch_live.sh         # tail-multiplex live state
├── audit/                  # Audit artifacts + reports
├── validation/             # Walk-forward + backtest validation suites
├── archive/                # Pre-fix snapshots
├── bt_out/                 # Backtest artifacts (metrics.json, equity.csv, trades.csv)
├── data/                   # Historical bar caches
├── dashboard/              # State-bridge files consumed by the public dashboard project
├── scripts/                # One-off helpers
└── tests/                  # Unit tests for strategy + signal math
```

## 📐 Strategy detail

`strategy.estimate_ou` fits an AR(1) model on log-prices:

> `x_{t+1} = a + b·x_t + ε`, where `x_t = log(close) − log(volume-weighted close)`

Derives **half-life** `ln(2)/θ`, equilibrium **σ**, and **R²**, then gates entries on:

- `min_half_life ≤ half-life ≤ max_half_life`
- `R² ≥ 0.05`
- ATR percentile in `[0.20, 0.80]` (vol-regime band)
- **ADX(14)**: regime = TREND (>25, blocked), CHOP (20–25, neutral), RANGE (<20, edge expected) via `regime.classify_regime`
- Recent volume above mean (avoid thin liquidity)
- Z-score crosses `±OU_Z_ENTRY` with reversal momentum
- Per-symbol Z-stop: `OU_Z_STOP_{BNF,NF,MCN}=2.5`

Velocity-stall (`Z_VEL_STALL`) was identified as the dominant exit-killer (3/3 losses, -₹2.47L) and is disabled via `OU_DISABLE_Z_VEL_STALL=on`.

## 🏛️ Capital tiers (`tier_policy.py`)

| Tier | Capital range | Max lots | Risk/trade | Daily loss cap | Concurrent | Z-entry |
|------|---------------|----------|------------|----------------|------------|---------|
| SEED | < ₹2L | 2 | 1.0% | 1.5% | 1 | 1.5 |
| GROWTH | ₹2L–15L | 50 | 0.8% | 1.5% | 2 | 1.5 |
| INSTITUTIONAL | ₹15L–25L | 50 | 0.6% | 1.2% | 3 | 1.4 |
| HEDGE_FUND | ₹25L–50L | 50 | 0.5% | 0.8% | 3 | 1.4 |
| QUANT_ELITE | ≥ ₹50L | 50 | 0.4% | 0.6% | 3 | 1.3 |

Institutional pattern: as capital grows, risk % per trade **shrinks**, concurrency **grows**, stops **widen**, and entry threshold **lowers** (LLN smooths variance across more concurrent trades).

## 💸 Cost model (`cost_model.py`, Phase 9.5c)

Realistic Indian F&O round-trip costs baked into backtests:

- Brokerage ₹20/order × 2
- STT 0.0125% on sell notional (side-aware)
- Exchange txn 0.0019%
- SEBI 0.0001%
- GST 18% on (brokerage + txn + sebi)
- Stamp duty 0.002% on buy notional

## 🛣️ Roadmap

- [ ] **Phase 9.12: Trend strategy** — `strategy_trend.py` skeleton ready; activation gate is 6 months TREND backtest + Sharpe ≥ 1.5 + 4-fold walk-forward
- [ ] Wire `sizing.adaptive_size_lots` into `ou_mrs.py` (currently only imported by tests/tools)
- [ ] Postgres-backed trade journal (replacing JSONL)
- [ ] Options-leg variant (writing IV-rich strangles into OU regime)
- [ ] Discord / Telegram alerts on kill-switch + first fill of day

## ⚠️ Risk disclaimer

Educational use only. Past performance does **not** predict future returns. Indian F&O losses **can exceed deposits**. Paper only — do not flip `LIVE=true` without:

1. Walk-forward validation on the active config
2. 30 paper sessions post-armor without incident
3. Independent risk review

Not financial advice.

---

## 👤 Author

**Dipanshu Kumar** — independent AI engineer.
📧 [connect.dipanshukumar@gmail.com](mailto:connect.dipanshukumar@gmail.com)
🌐 [paisareality.com](https://paisareality.com) · [value.codes](https://value.codes) · [algo.devpilotx.com](https://algo.devpilotx.com)
🐙 [@devpilotX](https://github.com/devpilotX)

## 📄 License

Proprietary — all rights reserved.
