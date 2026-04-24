"""Phase 8b.5: Position sizing sensitivity sweep.
Rescales realized trades by multipliers and bootstraps each scale
to find the size factor with max prop-firm pass probability."""
import csv, json, sys
from pathlib import Path
import numpy as np

OUT_DIR        = Path("bt_out")
CAPITAL        = 150_000
N_SIMS         = 10_000
FTMO_DAYS      = 30
TRADES_PER_DAY = 0.76
SIMS_TRADES    = int(round(FTMO_DAYS * TRADES_PER_DAY))  # ~23
RNG            = np.random.default_rng(42)

def load_pnls():
    pnls = []
    with open(OUT_DIR / "trades.csv") as f:
        for row in csv.DictReader(f):
            pnls.append(float(row["pnl"]))
    return np.array(pnls, dtype=float)

def eval_scale(pnls, scale, n_trades, n_sims, rng):
    scaled = pnls * scale
    idx = rng.integers(0, len(scaled), size=(n_sims, n_trades))
    samples = scaled[idx]
    cum = np.cumsum(samples, axis=1)
    total = cum[:, -1]
    ret = total / CAPITAL * 100
    running_max = np.maximum.accumulate(cum, axis=1)
    dd = (cum - running_max).min(axis=1) / CAPITAL * 100
    m = samples.mean(axis=1)
    s = samples.std(axis=1, ddof=1)
    s[s == 0] = 1e-9
    sharpe = (m / s) * np.sqrt(TRADES_PER_DAY * 252)
    return {
        "scale": float(scale), "n_trades": int(n_trades),
        "return_p5":   float(np.percentile(ret, 5)),
        "return_p50":  float(np.percentile(ret, 50)),
        "return_p95":  float(np.percentile(ret, 95)),
        "return_mean": float(ret.mean()),
        "dd_p5":       float(np.percentile(dd, 5)),
        "dd_p50":      float(np.percentile(dd, 50)),
        "dd_p95":      float(np.percentile(dd, 95)),
        "dd_mean":     float(dd.mean()),
        "sharpe_p50":  float(np.percentile(sharpe, 50)),
        "p_ftmo_1":     float(((ret >= 8)  & (dd >= -5)).mean() * 100),
        "p_ftmo_2p1":   float(((ret >= 10) & (dd >= -5)).mean() * 100),
        "p_topstep":    float(((ret >= 6)  & (dd >= -3)).mean() * 100),
        "p_hola":       float(((ret >= 8)  & (dd >= -6)).mean() * 100),
        "p_losing":     float((ret < 0).mean() * 100),
    }

def main():
    pnls = load_pnls()
    print(f"Loaded {len(pnls)} trades  mean_pnl=Rs{pnls.mean():+.0f}  std=Rs{pnls.std():.0f}")
    print(f"Simulating FTMO challenge window: {FTMO_DAYS} days ≈ {SIMS_TRADES} trades/sim")
    print(f"Each scale bootstrapped {N_SIMS:,} times\n")

    scales = [0.25, 0.35, 0.50, 0.65, 0.75, 1.00, 1.25, 1.50, 2.00]
    results = []
    hdr = (f"{'Size':>5}  {'RetMed':>8} {'RetP5':>8} {'RetP95':>8}   "
           f"{'DDmed':>7} {'DDp5':>7}   {'Shp50':>6}   "
           f"{'FTMO1':>6} {'FTMO2P1':>7} {'TopS':>6} {'Hola':>6}   {'Loss':>5}")
    print(hdr)
    print("-" * len(hdr))
    for s in scales:
        r = eval_scale(pnls, s, SIMS_TRADES, N_SIMS, RNG)
        results.append(r)
        print(f"{s:>4.2f}x  "
              f"{r['return_p50']:>+7.2f}% {r['return_p5']:>+7.2f}% {r['return_p95']:>+7.2f}%   "
              f"{r['dd_p50']:>+6.2f}% {r['dd_p5']:>+6.2f}%   "
              f"{r['sharpe_p50']:>+5.2f}   "
              f"{r['p_ftmo_1']:>5.1f}% {r['p_ftmo_2p1']:>6.1f}% {r['p_topstep']:>5.1f}% {r['p_hola']:>5.1f}%   "
              f"{r['p_losing']:>4.1f}%")

    print(f"\n=== OPTIMAL SCALE BY FIRM ===")
    best_ftmo1   = max(results, key=lambda r: r['p_ftmo_1'])
    best_ftmo2p1 = max(results, key=lambda r: r['p_ftmo_2p1'])
    best_topstep = max(results, key=lambda r: r['p_topstep'])
    best_hola    = max(results, key=lambda r: r['p_hola'])
    print(f"  FTMO 1-step    (+8/-5%):  best at {best_ftmo1['scale']:.2f}x  → P={best_ftmo1['p_ftmo_1']:.1f}%")
    print(f"  FTMO 2-step P1 (+10/-5%): best at {best_ftmo2p1['scale']:.2f}x  → P={best_ftmo2p1['p_ftmo_2p1']:.1f}%")
    print(f"  TopStep 50k    (+6/-3%):  best at {best_topstep['scale']:.2f}x  → P={best_topstep['p_topstep']:.1f}%")
    print(f"  Hola Prime     (+8/-6%):  best at {best_hola['scale']:.2f}x  → P={best_hola['p_hola']:.1f}%")

    # Practical recommendation: max of avg pass prob across all 4 firms
    for r in results:
        r["avg_pass_prob"] = (r["p_ftmo_1"] + r["p_ftmo_2p1"] + r["p_topstep"] + r["p_hola"]) / 4
    best_avg = max(results, key=lambda r: r['avg_pass_prob'])
    print(f"\n=== OVERALL RECOMMENDATION ===")
    print(f"  Best average pass-prob across all 4 firms: {best_avg['scale']:.2f}x (avg P={best_avg['avg_pass_prob']:.1f}%)")
    print(f"  Current production size: 1.00x  →  change to {best_avg['scale']:.2f}x")

    # How to apply it (informational only — does NOT patch code)
    print(f"\n=== TO APPLY (do NOT run yet — wait for confirmation) ===")
    if best_avg['scale'] < 1.0:
        print(f"  In ou_mrs.py: change  budget = 0.25 * 0.10 * CAPITAL  ->  budget = 0.25 * {0.10 * best_avg['scale']:.3f} * CAPITAL")
        print(f"  In backtest.py: same edit wherever sizing is calculated")
        print(f"  Then re-run backtest + MC + walk-forward to confirm lift is real.")
    else:
        print(f"  Current size is already near-optimal.")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "size_sensitivity.json").write_text(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUT_DIR / 'size_sensitivity.json'}")

if __name__ == "__main__":
    main()
