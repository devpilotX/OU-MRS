"""Phase 9.8h.B.3 regression tests.

Guard the defensive try/except wrapping around the trades.jsonl write and the
CRITICAL log payload on write failure. The May 12 13:19 NIFTY trade (+Rs32164)
was silently lost because the prior unwrapped open() block swallowed an I/O
exception with no operator-visible signal. These tests prevent silent regression
of the hardening.
"""
import ast
import re
from pathlib import Path

import pytest

OU_MRS = Path(__file__).resolve().parents[1] / "ou_mrs.py"
TRADES = Path(__file__).resolve().parents[1] / "trades.jsonl"


def _exit_src() -> str:
    """Return the source of the module-level `_exit` function."""
    src = OU_MRS.read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_exit":
            start = node.lineno - 1
            end = node.end_lineno
            return "\n".join(src.splitlines()[start:end])
    pytest.fail("_exit not found")


def test_trades_jsonl_write_is_wrapped_in_try_except():
    """The open(TRADES_PATH, 'a') block must live inside a try/except so any
    I/O failure is logged loudly rather than silently lost."""
    body = _exit_src()
    # The write block must appear inside a try: ... except clause.
    assert re.search(r"try:\s*\n\s*with open\(TRADES_PATH,\s*\"a\"\)", body), (
        "The `with open(TRADES_PATH, 'a') as f:` block in _exit must be "
        "wrapped in `try:` (Phase 9.8h.B.3 hardening)."
    )
    assert re.search(r"except Exception as", body), (
        "_exit must have an `except Exception as ...:` clause around the "
        "trades.jsonl write (Phase 9.8h.B.3 hardening)."
    )


def test_trade_write_failure_logs_critical_with_full_payload():
    """On write failure, the except branch must log.critical with the full row
    payload (entry/exit/qty/pnl/reason/symbol) so an operator can backfill from
    the log alone, exactly as we did for the May 12 trade."""
    body = _exit_src()
    assert "log.critical" in body, (
        "_exit must log at CRITICAL level on trades.jsonl write failure "
        "(Phase 9.8h.B.3): WARNING is too quiet, ERROR is ambiguous."
    )
    assert "LEDGER-DESYNC" in body, (
        "_exit critical log must include the `[LEDGER-DESYNC]` tag for "
        "greppability (Phase 9.8h.B.3)."
    )
    assert "ROW_PAYLOAD" in body, (
        "_exit critical log must include the full row payload as ROW_PAYLOAD=... "
        "so the lost trade can be backfilled from the log alone (Phase 9.8h.B.3)."
    )


def test_may12_1319_nifty_trade_is_present_in_trades_jsonl():
    """Phase 9.8h.B.3 backfill: the May 12 13:19 NIFTY trade (+Rs32164) was
    silently lost from trades.jsonl and reconstructed from the log archive.
    Guard against accidental deletion during future ledger edits."""
    if not TRADES.exists():
        pytest.skip("trades.jsonl not present in test env")
    import json as _json
    rows = [_json.loads(l) for l in TRADES.read_text().splitlines() if l.strip()]
    match = [
        r for r in rows
        if r.get("entry_ts") == "2026-05-12 13:19:00+05:30"
        and r.get("exit_ts") == "2026-05-12 13:30:00+05:30"
    ]
    assert len(match) == 1, (
        f"Expected exactly one backfilled May 12 13:19 NIFTY row in trades.jsonl, "
        f"got {len(match)}. Do not delete the backfilled row without rebuilding "
        f"P&L reconciliation (Phase 9.8h.B.3)."
    )
    r = match[0]
    assert r["side"] == "SELL" and r["qty"] == 36
    assert r["entry"] == 23597.30 and r["exit"] == 23579.00
    assert r["symbol"] == "NF"
    assert r.get("backfilled") == "phase-9.8h.B.3"
