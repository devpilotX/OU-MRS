"""Phase 8f.2: per-account state isolation."""
import os
from pathlib import Path

ACCOUNT_ID = os.environ.get("ACCOUNT_ID", "primary")


def state_dir(account_id=None):
    aid = account_id or ACCOUNT_ID
    p = Path("state") / aid
    p.mkdir(parents=True, exist_ok=True)
    return p


def equity_log_path(account_id=None):
    return state_dir(account_id) / "equity.jsonl"


def sl_orders_log_path(account_id=None):
    return state_dir(account_id) / "sl_orders.jsonl"
