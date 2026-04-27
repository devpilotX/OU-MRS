"""Phase 8f.5: Tradetron-compatible signal feed publisher."""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from account import state_dir, ACCOUNT_ID

IST = timezone(timedelta(hours=5, minutes=30))
VERSION = "1.0"
STRATEGY = "OU-MRS"
INSTRUMENT = os.environ.get("INSTRUMENT_SYMBOL", "BANKNIFTY26MAY26FUT")
EXCHANGE = os.environ.get("INSTRUMENT_EXCHANGE", "NFO")


def signals_path(account_id=None):
    return state_dir(account_id) / "signals.json"


def _ist_now():
    return datetime.now(IST).isoformat(timespec="seconds")


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)


def _flat_payload(account_id=None):
    return {
        "strategy": STRATEGY,
        "version": VERSION,
        "account": account_id or ACCOUNT_ID,
        "instrument": INSTRUMENT,
        "exchange": EXCHANGE,
        "signal": "FLAT",
        "qty": 0,
        "entry_price": None,
        "entry_time": None,
        "stop_loss": None,
        "current_pnl": 0.0,
        "last_update": _ist_now(),
    }


def publish_flat(account_id=None):
    _atomic_write(signals_path(account_id), _flat_payload(account_id))


def publish_entry(side, qty_lots, lot_size, entry_price, entry_time, stop_loss, account_id=None):
    side_map = {"BUY": "LONG", "SELL": "SHORT"}
    payload = {
        "strategy": STRATEGY,
        "version": VERSION,
        "account": account_id or ACCOUNT_ID,
        "instrument": INSTRUMENT,
        "exchange": EXCHANGE,
        "signal": side_map.get(str(side).upper(), "FLAT"),
        "qty": int(qty_lots) * int(lot_size),
        "entry_price": float(entry_price),
        "entry_time": str(entry_time),
        "stop_loss": float(stop_loss),
        "current_pnl": 0.0,
        "last_update": _ist_now(),
    }
    _atomic_write(signals_path(account_id), payload)


def publish_exit(realized_pnl=None, account_id=None):
    payload = _flat_payload(account_id)
    if realized_pnl is not None:
        payload["last_realized_pnl"] = float(realized_pnl)
    _atomic_write(signals_path(account_id), payload)


def heartbeat(current_pnl, account_id=None):
    sp = signals_path(account_id)
    if not sp.exists():
        return
    try:
        data = json.loads(sp.read_text())
        if data.get("signal") != "FLAT":
            data["current_pnl"] = float(current_pnl)
        data["last_update"] = _ist_now()
        _atomic_write(sp, data)
    except Exception:
        pass


def read_signal(account_id=None):
    sp = signals_path(account_id)
    if not sp.exists():
        return _flat_payload(account_id)
    try:
        return json.loads(sp.read_text())
    except Exception:
        return _flat_payload(account_id)
