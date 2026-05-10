"""
Politis-Romano stationary block bootstrap for trade-level + daily-equity stats.
Deterministic given a seed. No live-path imports. Pandas/numpy only.

Functions:
  - bootstrap_trade_stats(pnl, ...): per-trade pnl CI
  - bootstrap_daily_sharpe(equity_csv, ...): equity-series daily Sharpe CI
  - bootstrap_per_regime(trades_csv, ...): split CI by regime column
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional


def _stationary_resample_indices(n: int, mean_block_len: float, rng) -> np.ndarray:
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
        "ci95_total_pnl": [float(np.quantile(means * n, 0.025)),
                            float(np.quantile(means * n, 0.975))],
        "ci95_mean_pnl": [float(np.quantile(means, 0.025)),
                           float(np.quantile(means, 0.975))],
        "ci95_info_ratio": [float(np.quantile(info_ratios, 0.025)),
                             float(np.quantile(info_ratios, 0.975))],
        "ci95_win_rate": [float(np.quantile(win_rates, 0.025)),
                           float(np.quantile(win_rates, 0.975))],
        "p_value_one_sided": float((means <= 0).mean()),
    }


def _detect_col(cols, candidates):
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for c in cols:
        for cand in candidates:
            if cand in c.lower():
                return c
    return None


def bootstrap_daily_sharpe(
    equity_csv: Path,
    n_iter: int = 10000,
    mean_block_len: float = 5.0,
    seed: int = 42,
    ann_factor: int = 252,
) -> dict:
    df = pd.read_csv(equity_csv)
    ts_col = _detect_col(df.columns, ["ts", "timestamp", "date", "datetime", "time"])
    eq_col = _detect_col(df.columns, ["equity", "cum_pnl", "value", "balance"])
    if ts_col is None or eq_col is None:
        raise KeyError(f"equity.csv schema unrecognized; cols={list(df.columns)}")
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df.set_index(ts_col).sort_index()
    daily_eq = df[eq_col].resample("1D").last().dropna()
    daily_ret = daily_eq.diff().dropna().to_numpy(dtype=np.float64)
    n = len(daily_ret)
    if n < 2:
        raise ValueError(f"need >=2 daily returns, got {n}")
    rng = np.random.default_rng(seed)
    sharpes = np.empty(n_iter)
    means = np.empty(n_iter)
    for i in range(n_iter):
        idx = _stationary_resample_indices(n, mean_block_len, rng)
        sample = daily_ret[idx]
        m = sample.mean()
        s = sample.std(ddof=1)
        means[i] = m
        sharpes[i] = (m / s) * np.sqrt(ann_factor) if s > 1e-9 else 0.0
    point_m = daily_ret.mean()
    point_s = daily_ret.std(ddof=1)
    point_sharpe = (point_m / point_s) * np.sqrt(ann_factor) if point_s > 1e-9 else 0.0
    return {
        "source": "equity.csv daily mark-to-market",
        "ts_col": ts_col,
        "eq_col": eq_col,
        "n_days": n,
        "n_iter": n_iter,
        "mean_block_len": mean_block_len,
        "seed": seed,
        "ann_factor": ann_factor,
        "point_daily_mean_pnl": float(point_m),
        "point_daily_std_pnl": float(point_s),
        "point_annualized_sharpe": float(point_sharpe),
        "ci95_annualized_sharpe": [float(np.quantile(sharpes, 0.025)),
                                    float(np.quantile(sharpes, 0.975))],
        "p_value_one_sided": float((means <= 0).mean()),
    }


def bootstrap_per_regime(
    trades_csv: Path,
    n_iter: int = 10000,
    mean_block_len: float = 5.0,
    seed: int = 42,
) -> dict:
    df = pd.read_csv(trades_csv)
    pnl_col = _detect_col(df.columns, ["pnl", "net_pnl", "realized_pnl"])
    reg_col = _detect_col(df.columns, ["regime", "regime_label", "regime_at_entry"])
    if pnl_col is None:
        raise KeyError(f"no pnl column in {trades_csv}; cols={list(df.columns)}")
    out = {"pnl_col": pnl_col, "regime_col": reg_col, "by_regime": {}}
    if reg_col is None:
        out["note"] = "no regime column; per-regime split unavailable"
        return out
    for regime, sub in df.groupby(reg_col):
        if len(sub) < 2:
            out["by_regime"][str(regime)] = {"n_trades": int(len(sub)),
                                              "note": "n<2, bootstrap skipped"}
            continue
        out["by_regime"][str(regime)] = bootstrap_trade_stats(
            sub[pnl_col].to_numpy(dtype=np.float64),
            n_iter=n_iter, mean_block_len=mean_block_len, seed=seed,
        )
    return out


def load_trades_pnl(trades_csv: Path) -> np.ndarray:
    df = pd.read_csv(trades_csv)
    pnl_col = _detect_col(df.columns, ["pnl", "net_pnl", "realized_pnl"])
    if pnl_col is None:
        raise KeyError(f"no pnl column in {trades_csv}; cols={list(df.columns)}")
    return df[pnl_col].to_numpy(dtype=np.float64)


def main():
    import json
    here = Path(__file__).resolve().parent.parent
    trades = here / "bt_out" / "trades.csv"
    equity = here / "bt_out" / "equity.csv"
    artifact = here / "validation" / "baseline_post_b1.json"
    pnl = load_trades_pnl(trades)
    out = {
        "schema_version": "0.0.2",
        "git_commit": "post-7d589a3 (B-0b)",
        "trade_level": bootstrap_trade_stats(pnl),
        "equity_level": bootstrap_daily_sharpe(equity),
        "per_regime": bootstrap_per_regime(trades),
    }
    print(json.dumps(out, indent=2))
    artifact.write_text(json.dumps(out, indent=2))
    print(f"\n[B-0b] wrote durable artifact -> {artifact}")


if __name__ == "__main__":
    main()
