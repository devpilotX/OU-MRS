"""
C.4.b control experiment: slice INDEX-mode backtest output to the FUT calendar
window and compare to the C.3 FUT-window backtest. Isolates basis-effect from
regime-effect.

FUT windows (from tool-624 disk inspection):
  BANKNIFTY FUT: 2026-03-30 -> 2026-05-26 (38 trading sessions)
  MIDCPNIFTY FUT: 2026-03-27 -> 2026-05-22 (37 trading sessions)

INDEX windows (from tool-628):
  BANKNIFTY INDEX: 2025-10-01 -> 2026-04-24 (137 sessions)
  MIDCPNIFTY INDEX: 2025-10-01 -> 2026-05-15 (151 sessions)

Overlap = INDEX-end vs FUT-start (BNF ~26 sessions, MCN ~37 sessions). Slice each
INDEX trades.csv to its FUT calendar window and recompute metrics. Compare to
the C.4 unsliced metrics and (when available) the C.3 FUT metrics.
"""
import json, math, os, sys
from pathlib import Path

import pandas as pd
import numpy as np

REPO = Path("/home/ubuntu/bots/ou-mrs")

FUT_WINDOWS = {
    "BANKNIFTY":  ("2026-03-30", "2026-05-26"),
    "MIDCPNIFTY": ("2026-03-27", "2026-05-22"),
}

def sharpe_annualized_from_trade_pnl(pnls, periods_per_year=252):
    arr = np.array(pnls, dtype=float)
    if len(arr) < 2 or arr.std(ddof=1) == 0:
        return 0.0
    return float((arr.mean() / arr.std(ddof=1)) * math.sqrt(periods_per_year))

def compute_metrics(trades_df):
    if len(trades_df) == 0:
        return {"trades": 0, "win_rate": None, "pf": None, "sharpe": None, "total_pnl": 0.0}
    pnl = trades_df["pnl"].astype(float)
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    pf = (wins / losses) if losses > 0 else float("inf")
    wr = float((pnl > 0).sum() / len(pnl))
    return {
        "trades": int(len(pnl)),
        "win_rate": round(wr, 4),
        "pf": round(pf, 3) if pf != float("inf") else "inf",
        "sharpe": round(sharpe_annualized_from_trade_pnl(pnl), 3),
        "total_pnl": round(float(pnl.sum()), 2),
    }

def slice_symbol(sym):
    bt_out = REPO / f"bt_out_{sym}"
    trades_csv = bt_out / "trades.csv"
    if not trades_csv.exists():
        return {"error": f"no trades.csv at {trades_csv}"}
    df = pd.read_csv(trades_csv)
    # entry_ts is the canonical timestamp column
    ts_col = None
    for cand in ("entry_ts", "entry_time", "timestamp", "ts"):
        if cand in df.columns:
            ts_col = cand; break
    if ts_col is None:
        return {"error": f"no entry timestamp col in {list(df.columns)}"}
    df["_entry_dt"] = pd.to_datetime(df[ts_col]).dt.tz_localize(None)
    fut_from, fut_to = FUT_WINDOWS[sym]
    mask = (df["_entry_dt"] >= pd.to_datetime(fut_from)) & (df["_entry_dt"] <= pd.to_datetime(fut_to) + pd.Timedelta(days=1))
    sliced = df[mask].copy()
    full_metrics = compute_metrics(df)
    sliced_metrics = compute_metrics(sliced)
    # write sliced trades.csv to bt_out_<SYM>_C4b/
    out_dir = REPO / f"bt_out_{sym}_C4b"
    out_dir.mkdir(exist_ok=True)
    sliced.drop(columns=["_entry_dt"]).to_csv(out_dir / "trades.csv", index=False)
    return {
        "symbol": sym,
        "fut_window": [fut_from, fut_to],
        "full_index_137_150d": full_metrics,
        "sliced_to_fut_window": sliced_metrics,
        "out_dir": str(out_dir),
    }

result = {sym: slice_symbol(sym) for sym in FUT_WINDOWS}
out_path = REPO / "validation" / "c4b_basis_vs_regime.json"
out_path.parent.mkdir(exist_ok=True)
out_path.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
print(f"\nWritten to: {out_path}")
