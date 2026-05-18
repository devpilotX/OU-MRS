"""
Angel One SmartAPI adapter for OU-MRS.
Handles: login (MPIN + TOTP), historical candles, order placement, positions.
"""
import os, time, logging
from datetime import datetime, timedelta
from typing import Optional
import pyotp
from SmartApi import SmartConnect

log = logging.getLogger("angel")

import random as _random
import sys as p98f_rl_sys; p98f_rl_sys.path.insert(0, "/home/ubuntu/bots/ou-mrs/dashboard"); import rate_limit as p98f_rl

# --- _retry_v2 (2026-05-11) — rate-limit / auth-fail classification ---
_RATE_LIMIT_UNTIL = [0.0]  # shared epoch deadline across all AngelBroker instances
_RATE_LIMIT_SIGS = ("access rate", "exceeding", "exceed access", "rate limit")
_AUTH_FAIL_SIGS = ("invalid token", "session expired", "unauthorized",
                   "invalid_token", "token expired", "session is invalid")

def _is_rate_limit_err(err) -> bool:
    s = str(err).lower()
    return any(sig in s for sig in _RATE_LIMIT_SIGS)

def _is_auth_fail_err(err) -> bool:
    s = str(err).lower()
    return any(sig in s for sig in _AUTH_FAIL_SIGS)
# --- end _retry_v2 helpers ---


