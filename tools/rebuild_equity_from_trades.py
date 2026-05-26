"""Phase 9.8h.B.4 — canonical equity.jsonl + pfm.json rebuilder from trades.jsonl.

The bot's atexit-only equity flush is unreliable across mid-day restarts
(7 sessions on 2026-05-19, 2 on 2026-05-21). This tool derives equity.jsonl
and pfm.json from trades.jsonl, which is the canonical source of truth
post-B.3.

Usage:
    python tools/rebuild_equity_from_trades.py [--dry-run] [--no-backup]

Idempotent. Safe to run repeatedly. Backs up equity.jsonl before mutating
unless --no-backup is passed.
"""
import argparse, json, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EQ = ROOT / "state/primary/equity.jsonl"
TR = ROOT / "trades.jsonl"
PFM = ROOT / "state/pfm.json"


def rebuild(dry_run: bool = False, backup: bool = True) -> dict:
    if not TR.exists():
        raise FileNotFoundError(f"trades.jsonl not found at {TR}")
    if not EQ.exists():
        raise FileNotFoundError(f"equity.jsonl not found at {EQ}")

    trades = [json.loads(l) for l in TR.read_text().splitlines() if l.strip()]
    eq_rows = [json.loads(l) for l in EQ.read_text().splitlines() if l.strip()]

    trades_by_day = defaultdict(float)
    trade_count_by_day = defaultdict(int)
    for t in trades:
        day = (t.get("exit_ts") or t.get("entry_ts", ""))[:10]
        trades_by_day[day] += t.get("pnl", 0)
        trade_count_by_day[day] += 1

    edits = []
    for row in eq_rows:
        day = row["date"]
        expected = trades_by_day.get(day, 0)
        current = row.get("pnl", 0)
        if abs(expected - current) > 1.0 and abs(current) < 1.0:
            edits.append({"date": day, "was": current, "now": round(expected, 2)})
            row["pnl"] = round(expected, 2)
            row["backfilled"] = "phase-9.8h.B.4"
            row["backfill_reason"] = "orphaned by mid-day bot restarts; sourced from trades.jsonl"
            row["backfill_trade_count"] = trade_count_by_day[day]

    cum = 0.0
    for row in eq_rows:
        cum += row.get("pnl", 0)
        row["cumulative_pnl"] = round(cum, 2)

    final_cum = eq_rows[-1]["cumulative_pnl"] if eq_rows else 0.0
    result = {
        "edits": edits,
        "final_cumulative_pnl": final_cum,
        "trades_sum": round(sum(t.get("pnl", 0) for t in trades), 2),
        "equity_sum": round(sum(r.get("pnl", 0) for r in eq_rows), 2),
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    if backup:
        bak = EQ.with_suffix(".jsonl.pre-rebuild.bak")
        shutil.copy2(EQ, bak)
        result["backup"] = bak.name

    with open(EQ, "w") as f:
        for row in eq_rows:
            f.write(json.dumps(row) + "\n")

    pfm = json.loads(PFM.read_text())
    pfm["cumulative_pnl"] = final_cum
    pfm["snapshot_at"] = datetime.now(timezone.utc).isoformat()
    pfm["source"] = "rebuild_equity_from_trades.py"
    PFM.write_text(json.dumps(pfm, indent=2) + "\n")

    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="show edits without writing")
    ap.add_argument("--no-backup", action="store_true", help="skip equity.jsonl backup")
    args = ap.parse_args()

    res = rebuild(dry_run=args.dry_run, backup=not args.no_backup)
    print(json.dumps(res, indent=2))
    if res["edits"]:
        print(f"\n[ok] {'would patch' if args.dry_run else 'patched'} {len(res['edits'])} day(s)")
    else:
        print("\n[ok] no edits needed — equity.jsonl is in sync with trades.jsonl")
