"""Event-driven backtest of OU-MRS on cached 1-min data.
   Fills at NEXT bar's OPEN with slippage (no look-ahead bias).
   Outputs: trades.csv, equity.csv, metrics.json, equity.png"""
import os, json, math, logging
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from strategy import compute_signal, Params

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bt")

# ---------- CONFIG ----------
DATA = Path(os.environ.get("BT_DATA", "data/BANKNIFTY_FUT_1min.parquet"))
OUT  = Path("bt_out"); OUT.mkdir(exist_ok=True)

CAPITAL        = 150_000
LOT_SIZE       = 15
MAX_LOTS       = 2  # Phase 8b.5: halved for prop-firm DD rules
KELLY_SEED     = 0.05  # Phase 8b.5: halved from 0.10
BROKERAGE_RT   = 40
SLIPPAGE_TICKS = 2
TICK           = 0.05
SESSION_START  = pd.Timestamp("09:30").time()
SESSION_END    = pd.Timestamp("14:45").time()
SQUAREOFF      = pd.Timestamp("15:15").time()
DAILY_LOSS_PCT = 0.02
MAX_TRADES_DAY = 8

PARAMS = Params(
    adx_threshold=float(os.environ.get("BT_ADX", 25.0)),
    z_entry=float(os.environ.get("BT_ZENTRY", 1.5)),
    min_r2=float(os.environ.get("BT_MINR2", 0.05)),
)

def size_lots(atr: float) -> int:
    stop_rs = max(atr * 1.5, 20)
    risk_budget = 0.25 * KELLY_SEED * CAPITAL
    raw = risk_budget / (stop_rs * LOT_SIZE)
    return max(1, min(MAX_LOTS, int(raw)))

def _close(pos, fill_bar, fill_ts, reason):
    """Fill at NEXT bar's OPEN with slippage. No look-ahead."""
    exit_px = fill_bar["open"] - (SLIPPAGE_TICKS * TICK) * (1 if pos["side"] == "BUY" else -1)
    pnl_pts = (exit_px - pos["entry_px"]) * (1 if pos["side"] == "BUY" else -1)
    gross   = pnl_pts * pos["qty"] * LOT_SIZE
    net     = gross - BROKERAGE_RT
    return {
        "entry_ts": pos["entry_ts"], "exit_ts": fill_ts,
        "side": pos["side"], "qty": pos["qty"],
        "entry": pos["entry_px"], "exit": exit_px,
        "pnl": net, "gross": gross, "reason": reason,
        "bars_held": pos["bars_held"],
        "regime": pos.get("regime", "UNKNOWN"),
    }

def _last_n_stops(trades, n):
    return sum(1 for t in trades[-n:] if t["reason"] == "STOP")

def run():
    df = pd.read_parquet(DATA)
    log.info(f"Loaded {len(df):,} bars")

    # Phase 8h.2: classify regime per bar (full df, smoothing across days)
    from regime import classify_regime
    regime_series = classify_regime(df)
    log.info("Regime distribution: " + str(regime_series.value_counts().to_dict()))
    trades = []
    equity = []
    pnl_cum = 0.0

    for date, day in df.groupby(df.index.date):
        if len(day) < PARAMS.window + 20:
            continue
        position = None
        trades_today = 0
        pnl_today = 0.0
        kill = False

        # len(day) - 1 ensures day.iloc[i+1] always exists (no look-ahead)
        for i in range(PARAMS.window, len(day) - 1):
            bar_ts      = day.index[i]
            bar         = day.iloc[i]
            next_bar    = day.iloc[i+1]
            next_bar_ts = day.index[i+1]
            t           = bar_ts.time()

            if kill or pnl_today <= -DAILY_LOSS_PCT * CAPITAL:
                if position:
                    trades.append(_close(position, next_bar, next_bar_ts, "KILL"))
                    pnl_today += trades[-1]["pnl"]
                    pnl_cum   += trades[-1]["pnl"]
                    position = None
                kill = True
                break

            if position and t >= SQUAREOFF:
                trades.append(_close(position, next_bar, next_bar_ts, "EOD"))
                pnl_today += trades[-1]["pnl"]
                pnl_cum   += trades[-1]["pnl"]
                position = None
                continue

            window = day.iloc[i - PARAMS.window + 1 : i + 1]
            sig = compute_signal(window, PARAMS)

            if position:
                reason = None
                if sig:
                    z = sig.z
                    if   position["side"] == "BUY"  and z >= 0: reason = "TARGET"
                    elif position["side"] == "SELL" and z <= 0: reason = "TARGET"
                    elif abs(z) > PARAMS.z_stop and (
                         (position["side"] == "BUY"  and z < 0) or
                         (position["side"] == "SELL" and z > 0)):
                        reason = "STOP"
                position["bars_held"] += 1
                if not reason and position["bars_held"] >= int(5 * position["half_life"]):
                    reason = "TIME"
                if reason:
                    trades.append(_close(position, next_bar, next_bar_ts, reason))
                    pnl_today += trades[-1]["pnl"]
                    pnl_cum   += trades[-1]["pnl"]
                    position = None
                    if reason == "STOP" and _last_n_stops(trades, 3) >= 3:
                        kill = True
                continue

            if not sig or sig.side is None:
                continue
            if not (SESSION_START <= t <= SESSION_END):
                continue
            if trades_today >= MAX_TRADES_DAY:
                continue

            qty_lots = size_lots(sig.atr)
            # Entry fills at NEXT bar's OPEN with slippage (no look-ahead)
            entry_px = next_bar["open"] + (SLIPPAGE_TICKS * TICK) * (1 if sig.side == "BUY" else -1)
            position = {
                "side": sig.side, "qty": qty_lots,
                "entry_px": entry_px, "entry_ts": next_bar_ts,
                "half_life": sig.half_life, "atr": sig.atr,
                "bars_held": 0,
                "regime": str(regime_series.get(next_bar_ts, "UNKNOWN")),
            }
            trades_today += 1

        equity.append({"date": date, "pnl_day": pnl_today, "equity": CAPITAL + pnl_cum})

    tdf = pd.DataFrame(trades)
    edf = pd.DataFrame(equity)
    tdf.to_csv(OUT / "trades.csv", index=False)
    edf.to_csv(OUT / "equity.csv", index=False)

    metrics = compute_metrics(tdf, edf)
    with open(OUT / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    log.info("METRICS:\n" + json.dumps(metrics, indent=2, default=str))

    # Phase 8h.2: per-regime metrics
    regime_metrics = compute_regime_metrics(tdf)
    with open(OUT / "regime_metrics.json", "w") as f:
        json.dump(regime_metrics, f, indent=2, default=str)
    log.info("REGIME METRICS:\n" + json.dumps(regime_metrics, indent=2, default=str))

    if not edf.empty:
        plt.figure(figsize=(10, 5))
        plt.plot(pd.to_datetime(edf["date"]), edf["equity"])
        plt.title("OU-MRS Equity Curve (look-ahead fixed)")
        plt.ylabel("Rs")
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUT / "equity.png", dpi=120)
        log.info(f"Equity chart -> {OUT/'equity.png'}")

