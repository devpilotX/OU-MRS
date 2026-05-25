"""Phase 8f.4: tearsheet tests.

Phase 9.8g.9 (25 May 2026 audit Track 1): bt_out-dependent tests now
skip when the bt_out/ directory is empty (e.g. fresh CI checkout).
They remain useful smoke tests for the report builder, but are not
part of the PR #3 merge gate (which is the standalone backtest run).
"""
from pathlib import Path
import pytest
import tearsheet


def test_tier_thresholds():
    assert tearsheet._tier(100_000) == "SEED"
    assert tearsheet._tier(1_000_000) == "GROWTH"
    assert tearsheet._tier(2_000_000) == "INSTITUTIONAL"
    assert tearsheet._tier(3_000_000) == "HEDGE_FUND"
    assert tearsheet._tier(10_000_000) == "QUANT_ELITE"


def test_inr_formatting():
    assert "Cr" in tearsheet._inr(15_000_000)
    assert "L" in tearsheet._inr(500_000)
    assert "Rs" in tearsheet._inr(50_000)
    assert tearsheet._inr(None) == "\u2014"
    assert tearsheet._inr(float("nan")) == "\u2014"
    assert tearsheet._inr(-50_000).startswith("-")


def test_pct_formatting():
    assert tearsheet._pct(15.92) == "15.92%"
    assert tearsheet._pct(15.92, sign=True) == "+15.92%"
    assert tearsheet._pct(-2.13, sign=True) == "-2.13%"
    assert tearsheet._pct(None) == "\u2014"


_REPO_ROOT = Path(__file__).resolve().parent.parent
_BT_OUT_READY = (_REPO_ROOT / "bt_out" / "metrics.json").exists() and (_REPO_ROOT / "bt_out" / "trades.csv").exists()


@pytest.mark.skipif(not _BT_OUT_READY, reason="bt_out/ not populated; run backtest.py first")
def test_load_results_from_bt_out():
    edf, tdf, metrics = tearsheet._load("bt_out")
    assert not edf.empty
    assert not tdf.empty
    assert "trades" in metrics
    assert metrics["trades"] >= 1


@pytest.mark.skipif(not _BT_OUT_READY, reason="bt_out/ not populated; run backtest.py first")
def test_generate_tearsheet_creates_valid_pdf(tmp_path):
    out = tmp_path / "test_tearsheet.pdf"
    p = tearsheet.generate_tearsheet("bt_out", str(out))
    assert p.exists()
    assert p.stat().st_size > 5000
    with open(p, "rb") as f:
        assert f.read(4) == b"%PDF"
