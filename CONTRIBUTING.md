# Contributing to OU-MRS

## CI hygiene

GitHub Actions has been observed to silently skip workflow runs during transient incidents — see `audit/phase_9_8h_8_ci_incident_rca.md` for the 2026-05-26 9.7h dead-zone post-mortem.

**Rule**: If no workflow run appears in `gh run list --branch <your-branch>` within 60s of `git push`, do **not** merge.

### Recovery sequence

1. Wait 60s and re-check `gh run list --branch <your-branch> --limit 5`.
2. Push an empty commit to retry:
   ```bash
   git commit --allow-empty -m "ci: kick workflow"
   git push
   ```
3. If still silent for another 60s, open a GitHub Support ticket and add a `[ci-incident]` comment to the PR documenting the gap.
4. Merge only on independent verification:
   - Local `pytest -q` green
   - Production smoke (if behavior change touches live code path)
   - `[config-sanity]` log line on next bot launch (Sacred Rule #19)

### Daily heartbeat

The workflow `.github/workflows/ci-health.yml` emits a heartbeat run every day at 04:00 UTC. If no `CI Health Check` run is registered for >36h, that confirms Actions degradation for this repo. Cross-check with https://www.githubstatus.com — incident may not be public.

## Branching

- Branch off `phase-9.8f-bloomberg` (the current live branch) for incremental work.
- Name branches `phase-<version>-<short-slug>`, e.g. `phase-9.8h.8-ci-incident-rca`.
- The trigger pattern `phase-**` (in `.github/workflows/ci.yml`) is intentionally broad so every phase branch gets CI.

## Commit messages

- Subject line: `phase-<version>: <imperative summary>` (≤72 chars).
- Body: include verification evidence (pytest counts, smoke output snippets, CI run IDs).
- Reference Sacred Rules by number when applicable (e.g. "per Sacred Rule #19").
- Never `git add .env` (Sacred Rule #3).

## Sacred rules

See the agent instructions page (`OU-MRS Agent` in Notion). The most load-bearing ones for code review:

- **#1** — locate the real log file before diagnosing.
- **#6** — verify lot sizes and instrument tokens against `data/instruments.db`.
- **#7** — disabling a stop because it correlates with losses is survivorship bias. Root-cause first.
- **#13** — `trades.jsonl` lives at the repo root; equity at `state/primary/equity.jsonl`.
- **#15** — restart the bot only when no position is open.
- **#17** — source numbers from files, never from memory.
- **#19** — never claim a feature works until observed firing in live or backtest.
- **#41** — startup config-sanity log is the runtime backstop for pre-merge CI.
- **#43** — selection-bias correction (DSR / threshold_sr) required for parameter choices.
