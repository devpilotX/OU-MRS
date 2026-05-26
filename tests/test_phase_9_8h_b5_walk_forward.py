"""Phase 9.8h.B.5 - lock the walk-forward / slippage / vol-regime findings.

These tests are regression locks: if a future change moves the numbers, the
tests will fail loudly. They do NOT re-run the backtest (too slow for CI);
they assert the SHAPE and SIGN of the recorded results.
"""
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "validation"


def _load(name: str):
    p = VAL / name
    if not p.exists():
        pytest.skip(f"missing {p} (run tools/slippage_sweep.py first)")
    return json.loads(p.read_text())


def test_slippage_sweep_shape():
    """Slippage sweep must cover the documented 4-level x 3-symbol matrix."""
    rows = _load("phase_9_8h_B_5_slippage_sweep.json")
    levels = sorted({r["slippage_ticks"] for r in rows if "slippage_ticks" in r})
    symbols = sorted({r["symbol"] for r in rows if "symbol" in r})
    assert levels == [2, 5, 10, 20], f"unexpected slippage levels: {levels}"
    assert symbols == ["BANKNIFTY", "MIDCPNIFTY", "NIFTY"], f"unexpected symbols: {symbols}"
    assert len(rows) == 12, f"expected 12 cells, got {len(rows)}"


def test_slippage_monotonic_pnl_BANKNIFTY_MIDCPNIFTY():
    """Higher slippage must reduce P&L for symbols with a real edge (BNF, MCN)."""
    rows = _load("phase_9_8h_B_5_slippage_sweep.json")
    for sym in ("BANKNIFTY", "MIDCPNIFTY"):
        sym_rows = sorted(
            (r for r in rows if r.get("symbol") == sym and "total_pnl" in r),
            key=lambda r: r["slippage_ticks"],
        )
        pnls = [r["total_pnl"] for r in sym_rows]
        assert pnls == sorted(pnls, reverse=True), (
            f"{sym} P&L must be monotonically non-increasing in slippage; got {pnls}"
        )
        # Sanity: at the floor slippage the edge must be positive for these symbols.
        assert sym_rows[0]["total_pnl"] > 0, f"{sym} P&L should be positive at min slip"


def test_NIFTY_no_edge_at_any_slippage():
    """NIFTY must remain unprofitable across the entire slippage band.
    This is the B.5 finding that motivates disabling NF until re-tuned.
    """
    rows = _load("phase_9_8h_B_5_slippage_sweep.json")
    nf = [r for r in rows if r.get("symbol") == "NIFTY" and "total_pnl" in r]
    assert len(nf) == 4
    for r in nf:
        assert r["total_pnl"] < 0, (
            f"NIFTY P&L should be negative at slip={r['slippage_ticks']}; got {r['total_pnl']}"
        )
        assert r["profit_factor"] < 1.0, (
            f"NIFTY PF should be <1 at slip={r['slippage_ticks']}; got {r['profit_factor']}"
        )


def test_vol_regime_tercile_structure():
    """Vol-regime stratification must produce LOW/MID/HIGH buckets per symbol."""
    vol = _load("phase_9_8h_B_5_vol_regime.json")
    for sym in ("BANKNIFTY", "NIFTY", "MIDCPNIFTY"):
        assert sym in vol, f"missing {sym} in vol-regime report"
        buckets = vol[sym]["by_bucket"]
        assert set(buckets.keys()) <= {"LOW", "MID", "HIGH"}
        total_n = sum(b["n_trades"] for b in buckets.values())
        assert total_n == vol[sym]["n_trades_classified"]
        breaks = vol[sym]["rv20_tercile_breaks"]
        assert breaks[0] <= breaks[1], f"{sym} tercile breaks must be sorted: {breaks}"


def test_MIDCPNIFTY_low_vol_bucket_wins():
    """MCN LOW-vol bucket is the cleanest edge in the entire sweep.
    Win rate must be >= 80% per the B.5 finding (rationale for proposed vol gate).
    """
    vol = _load("phase_9_8h_B_5_vol_regime.json")
    mcn = vol["MIDCPNIFTY"]["by_bucket"]
    assert "LOW" in mcn
    assert mcn["LOW"]["win_rate"] >= 0.8, (
        f"MCN LOW-vol win rate should be >=80% per B.5; got {mcn['LOW']['win_rate']}"
    )
    assert mcn["LOW"]["mean_pnl"] > 0
