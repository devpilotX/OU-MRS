"""OU-MRS live runner. Paper by default. Re-uses strategy.py -- same signals as backtest."""
import os, time, json, logging
from datetime import datetime, time as dtime
import pandas as pd
from dotenv import load_dotenv
from angel_adapter import AngelBroker
from strategy import compute_signal, Params, should_time_stop_hl, should_velocity_stop  # Phase 9.5
from strategy import should_trail_stop  # Phase 9.5g
import live_hook
from account import ACCOUNT_ID, sl_orders_log_path  # Phase 8f.2
from ou_mrs_runner import OuMrsRunner  # Phase 8g.2.b
import signal_publisher  # Phase 8f.5
from prop_firm_monitor import PropFirmMonitor  # Phase 8e
from cost_model import compute_rt_cost  # Phase A1
from pathlib import Path as _A3P  # Phase A3 (idempotent alias)
from latency import Timer as _LatTimer, flush_if_due as _lat_flush  # Phase A12
TRADES_PATH = _A3P(__file__).resolve().parent / "trades.jsonl"  # Phase A3: CWD-independent

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("ou_mrs.log"), logging.StreamHandler()],
)
log = logging.getLogger("ou_mrs")

LIVE          = os.environ.get("LIVE", "false").lower() == "true"
CAPITAL       = int(os.environ.get("CAPITAL", 150_000))

# 8p.2: tier-aware parameter regime auto-applied by capital
from tier_policy import get_policy as _get_policy
_TIER_NAME, _POLICY = _get_policy(CAPITAL)

# --- Phase 8g: multi-instrument config ---
INSTRUMENT_CFG = {
    "BNF": {"symbol": os.environ.get("BANKNIFTY_FUT_SYMBOL", "BANKNIFTY26MAY26FUT"), "token": os.environ.get("BANKNIFTY_FUT_TOKEN", "66068"), "lot_size": 30, "margin_per_lot": 75_000, "atr_mult": _POLICY["atr_mult"], "exchange": "NFO"},
    "NF":  {"symbol": os.environ.get("NIFTY_FUT_SYMBOL", "NIFTY26MAY26FUT"),         "token": os.environ.get("NIFTY_FUT_TOKEN", "66071"),     "lot_size": 65, "margin_per_lot": 50_000, "atr_mult": _POLICY["atr_mult"], "exchange": "NFO"},
    "FNF": {"symbol": os.environ.get("FINNIFTY_FUT_SYMBOL", "FINNIFTY26MAY26FUT"),   "token": os.environ.get("FINNIFTY_FUT_TOKEN", "66069"),  "lot_size": 60, "margin_per_lot": 60_000, "atr_mult": _POLICY["atr_mult"], "exchange": "NFO"},
}
INSTRUMENTS = [s.strip().upper() for s in os.environ.get("INSTRUMENTS", "BNF").split(",") if s.strip().upper() in INSTRUMENT_CFG]
assert INSTRUMENTS, "INSTRUMENTS env var resolved to empty list; check INSTRUMENT_CFG keys"
# --- end Phase 8g ---
LOT_SIZE      = 15

