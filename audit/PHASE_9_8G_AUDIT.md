# Phase 9.8g — Full Repo Audit

**Date:** 25 May 2026 (Asia/Calcutta)
**Branch reviewed:** `phase-9.8f-bloomberg` @ `969fbf4`
**Fixes branch:** `phase-9.8g-audit-fixes` (this branch)
**Reviewer mandate (user, 25 May 2026 00:35 IST):** *"review every dot by dot code, any error any bugs and any kind of issue... do anything and update source code, and update readme."*
**Backtest gate:** Sacred Rule #31 — PR stays open against `phase-9.8f-bloomberg`. DO NOT auto-merge. Run BNF + NF + MCN backtests against the 11-day live window (29 Apr – 21 May 2026) before merging.

---

## 1. Branch survey (user asked to confirm "only 1 or 2 are working")

| Branch | Last commit | Verdict |
|---|---|---|
| `phase-9.8f-bloomberg` | `969fbf4` (24 May 2026) | **Live / active** — the only branch deployed on the VPS |
| `main` | `2e3f05d` | **Stale.** Last touched before Phase 8 began. Useful only as a historical anchor. |
| `phase-8f-capital-sizer` | `403dda4` | **Stale / merged.** Superseded by 9.7AL.1 dual-cap. |
| `phase-8g-multi-instrument` | `3467ab6` | **Stale / merged.** Multi-instrument shipped via 8g.2.a + later phases. |
| `phase-9.8d-dashboard-stabilization` | `d1650a2` | **Stale / out-of-scope.** Belongs to the dashboard project (Opus 4.7), Hard Constraint #1. |
| `phase-9.8e-calendar-and-ui` | `701b566` | **Stale / out-of-scope.** Dashboard concern. |

**Decision:** branches are kept (per user instruction 25 May 00:43 IST: *"Keep them, just tag 9.8f as the only active branch"*). This audit doc and the README now declare `phase-9.8f-bloomberg` as the single active branch. Stale branches are not deleted.

---

## 2. Findings index

| ID | Severity | File | Status |
|---|---|---|---|
| B1 | High | `ou_mrs.py` L56 + `ou_mrs_runner.py` L40 | partial (runner fixed in 9.8g.1, ou_mrs.py = manual) |
| B2 | High | `ou_mrs.py` `size_lots()` | manual (see §4) |
| B3 | High | `backtest.py` TRAIL_STOP indentation | **fixed in 9.8g.2** |
| B4 | High | `signal_publisher.py` no per-symbol routing | **fixed in 9.8g.3** (module side) + manual call-site (see §4) |
| B5 | Low | `README.md` duplicate disclaimer | **fixed in 9.8g.5** |
| B6 | Low | `strategy.py` dead vols guard | **fixed in 9.8g.4** |
| M7 | Med | `.env.example` FINNIFTY stale | **fixed in 9.8g.6** |
| I6 | Med | `backtest.py` hardcoded CAPITAL/LOT/MAX_LOTS | **fixed in 9.8g.2** |

Severity scale: High = silent wrong behavior in production; Med = misleading or rotation-time hazard; Low = code-hygiene / dead code.

---

## 3. Findings detail

### B1 — Stale `_LOT_SIZE_AL` / `_lot_nse` dictionaries (Hard Constraint #3)

- `ou_mrs.py` line 56 still defines `_LOT_SIZE_AL = {"BNF":30,"NF":75,"MCN":120,"SENSEX":10}`. **NF=75 is stale** — production reverted to NF=65 in Phase 9.7AQ on 21 May 2026 (verified against `data/instruments.db` scripmaster).
- `ou_mrs_runner.py` line 40 had the same stale dict as `_lot_nse`.
- Risk: any future code path reading these dicts instead of `INSTRUMENT_CFG[sym]['lot_size']` sizes NF trades against 75 contracts/lot — **15% oversized**.
- **Fix (runner, shipped 9.8g.1):** removed `_lot_nse` entirely; `self.lot_size = self.cfg['lot_size']`. Approx-spot moved to a module-level default with cfg override.
- **Fix (ou_mrs.py, manual — see §4):** delete `_LOT_SIZE_AL` and any local reads of it.
- **New Sacred Rule #33:** `INSTRUMENT_CFG` in `ou_mrs.py` is the single source of truth for lot sizes and tokens. No module shall re-declare them.

