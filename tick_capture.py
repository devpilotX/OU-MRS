#!/usr/bin/env python3
"""Phase 9.9a: tick capture service. Angel WS to parquet, hourly rotation."""
import os, json, time, logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).parent
(BASE / "data" / "ticks").mkdir(parents=True, exist_ok=True)
(BASE / "logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [tick_capture] %(message)s",
    handlers=[
        logging.FileHandler(BASE / "logs" / "tick_capture.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("tick_capture")

INSTRUMENTS = {
    "BNF": os.environ.get("BANKNIFTY_FUT_TOKEN", "66068"),
    "NF":  os.environ.get("NIFTY_FUT_TOKEN", "66071"),
}
TOKEN_TO_SYM = {v: k for k, v in INSTRUMENTS.items()}

BUFFER = defaultdict(list)
LAST_FLUSH = [time.time()]
FLUSH_SEC = 60
MAX_BUF = 10000


def flush():
    if not any(BUFFER.values()):
        return
    now = datetime.now()
    day_str = now.strftime("%Y-%m-%d")
    hour_str = now.strftime("%H")
    day_dir = BASE / "data" / "ticks" / day_str
    day_dir.mkdir(exist_ok=True)
    total = 0
    for sym, ticks in list(BUFFER.items()):
        if not ticks:
            continue
        df = pd.DataFrame(ticks)
        out = day_dir / (sym + "_" + hour_str + ".parquet")
        if out.exists():
            existing = pd.read_parquet(out)
            df = pd.concat([existing, df], ignore_index=True)
        df.to_parquet(out, compression="snappy")
        total += len(ticks)
        BUFFER[sym] = []
    LAST_FLUSH[0] = time.time()
    log.info("flushed " + str(total) + " ticks")


def on_data(_wsapp, message):
    try:
        data = message if isinstance(message, dict) else json.loads(message)
        token = str(data.get("token") or data.get("tk") or "")
        sym = TOKEN_TO_SYM.get(token)
        if not sym:
            return
        tick = {
            "ts": datetime.now().isoformat(),
            "ts_unix": time.time(),
            "ltp": data.get("last_traded_price") or data.get("ltp"),
            "vol": data.get("volume_traded") or data.get("v"),
            "bid": data.get("best_bid_price"),
            "ask": data.get("best_ask_price"),
        }
        BUFFER[sym].append(tick)
        n = sum(len(v) for v in BUFFER.values())
        if n > MAX_BUF or (time.time() - LAST_FLUSH[0]) > FLUSH_SEC:
            flush()
    except Exception as e:
        log.error("on_data error: " + str(e))


def on_open(wsapp):
    log.info("WS open, subscribing")
    tokens = [{"exchangeType": 2, "tokens": list(INSTRUMENTS.values())}]
    wsapp.subscribe("p99a_capture", 1, tokens)


def on_error(_w, e):
    log.error("WS error: " + str(e))


def on_close(_w, code, reason):
    log.warning("WS closed: " + str(code) + " " + str(reason))
    flush()


def main():
    from SmartApi.smartConnect import SmartConnect
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    import pyotp
    smart = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
    totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
    sess = smart.generateSession(
        os.environ["ANGEL_CLIENT_CODE"],
        os.environ["ANGEL_MPIN"],
        totp,
    )
    auth = sess["data"]["jwtToken"]
    feed = smart.getfeedToken()
    log.info("Angel login OK")
    sws = SmartWebSocketV2(
        auth,
        os.environ["ANGEL_API_KEY"],
        os.environ["ANGEL_CLIENT_CODE"],
        feed,
    )
    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = on_error
    sws.on_close = on_close
    sws.connect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("shutdown")
        flush()
    except Exception as e:
        log.exception("fatal: " + str(e))
        flush()
        raise
