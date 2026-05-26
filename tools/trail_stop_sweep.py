"""Phase 9.8h.A.3: 2D DSR-corrected sweep on (TRAIL_TRIGGER, TRAIL_LOCK).

Grid:
  OU_TRAIL_TRIGGER_ATR_MULT in {1.0, 1.25, 1.5, 1.75, 2.0, 2.5}   (6)
  OU_TRAIL_LOCK_PCT         in {0.30, 0.40, 0.50, 0.60}          (4)
  -> 24 cells per symbol x 3 symbols = 72 backtests, ~18 min total.

All other params pinned to live .env values. DSR uses n_trials = grid size
(per Bailey-Lopez de Prado 2014, Sacred Rule #43).

Output:
  bt_out_trail_sweep/{SYMBOL}/cfg_{i:04d}/  (raw backtest outputs)
  bt_out_trail_sweep/{SYMBOL}/results.csv
  bt_out_trail_sweep/{SYMBOL}/best.json
  bt_out_trail_sweep/portfolio_summary.json
  bt_out_trail_sweep/report.md
"""
from __future__ import annotations
import os, sys, json, csv, argparse, itertools, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

SYMBOLS = ["BANKNIFTY", "NIFTY", "MIDCPNIFTY"]
TRIG_KEY = "OU_TRAIL_TRIGGER_ATR_MULT"
LOCK_KEY = "OU_TRAIL_LOCK_PCT"

GRID = {
    TRIG_KEY: [1.0, 1.25, 1.5, 1.75, 2.0, 2.5],
    LOCK_KEY: [0.30, 0.40, 0.50, 0.60],
}
QUICK = {TRIG_KEY: [1.5], LOCK_KEY: [0.40]}

# Pins: all other params held at live .env values. backtest.py calls
# load_dotenv at import time (post-9.8h.6), so .env populates first; these
# setdefaults are defensive insurance and document the pinning explicitly.
PINS = {
    "BT_CAPITAL": "3750000",
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
    "OU_ATR_MULT": "1.2",
    "OU_BE_TRIGGER_ATR_MULT": "1.25",
    "OU_BE_LOCK_ATR_MULT": "0.1",
    "OU_PAPER_SL_ATR_MULT": "1.5",
}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=SYMBOLS, choices=SYMBOLS)
    ap.add_argument("--out", default="bt_out_trail_sweep")
    ap.add_argument("--quick", action="store_true")
    return ap.parse_args()


