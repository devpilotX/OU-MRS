#!/usr/bin/env python3
"""Phase 9.8h.B.5 - slippage sensitivity sweep + vol-regime stratification.

Runs backtest.py at multiple BT_SLIPPAGE_TICKS levels for all 3 symbols,
then stratifies per-trade outcomes by 20-bar realized vol terciles.

Idempotent. Reads bt_out_<sym>/{trades,equity}.csv after each backtest.
Writes:
  validation/phase_9_8h_B_5_slippage_sweep.json
  validation/phase_9_8h_B_5_vol_regime.json
  validation/b5_slip<N>_<SYM>/  (per-cell snapshots)

Usage:
  set -a; . .env; set +a
  ./venv/bin/python tools/slippage_sweep.py
  ./venv/bin/python tools/slippage_sweep.py --slippage 2,5,10,20 --symbols BANKNIFTY,NIFTY,MIDCPNIFTY
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "validation"
OUT_DIR.mkdir(exist_ok=True)

DEFAULT_SLIP = [2, 5, 10, 20]
DEFAULT_SYMBOLS = ["BANKNIFTY", "NIFTY", "MIDCPNIFTY"]
PYTHON = sys.executable


def run_one(slip: int, symbol: str, capital: str = "3750000") -> dict:
    env = os.environ.copy()
    env["BT_SLIPPAGE_TICKS"] = str(slip)
    env["BT_CAPITAL"] = capital
    t0 = time.time()
    r = subprocess.run(
        [PYTHON, str(ROOT / "backtest.py"), "--symbol", symbol, "--auto-lot"],
        env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=300,
    )
    elapsed = time.time() - t0
    metrics_path = ROOT / f"bt_out_{symbol}" / "metrics.json"
    if r.returncode != 0 or not metrics_path.exists():
        return {"slippage_ticks": slip, "symbol": symbol, "error": (r.stderr or r.stdout)[-300:]}
    m = json.loads(metrics_path.read_text())
    snap = OUT_DIR / f"b5_slip{slip}_{symbol}"
    snap.mkdir(exist_ok=True)
    (snap / "metrics.json").write_text(json.dumps(m, indent=2, default=str))
    for fname in ("trades.csv", "equity.csv"):
        src = ROOT / f"bt_out_{symbol}" / fname
        if src.exists():
            (snap / fname).write_bytes(src.read_bytes())
    return {
        "slippage_ticks": slip,
        "slippage_inr_per_side": round(slip * 0.05, 4),
        "symbol": symbol,
        "trades": m.get("trades", 0),
        "total_pnl": round(m.get("total_pnl", 0), 2),
        "win_rate": round(m.get("win_rate", 0), 4),
        "profit_factor": round(m.get("profit_factor", 0), 4),
        "sharpe": round(m.get("sharpe", 0), 4),
        "max_dd_pct": round(m.get("max_drawdown_pct", 0), 4),
        "trades_per_day": round(m.get("trades_per_day", 0), 4),
        "elapsed_sec": round(elapsed, 1),
    }


def vol_regime(symbol: str, slip: int = 2) -> dict | None:
    snap = OUT_DIR / f"b5_slip{slip}_{symbol}"
    trades_p = snap / "trades.csv"
    parquet = ROOT / "data" / f"{symbol}_FUT_1min.parquet"
    if not trades_p.exists() or not parquet.exists():
        return None
    trades = pd.read_csv(trades_p)
    if len(trades) < 3:
        return None
    bars = pd.read_parquet(parquet).sort_index()
    bars["ret"] = np.log(bars["close"] / bars["close"].shift(1))
    bars["rv20"] = bars["ret"].rolling(20).std() * np.sqrt(375)
    entry_col = next((c for c in trades.columns if c.lower() in ("entry_ts", "entry_time", "open_ts")), None)
    pnl_col = next((c for c in trades.columns if c.lower() in ("pnl", "net_pnl", "total_pnl")), None)
    if not entry_col or not pnl_col:
        return None
    trades["_entry_ts"] = pd.to_datetime(trades[entry_col], utc=True).dt.tz_convert("Asia/Kolkata")
    trades["_pnl"] = pd.to_numeric(trades[pnl_col], errors="coerce")
    trades = trades.dropna(subset=["_pnl"]).copy()
    rv = [bars["rv20"].asof(ts) for ts in trades["_entry_ts"]]
    trades["_rv20"] = rv
    trades = trades.dropna(subset=["_rv20"])
    if len(trades) < 3:
        return None
    qs = trades["_rv20"].quantile([1/3, 2/3]).tolist()
    def bucket(v): return "LOW" if v <= qs[0] else ("MID" if v <= qs[1] else "HIGH")
    trades["_bucket"] = trades["_rv20"].apply(bucket)
    stats = {}
    for b in ("LOW", "MID", "HIGH"):
        sub = trades[trades["_bucket"] == b]
        if len(sub) == 0:
            continue
        stats[b] = {
            "n_trades": int(len(sub)),
            "mean_pnl": float(round(sub["_pnl"].mean(), 2)),
            "sum_pnl": float(round(sub["_pnl"].sum(), 2)),
            "win_rate": float(round((sub["_pnl"] > 0).mean(), 4)),
            "sharpe": float(round(sub["_pnl"].mean() / sub["_pnl"].std(), 4)) if sub["_pnl"].std() > 0 else None,
            "rv20_min": float(round(sub["_rv20"].min(), 4)),
            "rv20_max": float(round(sub["_rv20"].max(), 4)),
        }
    return {
        "n_trades_classified": int(len(trades)),
        "rv20_tercile_breaks": [round(qs[0], 4), round(qs[1], 4)],
        "by_bucket": stats,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slippage", default=",".join(str(s) for s in DEFAULT_SLIP),
                    help="Comma-separated slippage tick levels.")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    args = ap.parse_args()
    slips = [int(s) for s in args.slippage.split(",") if s.strip()]
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    results = []
    for slip in slips:
        print(f"\n{'='*70}\nSLIPPAGE = {slip} ticks ({slip*0.05:.2f} INR/side)\n{'='*70}")
        for sym in syms:
            row = run_one(slip, sym)
            results.append(row)
            if "error" in row:
                print(f"  {sym}: FAILED  {row['error']}")
            else:
                print(f"  {sym:>10}  trades={row['trades']:>3}  pnl=Rs{row['total_pnl']:>+12,.0f}  "
                      f"win={row['win_rate']*100:>5.1f}%  PF={row['profit_factor']:>5.2f}  "
                      f"Sh={row['sharpe']:>+6.2f}  DD={row['max_dd_pct']*100:>5.1f}%  ({row['elapsed_sec']:.0f}s)")
    (OUT_DIR / "phase_9_8h_B_5_slippage_sweep.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\n[ok] -> validation/phase_9_8h_B_5_slippage_sweep.json")

    print(f"\n{'='*70}\nVOL REGIME STRATIFICATION (slip=2)\n{'='*70}")
    vol = {}
    base_slip = min(slips)
    for sym in syms:
        r = vol_regime(sym, slip=base_slip)
        if r is None:
            print(f"  {sym}: skip")
            continue
        vol[sym] = r
        print(f"  {sym}: classified={r['n_trades_classified']}  breaks={r['rv20_tercile_breaks']}")
        for b, s in r["by_bucket"].items():
            sh = f"{s['sharpe']:+.3f}" if s["sharpe"] is not None else "na"
            print(f"    {b:>4}: n={s['n_trades']:>2}  mean=Rs{s['mean_pnl']:>+10,.0f}  win={s['win_rate']*100:>5.1f}%  Sh={sh}")
    (OUT_DIR / "phase_9_8h_B_5_vol_regime.json").write_text(json.dumps(vol, indent=2, default=str))
    print(f"\n[ok] -> validation/phase_9_8h_B_5_vol_regime.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
