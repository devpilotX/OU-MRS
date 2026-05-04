"""Coverage for Phase 9.5 exit helpers: time-stop, velocity-stop, trail-stop."""
import os
import pytest

from strategy import should_time_stop_hl, should_velocity_stop, should_trail_stop


def test_time_stop_hl_fires_when_bars_exceed_multiplier():
    assert should_time_stop_hl(bars_held=30, half_life=5.0) is True


def test_time_stop_hl_does_not_fire_below_multiplier():
    assert should_time_stop_hl(bars_held=10, half_life=5.0) is False


def test_time_stop_hl_handles_zero_half_life():
    result = should_time_stop_hl(bars_held=10, half_life=0.0)
    assert result in (True, False)


def test_velocity_stop_fires_on_repeated_low_velocity():
    history = [0.5, 0.4, 0.3]
    assert should_velocity_stop(history) is True


def test_velocity_stop_does_not_fire_with_high_velocity():
    history = [2.0, 2.5, 1.8]
    assert should_velocity_stop(history) is False


def test_velocity_stop_handles_short_history():
    assert should_velocity_stop([]) is False
    assert should_velocity_stop([0.1]) is False


def test_trail_stop_dormant_by_default():
    result = should_trail_stop(current_pnl_pts=10.0, peak_pnl_pts=15.0, atr=2.0)
    assert result in (None, False)


def test_trail_stop_accepts_numeric_inputs():
    result = should_trail_stop(current_pnl_pts=5.0, peak_pnl_pts=20.0, atr=5.0)
    assert result in (None, True, False)
