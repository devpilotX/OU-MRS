# Phase 9.8h.B.1 — 12 May 2026 -₹162k Incident Forensics

**Branch:** `phase-9.8h.B.1-may12-forensics`
**Date authored:** 27 May 2026
**Status:** Root cause confirmed. Armor coverage verified (Phase 9.7AP). Optional defense-in-depth identified.
**Sacred Rule trigger:** #20 (every loss day > ₹50k requires a written forensic).

---

## 0. TL;DR

The May 12 net -₹162,103 day was **a single BANKNIFTY long trade** that lost **-₹199,749** in 103 minutes (partly masked by an unrelated NIFTY winner of +₹37,645).

The BANKNIFTY trade was a textbook **mean-reversion regime failure**:

1. Bot entered long at 12:29 on z=-1.50 (oversold signal).
2. Within 3 minutes the regime flipped to strong downtrend (ADX 43-45).
3. Z-score never blew out to the Z_STOP threshold of 2.5 because the rolling mean trended down with price (z stayed in -1.5 to -1.8 the entire trade).
4. Soft Z_VEL_STALL eventually fired at 14:12 by which time the position was -238 pts (6.7× ATR adverse) and -₹199,749.

**Counter-factual:** The Phase 9.7AP paper-side stop-loss at 1.5×ATR would have force-exited at 12:32 (3 minutes after entry) at 53926, capping the loss at -₹48,681 and **saving ₹151,068** on this single trade. Phase 9.7AP was deployed 21 May 2026, **AFTER** this incident. The May 12 trade is exactly why 9.7AP exists.

**Verdict:** Existing armor stack (9.7AN daily kill + 9.7AO z≥2.5 tighten + 9.7AP paper-side SL) covers this failure mode. **No live `.env` change recommended.** One optional defense-in-depth (regime-conflict force-exit) is logged as a future R&D item.

---

## 1. Trade ledger reconstruction

From `trades.jsonl`, May 12 2026 contains 2 trades:

| # | Symbol* | Side | Entry ts | Entry px | Exit ts | Exit px | Qty | Reason | PnL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | NIFTY | SELL | 11:57:08 | 23,649.6 | 12:03:38 | 23,628.0 | 34 | TARGET | **+₹37,645** |
| 2 | **BANKNIFTY** | **BUY** | 12:29:07 | 53,979.4 | **14:12:06** | 53,760.2 | 29 | **Z_VEL_STALL** | **-₹199,749** |

* `trades.jsonl` rows currently lack a `symbol` field — a data-quality gap discovered while authoring this report (see §6). Symbols inferred from price magnitude (NIFTY ~23k, BANKNIFTY ~53k, MIDCPNIFTY ~13k).