# Phase 8f: capital-aware lot caps and tier labels
# 1 BNF lot needs ~Rs40k margin + ~Rs35k buffer = ~Rs75k per lot
def max_lots_for_capital(capital: int, instrument: str = "BNF") -> int:
    per_lot = {"BNF": 75_000, "NF": 50_000, "FNF": 60_000, "SENSEX": 90_000}[instrument]
    return max(1, min(50, capital // per_lot))

def capital_tier(capital: int) -> str:
    # 8p.0: asset-management tier labels (no retail prop-firm vocab)
    if capital < 200_000:    return "SEED"
    if capital < 1_500_000:  return "GROWTH"
    if capital < 2_500_000:  return "INSTITUTIONAL"
    if capital < 5_000_000:  return "HEDGE_FUND"
    return "QUANT_ELITE"

MAX_LOTS_BNF  = max_lots_for_capital(CAPITAL, "BNF")  # Phase 8g.4.a: legacy startup log only
CAPITAL_TIER  = capital_tier(CAPITAL)
MAX_TRADES    = 8           # Phase 8g.5: now AGGREGATE cap across runners (was per-symbol)
MAX_CONCURRENT_POSITIONS = int(os.environ.get("MAX_CONCURRENT_POSITIONS", _POLICY["max_concurrent_positions"]))  # Phase 8g.5: corr cap
DAILY_LOSS    = _POLICY["daily_loss_cap_pct"]  # 8p.2: tier-aware
SESSION_START = dtime(9, 30)
SESSION_END   = dtime(14, 45)
SQUAREOFF     = dtime(15, 15)
# Phase 9.8i: per-symbol candle cache (incremental fetch, eliminates rate-limit bleed)
import pandas as _pd_p98i
from datetime import timedelta as _td_p98i
_candle_cache_p98i = {}  # {sym: pd.DataFrame}

PARAMS        = Params()
try:
    PARAMS.z_entry = _POLICY["z_entry"]  # 8p.2: tier-aware
    PARAMS.z_stop  = _POLICY["z_stop"]   # 8p.2: tier-aware
    PARAMS.adx_threshold = float(os.environ.get("OU_ADX_THRESHOLD", 30.0))  # Phase 9.5c: realistic-cost sweep winner PF=1.277 (was 1.24 fee-illusion)
    PARAMS.z_entry = float(os.environ.get("OU_Z_ENTRY", PARAMS.z_entry))  # Phase 9.7b: live tunable
    # Phase 9.8: regime allow-list filter via env (e.g. OU_REGIME_FILTER=CHOP or CHOP,RANGE)
    _rf_p98 = os.environ.get("OU_REGIME_FILTER", "").strip()
    if _rf_p98:
        PARAMS.regime_allow = tuple(r.strip().upper() for r in _rf_p98.split(",") if r.strip())
except Exception as _e:
    log.warning(f"8p.2 policy override on PARAMS skipped: {_e}")

HB_INTERVAL_SEC        = 30   # Phase 5b: exactly 1-per-30s heartbeat
PORTFOLIO_REFRESH_SEC  = 25   # Phase 4b: throttle Angel portfolio calls
STOP_CIRCUIT_THRESHOLD = 3    # Phase 3b: 3 consecutive STOPs -> runner.kill

def size_lots(atr: float, lot_size: int = 15, max_lots: int = 1, capital: int = None) -> int:
    """Phase 8g.4.a: pure. Pass per-symbol lot_size/max_lots; capital defaults to module CAPITAL."""
    if capital is None:
        capital = CAPITAL
    stop = max(atr * 1.5, 20)
    budget = 0.25 * 0.05 * capital  # Phase 8b.5: Kelly halved from 0.10
    return max(1, min(max_lots, int(budget / (stop * lot_size))))


def _can_enter_new_position(runners, current_runner, max_concurrent, max_agg_trades):
    """Phase 8g.5: gate new entries on aggregate state.

    Returns (allowed: bool, reason: str). Two checks:
      1. Correlation cap: max_concurrent simultaneous positions across all runners
      2. Aggregate trade cap: max_agg_trades total entries today across all runners
    """
    live_positions = sum(1 for r in runners.values() if r.position)
    if live_positions >= max_concurrent:
        return False, f"corr_cap {live_positions}/{max_concurrent}"
    agg_trades = sum(r.trades_today for r in runners.values())
    if agg_trades >= max_agg_trades:
        return False, f"max_trades_agg {agg_trades}/{max_agg_trades}"
    return True, "ok"

def _exit(broker, pos, bar, reason, symbol="BNF", lot_size=15):
    side = "SELL" if pos["side"] == "BUY" else "BUY"
    qty = pos["qty"] * lot_size
    # Phase 8d: cancel pending SL before closing (skip if reason==STOP — SL already fired)
    _sl_id = pos.get("sl_order_id")
    if LIVE and _sl_id and reason != "STOP":
        try:
            broker.cancel_order(_sl_id)
        except Exception as _e:
            log.warning(f"SL cancel failed for {_sl_id}: {_e}")
    try:
        import json as _json
        with open(str(sl_orders_log_path(symbol=symbol)), "a") as _f:
            _f.write(_json.dumps({
                "ts": str(bar.name), "event": "exit",
                "reason": reason, "sl_order_id": _sl_id,
            }) + "\n")
    except Exception as _e:
        log.debug(f"SL state log failed: {_e}")
    if LIVE:
        broker.place_market(side, qty)
    else:
        log.info(f"[PAPER] EXIT {side} {pos['qty']}l")
    pnl_pts = (bar["close"] - pos["entry_px"]) * (1 if pos["side"] == "BUY" else -1)
    gross = pnl_pts * pos["qty"] * lot_size
    cost = compute_rt_cost(pos["entry_px"], float(bar["close"]), lot_size, pos["qty"], side=pos["side"])
    pnl = gross - cost  # Phase A1
    log.info(f"EXIT ({reason}) @ {bar['close']:.2f} pnl=Rs{pnl:.0f}")
    with open(TRADES_PATH, "a") as f:
        f.write(json.dumps({
            "entry_ts": str(pos["entry_ts"]),
            "exit_ts": str(bar.name),
            "side": pos["side"],
            "qty": pos["qty"],
            "entry": pos["entry_px"],
            "exit": float(bar["close"]),
            "pnl": pnl,
            "reason": reason,
        }) + "\n")
    try:
        signal_publisher.publish_exit(realized_pnl=pnl)  # Phase 8f.5
    except Exception as _e:
        log.debug(f"signal publish_exit failed: {_e}")
    return pnl

def _market_hours_check():
    """Phase 5a: exit cleanly on weekends / after-hours.
    Prevents systemd restart-loops from burning Angel sessions."""
    now = datetime.now()
    if now.weekday() >= 5:
        log.info(f"Weekend ({now.strftime('%A')}) — not trading. Clean exit.")
        return False
    if now.time() >= dtime(15, 31):
        log.info(f"After market hours ({now.strftime('%H:%M')}) — clean exit.")
        return False
    if now.time() < dtime(9, 10):
        log.info(f"Before market ({now.strftime('%H:%M')}) — sleeping until 09:14.")
        while datetime.now().time() < dtime(9, 14):
            time.sleep(30)
    return True

def _snapshot_portfolio(broker):
    """Phase 4b: pull rmsLimit + runner.position once. Never raises."""
    try:
        rms = None; pos = None
        try:
            rms = broker.smart.rmsLimit().get("data")
        except Exception as _e:
            log.debug(f"_snapshot rmsLimit fetch failed: {_e}")
        try:
            pos = broker.smart.position().get("data")
        except Exception as _e:
            log.debug(f"_snapshot position fetch failed: {_e}")
        return {"rms": rms, "position": pos, "ts": datetime.now().isoformat()}
    except Exception as _e:
        log.debug(f"_snapshot_portfolio outer failed: {_e}")
        return None

def reconcile_sl_orders(broker, symbol="BNF"):
    """Phase 8d.1: on startup, sweep this account+symbol's sl_orders.jsonl for today's SL orders,
    query broker status, cancel any still-open orphans from a prior crashed session."""
    import json, os
    from datetime import date, datetime
    path = str(sl_orders_log_path(symbol=symbol))
    if not os.path.exists(path):
        log.info("[reconcile] no sl_orders.jsonl yet - clean slate")
        return {"checked": 0, "cancelled": 0, "stale": 0, "unknown": 0}
    today = date.today().isoformat()
    seen = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception as _e:
                    log.debug(f"reconcile sl_state json parse failed: {_e}")
                    continue
                oid = rec.get("sl_order_id")
                if not oid:
                    continue
                if not str(rec.get("ts", "")).startswith(today):
                    continue
                seen[oid] = rec
    except Exception as e:
        log.warning(f"[reconcile] failed to read {path}: {e}")
        return {"checked": 0, "cancelled": 0, "stale": 0, "unknown": 0, "error": str(e)}
    if not seen:
        log.info("[reconcile] no SL orders recorded today")
        return {"checked": 0, "cancelled": 0, "stale": 0, "unknown": 0}
    log.info(f"[reconcile] checking {len(seen)} SL orders from today")
    checked = cancelled = stale = unknown = 0
    for oid, rec in seen.items():
        checked += 1
        try:
            res = broker.get_order_status(oid)
        except Exception as e:
            log.warning(f"[reconcile] status {oid} raised: {e}")
            unknown += 1
            continue
        status = res.get("status", "unknown")
        action = rec.get("action", "?")
        if status == "open":
            log.warning(f"[reconcile] SL {oid} still OPEN (prior={action}) - cancelling orphan")
            try:
                broker.cancel_order(oid)
                cancelled += 1
                with open(path, "a") as _f:
                    _f.write(json.dumps({
                        "ts": datetime.now().isoformat(),
                        "action": "RECONCILE_CANCEL",
                        "sl_order_id": oid,
                        "prior_action": action,
                    }) + "\n")
            except Exception as e:
                log.error(f"[reconcile] cancel {oid} failed: {e}")
        elif status in ("complete", "cancelled", "rejected"):
            log.info(f"[reconcile] SL {oid} already {status} at broker - clean")
            stale += 1
        else:
            log.warning(f"[reconcile] SL {oid} status=unknown raw={res.get('raw')} - manual review")
            unknown += 1
    summary = {"checked": checked, "cancelled": cancelled, "stale": stale, "unknown": unknown}
    log.info(f"[reconcile] done: {summary}")
    return summary


def main():
    # Phase 5a: gate Angel login behind market-hours check
    if not _market_hours_check():
        return 0

    broker = AngelBroker().login()
    # Phase 9.7: pre-init reconcile removed (referenced undefined `runner`); see post-init loop after runners dict
    pfm = PropFirmMonitor(capital=CAPITAL)  # Phase 8e
    log.info(f"[pfm] init: {pfm.status_summary()}")
    # Phase 8g.4.a: per-symbol runners dict; 4.b will add per-symbol loop
    runners = {sym: OuMrsRunner(sym, INSTRUMENT_CFG[sym], broker=broker, capital=CAPITAL, params=PARAMS, pfm=pfm) for sym in INSTRUMENTS}
    log.info(f"[runners] init: {len(runners)} symbol(s): " + ", ".join(f"{s}={r!r}" for s, r in runners.items()))
    # Phase 9.7: post-init reconcile each runner's SL orders
    for _sym, _r in runners.items():
        try:
            reconcile_sl_orders(broker, symbol=_r.symbol)
        except Exception as _e:
            log.warning(f"[reconcile] {_sym} failed (non-fatal): {_e}")
    last_minute = None
    last_hb_ts = 0.0              # Phase 5b
    last_portfolio_ts = 0.0       # Phase 4b
    cached_portfolio = None
    log.info(f"OU-MRS started. ACCOUNT={ACCOUNT_ID} LIVE={LIVE} CAPITAL=Rs{CAPITAL:,} TIER={CAPITAL_TIER} MAX_LOTS_BNF={MAX_LOTS_BNF}")
    try:
        signal_publisher.publish_flat()  # Phase 8f.5
    except Exception as _e:
        log.debug(f"signal publish_flat failed: {_e}")

    while True:
        now = datetime.now()
        if now.time() > dtime(15, 30):
            _total_trades = sum(r.trades_today for r in runners.values())
            _total_pnl = sum(r.pnl_today for r in runners.values())
            log.info(f"EOD. trades={_total_trades} pnl=Rs{_total_pnl:.0f}")
            for _sym, _r in runners.items():
                log.info(f"  [{_sym}] trades={_r.trades_today} pnl=Rs{_r.pnl_today:.0f}")
            try:
                pfm.end_of_day(_total_pnl)
                log.info(f"[pfm] EOD: {pfm.status_summary()}")
            except Exception as _e:
                log.warning(f"[pfm] end_of_day failed: {_e}")
            break

        # Phase 5b: clean heartbeat
        _t = time.time()
        if _t - last_hb_ts >= HB_INTERVAL_SEC:
            _any_pos = any(r.position for r in runners.values())
            _hb_trades = sum(r.trades_today for r in runners.values())
            _hb_pnl = sum(r.pnl_today for r in runners.values())
            log.info(f"[heartbeat] alive in_trade={'YES' if _any_pos else 'no'} trades={_hb_trades} pnl=Rs{_hb_pnl:.0f}")
            last_hb_ts = _t
            try: signal_publisher.heartbeat(_hb_pnl)  # Phase 8f.5
            except Exception as _e: log.debug(f"signal heartbeat failed: {_e}")

        if now.minute == last_minute or now.second < 5:
            _lat_flush()  # Phase A12: emit aggregated stats every 60s
            time.sleep(1)
            continue
        last_minute = now.minute

        # Phase 8g.4.b: per-symbol orchestration loop with token mutation
        for sym, runner in runners.items():
            _saved_tok = getattr(broker, "token", None)
            _saved_exch = getattr(broker, "exchange", None)
            _saved_sym = getattr(broker, "symbol", None)
            broker.token = runner.token
            broker.exchange = runner.exchange
            broker.symbol = runner.symbol_full
            try:
                session_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
                if now < session_open:
                    continue
                # Phase 9.8i: incremental fetch with 2-min overlap
                _cached = _candle_cache_p98i.get(sym)
                if _cached is None or _cached.empty:
                    _fetch_start = session_open
                else:
                    _fetch_start = _cached.index[-1] - _td_p98i(minutes=2)
                rows = broker.get_candles(_fetch_start, now, "ONE_MINUTE")
                if not rows:
                    if _cached is not None and not _cached.empty:
                        df = _cached  # use cache when fetch fails
                    else:
                        continue
                else:
                    _new_df = pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])
                    _new_df["ts"] = pd.to_datetime(_new_df["ts"])
                    _new_df = _new_df.set_index("ts")
                    if _cached is not None and not _cached.empty:
                        df = pd.concat([_cached, _new_df])
                        df = df[~df.index.duplicated(keep="last")].sort_index()
                    else:
                        df = _new_df.sort_index()
                    _candle_cache_p98i[sym] = df.tail(500)
                bar = df.iloc[-1]
                with _LatTimer("compute_signal"):
                    sig = compute_signal(df, PARAMS)

                # Phase 4b: refresh portfolio snapshot, throttled (broker-wide; first symbol only)
                if sym == INSTRUMENTS[0] and _t - last_portfolio_ts >= PORTFOLIO_REFRESH_SEC:
                    with _LatTimer("snapshot_portfolio"):
                        cached_portfolio = _snapshot_portfolio(broker)
                    last_portfolio_ts = _t

                # Phase 8g.4.b: live_hook for first symbol only (per-symbol panels = Step 6)
                # --- LIVE_HOOK_v1: dashboard state writer (never breaks bot) ---
                try:
                    _win = getattr(PARAMS, "window", 40)
                    _closes = df["close"].tail(_win).tolist()
                    _mean = (sum(_closes)/len(_closes)) if _closes else None
                    _std = None
                    if _closes and _mean is not None:
                        _var = sum((x-_mean)**2 for x in _closes)/len(_closes)
                        _std = _var**0.5
                    if len(df) < _win:
                        _state, _reason = "warming_up", f"need {_win} bars, have {len(df)}"
                    elif runner.position:
                        _state = "in_trade"
                        _reason = f"holding {runner.position['side']} {runner.position['qty']}l @ Rs{runner.position.get('entry_px','-')}"
                    elif runner.kill:
                        _state, _reason = "cooldown", "daily loss or 3-STOP circuit breaker"
                    else:
                        _state = "idle"
                        _reason = f"watching · need |z| >= {getattr(PARAMS,'z_entry',1.5)}"
                    _ohlc = {
                        "o": float(df.iloc[0]["open"]),
                        "h": float(df["high"].max()),
                        "l": float(df["low"].min()),
                        "c": float(bar["close"]),
                        "vol": int(df["volume"].sum()) if "volume" in df.columns else 0,
                    }
                    _candles = [[idx.strftime("%H:%M"),
                                 float(r["open"]), float(r["high"]),
                                 float(r["low"]),  float(r["close"])]
                                for idx, r in df.tail(240).iterrows()]
                    _pos = None
                    if runner.position:
                        _pts = (float(bar["close"]) - runner.position["entry_px"]) * (1 if runner.position["side"]=="BUY" else -1)
                        _upnl = (_pts * runner.position["qty"] * runner.lot_size
                                 - compute_rt_cost(runner.position["entry_px"], float(bar["close"]), runner.lot_size, runner.position["qty"], side=runner.position["side"]))
                        _pos = {
                            "side": runner.position["side"],
                            "entry": float(runner.position["entry_px"]),
                            "qty": runner.position["qty"],
                            "entry_ts": str(runner.position.get("entry_ts","")),
                            "bars_held": runner.position.get("bars_held", 0),
                            "half_life": runner.position.get("half_life", 0),
                            "unrealized_pnl": round(_upnl, 2),
                        }
                    _depth = None
                    try:
                        _smart = getattr(broker, "smart", None) or getattr(broker, "client", None)
                        _tok = runner.token
                        if _smart and _tok and hasattr(_smart, "getMarketData"):
                            _md = _smart.getMarketData(mode="FULL", exchangeTokens={"NFO":[_tok]})
                            if _md.get("status") and _md.get("data",{}).get("fetched"):
                                _d = _md["data"]["fetched"][0]
                                _depth = {
                                    "bids": _d.get("depth",{}).get("buy",[])[:5],
                                    "asks": _d.get("depth",{}).get("sell",[])[:5],
                                }
                    except Exception as _e:
                        log.debug(f"live_hook payload build failed: {_e}")
                    if sym == INSTRUMENTS[0]:
                        live_hook.tick(
                            ltp=float(bar["close"]),
                            z=((_closes[-1] - _mean) / _std if (_closes and _mean is not None and _std) else getattr(sig, "z", None)),
                            mean=_mean, std=_std,
                            window=_win,
                            z_entry=getattr(PARAMS,"z_entry",1.5),
                            z_stop=getattr(PARAMS,"z_stop",3.5),
                            candles_count=len(df),
                            intraday_candles=_candles,
                            state=_state, state_reason=_reason,
                            position=_pos, depth=_depth,
                            ohlc_today=_ohlc,
                            next_check_in_sec=max(1, 60 - datetime.now().second),
                            portfolio=cached_portfolio,
                            reasons_log=runner.reasons_log[-10:],
                            kill=runner.kill,
                            trades_today=runner.trades_today,
                            pnl_today=round(runner.pnl_today, 2),
                        )
                except Exception as _e:
                    log.debug(f"live_hook tick failed: {_e}")
                # --- /LIVE_HOOK_v1 ---
                # Phase 8g.6: per-symbol dashboard state (all symbols)
                try:
                    if runner.kill:
                        _ps_state = "cooldown"
                    elif runner.position:
                        _ps_state = "in_trade"
                    elif len(df) < getattr(PARAMS, "window", 40):
                        _ps_state = "warming_up"
                    else:
                        _ps_state = "idle"
                    _ps_pos = None
                    if runner.position:
                        _ps_pts = (float(bar["close"]) - runner.position["entry_px"]) * (1 if runner.position["side"] == "BUY" else -1)
                        _ps_upnl = (_ps_pts * runner.position["qty"] * runner.lot_size
                                    - compute_rt_cost(runner.position["entry_px"], float(bar["close"]), runner.lot_size, runner.position["qty"], side=runner.position["side"]))
                        _ps_pos = {"side": runner.position["side"], "qty": runner.position["qty"], "entry": float(runner.position["entry_px"]), "unrealized_pnl": round(_ps_upnl, 2)}
                    _ll_8o3c = locals()
                    _ps_closes = _ll_8o3c.get("_closes") or []
                    _ps_mean   = _ll_8o3c.get("_mean")
                    _ps_std    = _ll_8o3c.get("_std")
                    _ps_z      = ((_ps_closes[-1] - _ps_mean) / _ps_std) if (_ps_closes and _ps_mean is not None and _ps_std) else None
                    live_hook.tick_symbol(
                        symbol=sym, ltp=float(bar["close"]), state=_ps_state,
                        state_reason=_ll_8o3c.get("_reason", ""),
                        position=_ps_pos, trades_today=runner.trades_today,
                        pnl_today=round(runner.pnl_today, 2),
                        kill=runner.kill, max_lots=runner.max_lots, lot_size=runner.lot_size,
                        reasons_log=runner.reasons_log[-5:],
                        z=_ps_z, mean=_ps_mean, std=_ps_std,
                        window=_ll_8o3c.get("_win", 40),
                        z_entry=getattr(PARAMS, "z_entry", 1.5),
                        z_stop=getattr(PARAMS, "z_stop", 3.5),
                        candles_count=len(df) if "df" in _ll_8o3c else 0,
                        intraday_candles=_ll_8o3c.get("_candles"),
                        depth=_ll_8o3c.get("_depth"),
                        ohlc_today=_ll_8o3c.get("_ohlc"),
                        next_check_in_sec=max(1, 60 - datetime.now().second),
                        portfolio=_ll_8o3c.get("cached_portfolio"),
                    )
                except Exception as _e:
                    log.debug(f"live_hook tick_symbol failed [{sym}]: {_e}")


                if runner.position and bar.name.time() >= SQUAREOFF:
                    p = _exit(broker, runner.position, bar, "EOD", symbol=runner.symbol, lot_size=runner.lot_size)
                    runner.pnl_today += p
                    runner.position = None
                    runner.reasons_log.append("EOD")
                    continue

                # Phase 8e: prop-firm rule check (aggregate pnl across runners)
                _agg_pnl = sum(r.pnl_today for r in runners.values())
                _pfm_state = pfm.check(_agg_pnl)
                if _pfm_state["state"] == "soft_halt" and not runner.soft_halt:
                    runner.soft_halt = True
                    log.warning(f"[pfm] SOFT HALT [{sym}]: {_pfm_state['reason']} agg_pnl={_agg_pnl:.0f} dd={_pfm_state['dd']:.0f}")
                _pfm_hard = _pfm_state["state"] == "hard_halt"
                if runner.kill or _agg_pnl <= -DAILY_LOSS * CAPITAL or _pfm_hard:
                    if _pfm_hard and not runner.kill:
                        log.error(f"[pfm] HARD HALT [{sym}]: {_pfm_state['reason']} agg_pnl={_agg_pnl:.0f} dd={_pfm_state['dd']:.0f}")
                    if runner.position:
                        p = _exit(broker, runner.position, bar, "KILL", symbol=runner.symbol, lot_size=runner.lot_size)
                        runner.pnl_today += p
                        runner.position = None
                        runner.reasons_log.append("KILL")
                    runner.kill = True
                    continue

                if runner.position:
                    if not sig:
                        continue
                    reason = None
                    z = sig.z
                    # Phase 9.5d: PnL-gate TARGET to skip breakeven-trap when mean drifts to price
                    _mtm = (sig.price - runner.position["entry_px"]) * (1 if runner.position["side"] == "BUY" else -1)
                    _profitable = _mtm > 0
                    if   runner.position["side"] == "BUY"  and z >= 0 and _profitable: reason = "TARGET"
                    elif runner.position["side"] == "SELL" and z <= 0 and _profitable: reason = "TARGET"
                    elif abs(z) > PARAMS.z_stop and (
                        (runner.position["side"] == "BUY"  and z < 0) or
                        (runner.position["side"] == "SELL" and z > 0)):
                        reason = "STOP"
                    runner.position["bars_held"] += 1
                    runner.position.setdefault("z_history", []).append(z)  # Phase 9.5: z_history append
                    if not reason and should_time_stop_hl(runner.position["bars_held"], runner.position["half_life"]):  # Phase 9.5
                        reason = "TIME_STOP_HL"
                    if not reason and should_velocity_stop(runner.position.get("z_history", []), runner.position["side"]):  # Phase 9.5
                        reason = "Z_VEL_STALL"
                    # Phase 9.5g: trail stop check (last priority)
                    if not reason:
                        _ppts_p95g = max(runner.position.get("peak_pnl_pts", 0.0), _mtm)
                        runner.position["peak_pnl_pts"] = _ppts_p95g
                        if should_trail_stop(_mtm, _ppts_p95g, runner.position["atr"]):
                            reason = "TRAIL_STOP"
                    if reason:
                        p = _exit(broker, runner.position, bar, reason, symbol=runner.symbol, lot_size=runner.lot_size)
                        runner.pnl_today += p
                        runner.position = None
                        runner.reasons_log.append(reason)
                        # Phase 3b: circuit breaker — 3 consecutive STOPs kills the day
                        if reason == "STOP" and runner.reasons_log[-STOP_CIRCUIT_THRESHOLD:].count("STOP") >= STOP_CIRCUIT_THRESHOLD:
                            runner.kill = True
                            log.warning(f"CIRCUIT BREAKER: {STOP_CIRCUIT_THRESHOLD} consecutive STOPs — shutting down for day.")
                    continue

                if not sig or not sig.side:
                    continue
                if runner.soft_halt:  # Phase 8e: no new entries during soft halt
                    continue
                if not (SESSION_START <= bar.name.time() <= SESSION_END):
                    continue
                # Phase 8g.5: correlation + aggregate trade cap
                _can, _block_reason = _can_enter_new_position(runners, runner, MAX_CONCURRENT_POSITIONS, MAX_TRADES)
                if not _can:
                    log.debug(f"[entry_blocked] [{sym}] {_block_reason}")
                    runner.reasons_log.append(f"BLOCKED:{_block_reason.split()[0]}")
                    continue

                qty_lots = size_lots(sig.atr, lot_size=runner.lot_size, max_lots=runner.max_lots, capital=CAPITAL)
                qty = qty_lots * runner.lot_size
                # Phase 8d: compute server-side SL price at entry ± 1.5 * ATR
                _sl_offset = max(runner.atr_mult * sig.atr, 20.0)
                _slip = max(0.3 * sig.atr, 5.0)
                if sig.side == "BUY":
                    _sl_trig = sig.price - _sl_offset
                    _sl_lim  = _sl_trig - _slip
                    _sl_side = "SELL"
                else:
                    _sl_trig = sig.price + _sl_offset
                    _sl_lim  = _sl_trig + _slip
                    _sl_side = "BUY"
                sl_oid = None
                if LIVE:
                    with _LatTimer("place_market_entry"):
                        broker.place_market(sig.side, qty)
                    try:
                        with _LatTimer("place_stoploss_limit"):
                            sl_oid = broker.place_stoploss_limit(_sl_side, qty, _sl_trig, _sl_lim)
                    except Exception as _e:
                        log.error(f"SL placement failed: {_e} — emergency market exit")
                        with _LatTimer("place_market_sl_fallback"):
                            broker.place_market(_sl_side, qty)
                        continue
                else:
                    log.info(f"[PAPER] {sig.side} {qty_lots}l @ {sig.price:.2f} [SL {_sl_side} trig={_sl_trig:.2f} lim={_sl_lim:.2f}]")
                runner.position = {
                    "peak_pnl_pts": 0.0,
                    "side": sig.side,
                    "qty": qty_lots,
                    "entry_px": sig.price,
                    "entry_ts": bar.name,
                    "half_life": sig.half_life,
                    "atr": sig.atr,
                    "bars_held": 0,
                    "sl_order_id": sl_oid,
                    "sl_trigger": _sl_trig,
                    "sl_limit": _sl_lim,
                    "z_history": [sig.z],  # Phase 9.5: z_history seed
                }
                # Phase 8d: persist SL state for crash recovery
                try:
                    import json as _json
                    with open(str(sl_orders_log_path(symbol=runner.symbol)), "a") as _f:
                        _f.write(_json.dumps({
                            "ts": str(bar.name), "event": "placed",
                            "sl_order_id": sl_oid, "side": _sl_side,
                            "trigger": _sl_trig, "limit": _sl_lim, "qty": qty,
                        }) + "\n")
                except Exception as _e:
                    log.debug(f"SL state persist failed: {_e}")
                runner.trades_today += 1
                log.info(f"ENTRY {sig.side} {qty_lots}l @ {sig.price:.2f} z={sig.z:.2f} hl={sig.half_life:.1f}")
                try:
                    signal_publisher.publish_entry(  # Phase 8f.5
                        side=sig.side, qty_lots=qty_lots, lot_size=runner.lot_size,
                        entry_price=sig.price, entry_time=bar.name, stop_loss=_sl_trig,
                    )
                except Exception as _e:
                    log.debug(f"signal publish_entry failed: {_e}")
            except Exception as e:
                log.exception(f"Loop error [{sym}]: {e}")
            finally:
                if _saved_tok is not None: broker.token = _saved_tok
                if _saved_exch is not None: broker.exchange = _saved_exch
                if _saved_sym is not None: broker.symbol = _saved_sym
            # Phase 9.8g: stagger inter-symbol fetches to avoid Angel rate-limit burst
            time.sleep(3)
        time.sleep(2)

if __name__ == "__main__":
    main()
