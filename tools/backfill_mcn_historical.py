"""
Phase 9.7V: MIDCPNIFTY (NIFTY MID SELECT) INDEX 1-min backfill via SmartAPI getCandleData.
Abandons FUT chain lookup (Angel doesn't index expired contracts).
INDEX has no expiry rolls -> single token, continuous series.
Output parquet is drop-in for backtest.py regime revalidation.
"""
import os, time, logging, sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from SmartApi import SmartConnect
import pyotp
import sys as p98f_rl_sys; p98f_rl_sys.path.insert(0, "/home/ubuntu/bots/ou-mrs/dashboard"); import rate_limit as p98f_rl

load_dotenv()
API_KEY     = os.getenv("ANGEL_API_KEY")
CLIENT_CODE = os.getenv("ANGEL_CLIENT_CODE")
MPIN        = os.getenv("ANGEL_MPIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

# BANKNIFTY INDEX (cash) - permanent, continuous, no rolls
INDEX_TOKEN    = "99926074"
INDEX_EXCHANGE = "NSE"
INDEX_SYMBOL   = "NIFTY MID SELECT"

DATA_PATH  = Path("data/MIDCPNIFTY_INDEX_1min.parquet")
START_DATE = datetime(2025, 10, 1)
END_DATE   = datetime.now()
CHUNK_DAYS = 30  # Angel's getCandleData caps at ~30 days per call for 1-min
RATE_SLEEP = 1.5  # sec between calls (well under 1/sec rate limit)

def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

def login():
    smart = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    resp = smart.generateSession(CLIENT_CODE, MPIN, totp)
    if not resp.get("status"):
        raise RuntimeError(f"Login failed: {resp}")
    log("Login OK")
    return smart

def fetch_chunk(smart, start, end):
    """Fetch one chunk of 1-min candles. Returns list of [ts, o, h, l, c, v]."""
    params = {
        "exchange":    INDEX_EXCHANGE,
        "symboltoken": INDEX_TOKEN,
        "interval":    "ONE_MINUTE",
        "fromdate":    start.strftime("%Y-%m-%d %H:%M"),
        "todate":      end.strftime("%Y-%m-%d %H:%M"),
    }
    p98f_rl.get_bucket("angel_quote").consume(block=True)
    resp = smart.getCandleData(params)
    if not resp or not resp.get("status"):
        raise RuntimeError(f"getCandleData failed: {resp}")
    return resp.get("data") or []

def main():
    log("=== Phase 8g v6 backfill START (INDEX mode) ===")
    log(f"Target: {INDEX_SYMBOL} token={INDEX_TOKEN} @ {INDEX_EXCHANGE}")
    log(f"Window: {START_DATE:%Y-%m-%d} -> {END_DATE:%Y-%m-%d}")

    smart = login()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    cur = START_DATE.replace(hour=9, minute=15, second=0, microsecond=0)
    while cur < END_DATE:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS), END_DATE)
        log(f"Fetch {cur:%Y-%m-%d} -> {chunk_end:%Y-%m-%d} ...")
        try:
            rows = fetch_chunk(smart, cur, chunk_end)
            log(f"  got {len(rows)} bars")
            all_rows.extend(rows)
        except Exception as e:
            log(f"  ERR: {e}  (sleeping 5s then advancing)")
            time.sleep(5)
        cur = chunk_end
        time.sleep(RATE_SLEEP)

    if not all_rows:
        log("ERROR: no bars collected.")
        sys.exit(1)

    log(f"Total raw bars collected: {len(all_rows)}")
    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df = df.set_index("ts")

    # Filter to NSE market hours (09:15-15:30 IST, Mon-Fri)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
    df = df[(df.index.time >= pd.Timestamp("09:15").time()) &
            (df.index.time <= pd.Timestamp("15:30").time())]
    df = df[df.index.dayofweek < 5]

    log(f"After dedup + market-hours filter: {len(df)} bars")
    log(f"Date range: {df.index.min()} -> {df.index.max()}")
    log(f"Trading days: {df.index.normalize().nunique()}")

    df.to_parquet(DATA_PATH)
    log(f"WROTE {DATA_PATH} ({DATA_PATH.stat().st_size/1024:.1f} KB)")
    log("=== Phase 8g v6 backfill DONE ===")

if __name__ == "__main__":
    main()
