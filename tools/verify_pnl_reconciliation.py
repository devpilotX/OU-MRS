"""Phase 9.8h.B.4 — verify trades.jsonl / equity.jsonl / pfm.json are in sync.

Non-mutating. Exit code 0 = in sync, 1 = mismatch. Suitable for CI and cron.

Usage:
    python tools/verify_pnl_reconciliation.py [--quiet]
"""
import argparse, json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EQ = ROOT / "state/primary/equity.jsonl"
TR = ROOT / "trades.jsonl"
PFM = ROOT / "state/pfm.json"
TOLERANCE = 1.0  # rupees — absorbs float rounding from log-printed integer pnls


def verify() -> dict:
    trades = [json.loads(l) for l in TR.read_text().splitlines() if l.strip()] if TR.exists() else []
    eq_rows = [json.loads(l) for l in EQ.read_text().splitlines() if l.strip()] if EQ.exists() else []
    pfm = json.loads(PFM.read_text()) if PFM.exists() else {}

    trades_sum = round(sum(t.get("pnl", 0) for t in trades), 2)
    equity_sum = round(sum(r.get("pnl", 0) for r in eq_rows), 2)
    equity_last_cum = eq_rows[-1].get("cumulative_pnl", 0) if eq_rows else 0
    pfm_cum = pfm.get("cumulative_pnl", 0)

    daily_mismatches = []
    trades_by_day = defaultdict(float)
    for t in trades:
        day = (t.get("exit_ts") or t.get("entry_ts", ""))[:10]
        trades_by_day[day] += t.get("pnl", 0)
    for row in eq_rows:
        d = row["date"]
        exp = trades_by_day.get(d, 0)
        got = row.get("pnl", 0)
        if abs(exp - got) > TOLERANCE:
            daily_mismatches.append({"date": d, "trades": round(exp, 2), "equity": round(got, 2), "delta": round(exp - got, 2)})

    issues = []
    if abs(trades_sum - equity_sum) > TOLERANCE:
        issues.append(f"trades.jsonl sum (Rs {trades_sum:,.2f}) vs equity.jsonl sum (Rs {equity_sum:,.2f}) delta = Rs {trades_sum - equity_sum:,.2f}")
    if abs(equity_last_cum - pfm_cum) > TOLERANCE:
        issues.append(f"equity.jsonl last cum (Rs {equity_last_cum:,.2f}) vs pfm.cumulative_pnl (Rs {pfm_cum:,.2f}) delta = Rs {equity_last_cum - pfm_cum:,.2f}")
    if daily_mismatches:
        issues.append(f"{len(daily_mismatches)} day(s) where trades.jsonl daily sum != equity.jsonl daily pnl")

    return {
        "trades_sum": trades_sum,
        "equity_sum": equity_sum,
        "equity_last_cumulative": equity_last_cum,
        "pfm_cumulative": pfm_cum,
        "daily_mismatches": daily_mismatches,
        "issues": issues,
        "in_sync": not issues,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    res = verify()
    if not args.quiet:
        print(json.dumps(res, indent=2))
    if res["in_sync"]:
        if not args.quiet:
            print("\n[ok] all three P&L sources agree")
        sys.exit(0)
    else:
        if not args.quiet:
            print("\n[FAIL] P&L reconciliation issues detected:")
            for i in res["issues"]:
                print(f"  - {i}")
        sys.exit(1)
