"""Dashboard live-data bridge. Never crashes the bot."""
import json, time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

_STATE = Path(__file__).parent / "state" / "live.json"
_STATE.parent.mkdir(exist_ok=True)
_IST = ZoneInfo("Asia/Kolkata")

def tick(*, ltp=None, z=None, mean=None, std=None, window=40,
         z_entry=1.5, z_stop=3.5, candles_count=0, intraday_candles=None,
         state="idle", state_reason="", position=None, depth=None,
         ohlc_today=None, next_check_in_sec=None):
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
        }
        tmp = _STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str))
        tmp.replace(_STATE)
    except Exception:
        pass  # never break the bot
