# Phase 9.8h.A.4 — live observation (queued)

**Status:** queued for next session after 09:30 IST on the next trading day.

## What A.4 is for

Sacred Rule #19 states: no feature can be claimed live unless observed in a real session log. A.4 is the verification step that the OU-MRS bot boots cleanly and emits all expected artifacts when it next launches at 09:14:01 IST via the `ou-mrs.timer` systemd unit.

## What CAN be observed live

- `Angel login OK` line at 09:14:0x
- `[pfm] init: {...}` portfolio-manager snapshot
- `[runners] init: 3 symbol(s): BNF=..., NF=..., MCN=...`
- `OU-MRS started. ACCOUNT=primary LIVE=False CAPITAL=Rs3,750,000 TIER=HEDGE_FUND MAX_LOTS_BNF=7`
- `[heartbeat]` every 30 s
- `[skip] Phase 9.7Z window: have N need 40` during the prime window
- `[entry]` lines if any signal fires
- vol_band / Phase 9.7AQ filter discipline blocks (if BNF qualifies)

## What CANNOT be observed live (open case OC-7)

Phase C.2 (`OU_COST_MODEL_V2=on`) and C.3 (`OU_GAP_THRESHOLD_ATR=1.5`, `OU_GAP_PENALTY_BPS=8`) hardened the **backtest** cost model only. The live bot (`ou_mrs.py`) does not currently read these env values. The provisional FUT PSR figures (BNF 0.837 / MCN 0.795) describe the backtest's realism, not the live execution stack.

**Open case OC-7** (added to docs/QUANT_GRADE_REVIEW.md follow-up): mirror C.2/C.3 cost adjustments into live PnL accounting before the backtest PSR can be claimed as predictive of live performance. Until then, live forward results will systematically over-perform backtest expectations if real costs come in lower than the C.2 model, or under-perform if real gap impact exceeds C.3 calibration. Either way, the backtest is no longer a clean predictor.

## How to run the A.4 verification

After 09:30 IST on the next trading day (giving the bot enough time to emit ~30 heartbeats):

```
cd /home/ubuntu/bots/ou-mrs
./venv/bin/python tools/verify_a4_live_observation.py
```

The script writes `audit/phase_9_8h_A_4_live_observation_<YYYY-MM-DD>.md` with a PASS/FAIL verdict. Commit that audit doc to the repo on a `phase-9.8h.A.4-observation` branch.

## Why this is queued, not automated

The next bot launch is 09:14:01 IST on the next trading day. This session is documenting at 06:30 IST, ~2h45 before bot launch. Rather than schedule a one-shot timer at 09:30 (which would require root systemctl installation and adds an additional moving part), the verify script ships as a tools/ utility for the next session to invoke.
