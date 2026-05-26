# Phase 9.8h.8 — CI incident RCA (2026-05-26 11:41 – 21:23 UTC)

## Headline
GitHub Actions silently registered **zero** workflow runs for the branch `phase-9.8h.6-loaddotenv-order` during the ~9.7h window 2026-05-26 11:41:37 UTC → 21:23:11 UTC, including the merge commit `d9a0a6d` into `phase-9.8f-bloomberg`. The workflow on the branch was unchanged and matched the trigger pattern (`phase-**`). The window is bracketed by green CI runs on PR #4 (before) and PR #6 (after). No commit in the gap contained a skip-CI directive.

**Determination:** GitHub-side incident (most likely Actions queue or webhook delivery degradation isolated to this repo + window). Not actionable on our side. PR #5 (`9.8h.6 — load_dotenv() order fix`) was merged anyway on the basis of production-truth proof (the `[config-sanity]` line at 17:35:55 IST showed the fix took effect) and local pytest 153/4 green.

## Evidence

### Run history

| Time (UTC) | Branch | Event | SHA | Run result | Run ID |
|---|---|---|---|---|---|
| 2026-05-25T20:25:45 | `phase-9.8f-bloomberg` | push (PR #4 merge) | `1e4c354` | success | 26418439543 |
| **2026-05-26T11:41:37** | `phase-9.8h.6-loaddotenv-order` | branch create + initial push | (PR #5 head) | **no run** | — |
| 2026-05-26T11:41:39 | `phase-9.8h.6-loaddotenv-order` | PullRequestEvent (PR #5 opened) | — | **no run** | — |
| **2026-05-26T12:10:04** | `phase-9.8h.6-loaddotenv-order` | push (`da2d257` empty kick) | `da2d257` | **no run** | — |
| **2026-05-26T12:14:17** | `phase-9.8h.6-loaddotenv-order` | PullRequestEvent (PR #5 merged) | — | **no run** | — |
| **2026-05-26T12:14:19** | `phase-9.8f-bloomberg` | push (PR #5 merge) | `d9a0a6d` | **no run** | — |
| 2026-05-26T21:23:11 | `phase-9.8h.7-trail-stop-delta-quantify` | branch create + push | `18fd2bb` | success | 26475959197 |
| 2026-05-26T21:24:03 | `phase-9.8h.7-trail-stop-delta-quantify` | PullRequestEvent (PR #6) | `18fd2bb` | success | 26475996947 |

API confirmations (via `gh api`):

- `GET /repos/devpilotX/OU-MRS/actions/runs?branch=phase-9.8h.6-loaddotenv-order&per_page=50` → `total_count: 0`
- `GET /repos/devpilotX/OU-MRS/actions/runs?head_sha=d9a0a6d…` → `total_count: 0`
- `GET /repos/devpilotX/OU-MRS/actions/runs?head_sha=da2d257…` → `total_count: 0`

### Configuration check

- `GET /repos/.../actions/permissions` → `{enabled: true, allowed_actions: all, sha_pinning_required: false}`
- Workflow `CI` (ID 270926151): `state: active`, `updated_at: 2026-05-05` (no tampering).
- `.github/workflows/ci.yml` on PR #5 head and on `da2d257` is **byte-identical** to the version that ran successfully on PR #4 and PR #6 (verified via `git show <sha>:.github/workflows/ci.yml`).
- Trigger pattern: `on.push.branches: [main, "phase-**"]` + `pull_request:` — both event types apply.
- No `[skip ci]` / `[ci skip]` / `[no ci]` directive in any commit message in the window.

### Sanity ruled out

- ❌ Skip-CI directive
- ❌ Workflow file corruption on head
- ❌ Workflow state disabled
- ❌ Actions permissions revoked
- ❌ Trigger pattern mismatch
- ❌ Concurrency cancellation (no preceding run-in-progress to cancel)
- ❌ Token scope (workflow runs require no special scope to *fire*; only to *manage*)
- ❌ Branch protection / required-status rule (none configured)

## Defensive actions shipped

### 1. CI health-check workflow

`.github/workflows/ci-health.yml`: scheduled daily at 04:00 UTC + manual `workflow_dispatch`. Single job that echoes a heartbeat. If no run appears in `actions/runs?workflow=ci-health` for >36h, Actions is degraded for this repo and a manual GitHub Support ticket is warranted.

### 2. CONTRIBUTING.md merge protocol

Added a section documenting: **if no workflow run is registered within 60s of pushing to a `phase-**` branch, do not merge.** Wait, retry with an empty commit, and if still silent, open a GitHub Support ticket. Merge only on independent verification (local pytest green + production smoke).

### Deliberately *not* done

- **Required-status branch protection** on `phase-9.8f-bloomberg` or `main` — would brick development during a real Actions outage. Detect-and-escalate is the right posture, not block-forever.
- **Self-hosted runners** — operational burden not justified by a single 9.7h incident.

## Lessons

1. The `[config-sanity]` line PR #4 added (Sacred Rule #41) was the **only reason** we caught the silent default-capture bug PR #5 fixed. Pre-merge CI green is not sufficient — observability at runtime is the backstop.
2. When CI is silent, do *not* default-trust the change. Surface the gap explicitly in the merge commit message (we did, see `d9a0a6d` body).
3. GitHub Actions has transient repo-level outages that don't always surface on https://www.githubstatus.com. Build local detection.

## References

- PR #5: https://github.com/devpilotX/OU-MRS/pull/5
- Merge commit `d9a0a6d2c8271cf94bf37a5fb0b293fff6cd5269`
- Empty kick commit `da2d257d1a8d1cc0c97571c5e76c658dd9f4911b`
- PR #6 (next branch, ran fine): https://github.com/devpilotX/OU-MRS/pull/6
- Sacred Rule #41 (observability backstop): see instructions page.