**Net May 12: -₹162,103.54.** Matches the figure flagged in the OU-MRS instructions page (Sacred Rule #20 incident).

The live log archive `logs/ou_mrs_20260512_091400.log` shows an additional NIFTY scalp at 13:19→13:30 (SELL 36l @ 23597.30 → 23579.00, +₹32,164), which does not appear in `trades.jsonl`. Suspected ledger desync — secondary; not core to this incident. Logged for future cleanup.

---

## 2. The BANKNIFTY catastrophe — log evidence

Grep of `logs/ou_mrs_20260512_091400.log` over 12:25-14:15 (BANKNIFTY-relevant lines only):

```
12:29:07  ENTRY BUY 29l @ 53979.40 z=-1.71 hl=4.6        ← LONG entry, oversold signal
12:34:08  [regime] skip: adx=43.55 > 28.0 (TREND)         ← TREND regime detected, NEW entries blocked
12:35:09  [regime] skip: adx=41.06 > 28.0 (TREND)
12:38:09  [regime] skip: adx=44.70 > 28.0 (TREND)
13:19:08  ENTRY SELL 36l @ 23597.30 z=1.58 hl=4.8         ← (NIFTY scalp, unrelated)
13:30:37  EXIT (Z_VEL_STALL) @ 23579.00 pnl=Rs32164       ← (NIFTY exit)
13:39:07  [regime] skip: adx=29.47 > 28.0 (TREND)
14:12:06  [PAPER] EXIT SELL 29l
14:12:06  EXIT (Z_VEL_STALL) @ 53760.20 pnl=Rs-199749     ← BANKNIFTY EXIT, 103 min after entry
14:12:06  [regime] skip: adx=28.93 > 28.0 (TREND)         ← STILL trending at exit
```

Note `hl=4.6` at entry — that's half-life of mean reversion in hours, well inside the OU_HL_MAX=5.0 filter (i.e., the entry passed all filters at the time).

**Exit reason was Z_VEL_STALL (soft), not Z_STOP (hard).** This means the z-score never reached the configured ±2.5 stop level. The regime filter correctly identified the trend within 3-5 minutes of entry, but it had — and still has — only entry-blocking semantics, not force-exit semantics on existing positions.

---

## 3. Price action and indicator reconstruction

From `data/BANKNIFTY_FUT_1min.parquet` (refetched 27 May 2026), window 12:25-14:15:

```
highest high:    54,081.80  at  12:25:00          (just before entry)
lowest low:      53,741.20  at  14:12:00          (at exit)
vs entry 53,979.40:   high +102.4 pts   low -238.2 pts
close at 14:12: 53,770.00
ATR(14) at entry minute: 35.6 pts                  ← compressed vol pre-breakdown
Derived lot multiplier (from actual pnl): 31.42    ← matches BANKNIFTY contract size
```

Approximate z-score reconstruction (rolling 60-bar mean/std on close):

| Time | Close | Roll mean | Roll std | z |
|---|---|---|---|---|
| 12:29 (entry) | 54,028.60 | 54,073.48 | 29.98 | **-1.50** |
| 12:45 | 53,907.60 | 54,018.49 | 89.06 | -1.25 |
| 13:00 | 53,890.00 | 53,953.20 | 107.68 | -0.59 |
| 13:15 | 53,972.60 | 53,912.44 | 88.55 | +0.68 |
| 13:30 | 53,960.00 | 53,892.67 | 57.83 | +1.16 |
| 13:45 | 53,825.00 | 53,904.65 | 62.87 | -1.27 |
| 14:00 | 53,824.80 | 53,913.41 | 54.29 | -1.63 |
| 14:12 (exit) | 53,770.00 | 53,896.58 | 70.53 | **-1.79** |

**The rolling mean tracked the price down.** Z never approached ±2.5. This is the structural failure mode of z-score stops in trending markets.

**Adverse excursion = 238 pts = 6.7× ATR(14).** Extreme outlier vs the bot's parameterized world (OU_ATR_MULT=1.2, OU_PAPER_SL_ATR_MULT=1.5).

---

## 4. Armor counter-factual

All exits priced at the relevant bar's close. Lot multiplier 31.42, qty 29.

| Armor | Source | Would-have-triggered | Hypo exit | Hypo PnL | Loss prevented |
|---|---|---|---|---|---|
| **Paper-side SL 1.5×ATR** | **Phase 9.7AP (live 21 May)** | **12:32 (3 min)** | **53,926** | **-₹48,681** | **+₹151,068** ✅ |
| Regime-exit on ADX-conflict | NEW — not implemented | 12:34 (5 min) | 53,866 | -₹103,337 | +₹96,412 |
| Time stop 15 min | NEW — not implemented | 12:44 | 53,866 | -₹102,973 | +₹96,776 |
| Time stop 30 min | NEW — not implemented | 12:59 | 53,826 | -₹139,970 | +₹59,779 |
| Time stop 45 min | NEW — not implemented | 13:14 | 53,948 | -₹28,614 | +₹171,135 |
| Time stop 60 min | NEW — not implemented | 13:29 | 53,950 | -₹26,791 | +₹172,958 |
| **Daily kill -₹50k** | Phase 9.7AN (live) | After this trade | n/a | Caps the DAY but **not this single trade** | 0 on this trade |
| Z_STOP=2.5 (tightened) | Phase 9.7AO (live) | **never reached** | n/a | n/a | 0 |
| BE ratchet 1.25×ATR | Phase 9.7AP partner | never armed (no profit) | n/a | n/a | 0 |

### Interpretation

- **Paper-side SL at 1.5×ATR is the right armor.** It fires fast (3 min), prices the worst-case at -₹48k per trade, and does not depend on z-score sanity.
- **Time-stops at 45-60 min look attractive in hindsight but are dangerous in general** — they catch this trade's bounce but would prematurely close legitimate long-held winners. Discard.
- **Regime-conflict force-exit** is a viable defense-in-depth (saves ~₹96k here, fires at 5 min). Cost: would force-exit winning trades that ride a developing trend in the wrong direction. Net-effect requires backtest. Logged as future R&D (Phase 9.8h.B.5).
- **Daily kill** is irrelevant for single-trade catastrophes of this magnitude; it caps the DAY but this trade alone is 4× the daily kill threshold.

---

## 5. Verdict — Sacred Rule #14 / #19 (no live config change without paper-or-backtest evidence)

**No live `.env` change recommended from this forensic.**

The existing armor stack already covers this failure mode:

1. **Phase 9.7AP paper-side SL @ 1.5×ATR (live since 21 May)** — would have capped this exact trade at -₹48k.
2. **Phase 9.7AN daily kill @ -₹50k (live)** — caps cumulative day damage.
3. **Phase 9.7AO z≥2.5 stop (live)** — backstop for cases where the spread does diverge (not applicable here, but covers other scenarios).

**Open item:** Regime-conflict force-exit. Promising but needs walk-forward backtest before deployment (planned Phase 9.8h.B.5 with the slippage-sensitivity sweep).

---

## 6. Data-quality gaps discovered

1. **`trades.jsonl` rows have no `symbol` field.** Keys are only `entry, entry_ts, exit, exit_ts, pnl, qty, reason, side`. Symbols had to be inferred from price magnitude. **Fix:** patch the trade-logging path in the bot to emit `symbol`. Schedule Phase 9.8h.B.2.
2. **Ledger desync.** The 13:19→13:30 NIFTY scalp visible in `logs/ou_mrs_20260512_091400.log` does not appear in `trades.jsonl`. Cause unknown — possibly logged by a different code path (paper-twin?). Schedule audit Phase 9.8h.B.3.
3. **Cumulative P&L drift.** The instructions page reports ₹2,33,859 cumulative; the trades.jsonl ledger sums to ₹1,52,112; pfm.json reports ~₹2,08,543. These three numbers should reconcile. Schedule audit Phase 9.8h.B.4.

---

## 7. Reproducibility

- Log archive: `logs/ou_mrs_20260512_091400.log` (280,640 bytes)
- Price data: `data/BANKNIFTY_FUT_1min.parquet` (14,244 bars, 2026-03-30 → 2026-05-26, refetched 27 May)
- Analysis scripts: `/tmp/may12_deep.py`, `/tmp/may12_ohlc2.py` (one-shot, not committed)
- Live config at incident: pre-Phase 9.7AP (paper-side SL did not yet exist)
- Live config now: Phase 9.8h.A.3 baseline (post-PR #9 merge, SHA 1a15d83)

All figures in this report are reproducible by re-running the two `/tmp/may12_*.py` scripts against the committed log archive and parquet.

---

*Authored by the OU-MRS custom agent, Phase 9.8h.B.1. Reviewed against Sacred Rules #14, #15, #17, #19, #20, #43.*
