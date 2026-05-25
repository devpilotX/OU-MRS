"""Cross-symbol portfolio metrics for OU-MRS.

Phase 9.8g.9 / Track 2 (25 May 2026): combines per-symbol P&L into a
correlation-adjusted portfolio Sharpe, with risk-parity weights and
optional Deflated Sharpe Ratio (n_trials = N symbols) when
validation/bootstrap.py is on PYTHONPATH.

Inputs:  per-symbol bt_out_<SYM>/trades.csv directories.
Outputs: validation/portfolio_metrics.json + console table.

Usage:
    python tools/portfolio_metrics.py --inputs bt_out_BANKNIFTY bt_out_NIFTY bt_out_MIDCPNIFTY
    python tools/portfolio_metrics.py --inputs bt_out_BANKNIFTY:BNF bt_out_NIFTY:NF
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from validation.bootstrap import (
        probabilistic_sharpe_ratio,
        deflated_sharpe_ratio,
    )
except Exception:
    probabilistic_sharpe_ratio = None
    deflated_sharpe_ratio = None


def _load_daily_pnl(bt_dir, symbol):
    """Load daily summed P&L from bt_out_<SYM>/trades.csv as a named Series."""
    p = Path(bt_dir) / "trades.csv"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found (run backtest.py --symbol first)")
    df = pd.read_csv(p)
    if "pnl" not in df.columns:
        raise ValueError(f"{p}: missing 'pnl' column")
    ts_col = "entry_ts" if "entry_ts" in df.columns else "exit_ts"
    df[ts_col] = pd.to_datetime(df[ts_col])
    df["date"] = df[ts_col].dt.date
    return df.groupby("date")["pnl"].sum().rename(symbol)


def _portfolio_sharpe(returns_df, weights=None):
    if weights is None:
        weights = np.ones(returns_df.shape[1]) / returns_df.shape[1]
    weights = np.asarray(weights, dtype=float)
    port = (returns_df * weights).sum(axis=1)
    mean = float(port.mean())
    std = float(port.std(ddof=1))
    if std <= 0:
        return 0.0, port
    return mean / std * math.sqrt(252), port


def _risk_parity_weights(returns_df):
    vols = returns_df.std(ddof=1)
    inv_vol = 1.0 / vols.replace(0, np.nan)
    w = inv_vol / inv_vol.sum()
    return w.fillna(0).values


def main():
    p = argparse.ArgumentParser(
        description="Cross-symbol portfolio Sharpe + correlation matrix for OU-MRS"
    )
    p.add_argument(
        "--inputs", nargs="+", required=True,
        help="Space-separated bt_out_<SYM> dirs. Optional :symbol suffix to override the label.",
    )
    p.add_argument("--out", default="validation/portfolio_metrics.json")
    args = p.parse_args()

    series = []
    for inp in args.inputs:
        if ":" in inp:
            bt_dir, sym = inp.split(":", 1)
        else:
            bt_dir = inp
            sym = Path(bt_dir).name.replace("bt_out_", "")
        series.append(_load_daily_pnl(bt_dir, sym))
    df = pd.concat(series, axis=1).fillna(0.0).sort_index()

    print(f"\nLoaded {len(df)} trading days across {df.shape[1]} symbols.")
    if not df.empty:
        print(df.tail(10))

    corr = df.corr().round(4)
    print("\nCorrelation matrix:")
    print(corr)

    eq_sharpe, eq_port = _portfolio_sharpe(df, weights=None)
    rp_weights = _risk_parity_weights(df)
    rp_sharpe, rp_port = _portfolio_sharpe(df, weights=rp_weights)

    per_sym = {}
    for sym in df.columns:
        s = df[sym]
        mean = float(s.mean())
        std = float(s.std(ddof=1))
        per_sym[sym] = {
            "mean_daily_pnl": mean,
            "std_daily_pnl": std,
            "sharpe_annual": (mean / std * math.sqrt(252)) if std else 0.0,
            "trading_days": int((s != 0).sum()),
            "total_pnl": float(s.sum()),
        }

    out = {
        "n_days": int(len(df)),
        "symbols": list(df.columns),
        "per_symbol": per_sym,
        "correlation_matrix": corr.to_dict(),
        "portfolio_equal_weight_sharpe": float(eq_sharpe),
        "portfolio_risk_parity_sharpe": float(rp_sharpe),
        "risk_parity_weights": {sym: float(w) for sym, w in zip(df.columns, rp_weights)},
    }

    if probabilistic_sharpe_ratio is not None:
        try:
            out["portfolio_psr_0_equal_weight"] = float(
                probabilistic_sharpe_ratio(eq_port.values, threshold_sr=0.0)
            )
        except Exception as e:
            out["portfolio_psr_0_equal_weight_error"] = str(e)
    if deflated_sharpe_ratio is not None:
        try:
            out["portfolio_dsr_equal_weight"] = float(
                deflated_sharpe_ratio(eq_port.values, n_trials=df.shape[1])
            )
        except Exception as e:
            out["portfolio_dsr_equal_weight_error"] = str(e)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {args.out}")
    print(f"\nEqual-weight portfolio Sharpe : {eq_sharpe:>7.3f}")
    print(f"Risk-parity   portfolio Sharpe : {rp_sharpe:>7.3f}")
    if "portfolio_psr_0_equal_weight" in out:
        print(f"Portfolio PSR(0) (equal-weight): {out['portfolio_psr_0_equal_weight']:>7.3f}")
    if "portfolio_dsr_equal_weight" in out:
        print(f"Portfolio DSR (n_trials={df.shape[1]}):     {out['portfolio_dsr_equal_weight']:>7.3f}")
    print()


if __name__ == "__main__":
    main()
