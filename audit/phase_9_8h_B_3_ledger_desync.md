# Phase 9.8h.B.3 — Ledger desync forensic (May 12, 2026)

**Status:** ROOT CAUSE LOCATED · BACKFILLED · HARDENED
**Severity:** Data-quality (no live capital impact — paper-trading mode)
**Surfaced by:** Phase 9.8h.B.1 May 12 forensic (audit trail anomaly)
**Closed:** Phase 9.8h.B.3 (this document)

## TL;DR

Exactly one trade — **NIFTY SELL 36l @ 23597.30 → 23579.00, 13:19→13:30 May 12, +₹32,164** — was missing from `trades.jsonl` despite being fully logged and reflected in `equity.jsonl`. Root cause: the unwrapped `with open(TRADES_PATH, "a") as f:` block in `_exit()` silently swallowed a transient I/O exception (almost certainly a filesystem hiccup during a get_candles RATE-LIMIT cool-down at 13:30:06). All other state paths captured the trade correctly. **Backfilled** the row with provenance markers, **wrapped** the write in try/except with CRITICAL `[LEDGER-DESYNC]` logging, and **added** a ledger-vs-log reconciliation block to the EOD report.

## Evidence

### 1. The missing trade IS in the log archive

`logs/ou_mrs_20260512_091400.log:2222-2223`:
```
2026-05-12 13:30:37,599 [INFO] [PAPER] EXIT BUY 36l
2026-05-12 13:30:37,599 [INFO] EXIT (Z_VEL_STALL) @ 23579.00 pnl=Rs32164
```
Entry line 1742 (~13:19:08): `ENTRY SELL 36l @ 23597.30 z=1.58 hl=4.8`.

### 2. The bot's internal state captured it correctly

Heartbeat 2 seconds after the EXIT:
```
2026-05-12 13:30:39,600 [INFO] [heartbeat] alive in_trade=YES trades=3 pnl=Rs69809
```
Prior heartbeat (just before the EXIT) showed `trades=2 pnl=Rs37645`. Delta: **+1 trade, +Rs32,164** — exact match.

`state/primary/equity.jsonl` for May 12:
```
{"date": "2026-05-12", "pnl": -129939.71, ...}
```
`37645 + 32164 + (-199749) = -129,940` ✓ — equity reflects all three trades.

### 3. trades.jsonl missed only this one row

Pre-B.3 trades.jsonl had 21 rows; log archives across the 11-day live window have 22 `EXIT (` lines. The single missing row is precisely the May 12 13:19 NIFTY.

### 4. Coincident RATE-LIMIT cool-down

Immediately before the EXIT (line 2221):
```
2026-05-12 13:30:06,714 [WARNING] get_candles attempt 1/4 RATE-LIMIT: ... cool-down 30.7s
```
The Angel rate-limit cool-down ended ~13:30:37 — exactly when the EXIT fired. The race between the cool-down resolution and the file-write is the most likely trigger, though the exact exception was lost because the write was not guarded.

## Root cause

The pre-B.3 `_exit()` function wrote to `trades.jsonl` with no exception handling:

```python
with open(TRADES_PATH, "a") as f:
    f.write(json.dumps({...}) + "\n")
```

Any exception inside this block — disk full, permission flap, filesystem hiccup during the concurrent get_candles I/O retry, an OS-level interrupt, anything — would propagate up the per-symbol runner loop and get caught by the runner's top-level `except Exception` handler that logs at WARNING level and continues. The trade exit had already been logged at INFO before the file write, so an operator scanning for ERROR/CRITICAL would see nothing wrong.

## Counter-factual: what hardening would have caught this

| Defense | Would have caught | Cost |
|---|---|---|
| Try/except around write with `log.critical("[LEDGER-DESYNC] ROW_PAYLOAD=...")` | ✅ YES — full row visible in log for backfill | trivial |
| EOD reconciliation: count `EXIT (` log lines vs trades.jsonl rows for today | ✅ YES — would have flagged at 15:35 IST same day | trivial |
| `fsync()` after the write | partial — would not have caught the exception itself but reduces lost-write window | small perf cost |
| Atomic write (tmp + rename) | partial — only covers crash-during-write | small complexity |

## Actions taken in Phase 9.8h.B.3

1. **Defensive wrap in `_exit()` (`ou_mrs.py`):** the write block is now inside `try: ... except Exception as _trade_write_err: log.critical("[LEDGER-DESYNC] ... ROW_PAYLOAD=...")`. The full row payload is embedded in the CRITICAL log line, so a future write failure leaves a fully-reconstructable audit trail. The exception is NOT re-raised because the position is already flat and re-raising would mask the exit_reason for downstream readers (signal_publisher, heartbeat).
2. **Backfill of the missing row** in `trades.jsonl` with provenance markers:
   - `"backfilled": "phase-9.8h.B.3"`
   - `"backfill_source": "logs/ou_mrs_20260512_091400.log:2222-2223"`
   - Inserted chronologically between the 12:29 BNF row and the 14:12 BNF row.
3. **EOD reconciliation block in `tools/eod_report.py`:** every EOD report now shows trades.jsonl row count vs `EXIT (` log line count for the day, with a ⚠️ `[LEDGER-DESYNC]` warning block on mismatch.
4. **Regression tests** (`tests/test_phase_9_8h_b3_ledger_desync.py`):
   - Asserts the try/except wrap exists in `_exit`.
   - Asserts the CRITICAL log contains `[LEDGER-DESYNC]` tag and `ROW_PAYLOAD=` payload.
   - Asserts the backfilled May 12 13:19 NIFTY row is present and intact in `trades.jsonl`.

## Reconciliation impact

| Source | May 12 net P&L | All-time sum (pre-B.3) | All-time sum (post-B.3) |
|---|---|---|---|
| `trades.jsonl` sum | -₹162,103 (only 2 of 3 trades) | ₹152,112 | **₹184,276** (+₹32,164 from backfill) |
| `state/primary/equity.jsonl` | -₹129,940 (correct) | ₹320,552 (last May-13 entry; stale) | unchanged |
| `state/pfm.json` cumulative_pnl | n/a | ₹208,543 (snapshotted May 26) | unchanged (regenerated on next snapshot) |
| Instructions page header | n/a | ₹233,859 (stale) | needs Phase 9.8h.B.4 reconciliation |

The ₹32,164 backfill moves trades.jsonl closer to the equity ledger but does NOT fully reconcile the three sources. Full reconciliation is the scope of **Phase 9.8h.B.4** (cumulative P&L reconciliation across pfm.json, equity.jsonl, trades.jsonl, and instructions page).

## Files touched

- `ou_mrs.py` — defensive try/except wrap around trades.jsonl write (+979 bytes)
- `trades.jsonl` — 1 row backfilled (21 → 22 rows)
- `tools/eod_report.py` — ledger-vs-log reconciliation block (+~1400 bytes)
- `tests/test_phase_9_8h_b3_ledger_desync.py` — NEW (3 regression tests)
- `audit/phase_9_8h_B_3_ledger_desync.md` — NEW (this document)

## Sacred rule satisfied

Sacred Rule #20 (May 12 -₹162k loss is a standalone open case) is now closed in two phases: **B.1** explained the loss itself (no armor gap, paper-SL would have saved ₹151k, regime-exit would have saved ₹96k), and **B.3** explained the ledger desync that obscured the loss reconstruction (silent I/O exception in unguarded trades.jsonl write).
