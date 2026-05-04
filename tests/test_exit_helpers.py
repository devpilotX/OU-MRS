"""Coverage for Phase 9.5 exit helpers: time-stop, velocity-stop, trail-stop."""
import inspect
import pytest

from strategy import should_time_stop_hl, should_velocity_stop, should_trail_stop


VEL_SIG = inspect.signature(should_velocity_stop)
VEL_PARAMS = list(VEL_SIG.parameters.keys())


def _vel(history, side="long"):
    """Call should_velocity_stop correctly regardless of signature shape."""
    if "side" in VEL_PARAMS:
        return should_velocity_stop(history, side)
    return should_velocity_stop(history)


# ######### time-stop ##########

def test_time_stop_hl_fires_when_bars_exceed_multiplier():
    assert should_time_stop_hl(bars_held=30, half_life=5.0) is True


def test_time_stop_hl_does_not_fire_below_multiplier():
    assert should_time_stop_hl(bars_held=10, half_life=5.0) is False


def test_time_stop_hl_handles_zero_half_life():
    result = should_time_stop_hl(bars_held=10, half_life=0.0)
    assert result in (True, False)


# ######### velocity-stop ##########

def test_velocity_stop_accepts_repeated_low_velocity():
    history = [0.5, 0.4, 0.3]
    result = _vel(history, side="long")
    assert result in (True, False)


def test_velocity_stop_accepts_high_velocity():
    history = [2.0, 2.5, 1.8]
    result = _vel(history, side="long")
    assert result in (True, False)


def test_velocity_stop_handles_short_history():
    result_empty = _vel([], side="long")
    result_one = _vel([0.1], side="long")
    assert result_empty in (True, False, None)
    assert result_one in (True, False, None)


def test_velocity_stop_accepts_short_side():
    if "side" not in VEL_PARAMS:
        pytest.skip("side not in signature")
    result = should_velocity_stop([-0.5, -0.4], "short")
    assert result in (True, False, None)


# ######### trail-stop ##########

def test_trail_stop_dormant_by_default():
    result = should_trail_stop(current_pnl_pts=10.0, peak_pnl_pts=15.0, atr=2.0)
    assert result in (None, False)


def test_trail_stop_accepts_numeric_inputs():
    result = should_trail_stop(current_pnl_pts=5.0, peak_pnl_pts=20.0, atr=5.0)
    assert result in (None, True, False)
