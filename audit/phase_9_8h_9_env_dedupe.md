# Phase 9.8h.9 — .env duplicate-key dedupe

**Date:** 2026-05-27 (Asia/Calcutta)
**Branch:** `phase-9.8h.9-env-dedupe`
**Base:** `phase-9.8f-bloomberg`
**Trigger:** Recurring `.env` duplicate-key smell flagged during the
[Phase 9.8h.8 CI incident RCA](./phase_9_8h_8_ci_incident_rca.md).

## Symptom

The on-VPS `.env` had `OU_Z_STOP_BNF/NF/MCN` defined twice:

- **L37–40** (Phase 9.7N, 2026-05-15 era):
  ```
  # Phase 9.7N: z_stop unified at 3.5 across all symbols (backtest default; per-sym sweep deferred)
  OU_Z_STOP_BNF=3.5
  OU_Z_STOP_NF=3.5
  OU_Z_STOP_MCN=3.5
  ```
- **L51–55** (Phase 9.7AL.1+…+AP, 2026-05-21):
  ```
  # === Phase 9.7AL.1+AM+AN+AO+AP (21 May 2026) ===
  NOTIONAL_LEVERAGE_MAX=3.0
  OU_Z_STOP_BNF=2.5
  OU_Z_STOP_NF=2.5
  OU_Z_STOP_MCN=2.5
  ```

Under python-dotenv's default `override` semantics, the last assignment wins,
so the live armor (2.5) was applied correctly. But the 3.5 block lingered as
dead code — any reviewer glancing at the file would think the bot was running
with z-stops at 3.5 (a much looser stop) and silently mis-diagnose any future
incident.

`.env.example` (committed to git) had a related but distinct staleness:

```
# Phase 9.7AO: tight stops (ATR multiplier + per-symbol z-stop bands)
OU_Z_STOP_BNF=2.5
OU_Z_STOP_NF=3.5
OU_Z_STOP_MCN=3.5
```

This did not match live (`2.5/2.5/2.5`), so any fresh deploy from the template
would have entered service with two of the three z-stops wider than intended
— a silent risk regression at the moment of greatest risk (fresh deploy).

## Root cause

Two convergent forces:

1. **Auto-append culture.** Multiple phase rollouts appended new key blocks
   to the end of `.env` rather than editing existing values in place. The L43
   marker `# Phase 9.7U auto-appended 2026-05-16 17:42 IST` shows the
   pattern explicitly. Each append left the prior block intact.
2. **No defensive check.** Neither CI nor the bot startup verified that a key
   appears at most once across any `.env*` file. The 3.5 block survived 6
   days (15–21 May) of "always meant to clean that up" debt, then an
   additional 6 days (21–27 May) before being noticed and fixed.

## Remediation (this PR)

1. **VPS `.env` surgery.** Deleted L37–40 (the comment + three 3.5
   assignments). Original backed up to
   `state/backups/env-20260526T214856Z.bak` (`state/` is gitignored).
   No functional change — the live armor was already 2.5 (last-wins).
2. **`.env.example` truth-up.** Updated `OU_Z_STOP_NF` and `OU_Z_STOP_MCN`
   from `3.5` to `2.5` to match the live armor. `BNF` was already `2.5`.
   Comment updated from "per-symbol z-stop bands" to "unified z-stop band at
   2.5" since the bands are no longer per-symbol.
3. **Defensive linter (`scripts/check_env_dups.py`).**
   - Detects duplicate keys in any `.env*` file (excluding `.env` itself,
     which is gitignored).
   - Returns exit 1 on any duplicate, exit 0 otherwise.
   - Also surfaces `auto-appended` comment markers as informational
     warnings, since they correlate with the auto-append pattern that
     produces dupes.
4. **CI wiring.** Added a `Check .env* for duplicate keys` step to the
   `lint` job in `.github/workflows/ci.yml`. Any future PR that introduces
   a duplicate key in `.env.example` (or any other tracked `.env*`) fails
   CI loudly — no `continue-on-error`.

## Verification

- Backup file exists, byte-identical to pre-edit `.env`
  (`state/backups/env-20260526T214856Z.bak`, 1944 bytes).
- Bot is flat (no `ou_mrs` process, service inactive, no live state
  snapshots); next launch is 09:14 IST on the next trading day — Sacred
  Rule #15 satisfied.
- After the L37–40 deletion, `grep ^OU_Z_STOP .env` returns exactly
  three lines, all `=2.5`.
- `python scripts/check_env_dups.py .env` → 0 dupes.
- `python scripts/check_env_dups.py .env.example` → 0 dupes.
- `python scripts/check_env_dups.py` (auto-discovery) → 0 dupes across
  all tracked `.env*` files.

## Sacred Rules touched

- **Rule #3** (never `git add .env`): respected. `.env` stays gitignored.
- **Rule #6** (verify against `data/instruments.db` before changing
  contract parameters): N/A — z-stop is a strategy parameter, not a
  contract parameter.
- **Rule #7** (don't disable stops because they correlate with losses):
  respected. We did not weaken any stop. We removed dead duplicates of
  the already-live tight 2.5 setting.
- **Rule #15** (no restart with open position): respected — bot is flat.
- **Rule #19** (no "works" claim until observed in live conditions or a
  backtest): the linter has been observed firing on a synthetic input
  with known dupes; the CI integration will be observed firing on this
  PR's checks.

## What this prevents

Any future "Phase X auto-appended …" block that re-declares an existing
key will now be caught at PR time by `check-env-dups`, not 6 days later
by a careful eyeball read. The cost of running the check is negligible
(<200 ms on a 100-line file).

## Follow-ups (not in this PR)

- **Phase 9.8h.10 (optional)**: extend `log_config_sanity()` (added in
  Phase 9.8h.5) to also call the dedupe check at bot startup against the
  live `.env`. The bot would then refuse to start if dupes appear,
  catching even VPS-only drift that never enters git.
- **Phase 9.8h.11 (optional)**: refactor any code path that appends to
  `.env` (e.g. the Phase 9.7U auto-append flow) to instead use an
  upsert helper that respects existing keys.
