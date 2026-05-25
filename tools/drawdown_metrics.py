#!/usr/bin/env python3
"""
Drawdown analytics for OU-MRS backtests.

Reads bt_out_<SYM>/trades.csv and computes drawdown metrics that PSR/DSR
alone do not surface:

  - Max drawdown (MDD) absolute and as percent of peak equity
  - MDD duration in trades (peak -> trough -> recovery)
  - Calmar ratio (annualized net P&L / |MDD|)
  - Ulcer Index (Martin & McCann 1989)
  - Recovery factor (net P&L / |MDD|)

Outputs validation/drawdown_metrics.json with per-symbol breakdown.

Usage:
  python tools/drawdown_metrics.py            # all symbols in bt_out_*
  python tools/drawdown_metrics.py BNF NF     # specific symbols
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _equity_curve_from_trades(trades_csv: Path) -> pd.Series:
    df = pd.read_csv(trades_csv)
    if "exit_ts" not in df.columns or "pnl" not in df.columns:
        raise ValueError(
            f"{trades_csv}: expected columns 'exit_ts' and 'pnl'; "
            f"got {list(df.columns)}"
        )
    df["exit_ts"] = pd.to_datetime(df["exit_ts"])
    df = df.sort_values("exit_ts").reset_index(drop=True)
    eq = df["pnl"].cumsum()
    eq.index = df["exit_ts"]
    return eq


def _drawdown_series(equity: pd.Series) -> pd.Series:
    running_max = equity.cummax()
    return equity - running_max


def _mdd_duration_trades(equity: pd.Series) -> int:
    if len(equity) < 2:
        return 0
    running_max = equity.cummax()
    dd = equity - running_max
    if dd.min() == 0:
        return 0
    trough_pos = int(np.argmin(dd.values))
    peak_val = running_max.iloc[trough_pos]
    # Recovery is first index after trough where equity >= peak value.
    after = equity.iloc[trough_pos:]
    rec_mask = after.values >= peak_val
    if not rec_mask.any():
        return len(equity) - int(np.argmax(running_max.values == peak_val))
    rec_pos = trough_pos + int(np.argmax(rec_mask))
    peak_pos = int(np.argmax(running_max.values == peak_val))
    return rec_pos - peak_pos


def _ulcer_index(equity: pd.Series, base_capital: float = 3_750_000.0) -> float:
    # Express drawdown as percent of (base_capital + running max) so an
    # all-zero start does not divide by zero.
    running_max = equity.cummax()
    base = (running_max + base_capital).replace(0, np.nan)
    pct_dd = ((equity - running_max) / base) * 100.0
    pct_dd = pct_dd.fillna(0.0)
    return float(np.sqrt(np.mean(pct_dd.values ** 2)))


def _calmar(equity: pd.Series, periods_per_year: float = 252.0) -> float:
    if len(equity) < 2:
        return 0.0
    total_return = float(equity.iloc[-1] - equity.iloc[0])
    span_days = max((equity.index[-1] - equity.index[0]).days, 1)
    annualized = total_return * (periods_per_year / span_days)
    mdd = abs(float(_drawdown_series(equity).min()))
    if mdd == 0:
        return float("inf") if annualized > 0 else 0.0
    return float(annualized / mdd)


def analyze_symbol(symbol: str, bt_dir: Path) -> dict:
    trades_csv = bt_dir / "trades.csv"
    if not trades_csv.exists():
        return {"symbol": symbol, "error": f"missing {trades_csv}"}
    try:
        equity = _equity_curve_from_trades(trades_csv)
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}
    if len(equity) == 0:
        return {"symbol": symbol, "error": "empty equity curve"}
    dd = _drawdown_series(equity)
    mdd = float(dd.min())
    net = float(equity.iloc[-1] - equity.iloc[0])
    return {
        "symbol": symbol,
        "n_trades": int(len(equity)),
        "net_pnl": net,
        "mdd": mdd,
        "mdd_pct_of_base": float(mdd / 3_750_000.0 * 100.0),
        "mdd_duration_trades": _mdd_duration_trades(equity),
        "ulcer_index": _ulcer_index(equity),
        "calmar_ratio": _calmar(equity),
        "recovery_factor": float(net / abs(mdd)) if mdd != 0 else None,
    }


def main(symbols: list) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    if not symbols:
        symbols = sorted(
            d.name.replace("bt_out_", "")
            for d in repo_root.glob("bt_out_*")
            if d.is_dir()
        )
    results = []
    for sym in symbols:
        bt_dir = repo_root / f"bt_out_{sym}"
        if not bt_dir.exists():
            results.append({"symbol": sym, "error": f"missing dir {bt_dir}"})
            continue
        results.append(analyze_symbol(sym, bt_dir))

    out_dir = repo_root / "validation"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "drawdown_metrics.json"
    out_path.write_text(json.dumps({"per_symbol": results}, indent=2))
    print(f"Wrote {out_path}")
    for r in results:
        print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
