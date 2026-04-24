"""Fetch 6 months of 1-min BankNifty futures candles via SmartAPI.
   Caches to data/BANKNIFTY_SPOT_3min.parquet."""
import os, time, logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path as _P
from angel_adapter import AngelBroker

load_dotenv(_P(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("fetch")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
OUT = DATA_DIR / "BANKNIFTY_SPOT_3min.parquet"

def main():
    broker = AngelBroker().login()
    end = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
    start = end - timedelta(days=180)
    all_rows = []
    cur = start
    while cur < end:
        chunk_end = min(cur + timedelta(days=25), end)
        log.info(f"Fetching {cur.date()} -> {chunk_end.date()}")
        try:
            rows = broker.get_candles(cur, chunk_end, interval="THREE_MINUTE")
            all_rows.extend(rows)
        except Exception as e:
            log.warning(f"Chunk failed: {e} -- retrying in 5s")
            time.sleep(5)
            continue
        cur = chunk_end
        time.sleep(1)

    if not all_rows:
        log.error("No candles returned. Check symbol/token and market hours.")
        return

    df = pd.DataFrame(all_rows, columns=["ts","open","high","low","close","volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.drop_duplicates("ts").set_index("ts").sort_index()
    df = df.between_time("09:15", "15:30")
    df.to_parquet(OUT)
    log.info(f"Saved {len(df):,} bars to {OUT}")
    log.info(f"Date range: {df.index.min()} -> {df.index.max()}")

if __name__ == "__main__":
    main()
