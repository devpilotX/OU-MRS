"""Phase 8b: Monte Carlo bootstrap on realized trades.
Resamples trades with replacement 10,000 times to build CI and
prop-firm pass probabilities."""
import csv, json, subprocess, sys
from pathlib import Path
import numpy as np

OUT_DIR = Path("bt_out")
CAPITAL = 150_000
N_SIMS  = 10_000
RNG     = np.random.default_rng(42)

def find_trades():
    candidates = [
        OUT_DIR / "trades.jsonl",
        OUT_DIR / "trades.json",
        OUT_DIR / "trades.csv",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 0:
            return p
    p = Path("trades.jsonl")
    if p.exists() and p.stat().st_size > 0:
        print(f"WARNING: using live-bot file {p} (may mix paper + backtest)")
        return p
    return None

def parse_trades(path):
    pnls = []
    if path.suffix == ".csv":
        with open(path) as f:
            for row in csv.DictReader(f):
                val = row.get("pnl") or row.get("PnL") or row.get("total_pnl")
                if val is not None:
                    pnls.append(float(val))
    elif path.suffix == ".json":
        for t in json.loads(path.read_text()):
            pnls.append(float(t["pnl"]))
    elif path.suffix == ".jsonl":
        for line in open(path):
            line = line.strip()
            if line:
                pnls.append(float(json.loads(line)["pnl"]))
    return np.array(pnls, dtype=float)

def stats(samples):
    cum = np.cumsum(samples, axis=1)
    total = cum[:, -1]
    ret_pct = total / CAPITAL * 100
    m = samples.mean(axis=1)
    s = samples.std(axis=1, ddof=1)
    s[s == 0] = 1e-9
    trades_per_year = 0.76 * 252
    sharpe = (m / s) * np.sqrt(trades_per_year)
    running_max = np.maximum.accumulate(cum, axis=1)
    dd = cum - running_max
    max_dd_pct = dd.min(axis=1) / CAPITAL * 100
    return ret_pct, sharpe, max_dd_pct

def pct(arr, name):
    p = np.percentile(arr, [5, 25, 50, 75, 95])
    print(f"  {name:<12}  p5={p[0]:+7.2f}  p25={p[1]:+7.2f}  p50={p[2]:+7.2f}  p75={p[3]:+7.2f}  p95={p[4]:+7.2f}  mean={arr.mean():+.2f}  std={arr.std():.2f}")
    return {"p5": float(p[0]), "p25": float(p[1]), "p50": float(p[2]),
            "p75": float(p[3]), "p95": float(p[4]),
            "mean": float(arr.mean()), "std": float(arr.std())}

def main():
    print("Running fresh backtest to ensure trades are current...")
    subprocess.run([sys.executable, "backtest.py"], capture_output=True, check=False)

    path = find_trades()
    if path is None:
        print("\nERROR: No trades file found. Checked:")
        for p in [OUT_DIR/"trades.jsonl", OUT_DIR/"trades.json",
                  OUT_DIR/"trades.csv", Path("trades.jsonl")]:
            print(f"  - {p}: {'exists' if p.exists() else 'missing'}")
        print("\nNext: share the diagnostic output above and we'll patch backtest.py to export trades.")
        sys.exit(2)

    pnls = parse_trades(path)
    print(f"\nLoaded {len(pnls)} trades from {path}")
    print(f"  mean={pnls.mean():+.1f}  std={pnls.std():.1f}  "
          f"min={pnls.min():+.1f}  max={pnls.max():+.1f}  win_rate={(pnls>0).mean()*100:.1f}%")

    N = len(pnls)
    print(f"\nBootstrap: {N_SIMS:,} sims × {N} trades each (with replacement)")
    idx = RNG.integers(0, N, size=(N_SIMS, N))
    samples = pnls[idx]
    ret_pct, sharpe, max_dd_pct = stats(samples)

    print(f"\n=== MONTE CARLO 90% CI (N={N_SIMS:,}, horizon={N} trades ≈ 37d) ===")
    out = {
        "n_sims": N_SIMS, "n_trades": int(N),
        "input_trades": {
            "mean_pnl": float(pnls.mean()), "std_pnl": float(pnls.std()),
            "min_pnl":  float(pnls.min()),  "max_pnl": float(pnls.max()),
            "win_rate": float((pnls>0).mean()),
        },
        "return_pct": pct(ret_pct, "Return %"),
        "sharpe":     pct(sharpe,  "Sharpe"),
        "max_dd_pct": pct(max_dd_pct, "Max DD %"),
    }

    print(f"\n=== PROP-FIRM PASS PROBABILITIES (single evaluation window) ===")
    p_loss    = (ret_pct < 0).mean() * 100
    p_r5      = (ret_pct >= 5).mean() * 100
    p_r8      = (ret_pct >= 8).mean() * 100
    p_r10     = (ret_pct >= 10).mean() * 100
    p_dd3     = (max_dd_pct >= -3).mean() * 100
    p_dd5     = (max_dd_pct >= -5).mean() * 100
    p_dd8     = (max_dd_pct >= -8).mean() * 100
    p_dd10    = (max_dd_pct >= -10).mean() * 100
    p_ftmo1   = ((ret_pct >= 8)  & (max_dd_pct >= -5)).mean() * 100
    p_ftmo2p1 = ((ret_pct >= 10) & (max_dd_pct >= -5)).mean() * 100
    p_topstep = ((ret_pct >= 6)  & (max_dd_pct >= -3)).mean() * 100
    p_hola    = ((ret_pct >= 8)  & (max_dd_pct >= -6)).mean() * 100
    print(f"  P(losing month)              = {p_loss:>5.1f}%")
    print(f"  P(return ≥ +5%)              = {p_r5:>5.1f}%")
    print(f"  P(return ≥ +8%)              = {p_r8:>5.1f}%")
    print(f"  P(return ≥ +10%)             = {p_r10:>5.1f}%")
    print(f"  P(max DD ≤ 3%)               = {p_dd3:>5.1f}%")
    print(f"  P(max DD ≤ 5%)               = {p_dd5:>5.1f}%")
    print(f"  P(max DD ≤ 8%)               = {p_dd8:>5.1f}%")
    print(f"  P(max DD ≤ 10%)              = {p_dd10:>5.1f}%")
    print(f"  P(PASS FTMO 1-step: +8/-5%)  = {p_ftmo1:>5.1f}%")
    print(f"  P(PASS FTMO 2-step P1: +10/-5%) = {p_ftmo2p1:>5.1f}%")
    print(f"  P(PASS TopStep 50k: +6/-3%)  = {p_topstep:>5.1f}%")
    print(f"  P(PASS Hola Prime:  +8/-6%)  = {p_hola:>5.1f}%")

    out["prop_firm"] = {
        "prob_losing_month":   float(p_loss),
        "prob_return_ge_5":    float(p_r5),
        "prob_return_ge_8":    float(p_r8),
        "prob_return_ge_10":   float(p_r10),
        "prob_dd_safe_3":      float(p_dd3),
        "prob_dd_safe_5":      float(p_dd5),
        "prob_dd_safe_8":      float(p_dd8),
        "prob_dd_safe_10":     float(p_dd10),
        "prob_pass_ftmo_1st":  float(p_ftmo1),
        "prob_pass_ftmo_2p1":  float(p_ftmo2p1),
        "prob_pass_topstep":   float(p_topstep),
        "prob_pass_hola":      float(p_hola),
    }

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "monte_carlo.json").write_text(json.dumps(out, indent=2))
    print(f"\nSaved -> {OUT_DIR / 'monte_carlo.json'}")
if __name__ == "__main__":
    main()
