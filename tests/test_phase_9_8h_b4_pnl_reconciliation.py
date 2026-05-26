"""Phase 9.8h.B.4 regression: P&L reconciliation across the three sources.

Guards against silent equity.jsonl divergence from trades.jsonl. Imports the
verify_pnl_reconciliation tool and asserts in_sync=True on the committed state.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_tool(name: str):
    p = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_tool_present_and_runnable():
    """verify_pnl_reconciliation.py must exist and expose verify()."""
    p = ROOT / "tools" / "verify_pnl_reconciliation.py"
    assert p.exists(), "tools/verify_pnl_reconciliation.py is missing"
    mod = _load_tool("verify_pnl_reconciliation")
    assert callable(getattr(mod, "verify", None)), "verify() must be a callable"


def test_rebuild_tool_present_and_idempotent():
    """rebuild_equity_from_trades.py must exist and be a no-op on synced state."""
    p = ROOT / "tools" / "rebuild_equity_from_trades.py"
    assert p.exists(), "tools/rebuild_equity_from_trades.py is missing"
    mod = _load_tool("rebuild_equity_from_trades")
    assert callable(getattr(mod, "rebuild", None)), "rebuild() must be a callable"
    # Dry-run on the live state. Post-B.4 it should report zero edits.
    if not (ROOT / "trades.jsonl").exists() or not (ROOT / "state/primary/equity.jsonl").exists():
        return  # CI environment may not ship runtime state
    res = mod.rebuild(dry_run=True, backup=False)
    assert res["edits"] == [], f"equity.jsonl out of sync with trades.jsonl: {res['edits']}"


def test_pnl_three_way_reconciliation():
    """trades.jsonl sum, equity.jsonl last cumulative, and pfm.cumulative_pnl must agree."""
    if not (ROOT / "trades.jsonl").exists() or not (ROOT / "state/primary/equity.jsonl").exists() or not (ROOT / "state/pfm.json").exists():
        return  # CI environment may not ship runtime state
    mod = _load_tool("verify_pnl_reconciliation")
    res = mod.verify()
    assert res["in_sync"], (
        f"P&L reconciliation FAILED: {res['issues']}\n"
        f"trades_sum=Rs{res['trades_sum']:,.2f} equity_sum=Rs{res['equity_sum']:,.2f} "
        f"equity_last_cum=Rs{res['equity_last_cumulative']:,.2f} pfm_cum=Rs{res['pfm_cumulative']:,.2f}"
    )
