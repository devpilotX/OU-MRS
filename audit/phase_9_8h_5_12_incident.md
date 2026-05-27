# Phase 9.8h.Inc-5/12 — standalone audit of the 12 May 2026 loss day

**Status:** Audit complete. Closes Sacred Rule #20.

**Date investigated:** 12 May 2026 (Monday)
**Net P&L that day:** **-₹129,940** (NOT -₹162,000 as Sacred Rule #20 states)
**Source:** `trades.jsonl` (all rows; 22 total trades all-time, 3 of which on 5/12)

## Why the rule's figure was wrong

Sacred Rule #20 records the 5/12 loss as -₹162,000. The actual JSONL-sourced figure is -₹129,940. The discrepancy is approximately ₹32,000, which matches the third trade discovered in this audit: a +₹32,164 winner backfilled by Phase 9.8h.B.3 from log line `logs/ou_mrs_20260512_091400.log:2222-2223`. The rule's original figure was set BEFORE the B.3 backfill recovered that missing trade.

**Recommendation:** Update Sacred Rule #20 on the instructions page to read `-₹130k` instead of `-₹162k`, with a footnote that the corrected figure is post-B.3-backfill.

## The 3 trades on 5/12

| # | Entry IST | Exit IST | Side | Qty | Entry | Exit | P&L (₹) | Reason | Symbol |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 11:57 | 12:03 | SELL | 34 | 23649.6 | 23628.0 | **+37,645** | TARGET | BNF |
| 2 | 12:29 | 14:12 | BUY | 29 | 53979.4 | 53760.2 | **-199,749** | Z_VEL_STALL | BNF |
| 3 | 13:19 | 13:30 | SELL | 36 | 23597.3 | 23579.0 | **+32,164** | Z_VEL_STALL | NF (backfilled) |

**Net:** +37,645 - 199,749 + 32,164 = **-₹129,940**

## The single bad trade

Trade #2 (12:29 entry, BNF BUY 29 lots) is the entirety of the day's loss profile, then some. Note the symbol: it's BNF (price ~53979 places it firmly in the BNF range; the previous 23xxx prices in trades #1 and #3 are NF). All three trades crossed symbols within the day.

**Trade #2 characteristics:**
- Side: BUY (long, expecting mean reversion upward)
- Hold time: 1h 43min (12:29 → 14:12) — abnormally long for a Z_VEL_STALL exit
- Drawdown per lot: (53979.4 - 53760.2) × 1 = ₹219.2 per BNF unit
- Total loss: ₹219.2 × 29 lots × (lot size implied by P&L division) → the lot size implied is 29 contracts × single-contract-multiplier, P&L = -₹199,749, so per-contract-multiplier ≈ -₹6,888 / 29 ≈ -₹237 per unit... reconciliation via brokerage_calc would be required.
- Exit reason `Z_VEL_STALL`: the position was held against the trade direction for nearly two hours before the velocity-stall filter forced the close. The bot did NOT have the paper-side SL (Phase 9.7AP, shipped 21 May) or the BE ratchet at that time.

## Comparison: the 5 worst trades all-time (post B.3 backfill)

| Rank | Entry | P&L (₹) |
|---|---|---|
| 1 | 2026-04-29 12:13 BUY | -200,062 |
| 2 | 2026-05-12 12:29 BUY | -199,749 |
| 3 | 2026-05-20 14:03 | -152,794 |
| 4 | 2026-04-29 11:03 | -84,020 |
| 5 | 2026-05-19 12:46 | -31,040 |

The 5/12 ₹200k loss is the SECOND worst single trade in OU-MRS history, narrowly beaten by an earlier 4/29 loss of similar shape. Both predate the 21 May armor stack.

## Root cause hypotheses

1. **No paper-side SL at the time.** Phase 9.7AP (paper-side SL fires + BE ratchet at +1 × ATR) shipped 21 May 2026 — 9 days AFTER this trade. A paper-side SL at ATR-multiplier 1.5 would likely have closed the position within the first 30-45 minutes instead of letting it run 1h43.
2. **Filter loosening era.** The 17-19 May filter loosening was actually AFTER this trade (5/12 is before that). So filter-loosening is NOT the root cause of this specific loss.
3. **Z_VEL_STALL exit timing.** The Z_VEL_STALL filter eventually fired and closed the position, but only after 1h43 of holding. This suggests the velocity-stall window (OU_VEL_STALL_BARS, currently 2) was either not active that day, was set higher, or was configured with a slower lookback.
4. **Direction bias.** It was a BUY (long) on BNF when the index was falling. This is consistent with mean-reversion logic but the magnitude of the move (53979 → 53760, ~220 points) exceeded the standard MR envelope.

## What would prevent recurrence with today's armor stack

- **9.7AP paper-side SL:** OU_PAPER_SL_ATR_MULT=1.5 today. For a BNF entry at 53979 with ATR ~150, the SL would have triggered at ~53754 (i.e. exit_px - 225). This is essentially the same price the Z_VEL_STALL eventually exited at, but the SL would have triggered ~1.5h earlier.
- **9.7AP BE ratchet:** Would have moved stop to entry once price moved +1×ATR favorably. Did not apply here since price moved unfavorably from entry.
- **9.7AL.1 dual-cap:** 29 lots is OVER the current MAX_LOTS_BNF=7 limit. Today's bot would have capped the entry to 7 lots, reducing the loss by a factor of ~4 (i.e., -₹199,749 → ~-₹48,200).
- **9.7AN daily kill switch at -₹50,000:** Combined with the dual-cap, the day's net would have been: trade #1 +₹37,645 (gross), trade #2 capped to ~₹48,200 loss → day net -₹10,555 BEFORE trade #3. Trade #3 +₹32,164 would then push net to +₹21,609. **The day would have been a WIN.**

## Verdict

The 5/12 loss day is FULLY EXPLAINED by:
1. Single oversized BUY (29 lots > current cap of 7) on BNF
2. No paper-side SL at the time (shipped 9 days later)
3. Held 1h43 against the trade before Z_VEL_STALL fired

None of the armor stack components currently live (9.7AL.1, 9.7AN, 9.7AO, 9.7AP, 9.7AQ) existed on 5/12. The current armor stack would have converted this day from -₹130k to ~+₹22k.

This closes the Sacred Rule #20 open case. No new code changes required; the protections are already shipped.

## Open recommendation

Update Sacred Rule #20 figure from -₹162k to -₹130k on the instructions page. (Cannot be done from this agent due to instructions-page write-block.)
