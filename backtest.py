"""Event-driven backtest of OU-MRS on cached 1-min data.
   Fills at NEXT bar's OPEN with slippage (no look-ahead bias).
   Outputs: trades.csv, equity.csv, metrics.json, equity.png

Phase 9.8h: PAPER_SL + BE_RATCHET wired into exit cascade.
            log_config_sanity() called at run() start.
            Exit priority: PAPER_SL > TARGET > STOP > BE_RATCHET >
                           TIME_STOP_HL > Z_VEL_STALL > TRAIL_STOP.

Phase 9.8g.11 (Fix B): symbol-specific TOD entry cutoff. The cutoff is OFF
            by default; opt-in via OU_<SHORT>_AFTERNOON_CUTOFF_HHMM env var.
            Symbol context is captured from --symbol into _BT_SYMBOL.
"""
import os, json, math, logging, argparse, sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from strategy import compute_signal, Params, should_time_stop_hl, should_velocity_stop  # Phase 9.5
from strategy_vol_regime import (
    compute_rv20 as _vr_compute_rv20,
    passes_vol_filter as _vr_passes_vol_filter,
    vol_size_multiplier as _vr_size_multiplier,
)  # Phase 9.8h.C.1
from strategy import should_trail_stop  # Phase 9.5g
from strategy import be_ratchet_hit, paper_sl_hit, log_config_sanity  # Phase 9.8h
from strategy import is_entry_blocked_by_tod  # Phase 9.8g.11 (Fix B)
from cost_model import compute_rt_cost, estimate_slippage_ticks, estimate_gap_slippage_ticks  # Phase 9.5c / 9.8h.C.2 / 9.8h.C.3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bt")

# ---------- CONFIG ----------
# Phase 9.8g.8 (audit B7/B8): per-symbol data routing.
# Phase 9.8h.C.4: BT_USE_INDEX swaps FUT -> INDEX 1-min parquets to expand
# sample size (BNF 38 -> 137 sessions, MCN 37 -> 151). NIFTY INDEX is not
# yet fetched; INDEX mode fails fast for NIFTY rather than silently using
# stale FUT data.
_SYMBOL_TO_DATA_FUT = {
    "BANKNIFTY":  "data/BANKNIFTY_FUT_1min.parquet",
    "NIFTY":      "data/NIFTY_FUT_1min.parquet",
    "MIDCPNIFTY": "data/MIDCPNIFTY_FUT_1min.parquet",
}
_SYMBOL_TO_DATA_INDEX = {
    "BANKNIFTY":  "data/BANKNIFTY_INDEX_1min_tz.parquet",
    "MIDCPNIFTY": "data/MIDCPNIFTY_INDEX_1min.parquet",
    # NIFTY intentionally omitted: no INDEX parquet on disk yet.
}


def _use_index_mode() -> bool:
    v = os.environ.get("BT_USE_INDEX", "off").strip().lower()
    return v in ("on", "true", "1", "yes")


def _resolve_data_path(symbol: str) -> str:
    if _use_index_mode():
        if symbol not in _SYMBOL_TO_DATA_INDEX:
            raise SystemExit(
                f"BT_USE_INDEX=on but no INDEX parquet for {symbol}. "
                f"Available: {sorted(_SYMBOL_TO_DATA_INDEX)}. "
                f"Either fetch {symbol}_INDEX_1min.parquet first or run with BT_USE_INDEX=off."
            )
        return _SYMBOL_TO_DATA_INDEX[symbol]
    return _SYMBOL_TO_DATA_FUT[symbol]


_SYMBOL_TO_DATA = _SYMBOL_TO_DATA_FUT  # legacy alias retained for any external use
_SYMBOL_TO_LOT = {  # Sacred Rule #6: ratified via data/instruments.db on 21 May 2026 (Phase 9.7AQ)
    "BANKNIFTY":  30,
    "NIFTY":      65,
    "MIDCPNIFTY": 120,
}
# Phase 9.8g.12 (audit B2 parity++): map backtest long names to ou_mrs.INSTRUMENT_CFG short keys
_LONG_TO_SHORT = {
    "BANKNIFTY":  "BNF",
    "NIFTY":      "NF",
    "MIDCPNIFTY": "MCN",
}

# Phase 9.8g.11 (Fix B): symbol context for the TOD cutoff helper. Set from
# --symbol in __main__; remains None for legacy bare `python backtest.py` runs
# (in which case is_entry_blocked_by_tod is a no-op).
_BT_SYMBOL = None

