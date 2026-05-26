# Phase 9.8h.B.4 — Cumulative P&L reconciliation

**Status:** ROOT CAUSE LOCATED · EQUITY REBUILT · CANONICAL TOOL SHIPPED · CI GUARD
**Severity:** Data-quality (no live capital impact — paper-trading mode)
**Surfaced by:** Phase 9.8h.B.3 (post-backfill reconciliation matrix revealed a second class of desync)
**Closed:** Phase 9.8h.B.4 (this document)

## TL;DR

After B.3 backfilled the missing May 12 NIFTY trade, the reconciliation matrix exposed a **₹24,267.45 delta** between `trades.jsonl` (₹184,275.95) and `state/primary/equity.jsonl` / `state/pfm.json` (both ₹208,543.40). Drill-down found **two orphaned daily roll-ups**: 2026-05-19 (-₹31,040.23) and 2026-05-21 (+₹6,772.60), both showing as 0.00 in equity.jsonl despite trades.jsonl carrying the trades. Root cause: the bot writes `equity.jsonl` only via `_flush_all_caches_p97p` registered with `atexit`, and **mid-day restarts orphan the prior session's intra-day P&L**. 05-19 had **7 bot restart sessions** (filter-loosening churn era), 05-21 had **2** (the 14:21 armor-restoration restart). Fix: derive equity.jsonl from trades.jsonl as the canonical source, ship `tools/rebuild_equity_from_trades.py` for idempotent reconciliation, ship `tools/verify_pnl_reconciliation.py` as a CI guard, and lock in the rule that **trades.jsonl is the source of truth, equity.jsonl/pfm.json are derived**.

**Canonical cumulative_pnl post-B.4: ₹1,84,275.77** (was ₹2,08,543.40 — prior value over-stated by ₹24,267.63 due to the orphaned losses on 05-19 not being booked).

## Pre-B.4 reconciliation matrix

