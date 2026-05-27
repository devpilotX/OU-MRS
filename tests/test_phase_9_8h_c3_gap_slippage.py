"""Phase 9.8h.C.3: intra-bar gap-risk slippage on STOP-class exits.

Locks the contract of estimate_gap_slippage_ticks() and verifies backtest.py
wires it into the exit fill site.
"""
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cost_model  # noqa: E402


def _v2_on(mp, **extras):
    mp.setenv("OU_COST_MODEL_V2", "on")
    for k, v in extras.items():
        mp.setenv(k, v)


def test_1_v2_off_returns_zero(monkeypatch):
    """Legacy mode never applies the C.3 surcharge."""
    monkeypatch.delenv("OU_COST_MODEL_V2", raising=False)
    assert cost_model.estimate_gap_slippage_ticks(300.0, 100.0, "STOP") == 0.0
    assert cost_model.estimate_gap_slippage_ticks(10000.0, 1.0, "STOP") == 0.0


def test_2_narrow_bar_no_surcharge(monkeypatch):
    """bar_range/atr below the default 1.5 threshold -> 0."""
    _v2_on(monkeypatch)
    assert cost_model.estimate_gap_slippage_ticks(50.0, 100.0, "STOP") == 0.0
    # ratio == threshold exactly -> still 0 (strict >).
    assert cost_model.estimate_gap_slippage_ticks(150.0, 100.0, "STOP") == 0.0


def test_3_wide_bar_stop_gets_surcharge(monkeypatch):
    """range/atr = 3.0 -> excess 1.5 -> 1.5 ticks at default slope."""
    _v2_on(monkeypatch)
    assert cost_model.estimate_gap_slippage_ticks(300.0, 100.0, "STOP") == 1.5
    # range/atr = 2.0 -> excess 0.5 -> 0.5 ticks.
    assert cost_model.estimate_gap_slippage_ticks(200.0, 100.0, "STOP") == 0.5


def test_4_all_stop_class_reasons_get_surcharge(monkeypatch):
    """Every market-exit reason carries gap risk."""
    _v2_on(monkeypatch)
    for reason in ("STOP", "PAPER_SL", "BE_RATCHET", "TIME_STOP_HL", "Z_VEL_STALL", "TRAIL_STOP"):
        v = cost_model.estimate_gap_slippage_ticks(300.0, 100.0, reason)
        assert v == 1.5, f"reason={reason} got {v}"


def test_5_target_limit_exempt(monkeypatch):
    """TARGET (limit TP) exits do NOT cross the spread - zero gap surcharge."""
    _v2_on(monkeypatch)
    assert cost_model.estimate_gap_slippage_ticks(300.0, 100.0, "TARGET") == 0.0
    assert cost_model.estimate_gap_slippage_ticks(10000.0, 1.0, "TARGET") == 0.0


def test_6_unknown_reason_exempt(monkeypatch):
    """Unknown / None reasons -> 0 (conservative: only known STOP-class pays)."""
    _v2_on(monkeypatch)
    assert cost_model.estimate_gap_slippage_ticks(300.0, 100.0, None) == 0.0
    assert cost_model.estimate_gap_slippage_ticks(300.0, 100.0, "") == 0.0
    assert cost_model.estimate_gap_slippage_ticks(300.0, 100.0, "FOO") == 0.0


def test_7_invalid_inputs_return_zero(monkeypatch):
    """Missing/non-positive atr or bar_range -> 0, no crash."""
    _v2_on(monkeypatch)
    assert cost_model.estimate_gap_slippage_ticks(None, 100.0, "STOP") == 0.0
    assert cost_model.estimate_gap_slippage_ticks(300.0, None, "STOP") == 0.0
    assert cost_model.estimate_gap_slippage_ticks(300.0, 0.0, "STOP") == 0.0
    assert cost_model.estimate_gap_slippage_ticks(0.0, 100.0, "STOP") == 0.0
    assert cost_model.estimate_gap_slippage_ticks(-1.0, 100.0, "STOP") == 0.0
    assert cost_model.estimate_gap_slippage_ticks("oops", 100.0, "STOP") == 0.0


def test_8_threshold_and_slope_env_configurable(monkeypatch):
    """OU_GAP_THRESHOLD_ATR and OU_GAP_PENALTY_SLOPE shift behavior."""
    _v2_on(monkeypatch, OU_GAP_THRESHOLD_ATR="1.0", OU_GAP_PENALTY_SLOPE="2.0")
    # range/atr = 2.0 -> excess 1.0 -> 2.0 ticks.
    assert cost_model.estimate_gap_slippage_ticks(200.0, 100.0, "STOP") == 2.0
    # range/atr = 1.5 -> excess 0.5 -> 1.0 tick.
    assert cost_model.estimate_gap_slippage_ticks(150.0, 100.0, "STOP") == 1.0


def test_9_always_non_negative(monkeypatch):
    """Surcharge invariant: never negative regardless of inputs."""
    _v2_on(monkeypatch)
    for r in (None, "STOP", "PAPER_SL", "TARGET", "FOO"):
        for br in (None, 0.0, 50.0, 1000.0):
            for atr in (None, 0.0, 100.0, 1.0):
                v = cost_model.estimate_gap_slippage_ticks(br, atr, r)
                assert v >= 0.0


def test_10_backtest_wires_gap_slippage():
    """Regression: backtest._close must compute _gap_ticks_c3 and add it."""
    src = (ROOT / "backtest.py").read_text()
    assert "estimate_gap_slippage_ticks" in src
    assert "_gap_ticks_c3" in src
    assert "_total_slip_ticks = _slip_ticks_c2 + _gap_ticks_c3" in src
    # Both C.2 and C.3 must compose - C.2 was per-symbol+size, C.3 is gap.
    assert "_slip_ticks_c2" in src


def test_11_constants_exported():
    """STOP_CLASS_EXIT_REASONS and LIMIT_TP_EXIT_REASONS are public sets."""
    assert "STOP" in cost_model.STOP_CLASS_EXIT_REASONS
    assert "PAPER_SL" in cost_model.STOP_CLASS_EXIT_REASONS
    assert "TRAIL_STOP" in cost_model.STOP_CLASS_EXIT_REASONS
    assert "TARGET" in cost_model.LIMIT_TP_EXIT_REASONS
    assert "TARGET" not in cost_model.STOP_CLASS_EXIT_REASONS
    assert "STOP" not in cost_model.LIMIT_TP_EXIT_REASONS


def test_12_compose_with_c2_slippage(monkeypatch):
    """Integration check: a violent STOP bar combines C.2 + C.3 surcharges.

    Caller computes (estimate_slippage_ticks + estimate_gap_slippage_ticks)
    and multiplies by TICK. This test locks that both pieces produce expected
    floats so the sum is well-defined.
    """
    _v2_on(monkeypatch)
    c2 = cost_model.estimate_slippage_ticks("BANKNIFTY", 1, rv20=0.005)
    c3 = cost_model.estimate_gap_slippage_ticks(300.0, 100.0, "STOP")
    assert c2 + c3 == pytest.approx(3.5, abs=1e-9)  # 2.0 + 1.5
    # TARGET adds nothing.
    c3_t = cost_model.estimate_gap_slippage_ticks(300.0, 100.0, "TARGET")
    assert c2 + c3_t == pytest.approx(2.0, abs=1e-9)
