# Phase 9.8h.A.4 — live observation (queued)

**Status:** queued for next session after 09:30 IST on the next trading day.

## What A.4 is for

Sacred Rule #19 states: no feature can be claimed live unless observed in a real session log. A.4 is the verification step that the OU-MRS bot boots cleanly and emits all expected artifacts when it next launches at 09:14:01 IST via the `ou-mrs.timer` systemd unit.

## What CAN be observed live

- `Angel login OK` line at 09:14:0x
- `[pfm] init: {...}` portfolio-manager snapshot
- `[runners] init: 3 symbol(s): BNF=..., NF=..., MCN=...`
- `OU-MRS started. ACCOUNT=primary LIVE=False CAPITAL=Rs3,750,000 TIER=HEDGE_FUND MAX_LOTS_BNF=7`
- **`[config-sanity] OU_HL_MULTIPLIER=..., OU_Z_VEL_STALL=..., ...`** — the Phase 9.8h.5 (Sacred Rule #41) startup banner. Already wired in `ou_mrs.py:main()` at line 388. The 5/25 log predates this addition, so the next bot run is the first one expected to emit it live.
- `[heartbeat]` every 30 s
- `[skip] Phase 9.7Z window: have N need 40` during the prime window
- `[entry]` lines if any signal fires
- vol_band / Phase 9.7AQ filter discipline blocks (if BNF qualifies)

## RETRACTION: previous OC-7 framing was wrong on two counts

Phase F (commit `f8df8ad`) shipped this audit doc with an "Open case OC-7" section that stated:

> Phases C.2 and C.3 hardened only the BACKTEST cost model. The live bot ou_mrs.py does NOT read these env values. ... Live forward results will systematically diverge from backtest until C.2/C.3 are mirrored into ou_mrs.py PnL accounting.

**Both halves of that framing were wrong.** Documented retraction:

### Wrong claim #1: "C.2/C.3 should be mirrored into live PnL"

C.2 (`estimate_slippage_ticks`) and C.3 (`estimate_gap_slippage_ticks`) are **slippage-estimation** functions that exist specifically because **backtest has no real fills**. In live trading, the bot receives actual fill prices from Angel One; whatever slippage occurs is already baked into those fills. There is nothing to "mirror" — you cannot apply an estimated slippage to a real fill.

The correct relationship between backtest and live cost modeling is:
- Backtest *estimates* slippage via C.2/C.3 to approximate live execution
- Live *measures* actual slippage from real fills
- The honest comparison is *post-hoc empirical reconciliation*: after N live trades, compare realized slippage against C.2/C.3's prediction. If the live distribution falls within C.2/C.3's predicted envelope, the backtest is calibrated. If not, recalibrate C.2/C.3.

This is a *forward measurement* concern, not a code-change concern.

### Wrong claim #2: "config-sanity line is missing from live"

`log_config_sanity()` is **already imported and called** in `ou_mrs.py` — import at line 14, call at line 388 (Phase 9.8h.5). The previous claim was based on grepping the 5/25 log, which predates the addition. The next bot run is the first one expected to emit the line live, which is what A.4 is for.

### What replaces OC-7

A new, correctly-scoped open case **OC-7' (post-trade slippage reconciliation)** is filed in `docs/QUANT_GRADE_REVIEW.md`: after the bot accumulates 30+ closed trades, instrument the runner to log per-trade `signal_price` vs `fill_price` and compare the empirical slippage distribution to C.2/C.3's prediction. This is a future phase, not a current correction.

## How to run the A.4 verification

After 09:30 IST on the next trading day:

```
cd /home/ubuntu/bots/ou-mrs
./venv/bin/python tools/verify_a4_live_observation.py
```

The script writes `audit/phase_9_8h_A_4_live_observation_<YYYY-MM-DD>.md` with PASS/FAIL. Commit the result on a follow-up branch.

## Why this stays queued

The next bot launch is 09:14:01 IST tomorrow. This session is documenting at 07:30 IST today, ~2h before bot launch. The verify script ships as a tools/ utility for the next session to invoke; it does not need automation.
