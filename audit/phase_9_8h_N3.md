# Phase 9.8h.N.3 — 28 May 2026 "tick-blind" incident: market was closed (Bakri Eid)

**Date**: 2026-05-28  
**Severity**: low (no money lost, no false trades) — but eroded user trust and wasted ~2h28m of agent debug time chasing a non-bug.  
**Root cause class**: missing exchange-calendar awareness.

## Symptom
- Dashboard showed `STALLED` with heartbeat lagging by 7000+ seconds.
- Bot PID 1552256 (started 11:14:24 IST) was alive, logging in fine, then emitting only `[heartbeat] alive in_trade=no` every 30 s for 2h+.
- `state/live_*.json` timestamps stuck at yesterday's close.
- User pressed: "then fix it. i want trade today".

## Investigation path (chronological)
1. py-spy on PID 1552256 → idle inside `angel_adapter.get_candles` jitter sleep (`angel_adapter.py:92`), called from `ou_mrs.py:512`.
2. Read `get_candles`: the only silent return-empty path is `return resp.get("data") or []` when `data is None`. No WARNING logs ⇒ retry-loop never fired.
3. Direct API probe (`/tmp/probe_v2.py`) with fresh login on JUN+MAY+JUL tokens:
   - `getCandleData` for **today (09:15→13:38)**: `status=True, message=SUCCESS, data=[]` across BNF/NF/MCN.
   - `getCandleData` for **yesterday (27 May)**: 375 one-minute bars for BNF JUN + NF JUN. Tokens are correct.
   - `getMarketData` LTPs returned, **but `exchTradeTime` = `27-May-2026 15:29:5X`** for all four contracts (BNF/NF/MCN JUN + BNF JUL). LTP equals yesterday's close. Net change vs prior close = 0% for some, small for others (stale snapshot).
4. Multi-source web cross-reference (NSE official + Zerodha + Niftyindices + Economic Times + Profitmart + YES Securities): **28 May 2026 = NSE/BSE holiday for Bakri Eid (Equity + Equity Derivatives segments)**. MCX has partial closure. NCDEX fully closed. NSE's own homepage shows index last updated `27-May-2026 15:30`.

## Verdict
**The bot was not broken.** The Angel API behaved correctly: it served stale LTP and zero historical candles because zero trades occurred on the entire NFO segment today. The bot's `_market_hours_check` lacked a holiday list, so it started on a holiday morning, succeeded at login, and then spun heartbeats while waiting for candles that would never come.

## Fix
`ou_mrs.py` Phase 9.8h.N.3: hard-coded NSE/BSE Equity Derivatives 2026 holiday list (15 dates) and added an early-exit branch to `_market_hours_check` that compares `datetime.now().strftime("%Y-%m-%d")` against the set. Backup: `ou_mrs.py.bak.p98hN3`.

```python
_NSE_HOLIDAYS_2026 = {
    "2026-01-26",  # Republic Day
    ... 13 others ...
    "2026-05-28",  # Bakri Id  <-- today
    ...
}
```

The `_market_hours_check` weekend check was already present; the new branch sits immediately after it and exits cleanly with an INFO log. Backtest is unaffected (it iterates historical bars, not wall-clock).

## Why not also a hard-fail tick-blind guard?
Future work (Phase 9.8h.O). A separate guard inside the main loop that says "if no candles received from any symbol for N consecutive minutes during market hours, log ERROR and `sys.exit(1)`" would also catch the case where Angel itself is down or our auth silently fails. That's complementary but lower-priority than the holiday fix, since holiday tick-blind has a known pattern and the guard would also need to avoid false-positives at the open and around scheduled exchange pauses.

## Today's outcome
- Bot stopped at 13:42:44 IST (systemctl stop). It would have otherwise burned `~3 calls/minute × 540 minutes = ~1620` get_candles calls today producing zero data.
- `ou-mrs.timer` left untouched — tomorrow (Fri 29 May 2026, trading day) it will auto-start at the scheduled time and run normally.
- **No paper trade was possible today on any system. The exchange was closed.**

## P&L impact
₹0. Capital preserved.

## Sacred-rule notes
- Rule #14 (defensible delegated decision): the right action under user pressure ("trade today") was to investigate, not to slam-restart or loosen filters. Investigation revealed there is no trade to be had today on any platform; honest delivery of that finding is the right answer.
- Rule #15 (verify flat before stopping): bot was flat, stop was safe.
- Rule #20 (pfm baseline figure): unchanged.

## Files touched
- `ou_mrs.py`: +18 lines (holiday set + 3-line check)
- `audit/phase_9_8h_N3.md` (this file)

## Verification
- `python -c "import ou_mrs"` clean (no syntax errors).
- Manual call `_market_hours_check()` on 2026-05-28 returns False with log `NSE holiday 2026-05-28 (Thursday) — not trading. Clean exit.`.
- Next holidays the patch covers: 26 Jun 2026 (Muharram), 14 Sep 2026 (Ganesh Chaturthi), 02 Oct 2026 (Gandhi Jayanti), 20 Oct 2026 (Dussehra), 10 Nov 2026 (Diwali Balipratipada), 24 Nov 2026 (Guru Nanak), 25 Dec 2026 (Christmas).