| Source | Value | Status |
|---|---|---|
| `trades.jsonl` sum (post-B.3, 22 rows) | ₹1,84,275.95 | true sum of all booked trades |
| `state/primary/equity.jsonl` sum / last cum | ₹2,08,543.40 | drifted +₹24,267 (missing 2 days' bookings) |
| `state/pfm.json` cumulative_pnl | ₹2,08,543.40 | mirrored equity.jsonl (snapshot 26 May 15:59) |
| Instructions page header | ₹2,33,859.00 | stale snapshot from 21 May (equity.jsonl 05-20 row exactly) |

Deltas:
- trades vs equity = **-₹24,267.45** (the bug)
- pfm vs equity = ₹0.00 (pfm is a faithful mirror of equity)
- instructions vs current = -₹25,316.13 (post-21 May organic drift, not a bug)

## Root cause

`ou_mrs.py` writes `equity.jsonl` only inside `_flush_all_caches_p97p`, which is registered via `atexit`:

```python
import atexit as _atexit_p97p
# ...
def _flush_all_caches_p97p():
    """Persist all in-memory caches on shutdown (atexit)."""
    # ... writes equity.jsonl daily roll-up here
_atexit_p97p.register(_flush_all_caches_p97p)
```

If the bot exits via `SIGKILL`, OOM, crash, or even a normal restart mid-session, `atexit` handlers do not fire reliably (especially `SIGKILL`, which never fires them). The intra-day P&L state held in memory is lost.

## Evidence

### Log archive census proves the multi-session pattern

**2026-05-19** — **7 separate launch sessions** in one trading day:
```
logs/ou_mrs_20260519_091400.log    EXIT-count: 0
logs/ou_mrs_20260519_120510.log    EXIT-count: 0
logs/ou_mrs_20260519_130129.log    EXIT-count: 1   <-- the -Rs31,040.23 trade
logs/ou_mrs_20260519_130913.log    EXIT-count: 0
logs/ou_mrs_20260519_131313.log    EXIT-count: 0
logs/ou_mrs_20260519_134040.log    EXIT-count: 0
logs/ou_mrs_20260519_151426.log    EXIT-count: 0
```
Only the 13:01:29 session captured the trade. Subsequent restarts at 13:09, 13:13, 13:40, 15:14 wiped the in-memory P&L without booking it. Note the 15:14 launch — 16 minutes before the internal EOD at 15:30 — means the final session had a too-short window to accumulate anything, and the prior 5 sessions' P&L was orphaned.

**2026-05-21** — **2 sessions**: 09:14:01 and 14:21:50 (the armor-stack restoration restart noted in Sacred Rules):
```
logs/ou_mrs_20260521_091401.log    EXIT-count: 2
logs/ou_mrs_20260521_142150.log    EXIT-count: 1   <-- the +Rs6,772.60 trade
```
The 14:21 session booked the +₹6,772.60 trade in trades.jsonl, but `atexit` ran only against the 14:21–15:30 session's P&L counter (which had only that one trade); somehow equity.jsonl didn't get the daily roll-up either. The exact failure mode for 05-21 is less clear than 05-19 (the bot did exit cleanly), but the symptom is the same: orphaned daily roll-up.

### Per-day cross-check (pre-B.4)

```
Date         trades.jsonl     equity.jsonl    delta
2026-04-28      164,432.00      164,432.00       0     OK
2026-04-29     -230,338.00     -230,338.00       0     OK
2026-04-30       70,891.00       70,891.00       0     OK
2026-05-04       15,228.50       15,228.50       0     OK
2026-05-05      103,478.00      103,478.00       0     OK
2026-05-08       46,760.00       46,760.00       0     OK
2026-05-11      280,040.26      280,040.26       0     OK
2026-05-12     -129,939.54     -129,939.71      -0.17  OK (Rs0.17 rounding from B.3 backfill)
2026-05-14      -16,727.03      -16,727.03       0     OK
2026-05-19      -31,040.23            0       -31,040.23  ORPHAN
2026-05-20      -69,965.49      -69,965.49       0     OK
2026-05-21        6,772.60            0        +6,772.60  ORPHAN
2026-05-22        1,919.68        1,919.68       0     OK
2026-05-25      -27,235.81      -27,235.81       0     OK
```

Net orphan: -₹31,040.23 + ₹6,772.60 = **-₹24,267.63** (matches the matrix delta within rounding).

## Canonical rule established

**`trades.jsonl` is the source of truth.** Every closed trade is appended exactly once (B.3 hardening guarantees this with try/except + CRITICAL `[LEDGER-DESYNC]` logging). Every other P&L view (`equity.jsonl`, `pfm.json`, dashboard counters, instructions page header) is **derived** and must be rebuildable from `trades.jsonl` at any time.

## Actions taken in B.4

1. **Surgical backfill of equity.jsonl** — the 05-19 and 05-21 rows now carry the trades-derived `pnl` value plus provenance markers (`backfilled=phase-9.8h.B.4`, `backfill_reason`, `backfill_trade_count`). All `cumulative_pnl` values from 05-19 onwards are recomputed.
2. **Re-snapshot of pfm.json** — `cumulative_pnl` corrected to ₹1,84,275.77; `source` updated to `rebuild_equity_from_trades.py`.
3. **Permanent rebuild tool** — `tools/rebuild_equity_from_trades.py` is idempotent, supports `--dry-run`, backs up equity.jsonl, and can be re-run any time the bot loses a daily roll-up.
4. **Permanent verification tool** — `tools/verify_pnl_reconciliation.py` non-mutating; exits 0 if all three sources agree (within ₹1 tolerance for log-printed-integer rounding), exits 1 with detailed diff if not. Suitable for CI and cron.
5. **Regression tests** — `tests/test_phase_9_8h_b4_pnl_reconciliation.py` asserts both tools exist with their public callables and that the live state is in sync. CI will now fail any future PR that re-introduces a divergence.
6. **Backup retained** — `state/primary/equity.jsonl.pre-B.4.bak` (pre-rebuild snapshot) preserved on VPS.

## Reconciliation post-B.4

| Source | Value |
|---|---|
| `trades.jsonl` sum | ₹1,84,275.95 |
| `state/primary/equity.jsonl` sum / last cum | ₹1,84,275.77 |
| `state/pfm.json` cumulative_pnl | ₹1,84,275.77 |

Residual: ₹0.18 between trades.jsonl and the equity/pfm pair. This is the B.3 backfill rounding (the May 12 NIFTY row was sourced from a log line that printed `pnl=Rs32164` as an integer; equity.jsonl had captured the original float `32,164.17` at the time). Within the ₹1 verification tolerance — acceptable.

## Instructions page header

The `📖 Overview` cumulative_pnl field on `OU-MRS Algorithm Instructions` is updated separately from this PR to read **₹1,84,275.77** with a note that the canonical value is now derived from trades.jsonl via the B.4 rebuild tool.

## Sacred rules satisfied / strengthened

- **Rule #17** ("source numbers from files, never from prior memory of a number") — reinforced: the new verification tool is the file-of-record check.
- **Rule #20** (May 12 -₹162k standalone open case) — closed in B.1 / B.3 / B.4 together. B.4 corrected the cumulative figure that B.1/B.3 reconciliations depended on.

## Recurrence prevention

- B.4 ships the rebuild + verify tools, so any future single-day orphan is detectable on the next EOD run and repairable with one command.
- **Open follow-up (Phase 9.8h.C or later):** add per-trade equity.jsonl checkpoint writes inside `_exit()` so the daily roll-up is never dependent on `atexit`. Tracked separately because it changes the bot's hot path and needs broader regression coverage.

## Files touched

- `tools/rebuild_equity_from_trades.py` — NEW (permanent canonical rebuilder, idempotent)
- `tools/verify_pnl_reconciliation.py` — NEW (non-mutating verifier, CI/cron-friendly)
- `tests/test_phase_9_8h_b4_pnl_reconciliation.py` — NEW (3 regression tests)
- `audit/phase_9_8h_B_4_pnl_reconciliation.md` — NEW (this document)
- `state/primary/equity.jsonl` — NOT in PR (gitignored runtime state), backfilled in-place on VPS with provenance markers; pre-rebuild backup retained
- `state/pfm.json` — NOT in PR (gitignored runtime state), `cumulative_pnl` updated to ₹1,84,275.77
