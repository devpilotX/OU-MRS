"""Phase 8a: Walk-forward analysis on existing 37 days.
Splits data into 4 sequential folds, runs backtest on each,
and reports per-fold metrics. Stable Sharpe across folds = robust edge."""
import json, shutil, subprocess, sys
from pathlib import Path
import pandas as pd

DATA    = Path("data/BANKNIFTY_FUT_1min.parquet")
BACKUP  = Path("data/BANKNIFTY_FUT_1min.parquet.wf_backup")
METRICS = Path("bt_out/metrics.json")
OUT     = Path("bt_out/walk_forward.json")

def run_fold(start, end, name):
    df = pd.read_parquet(BACKUP)
    sub = df[(df.index >= start) & (df.index < end)]
    if len(sub) < 500:
        return {"fold": name, "error": f"insufficient bars: {len(sub)}"}
    sub.to_parquet(DATA)
    r = subprocess.run([sys.executable, "backtest.py"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"fold": name, "error": r.stderr[-500:]}
    m = json.loads(METRICS.read_text())
    m["fold"]  = name
    m["start"] = start
    m["end"]   = end
    m["bars"]  = len(sub)
    return m

def main():
    if not DATA.exists():
        print("ERROR: data file missing"); sys.exit(1)
    shutil.copy(DATA, BACKUP)
    print(f"Backed up original data -> {BACKUP.name}")
    try:
        folds = [
            ("2026-03-01", "2026-03-15", "Fold1_EarlyMar"),
            ("2026-03-15", "2026-03-29", "Fold2_LateMar"),
            ("2026-03-29", "2026-04-12", "Fold3_EarlyApr"),
            ("2026-04-12", "2026-04-25", "Fold4_LateApr"),
        ]
        results = []
        for s, e, n in folds:
            print(f"\n--- Running {n} [{s} -> {e}] ---")
            r = run_fold(s, e, n)
            results.append(r)
            if "error" in r:
                print(f"  FAILED: {r['error']}")
            else:
                print(f"  trades={r['trades']:>2}  sharpe={r['sharpe']:>5.2f}  "
                      f"return={r['return_pct']:>+6.2f}%  max_dd={r['max_drawdown_pct']:>+6.2f}%")
        OUT.write_text(json.dumps(results, indent=2))
        print(f"\nSaved -> {OUT}")
        valid = [r for r in results if "error" not in r]
        if len(valid) >= 2:
            sharpes = [r["sharpe"] for r in valid]
            returns = [r["return_pct"] for r in valid]
            dds     = [r["max_drawdown_pct"] for r in valid]
            print(f"\n=== AGGREGATE ({len(valid)}/{len(folds)} folds ran) ===")
            print(f"  Sharpe  min={min(sharpes):+.2f}  max={max(sharpes):+.2f}  "
                  f"mean={sum(sharpes)/len(sharpes):+.2f}")
            print(f"  Return  min={min(returns):+.2f}%  max={max(returns):+.2f}%  "
                  f"mean={sum(returns)/len(returns):+.2f}%")
            print(f"  MaxDD   worst={min(dds):+.2f}%  best={max(dds):+.2f}%")
            positive_folds = sum(1 for r in returns if r > 0)
            print(f"  Positive folds: {positive_folds}/{len(valid)}")
            if positive_folds == len(valid) and min(sharpes) > 1.0:
                print("  VERDICT: ROBUST — every fold profitable, min Sharpe > 1.0")
            elif positive_folds >= len(valid) * 0.75:
                print("  VERDICT: ACCEPTABLE — majority profitable")
            else:
                print("  VERDICT: FRAGILE — edge may be period-specific")
    finally:
        shutil.copy(BACKUP, DATA)
        BACKUP.unlink()
        subprocess.run([sys.executable, "backtest.py"], capture_output=True)
        print(f"\nRestored original data + re-ran full backtest for fresh bt_out/")

if __name__ == "__main__":
    main()
