"""Phase 9.8g.8 (audit B8): Fetch 1-min FUT candles for BANKNIFTY/NIFTY/MIDCPNIFTY.

Pre-9.8g.8 the repo only shipped `fetch_history.py`, hardcoded to BANKNIFTY via
angel_adapter.AngelBroker (which reads only BANKNIFTY_FUT_TOKEN from .env).
The algo has been live-paper-trading NIFTY and MIDCPNIFTY since Phase 9.7AC
(~19 May 2026) WITHOUT BACKTEST VALIDATION on those symbols. Sacred Rule #19
violation in spirit. Sacred Rule #39 introduced in this commit to prevent
recurrence.

Usage:
    python tools/fetch_futures_data.py --symbol BANKNIFTY
    python tools/fetch_futures_data.py --symbol NIFTY
    python tools/fetch_futures_data.py --symbol MIDCPNIFTY
    python tools/fetch_futures_data.py --all --days 60

Tokens are read from .env (current monthly expiry):
    BANKNIFTY_FUT_TOKEN=66068
    NIFTY_FUT_TOKEN=66071
    MIDCPNIFTY_FUT_TOKEN=66070

LIMITATION: only fetches data within the current expiry's history window
(typically ~25 trading days). For multi-expiry stitching across months,
expired-token historical access is required (Tier B-0j scope).
"""
import os, time, logging, argparse, sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
load_dotenv(_REPO_ROOT / ".env")

import pyotp
from SmartApi import SmartConnect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("fetch_futures")

DATA_DIR = _REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

SYMBOLS = {
    "BANKNIFTY":  {"token_env": "BANKNIFTY_FUT_TOKEN",  "out": "BANKNIFTY_FUT_1min.parquet"},
    "NIFTY":      {"token_env": "NIFTY_FUT_TOKEN",      "out": "NIFTY_FUT_1min.parquet"},
    "MIDCPNIFTY": {"token_env": "MIDCPNIFTY_FUT_TOKEN", "out": "MIDCPNIFTY_FUT_1min.parquet"},
}


def _login():
    api_key = os.environ["ANGEL_API_KEY"]
    client_code = os.environ["ANGEL_CLIENT_CODE"]
    mpin = os.environ["ANGEL_MPIN"]
    totp_secret = os.environ["ANGEL_TOTP_SECRET"]
    smart = SmartConnect(api_key=api_key)
    totp = pyotp.TOTP(totp_secret).now()
    data = smart.generateSession(client_code, mpin, totp)
    if not data or not data.get("status"):
        raise RuntimeError(f"Angel login failed: {data}")
    log.info(f"Angel login OK. client={client_code}")
    return smart


def fetch_symbol(smart, symbol: str, days_back: int = 60):
    cfg = SYMBOLS[symbol]
    token = os.environ.get(cfg["token_env"])
    if not token:
        log.error(f"{cfg['token_env']} not set in .env -- skipping {symbol}")
        return None

    end = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
    start = end - timedelta(days=days_back)
    log.info(f"Fetching {symbol} (token={token}) {start.date()} -> {end.date()} (1-min)")

    all_rows = []
    cur = start
    while cur < end:
        chunk_end = min(cur + timedelta(days=25), end)
        params = {
            "exchange":    "NFO",
            "symboltoken": token,
            "interval":    "ONE_MINUTE",
            "fromdate":    cur.strftime("%Y-%m-%d %H:%M"),
            "todate":      chunk_end.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            resp = smart.getCandleData(params)
            if isinstance(resp, dict) and resp.get("status"):
                rows = resp.get("data") or []
                all_rows.extend(rows)
                log.info(f"  {cur.date()} -> {chunk_end.date()}: +{len(rows)} bars")
            else:
                log.warning(f"  {cur.date()} -> {chunk_end.date()} bad response: {resp}")
        except Exception as e:
            log.warning(f"  {cur.date()} -> {chunk_end.date()} failed: {e} -- sleeping 5s")
            time.sleep(5)
            continue
        cur = chunk_end
        time.sleep(1)

    if not all_rows:
        log.error(f"{symbol}: no candles returned. Check token, expiry, and market hours.")
        return None

    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.drop_duplicates("ts").set_index("ts").sort_index()
    df = df.between_time("09:15", "15:30")

    out_path = DATA_DIR / cfg["out"]
    df.to_parquet(out_path)
    log.info(f"{symbol}: saved {len(df):,} bars to {out_path}")
    log.info(f"{symbol}: date range {df.index.min()} -> {df.index.max()}")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Multi-symbol futures historical fetcher (Phase 9.8g.8 / audit B8)")
    ap.add_argument("--symbol", choices=sorted(SYMBOLS.keys()))
    ap.add_argument("--all", action="store_true", help="Fetch all three symbols sequentially")
    ap.add_argument("--days", type=int, default=60, help="Lookback in days (default 60)")
    args = ap.parse_args()

    if not args.symbol and not args.all:
        ap.error("must pass --symbol or --all")

    smart = _login()

    targets = sorted(SYMBOLS.keys()) if args.all else [args.symbol]
    for sym in targets:
        try:
            fetch_symbol(smart, sym, days_back=args.days)
        except Exception as e:
            log.error(f"{sym}: fetch failed: {e}")
        time.sleep(2)  # space requests between symbols


if __name__ == "__main__":
    main()
