"""Phase 9.8g.11 (Fix B): tests for symbol-specific TOD entry cutoff.

The helper is intentionally disabled when the env var is unset / "0000" /
unrecognized symbol, so the default behaviour matches pre-Fix-B (no skip).
Opt-in via OU_<SHORT>_AFTERNOON_CUTOFF_HHMM env var (e.g. "1330" = block
entries at and after 13:30 IST).
"""
import pandas as pd
import pytest

from strategy import is_entry_blocked_by_tod


class _Bar:
    """Minimal stand-in for pd.Timestamp / datetime with .hour and .minute."""

    def __init__(self, h: int, m: int):
        self.hour = h
        self.minute = m


@pytest.fixture(autouse=True)
def _clear_tod_env(monkeypatch):
    for k in (
        "OU_NF_AFTERNOON_CUTOFF_HHMM",
        "OU_BNF_AFTERNOON_CUTOFF_HHMM",
        "OU_MCN_AFTERNOON_CUTOFF_HHMM",
        "OU_FOO_AFTERNOON_CUTOFF_HHMM",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def test_disabled_by_default():
    # No env var set -> always returns False even deep in the afternoon
    assert is_entry_blocked_by_tod("NIFTY", _Bar(14, 30)) is False
    assert is_entry_blocked_by_tod("BANKNIFTY", _Bar(14, 30)) is False
    assert is_entry_blocked_by_tod("MIDCPNIFTY", _Bar(14, 30)) is False


def test_nf_cutoff_blocks_at_and_after_threshold(monkeypatch):
    monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", "1330")
    # Before cutoff: allow
    assert is_entry_blocked_by_tod("NIFTY", _Bar(9, 30)) is False
    assert is_entry_blocked_by_tod("NIFTY", _Bar(11, 0)) is False
    assert is_entry_blocked_by_tod("NIFTY", _Bar(13, 29)) is False
    # At cutoff (>= semantics): block
    assert is_entry_blocked_by_tod("NIFTY", _Bar(13, 30)) is True
    # After cutoff: block
    assert is_entry_blocked_by_tod("NIFTY", _Bar(13, 45)) is True
    assert is_entry_blocked_by_tod("NIFTY", _Bar(14, 30)) is True


def test_short_form_symbol_matches(monkeypatch):
    """Live runner uses INSTRUMENT_CFG short keys (BNF/NF/MCN)."""
    monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", "1330")
    assert is_entry_blocked_by_tod("NF", _Bar(13, 30)) is True
    assert is_entry_blocked_by_tod("NF", _Bar(13, 29)) is False
    assert is_entry_blocked_by_tod("nf", _Bar(13, 30)) is True  # case-insensitive


def test_cutoff_is_symbol_specific(monkeypatch):
    # Only NF cutoff set; BNF and MCN afternoon entries must still be allowed.
    # This is the whole point of Fix B per 9.8g.10 TOD analysis.
    monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", "1330")
    assert is_entry_blocked_by_tod("BANKNIFTY", _Bar(14, 0)) is False
    assert is_entry_blocked_by_tod("MIDCPNIFTY", _Bar(14, 0)) is False
    assert is_entry_blocked_by_tod("NIFTY", _Bar(14, 0)) is True


def test_zero_value_disables(monkeypatch):
    monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", "0000")
    assert is_entry_blocked_by_tod("NIFTY", _Bar(14, 30)) is False


def test_empty_value_disables(monkeypatch):
    monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", "")
    assert is_entry_blocked_by_tod("NIFTY", _Bar(14, 30)) is False


def test_invalid_value_disables(monkeypatch):
    # "abc" -> int() fails; "9999" -> h=99 out-of-range; "2570" -> m=70 out-of-range
    for v in ("abc", "9999", "2570", "-130"):
        monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", v)
        assert is_entry_blocked_by_tod("NIFTY", _Bar(14, 30)) is False


def test_unknown_symbol_disables(monkeypatch):
    monkeypatch.setenv("OU_FOO_AFTERNOON_CUTOFF_HHMM", "1330")
    assert is_entry_blocked_by_tod("FOO", _Bar(14, 30)) is False


def test_none_inputs_disabled():
    assert is_entry_blocked_by_tod(None, _Bar(14, 30)) is False
    assert is_entry_blocked_by_tod("NIFTY", None) is False
    assert is_entry_blocked_by_tod(None, None) is False


def test_pd_timestamp_input(monkeypatch):
    monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", "1330")
    assert is_entry_blocked_by_tod("NIFTY", pd.Timestamp("2026-05-25 13:29")) is False
    assert is_entry_blocked_by_tod("NIFTY", pd.Timestamp("2026-05-25 13:30")) is True
    assert is_entry_blocked_by_tod("NIFTY", pd.Timestamp("2026-05-25 14:30")) is True


def test_bnf_cutoff_independent(monkeypatch):
    """BNF env key works the same way if a user opts in for a BNF cutoff."""
    monkeypatch.setenv("OU_BNF_AFTERNOON_CUTOFF_HHMM", "1400")
    assert is_entry_blocked_by_tod("BANKNIFTY", _Bar(13, 59)) is False
    assert is_entry_blocked_by_tod("BANKNIFTY", _Bar(14, 0)) is True
    # NF unaffected because its env is not set
    assert is_entry_blocked_by_tod("NIFTY", _Bar(14, 0)) is False


def test_morning_cutoff_also_works(monkeypatch):
    """Helper is generic; afternoon-naming is conventional, not enforced.
    A 9:45 cutoff would block all entries after 09:45 if set."""
    monkeypatch.setenv("OU_NF_AFTERNOON_CUTOFF_HHMM", "0945")
    assert is_entry_blocked_by_tod("NIFTY", _Bar(9, 44)) is False
    assert is_entry_blocked_by_tod("NIFTY", _Bar(9, 45)) is True
    assert is_entry_blocked_by_tod("NIFTY", _Bar(10, 0)) is True
