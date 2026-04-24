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
        # _retry_v1 — Angel candle API is flaky; retry 4x with backoff + relogin
        import time, logging
        params = {
            "exchange": getattr(self, "exchange", "NFO"),
            "symboltoken": self.token,
            "interval": interval,
            "fromdate": start_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": end_dt.strftime("%Y-%m-%d %H:%M"),
        }
        log = logging.getLogger()
        last_err = None
        for attempt in range(4):
            try:
                resp = self.smart.getCandleData(params)
                if isinstance(resp, dict) and resp.get("status"):
                    return resp.get("data") or []
                last_err = RuntimeError(f"bad response: resp")
            except Exception as e:
                last_err = e
            wait = 2 ** (attempt + 1)  # 2, 4, 8, 16 seconds
            log.warning(f"get_candles attempt attempt+1/4 failed: last_err; retry in waits")
            time.sleep(wait)
            if attempt >= 1:
                for mname in ("login", "_login", "connect", "reauth"):
                    if hasattr(self, mname):
                        try:
                            getattr(self, mname)()
                            log.info(f"re-authenticated via mname()")
                            break
                        except Exception as le:
                            log.warning(f"re-auth via mname failed: le")
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
