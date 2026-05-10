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


# -----------------------------------------------------------------------------
# Phase B-0c: Bailey-Lopez de Prado PSR / DSR
# Reference: Bailey & Lopez de Prado (2012) "The Sharpe Ratio Efficient Frontier"
# Reference: Bailey & Lopez de Prado (2014) "The Deflated Sharpe Ratio"
# -----------------------------------------------------------------------------

_GAMMA_EM = 0.5772156649015329  # Euler-Mascheroni


def probabilistic_sharpe_ratio(
    returns: np.ndarray,
    sr_threshold_periodic: float = 0.0,
) -> dict:
    """Bailey-LdP PSR. P(true periodic SR > threshold | observed series).

    Uses skewness/kurtosis-corrected variance of the SR estimator.
    Caller annualizes the periodic SR for display.
    """
    from scipy.stats import norm
    r = np.asarray(returns, dtype=np.float64)
    T = int(len(r))
    if T < 4:
        raise ValueError(f"PSR needs T>=4, got {T}")
    mu = float(r.mean())
    sigma = float(r.std(ddof=1))
    if sigma <= 1e-12:
        return {"T": T, "sr_periodic": 0.0, "psr": float("nan"),
                "skewness": 0.0, "kurtosis_raw": 3.0,
                "note": "zero std"}
    sr = mu / sigma  # periodic SR
    centered = r - mu
    m3 = float((centered**3).mean())
    m4 = float((centered**4).mean())
    gamma3 = m3 / sigma**3
    gamma4_raw = m4 / sigma**4   # raw kurtosis: 3 for Gaussian
    var_sr = (1.0 - gamma3 * sr + ((gamma4_raw - 1.0) / 4.0) * sr**2) / (T - 1)
    if var_sr <= 0:
        return {"T": T, "sr_periodic": float(sr), "psr": float("nan"),
                "skewness": float(gamma3), "kurtosis_raw": float(gamma4_raw),
                "note": "non-positive var_sr (heavy negative skew + high SR)"}
    z = (sr - sr_threshold_periodic) / np.sqrt(var_sr)
    return {
        "T": T,
        "sr_periodic": float(sr),
        "sr_threshold_periodic": float(sr_threshold_periodic),
        "skewness": float(gamma3),
        "kurtosis_raw": float(gamma4_raw),
        "var_sr_periodic": float(var_sr),
        "z_stat": float(z),
        "psr": float(norm.cdf(z)),
    }


def expected_max_sr_periodic(n_trials: int, T: int) -> float:
    """E[max{SR_n}] under null SR=0, n_trials independent trials, T returns each."""
    from scipy.stats import norm
    if n_trials < 2 or T < 2:
        return 0.0
    var_null = 1.0 / (T - 1)
    z1 = float(norm.ppf(1.0 - 1.0 / n_trials))
    z2 = float(norm.ppf(1.0 - 1.0 / (n_trials * np.e)))
    return float(np.sqrt(var_null) * ((1.0 - _GAMMA_EM) * z1 + _GAMMA_EM * z2))


def deflated_sharpe_ratio(
    returns: np.ndarray,
    n_trials: int,
    ann_factor: int = 252,
) -> dict:
    """DSR = PSR with threshold set to E[max{SR_n}] under null. Selection-bias corrected."""
    T = int(len(returns))
    sr_max_per = expected_max_sr_periodic(n_trials, T)
    out = probabilistic_sharpe_ratio(returns, sr_threshold_periodic=sr_max_per)
    out["n_trials"] = int(n_trials)
    out["sr_max_periodic_under_null"] = float(sr_max_per)
    out["sr_max_annualized_under_null"] = float(sr_max_per * np.sqrt(ann_factor))
    out["sr_observed_annualized"] = float(out["sr_periodic"] * np.sqrt(ann_factor))
    out["dsr"] = out.pop("psr")
    out["ann_factor"] = int(ann_factor)
    return out


