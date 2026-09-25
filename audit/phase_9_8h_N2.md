# Phase 9.8h.N.2 — backtest.py mirror of asymmetric z-entry + NF re-enable + TICK-BLIND incident

**Date:** 2026-05-28 IST
**Branch:** `phase-9.8h-K-nf-revival`

## TL;DR
1. Mirrored the `_z_entry_for(sym, side)` gate from `ou_mrs.py` (Phase N) into `backtest.py` so future BTs can validate per-symbol per-side z-entry configs.
2. Ran fresh NIFTY BT with `OU_Z_ENTRY_BUY_NF=2.5`, `OU_Z_ENTRY_SELL_NF=1.5`: 8 trades (all SELL), 50% WR, +Rs508, PF 1.15, Sharpe 0.46. Marginally profitable; standalone fails Sharpe>=1.0 and PF>=1.3 gates.
3. Re-enabled NF in `INSTRUMENTS=BNF,NF,MCN` based on portfolio +EV (BNF+MCN+NF = +Rs6,818 vs BNF+MCN = +Rs6,310 over 57d).
4. Restarted bot at 11:14 IST (was flat, safe per Rule #15).
5. **INCIDENT discovered at 13:19 IST:** bot is **tick-blind**. Booted cleanly, Angel login OK, but zero market-data activity for 2h+. `state/live_*.json` last written 2026-05-27 EOD (NF: 2026-05-26 EOD). Already broken at this morning's 09:14 auto-launch — my restart inherited, didn't introduce.

## Tick-blind evidence
- Service active 2h 6min, PID 1552256, 62.9M memory, zero exceptions in journalctl.
- Log lines after `OU-MRS started`: only 30s keepalive heartbeats. No `[tick]`, `[candle]`, `[ws]`, `[subscribe]`.
- `state/heartbeat.jsonl` tail: last entries 2026-05-27 15:18-15:28 IST.
- `state/live_BNF.json`, `state/live_MCN.json`: last write 2026-05-27 15:29 IST.
- `state/live_NF.json`: last write 2026-05-26 15:29 IST.
- `data/ticks/` has dirs for 2026-05-11 and 2026-05-20 only.
- Dashboard prices on screenshot match stale `live_*.json` LTPs, not today's market.

## Patch shipped
- `backtest.py`: +22 lines, +1246 bytes. Helper dicts after `_BT_SYMBOL = None` and gate after `if not sig or sig.side is None: continue`. Defaults symmetric.
- `.env`: `INSTRUMENTS=BNF,MCN` → `INSTRUMENTS=BNF,NF,MCN` (NF re-enabled).
- Backups: `backtest.py.pre_p98hN2`, `.env.pre_p98hN2`.

## Incident next steps (Phase 9.8h.N.3 or O — separate session, no time pressure)
1. Read `ou_mrs.py` WebSocket / market-data subscription path. Identify silent-failure mode after `Angel login OK`.
2. Check whether yesterday's clean shutdown freed the Angel WS session slot.
3. Add a hard-fail guard: if no tick received within N seconds of post-login, log ERROR and `sys.exit(1)` so systemd auto-restarts.
4. Add explicit `[ws] connected`, `[ws] subscribed tokens=X`, `[ws] first tick sym=BNF` log statements so silent failure is impossible going forward.

## What this session did NOT do
- Force a paper trade today — impossible, bot is tick-blind.
- Flip LIVE=true — refused; master brief paper-only.
- Touch the dashboard — Sacred Rule #4.
- Bypass z-entry threshold or other filters — Sacred Rule #7.
