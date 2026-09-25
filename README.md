# OU-MRS — Ornstein–Uhlenbeck Mean-Reversion Strategy

Intraday systematic mean-reversion algorithm trading three Indian index futures (BANKNIFTY, NIFTY, MIDCPNIFTY) on monthly expiries via the Angel One API.

**Status:** Paper trading mode. **LIVE deployment target:** end of July 2026 (after 2 months of additional paper observation per current plan).

**Latest (2026-05-30):** CI green (204 tests passing); test suite made hermetic and prop-firm halt-state isolated (`OU_PFM_HALT_PATH`); validation master report regenerated honestly for all 3 symbols; dashboard `/healthz` liveness probe added. Honest backtest (2026-03-30 → 05-26, 1-lot, capital-isolated): **BNF +₹9,045** (PF 1.85, Sharpe 2.62), **MCN +₹7,252** (PF 1.97), **NIFTY −₹10,727** (PF 0.49 — no robust mean-reversion edge; kept effectively short-only / disabled).

---

## 📊 Current state

_Source: `state/pfm.json`, updated 2026-05-27 via `scripts/pfm_snapshot.sh`_

| Metric | Value |
|---|---|
| Peak equity | ₹42,00,491 |
| Cumulative paper P&L | +₹1,84,275 |
| Days traded | 14 |
| Best day | +₹2,80,040 |
| Active instruments | **BNF, MCN** (NF disabled — see Phase 9.8h.K) |
| Bot mode | `LIVE=false` (paper) |

### Live phase stack

| Phase | Component | Effect |
|---|---|---|
| 9.7AL.1 | Dual-cap sizing | min(margin_cap, notional_cap × 3x leverage) |
| 9.7AN | Daily kill switch | Aggregate P&L ≤ -₹50,000 → all runners flat |
| 9.7AO | Tight stops | z ≥ 2.5 entry, ATR × 1.2 stop |
| 9.7AP | Paper-side SL + BE ratchet | At +1×ATR, stop ratchets to breakeven |
| 9.7AQ | NF lot reverted to 65 | Filter discipline restored |
| 9.8h.C.1 | NF disabled | Walk-forward failed; PF 0.45, WF 0.00 |
| **9.8h.L.1** | **Auto-compounding capital** | CAPITAL reads `pfm.json[peak_equity]` at startup |
| **9.8h.M** | **Auto-rollover script** | Next-month FUT symbol/token patching from instruments.db |

---

## 🧪 Backtest evidence (Phase 9.8h.L deep BT, 57-day window)

_Window: 2026-03-30 → 2026-05-26, armor stack default, 1-lot baseline (capital-isolated)._
_Methodology: walk-forward 3 splits + Monte Carlo bootstrap 10,000 paths._

| Symbol | N | PnL | PF | Sharpe | PSR | MaxDD | WF | Gate | MC prob(+) |
|---|---|---|---|---|---|---|---|---|---|
| **BANKNIFTY** | 17 | **+₹4,550** | 1.65 | **3.55** | **0.814** | -0.08% | 0.67 | **PASS 5/5** | 82.8% |
| **MIDCPNIFTY** | 15 | **+₹1,760** | 1.83 | **2.75** | **0.792** | -0.03% | 0.67 | **PASS 5/5** | 73.8% |
| NIFTY | 22 | -₹5,510 | 0.45 | -5.15 | 0.085 | -0.18% | 0.00 | FAIL 1/5 | 6.3% |
| Portfolio (all 3) | 54 | +₹799 | 1.04 | 0.26 | 0.547 | -0.17% | 0.67 | CONDITIONAL 3/5 | 54.3% |
| **Portfolio (BNF+MCN)** | 32 | **+₹6,310** | — | — | — | — | — | **PASS** (both gates) | — |

**Acceptance gates:** PSR ≥ 0.5, PF > 1.2, MaxDD% < 8%, WF consistency ≥ 0.6, win rate > 45%.

**Verdict:** BNF + MCN clear all gates with statistical confidence. NF fails on PF, Sharpe, PSR, and WF — keep disabled until N≥30 trades with re-evaluation in Aug 2026 (see `audit/phase_9_8h_K_nf_revival.md`).

---