def compute_metrics(tdf: pd.DataFrame, edf: pd.DataFrame) -> dict:
    if tdf.empty:
        return {"trades": 0, "note": "no trades generated"}
    wins = tdf[tdf["pnl"] > 0]
    losses = tdf[tdf["pnl"] <= 0]
    total_pnl = tdf["pnl"].sum()
    daily = edf.set_index("date")["pnl_day"]
    daily_ret = daily / CAPITAL
    sharpe = (daily_ret.mean() / (daily_ret.std() + 1e-12)) * math.sqrt(252) if len(daily_ret) > 1 else 0
    downside = daily_ret[daily_ret < 0].std() or 1e-12
    sortino = (daily_ret.mean() / downside) * math.sqrt(252)
    equity = edf["equity"]
    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = float(dd.min())
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) and losses["pnl"].sum() != 0 else float("inf")
    return {
        "trades": int(len(tdf)),
        "win_rate": round(len(wins) / len(tdf), 4),
        "avg_win": round(float(wins["pnl"].mean()) if len(wins) else 0, 2),
        "avg_loss": round(float(losses["pnl"].mean()) if len(losses) else 0, 2),
        "profit_factor": round(float(pf), 3),
        "total_pnl": round(float(total_pnl), 2),
        "return_pct": round(float(total_pnl / CAPITAL * 100), 2),
        "sharpe": round(float(sharpe), 3),
        "sortino": round(float(sortino), 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "trading_days": int(len(edf)),
        "trades_per_day": round(len(tdf) / max(len(edf), 1), 2),
        "reasons": tdf["reason"].value_counts().to_dict(),
    }

def compute_regime_metrics(tdf):
    """Phase 8h.2: split metrics by ADX regime (TREND/RANGE/CHOP).
    Mean-reversion edge expected in RANGE, neutral CHOP, hostile TREND.
    """
    if tdf.empty or 'regime' not in tdf.columns:
        return {}
    out = {}
    for regime in ['TREND', 'RANGE', 'CHOP', 'UNKNOWN']:
        sub = tdf[tdf['regime'] == regime]
        if len(sub) == 0:
            out[regime] = {'trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0, 'avg_pnl': 0.0, 'profit_factor': 0.0}
            continue
        wins = sub[sub['pnl'] > 0]
        losses = sub[sub['pnl'] <= 0]
        loss_sum = abs(float(losses['pnl'].sum())) if len(losses) else 0.0
        win_sum = float(wins['pnl'].sum()) if len(wins) else 0.0
        if loss_sum > 0:
            pf = win_sum / loss_sum
        elif win_sum > 0:
            pf = 999.0
        else:
            pf = 0.0
        out[regime] = {
            'trades': int(len(sub)),
            'win_rate': round(len(wins) / len(sub), 4),
            'total_pnl': round(float(sub['pnl'].sum()), 2),
            'avg_pnl': round(float(sub['pnl'].mean()), 2),
            'profit_factor': round(float(pf), 3),
        }
    return out


if __name__ == "__main__":
    run()