# Phase 9.8h.N.2: mirror per-symbol/per-side z-entry from ou_mrs.py into the backtester.
# Defaults to symmetric BT_ZENTRY (1.4) so no behavior change unless OU_Z_ENTRY_{BUY,SELL}_{BNF,NF,MCN} is set.
_BT_DEFAULT_Z_ENTRY = float(os.environ.get("BT_ZENTRY", 1.4))
_Z_ENTRY_BUY_PER_SYM_BT = {
    "BANKNIFTY":  float(os.environ.get("OU_Z_ENTRY_BUY_BNF", _BT_DEFAULT_Z_ENTRY)),
    "NIFTY":      float(os.environ.get("OU_Z_ENTRY_BUY_NF",  _BT_DEFAULT_Z_ENTRY)),
    "MIDCPNIFTY": float(os.environ.get("OU_Z_ENTRY_BUY_MCN", _BT_DEFAULT_Z_ENTRY)),
}
_Z_ENTRY_SELL_PER_SYM_BT = {
    "BANKNIFTY":  float(os.environ.get("OU_Z_ENTRY_SELL_BNF", _BT_DEFAULT_Z_ENTRY)),
    "NIFTY":      float(os.environ.get("OU_Z_ENTRY_SELL_NF",  _BT_DEFAULT_Z_ENTRY)),
    "MIDCPNIFTY": float(os.environ.get("OU_Z_ENTRY_SELL_MCN", _BT_DEFAULT_Z_ENTRY)),
}
def _z_entry_for_bt(sym, side):
    table = _Z_ENTRY_BUY_PER_SYM_BT if side == "BUY" else _Z_ENTRY_SELL_PER_SYM_BT
    return table.get(sym or "", _BT_DEFAULT_Z_ENTRY)


DATA = Path(os.environ.get("BT_DATA", "data/BANKNIFTY_FUT_1min.parquet"))
_HERE = Path(__file__).resolve().parent  # Phase A3: CWD-independent
OUT = _HERE / "bt_out"

# Phase 9.8g.2 (audit I6): env-tunable so backtests can match the live tier.
CAPITAL        = float(os.environ.get("BT_CAPITAL",  150_000))
LOT_SIZE       = int(  os.environ.get("BT_LOT_SIZE", 15))
MAX_LOTS       = int(  os.environ.get("BT_MAX_LOTS", 2))
KELLY_SEED     = float(os.environ.get("BT_KELLY",    0.05))
BROKERAGE_RT   = 40
SLIPPAGE_TICKS = int(os.environ.get("BT_SLIPPAGE_TICKS", 2))  # Phase 9.8h.B.5: env-driven for sensitivity sweep
TICK           = 0.05
SESSION_START  = pd.Timestamp("09:30").time()
SESSION_END    = pd.Timestamp("14:45").time()
SQUAREOFF      = pd.Timestamp("15:15").time()
DAILY_LOSS_PCT = float(os.environ.get("BT_DAILY_LOSS_PCT", 0.02))
MAX_TRADES_DAY = int(  os.environ.get("BT_MAX_TRADES_DAY", 8))

# Phase 9.8: optional regime allow-list
_bt_rf_p98 = os.environ.get("BT_REGIME_FILTER", "CHOP,RANGE").strip()
_regime_allow_p98 = tuple(r.strip().upper() for r in _bt_rf_p98.split(",") if r.strip()) if _bt_rf_p98 else ()
PARAMS = Params(
    adx_threshold=float(os.environ.get("BT_ADX", 30.0)),
    z_entry=float(os.environ.get("BT_ZENTRY", 1.4)),
    min_r2=float(os.environ.get("BT_MINR2", 0.05)),
    z_stop=float(os.environ.get("BT_ZSTOP", 3.5)),
    regime_allow=_regime_allow_p98,
)

# Phase 9.8g.12 (audit B2 parity++): derive defaults from the same tier policy
# that drives live (ou_mrs._get_policy, Sacred Rule #33 extended to backtest).
# Env-vars retain override priority so sensitivity sweeps still work.
from ou_mrs import _get_policy as _bt_get_policy, max_lots_for_capital as _bt_max_lots_for
_BT_TIER_NAME, _BT_POLICY = _bt_get_policy(int(CAPITAL))
_ATR_MULT = float(os.environ.get("OU_ATR_MULT", _BT_POLICY["atr_mult"]))
_RISK_PCT = float(os.environ.get("BT_RISK_PCT", _BT_POLICY["risk_per_trade_pct"]))

def size_lots(atr: float) -> int:
    stop_rs = max(atr * _ATR_MULT, 20)
    risk_budget = _RISK_PCT * CAPITAL
    raw = risk_budget / (stop_rs * LOT_SIZE)
    return max(1, min(MAX_LOTS, int(raw)))

