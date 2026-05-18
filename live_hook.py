"""Dashboard live-data bridge. Never crashes the bot."""
import json, time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

_STATE = Path(__file__).parent / "state" / "live.json"
_STATE.parent.mkdir(exist_ok=True)
_IST = ZoneInfo("Asia/Kolkata")

# Phase 9.7T: 5-min heartbeat z-snapshot JSONL logging (forensic trail)
_HEARTBEAT_PATH = _STATE.parent / "heartbeat.jsonl"
_LAST_HEARTBEAT_TS = {}
_HEARTBEAT_INTERVAL_S = 300.0


def _maybe_emit_heartbeat_p97t(data):
    try:
        sym = data.get("symbol")
        if not sym:
            return
        now = time.time()
        last = _LAST_HEARTBEAT_TS.get(sym, 0.0)
        if now - last < _HEARTBEAT_INTERVAL_S:
            return
        _LAST_HEARTBEAT_TS[sym] = now
        keys = ("updated_ts","updated_at","ltp","z","mean","std","state","state_reason","position","trades_today","pnl_today","candles_count")
        out = {"sym": sym}
        for k in keys:
            out[k] = data.get(k)
        _HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _HEARTBEAT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out, default=str) + chr(10))
    except Exception:
        pass



def tick(*, ltp=None, z=None, mean=None, std=None, window=40,
         z_entry=1.5, z_stop=3.5, candles_count=0, intraday_candles=None,
         state="idle", state_reason="", position=None, depth=None,
         ohlc_today=None, next_check_in_sec=None,
         portfolio=None, reasons_log=None, kill=False,
         trades_today=0, pnl_today=0.0):
    """LEGACY: writes single state/live.json (kept for dashboard backward compat)."""
    try:
        data = {
            "updated_at": datetime.now(_IST).isoformat(),
            "updated_ts": int(time.time()),
            "ltp": ltp, "z": z, "mean": mean, "std": std,
            "window": window, "z_entry": z_entry, "z_stop": z_stop,
            "candles_count": candles_count,
            "intraday_candles": intraday_candles or [],
            "state": state, "state_reason": state_reason,
            "position": position, "depth": depth,
            "ohlc_today": ohlc_today,
            "next_check_in_sec": next_check_in_sec,
            "portfolio": portfolio,
            "reasons_log": reasons_log or [],
            "kill": kill,
            "trades_today": trades_today,
            "pnl_today": pnl_today,
        }
        tmp = _STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str))
        tmp.replace(_STATE)
    except Exception:
        pass


# Phase 8o.3c: per-symbol RICH state (23-field superset)
def tick_symbol(*, symbol, ltp=None, state="idle", state_reason="",
                position=None, trades_today=0, pnl_today=0.0,
                kill=False, max_lots=1, lot_size=15, reasons_log=None,
                z=None, mean=None, std=None, window=40,
                z_entry=1.5, z_stop=3.5, candles_count=0,
                intraday_candles=None, depth=None, ohlc_today=None,
                next_check_in_sec=None, portfolio=None):
    """Write state/live_{symbol}.json with full rich data (8o.3c)."""
    try:
        path = _STATE.parent / f"live_{symbol}.json"
        data = {
            "symbol": symbol,
            "updated_at": datetime.now(_IST).isoformat(),
            "updated_ts": int(time.time()),
            "ltp": ltp,
            "z": z, "mean": mean, "std": std,
            "window": window, "z_entry": z_entry, "z_stop": z_stop,
            "candles_count": candles_count,
            "intraday_candles": intraday_candles or [],
            "state": state, "state_reason": state_reason,
            "position": position, "depth": depth,
            "ohlc_today": ohlc_today,
            "next_check_in_sec": next_check_in_sec,
            "portfolio": portfolio,
            "trades_today": trades_today,
            "pnl_today": pnl_today,
            "kill": kill,
            "max_lots": max_lots,
            "lot_size": lot_size,
            "reasons_log": reasons_log or [],
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str))
        tmp.replace(path)
        _maybe_emit_heartbeat_p97t(data)
    except Exception:
        pass
