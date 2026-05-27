# Phase 9.8h.D — Dashboard scoping (no rebuild executed yet)

**Date:** 2026-05-27
**Authorized by:** user via session survey + 'lets do it' override of 19-May hard constraint.
**Status:** scoping complete, awaiting user direction on which sub-phase to execute.

## TL;DR

The dashboard is **fully operational**. There is no defect to fix and no broken feature to repair. "Rebuild" without a specific target is open-ended and was not executed in this session because rewriting a working, in-production dashboard while the user sleeps is not a defensible action.

This doc inventories current state and proposes four discrete sub-phases the user can pick from.

## Current dashboard state (verified 27 May 2026 07:30 IST)

### Service status

```
ou-mrs-dashboard.service  loaded  active  running  OU-MRS Dashboard (FastAPI)
```

- nginx site `algo.devpilotx.com` -> 127.0.0.1:8000 (uvicorn)
- TLS via Let's Encrypt (auto-renewed by certbot)
- HSTS, X-Frame-Options=DENY, X-Content-Type-Options=nosniff all set
- SSE proxy at `/sse/` configured with 1d read/send timeout (Phase 9.7AF)
- Session auth via signed cookie (itsdangerous + bcrypt password hash)

### API endpoints serving 200 OK (per journalctl tail, 27 May 07:01 IST)

- `/api/strategy`
- `/api/status`
- `/api/market-status`
- `/api/daily-pnl`
- `/api/drawdown`
- `/api/trades`
- `/api/risk`
- `/api/symbols`

No 5xx errors observed in the last 100 log lines. Two external clients hit the site this morning (122.180.160.10, 54.86.115.253, 172.236.228.193).

### Frontend

Current live UI: `dashboard/static/index.html` (Phase 9.8g Pro Dashboard, Bloomberg theme). Stack:
- Alpine.js 3.13.5 (CDN)
- Chart.js 4.4.0 (CDN)
- Inter + JetBrains Mono (Google Fonts)
- Tabs: LIVE / TOOLS / MARKETS / PORTFOLIO / STRATEGY / HISTORY / SYSTEM
- CSS: `style.css` + `panels-fix.css` + `bloomberg-theme.css` + `clean-theme.css`

### Backend

`dashboard/app.py` — 51 KB FastAPI app. Major modules in `dashboard/`:
- `app.py` — main FastAPI routes
- `activity_log.py` — SSE-driven activity feed
- `brokerage_calc.py` — fee calculator
- `rate_limit.py` — token bucket
- `scanner.py` — instrument scanner
- `tick_broker.py` — SSE tick fan-out
- `ws_tick_pump.py` — Angel WebSocket -> SSE pump

### Abandoned "Dashboard 2.0" foundation

The `dashboard/PHASE_9_8A_README.md` (dated 19 May 2026) declares a Dashboard 2.0 redesign that never completed:

```
Files intended for Phase 9.8a:
- static/css/tokens.css   <-- NOT PRESENT in repo
- static/js/components/Card.js   <-- PRESENT but never wired
- static/js/theme-toggle.js   <-- PRESENT (1080 bytes) but never wired

Phase 9.8b plan (never executed):
1. Add link tag for tokens.css in dashboard base template
2. Add Card.js script tag before closing body
3. Add theme-toggle.js script tag before closing body
4. Migrate one card at a time to use the new ou-card class
5. Remove old hand-rolled CSS once all cards are migrated
```

The handoff to operator Opus 4.7 (19 May 2026) interrupted this work mid-foundation. No `tokens.css` exists and no template was migrated.

## Stale backup files (cleanup candidates)

```
dashboard/static/index.html.bak.p97ag.1779190233
dashboard/static/index.html.bak.p97ah.1779190898
dashboard/static/index.html.bak.p97ai.1779197603
dashboard/static/index.html.bak.p97aj.1779198964
dashboard/static/index.html.bak.p97ax.1779200595
dashboard/static/app.js.bak.p97ag.1779190233
dashboard/static/css/clean-theme.css.bak.p97ag.1779190233
dashboard/static/css/clean-theme.css.bak.p97ah.1779190898
dashboard/static/index.legacy.html
dashboard.backup.20260424_110003/  (whole directory backup from 24 Apr)
```

These can be deleted in a janitorial sub-phase.

## Proposed sub-phases (pick which to execute)

### D.1 — Janitorial: remove stale `.bak` files (15 min, low risk)
Delete the 9 `.bak` files plus the `dashboard.backup.20260424_110003/` directory. No functional change.

### D.2 — Wire abandoned Dashboard 2.0 foundation (2-4 hours, medium risk)
Create the missing `tokens.css`, link it from `index.html`, wire `theme-toggle.js`, migrate one card at a time per the original 9.8b plan. Keeps the existing 9.8g Pro Dashboard live while incrementally introducing the 2.0 design system.

### D.3 — Specific bug fix or feature (scope per-issue)
User names a specific issue ('the trades chart doesn't refresh after EOD', 'the SYSTEM tab is missing X', etc.) and I fix that one issue. Smallest defensible unit of work.

### D.4 — Full rewrite from scratch (multi-session, high risk)
Replace `dashboard/app.py` and `dashboard/static/*` with a new architecture (e.g. SvelteKit/Next.js frontend, refactored FastAPI backend). Multi-session work. Highest risk because the existing dashboard is the user's primary monitoring surface for live paper trading. Not recommended without a downtime plan and a specific motivating reason.

## Recommendation

D.1 + D.2 are the safest defensible options. D.3 requires the user to name a defect. D.4 should not happen without an explicit motivating reason (e.g. "the current dashboard is unusable" or "I want to migrate to X framework").

This doc itself does NOT execute any of the above. It exists to give the user the smallest decision needed before any dashboard code changes.