def compute_b0c_report(equity_csv: Path, trades_csv: Path) -> dict:
    """Apply PSR + DSR(N=10,20) to (a) equity daily, (b) trade-level full, (c) per-regime."""
    df_eq = pd.read_csv(equity_csv)
    ts_col = _detect_col(df_eq.columns, ["ts", "timestamp", "date", "datetime", "time"])
    eq_col = _detect_col(df_eq.columns, ["equity", "cum_pnl", "value", "balance"])
    df_eq[ts_col] = pd.to_datetime(df_eq[ts_col])
    daily_eq = df_eq.set_index(ts_col).sort_index()[eq_col].resample("1D").last().dropna()
    daily_ret = daily_eq.diff().dropna().to_numpy(dtype=np.float64)

    df_tr = pd.read_csv(trades_csv)
    pnl_col = _detect_col(df_tr.columns, ["pnl", "net_pnl", "realized_pnl"])
    reg_col = _detect_col(df_tr.columns, ["regime"])
    trade_pnl = df_tr[pnl_col].to_numpy(dtype=np.float64)

    out = {
        "equity_daily_T36": {
            "psr_at_threshold_0": probabilistic_sharpe_ratio(daily_ret, 0.0),
            "dsr_N10": deflated_sharpe_ratio(daily_ret, n_trials=10, ann_factor=252),
            "dsr_N20": deflated_sharpe_ratio(daily_ret, n_trials=20, ann_factor=252),
        },
        "trade_full_T24": {
            "psr_at_threshold_0": probabilistic_sharpe_ratio(trade_pnl, 0.0),
            "dsr_N10": deflated_sharpe_ratio(trade_pnl, n_trials=10, ann_factor=1),
            "dsr_N20": deflated_sharpe_ratio(trade_pnl, n_trials=20, ann_factor=1),
        },
        "trade_per_regime": {},
    }
    if reg_col is not None:
        for regime, sub in df_tr.groupby(reg_col):
            n = len(sub)
            if n < 4:
                out["trade_per_regime"][str(regime)] = {
                    "n_trades": int(n), "note": "n<4, PSR not applicable",
                }
                continue
            r = sub[pnl_col].to_numpy(dtype=np.float64)
            out["trade_per_regime"][str(regime)] = {
                "n_trades": int(n),
                "psr_at_threshold_0": probabilistic_sharpe_ratio(r, 0.0),
                "dsr_N10": deflated_sharpe_ratio(r, n_trials=10, ann_factor=1),
            }
    return out


# -----------------------------------------------------------------------------
# Phase B-0e: IID validation diagnostics
# Ljung-Box autocorrelation test + Augmented Dickey-Fuller stationarity
# -----------------------------------------------------------------------------

def ljung_box_test(returns, lags: int = 10) -> dict:
    """Ljung-Box Q test for autocorrelation. H0: IID. p<0.05 -> autocorrelated."""
    from statsmodels.stats.diagnostic import acorr_ljungbox
    r = np.asarray(returns, dtype=np.float64)
    r = r[~np.isnan(r)]
    if len(r) < lags + 5:
        return {"T": int(len(r)), "lags": int(lags), "Q": float("nan"),
                "p_value": float("nan"), "verdict": "insufficient_sample"}
    res = acorr_ljungbox(r, lags=[lags], return_df=True)
    Q = float(res["lb_stat"].iloc[0])
    p = float(res["lb_pvalue"].iloc[0])
    verdict = "IID_rejected_autocorrelated" if p < 0.05 else "IID_cannot_reject"
    return {"T": int(len(r)), "lags": int(lags), "Q": Q, "p_value": p, "verdict": verdict}


def adf_test(returns) -> dict:
    """Augmented Dickey-Fuller. H0: unit root. p<0.05 -> stationary."""
    from statsmodels.tsa.stattools import adfuller
    r = np.asarray(returns, dtype=np.float64)
    r = r[~np.isnan(r)]
    if len(r) < 10:
        return {"T": int(len(r)), "stat": float("nan"), "p_value": float("nan"),
                "verdict": "insufficient_sample"}
    stat, pval, _, _, crit, _ = adfuller(r, autolag="AIC")
    verdict = "stationary" if pval < 0.05 else "non_stationary_cannot_reject_unit_root"
    return {"T": int(len(r)), "stat": float(stat), "p_value": float(pval),
            "crit_5pct": float(crit["5%"]), "verdict": verdict}


