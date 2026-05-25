"""Phase 9.8h: per-symbol full validation suite.

One-command orchestrator wrapping the existing validation.bootstrap stack
(Politis-Romano stationary bootstrap, Bailey-LdP PSR/DSR, Ljung-Box, ADF,
walk-forward Sharpe, hold-out 24/13 split).

For each symbol:
  1. Run backtest.py --symbol <sym> --auto-lot  (uses current shell env)
  2. Run the full statistical suite on bt_out_<sym>/{trades,equity}.csv
  3. Apply Phase 9.8h acceptance criteria (6 checks)
  4. Write per-symbol report + master report to validation/

Usage:
  python tools/run_validation_suite.py
  python tools/run_validation_suite.py --symbols BANKNIFTY,MIDCPNIFTY
  python tools/run_validation_suite.py --skip-backtest  (reuse existing bt_out_*)

Returns non-zero exit code if any symbol fails acceptance, so this is safe to
use as a CI / pre-merge gate (Sacred Rule #31).
"""
from __future__ import annotations
import os, sys, json, argparse, subprocess, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

SYMBOLS = ["BANKNIFTY", "NIFTY", "MIDCPNIFTY"]

# Phase 9.8h acceptance criteria.
# These are the *out-of-sample* statistical floors a strategy must clear
# before it can claim quant-grade significance on this short (37-day) sample.
ACCEPTANCE = {
    "psr_at_zero_min":      0.95,   # P(true SR > 0) >= 95%
    "dsr_n20_min":          0.50,   # Deflated SR > 50% after 20-trial correction
    "wf_consistency_min":   0.60,   # >=60% of walk-forward windows have SR > 0
    "wf_stability_max":     1.50,   # CV(SR) across walk-forward windows <= 1.5
    "ljung_box_p_min":      0.05,   # cannot reject IID at 5%
    "holdout_same_sign":    True,   # train SR sign == test SR sign
}


def run_backtest(symbol: str) -> dict:
    out_dir = HERE / f"bt_out_{symbol}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = ["python", "backtest.py", "--symbol", symbol, "--auto-lot"]
    r = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return {"error": "backtest failed", "stderr": r.stderr[-1500:]}
    mp = out_dir / "metrics.json"
    if not mp.exists():
        return {"error": "no metrics.json"}
    return json.loads(mp.read_text())


def run_validation(symbol: str) -> dict:
    """Run the full Bailey-LdP statistical stack on one symbol's backtest output."""
    from validation.bootstrap import (
        bootstrap_trade_stats, bootstrap_daily_sharpe, bootstrap_per_regime,
        compute_b0c_report, compute_b0e_report, compute_b0f_report, compute_b0g_report,
        load_trades_pnl,
    )
    out_dir = HERE / f"bt_out_{symbol}"
    trades_csv = out_dir / "trades.csv"
    equity_csv = out_dir / "equity.csv"
    if not (trades_csv.exists() and equity_csv.exists()):
        return {"error": "backtest artifacts missing"}
    pnl = load_trades_pnl(trades_csv)
    if len(pnl) < 4:
        return {"error": f"too few trades for validation ({len(pnl)})"}
    return {
        "trade_bootstrap":  bootstrap_trade_stats(pnl, n_iter=10000, seed=42),
        "daily_sharpe":     bootstrap_daily_sharpe(equity_csv, n_iter=10000, seed=42),
        "per_regime":       bootstrap_per_regime(trades_csv, n_iter=10000, seed=42),
        "psr_dsr":          compute_b0c_report(equity_csv, trades_csv),
        "iid_diagnostics":  compute_b0e_report(str(equity_csv), str(trades_csv)),
        "walk_forward":     compute_b0f_report(str(equity_csv), str(trades_csv)),
        "holdout":          compute_b0g_report(str(equity_csv), str(trades_csv)),
    }


def _safe_get(d, path, default=float("nan")):
    cur = d
    for k in path:
        try:
            cur = cur[k]
        except (KeyError, TypeError, IndexError):
            return default
    return cur


def apply_acceptance(validation: dict) -> dict:
    if "error" in validation:
        return {"PASS": False, "reason": validation["error"]}
    checks = {}
    psr = _safe_get(validation, ["psr_dsr", "trade_full_T24", "psr_at_threshold_0", "psr"])
    dsr = _safe_get(validation, ["psr_dsr", "trade_full_T24", "dsr_N20", "dsr"])
    cr  = _safe_get(validation, ["walk_forward", "trade_pnl_w15", "summary", "consistency_rate"])
    st  = _safe_get(validation, ["walk_forward", "trade_pnl_w15", "summary", "stability"])
    lb  = _safe_get(validation, ["iid_diagnostics", "trade_pnl", "ljung_box_lag5", "p_value"])
    ss  = bool(_safe_get(validation, ["holdout", "trade_holdout_train24d", "decision", "same_sign"], False))
    checks["PSR_at_0_>=0.95"]      = {"pass": (psr == psr and psr >= ACCEPTANCE["psr_at_zero_min"]), "value": psr}
    checks["DSR_N20_>=0.50"]       = {"pass": (dsr == dsr and dsr >= ACCEPTANCE["dsr_n20_min"]),     "value": dsr}
    checks["WF_consistency_>=0.60"] = {"pass": (cr == cr and cr >= ACCEPTANCE["wf_consistency_min"]), "value": cr}
    checks["WF_stability_<=1.50"]   = {"pass": (st == st and st <= ACCEPTANCE["wf_stability_max"]),   "value": st}
    checks["LjungBox_p_>=0.05"]    = {"pass": (lb == lb and lb >= ACCEPTANCE["ljung_box_p_min"]),     "value": lb}
    checks["Holdout_same_sign"]     = {"pass": (ss == ACCEPTANCE["holdout_same_sign"]),                "value": ss}
    overall = all(c["pass"] for c in checks.values())
    return {"PASS": overall, "checks": checks, "acceptance": ACCEPTANCE}