## 🏗 Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Angel One API (REST + WebSocket)                          │
│  • LTP feed (per-second)                                   │
│  • Historical candles (1-min)                              │
│  • Order placement (paper sim in LIVE=false)               │
└─────────────────────────┬──────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────┐
│  ou_mrs.py — main runtime                                  │
│  • Per-symbol OuMrsRunner                                  │
│  • OU half-life estimation (rolling)                       │
│  • Z-score entry (|z|≥z_entry)                             │
│  • Multi-gate: regime, vol, ATR%, vol-band exclusion       │
│  • Multi-stop: paper SL, BE ratchet, trail, z-vel-stall,   │
│    time stop on HL, target, daily kill                     │
└─────────────────────────┬──────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────┐
│  state/                                                    │
│  • pfm.json            (peak equity, cumulative P&L)       │
│  • live_<SYM>.json     (per-symbol position snapshot)      │
│  • primary/equity.jsonl (daily equity curve)               │
│  • heartbeat.jsonl     (per-30s tick)                      │
│  • candle_cache_<SYM>.parquet (persistent OHLCV cache)     │
└────────────────────────────────────────────────────────────┘
```

### Key strategy parameters (from `.env`)

| Knob | Current | Description |
|---|---|---|
| `OU_Z_ENTRY` | 1.5 | Standardized residual entry threshold |
| `OU_Z_STOP_NF` / `_BNF` / `_MCN` | 2.5 / 3.5 / 3.5 | Per-symbol stop-z |
| `OU_HL_MIN` / `OU_HL_MAX` | 0.5 / 5.0 | Half-life acceptance band (bars) |
| `OU_ADX_THRESHOLD` | 32 | ADX above → trend regime (skip) |
| `OU_REGIME_FILTER` | CHOP,RANGE | Allowed regimes |
| `OU_PAPER_SL_ATR_MULT` | 1.5 | Stop distance multiplier |
| `OU_TRAIL_TRIGGER_ATR_MULT` | 1.5 | Trail activation distance |
| `OU_TRAIL_LOCK_PCT` | 0.40 | Trail lock fraction |
| `OU_VOL_CONFIRM` / `OU_ATR_PCT_FILTER` | on / on | Volatility gates |
| `NOTIONAL_LEVERAGE_MAX` | 3.0 | Notional / capital ceiling |
| `DAILY_LOSS_LIMIT` | -50,000 | Aggregate kill switch (₹) |
| `INSTRUMENTS` | BNF,MCN | Active symbols (NF disabled 9.8h.C.1) |

---

## 🔧 Capital scaling

Sizing is **dual-capped and capital-proportional**. At startup, `CAPITAL` is resolved as:

```python
CAPITAL = max(env.CAPITAL, pfm.peak_equity)  # Phase 9.8h.L.1
```

Disable auto-compounding with `OU_DISABLE_AUTO_CAPITAL=1` (deterministic backtests).

For each entry, `_cap_lots(capital, symbol)` computes:

```
margin_cap   = capital // margin_per_lot       (e.g. ₹35L / ₹65k = 53 BNF lots)
notional_cap = capital * 3.0 / (spot * lot_size)  (3x notional leverage ceiling)
max_lots     = min(margin_cap, notional_cap)
```

Then per-trade `size_lots(runner, atr)` applies a 0.5% risk budget on stop distance (HEDGE_FUND tier).

### Sizing table at current spots

| Capital | BNF lots | NF lots | MCN lots | Notional/trade |
|---|---|---|---|---|
| ₹1L | 1 | — (sub-margin) | — | ~₹16L |
| ₹10L | 5 | 4 | 2 | ~₹50L |
| **₹42L** (peak) | **7** | **7** | **6** | **~₹1.3Cr** |
| ₹1Cr | 18 | 19 | 16 | ~₹3.0Cr |
| ₹5Cr | 90 | 96 | 84 | ~₹15Cr |

At ₹5Cr capital the bot would trade ~15× larger than today, with the 3× notional leverage ceiling preventing the 19 May 20.6x-leverage incident from recurring.

---

## 📂 Repo layout

```
ou-mrs/
├── ou_mrs.py           # main runtime (~2000 lines)
├── backtest.py         # CLI backtest harness
├── ou_core.py          # OU estimator, signal generation
├── angel_adapter.py    # broker shim (live + paper)
├── compute_costs.py    # round-trip cost model
├── prop_firm_monitor.py # PFM equity/consistency tracker
├── dashboard/          # Bloomberg-style web dashboard (Phase 9.8h.J2)
├── audit/              # phase audit docs (Markdown)
├── validation/         # per-phase metrics + walk-forward JSON
├── scripts/
│   ├── pfm_snapshot.sh                  # snapshot pfm.json from runtime state
│   ├── sync_instruments.py              # refresh data/instruments.db
│   ├── rollover_to_next_expiry.py       # Phase 9.8h.M — next-expiry FUT rollover
│   └── check_env_dups.py                # detect duplicate .env keys
├── state/              # runtime state (pfm.json, live_*.json, equity.jsonl, ...)
├── data/
│   ├── instruments.db                   # Angel scripmaster
│   ├── BANKNIFTY_FUT_1min.parquet       # historical 1-min OHLCV (57 days)
│   ├── NIFTY_FUT_1min.parquet
│   └── MIDCPNIFTY_FUT_1min.parquet
├── bt_out/             # backtest outputs (per-phase)
├── trades.jsonl        # all closed trades (repo root)
└── .env.example        # config template (real .env is gitignored)
```

---

## 🛡 Risk controls

1. **Dual-cap sizing** (9.7AL.1): margin & notional both capped; 3× notional leverage max.
2. **Daily kill switch** (9.7AN): -₹50,000 aggregate ⇒ all runners squared off; no re-entry today.
3. **Per-symbol z_stop** (9.7j): per-symbol stop multipliers; BNF tighter than NF.
4. **Paper-side SL** (9.7AP): bot-level stop fires before broker SL trigger; protects against gap moves.
5. **BE ratchet** (9.7AP): at +1×ATR profit, stop moves to breakeven; locks no-loss.
6. **Trail stop** (active): at +1.5×ATR, trails 40% of profit.
7. **Time stop on HL** (9.7-baseline): exit after `OU_HL_MAX × bars` if not at target.
8. **Z-velocity stall** (9.7-baseline): exit if mean-reversion velocity decays.
9. **Square-off** (15:15 IST): all positions closed before EOD.
10. **EOD shutdown** (15:30 IST): bot exits cleanly, flushes state.
11. **NF disabled** (9.8h.C.1): structurally unprofitable on this strategy.

---

## ⏰ Operations

- **`ou-mrs.timer`** — auto-launches the bot Mon–Fri at 09:14 IST
- **Bot internal EOD** — 15:30 IST clean exit, state flushed
- **`ou-mrs-eod.timer`** — EOD report service at 15:35 IST
- **`ou-mrs-rollover.timer`** (planned Phase 9.8h.M) — fires day-before-expiry at 16:00 IST

---

## 📈 Phase ledger

Recent phases (full history in `audit/`):

| Phase | Description | PR |
|---|---|---|
| 9.8h.B | Slippage stress walk-forward | merged |
| 9.8h.C.1 | NF disable based on B.5 evidence | merged |
| 9.8h.E | Bloomberg-grade rebuild scoping | merged |
| 9.8h.F | A4 verify + carryover | merged |
| 9.8h.G | Retraction + scoping | merged |
| 9.8h.H | Phase H closeout | PR #25 |
| 9.8h.I | Phase I closeout | PR #26 |
| 9.8h.J/J2 | Premium dashboard + algo health revert | PR #27 |
| **9.8h.K** | **NF revival investigation (keep disabled)** | **PR #28** |
| **9.8h.L** | **Auto-compounding capital + deep BT (this phase)** | **PR #29** |
| **9.8h.M** | **July expiry auto-rollover script** | **PR #29** |

---

## 🚀 Quickstart (operators)

```bash
# 1. Clone
git clone git@github.com:devpilotX/OU-MRS.git
cd OU-MRS

# 2. Python env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Config
cp .env.example .env
#  Edit .env: set ANGEL_*, CAPITAL, LIVE=false, etc.

# 4. Refresh scripmaster (run once daily)
venv/bin/python scripts/sync_instruments.py

# 5. Backtest
venv/bin/python backtest.py --symbol BANKNIFTY --out bt_out/

# 6. Live (paper) run
venv/bin/python ou_mrs.py
```

---

## ⚠️ Constraints (hard rules)

- **Never** `git add .env` — credentials must stay out of the repo.
- **Never** patch lot sizes or instrument tokens from memory; always verify against `data/instruments.db` (Angel scripmaster).
- **Never** disable a STOP because it correlates with recent losses (survivorship bias).
- **Never** restart the bot when a position is open; verify flat first.
- **Dashboard is owned by a separate operator (Opus 4.7);** do not modify dashboard code paths from the algo workstream.

---

## 📚 Documentation

- `audit/phase_9_8h_*.md` — per-phase decision records
- `validation/phase_9_8h_*.json` — quantitative gate results
- `bt_out/eod/YYYY-MM-DD.md` — daily EOD recaps (auto-generated 15:35 IST)

---

_OU-MRS is a research / paper-trading system. No real capital at risk. Not financial advice._
