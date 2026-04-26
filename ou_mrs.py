"""OU-MRS live runner. Paper by default. Re-uses strategy.py -- same signals as backtest."""
import os, time, json, logging
from datetime import datetime, time as dtime
import pandas as pd
from dotenv import load_dotenv
from angel_adapter import AngelBroker
from strategy import compute_signal, Params
import live_hook
from account import ACCOUNT_ID, sl_orders_log_path  # Phase 8f.2
import signal_publisher  # Phase 8f.5
from prop_firm_monitor import PropFirmMonitor  # Phase 8e

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("ou_mrs.log"), logging.StreamHandler()],
)
log = logging.getLogger("ou_mrs")

LIVE          = os.environ.get("LIVE", "false").lower() == "true"
CAPITAL       = int(os.environ.get("CAPITAL", 150_000))

# --- Phase 8g: multi-instrument config ---
INSTRUMENT_CFG = {
    "BNF": {"symbol": os.environ.get("BANKNIFTY_FUT_SYMBOL", "BANKNIFTY26MAY26FUT"), "token": os.environ.get("BANKNIFTY_FUT_TOKEN", "66068"), "lot_size": 30, "margin_per_lot": 75_000, "atr_mult": 1.5, "exchange": "NFO"},
    "NF":  {"symbol": os.environ.get("NIFTY_FUT_SYMBOL", "NIFTY26MAY26FUT"),         "token": os.environ.get("NIFTY_FUT_TOKEN", "66071"),     "lot_size": 65, "margin_per_lot": 50_000, "atr_mult": 1.5, "exchange": "NFO"},
    "FNF": {"symbol": os.environ.get("FINNIFTY_FUT_SYMBOL", "FINNIFTY26MAY26FUT"),   "token": os.environ.get("FINNIFTY_FUT_TOKEN", "66069"),  "lot_size": 60, "margin_per_lot": 60_000, "atr_mult": 1.5, "exchange": "NFO"},
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
    if capital < 200_000:    return "TINY"
    if capital < 1_500_000:  return "PAPER"
    if capital < 2_500_000:  return "FTMO_STARTER"
    if capital < 5_000_000:  return "FTMO_PRO"
    return "FTMO_ELITE"

MAX_LOTS      = max_lots_for_capital(CAPITAL, "BNF")
CAPITAL_TIER  = capital_tier(CAPITAL)
MAX_TRADES    = 8
DAILY_LOSS    = 0.02
SESSION_START = dtime(9, 30)
SESSION_END   = dtime(14, 45)
SQUAREOFF     = dtime(15, 15)
PARAMS        = Params()

HB_INTERVAL_SEC        = 30   # Phase 5b: exactly 1-per-30s heartbeat
PORTFOLIO_REFRESH_SEC  = 25   # Phase 4b: throttle Angel portfolio calls
STOP_CIRCUIT_THRESHOLD = 3    # Phase 3b: 3 consecutive STOPs -> kill

def size_lots(atr: float) -> int:
    stop = max(atr * 1.5, 20)
    budget = 0.25 * 0.05 * CAPITAL  # Phase 8b.5: Kelly halved from 0.10
    return max(1, min(MAX_LOTS, int(budget / (stop * LOT_SIZE))))

def _exit(broker, pos, bar, reason):
    side = "SELL" if pos["side"] == "BUY" else "BUY"
    qty = pos["qty"] * LOT_SIZE
    # Phase 8d: cancel pending SL before closing (skip if reason==STOP — SL already fired)
    _sl_id = pos.get("sl_order_id")
    if LIVE and _sl_id and reason != "STOP":
        try:
            broker.cancel_order(_sl_id)
        except Exception as _e:
            log.warning(f"SL cancel failed for {_sl_id}: {_e}")
    try:
        import json as _json
        from pathlib import Path as _P
        _P("state").mkdir(exist_ok=True)
        with open("state/sl_orders.jsonl", "a") as _f:
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
    pnl = pnl_pts * pos["qty"] * LOT_SIZE - 40
    log.info(f"EXIT ({reason}) @ {bar['close']:.2f} pnl=Rs{pnl:.0f}")
    with open("trades.jsonl", "a") as f:
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
    """Phase 4b: pull rmsLimit + position once. Never raises."""
    try:
        rms = None; pos = None
        try:
            rms = broker.smart.rmsLimit().get("data")
        except Exception:
            pass
        try:
            pos = broker.smart.position().get("data")
        except Exception:
            pass
        return {"rms": rms, "position": pos, "ts": datetime.now().isoformat()}
    except Exception:
        return None

def reconcile_sl_orders(broker):
    """Phase 8d.1: on startup, sweep state/sl_orders.jsonl for today's SL orders,
    query broker status, cancel any still-open orphans from a prior crashed session."""
    import json, os
    from datetime import date, datetime
    path = "state/sl_orders.jsonl"
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
                except Exception:
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
    try:
        reconcile_sl_orders(broker)   # Phase 8d.1
    except Exception as _e:
        log.warning(f"[reconcile] failed (non-fatal): {_e}")
    position = None
    trades_today = 0
    pnl_today = 0.0
    kill = False
    soft_halt = False  # Phase 8e: prop-firm soft halt blocks new entries
    pfm = PropFirmMonitor(capital=CAPITAL)  # Phase 8e
    log.info(f"[pfm] init: {pfm.status_summary()}")
    last_minute = None
    reasons_log = []              # Phase 3b: for circuit breaker
    last_hb_ts = 0.0              # Phase 5b
    last_portfolio_ts = 0.0       # Phase 4b
    cached_portfolio = None
    log.info(f"OU-MRS started. ACCOUNT={ACCOUNT_ID} LIVE={LIVE} CAPITAL=Rs{CAPITAL:,} TIER={CAPITAL_TIER} MAX_LOTS_BNF={MAX_LOTS}")
    try:
        signal_publisher.publish_flat()  # Phase 8f.5
    except Exception as _e:
        log.debug(f"signal publish_flat failed: {_e}")

    while True:
        now = datetime.now()
        if now.time() > dtime(15, 30):
            log.info(f"EOD. trades={trades_today} pnl=Rs{pnl_today:.0f}")
            try:
                pfm.end_of_day(pnl_today)
                log.info(f"[pfm] EOD: {pfm.status_summary()}")
            except Exception as _e:
                log.warning(f"[pfm] end_of_day failed: {_e}")
            break

        # Phase 5b: clean heartbeat
        _t = time.time()
        if _t - last_hb_ts >= HB_INTERVAL_SEC:
            log.info(f"[heartbeat] alive position={'YES' if position else 'no'} trades={trades_today} pnl=Rs{pnl_today:.0f}")
            last_hb_ts = _t
            try: signal_publisher.heartbeat(pnl_today)  # Phase 8f.5
            except Exception as _e: log.debug(f"signal heartbeat failed: {_e}")

        if now.minute == last_minute or now.second < 5:
            time.sleep(1)
            continue
        last_minute = now.minute

        try:
            session_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            rows = broker.get_candles(session_open, now, "ONE_MINUTE")
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])
            df["ts"] = pd.to_datetime(df["ts"])
            df = df.set_index("ts")
            bar = df.iloc[-1]
            sig = compute_signal(df, PARAMS)

            # Phase 4b: refresh portfolio snapshot, throttled
            if _t - last_portfolio_ts >= PORTFOLIO_REFRESH_SEC:
                cached_portfolio = _snapshot_portfolio(broker)
                last_portfolio_ts = _t

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
                elif position:
                    _state = "in_trade"
                    _reason = f"holding {position['side']} {position['qty']}l @ Rs{position.get('entry_px','-')}"
                elif kill:
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
                if position:
                    _pts = (float(bar["close"]) - position["entry_px"]) * (1 if position["side"]=="BUY" else -1)
                    _upnl = _pts * position["qty"] * LOT_SIZE - 40
                    _pos = {
                        "side": position["side"],
                        "entry": float(position["entry_px"]),
                        "qty": position["qty"],
                        "entry_ts": str(position.get("entry_ts","")),
                        "bars_held": position.get("bars_held", 0),
                        "half_life": position.get("half_life", 0),
                        "unrealized_pnl": round(_upnl, 2),
                    }
                _depth = None
                try:
                    _smart = getattr(broker, "smart", None) or getattr(broker, "client", None)
                    _tok = os.getenv("BANKNIFTY_FUT_TOKEN")
                    if _smart and _tok and hasattr(_smart, "getMarketData"):
                        _md = _smart.getMarketData(mode="FULL", exchangeTokens={"NFO":[_tok]})
                        if _md.get("status") and _md.get("data",{}).get("fetched"):
                            _d = _md["data"]["fetched"][0]
                            _depth = {
                                "bids": _d.get("depth",{}).get("buy",[])[:5],
                                "asks": _d.get("depth",{}).get("sell",[])[:5],
                            }
                except Exception:
                    pass
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
                    reasons_log=reasons_log[-10:],
                    kill=kill,
                    trades_today=trades_today,
                    pnl_today=round(pnl_today, 2),
                )
            except Exception as _e:
                log.debug(f"live_hook tick failed: {_e}")
            # --- /LIVE_HOOK_v1 ---


            if position and bar.name.time() >= SQUAREOFF:
                p = _exit(broker, position, bar, "EOD")
                pnl_today += p
                position = None
                reasons_log.append("EOD")
                continue

            # Phase 8e: prop-firm rule check
            _pfm_state = pfm.check(pnl_today)
            if _pfm_state["state"] == "soft_halt" and not soft_halt:
                soft_halt = True
                log.warning(f"[pfm] SOFT HALT: {_pfm_state['reason']} pnl={pnl_today:.0f} dd={_pfm_state['dd']:.0f}")
            _pfm_hard = _pfm_state["state"] == "hard_halt"
            if kill or pnl_today <= -DAILY_LOSS * CAPITAL or _pfm_hard:
                if _pfm_hard and not kill:
                    log.error(f"[pfm] HARD HALT: {_pfm_state['reason']} pnl={pnl_today:.0f} dd={_pfm_state['dd']:.0f}")
                if position:
                    p = _exit(broker, position, bar, "KILL")
                    pnl_today += p
                    position = None
                    reasons_log.append("KILL")
                kill = True
                continue

            if position:
                if not sig:
                    continue
                reason = None
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
                    p = _exit(broker, position, bar, reason)
                    pnl_today += p
                    position = None
                    reasons_log.append(reason)
                    # Phase 3b: circuit breaker — 3 consecutive STOPs kills the day
                    if reason == "STOP" and reasons_log[-STOP_CIRCUIT_THRESHOLD:].count("STOP") >= STOP_CIRCUIT_THRESHOLD:
                        kill = True
                        log.warning(f"CIRCUIT BREAKER: {STOP_CIRCUIT_THRESHOLD} consecutive STOPs — shutting down for day.")
                continue

            if not sig or not sig.side:
                continue
            if soft_halt:  # Phase 8e: no new entries during soft halt
                continue
            if not (SESSION_START <= bar.name.time() <= SESSION_END):
                continue
            if trades_today >= MAX_TRADES:
                continue

            qty_lots = size_lots(sig.atr)
            qty = qty_lots * LOT_SIZE
            # Phase 8d: compute server-side SL price at entry ± 1.5 * ATR
            _sl_offset = max(1.5 * sig.atr, 20.0)
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
                broker.place_market(sig.side, qty)
                try:
                    sl_oid = broker.place_stoploss_limit(_sl_side, qty, _sl_trig, _sl_lim)
                except Exception as _e:
                    log.error(f"SL placement failed: {_e} — emergency market exit")
                    broker.place_market(_sl_side, qty)
                    continue
            else:
                log.info(f"[PAPER] {sig.side} {qty_lots}l @ {sig.price:.2f} [SL {_sl_side} trig={_sl_trig:.2f} lim={_sl_lim:.2f}]")
            position = {
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
            }
            # Phase 8d: persist SL state for crash recovery
            try:
                import json as _json
                from pathlib import Path as _P
                _P("state").mkdir(exist_ok=True)
                with open("state/sl_orders.jsonl", "a") as _f:
                    _f.write(_json.dumps({
                        "ts": str(bar.name), "event": "placed",
                        "sl_order_id": sl_oid, "side": _sl_side,
                        "trigger": _sl_trig, "limit": _sl_lim, "qty": qty,
                    }) + "\n")
            except Exception as _e:
                log.debug(f"SL state persist failed: {_e}")
            trades_today += 1
            log.info(f"ENTRY {sig.side} {qty_lots}l @ {sig.price:.2f} z={sig.z:.2f} hl={sig.half_life:.1f}")
            try:
                signal_publisher.publish_entry(  # Phase 8f.5
                    side=sig.side, qty_lots=qty_lots, lot_size=LOT_SIZE,
                    entry_price=sig.price, entry_time=bar.name, stop_loss=_sl_trig,
                )
            except Exception as _e:
                log.debug(f"signal publish_entry failed: {_e}")
        except Exception as e:
            log.exception(f"Loop error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()
