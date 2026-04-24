"""OU-MRS live runner. Paper by default. Re-uses strategy.py -- same signals as backtest."""
import os, time, json, logging
from datetime import datetime, time as dtime
import pandas as pd
from dotenv import load_dotenv
from angel_adapter import AngelBroker
from strategy import compute_signal, Params
import live_hook

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("ou_mrs.log"), logging.StreamHandler()],
)
log = logging.getLogger("ou_mrs")

LIVE          = os.environ.get("LIVE", "false").lower() == "true"
CAPITAL       = int(os.environ.get("CAPITAL", 150_000))
LOT_SIZE      = 15
MAX_LOTS      = 4
MAX_TRADES    = 8
DAILY_LOSS    = 0.02
SESSION_START = dtime(9, 30)
SESSION_END   = dtime(14, 45)
SQUAREOFF     = dtime(15, 15)
PARAMS        = Params()

def size_lots(atr: float) -> int:
    stop = max(atr * 1.5, 20)
    budget = 0.25 * 0.10 * CAPITAL
    return max(1, min(MAX_LOTS, int(budget / (stop * LOT_SIZE))))

def _exit(broker, pos, bar, reason):
    side = "SELL" if pos["side"] == "BUY" else "BUY"
    qty = pos["qty"] * LOT_SIZE
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
    return pnl

def main():
    broker = AngelBroker().login()
    position = None
    trades_today = 0
    pnl_today = 0.0
    kill = False
    last_minute = None
    log.info(f"OU-MRS started. LIVE={LIVE} CAPITAL=Rs{CAPITAL:,}")

    while True:
        now = datetime.now()
        if now.time() > dtime(15, 30):
            log.info(f"EOD. trades={trades_today} pnl=Rs{pnl_today:.0f}")
            break
        if now.minute == last_minute or now.second < 5:
            _now = time.time()
            if int(_now) % 60 < 2 and int(_now) != getattr(main, "_hb", 0):
                main._hb = int(_now)
                print("[heartbeat] alive at " + time.strftime("%H:%M:%S"), flush=True)
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
                    _state, _reason = "cooldown", "daily loss limit hit"
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
                )
            except Exception as _e:
                log.debug(f"live_hook tick failed: {_e}")
            # --- /LIVE_HOOK_v1 ---


            if position and bar.name.time() >= SQUAREOFF:
                _exit(broker, position, bar, "EOD")
                position = None
                continue

            if kill or pnl_today <= -DAILY_LOSS * CAPITAL:
                if position:
                    _exit(broker, position, bar, "KILL")
                    position = None
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
                continue

            if not sig or not sig.side:
                continue
            if not (SESSION_START <= bar.name.time() <= SESSION_END):
                continue
            if trades_today >= MAX_TRADES:
                continue

            qty_lots = size_lots(sig.atr)
            qty = qty_lots * LOT_SIZE
            if LIVE:
                broker.place_market(sig.side, qty)
            else:
                log.info(f"[PAPER] {sig.side} {qty_lots}l @ {sig.price:.2f}")
            position = {
                "side": sig.side,
                "qty": qty_lots,
                "entry_px": sig.price,
                "entry_ts": bar.name,
                "half_life": sig.half_life,
                "atr": sig.atr,
                "bars_held": 0,
            }
            trades_today += 1
            log.info(f"ENTRY {sig.side} {qty_lots}l @ {sig.price:.2f} z={sig.z:.2f} hl={sig.half_life:.1f}")
        except Exception as e:
            log.exception(f"Loop error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()
