"""
Phase 9.8f.52: Token-bucket rate limiter (Angel feature #16). Stdlib only.
"""
import time
import threading
from collections import defaultdict


class TokenBucket:
    def __init__(self, name, capacity, refill_rate):
        self.name = name
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()
        self.total_consumed = 0
        self.total_blocked = 0
        self.total_wait_time = 0.0
        self.total_429 = 0

    def refill_now(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    def consume(self, tokens=1.0, block=True, timeout=None):
        start = time.monotonic()
        deadline = (start + timeout) if timeout else None
        while True:
            with self.lock:
                self.refill_now()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    self.total_consumed += 1
                    self.total_wait_time += (time.monotonic() - start)
                    return True
                needed = tokens - self.tokens
                wait = needed / self.refill_rate if self.refill_rate > 0 else 1.0
            if not block:
                self.total_blocked += 1
                return False
            if deadline and (time.monotonic() + wait) > deadline:
                self.total_blocked += 1
                return False
            time.sleep(min(wait, 0.25))

    def try_consume(self, tokens=1.0):
        return self.consume(tokens=tokens, block=False)

    def state(self):
        with self.lock:
            self.refill_now()
            return {
                "name": self.name,
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
                "tokens_available": round(self.tokens, 3),
                "fill_pct": round(100 * self.tokens / self.capacity, 1) if self.capacity > 0 else 0,
                "total_consumed": self.total_consumed,
                "total_blocked": self.total_blocked,
                "total_429": self.total_429,
                "avg_wait_ms": round(1000 * self.total_wait_time / max(1, self.total_consumed), 2),
            }

    def record_429(self):
        with self.lock:
            self.tokens = 0
            self.total_429 += 1


IP_BUCKETS = defaultdict(dict)
IP_LOCK = threading.Lock()
GLOBAL_BUCKETS = {}
GLOBAL_LOCK = threading.Lock()


def get_bucket(name, capacity=10.0, refill_rate=10.0):
    with GLOBAL_LOCK:
        if name not in GLOBAL_BUCKETS:
            GLOBAL_BUCKETS[name] = TokenBucket(name, capacity, refill_rate)
        return GLOBAL_BUCKETS[name]


def get_ip_bucket(ip, scope, capacity, refill_rate):
    with IP_LOCK:
        if scope not in IP_BUCKETS[ip]:
            IP_BUCKETS[ip][scope] = TokenBucket(ip + ":" + scope, capacity, refill_rate)
        return IP_BUCKETS[ip][scope]


def all_stats():
    out = {"global": {}, "per_ip": {}}
    with GLOBAL_LOCK:
        for n, b in GLOBAL_BUCKETS.items():
            out["global"][n] = b.state()
    with IP_LOCK:
        for ip, buckets in IP_BUCKETS.items():
            out["per_ip"][ip] = {scope: b.state() for scope, b in buckets.items()}
    return out


get_bucket("angel_default", 9, 9)
get_bucket("angel_order", 4, 4)
get_bucket("angel_quote", 8, 8)
get_bucket("dashboard_api", 30, 30)
get_bucket("dashboard_post", 5, 5)


def fastapi_incoming(scope="dashboard_api", capacity=30, refill_rate=30, per_ip=True):
    from fastapi import HTTPException, Request
    def make_dep(request: Request):
        ip = request.client.host if request.client else "unknown"
        if per_ip:
            bucket = get_ip_bucket(ip, scope, capacity, refill_rate)
        else:
            bucket = get_bucket(scope, capacity, refill_rate)
        if not bucket.try_consume(1):
            bucket.total_429 += 1
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limit_exceeded", "scope": scope,
                        "retry_after_ms": int(1000 / max(0.1, bucket.refill_rate))},
                headers={"Retry-After": "1"},
            )
        return True
    return make_dep