def compute_b0e_report(equity_csv: str = "bt_out/equity.csv",
                       trades_csv: str = "bt_out/trades.csv") -> dict:
    """Run Ljung-Box + ADF on equity daily returns and trade pnl series."""
    import pandas as pd
    eq = pd.read_csv(equity_csv)
    tr = pd.read_csv(trades_csv)
    eq_col = _detect_col(eq, ["pnl_day", "ret", "return", "daily_return"])
    eq_r = eq[eq_col].values if eq_col else eq.iloc[:, 1].values
    return {
        "equity_daily": {
            "T": int(len(eq_r)),
            "ljung_box_lag5": ljung_box_test(eq_r, lags=5),
            "ljung_box_lag10": ljung_box_test(eq_r, lags=10),
            "adf": adf_test(eq_r),
        },
        "trade_pnl": {
            "T": int(len(tr)),
            "ljung_box_lag5": ljung_box_test(tr["pnl"].values, lags=5),
            "ljung_box_lag10": ljung_box_test(tr["pnl"].values, lags=10),
            "adf": adf_test(tr["pnl"].values),
        },
    }


# -----------------------------------------------------------------------------
# Phase B-0f: walk-forward rolling-window Sharpe stability
# Tests whether the headline Sharpe is concentrated in a few lucky periods
# or distributed consistently across the sample.
# -----------------------------------------------------------------------------

def walk_forward_sharpe(returns, window: int, step: int = 1, ann_factor: float = 1.0) -> list:
    """Rolling-window Sharpe over a returns series.
    Returns list of dicts: {start, end, n, mean, std, sharpe, sharpe_ann, total}.
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[~np.isnan(r)]
    out = []
    if len(r) < window:
        return out
    for s in range(0, len(r) - window + 1, step):
        w = r[s:s + window]
        mu = float(w.mean())
        sd = float(w.std(ddof=1)) if len(w) > 1 else 0.0
        sr = (mu / sd) if sd > 0 else float("nan")
        sr_ann = sr * np.sqrt(ann_factor) if not np.isnan(sr) else float("nan")
        out.append({
            "start": int(s), "end": int(s + window - 1), "n": int(window),
            "mean": mu, "std": sd,
            "sharpe": float(sr), "sharpe_ann": float(sr_ann),
            "total": float(w.sum()),
        })
    return out


def walk_forward_summary(windows: list) -> dict:
    """Aggregate stability stats over walk-forward windows."""
    if not windows:
        return {"n_windows": 0, "consistency_rate": float("nan"),
                "sharpe_mean": float("nan"), "sharpe_std": float("nan"),
                "sharpe_min": float("nan"), "sharpe_max": float("nan"),
                "stability": float("nan")}
    sharpes = np.array([w["sharpe"] for w in windows], dtype=np.float64)
    sharpes = sharpes[~np.isnan(sharpes)]
    if len(sharpes) == 0:
        return {"n_windows": len(windows), "consistency_rate": float("nan"),
                "sharpe_mean": float("nan"), "sharpe_std": float("nan"),
                "sharpe_min": float("nan"), "sharpe_max": float("nan"),
                "stability": float("nan")}
    mu = float(sharpes.mean())
    sd = float(sharpes.std(ddof=1)) if len(sharpes) > 1 else 0.0
    consistency = float(np.mean(sharpes > 0))
    stability = float(sd / abs(mu)) if mu != 0 else float("inf")  # CV of Sharpe; lower = more stable
    return {
        "n_windows": int(len(windows)),
        "consistency_rate": consistency,         # fraction of windows with Sharpe > 0
        "sharpe_mean": mu,
        "sharpe_std": sd,
        "sharpe_min": float(sharpes.min()),
        "sharpe_max": float(sharpes.max()),
        "stability": stability,                  # coefficient of variation of Sharpe
    }


def compute_b0f_report(equity_csv: str = "bt_out/equity.csv",
                       trades_csv: str = "bt_out/trades.csv") -> dict:
    """Walk-forward Sharpe on equity daily returns (window=20) and trade pnl (window=15)."""
    import pandas as pd
    eq = pd.read_csv(equity_csv)
    tr = pd.read_csv(trades_csv)
    eq_col = _detect_col(eq, ["pnl_day", "ret", "return", "daily_return"])
    eq_r = eq[eq_col].values if eq_col else eq.iloc[:, 1].values
    eq_windows = walk_forward_sharpe(eq_r, window=20, step=1, ann_factor=252.0)
    tr_windows = walk_forward_sharpe(tr["pnl"].values, window=15, step=1, ann_factor=1.0)
    return {
        "equity_daily_w20": {
            "summary": walk_forward_summary(eq_windows),
            "windows": eq_windows,
        },
        "trade_pnl_w15": {
            "summary": walk_forward_summary(tr_windows),
            "windows": tr_windows,
        },
    }