def summarize_validation(v: dict) -> dict:
    if "error" in v:
        return v
    try:
        return {
            "n_trades":             v["trade_bootstrap"]["n_trades"],
            "point_mean_pnl":       v["trade_bootstrap"]["point_mean_pnl"],
            "ci95_mean_pnl":        v["trade_bootstrap"]["ci95_mean_pnl"],
            "p_value_one_sided":    v["trade_bootstrap"]["p_value_one_sided"],
            "point_annualized_sharpe":  v["daily_sharpe"]["point_annualized_sharpe"],
            "ci95_annualized_sharpe":   v["daily_sharpe"]["ci95_annualized_sharpe"],
            "psr_at_zero":          _safe_get(v, ["psr_dsr", "trade_full_T24", "psr_at_threshold_0", "psr"]),
            "dsr_n10":              _safe_get(v, ["psr_dsr", "trade_full_T24", "dsr_N10", "dsr"]),
            "dsr_n20":              _safe_get(v, ["psr_dsr", "trade_full_T24", "dsr_N20", "dsr"]),
            "ljung_box_lag5_p":     _safe_get(v, ["iid_diagnostics", "trade_pnl", "ljung_box_lag5", "p_value"]),
            "ljung_box_lag10_p":    _safe_get(v, ["iid_diagnostics", "trade_pnl", "ljung_box_lag10", "p_value"]),
            "adf_p":                _safe_get(v, ["iid_diagnostics", "trade_pnl", "adf", "p_value"]),
            "wf_consistency_rate":  _safe_get(v, ["walk_forward", "trade_pnl_w15", "summary", "consistency_rate"]),
            "wf_stability":         _safe_get(v, ["walk_forward", "trade_pnl_w15", "summary", "stability"]),
            "wf_sharpe_mean":       _safe_get(v, ["walk_forward", "trade_pnl_w15", "summary", "sharpe_mean"]),
            "holdout_train_sharpe": _safe_get(v, ["holdout", "trade_holdout_train24d", "train", "sharpe_per"]),
            "holdout_test_sharpe":  _safe_get(v, ["holdout", "trade_holdout_train24d", "test", "sharpe_per"]),
            "holdout_decision":     _safe_get(v, ["holdout", "trade_holdout_train24d", "decision"], {}),
        }
    except Exception as e:
        return {"summarize_error": str(e)}


def format_verdict_line(symbol: str, sym_result: dict) -> str:
    v = sym_result.get("verdict", {})
    if not v:
        return f"  {symbol}: no verdict (backtest or validation failed)"
    flag = "PASS" if v.get("PASS") else "FAIL"
    bits = []
    for name, check in v.get("checks", {}).items():
        glyph = "+" if check["pass"] else "-"
        val = check["value"]
        val_str = f"{val:.3f}" if isinstance(val, float) else str(val)
        bits.append(f"{glyph} {name}={val_str}")
    return f"  {symbol}: {flag}  [{'  '.join(bits)}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--skip-backtest", action="store_true",
                    help="Reuse existing bt_out_<sym>/ without rerunning backtest.py")
    args = ap.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    master = {}
    for sym in symbols:
        print(f"\n===== {sym} =====")
        if args.skip_backtest:
            mp = HERE / f"bt_out_{sym}" / "metrics.json"
            metrics = json.loads(mp.read_text()) if mp.exists() else {"error": "no metrics"}
        else:
            print(f"  [1/2] running backtest.py --symbol {sym} --auto-lot ...")
            metrics = run_backtest(sym)
        if "error" in metrics:
            print(f"  ! backtest failed: {metrics['error']}")
            master[sym] = {"backtest": metrics}
            continue
        print(f"  [2/2] running validation suite ...")
        validation = run_validation(sym)
        verdict = apply_acceptance(validation)
        master[sym] = {
            "metrics": {
                "trades":          metrics.get("trades"),
                "total_pnl":       metrics.get("total_pnl"),
                "win_rate":        metrics.get("win_rate"),
                "profit_factor":   metrics.get("profit_factor"),
                "sharpe":          metrics.get("sharpe"),
                "max_drawdown":    metrics.get("max_drawdown_pct"),
                "reasons":         metrics.get("reasons"),
            },
            "verdict":            verdict,
            "validation_summary": summarize_validation(validation),
        }

        per_sym_path = HERE / "validation" / f"phase_9_8h_{sym}.json"
        per_sym_path.parent.mkdir(parents=True, exist_ok=True)
        per_sym_path.write_text(json.dumps({
            **master[sym],
            "full_validation": validation,
        }, indent=2, default=str))
        print(f"  -> wrote {per_sym_path}")

    print("\n" + "=" * 70)
    print("PHASE 9.8h ACCEPTANCE")
    print("=" * 70)
    for sym in symbols:
        if sym not in master:
            continue
        print(format_verdict_line(sym, master[sym]))
    n_pass = sum(1 for s in master.values() if s.get("verdict", {}).get("PASS"))
    print(f"\n  {n_pass}/{len(symbols)} symbols PASS all 6 acceptance checks")

    out_path = HERE / "validation" / "phase_9_8h_master_report.json"
    out_path.write_text(json.dumps(master, indent=2, default=str))
    print(f"\nMaster report -> {out_path}")

    sys.exit(0 if n_pass == len(symbols) else 1)


if __name__ == "__main__":
    main()
