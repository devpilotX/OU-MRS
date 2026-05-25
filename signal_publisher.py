"""Phase 8f.5: Tradetron-compatible signal feed publisher.

Phase 9.8g.3 (25 May 2026 audit B4): per-symbol routing.
Every publisher now accepts `symbol=` (and optional instrument_symbol /
exchange overrides). When `symbol` is provided the writer targets
signals_<symbol>.json (lowercased) instead of the legacy signals.json,
so BNF / NF / MCN no longer overwrite each other in a multi-instrument
run. No kwargs = legacy single-symbol behavior unchanged.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from account import state_dir, ACCOUNT_ID

IST = timezone(timedelta(hours=5, minutes=30))
VERSION = "1.0"
STRATEGY = "OU-MRS"
# Legacy single-symbol defaults (used when caller passes no symbol kwarg)
INSTRUMENT = os.environ.get("INSTRUMENT_SYMBOL", "BANKNIFTY26MAY26FUT")
EXCHANGE   = os.environ.get("INSTRUMENT_EXCHANGE", "NFO")


def signals_path(account_id=None, symbol=None):
    """Phase 9.8g.3: when symbol is set, route to signals_<symbol>.json.
    Backwards-compatible: no symbol => legacy signals.json.
    """
    if symbol:
        return state_dir(account_id) / f"signals_{str(symbol).lower()}.json"
    return state_dir(account_id) / "signals.json"


def _ist_now():
    return datetime.now(IST).isoformat(timespec="seconds")


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)


def _resolve_instrument(instrument_symbol=None, exchange=None):
    """Phase 9.8g.3: per-call instrument/exchange overrides, falling back
    to module-level legacy defaults.
    """
    inst = instrument_symbol if instrument_symbol else INSTRUMENT
    exch = exchange if exchange else EXCHANGE
    return inst, exch


def _flat_payload(account_id=None, symbol=None, instrument_symbol=None, exchange=None):
    inst, exch = _resolve_instrument(instrument_symbol, exchange)
    payload = {
        "strategy": STRATEGY,
        "version": VERSION,
        "account": account_id or ACCOUNT_ID,
        "instrument": inst,
        "exchange": exch,
        "signal": "FLAT",
        "qty": 0,
        "entry_price": None,
        "entry_time": None,
        "stop_loss": None,
        "current_pnl": 0.0,
        "last_update": _ist_now(),
    }
    if symbol:
        payload["symbol"] = str(symbol)
    return payload


def publish_flat(account_id=None, symbol=None, instrument_symbol=None, exchange=None):
    _atomic_write(
        signals_path(account_id, symbol=symbol),
        _flat_payload(account_id, symbol=symbol, instrument_symbol=instrument_symbol, exchange=exchange),
    )


def publish_entry(side, qty_lots, lot_size, entry_price, entry_time, stop_loss,
                  account_id=None, symbol=None, instrument_symbol=None, exchange=None):
    side_map = {"BUY": "LONG", "SELL": "SHORT"}
    inst, exch = _resolve_instrument(instrument_symbol, exchange)
    payload = {
        "strategy": STRATEGY,
        "version": VERSION,
        "account": account_id or ACCOUNT_ID,
        "instrument": inst,
        "exchange": exch,
        "signal": side_map.get(str(side).upper(), "FLAT"),
        "qty": int(qty_lots) * int(lot_size),
        "entry_price": float(entry_price),
        "entry_time": str(entry_time),
        "stop_loss": float(stop_loss),
        "current_pnl": 0.0,
        "last_update": _ist_now(),
    }
    if symbol:
        payload["symbol"] = str(symbol)
    _atomic_write(signals_path(account_id, symbol=symbol), payload)


def publish_exit(realized_pnl=None, account_id=None, symbol=None,
                 instrument_symbol=None, exchange=None):
    payload = _flat_payload(account_id, symbol=symbol,
                            instrument_symbol=instrument_symbol, exchange=exchange)
    if realized_pnl is not None:
        payload["last_realized_pnl"] = float(realized_pnl)
    _atomic_write(signals_path(account_id, symbol=symbol), payload)


def heartbeat(current_pnl, account_id=None, symbol=None):
    sp = signals_path(account_id, symbol=symbol)
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


def read_signal(account_id=None, symbol=None):
    sp = signals_path(account_id, symbol=symbol)
    if not sp.exists():
        return _flat_payload(account_id, symbol=symbol)
    try:
        return json.loads(sp.read_text())
    except Exception:
        return _flat_payload(account_id, symbol=symbol)
