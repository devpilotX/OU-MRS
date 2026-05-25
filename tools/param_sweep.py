"""Phase 9.8h: parameter sweep with selection-bias correction.

Grid sweeps the protective-exit parameters per symbol. For each (config, symbol),
runs backtest.py with the config injected via env, computes Deflated Sharpe
Ratio (Bailey-LdP 2014) with n_trials set to the actual sweep size so the
reported significance is honestly multiple-testing corrected.

Results are ranked by DSR-corrected, NOT raw Sharpe. This is the Bailey-LdP
defense against picking the lucky cell of a 200-cell grid (Sacred Rule #43).

Grid (default):
  OU_PAPER_SL_ATR_MULT     in {1.5, 2.0, 2.5}                       (3)
  OU_BE_TRIGGER_ATR_MULT   in {0.0, 0.75, 1.0, 1.25}                (4) -- 0.0 disables BE
  OU_TRAIL_TRIGGER_ATR_MULT in {1.5, 2.0, 2.5, 3.0}                 (4)
  OU_TRAIL_LOCK_PCT        in {0.3, 0.4, 0.5, 0.6}                  (4)
  -> 192 configs per symbol, ~12s each = ~40 min per symbol

Use --coarse to drop to 2 points per axis: 2*2*2*2 = 16 configs, ~5 min/symbol.
Use --quick to test only one corner cell (sanity check).

Usage:
  python tools/param_sweep.py --symbol BANKNIFTY --coarse
  python tools/param_sweep.py --symbol NIFTY
  python tools/param_sweep.py --symbol MIDCPNIFTY --quick
"""
from __future__ import annotations
import os, sys, json, csv, argparse, itertools, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

DEFAULT_GRID = {
    "OU_PAPER_SL_ATR_MULT":      [1.5, 2.0, 2.5],
    "OU_BE_TRIGGER_ATR_MULT":    [0.0, 0.75, 1.0, 1.25],
    "OU_TRAIL_TRIGGER_ATR_MULT": [1.5, 2.0, 2.5, 3.0],
    "OU_TRAIL_LOCK_PCT":         [0.3, 0.4, 0.5, 0.6],
}

COARSE_GRID = {k: [v[0], v[-1]] for k, v in DEFAULT_GRID.items()}

QUICK_GRID = {k: [v[len(v) // 2]] for k, v in DEFAULT_GRID.items()}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True,
                    choices=["BANKNIFTY", "NIFTY", "MIDCPNIFTY"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--coarse", action="store_true")
    ap.add_argument("--quick", action="store_true")
    return ap.parse_args()


def run_one(symbol: str, env_overrides: dict, out_dir: Path) -> dict:
    env = os.environ.copy()
    env.update({k: str(v) for k, v in env_overrides.items()})
    env.setdefault("BT_CAPITAL", "3750000")
    env.setdefault("OU_ATR_MULT", "1.2")
    cmd = ["python", "backtest.py", "--symbol", symbol, "--auto-lot",
           "--out", str(out_dir)]
    r = subprocess.run(cmd, cwd=str(HERE), env=env,
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return {"error": r.stderr[-500:]}
    mp = out_dir / "metrics.json"
    if not mp.exists():
        return {"error": "no metrics.json"}
    return json.loads(mp.read_text())


def compute_dsr_for_run(out_dir: Path, n_trials: int) -> float:
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


def main():
    args = parse_args()
    if args.quick:
        grid = QUICK_GRID
    elif args.coarse:
        grid = COARSE_GRID
    else:
        grid = DEFAULT_GRID
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    configs = list(itertools.product(*values))
    n_trials = len(configs)

    sweep_root = Path(args.out) if args.out else (HERE / f"bt_sweep_{args.symbol}")
    sweep_root.mkdir(parents=True, exist_ok=True)

    print(f"Symbol: {args.symbol}")
    print(f"Grid size: {n_trials} configs")
    for k, v in grid.items():
        print(f"  {k}: {v}")
    print()

    results = []
    for i, vals in enumerate(configs):
        overrides = dict(zip(keys, vals))
        run_dir = sweep_root / f"cfg_{i:04d}"
        run_dir.mkdir(exist_ok=True)
        metrics = run_one(args.symbol, overrides, run_dir)
        dsr = compute_dsr_for_run(run_dir, n_trials)
        row = dict(overrides)
        for k in ("trades", "win_rate", "profit_factor", "total_pnl",
                  "sharpe", "max_drawdown_pct"):
            row[k] = metrics.get(k) if isinstance(metrics, dict) else None
        row["dsr_corrected_n" + str(n_trials)] = dsr
        row["config_id"] = i
        if "error" in (metrics or {}):
            row["error"] = metrics["error"]
        results.append(row)
        pnl_str = ("%.0f" % metrics["total_pnl"]) if isinstance(metrics, dict) and "total_pnl" in metrics else "ERR"
        dsr_str = ("%.3f" % dsr) if dsr == dsr else "nan"
        print(f"[{i+1:3d}/{n_trials}] paper={overrides['OU_PAPER_SL_ATR_MULT']} be={overrides['OU_BE_TRIGGER_ATR_MULT']} trail={overrides['OU_TRAIL_TRIGGER_ATR_MULT']}/{overrides['OU_TRAIL_LOCK_PCT']}  pnl={pnl_str} dsr={dsr_str}")

    def _rank_key(r):
        d = r.get("dsr_corrected_n" + str(n_trials))
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
        print(f"\nWrote {csv_path}")
        print(f"\nTop 5 configs for {args.symbol} (ranked by DSR_n{n_trials}):")
        for r in results[:5]:
            print("  " + " ".join(f"{k}={r.get(k)}" for k in keys)
                  + f"  pnl={r.get('total_pnl')} dsr={r.get('dsr_corrected_n' + str(n_trials))}")

        best = results[0]
        bp = sweep_root / "best.json"
        bp.write_text(json.dumps(best, indent=2, default=str))
        print(f"\nBest config -> {bp}")


if __name__ == "__main__":
    main()
