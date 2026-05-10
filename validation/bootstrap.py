"""
Politis-Romano stationary block bootstrap for trade-level statistics.
Deterministic given a seed. No live-path imports. Pandas/numpy only.

Reproduces:
  - 95% CI on total pnl, mean pnl/trade, win rate
  - 95% CI on trade-level info ratio (mean/std * sqrt(N))
  - One-sided p-value: P(resample_mean <= 0)

Tier B-0b will extend to time-series Sharpe via equity.csv.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple


def _stationary_resample_indices(n: int, mean_block_len: float, rng) -> np.ndarray:
    """Generate one length-n stationary-bootstrap index array."""
    p = 1.0 / mean_block_len
    idx = np.empty(n, dtype=np.int64)
    j = 0
    while j < n:
        start = int(rng.integers(0, n))
        block_len = max(1, int(rng.geometric(p)))
        for k in range(block_len):
            if j >= n:
                break
            idx[j] = (start + k) % n
            j += 1
    return idx


def bootstrap_trade_stats(
    pnl: np.ndarray,
    n_iter: int = 10000,
    mean_block_len: float = 5.0,
    seed: int = 42,
) -> dict:
    """Stationary block bootstrap on a per-trade pnl array."""
    pnl = np.asarray(pnl, dtype=np.float64)
    n = len(pnl)
    if n < 2:
        raise ValueError(f"need >=2 trades, got {n}")
    rng = np.random.default_rng(seed)
    means = np.empty(n_iter)
    info_ratios = np.empty(n_iter)
    win_rates = np.empty(n_iter)
    for i in range(n_iter):
        idx = _stationary_resample_indices(n, mean_block_len, rng)
        sample = pnl[idx]
        m = sample.mean()
        s = sample.std(ddof=1)
        means[i] = m
        info_ratios[i] = (m / s) * np.sqrt(n) if s > 1e-9 else 0.0
        win_rates[i] = (sample > 0).mean()
    point_mean = pnl.mean()
    point_std = pnl.std(ddof=1)
    point_ir = (point_mean / point_std) * np.sqrt(n) if point_std > 1e-9 else 0.0
    return {
        "n_trades": n,
        "n_iter": n_iter,
        "mean_block_len": mean_block_len,
        "seed": seed,
        "point_total_pnl": float(pnl.sum()),
        "point_mean_pnl": float(point_mean),
        "point_info_ratio": float(point_ir),
        "point_win_rate": float((pnl > 0).mean()),
        "ci95_total_pnl": (float(np.quantile(means * n, 0.025)),
                           float(np.quantile(means * n, 0.975))),
        "ci95_mean_pnl": (float(np.quantile(means, 0.025)),
                          float(np.quantile(means, 0.975))),
        "ci95_info_ratio": (float(np.quantile(info_ratios, 0.025)),
                            float(np.quantile(info_ratios, 0.975))),
        "ci95_win_rate": (float(np.quantile(win_rates, 0.025)),
                          float(np.quantile(win_rates, 0.975))),
        "p_value_one_sided": float((means <= 0).mean()),
    }


def load_trades_pnl(trades_csv: Path) -> np.ndarray:
    """Load per-trade pnl from a backtest trades.csv."""
    df = pd.read_csv(trades_csv)
    for col in ("pnl", "net_pnl", "realized_pnl"):
        if col in df.columns:
            return df[col].to_numpy(dtype=np.float64)
    raise KeyError(f"no pnl column in {trades_csv}; cols={list(df.columns)}")


def main():
    import json, sys
    here = Path(__file__).resolve().parent.parent
    trades = here / "bt_out" / "trades.csv"
    pnl = load_trades_pnl(trades)
    out = bootstrap_trade_stats(pnl)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
