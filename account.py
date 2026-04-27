"""Phase 8f.2: per-account state isolation. Phase 8g.3: per-symbol scoping."""
import os
from pathlib import Path

ACCOUNT_ID = os.environ.get("ACCOUNT_ID", "primary")


def state_dir(account_id=None, symbol=None):
    aid = account_id or ACCOUNT_ID
    p = Path("state") / aid
    if symbol:
        p = p / symbol
    p.mkdir(parents=True, exist_ok=True)
    return p


def equity_log_path(account_id=None):
    return state_dir(account_id) / "equity.jsonl"


def sl_orders_log_path(account_id=None, symbol=None):
    return state_dir(account_id, symbol) / "sl_orders.jsonl"