def _close(pos, fill_bar, fill_ts, reason):
    """Fill at NEXT bar's OPEN with slippage. No look-ahead."""
    # Phase 9.8h.C.2: per-symbol + size-aware slippage. Falls back to legacy
    # flat BT_SLIPPAGE_TICKS when OU_COST_MODEL_V2 is off (default).
    _slip_ticks_c2 = estimate_slippage_ticks(_BT_SYMBOL, pos["qty"], rv20=None)
    # Phase 9.8h.C.3: gap-risk surcharge for STOP-class exits on violent bars.
    # Zero for TARGET (limit) exits and for bars within normal range/ATR ratio.
    _gap_ticks_c3 = estimate_gap_slippage_ticks(
        bar_range=(fill_bar["high"] - fill_bar["low"]),
        atr=pos.get("atr"),
        reason=reason,
    )
    _total_slip_ticks = _slip_ticks_c2 + _gap_ticks_c3
    exit_px = fill_bar["open"] - (_total_slip_ticks * TICK) * (1 if pos["side"] == "BUY" else -1)
    pnl_pts = (exit_px - pos["entry_px"]) * (1 if pos["side"] == "BUY" else -1)
    gross   = pnl_pts * pos["qty"] * LOT_SIZE
    net     = gross - compute_rt_cost(pos["entry_px"], exit_px, LOT_SIZE, pos["qty"], side=pos["side"])  # Phase 9.5c
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
    OUT.mkdir(exist_ok=True, parents=True)
    if not DATA.exists():
        log.error(f"DATA file not found: {DATA}")
        log.error(f"Run: python tools/fetch_futures_data.py --symbol <SYMBOL>  (or --all)")
        raise SystemExit(2)
    # Phase 9.8h (Sacred Rule #41): emit effective env-gated config at startup
    log_config_sanity()
    df = pd.read_parquet(DATA)
    log.info(f"Loaded {len(df):,} bars from {DATA}")
    log.info(f"Backtest config: tier={_BT_TIER_NAME}  capital={CAPITAL:,.0f}  lot_size={LOT_SIZE}  max_lots={MAX_LOTS}  atr_mult={_ATR_MULT}  risk_pct={_RISK_PCT:.4f}")
    log.info(f"Output dir: {OUT}")
    if _BT_SYMBOL is not None:
        log.info(f"Backtest symbol context (Phase 9.8g.11 TOD cutoff): {_BT_SYMBOL}")

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
                # Phase 9.8g.2 (audit B3): compute _mtm + refresh peak every bar,
                # not only on bars where a signal was generated.
                _mtm = (bar["close"] - position["entry_px"]) * (1 if position["side"] == "BUY" else -1)
                position["peak_pnl_pts"] = max(position.get("peak_pnl_pts", 0.0), _mtm)

                # Phase 9.8h: PAPER_SL FIRST -- catastrophic intra-bar stop.
                # Detected on current bar via adverse extreme (low/high); fill at next bar open.
                adverse_px = float(bar["low"]) if position["side"] == "BUY" else float(bar["high"])
                if paper_sl_hit(adverse_px, position["entry_px"], position["side"], position["atr"]):
                    reason = "PAPER_SL"

                if not reason and sig:
                    z = sig.z
                    position.setdefault("z_history", []).append(z)
                    # Phase 9.5d: PnL-gate TARGET to skip breakeven-trap when mean drifts to price
                    _profitable = _mtm > 0
                    if   position["side"] == "BUY"  and z >= 0 and _profitable: reason = "TARGET"
                    elif position["side"] == "SELL" and z <= 0 and _profitable: reason = "TARGET"
                    elif abs(z) > PARAMS.z_stop and (
                         (position["side"] == "BUY"  and z < 0) or
                         (position["side"] == "SELL" and z > 0)):
                        reason = "STOP"
                position["bars_held"] += 1

                # Phase 9.8h: BE_RATCHET -- between STOP and TIME_STOP_HL.
                # Once peak gain hit trigger * ATR, exit at lock floor (~breakeven).
                if not reason and be_ratchet_hit(_mtm, position["peak_pnl_pts"], position["atr"]):
                    reason = "BE_RATCHET"
                if not reason and should_time_stop_hl(position["bars_held"], position["half_life"]):  # Phase 9.5
                    reason = "TIME_STOP_HL"
                if not reason and should_velocity_stop(position.get("z_history", []), position["side"]):  # Phase 9.5
                    reason = "Z_VEL_STALL"
                if not reason and should_trail_stop(_mtm, position["peak_pnl_pts"], position["atr"]):  # 9.5g + 9.8g.2 dedent
                    reason = "TRAIL_STOP"
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
            # Phase 9.8h.N.2: per-symbol/per-side z-entry gate (defaults symmetric -> no-op).
            _z_thr_p98hn2 = _z_entry_for_bt(_BT_SYMBOL, sig.side)
            if abs(getattr(sig, "z", 0.0)) < _z_thr_p98hn2:
                continue
            if not (SESSION_START <= t <= SESSION_END):
                continue
            if trades_today >= MAX_TRADES_DAY:
                continue
            # Phase 9.8g.11 (Fix B): symbol-specific afternoon cutoff.
            # Env-gated via OU_<SHORT>_AFTERNOON_CUTOFF_HHMM; default OFF for all symbols.
            # Per Phase 9.8g.10 TOD analysis: NF 13:30-14:45 carried 63% of NF's loss.
            if is_entry_blocked_by_tod(_BT_SYMBOL, bar_ts):
                continue

            # Phase 9.8h.C.1: vol-regime gate from B.5 findings.
            try:
                _vr_closes_c1 = window["close"].tolist()[-21:]
            except Exception:
                _vr_closes_c1 = []
            _vr_rv20_c1 = _vr_compute_rv20(_vr_closes_c1)
            _vr_sym_c1 = (_BT_SYMBOL or "")
            _vr_ok_c1, _vr_reason_c1 = _vr_passes_vol_filter(_vr_sym_c1, _vr_rv20_c1)
            if not _vr_ok_c1:
                continue
            _vr_mult_c1 = _vr_size_multiplier(_vr_sym_c1, _vr_rv20_c1)
            qty_lots = max(1, int(size_lots(sig.atr) * _vr_mult_c1))  # Phase 9.8h.C.1: vol-aware sizing
            # Phase 9.8h.C.2: per-symbol + size-aware slippage. qty_lots already
            # reflects C.1 vol-multiplier so size penalty kicks in for MCN low-vol bursts.
            _slip_ticks_c2 = estimate_slippage_ticks(_BT_SYMBOL, qty_lots, rv20=_vr_rv20_c1)
            entry_px = next_bar["open"] + (_slip_ticks_c2 * TICK) * (1 if sig.side == "BUY" else -1)
            position = {
                "peak_pnl_pts": 0.0,
                "side": sig.side, "qty": qty_lots,
                "entry_px": entry_px, "entry_ts": next_bar_ts,
                "half_life": sig.half_life, "atr": sig.atr,
                "bars_held": 0,
                "regime": str(regime_series.shift(1).get(next_bar_ts, "UNKNOWN")),
                "z_history": [sig.z],
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

    regime_metrics = compute_regime_metrics(tdf)
    with open(OUT / "regime_metrics.json", "w") as f:
        json.dump(regime_metrics, f, indent=2, default=str)
    log.info("REGIME METRICS:\n" + json.dumps(regime_metrics, indent=2, default=str))

    if not edf.empty:
        plt.figure(figsize=(10, 5))
        plt.plot(pd.to_datetime(edf["date"]), edf["equity"])
        plt.title(f"OU-MRS Equity Curve ({DATA.stem})")
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


def _parse_args():
    p = argparse.ArgumentParser(description="OU-MRS event-driven backtest")
    p.add_argument("--symbol", choices=sorted(_SYMBOL_TO_DATA.keys()),
                   help="Symbol selector. Auto-resolves BT_DATA and OUT dir.")
    p.add_argument("--out", default=None,
                   help="Output directory (default: bt_out/ or bt_out_<symbol>/ when --symbol set)")
    p.add_argument("--auto-lot", action="store_true",
                   help="With --symbol, auto-set LOT_SIZE from instruments registry.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.symbol:
        DATA = (_HERE / _resolve_data_path(args.symbol)).resolve()
        if args.auto_lot:
            LOT_SIZE = _SYMBOL_TO_LOT[args.symbol]
            # Phase 9.8g.12 (audit B2 parity++): also auto-set MAX_LOTS from the
            # tier-aware cap function iff caller has not pinned it via BT_MAX_LOTS.
            if "BT_MAX_LOTS" not in os.environ:
                MAX_LOTS = _bt_max_lots_for(int(CAPITAL), _LONG_TO_SHORT[args.symbol])
        if not args.out:
            OUT = _HERE / f"bt_out_{args.symbol}"
        _BT_SYMBOL = args.symbol  # Phase 9.8g.11 (Fix B): feed TOD cutoff helper
    if args.out:
        OUT = Path(args.out).resolve()
    run()
