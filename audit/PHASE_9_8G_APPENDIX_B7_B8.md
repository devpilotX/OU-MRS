# Phase 9.8g — Appendix: B7 & B8 (CLI gap + per-symbol data gap)

*Discovered 25 May 2026 during backtest gate verification of PR #3. Both findings invalidate the original 9.8g backtest pass and forced PR #3 to remain draft.*

## B7 — `backtest.py` had no `--symbol` flag at all

### Symptom
All three audit runs against BANKNIFTY / NIFTY / MIDCPNIFTY produced **identical** trade counts, identical win rates, identical reason distributions. Only P&L magnitudes scaled — and only with `LOT_SIZE`, not with price-series characteristics.

```
BNF (lot 30):  trades=24  WR=54.17%  reasons={TIME_STOP_HL:15, Z_VEL_STALL:5, TARGET:4}
NF  (lot 65):  trades=24  WR=54.17%  reasons={TIME_STOP_HL:15, Z_VEL_STALL:5, TARGET:4}
MCN (lot 120): trades=24  WR=54.17%  reasons={TIME_STOP_HL:15, Z_VEL_STALL:5, TARGET:4}
```

Math confirmation (avg-win-pts per lot):
- BNF: 4587.84 / 30  = 152.93 pts
- NF:  9995.38 / 65  = 153.78 pts
- MCN: 18492.95 / 120 = 154.11 pts

Same underlying price series across all three. ✗

### Root cause
Inspection of `backtest.py` at commit `70081a4` revealed:
- **No `import argparse`**
- **No CLI parsing of any kind**
- `__main__` block consists of exactly `run()`
- Python silently ignored every `--symbol …` argument as unused argv
- Data source was governed solely by env var `BT_DATA`, default `data/BANKNIFTY_FUT_1min.parquet`

