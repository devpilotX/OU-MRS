#!/usr/bin/env python3
"""
Phase 9.8h.7 — Trail-stop delta backtest harness.

Quantifies the P&L impact of the Phase 9.8h.6 load_dotenv() ordering bug fix.

Run A (pre-fix bug):    OU_TRAIL_TRIGGER_ATR_MULT=3.0, OU_TRAIL_LOCK_PCT=0.30
Run B (post-fix .env):  OU_TRAIL_TRIGGER_ATR_MULT=1.5, OU_TRAIL_LOCK_PCT=0.40

All other params held constant at the live .env + strategy.py-default values.

For each of BANKNIFTY / NIFTY / MIDCPNIFTY:
  1. Run backtest.py with A env, capture trades.csv + metrics.json
  2. Run backtest.py with B env, capture trades.csv + metrics.json
  3. Diff: per-symbol P&L, exit-reason redistribution, trade-by-trade pnl delta
  4. Slice by live window (2026-04-28 .. 2026-05-25) for live-parity comparison

Final output:
  bt_out_trail_delta/
    <SYMBOL>/A/{trades.csv,metrics.json,equity.csv,equity.png}
    <SYMBOL>/B/{trades.csv,metrics.json,equity.csv,equity.png}
    <SYMBOL>/delta.json
    portfolio_summary.json
    report.md

Statistical rigor (Sacred Rule #43): block-bootstrap 95% CI on portfolio P&L delta.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
OUT_ROOT = HERE / "bt_out_trail_delta"
SYMBOLS = ["BANKNIFTY", "NIFTY", "MIDCPNIFTY"]
LIVE_START = pd.Timestamp("2026-04-28", tz="Asia/Kolkata")
LIVE_END = pd.Timestamp("2026-05-26", tz="Asia/Kolkata")  # exclusive upper

# Live env locked to current .env + strategy.py defaults (matches today's
# [config-sanity] line printed by ou_mrs.py at startup).
COMMON_ENV: Dict[str, str] = {
    "BT_CAPITAL": "3750000",
    # .env knobs (Phase 9.7N + 9.7AO + 9.7U + 9.7AL.1+):
    "OU_ADX_THRESHOLD": "32",
    "OU_Z_ENTRY": "1.5",
    "OU_REGIME_FILTER": "CHOP,RANGE",
    "OU_Z_STOP_BNF": "2.5",
    "OU_Z_STOP_NF": "2.5",
    "OU_Z_STOP_MCN": "2.5",
    "OU_VOL_CONFIRM": "on",
    "OU_ATR_PCT_FILTER": "on",
    "OU_HL_MIN": "0.5",
    "OU_HL_MAX": "5.0",
    "OU_DISABLE_Z_VEL_STALL": "off",
    "NOTIONAL_LEVERAGE_MAX": "3.0",
    "DAILY_LOSS_LIMIT": "-50000",
    # strategy.py defaults (NOT in .env — match live):
    "OU_ATR_MULT": "1.5",
    "OU_BE_TRIGGER_ATR_MULT": "1.25",
    "OU_BE_LOCK_ATR_MULT": "0.1",
    "OU_PAPER_SL_ATR_MULT": "1.5",
}

CONFIGS: Dict[str, Dict[str, str]] = {
    "A": {  # pre-fix bug (strategy.py defaults active because .env load was too late)
        "OU_TRAIL_TRIGGER_ATR_MULT": "3.0",
        "OU_TRAIL_LOCK_PCT": "0.30",
    },
    "B": {  # post-fix (.env values applied)
        "OU_TRAIL_TRIGGER_ATR_MULT": "1.5",
        "OU_TRAIL_LOCK_PCT": "0.40",
    },
}


def run_backtest(symbol: str, cfg_name: str) -> Tuple[Path, float]:
    """Run backtest.py for one (symbol, config) pair. Returns (out_dir, wall_seconds)."""
    import time
    out_dir = OUT_ROOT / symbol / cfg_name
    out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(COMMON_ENV)
    env.update(CONFIGS[cfg_name])
    # Strip any inherited OU_TRAIL_* that aren't in this config — defensive.
    for k in list(env.keys()):
        if k.startswith("OU_TRAIL_") and k not in CONFIGS[cfg_name]:
            del env[k]
    cmd = [
        sys.executable, "backtest.py",
        "--symbol", symbol,
        "--auto-lot",
        "--out", str(out_dir),
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(HERE), env=env, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - t0
    if proc.returncode != 0:
        log = out_dir / "stderr.log"
        log.write_text(proc.stderr)
        raise RuntimeError(f"backtest failed for {symbol}/{cfg_name}: see {log}")
    (out_dir / "stdout.log").write_text(proc.stdout)
    return out_dir, elapsed


def load_run(out_dir: Path) -> Dict:
    metrics = json.loads((out_dir / "metrics.json").read_text())
    trades_csv = out_dir / "trades.csv"
    trades = pd.read_csv(trades_csv) if trades_csv.exists() and trades_csv.stat().st_size > 50 else pd.DataFrame()
    if not trades.empty:
        trades["entry_ts"] = pd.to_datetime(trades["entry_ts"], utc=False)
        trades["exit_ts"] = pd.to_datetime(trades["exit_ts"], utc=False)
    return {"metrics": metrics, "trades": trades, "dir": out_dir}


def slice_live_window(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    mask = (trades["entry_ts"] >= LIVE_START) & (trades["entry_ts"] < LIVE_END)
    return trades.loc[mask].copy()


def exit_reason_breakdown(trades: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    if trades.empty:
        return {}
    g = trades.groupby("reason")["pnl"]
    return {
        r: {"count": int(g.size().loc[r]), "pnl": round(float(g.sum().loc[r]), 2)}
        for r in g.groups
    }


def stationary_bootstrap_pnl_delta(pnl_a: np.ndarray, pnl_b: np.ndarray, n_iter: int = 2000,
                                   block_p: float = 0.10, seed: int = 42) -> Dict[str, float]:
    """Stationary block bootstrap (Politis & Romano 1994) on per-trade pnl delta.

    pnl_a, pnl_b: per-trade pnl arrays. They are usually different-length, so we
    bootstrap each series separately and take totals.
    """
    rng = np.random.default_rng(seed)
    def boot(arr: np.ndarray) -> float:
        n = len(arr)
        if n == 0:
            return 0.0
        out = np.empty(n)
        i = 0
        while i < n:
            idx = rng.integers(0, n)
            L = rng.geometric(block_p)
            for _ in range(L):
                if i >= n:
                    break
                out[i] = arr[idx % n]
                idx += 1
                i += 1
        return float(out.sum())
    deltas = np.empty(n_iter)
    for k in range(n_iter):
        deltas[k] = boot(pnl_b) - boot(pnl_a)
    return {
        "point": float(pnl_b.sum() - pnl_a.sum()),
        "mean": float(deltas.mean()),
        "ci_low_95": float(np.quantile(deltas, 0.025)),
        "ci_high_95": float(np.quantile(deltas, 0.975)),
        "prob_delta_positive": float((deltas > 0).mean()),
    }


def per_symbol_delta(symbol: str, run_a: Dict, run_b: Dict) -> Dict:
    ta, tb = run_a["trades"], run_b["trades"]
    ta_live, tb_live = slice_live_window(ta), slice_live_window(tb)
    boot_full = stationary_bootstrap_pnl_delta(
        ta["pnl"].to_numpy() if not ta.empty else np.array([]),
        tb["pnl"].to_numpy() if not tb.empty else np.array([]),
    )
    boot_live = stationary_bootstrap_pnl_delta(
        ta_live["pnl"].to_numpy() if not ta_live.empty else np.array([]),
        tb_live["pnl"].to_numpy() if not tb_live.empty else np.array([]),
    )
    return {
        "symbol": symbol,
        "full_window": {
            "A": {"trades": int(len(ta)), "pnl": round(float(ta["pnl"].sum() if not ta.empty else 0), 2),
                  "exit_reasons": exit_reason_breakdown(ta),
                  "metrics": run_a["metrics"]},
            "B": {"trades": int(len(tb)), "pnl": round(float(tb["pnl"].sum() if not tb.empty else 0), 2),
                  "exit_reasons": exit_reason_breakdown(tb),
                  "metrics": run_b["metrics"]},
            "delta_pnl": round(float((tb["pnl"].sum() if not tb.empty else 0) - (ta["pnl"].sum() if not ta.empty else 0)), 2),
            "bootstrap_delta": boot_full,
        },
        "live_window": {
            "A": {"trades": int(len(ta_live)), "pnl": round(float(ta_live["pnl"].sum() if not ta_live.empty else 0), 2),
                  "exit_reasons": exit_reason_breakdown(ta_live)},
            "B": {"trades": int(len(tb_live)), "pnl": round(float(tb_live["pnl"].sum() if not tb_live.empty else 0), 2),
                  "exit_reasons": exit_reason_breakdown(tb_live)},
            "delta_pnl": round(float((tb_live["pnl"].sum() if not tb_live.empty else 0) - (ta_live["pnl"].sum() if not ta_live.empty else 0)), 2),
            "bootstrap_delta": boot_live,
        },
    }


def render_report(deltas: List[Dict], portfolio: Dict) -> str:
    lines = []
    lines.append("# Phase 9.8h.7 — Trail-stop delta backtest\n")
    lines.append("**Purpose**: Quantify the P&L impact of Phase 9.8h.6 load_dotenv ordering bug fix.\n\n")
    lines.append("**Configs**\n")
    lines.append("- **Run A (pre-fix bug)**: OU_TRAIL_TRIGGER_ATR_MULT=3.0, OU_TRAIL_LOCK_PCT=0.30 (strategy.py defaults; bug masked .env)\n")
    lines.append("- **Run B (post-fix)**: OU_TRAIL_TRIGGER_ATR_MULT=1.5, OU_TRAIL_LOCK_PCT=0.40 (.env values applied)\n\n")
    lines.append("All other params held constant at live .env + strategy.py defaults.\n\n")
    lines.append("## Per-symbol P&L (full backtest window 2026-03-27 .. 2026-05-22)\n\n")
    lines.append("| Symbol | A trades | A P&L (₹) | B trades | B P&L (₹) | Δ P&L (₹) | 95% CI (₹) | P(Δ>0) |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---|---:|\n")
    for d in deltas:
        fw = d["full_window"]
        bs = fw["bootstrap_delta"]
        lines.append(
            f"| {d['symbol']} | {fw['A']['trades']} | {fw['A']['pnl']:,.0f} | "
            f"{fw['B']['trades']} | {fw['B']['pnl']:,.0f} | {fw['delta_pnl']:,.0f} | "
            f"[{bs['ci_low_95']:,.0f}, {bs['ci_high_95']:,.0f}] | {bs['prob_delta_positive']:.2%} |\n"
        )
    lines.append("\n## Per-symbol P&L (live window 2026-04-28 .. 2026-05-25)\n\n")
    lines.append("| Symbol | A trades | A P&L (₹) | B trades | B P&L (₹) | Δ P&L (₹) | 95% CI (₹) | P(Δ>0) |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---|---:|\n")
    for d in deltas:
        lw = d["live_window"]
        bs = lw["bootstrap_delta"]
        lines.append(
            f"| {d['symbol']} | {lw['A']['trades']} | {lw['A']['pnl']:,.0f} | "
            f"{lw['B']['trades']} | {lw['B']['pnl']:,.0f} | {lw['delta_pnl']:,.0f} | "
            f"[{bs['ci_low_95']:,.0f}, {bs['ci_high_95']:,.0f}] | {bs['prob_delta_positive']:.2%} |\n"
        )
    lines.append("\n## Portfolio totals\n\n")
    lines.append(f"- **Full-window Δ P&L**: ₹{portfolio['full_window']['delta_pnl']:,.0f} "
                 f"(95% CI [₹{portfolio['full_window']['bootstrap_delta']['ci_low_95']:,.0f}, "
                 f"₹{portfolio['full_window']['bootstrap_delta']['ci_high_95']:,.0f}], "
                 f"P(Δ>0)={portfolio['full_window']['bootstrap_delta']['prob_delta_positive']:.2%})\n")
    lines.append(f"- **Live-window Δ P&L**: ₹{portfolio['live_window']['delta_pnl']:,.0f} "
                 f"(95% CI [₹{portfolio['live_window']['bootstrap_delta']['ci_low_95']:,.0f}, "
                 f"₹{portfolio['live_window']['bootstrap_delta']['ci_high_95']:,.0f}], "
                 f"P(Δ>0)={portfolio['live_window']['bootstrap_delta']['prob_delta_positive']:.2%})\n")
    lines.append("\n## Exit-reason redistribution (full window, portfolio)\n\n")
    lines.append("| Reason | A count | A P&L | B count | B P&L |\n|---|---:|---:|---:|---:|\n")
    a_breakdown: Dict[str, Dict[str, float]] = {}
    b_breakdown: Dict[str, Dict[str, float]] = {}
    for d in deltas:
        for r, v in d["full_window"]["A"]["exit_reasons"].items():
            a_breakdown.setdefault(r, {"count": 0, "pnl": 0.0})
            a_breakdown[r]["count"] += v["count"]
            a_breakdown[r]["pnl"] += v["pnl"]
        for r, v in d["full_window"]["B"]["exit_reasons"].items():
            b_breakdown.setdefault(r, {"count": 0, "pnl": 0.0})
            b_breakdown[r]["count"] += v["count"]
            b_breakdown[r]["pnl"] += v["pnl"]
    reasons = sorted(set(a_breakdown) | set(b_breakdown))
    for r in reasons:
        a = a_breakdown.get(r, {"count": 0, "pnl": 0.0})
        b = b_breakdown.get(r, {"count": 0, "pnl": 0.0})
        lines.append(f"| {r} | {a['count']} | {a['pnl']:,.0f} | {b['count']} | {b['pnl']:,.0f} |\n")
    lines.append("\n---\n*Generated by tools/trail_stop_delta.py — Phase 9.8h.7*\n")
    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=SYMBOLS)
    ap.add_argument("--skip-run", action="store_true", help="Reuse existing outputs.")
    args = ap.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    timing: Dict[str, float] = {}
    runs: Dict[str, Dict[str, Dict]] = {}
    for sym in args.symbols:
        runs[sym] = {}
        for cfg in ("A", "B"):
            out_dir = OUT_ROOT / sym / cfg
            if args.skip_run and (out_dir / "metrics.json").exists():
                print(f"[skip-run] reusing {sym}/{cfg}")
            else:
                print(f"[run] {sym}/{cfg} ... ", end="", flush=True)
                out_dir, elapsed = run_backtest(sym, cfg)
                timing[f"{sym}/{cfg}"] = elapsed
                print(f"{elapsed:.1f}s")
            runs[sym][cfg] = load_run(out_dir)

    deltas: List[Dict] = []
    for sym in args.symbols:
        d = per_symbol_delta(sym, runs[sym]["A"], runs[sym]["B"])
        (OUT_ROOT / sym / "delta.json").write_text(json.dumps(d, indent=2, default=str))
        deltas.append(d)

    # Portfolio aggregate
    all_pnl_a_full = np.concatenate([runs[s]["A"]["trades"]["pnl"].to_numpy() if not runs[s]["A"]["trades"].empty else np.array([]) for s in args.symbols])
    all_pnl_b_full = np.concatenate([runs[s]["B"]["trades"]["pnl"].to_numpy() if not runs[s]["B"]["trades"].empty else np.array([]) for s in args.symbols])
    all_pnl_a_live = np.concatenate([slice_live_window(runs[s]["A"]["trades"])["pnl"].to_numpy() if not runs[s]["A"]["trades"].empty else np.array([]) for s in args.symbols])
    all_pnl_b_live = np.concatenate([slice_live_window(runs[s]["B"]["trades"])["pnl"].to_numpy() if not runs[s]["B"]["trades"].empty else np.array([]) for s in args.symbols])
    portfolio = {
        "full_window": {
            "delta_pnl": round(float(all_pnl_b_full.sum() - all_pnl_a_full.sum()), 2),
            "bootstrap_delta": stationary_bootstrap_pnl_delta(all_pnl_a_full, all_pnl_b_full),
        },
        "live_window": {
            "delta_pnl": round(float(all_pnl_b_live.sum() - all_pnl_a_live.sum()), 2),
            "bootstrap_delta": stationary_bootstrap_pnl_delta(all_pnl_a_live, all_pnl_b_live),
        },
        "timing_seconds": timing,
        "common_env": COMMON_ENV,
        "configs": CONFIGS,
        "symbols": list(args.symbols),
    }
    (OUT_ROOT / "portfolio_summary.json").write_text(json.dumps(portfolio, indent=2, default=str))
    (OUT_ROOT / "report.md").write_text(render_report(deltas, portfolio))
    print(f"\n=== Done ===")
    print(f"Full-window  portfolio Δ: ₹{portfolio['full_window']['delta_pnl']:,.0f}")
    print(f"Live-window  portfolio Δ: ₹{portfolio['live_window']['delta_pnl']:,.0f}")
    print(f"Report: {OUT_ROOT/'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