### B2 — `size_lots()` ignores tier policy and OU_ATR_MULT

`ou_mrs.py` `size_lots()` currently has:

```python
stop = max(atr * 1.5, 20)              # ignores OU_ATR_MULT=1.2
budget = 0.25 * 0.05 * capital         # = 1.25% of capital, not tier risk_per_trade_pct
```

- HEDGE_FUND tier (from `tier_policy.py`, qualified at capital ≥ ₹25L < ₹50L) wants `risk_per_trade_pct = 0.005` (0.5%). The current code sizes positions against 1.25% — **2.5x larger than tier policy intends**.
- `OU_ATR_MULT=1.2` env override (Phase 9.7AO) is silently ignored by the sizer; only the live stop-placement code reads it. Sizing therefore uses a wider stop than the actual stop, undersizing risk per Rupee.
- **Fix (manual):** rewrite `size_lots()` to pull `risk_pct = _POLICY['risk_per_trade_pct']` and `atr_mult = runner.atr_mult` (the runner already reads `OU_ATR_MULT`). See §4 for the patch.

### B3 — TRAIL_STOP unreachable in `backtest.py` (since Phase 9.5g)

```python
if not reason and should_velocity_stop(...):
    reason = "Z_VEL_STALL"
    # Phase 9.5g: trail stop check (last priority)
    if not reason:        #  <-- always False here, reason was just set
        ...
        if should_trail_stop(...):
            reason = "TRAIL_STOP"
```

- Indentation bug: `should_trail_stop` was nested **inside** the Z_VEL_STALL true-branch where `reason` is already set, so `if not reason` was always false. **TRAIL_STOP has never appeared in any backtest's `metrics.json['reasons']` since 9.5g shipped on 8 May.**
- Compounding: `_mtm` was only computed inside `if sig:`, so on bars with no signal the peak wasn't refreshed either.
- **Fix (shipped 9.8g.2):** lifted `_mtm` + `peak_pnl_pts` refresh out of `if sig:`; TRAIL_STOP is now its own top-level `if not reason:` check after Z_VEL_STALL.
- **Backtest verification:** after merging, `bt_out/metrics.json` should now include `TRAIL_STOP` in the `reasons` dict for at least one BNF / NF day in the 29 Apr – 21 May window.

### B4 — `signal_publisher.py` overwrites across symbols

- Module-level `INSTRUMENT = os.environ.get("INSTRUMENT_SYMBOL", "BANKNIFTY26MAY26FUT")` is a single string. `signals_path()` writes one file: `state/<account>/signals.json`.
- With `INSTRUMENTS=BNF,NF,MCN`, the three runners call `publish_entry/exit/flat/heartbeat` against the same file each tick. **The last symbol to write each cycle clobbers the other two.** Tradetron and the dashboard saw only one symbol's state, at random.
- **Fix (module, shipped 9.8g.3):** every publisher now accepts `symbol=` (and optional `instrument_symbol` / `exchange` overrides). When `symbol` is set, the writer targets `signals_<symbol>.json`. No-kwarg behavior is preserved (legacy single-symbol deployments unchanged).
- **Manual call-site edits (§4):** every `signal_publisher.publish_*` / `heartbeat` call in `ou_mrs.py` must add `symbol=runner.symbol` and `instrument_symbol=runner.symbol_full`. Until those are applied, the symbol kwarg defaults to `None` and the legacy single-file behavior continues (still broken multi-symbol).

### B5 — `README.md` duplicate disclaimer

Two near-identical trailing "without walk-forward validation…" lines, artifact of merges `c371df9` + `969fbf4`. Collapsed to one. Also added the Phase 9.8g audit summary section. **Shipped in 9.8g.5.**

### B6 — `strategy.py` dead `vols.sum() <= 0` check

After the TWAP fallback `vols = np.ones_like(vols, dtype=float)`, the very next `if vols.sum() <= 0: return None` is unreachable (`sum == len(vols) > 0`). The accompanying "Strict volume: futures data always has volume" comment also contradicted the fallback two lines above. Both removed. **Shipped in 9.8g.4.** Behavior change: none.

### M7 — `.env.example` references deprecated FINNIFTY