Every `--symbol BANKNIFTY/NIFTY/MIDCPNIFTY` invocation since the flag was first referenced in runbooks (unclear which phase, but present in PR #3 protocol) silently replayed BANKNIFTY data.

### Fix (commit 9.8g.8)
`backtest.py`:
- Added `import argparse` and `_parse_args()`
- New `--symbol` flag (choices: BANKNIFTY, NIFTY, MIDCPNIFTY) — auto-resolves `BT_DATA` to `data/<SYM>_FUT_1min.parquet` and auto-sets output dir to `bt_out_<SYM>/`
- New `--out` flag for explicit output dir override
- New `--auto-lot` flag — when used with `--symbol`, sets `LOT_SIZE` from the in-file `_SYMBOL_TO_LOT` map (BNF=30, NF=65, MCN=120) which is sourced from `data/instruments.db` per Sacred Rule #6
- Pre-flight existence check on `DATA` — clean error + remediation hint instead of opaque pandas crash
- `OUT.mkdir(...)` moved into `run()` so `--out` / `--symbol` mutation works
- Equity-chart title now includes the data-file stem so charts are self-identifying

## B8 — Algo has never been backtested on NIFTY or MIDCPNIFTY (ever)

### Symptom
```
$ ls -la data/*.parquet
-rw-rw-r-- 1 ubuntu ubuntu  319357 May 10 14:28 data/BANKNIFTY_FUT_1min.parquet
-rw-rw-r-- 1 ubuntu ubuntu  133920 Apr 23 13:30 data/BANKNIFTY_FUT_3min.parquet
-rw-rw-r-- 1 ubuntu ubuntu 1572617 May  4 22:44 data/BANKNIFTY_INDEX_1min.parquet
-rw-rw-r-- 1 ubuntu ubuntu 1514971 Apr 28 07:26 data/BANKNIFTY_INDEX_1min_tz.parquet
-rw-rw-r-- 1 ubuntu ubuntu  484227 Apr 23 13:58 data/BANKNIFTY_SPOT_3min.parquet
-rw-rw-r-- 1 ubuntu ubuntu 1326750 May 16 17:47 data/MIDCPNIFTY_INDEX_1min.parquet
```

No `NIFTY_FUT_1min.parquet`. No `MIDCPNIFTY_FUT_1min.parquet`. Only `MIDCPNIFTY_INDEX_1min` (index, not futures — basis ignored).

### Impact (severe)
- NIFTY has been live-paper-traded since Phase 9.7L (~15 May 2026)
- MIDCPNIFTY has been live-paper-traded since Phase 9.7AC (~19 May 2026)
- Neither symbol has been validated by backtest at any point in the algo's history
- Sacred Rule #19 ("never claim a feature works until observed in live or backtest") is violated in spirit — we made the live claim without a backtest leg

### Root cause
- `fetch_history.py` uses `angel_adapter.AngelBroker` which is hardcoded to `BANKNIFTY_FUT_TOKEN` / `BANKNIFTY_FUT_SYMBOL` via `__init__`
- No multi-symbol historical fetcher has ever existed in the repo
- Multi-symbol live trading (Phase 8g `phase-8g-multi-instrument` branch) added live execution paths but no historical-data plumbing

### Fix (commit 9.8g.8)
New `tools/fetch_futures_data.py`:
- Standalone script — uses `SmartConnect` directly to bypass the BANKNIFTY-locked adapter
- `--symbol {BANKNIFTY,NIFTY,MIDCPNIFTY}` or `--all`
- `--days` lookback (default 60)
- Reads `NIFTY_FUT_TOKEN` and `MIDCPNIFTY_FUT_TOKEN` from `.env` (current monthly expiry)
- Writes to `data/<SYM>_FUT_1min.parquet` in the format `backtest.py` expects
- Handles chunked fetching (Angel API caps at ~30 days per call), de-dups, sorts, filters market hours

### Limitation (known, documented)
The new fetcher only pulls data within the **current expiry's history window** (typically ~25 trading days). Stitching multiple expiries across months requires expired-token API access, which is scoped to **Tier B-0j** on the roadmap.

For the immediate PR #3 backtest gate, ~25 days × 3 symbols is sufficient to produce per-symbol non-identical metrics and confirm B3/B7 fixes are valid across instruments.

## New Sacred Rules introduced by 9.8g.8

### Sacred Rule #38
Every CLI flag claimed in docs, runbooks, or commit messages **must be backed by `argparse` and unit-tested**. Silently-ignored flags are dangerous — they create the illusion of differentiated runs while producing identical output. Before relying on a flag, grep the script for `argparse` or explicit argv parsing.

### Sacred Rule #39
Per-symbol backtest data must exist **before** the algo goes live on that symbol. No live-paper-trading a new symbol without a verified backtest parquet of at least 30 trading days under the same `OU_ATR_MULT` / `BT_REGIME_FILTER` / `BT_CAPITAL` settings as the live tier. Add the symbol to `tools/fetch_futures_data.py`, fetch the data, run `backtest.py --symbol <NEW>`, archive the `metrics.json`, then enable in `INSTRUMENTS` env var.

## PR #3 status — STILL DRAFT

Do not merge until:
1. `tools/fetch_futures_data.py --all --days 60` completes successfully on VPS
2. `data/NIFTY_FUT_1min.parquet` and `data/MIDCPNIFTY_FUT_1min.parquet` both exist with `>= 30` trading days
3. `backtest.py --symbol BANKNIFTY`, `--symbol NIFTY`, `--symbol MIDCPNIFTY` all produce **distinct** `metrics.json` (different trade counts and/or different reason distributions, not just lot-scaled P&L)
4. At least one of the three runs has non-zero `TRAIL_STOP` count in `reasons` (B3 verification — needs data with deep enough peak-to-trough moves)
5. Manual edits to `ou_mrs.py` (B1 / B2 / B4) applied per `audit/PHASE_9_8G_AUDIT.md`
6. Final pre-merge backtest re-run with the manual `ou_mrs.py` edits committed (commit 9.8g.9 placeholder)

Only then squash-merge into `phase-9.8f-bloomberg`, restart bot when flat, observe one clean trading day, and rate.
