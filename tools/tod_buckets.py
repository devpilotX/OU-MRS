"""Time-of-day P&L distribution for OU-MRS.

Phase 9.8g.9 / Track 2 (25 May 2026): buckets per-trade P&L by entry
hour to surface intraday edge concentration. Mean-reversion edge in
Indian index futures is concentrated in the post-open / mid-morning
window; the close auction is dominated by trend continuation. This
tool quantifies that.

Usage:
    python tools/tod_buckets.py --input bt_out_BANKNIFTY/trades.csv
    python tools/tod_buckets.py --input trades.jsonl --out validation/tod_BNF.json

Bucket definitions (Indian markets, IST):
    open_auction   09:15 - 09:30
    mid_morning    09:30 - 11:30
    midday         11:30 - 13:30
    afternoon      13:30 - 14:45
    close_auction  14:45 - 15:15
"""
import argparse
import json
import math
from pathlib import Path

import pandas as pd

BUCKETS = [
    ("open_auction",  "09:15", "09:30"),
    ("mid_morning",   "09:30", "11:30"),
    ("midday",        "11:30", "13:30"),
    ("afternoon",     "13:30", "14:45"),
    ("close_auction", "14:45", "15:15"),
]


def _bucket_of(ts):
    s = ts.strftime("%H:%M")
    for name, lo, hi in BUCKETS:
        if lo <= s < hi:
            return name
    return "other"


def _load(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{p} not found")
    if p.suffix == ".csv":
        return pd.read_csv(p)
    if p.suffix in (".jsonl", ".json"):
        return pd.read_json(p, lines=True)
    raise SystemExit(f"unknown input suffix: {p.suffix}")


def main():
    p = argparse.ArgumentParser(
        description="Per-trade P&L bucketed by entry hour for OU-MRS"
    )
    p.add_argument("--input", required=True, help="trades.csv or trades.jsonl path")
    p.add_argument("--out", default=None, help="Optional JSON output path")
    args = p.parse_args()

    df = _load(args.input)
    if "entry_ts" not in df.columns:
        raise SystemExit(f"{args.input}: missing 'entry_ts' column")
    if "pnl" not in df.columns:
        raise SystemExit(f"{args.input}: missing 'pnl' column")
    df["entry_ts"] = pd.to_datetime(df["entry_ts"])
    df["bucket"] = df["entry_ts"].apply(_bucket_of)

    rows = []
    for name, _, _ in BUCKETS + [("other", "", "")]:
        sub = df[df["bucket"] == name]
        if sub.empty:
            rows.append({"bucket": name, "n_trades": 0})
            continue
        pnl = sub["pnl"].astype(float)
        wins = int((pnl > 0).sum())
        losses = int((pnl < 0).sum())
        wr = wins / (wins + losses) if (wins + losses) else 0.0
        mean = float(pnl.mean())
        std = float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0
        sharpe = (mean / std * math.sqrt(len(pnl))) if std > 0 else 0.0
        rows.append({
            "bucket":      name,
            "n_trades":    int(len(sub)),
            "wins":        wins,
            "losses":      losses,
            "win_rate":    float(wr),
            "total_pnl":   float(pnl.sum()),
            "mean_pnl":    mean,
            "std_pnl":     std,
            "trade_sharpe": float(sharpe),
        })

    print(f"\nTime-of-day P&L distribution ({len(df)} trades from {args.input}):\n")
    print(f"{'bucket':<16}{'n':>5}{'WR':>8}{'total':>11}{'mean':>10}{'std':>10}{'tSR':>8}")
    print("-" * 68)
    for r in rows:
        if r["n_trades"] == 0:
            print(f"{r['bucket']:<16}{r['n_trades']:>5}{'-':>8}{'-':>11}{'-':>10}{'-':>10}{'-':>8}")
        else:
            print(
                f"{r['bucket']:<16}"
                f"{r['n_trades']:>5}"
                f"{r['win_rate']:>7.1%}"
                f"{r['total_pnl']:>11.0f}"
                f"{r['mean_pnl']:>10.0f}"
                f"{r['std_pnl']:>10.0f}"
                f"{r['trade_sharpe']:>8.2f}"
            )

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as f:
            json.dump({"input": str(args.input), "buckets": rows}, f, indent=2)
        print(f"\nWrote {args.out}")
    print()


if __name__ == "__main__":
    main()
