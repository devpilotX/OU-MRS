"""Phase 9.6: Angel SmartAPI WebSocket V2 tick pump.

Runs as a daemon thread inside the dashboard process. Subscribes to
BANKNIFTY/NIFTY/MIDCPNIFTY FUT tokens (NFO=2, mode=1 LTP), publishes ticks
to the in-memory TickBroker for SSE fan-out.

Failures are non-fatal: if Angel auth or websocket fails, the dashboard
keeps serving REST routes. Reconnects with 5s backoff.
"""
import os
import time
import threading
import logging
from typing import Optional, Dict

import pyotp

from dashboard.tick_broker import broker
import sys as p98f_rl_sys; p98f_rl_sys.path.insert(0, "/home/ubuntu/bots/ou-mrs/dashboard"); import rate_limit as p98f_rl

log = logging.getLogger("ws_tick_pump")

NFO_EXCHANGE_TYPE = 2
LTP_MODE = 1


def _build_token_map() -> Dict[str, str]:
    """env token -> friendly symbol code."""
    m: Dict[str, str] = {}
    for env_key, code in (
        ("BANKNIFTY_FUT_TOKEN", "BNF"),
        ("NIFTY_FUT_TOKEN", "NF"),
        ("MIDCPNIFTY_FUT_TOKEN", "MCN"),  # Phase 9.7O-dash: FNF -> MIDCPNIFTY
    ):
        tok = (os.environ.get(env_key) or "").strip()
        if tok:
            m[tok] = code
    return m


class WsTickPump:
    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()
        self.token_map = _build_token_map()
        self._iter = 0

    def start(self) -> None:
        # Phase 9.7L: env gate releases Angel REST quota for bot
        import os as _os_p97L
        if _os_p97L.environ.get("DASHBOARD_LIVE_TICK", "1") != "1":
            log.warning("[ws_pump] disabled via DASHBOARD_LIVE_TICK=0 env var")
            return
        if not self.token_map:
            log.warning("[ws_pump] no FUT tokens in env; pump disabled")
            return
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(
            target=self._run_forever, daemon=True, name="ws-tick-pump"
        )
        self.thread.start()
        log.info("[ws_pump] started, tokens=%s", list(self.token_map.keys()))

    def stop(self) -> None:
        self.stop_flag.set()

    def _run_forever(self) -> None:
        while not self.stop_flag.is_set():
            self._iter += 1
            try:
                self._connect_and_pump()
            except Exception as e:
                log.exception("[ws_pump] iter=%d crashed: %s", self._iter, e)
            if not self.stop_flag.is_set():
                time.sleep(5.0)

    def _login(self):
        from SmartApi import SmartConnect

        api_key = os.environ["ANGEL_API_KEY"]
        client_code = os.environ["ANGEL_CLIENT_CODE"]
        mpin = os.environ["ANGEL_MPIN"]
        totp_secret = os.environ["ANGEL_TOTP_SECRET"]
        smart = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        p98f_rl.get_bucket("angel_default").consume(block=True)
        sess = smart.generateSession(client_code, mpin, totp)
        feed_token = smart.getfeedToken()
        auth_token = sess["data"]["jwtToken"]
        return api_key, client_code, auth_token, feed_token

    def _connect_and_pump(self) -> None:
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        api_key, client_code, auth_token, feed_token = self._login()
        log.info("[ws_pump] angel login OK client=%s iter=%d", client_code, self._iter)

        sws = SmartWebSocketV2(auth_token, api_key, client_code, feed_token)

        def on_open(wsapp):
            tokens = list(self.token_map.keys())
            sws.subscribe(
                "ou-mrs-ticks",
                LTP_MODE,
                [{"exchangeType": NFO_EXCHANGE_TYPE, "tokens": tokens}],
            )
            log.info("[ws_pump] subscribed to %d tokens", len(tokens))

        def on_data(wsapp, message):
            try:
                if not isinstance(message, dict):
                    return
                tok = str(message.get("token", ""))
                ltp_raw = message.get("last_traded_price")
                if ltp_raw is None or not tok:
                    return
                ltp = float(ltp_raw) / 100.0
                sym = self.token_map.get(tok, tok)
                tick = {
                    "symbol": sym,
                    "token": tok,
                    "ltp": ltp,
                    "ts": int(time.time() * 1000),
                }
                broker.publish_threadsafe(tick)
            except Exception:
                log.exception("[ws_pump] on_data parse failure")

        def on_error(wsapp, error):
            log.error("[ws_pump] on_error: %s", error)

        def on_close(wsapp):
            log.warning("[ws_pump] connection closed")

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close
        sws.connect()


pump = WsTickPump()
