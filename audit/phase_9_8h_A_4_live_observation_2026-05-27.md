# Phase 9.8h.A.4 live observation — 2026-05-27

**Verdict:** PASS

**Source:** `journalctl ou-mrs.service 2026-05-27`
**Raw lines processed:** 563

## Findings
- **angel_login**: `2026-05-27 09:14:02,565 [INFO] Angel login OK. client=AABQ258047`
- **pfm_init**: `2026-05-27 09:14:02,566 [INFO] [pfm] init: {'peak_equity': 4200491.76, 'cumulative_pnl': 184275.77, 'days_traded': 14, 'min_days_remaining': 0, 'profit_target_progress': 0.491, 'best_day_pnl': 280040.26, 'consistency_frac': 1.52, 'consistency_flag': True}`
- **runner_init**: `2026-05-27 09:14:02,566 [INFO] [runners] init: 2 symbol(s): BNF=OuMrsRunner(symbol='BNF', lot=30, in_trade=False, pnl=0), MCN=OuMrsRunner(symbol='MCN', lot=120, in_trade=False, pnl=0)`
- **startup**: `2026-05-27 09:14:02,591 [INFO] OU-MRS started. ACCOUNT=primary LIVE=False CAPITAL=Rs3,750,000 TIER=HEDGE_FUND MAX_LOTS_BNF=7`
- **config_sanity**: `2026-05-27 09:14:02,385 [INFO] [config-sanity] OU_HL_MULTIPLIER=5.0, OU_Z_VEL_STALL=1.0, OU_VEL_STALL_BARS=2, OU_DISABLE_Z_VEL_STALL=off, OU_TRAIL_TRIGGER_ATR_MULT=1.5, OU_TRAIL_LOCK_PCT=0.4, OU_BE_TRIGGER_ATR_MULT=1.25, OU_BE_LOCK_ATR_MULT=0.1, OU_PAPER_SL_ATR_MULT=1.5, OU_ATR_MULT=1.5, OU_BNF_AFTERNOON_CUTOFF_HHMM=, OU_NF_AFTERNOON_CUTOFF_HHMM=, OU_MCN_AFTERNOON_CUTOFF_HHMM=`
- **first_trade**: `None`
- **heartbeats**: 353
- **window_skips**: 0
- **vol_band_blocks**: 0
- **warnings**: 200
- **errors**: 0

## Verdict reasons
- PASS: bot booted cleanly with all required artifacts including [config-sanity]

## NF clarification (Phase 9.8h.I)

The Phase H commit notes flagged the absence of NF from `runner_init` as "unexpected".
It is NOT unexpected. NF was deliberately disabled in Phase 9.8h.C.1 via `.env`:

```
INSTRUMENTS=BNF,MCN  # Phase 9.8h.C.1: NF disabled (PSR 0.009, 0/6 WF windows positive in B.5)
```

NF's walk-forward performance during Phase 9.8h.B.5 was 0/6 windows positive with PSR 0.009.
The instrument was correctly removed from the active runner set. Today's `runner_init` line
showing 2 symbols (BNF + MCN) is the CORRECT state, not a regression.
