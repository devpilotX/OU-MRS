"""Phase A12 latency observability for OU-MRS.

Records per-operation timing into a thread-safe accumulator.
Periodic flush emits aggregated stats at INFO every 60s.
Slow operations (>1000ms) alert immediately at WARNING.
"""
import time
import threading
import logging
from collections import defaultdict
from contextlib import contextmanager

log = logging.getLogger("latency")
_lock = threading.Lock()
_buckets = defaultdict(list)
_last_flush = time.time()

FLUSH_INTERVAL_SEC = 60.0
SLOW_THRESHOLD_MS = 1000.0
MAX_SAMPLES_PER_OP = 1000


@contextmanager
def Timer(name):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        with _lock:
            buf = _buckets[name]
            buf.append(dt_ms)
            if len(buf) > MAX_SAMPLES_PER_OP:
                del buf[: len(buf) - MAX_SAMPLES_PER_OP]
        if dt_ms > SLOW_THRESHOLD_MS:
            log.warning(f"slow {name}: {dt_ms:.1f}ms")


def flush_if_due():
    global _last_flush
    now = time.time()
    if now - _last_flush < FLUSH_INTERVAL_SEC:
        return
    with _lock:
        snapshot = {k: list(v) for k, v in _buckets.items() if v}
        _buckets.clear()
        _last_flush = now
    if not snapshot:
        return
    for name in sorted(snapshot.keys()):
        samples = snapshot[name]
        samples.sort()
        n = len(samples)
        p50 = samples[n // 2]
        p95 = samples[min(n - 1, int(n * 0.95))]
        p99 = samples[min(n - 1, int(n * 0.99))]
        mx = samples[-1]
        mean = sum(samples) / n
        log.info(f"latency[{name}] n={n} mean={mean:.1f} p50={p50:.1f} p95={p95:.1f} p99={p99:.1f} max={mx:.1f} ms")


def reset():
    global _last_flush
    with _lock:
        _buckets.clear()
        _last_flush = time.time()