FINNIFTY was swapped to MIDCPNIFTY in Phase 9.7O on 15 May 2026, but `.env.example` still listed `FINNIFTY_FUT_SYMBOL` / `FINNIFTY_FUT_TOKEN` with no MIDCPNIFTY equivalent. Anyone bootstrapping from the template produced a broken `.env`. **Shipped in 9.8g.6** — swapped, plus surfaced the full armor-stack env vars the live config relies on (`OU_ATR_MULT`, `NOTIONAL_LEVERAGE_MAX`, `OU_Z_STOP_*`, `DAILY_LOSS_LIMIT`, `STOP_CIRCUIT_THRESHOLD`, `MAX_CONCURRENT_POSITIONS`, and the new `BT_*` knobs).

### I6 — `backtest.py` capital/lot/max_lots hardcoded

`CAPITAL=150_000`, `LOT_SIZE=15`, `MAX_LOTS=2` were module-level constants. Every backtest reported on a ₹1.5L base regardless of the live tier (HEDGE_FUND @ ₹37.5L). **Shipped in 9.8g.2** — `BT_CAPITAL` / `BT_LOT_SIZE` / `BT_MAX_LOTS` / `BT_KELLY` / `BT_RISK_PCT` env overrides with the old values as defaults.

---

## 4. Manual edits required on the VPS (`ou_mrs.py`)

`ou_mrs.py` is large (~42 KB) and the agent's file-content view truncated it at ~56% (B1 visible, B2/B4 call sites not visible). Rather than risk a partial-overwrite rewrite via the GitHub MCP `create_or_update_file` (which would silently drop the bottom half of the file), the following edits are documented for manual application by the human on the VPS, then committed by hand.

**Sacred Rule #34 (new):** for any source file above ~30 KB, do NOT use `create_or_update_file` to round-trip a full rewrite through the agent. Use `sed`/`patch`/`scp` on the VPS instead, or split the file before editing. Truncation in the tool view is invisible to the writer and produces silent data loss.

### Edit 1 — drop `_LOT_SIZE_AL` (B1)

```bash
cd /home/ubuntu/bots/ou-mrs
git checkout phase-9.8g-audit-fixes
git pull --ff-only
# Verify the dict is present
grep -n '_LOT_SIZE_AL' ou_mrs.py
# Remove the line (one-shot, single line)
sed -i '/_LOT_SIZE_AL = {/d' ou_mrs.py
# If the dict spans multiple lines, open ou_mrs.py and delete the block
# from `_LOT_SIZE_AL = {` through the matching `}` line.
# Then grep -n '_LOT_SIZE_AL' ou_mrs.py  to confirm zero hits.
```

Also grep for any `_LOT_SIZE_AL[...]` reads in `ou_mrs.py`. Each must be replaced with `runner.lot_size` or `INSTRUMENT_CFG[sym]['lot_size']`.

### Edit 2 — rewrite `size_lots()` to use tier policy + OU_ATR_MULT (B2)

