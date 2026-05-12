"""Phase A12: unit tests for latency observability module."""
import time
import pytest
import latency


@pytest.fixture(autouse=True)
def _reset_latency():
    latency.reset()
    yield
    latency.reset()


def test_timer_accumulates_samples():
    with latency.Timer("acc_test"):
        time.sleep(0.001)
    with latency.Timer("acc_test"):
        time.sleep(0.001)
    assert "acc_test" in latency._buckets
    assert len(latency._buckets["acc_test"]) == 2
    for sample in latency._buckets["acc_test"]:
        assert sample > 0


def test_timer_isolates_by_name():
    with latency.Timer("op_a"):
        time.sleep(0.001)
    with latency.Timer("op_b"):
        time.sleep(0.001)
    assert len(latency._buckets["op_a"]) == 1
    assert len(latency._buckets["op_b"]) == 1


def test_flush_if_due_skipped_within_interval():
    with latency.Timer("skip_test"):
        time.sleep(0.001)
    # reset() set _last_flush=now, so flush should no-op
    latency.flush_if_due()
    assert "skip_test" in latency._buckets
    assert len(latency._buckets["skip_test"]) == 1


def test_flush_if_due_emits_after_interval(caplog):
    with latency.Timer("emit_test"):
        time.sleep(0.001)
    latency._last_flush = 0.0
    with caplog.at_level("INFO", logger="latency"):
        latency.flush_if_due()
    assert latency._buckets.get("emit_test", []) == []
    text = " ".join(r.message for r in caplog.records)
    assert "emit_test" in text
    assert "n=1" in text


def test_aggregation_percentiles(caplog):
    # Inject deterministic 1..100 ms samples
    latency._buckets["pct_test"] = [float(i) for i in range(1, 101)]
    latency._last_flush = 0.0
    with caplog.at_level("INFO", logger="latency"):
        latency.flush_if_due()
    text = " ".join(r.message for r in caplog.records)
    assert "pct_test" in text
    assert "n=100" in text
    # p50 = sorted_samples[n//2] = sorted_samples[50] = 51
    assert "p50=51" in text
    assert "max=100" in text


def test_slow_op_warns(monkeypatch, caplog):
    # Lower threshold so a 2ms op trips the warning without real 1s sleep
    monkeypatch.setattr(latency, "SLOW_THRESHOLD_MS", 0.5)
    with caplog.at_level("WARNING", logger="latency"):
        with latency.Timer("slow_test"):
            time.sleep(0.002)
    warning_text = " ".join(r.message for r in caplog.records if r.levelname == "WARNING")
    assert "slow slow_test" in warning_text


def test_max_samples_per_op_cap(monkeypatch):
    monkeypatch.setattr(latency, "MAX_SAMPLES_PER_OP", 50)
    for _ in range(75):
        with latency.Timer("cap_test"):
            pass
    assert len(latency._buckets["cap_test"]) <= 50


def test_reset_clears_state():
    with latency.Timer("clear_me"):
        time.sleep(0.001)
    assert "clear_me" in latency._buckets
    latency.reset()
    assert len(latency._buckets) == 0


def test_timer_does_not_swallow_exceptions():
    with pytest.raises(ValueError, match="propagate"):
        with latency.Timer("exc_test"):
            raise ValueError("propagate")
    # finally-block must still record sample
    assert "exc_test" in latency._buckets
    assert len(latency._buckets["exc_test"]) == 1
