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
