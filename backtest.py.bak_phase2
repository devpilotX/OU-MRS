"""Event-driven backtest of OU-MRS on cached 1-min data.
   Outputs: trades.csv, equity.csv, metrics.json, equity.png"""
import json, math, logging
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
DATA = Path("data/BANKNIFTY_SPOT_3min.parquet")
OUT  = Path("bt_out"); OUT.mkdir(exist_ok=True)

CAPITAL        = 150_000
LOT_SIZE       = 15
MAX_LOTS       = 4
KELLY_SEED     = 0.10
BROKERAGE_RT   = 40        # Rs per round-trip
SLIPPAGE_TICKS = 1
TICK           = 0.05
SESSION_START  = pd.Timestamp("09:30").time()
SESSION_END    = pd.Timestamp("14:45").time()
SQUAREOFF      = pd.Timestamp("15:15").time()
DAILY_LOSS_PCT = 0.02
MAX_TRADES_DAY = 8

PARAMS = Params()

def size_lots(atr: float) -> int:
    stop_rs = max(atr * 1.5, 20)
    risk_budget = 0.25 * KELLY_SEED * CAPITAL
    raw = risk_budget / (stop_rs * LOT_SIZE)
    return max(1, min(MAX_LOTS, int(raw)))

def _close(pos, bar, reason):
    exit_px = bar["close"] - (SLIPPAGE_TICKS * TICK) * (1 if pos["side"] == "BUY" else -1)
    pnl_pts = (exit_px - pos["entry_px"]) * (1 if pos["side"] == "BUY" else -1)
    gross   = pnl_pts * pos["qty"] * LOT_SIZE
    net     = gross - BROKERAGE_RT
    return {
        "entry_ts": pos["entry_ts"], "exit_ts": bar.name,
        "side": pos["side"], "qty": pos["qty"],
        "entry": pos["entry_px"], "exit": exit_px,
        "pnl": net, "gross": gross, "reason": reason,
        "bars_held": pos["bars_held"],
    }

def _last_n_stops(trades, n):
    return sum(1 for t in trades[-n:] if t["reason"] == "STOP")

def run():
    df = pd.read_parquet(DATA)
    log.info(f"Loaded {len(df):,} bars")
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

        for i in range(PARAMS.window, len(day)):
            bar_ts = day.index[i]
            bar    = day.iloc[i]
            t      = bar_ts.time()

            if kill or pnl_today <= -DAILY_LOSS_PCT * CAPITAL:
                if position:
                    trades.append(_close(position, bar, "KILL"))
                    pnl_today += trades[-1]["pnl"]
                    pnl_cum   += trades[-1]["pnl"]
                    position = None
                kill = True
                break

            if position and t >= SQUAREOFF:
                trades.append(_close(position, bar, "EOD"))
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
                         (position["side"] == "BUY" and z < 0) or
                         (position["side"] == "SELL" and z > 0)):
                        reason = "STOP"
                position["bars_held"] += 1
                if not reason and position["bars_held"] >= int(5 * position["half_life"]):
                    reason = "TIME"
                if reason:
                    trades.append(_close(position, bar, reason))
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
            entry_px = sig.price + (SLIPPAGE_TICKS * TICK) * (1 if sig.side == "BUY" else -1)
            position = {
                "side": sig.side, "qty": qty_lots,
                "entry_px": entry_px, "entry_ts": bar_ts,
                "half_life": sig.half_life, "atr": sig.atr,
                "bars_held": 0,
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

    if not edf.empty:
        plt.figure(figsize=(10, 5))
        plt.plot(pd.to_datetime(edf["date"]), edf["equity"])
        plt.title("OU-MRS Equity Curve")
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

if __name__ == "__main__":
    run()