Replace the body of `size_lots()` (current ~5 lines) with the following. Patch it in your editor, do not paste through chat (Sacred Rule #8).

```python
def size_lots(runner, atr: float) -> int:
    """Phase 9.8g.2 (audit B2): size from tier policy + OU_ATR_MULT.

    runner.atr_mult already honors OU_ATR_MULT env (set in OuMrsRunner.__init__).
    risk_pct comes from _POLICY['risk_per_trade_pct'] (HEDGE_FUND = 0.005).
    """
    atr_mult = float(getattr(runner, 'atr_mult', 1.5))
    stop_rs  = max(atr * atr_mult, 20.0)
    risk_pct = float(_POLICY.get('risk_per_trade_pct', 0.005))
    budget   = risk_pct * runner.capital
    raw      = budget / (stop_rs * runner.lot_size)
    return max(1, min(runner.max_lots, int(raw)))
```

Then update **every call site** of `size_lots(...)` in `ou_mrs.py` to pass `runner` first (e.g. `qty = size_lots(runner, sig.atr)`).

### Edit 3 — per-symbol `signal_publisher` calls (B4)

In `ou_mrs.py`, locate every call to `signal_publisher.publish_entry`, `publish_exit`, `publish_flat`, and `heartbeat`. Add `symbol=runner.symbol` and `instrument_symbol=runner.symbol_full` to each call.

Grep first to find all call sites:

```bash
grep -n 'signal_publisher\.' ou_mrs.py
```

For each line, append the kwargs. Example transformations:

```python
# before
signal_publisher.publish_entry(side, qty, runner.lot_size, fill_px, ts, sl_px)
# after
signal_publisher.publish_entry(side, qty, runner.lot_size, fill_px, ts, sl_px,
                               symbol=runner.symbol, instrument_symbol=runner.symbol_full)

# before
signal_publisher.heartbeat(pnl)
# after
signal_publisher.heartbeat(pnl, symbol=runner.symbol)

# before
signal_publisher.publish_flat()
# after
signal_publisher.publish_flat(symbol=runner.symbol, instrument_symbol=runner.symbol_full)

# before
signal_publisher.publish_exit(realized_pnl=realized)
# after
signal_publisher.publish_exit(realized_pnl=realized, symbol=runner.symbol,
                              instrument_symbol=runner.symbol_full)
```

After these edits, downstream consumers must read from `state/<account>/signals_bnf.json`, `_nf.json`, `_mcn.json` instead of the single `signals.json`. The dashboard fetcher is owned by Opus 4.7 (Hard Constraint #1) — raise this in the next dashboard handoff spec update.

### Commit + push the manual edits

```bash
cd /home/ubuntu/bots/ou-mrs
git checkout phase-9.8g-audit-fixes
git pull --ff-only
# (apply edits 1-3 manually)
python -c "import ou_mrs"   # smoke test for syntax errors
python backtest.py          # Sacred Rule #31 backtest gate
# inspect bt_out/metrics.json for TRAIL_STOP appearance + sane sizing
git add ou_mrs.py
git commit -m "fix(9.8g.8): manual edits — drop _LOT_SIZE_AL, tier-aware size_lots, per-symbol signal_publisher"
git push origin phase-9.8g-audit-fixes
```

---

## 5. Out-of-scope / NOT touched

- Dashboard (`algo.devpilotx.com`) — Hard Constraint #1, Opus 4.7's project.
- `.env` on the VPS — Hard Constraint #2, never `git add .env`.
- `data/instruments.db` schema — Sacred Rule #6, source of truth, do not edit from memory.
- Bot restart — Hard Constraint #6, only when flat. The PR is opened against `phase-9.8f-bloomberg` precisely so that no live behavior changes until the user explicitly merges + restarts during a flat window.

## 6. PR + merge protocol (Sacred Rule #31)

1. PR `phase-9.8g-audit-fixes` → `phase-9.8f-bloomberg` is opened as a **draft**.
2. Apply manual edits (§4), push commit 9.8g.8.
3. Run `python backtest.py` for BNF, NF, MCN against the 29 Apr – 21 May window. Sample command:
   ```bash
   for SYM in BANKNIFTY NIFTY MIDCPNIFTY; do
     BT_DATA=data/${SYM}_FUT_1min.parquet \
     BT_CAPITAL=3750000 BT_LOT_SIZE=30 BT_MAX_LOTS=7 \
     OU_ATR_MULT=1.2 python backtest.py
     cp -r bt_out bt_out_${SYM}_9.8g
   done
   ```
4. Confirm `bt_out_*/metrics.json` shows `TRAIL_STOP` in the `reasons` dict (B3 verification), and that net P&L on the window is **not worse than the 9.8f baseline**.
5. Mark PR ready for review, squash-merge, **then** restart the bot only when all three runners report flat.

## 7. New sacred rules added from this audit

- **#33** — `INSTRUMENT_CFG` is the single source of truth for lot sizes and tokens. No module re-declares them. Stale duplicate dicts are landmines (see B1).
- **#34** — Files above ~30 KB must not be rewritten through the GitHub MCP `create_or_update_file` round-trip. Use `sed`/`patch`/`scp` on the VPS, or split the file first. The agent's file view truncates silently.
- **#35** — Any "check" nested inside another check's true-branch is suspect; review its guard expression carefully. TRAIL_STOP was unreachable for 17 days because of one extra level of indentation.
- **#36** — A single shared output file across multiple symbols is always wrong; per-symbol file routing is mandatory whenever `INSTRUMENTS` has > 1 entry.
- **#37** — `.env.example` must mirror the production `.env` keyset (values blank). Bootstrap from template should produce a working config after credentials are filled in; otherwise the template is a liability.
