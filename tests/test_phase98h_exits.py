"""Phase 9.8h: pure-function tests for BE_RATCHET and PAPER_SL exit helpers.

All tests pass override params directly to the helpers (trigger_mult, lock_mult,
sl_mult) so no env-var manipulation or module reload is required. This keeps
test behavior deterministic and decoupled from the shell environment.
"""
from strategy import be_ratchet_armed, be_ratchet_hit, paper_sl_hit


# === BE ratchet armed ===

def test_be_ratchet_armed_below_trigger_returns_false():
    # peak 1.5 pts vs threshold 1.0*2.0=2.0 -> not armed
    assert be_ratchet_armed(peak_pnl_pts=1.5, atr=2.0, trigger_mult=1.0) is False


def test_be_ratchet_armed_above_trigger_returns_true():
    # peak 2.5 pts vs threshold 1.0*2.0=2.0 -> armed
    assert be_ratchet_armed(peak_pnl_pts=2.5, atr=2.0, trigger_mult=1.0) is True


def test_be_ratchet_armed_at_trigger_returns_true():
    # exact equality should arm (inclusive boundary)
    assert be_ratchet_armed(peak_pnl_pts=2.0, atr=2.0, trigger_mult=1.0) is True


def test_be_ratchet_armed_zero_atr_returns_false():
    assert be_ratchet_armed(peak_pnl_pts=10.0, atr=0.0, trigger_mult=1.0) is False


def test_be_ratchet_armed_zero_trigger_returns_false():
    # trigger_mult=0 disables the feature
    assert be_ratchet_armed(peak_pnl_pts=10.0, atr=2.0, trigger_mult=0.0) is False


# === BE ratchet hit ===

def test_be_ratchet_hit_not_armed_returns_false():
    # peak < trigger threshold -> never armed -> no hit even with deep loss
    assert be_ratchet_hit(current_pnl_pts=-5.0, peak_pnl_pts=1.0, atr=2.0,
                          trigger_mult=1.0, lock_mult=0.1) is False


def test_be_ratchet_hit_armed_above_lock_returns_false():
    # armed (peak 3.0 > 2.0), current 1.0 > lock floor 0.2 (=0.1*2.0)
    assert be_ratchet_hit(current_pnl_pts=1.0, peak_pnl_pts=3.0, atr=2.0,
                          trigger_mult=1.0, lock_mult=0.1) is False


def test_be_ratchet_hit_armed_at_lock_returns_true():
    # armed (peak 3.0), current = lock floor exactly
    assert be_ratchet_hit(current_pnl_pts=0.2, peak_pnl_pts=3.0, atr=2.0,
                          trigger_mult=1.0, lock_mult=0.1) is True


def test_be_ratchet_hit_armed_below_lock_returns_true():
    # armed, current went negative -> fires
    assert be_ratchet_hit(current_pnl_pts=-1.0, peak_pnl_pts=3.0, atr=2.0,
                          trigger_mult=1.0, lock_mult=0.1) is True


# === Paper SL ===

def test_paper_sl_long_above_stop_returns_false():
    # entry 100, ATR 2, mult 2 -> stop at 96. Adverse 97 > 96 -> no hit
    assert paper_sl_hit(adverse_px=97.0, entry_px=100.0, side="BUY",
                        atr=2.0, sl_mult=2.0) is False


def test_paper_sl_long_at_stop_returns_true():
    # adverse 96 == 96 -> hit (inclusive boundary)
    assert paper_sl_hit(adverse_px=96.0, entry_px=100.0, side="BUY",
                        atr=2.0, sl_mult=2.0) is True


def test_paper_sl_long_below_stop_returns_true():
    assert paper_sl_hit(adverse_px=95.0, entry_px=100.0, side="BUY",
                        atr=2.0, sl_mult=2.0) is True


def test_paper_sl_short_below_stop_returns_false():
    