def run_one(symbol, env_overrides, out_dir):
    env = os.environ.copy()
    for k, v in PINS.items():
        env.setdefault(k, v)
    env.update({k: str(v) for k, v in env_overrides.items()})
    cmd = [sys.executable, "backtest.py", "--symbol", symbol, "--auto-lot",
           "--out", str(out_dir)]
    r = subprocess.run(cmd, cwd=str(HERE), env=env,
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return {"error": r.stderr[-500:]}
    mp = out_dir / "metrics.json"
    if not mp.exists():
        return {"error": "no metrics.json"}
    return json.loads(mp.read_text())


def compute_dsr(out_dir, n_trials):
    from validation.bootstrap import deflated_sharpe_ratio, load_trades_pnl
    trades_csv = out_dir / "trades.csv"
    if not trades_csv.exists():
        return float("nan")
    try:
        pnl = load_trades_pnl(trades_csv)
    except Exception:
        return float("nan")
    if len(pnl) < 4:
        return float("nan")
    try:
        d = deflated_sharpe_ratio(pnl, n_trials=max(2, n_trials), ann_factor=1)
        v = d.get("dsr")
        return float(v) if v is not None else float("nan")
    except Exception:
        return float("nan")


def sweep_symbol(symbol, grid, out_root):
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    configs = list(itertools.product(*values))
    n_trials = len(configs)
    dsr_col = "dsr_n{}".format(n_trials)

    sweep_root = out_root / symbol
    sweep_root.mkdir(parents=True, exist_ok=True)

    print("\n=== {}: {} configs ===".format(symbol, n_trials), flush=True)
    results = []
    t0 = time.time()
    for i, vals in enumerate(configs):
        overrides = dict(zip(keys, vals))
        run_dir = sweep_root / "cfg_{:04d}".format(i)
        run_dir.mkdir(exist_ok=True)
        metrics = run_one(symbol, overrides, run_dir)
        dsr = compute_dsr(run_dir, n_trials)
        row = dict(overrides)
        for k in ("trades", "win_rate", "profit_factor", "total_pnl",
                  "sharpe", "max_drawdown_pct"):
            row[k] = metrics.get(k) if isinstance(metrics, dict) else None
        row[dsr_col] = dsr
        row["config_id"] = i
        if "error" in (metrics or {}):
            row["error"] = metrics["error"]
        results.append(row)
        pnl_str = ("%.0f" % metrics["total_pnl"]) if isinstance(metrics, dict) and "total_pnl" in metrics else "ERR"
        dsr_str = ("%.3f" % dsr) if dsr == dsr else "nan"
        print("  [{:2d}/{}] trig={} lock={}  pnl={} dsr={}".format(
            i + 1, n_trials, overrides[TRIG_KEY], overrides[LOCK_KEY],
            pnl_str, dsr_str), flush=True)

    def _rank_key(r):
        d = r.get(dsr_col)
        if d is None or d != d:
            d = -999.0
        p = r.get("total_pnl") or 0.0
        return (-d, -p)
    results.sort(key=_rank_key)

    csv_path = sweep_root / "results.csv"
    if results:
        all_keys = sorted({k for r in results for k in r.keys()})
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            w.writerows(results)
        best = results[0]
        (sweep_root / "best.json").write_text(json.dumps(best, indent=2, default=str))

    elapsed = time.time() - t0
    return {"symbol": symbol, "n_trials": n_trials,
            "results": results, "elapsed_s": elapsed}


def build_report(out_root, per_symbol, grid):
    L = []
    L.append("# Phase 9.8h.A.3 \u2014 Trail-stop 2D DSR-corrected sweep\n\n")
    L.append("**Grid (per symbol):**\n")
    for k, v in grid.items():
        L.append("- `{}` in {}\n".format(k, v))
    n_cells = 1
    for v in grid.values():
        n_cells *= len(v)
    L.append("\n**Cells per symbol:** {}  \n".format(n_cells))
    L.append("**Total backtests:** {}  \n".format(n_cells * len(per_symbol)))
    L.append("**DSR n_trials:** {} (Bailey-LdP 2014, Sacred Rule #43)\n\n".format(n_cells))
    L.append("**Pins (all other params at live .env):**\n")
    for k, v in PINS.items():
        L.append("- `{}` = `{}`\n".format(k, v))
    L.append("\n## Top 3 per symbol (ranked by DSR-corrected, tiebreak by total_pnl)\n")
    for s in per_symbol:
        L.append("\n### {}  (elapsed {:.1f}s)\n\n".format(s["symbol"], s["elapsed_s"]))
        L.append("| Rank | TRAIL_TRIGGER | TRAIL_LOCK | Trades | Total P&L (Rs) | Raw Sharpe | DSR | Max DD %% |\n")
        L.append("|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        dsr_col = "dsr_n{}".format(s["n_trials"])
        for rank, r in enumerate(s["results"][:3], 1):
            pnl = r.get("total_pnl")
            dsr = r.get(dsr_col)
            sh = r.get("sharpe")
            mdd = r.get("max_drawdown_pct")
            tr = r.get("trades")
            pnl_s = "{:,.0f}".format(pnl) if isinstance(pnl, (int, float)) else "-"
            dsr_s = "{:.3f}".format(dsr) if isinstance(dsr, (int, float)) and dsr == dsr else "-"
            sh_s = "{:.2f}".format(sh) if isinstance(sh, (int, float)) and sh == sh else "-"
            mdd_s = "{:.2f}".format(mdd) if isinstance(mdd, (int, float)) and mdd == mdd else "-"
            L.append("| {} | {} | {} | {} | {} | {} | {} | {} |\n".format(
                rank, r[TRIG_KEY], r[LOCK_KEY], tr, pnl_s, sh_s, dsr_s, mdd_s))
    L.append("\n## Live config reference\n")
    L.append("Live `.env` (post-9.8h.6): `OU_TRAIL_TRIGGER_ATR_MULT=1.5`, `OU_TRAIL_LOCK_PCT=0.40`.\n")
    L.append("\n---\n*Generated by `tools/trail_stop_sweep.py`*\n")
    (out_root / "report.md").write_text("".join(L))


def main():
    args = parse_args()
    grid = QUICK if args.quick else GRID
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    per_symbol = []
    for sym in args.symbols:
        per_symbol.append(sweep_symbol(sym, grid, out_root))
    summary = {
        "grid": grid,
        "pins": PINS,
        "symbols": args.symbols,
        "per_symbol_n_trials": {s["symbol"]: s["n_trials"] for s in per_symbol},
        "elapsed_s": time.time() - t0,
    }
    (out_root / "portfolio_summary.json").write_text(
        json.dumps(summary, indent=2, default=str))
    build_report(out_root, per_symbol, grid)
    print("\nDONE in {:.1f}s. Report at {}/report.md".format(
        summary["elapsed_s"], out_root))


if __name__ == "__main__":
    main()