class AngelBroker:
    def __init__(self):
        self.api_key = os.environ["ANGEL_API_KEY"]
        self.client_code = os.environ["ANGEL_CLIENT_CODE"]
        self.mpin = os.environ["ANGEL_MPIN"]
        self.totp_secret = os.environ["ANGEL_TOTP_SECRET"]
        self.symbol = os.environ["BANKNIFTY_FUT_SYMBOL"]
        self.token = os.environ["BANKNIFTY_FUT_TOKEN"]
        self.smart: Optional[SmartConnect] = None
        self.feed_token = None
        self.jwt_token = None
        self.session_time: Optional[datetime] = None

    # ---------- AUTH ----------
    def login(self):
        self.smart = SmartConnect(api_key=self.api_key)
        totp = pyotp.TOTP(self.totp_secret).now()
        data = self.smart.generateSession(self.client_code, self.mpin, totp)
        if not data or not data.get("status"):
            raise RuntimeError(f"Angel login failed: {data}")
        self.jwt_token = data["data"]["jwtToken"]
        self.feed_token = self.smart.getfeedToken()
        self.session_time = datetime.now()
        log.info(f"Angel login OK. client={self.client_code}")
        return self

    def ensure_session(self):
        if not self.session_time or (datetime.now() - self.session_time).total_seconds() > 6 * 3600:
            log.info("Refreshing Angel session")
            self.login()

    # ---------- MARKET DATA ----------
    def get_candles(self, start_dt, end_dt, interval):
        """_retry_v2 (2026-05-11): rate-limit aware retry.
        - Rate-limit (Angel 'access rate' / 'exceeding'): long backoff (30/60/120/240s + jitter),
          NO re-login. Re-login during rate-limit storm just consumes more quota.
        - Auth failure (token/session expired): re-login + short retry.
        - Other (network/parse): short backoff, NO re-login.
        - Pre-call jitter 0-2.5s to de-sync from other Angel-API consumers (tick_capture, dashboard).
        - Global cool-down: if ANY recent call hit rate-limit, all callers wait it out.
        """
        # Honor global cool-down set by any prior rate-limited call
        now_ts = time.time()
        if now_ts < _RATE_LIMIT_UNTIL[0]:
            cool = _RATE_LIMIT_UNTIL[0] - now_ts
            log.warning(f"[9.7X] global rate-limit cool-down active for {cool:.1f}s -- returning [] so caller falls back to cached candles")
            return []
        # De-sync jitter
        time.sleep(_random.uniform(0.0, 2.5))

        params = {
            "exchange": getattr(self, "exchange", "NFO"),
            "symboltoken": self.token,
            "interval": interval,
            "fromdate": start_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": end_dt.strftime("%Y-%m-%d %H:%M"),
        }
        last_err = None
        for attempt in range(2):  # Phase 9.7M: 4->2 retries to cap quota burn at 90s vs 450s
            try:
                p98f_rl.get_bucket("angel_quote").consume(block=True)
                resp = self.smart.getCandleData(params)
                if isinstance(resp, dict) and resp.get("status"):
                    return resp.get("data") or []
                last_err = RuntimeError(f"bad response: {resp}")
            except Exception as e:
                last_err = e

            is_rate = _is_rate_limit_err(last_err)
            is_auth = _is_auth_fail_err(last_err)

            if is_rate:
                # Phase 9.7X: set global cool-down then return [] (no sleep).
                # Caller falls back to cached candles via existing 'if not rows' path.
                wait = (90 * (2 ** attempt)) + _random.uniform(0, 5)
                _RATE_LIMIT_UNTIL[0] = time.time() + wait
                log.warning(f"[9.7X] get_candles RATE-LIMIT (attempt {attempt+1}): cool-down {wait:.1f}s set, returning [] (caller uses cached candles)")
                return []
            elif is_auth:
                wait = 2 * (attempt + 1)
                log.warning(f"get_candles attempt {attempt+1}/4 AUTH-FAIL: {last_err}; "
                            f"relogin + retry in {wait}s")
                time.sleep(wait)
                try:
                    self.login()
                    log.info("re-authenticated via login()")
                except Exception as le:
                    log.warning(f"re-login failed: {le}")
            else:
                wait = 2 ** (attempt + 1)
                log.warning(f"get_candles attempt {attempt+1}/4 OTHER: {last_err}; "
                            f"retry in {wait}s (no relogin for unknown errors)")
                time.sleep(wait)
                # NOTE: no relogin for unknown errors — preserve quota

        raise last_err or RuntimeError("get_candles failed after 4 retries")

    # ---------- ORDERS ----------
    def place_market(self, side: str, qty: int) -> str:
        self.ensure_session()
        params = {
            "variety": "NORMAL",
            "tradingsymbol": self.symbol,
            "symboltoken": str(self.token),
            "transactiontype": side,
            "exchange": "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": "0",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(qty),
        }
        p98f_rl.get_bucket("angel_order").consume(block=True)
        oid = self.smart.placeOrder(params)
        log.info(f"Angel order placed: {side} {qty} -> {oid}")
        return oid

    def positions(self):
        self.ensure_session()
        return self.smart.position()

    def place_stoploss_limit(self, side: str, qty: int, trigger_px: float, limit_px: float) -> str:
        """Phase 8d: server-side SL that survives bot crash. STOPLOSS_LIMIT variant."""
        self.ensure_session()
        params = {
            "variety": "STOPLOSS",
            "tradingsymbol": self.symbol,
            "symboltoken": str(self.token),
            "transactiontype": side,
            "exchange": "NFO",
            "ordertype": "STOPLOSS_LIMIT",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": f"{limit_px:.2f}",
            "triggerprice": f"{trigger_px:.2f}",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(qty),
        }
        p98f_rl.get_bucket("angel_order").consume(block=True)
        oid = self.smart.placeOrder(params)
        log.info(f"Angel SL-LIMIT: {side} {qty} trig={trigger_px:.2f} lim={limit_px:.2f} -> {oid}")
        return oid

    def get_order_status(self, order_id: str) -> dict:
        """Phase 8d.1: query single-order status.
        Returns {'status': 'open'|'complete'|'cancelled'|'rejected'|'unknown', 'raw': dict}."""
        self.ensure_session()
        try:
            resp = self.smart.individual_order_details(order_id)
            if not resp:
                return {"status": "unknown", "raw": {}}
            data = resp.get("data") or {}
            raw_status = str(data.get("orderstatus") or data.get("status") or "").lower().strip()
            if raw_status in ("open", "trigger pending", "pending", "open pending"):
                norm = "open"
            elif raw_status in ("complete", "completed", "executed", "traded"):
                norm = "complete"
            elif raw_status in ("cancelled", "canceled"):
                norm = "cancelled"
            elif raw_status in ("rejected", "reject"):
                norm = "rejected"
            else:
                norm = raw_status or "unknown"
            return {"status": norm, "raw": data}
        except Exception as e:
            log.warning(f"get_order_status({order_id}) failed: {e}")
            return {"status": "unknown", "raw": {"error": str(e)}}

    def cancel_order(self, order_id: str, variety: str = "STOPLOSS") -> dict:
        """Phase 8d: cancel pending SL on normal TIME/TARGET/EOD exit."""
        self.ensure_session()
        try:
            resp = self.smart.cancelOrder(order_id, variety)
            log.info(f"Angel cancel {order_id}: {resp}")
            return resp
        except Exception as e:
            log.warning(f"cancel_order {order_id} failed: {e}")
            return {"status": False, "message": str(e)}

    def open_orders(self) -> list:
        """Phase 8d: list pending orders for startup reconciliation."""
        self.ensure_session()
        try:
            resp = self.smart.orderBook()
            if not resp or not resp.get("status"):
                return []
            return [o for o in (resp.get("data") or [])
                    if str(o.get("orderstatus", "")).lower() in ("open", "pending", "trigger pending")]
        except Exception as e:
            log.warning(f"orderBook failed: {e}")
            return []

    def square_off_all(self):
        pos = self.positions()
        if not pos or not pos.get("data"):
            return
        for p in pos["data"]:
            net = int(p.get("netqty", 0))
            if net == 0:
                continue
            side = "SELL" if net > 0 else "BUY"
            self.place_market(side, abs(net))
